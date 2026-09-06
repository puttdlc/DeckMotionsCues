"""A transparent, click-through, always-on-top X11 overlay for gamescope.

This is the piece that gets pixels on top of a running game.  The approach is
the one gamescope itself defines and that Steam's own performance overlay
uses: create an ARGB window on the gamescope Xwayland display and set the
``GAMESCOPE_EXTERNAL_OVERLAY`` property on it.  gamescope then promotes that
window to a dedicated overlay plane composited above the game.

Implementation notes that are easy to get wrong:

* **ctypes prototypes are declared explicitly.**  On x86-64, ``Window``,
  ``Atom`` and ``Colormap`` are 64-bit; leaving ctypes to assume ``int``
  silently truncates XIDs and produces ``BadWindow`` errors that look like
  logic bugs.
* **Depth-32 visual + its own colormap.**  A depth-32 TrueColor visual is what
  gives per-pixel alpha; it needs a matching colormap and a border pixel, or
  ``XCreateWindow`` fails with ``BadMatch``.
* **Empty input region.**  An XFixes input shape with zero rectangles makes
  the window invisible to touch, trackpad and clicks, so the overlay cannot
  interfere with gameplay or gyro aiming.
* **Not override-redirect.**  gamescope classifies override-redirect windows
  separately; the overlay must be a normal managed window for the external
  overlay path to pick it up.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from typing import Any, Dict, List, Optional, Tuple

# -- X protocol constants ---------------------------------------------------
INPUT_OUTPUT = 1
TRUE_COLOR = 4
ALLOC_NONE = 0
Z_PIXMAP = 2
PROP_MODE_REPLACE = 0

XA_CARDINAL = 6
XA_STRING = 31

CW_BACK_PIXEL = 1 << 1
CW_BORDER_PIXEL = 1 << 3
CW_OVERRIDE_REDIRECT = 1 << 9
CW_EVENT_MASK = 1 << 11
CW_COLORMAP = 1 << 13

EXPOSURE_MASK = 1 << 15
STRUCTURE_NOTIFY_MASK = 1 << 17

SHAPE_INPUT = 2

GAMESCOPE_OVERLAY_PROPERTY = b"GAMESCOPE_EXTERNAL_OVERLAY"
NET_WM_OPACITY_PROPERTY = b"_NET_WM_WINDOW_OPACITY"

#: Atoms gamescope defines on its own Xwayland servers.  Their presence is how
#: we work out which DISPLAY is the compositor's, rather than guessing ":0".
GAMESCOPE_MARKER_ATOMS = (
    b"GAMESCOPE_FOCUSED_WINDOW",
    b"GAMESCOPE_FOCUSED_APP",
    b"GAMESCOPE_FOCUSABLE_WINDOWS",
    b"GAMESCOPE_EXTERNAL_OVERLAY",
)


class X11Error(RuntimeError):
    pass


class XVisualInfo(ctypes.Structure):
    _fields_ = [
        ("visual", ctypes.c_void_p),
        ("visualid", ctypes.c_ulong),
        ("screen", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("class_", ctypes.c_int),
        ("red_mask", ctypes.c_ulong),
        ("green_mask", ctypes.c_ulong),
        ("blue_mask", ctypes.c_ulong),
        ("colormap_size", ctypes.c_int),
        ("bits_per_rgb", ctypes.c_int),
    ]


class XSetWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("background_pixmap", ctypes.c_ulong),
        ("background_pixel", ctypes.c_ulong),
        ("border_pixmap", ctypes.c_ulong),
        ("border_pixel", ctypes.c_ulong),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("cursor", ctypes.c_ulong),
    ]


class XRectangle(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_short),
        ("y", ctypes.c_short),
        ("width", ctypes.c_ushort),
        ("height", ctypes.c_ushort),
    ]


class XErrorEvent(ctypes.Structure):
    """Field order matters: ``resourceid`` precedes ``serial`` in Xlib."""

    _fields_ = [
        ("type", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong),
        ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte),
        ("request_code", ctypes.c_ubyte),
        ("minor_code", ctypes.c_ubyte),
    ]


XErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                 ctypes.POINTER(XErrorEvent))


def _load(name: str, fallback: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    try:
        return ctypes.CDLL(path or fallback)
    except OSError as exc:  # pragma: no cover - depends on host libraries
        raise X11Error(f"cannot load lib{name}: {exc}") from exc


class Xlib:
    """Lazily loaded libX11 / libXfixes bindings with correct prototypes."""

    _instance: Optional["Xlib"] = None

    def __init__(self) -> None:
        self.x11 = _load("X11", "libX11.so.6")
        #: Kept so the overlay can explain *why* input pass-through is
        #: unavailable rather than just reporting that it is.
        self.xfixes_error = ""
        try:
            self.xfixes: Optional[ctypes.CDLL] = _load("Xfixes", "libXfixes.so.3")
        except X11Error as exc:
            self.xfixes = None
            self.xfixes_error = str(exc)

        x = self.x11
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XCloseDisplay.restype = ctypes.c_int
        x.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x.XDefaultScreen.restype = ctypes.c_int
        x.XRootWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XRootWindow.restype = ctypes.c_ulong
        x.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDisplayWidth.restype = ctypes.c_int
        x.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDisplayHeight.restype = ctypes.c_int
        x.XMatchVisualInfo.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.POINTER(XVisualInfo)]
        x.XMatchVisualInfo.restype = ctypes.c_int
        x.XCreateColormap.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.c_void_p, ctypes.c_int]
        x.XCreateColormap.restype = ctypes.c_ulong
        x.XCreateWindow.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_uint, ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(XSetWindowAttributes),
        ]
        x.XCreateWindow.restype = ctypes.c_ulong
        x.XDestroyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ]
        x.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                ctypes.c_ulong, ctypes.c_void_p]
        x.XCreateGC.restype = ctypes.c_void_p
        x.XFreeGC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        x.XCreateImage.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
            ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int,
        ]
        x.XCreateImage.restype = ctypes.c_void_p
        x.XPutImage.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint, ctypes.c_uint,
        ]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XStoreName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p]
        x.XPending.argtypes = [ctypes.c_void_p]
        x.XPending.restype = ctypes.c_int
        x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        x.XConnectionNumber.argtypes = [ctypes.c_void_p]
        x.XConnectionNumber.restype = ctypes.c_int
        x.XSetErrorHandler.argtypes = [XErrorHandler]
        x.XSetErrorHandler.restype = ctypes.c_void_p
        x.XGetErrorText.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_char_p, ctypes.c_int]
        x.XGetErrorText.restype = ctypes.c_int

        if self.xfixes is not None:
            f = self.xfixes
            f.XFixesQueryExtension.argtypes = [ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_int),
                                               ctypes.POINTER(ctypes.c_int)]
            f.XFixesQueryExtension.restype = ctypes.c_int
            f.XFixesCreateRegion.argtypes = [ctypes.c_void_p,
                                             ctypes.POINTER(XRectangle), ctypes.c_int]
            f.XFixesCreateRegion.restype = ctypes.c_ulong
            f.XFixesSetWindowShapeRegion.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_ulong,
            ]
            f.XFixesDestroyRegion.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

    @classmethod
    def get(cls) -> "Xlib":
        if cls._instance is None:
            cls._instance = Xlib()
        return cls._instance


def candidate_displays(preferred: str = "auto") -> List[str]:
    """Displays to try, best first."""

    if preferred and preferred != "auto":
        return [preferred]
    ordered: List[str] = []
    env = os.environ.get("DISPLAY")
    if env:
        ordered.append(env)
    for index in range(4):
        name = f":{index}"
        if name not in ordered:
            ordered.append(name)
    return ordered


def _is_gamescope_display(lib: Xlib, display: ctypes.c_void_p) -> bool:
    """True if this X server looks like gamescope's Xwayland."""

    for atom_name in GAMESCOPE_MARKER_ATOMS:
        # only_if_exists=True: a non-zero result means gamescope interned it.
        if lib.x11.XInternAtom(display, atom_name, 1):
            return True
    return False


def probe_displays(preferred: str = "auto") -> List[Dict[str, Any]]:
    """Report which X displays are reachable and which look like gamescope."""

    try:
        lib = Xlib.get()
    except X11Error as exc:
        return [{"display": "-", "open": False, "gamescope": False, "detail": str(exc)}]

    results: List[Dict[str, Any]] = []
    for name in candidate_displays(preferred):
        handle = lib.x11.XOpenDisplay(name.encode())
        if not handle:
            results.append({"display": name, "open": False, "gamescope": False,
                            "detail": "cannot connect"})
            continue
        try:
            screen = lib.x11.XDefaultScreen(handle)
            width = lib.x11.XDisplayWidth(handle, screen)
            height = lib.x11.XDisplayHeight(handle, screen)
            gamescope = _is_gamescope_display(lib, handle)
            results.append({
                "display": name,
                "open": True,
                "gamescope": gamescope,
                "detail": f"{width}x{height}" + (" (gamescope)" if gamescope else ""),
            })
        finally:
            lib.x11.XCloseDisplay(handle)
    return results


class OverlayWindow:
    """A full-screen transparent overlay that gamescope composites over games."""

    def __init__(self, display: str = "auto", title: str = "Motion Cues overlay",
                 problems: Any = None) -> None:
        self.requested_display = display
        self.title = title
        #: Optional :class:`motioncues.problems.ProblemLog`.
        self.problems = problems
        self.click_through = False
        self._error_handler: Any = None
        self.lib = Xlib.get()
        self.display: Optional[ctypes.c_void_p] = None
        self.display_name = ""
        self.window = 0
        self.gc: Optional[ctypes.c_void_p] = None
        self.width = 0
        self.height = 0
        self.is_gamescope = False
        self.mapped = False
        self._visual: Optional[ctypes.c_void_p] = None
        self._images: Dict[Tuple[int, int], Tuple[ctypes.c_void_p, Any]] = {}

    # ------------------------------------------------------------------
    def open(self) -> None:
        lib = self.lib
        last_error = "no display could be opened"
        chosen = None

        # Prefer a display that is demonstrably gamescope's; fall back to the
        # first one that opens at all so desktop mode still works.
        fallback = None
        for name in candidate_displays(self.requested_display):
            handle = lib.x11.XOpenDisplay(name.encode())
            if not handle:
                last_error = f"cannot connect to {name}"
                continue
            if _is_gamescope_display(lib, handle):
                chosen = (name, handle, True)
                break
            if fallback is None:
                fallback = (name, handle, False)
            else:
                lib.x11.XCloseDisplay(handle)

        if chosen is None:
            chosen = fallback
        if chosen is None:
            raise X11Error(last_error)

        self.display_name, self.display, self.is_gamescope = chosen
        self._install_error_handler()

        screen = lib.x11.XDefaultScreen(self.display)
        root = lib.x11.XRootWindow(self.display, screen)
        self.width = lib.x11.XDisplayWidth(self.display, screen)
        self.height = lib.x11.XDisplayHeight(self.display, screen)

        visual_info = XVisualInfo()
        if not lib.x11.XMatchVisualInfo(self.display, screen, 32, TRUE_COLOR,
                                        ctypes.byref(visual_info)):
            raise X11Error("no 32-bit TrueColor visual: the X server cannot do "
                           "per-pixel alpha, so a transparent overlay is impossible")
        self._visual = visual_info.visual

        colormap = lib.x11.XCreateColormap(self.display, root,
                                           visual_info.visual, ALLOC_NONE)

        attributes = XSetWindowAttributes()
        attributes.background_pixel = 0  # fully transparent
        attributes.border_pixel = 0
        attributes.colormap = colormap
        attributes.override_redirect = 0
        attributes.event_mask = EXPOSURE_MASK | STRUCTURE_NOTIFY_MASK

        self.window = lib.x11.XCreateWindow(
            self.display, root, 0, 0, self.width, self.height, 0, 32,
            INPUT_OUTPUT, visual_info.visual,
            CW_BACK_PIXEL | CW_BORDER_PIXEL | CW_COLORMAP | CW_EVENT_MASK
            | CW_OVERRIDE_REDIRECT,
            ctypes.byref(attributes),
        )
        if not self.window:
            raise X11Error("XCreateWindow failed")

        lib.x11.XStoreName(self.display, self.window, self.title.encode())
        self._set_cardinal(GAMESCOPE_OVERLAY_PROPERTY, 1)
        # Maximum opacity: gamescope ranks competing external-overlay windows
        # by opacity, so an explicit 0xFFFFFFFF is how we win the slot from a
        # hidden mangoapp that has faded itself out.
        self._set_cardinal(NET_WM_OPACITY_PROPERTY, 0xFFFFFFFF)

        # An overlay that is not click-through would eat touches and trackpad
        # input meant for the game.  Refuse to exist rather than do that.
        self.click_through = self._set_click_through()
        if not self.click_through:
            self.close()
            raise X11Error(
                "refusing to map the overlay: input pass-through could not be "
                "established, and a full-screen window without it would "
                "swallow touch and trackpad input"
            )

        if not self.is_gamescope:
            self._report(
                "Overlay is not on the gamescope display",
                f"The overlay was created on {self.display_name}, which does "
                "not advertise gamescope's atoms, so it will not appear over "
                "running games.",
                severity="warning",
                hint="This is normal in desktop mode. In Game Mode, try "
                     "Restart overlay process under Advanced.",
            )

        self.gc = lib.x11.XCreateGC(self.display, self.window, 0, None)
        if not self.gc:
            raise X11Error("XCreateGC failed")

        lib.x11.XFlush(self.display)

    # ------------------------------------------------------------------
    def _set_cardinal(self, name: bytes, value: int) -> None:
        atom = self.lib.x11.XInternAtom(self.display, name, 0)
        payload = (ctypes.c_uint32 * 1)(value & 0xFFFFFFFF)
        self.lib.x11.XChangeProperty(
            self.display, self.window, atom, XA_CARDINAL, 32,
            PROP_MODE_REPLACE, ctypes.cast(payload, ctypes.c_void_p), 1,
        )

    def _report(self, title: str, detail: str = "", severity: str = "error",
                hint: str = "") -> None:
        if self.problems is not None:
            self.problems.record("overlay/x11", title, detail,
                                 severity=severity, hint=hint)

    def _install_error_handler(self) -> None:
        """Route asynchronous Xlib protocol errors into the problem log.

        Xlib's default handler writes to stderr and carries on, so a stream of
        ``BadMatch`` or ``BadDrawable`` errors would otherwise be invisible to
        the user while the overlay quietly drew nothing.
        """

        def handler(display: Any, event: Any) -> int:
            try:
                error = event.contents
                buffer = ctypes.create_string_buffer(160)
                self.lib.x11.XGetErrorText(display, error.error_code, buffer, 160)
                text = buffer.value.decode("utf-8", "replace")
                self._report(
                    "X server rejected a drawing request",
                    f"{text} (error {error.error_code}, "
                    f"request {error.request_code}.{error.minor_code}, "
                    f"resource 0x{error.resourceid:x})",
                    hint="Try Restart overlay process under Advanced.",
                )
            except Exception:  # noqa: BLE001 - a handler must never raise into C
                pass
            return 0

        # Kept on the instance so ctypes does not garbage-collect the
        # trampoline while Xlib still holds a pointer to it.
        self._error_handler = XErrorHandler(handler)
        self.lib.x11.XSetErrorHandler(self._error_handler)

    def _set_click_through(self) -> bool:
        """Make the window transparent to all input via an empty XFixes region.

        If this fails the overlay is a full-screen window that *takes input*,
        which would swallow touches and trackpad clicks meant for the game.
        That is far too serious to fail quietly, so every failure path here is
        reported and the caller refuses to map the window.
        """

        if self.lib.xfixes is None:
            self._report(
                "Input pass-through unavailable",
                f"libXfixes could not be loaded ({self.lib.xfixes_error or 'reason unknown'}), "
                "so the overlay cannot be made transparent to touch and "
                "trackpad input.",
                hint="The overlay has been disabled to avoid swallowing input. "
                     "Install libXfixes, or use the Steam UI fallback.",
            )
            return False

        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        if not self.lib.xfixes.XFixesQueryExtension(
                self.display, ctypes.byref(event_base), ctypes.byref(error_base)):
            self._report(
                "Input pass-through unavailable",
                f"The X server on {self.display_name} does not provide the "
                "XFixes extension, so the overlay cannot be made click-through.",
                hint="The overlay has been disabled to avoid swallowing input.",
            )
            return False

        region = self.lib.xfixes.XFixesCreateRegion(self.display, None, 0)
        self.lib.xfixes.XFixesSetWindowShapeRegion(
            self.display, self.window, SHAPE_INPUT, 0, 0, region)
        self.lib.xfixes.XFixesDestroyRegion(self.display, region)
        self.lib.x11.XSync(self.display, 0)
        return True

    # ------------------------------------------------------------------
    def map(self) -> None:
        if not self.mapped:
            self.lib.x11.XMapWindow(self.display, self.window)
            self.lib.x11.XFlush(self.display)
            self.mapped = True

    def unmap(self) -> None:
        if self.mapped:
            self.lib.x11.XUnmapWindow(self.display, self.window)
            self.lib.x11.XFlush(self.display)
            self.mapped = False

    def flush(self) -> None:
        self.lib.x11.XFlush(self.display)

    def drain_events(self) -> None:
        """Discard pending events so the connection buffer cannot grow."""

        if self.display is None:
            return
        event = ctypes.create_string_buffer(256)  # sizeof(XEvent) is 192 on x86-64
        while self.lib.x11.XPending(self.display) > 0:
            self.lib.x11.XNextEvent(self.display, event)

    # ------------------------------------------------------------------
    def _image_for(self, width: int, height: int) -> Tuple[ctypes.c_void_p, Any]:
        key = (width, height)
        cached = self._images.get(key)
        if cached is not None:
            return cached
        buffer = ctypes.create_string_buffer(width * height * 4)
        image = self.lib.x11.XCreateImage(
            self.display, self._visual, 32, Z_PIXMAP, 0,
            ctypes.cast(buffer, ctypes.c_void_p), width, height, 32, width * 4,
        )
        if not image:
            raise X11Error("XCreateImage failed")
        self._images[key] = (image, buffer)
        return self._images[key]

    def blit(self, x: int, y: int, width: int, height: int, pixels: bytes) -> None:
        """Copy a premultiplied ARGB tile onto the overlay."""

        image, buffer = self._image_for(width, height)
        ctypes.memmove(buffer, pixels, min(len(pixels), width * height * 4))
        self.lib.x11.XPutImage(self.display, self.window, self.gc, image,
                               0, 0, x, y, width, height)

    def close(self) -> None:
        if self.display is None:
            return
        try:
            for image, _buffer in self._images.values():
                # Free the XImage struct only - the pixel buffer belongs to
                # ctypes, so XDestroyImage would double-free it.
                self.lib.x11.XFree(image)
            self._images.clear()
            if self.gc:
                self.lib.x11.XFreeGC(self.display, self.gc)
                self.gc = None
            if self.window:
                self.lib.x11.XDestroyWindow(self.display, self.window)
                self.window = 0
            self.lib.x11.XCloseDisplay(self.display)
        finally:
            self.display = None
            self.mapped = False

    def describe(self) -> Dict[str, Any]:
        return {
            "display": self.display_name,
            "gamescope": self.is_gamescope,
            "width": self.width,
            "height": self.height,
            "mapped": self.mapped,
            "click_through": self.click_through,
        }
