"""Configuration schema, validation, persistence and presets.

Every user-facing setting lives here.  The schema is declarative so the
backend can validate anything the frontend sends without trusting it, and so
the UI can be driven from a single source of truth.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 2

EDGES = ("left", "right", "top", "bottom")
SHAPES = ("circle", "ring", "square", "diamond")
MODES = ("auto", "on", "off")
LAYOUTS = ("even", "corners", "clustered")
SENSOR_SOURCES = ("auto", "evdev", "iio", "hidraw", "synthetic")
AXES = ("x", "y", "z")

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


DEFAULTS: Dict[str, Any] = {
    "version": SCHEMA_VERSION,
    "mode": "auto",
    "active_preset": "Car",
    "appearance": {
        # Dots per edge.  12 per edge on left+right is close to Apple's density.
        "count": 12,
        "size": 9.0,
        "shape": "circle",
        "color": "#FFFFFF",
        "opacity": 0.55,
        "edges": ["left", "right"],
        "edge_padding": 26.0,
        "layout": "even",
        "margin_fraction": 0.06,
        "outline": 0.0,
        "outline_color": "#000000",
    },
    "motion": {
        # Pixels of dot travel per g of linear (gravity-removed) acceleration.
        "gain_x": 160.0,
        "gain_y": 140.0,
        # Pixels per degree/second of yaw - gives an early turn cue before
        # lateral acceleration fully builds.
        "gyro_gain": 0.55,
        "max_travel": 48.0,
        # How much of a bump (vertical acceleration) folds into vertical dot
        # travel, on top of the fore/aft term.
        "vertical_weight": 0.5,
        # 0..1, higher = smoother/slower response.
        "smoothing": 0.35,
        # 0..1, higher = faster snap back to centre once motion settles.
        "return_speed": 0.45,
        "deadzone": 0.010,
        "invert_x": False,
        "invert_y": False,
        # Which IMU axis maps to screen right / screen up, and their signs.
        #
        # hid-steam maps the Deck's IMU onto ABS_X (the left/right axis),
        # ABS_Y (front/back) and ABS_Z (bottom/top).  Which *direction* each
        # points along its axis is the one thing that cannot be confirmed
        # without hardware, so these defaults encode a single stated
        # assumption: ABS_X points to the user's right, and ABS_Z points up.
        # ABS_Z is corroborated - a resting accelerometer reads +1 g on the
        # up axis - and "forward" is then derived as ABS_Y, which matches the
        # documented front-to-back axis.  The basis is therefore internally
        # consistent; if the hardware disagrees about a direction, "Invert
        # sideways" / "Invert fore/aft" correct it in one tap, and
        # "Calibrate orientation" derives the up axis from gravity.
        "axis_right": "x",
        "axis_right_sign": 1,
        "axis_up": "z",
        "axis_up_sign": 1,
        "gravity_tau": 3.0,
    },
    "auto": {
        "enter_threshold": 0.030,
        "exit_threshold": 0.016,
        "enter_seconds": 4.0,
        "exit_seconds": 12.0,
        "handling_gyro_dps": 55.0,
        "fade_seconds": 1.2,
    },
    "runtime": {
        "sensor_source": "auto",
        "target_fps": 60,
        "display": "auto",
        # If gamescope's single external-overlay slot is held by mangoapp,
        # optionally stop mangoapp to take it (disables the perf overlay).
        "claim_overlay_slot": False,
        "fallback_steam_ui": True,
        "debug_readout": False,
        "synthetic_profile": "city",
    },
}


# --------------------------------------------------------------------------
# validation helpers
# --------------------------------------------------------------------------

def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _as_float(value: Any, fallback: float, low: float, high: float) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError
        return _clamp(float(value), low, high)
    except (TypeError, ValueError):
        return fallback


def _as_int(value: Any, fallback: int, low: int, high: int) -> int:
    try:
        if isinstance(value, bool):
            raise TypeError
        return int(_clamp(int(value), low, high))
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
    return fallback


def _as_choice(value: Any, fallback: str, choices: Iterable[str]) -> str:
    if isinstance(value, str) and value in choices:
        return value
    return fallback


def _as_color(value: Any, fallback: str) -> str:
    if isinstance(value, str) and _HEX_RE.match(value.strip()):
        text = value.strip()
        if len(text) == 4:  # #abc -> #aabbcc
            text = "#" + "".join(ch * 2 for ch in text[1:])
        return text.upper()
    return fallback


def _as_sign(value: Any, fallback: int) -> int:
    try:
        return 1 if float(value) >= 0 else -1
    except (TypeError, ValueError):
        return fallback


def _as_edges(value: Any, fallback: List[str]) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return list(fallback)
    seen: List[str] = []
    for item in value:
        if isinstance(item, str) and item in EDGES and item not in seen:
            seen.append(item)
    return seen if seen else list(fallback)


def validate(raw: Any) -> Dict[str, Any]:
    """Coerce arbitrary input into a complete, in-range configuration."""

    data = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(DEFAULTS)

    out["version"] = SCHEMA_VERSION
    out["mode"] = _as_choice(data.get("mode"), DEFAULTS["mode"], MODES)
    active = data.get("active_preset")
    out["active_preset"] = active if isinstance(active, str) and active else ""

    src = data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
    dst = out["appearance"]
    ref = DEFAULTS["appearance"]
    dst["count"] = _as_int(src.get("count"), ref["count"], 1, 64)
    dst["size"] = _as_float(src.get("size"), ref["size"], 2.0, 48.0)
    dst["shape"] = _as_choice(src.get("shape"), ref["shape"], SHAPES)
    dst["color"] = _as_color(src.get("color"), ref["color"])
    dst["opacity"] = _as_float(src.get("opacity"), ref["opacity"], 0.02, 1.0)
    dst["edges"] = _as_edges(src.get("edges"), ref["edges"])
    dst["edge_padding"] = _as_float(src.get("edge_padding"), ref["edge_padding"], 0.0, 400.0)
    dst["layout"] = _as_choice(src.get("layout"), ref["layout"], LAYOUTS)
    dst["margin_fraction"] = _as_float(src.get("margin_fraction"), ref["margin_fraction"], 0.0, 0.45)
    dst["outline"] = _as_float(src.get("outline"), ref["outline"], 0.0, 4.0)
    dst["outline_color"] = _as_color(src.get("outline_color"), ref["outline_color"])

    src = data.get("motion") if isinstance(data.get("motion"), dict) else {}
    dst = out["motion"]
    ref = DEFAULTS["motion"]
    dst["gain_x"] = _as_float(src.get("gain_x"), ref["gain_x"], 0.0, 600.0)
    dst["gain_y"] = _as_float(src.get("gain_y"), ref["gain_y"], 0.0, 600.0)
    dst["gyro_gain"] = _as_float(src.get("gyro_gain"), ref["gyro_gain"], 0.0, 8.0)
    dst["max_travel"] = _as_float(src.get("max_travel"), ref["max_travel"], 1.0, 300.0)
    dst["vertical_weight"] = _as_float(src.get("vertical_weight"), ref["vertical_weight"], 0.0, 2.0)
    dst["smoothing"] = _as_float(src.get("smoothing"), ref["smoothing"], 0.0, 0.99)
    dst["return_speed"] = _as_float(src.get("return_speed"), ref["return_speed"], 0.01, 1.0)
    dst["deadzone"] = _as_float(src.get("deadzone"), ref["deadzone"], 0.0, 0.25)
    dst["invert_x"] = _as_bool(src.get("invert_x"), ref["invert_x"])
    dst["invert_y"] = _as_bool(src.get("invert_y"), ref["invert_y"])
    dst["axis_right"] = _as_choice(src.get("axis_right"), ref["axis_right"], AXES)
    dst["axis_right_sign"] = _as_sign(src.get("axis_right_sign"), ref["axis_right_sign"])
    dst["axis_up"] = _as_choice(src.get("axis_up"), ref["axis_up"], AXES)
    dst["axis_up_sign"] = _as_sign(src.get("axis_up_sign"), ref["axis_up_sign"])
    dst["gravity_tau"] = _as_float(src.get("gravity_tau"), ref["gravity_tau"], 0.2, 10.0)

    src = data.get("auto") if isinstance(data.get("auto"), dict) else {}
    dst = out["auto"]
    ref = DEFAULTS["auto"]
    dst["enter_threshold"] = _as_float(src.get("enter_threshold"), ref["enter_threshold"], 0.002, 0.5)
    dst["exit_threshold"] = _as_float(src.get("exit_threshold"), ref["exit_threshold"], 0.001, 0.5)
    dst["enter_seconds"] = _as_float(src.get("enter_seconds"), ref["enter_seconds"], 0.5, 60.0)
    dst["exit_seconds"] = _as_float(src.get("exit_seconds"), ref["exit_seconds"], 1.0, 300.0)
    dst["handling_gyro_dps"] = _as_float(src.get("handling_gyro_dps"), ref["handling_gyro_dps"], 5.0, 500.0)
    dst["fade_seconds"] = _as_float(src.get("fade_seconds"), ref["fade_seconds"], 0.0, 10.0)
    # Exit threshold below enter threshold keeps the hysteresis meaningful.
    if dst["exit_threshold"] >= dst["enter_threshold"]:
        dst["exit_threshold"] = dst["enter_threshold"] * 0.55

    src = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    dst = out["runtime"]
    ref = DEFAULTS["runtime"]
    dst["sensor_source"] = _as_choice(src.get("sensor_source"), ref["sensor_source"], SENSOR_SOURCES)
    dst["target_fps"] = _as_int(src.get("target_fps"), ref["target_fps"], 15, 144)
    display = src.get("display")
    dst["display"] = display if isinstance(display, str) and display else "auto"
    dst["claim_overlay_slot"] = _as_bool(src.get("claim_overlay_slot"), ref["claim_overlay_slot"])
    dst["fallback_steam_ui"] = _as_bool(src.get("fallback_steam_ui"), ref["fallback_steam_ui"])
    dst["debug_readout"] = _as_bool(src.get("debug_readout"), ref["debug_readout"])
    profile = src.get("synthetic_profile")
    dst["synthetic_profile"] = profile if isinstance(profile, str) and profile else ref["synthetic_profile"]

    return out


def merge(base: Dict[str, Any], patch: Any) -> Dict[str, Any]:
    """Deep-merge ``patch`` into ``base`` and re-validate the result."""

    merged = copy.deepcopy(base)

    def _merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value

    if isinstance(patch, dict):
        _merge(merged, patch)
    return validate(merged)


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    text = color.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


# --------------------------------------------------------------------------
# presets
# --------------------------------------------------------------------------

def _preset(mode: str, appearance: Dict[str, Any], motion: Dict[str, Any],
            auto: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"mode": mode, "appearance": appearance, "motion": motion}
    if auto:
        body["auto"] = auto
    return body


#: Shipped presets.  These are stored as *partial* configurations and applied
#: on top of the current config, so a preset never clobbers runtime settings
#: such as the chosen sensor source.
BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "Car": _preset(
        "auto",
        {"count": 12, "size": 9.0, "opacity": 0.55, "edges": ["left", "right"],
         "edge_padding": 26.0, "shape": "circle"},
        {"gain_x": 160.0, "gain_y": 140.0, "gyro_gain": 0.55, "max_travel": 48.0,
         "smoothing": 0.35, "return_speed": 0.45, "deadzone": 0.010},
    ),
    "Train/Bus": _preset(
        "auto",
        {"count": 14, "size": 8.0, "opacity": 0.48, "edges": ["left", "right", "top", "bottom"],
         "edge_padding": 22.0, "shape": "circle"},
        # Rail motion is lower frequency and more lateral; damp the vertical
        # jolts from track joints but keep sway visible.
        {"gain_x": 185.0, "gain_y": 90.0, "gyro_gain": 0.35, "max_travel": 54.0,
         "smoothing": 0.5, "return_speed": 0.32, "deadzone": 0.014},
    ),
    "Boat": _preset(
        "auto",
        {"count": 16, "size": 10.0, "opacity": 0.6, "edges": ["left", "right", "top", "bottom"],
         "edge_padding": 20.0, "shape": "circle"},
        # Swell is slow and large-amplitude: long travel, heavy smoothing and a
        # lazy return so the dots ride the roll instead of chasing it.
        {"gain_x": 210.0, "gain_y": 210.0, "gyro_gain": 0.9, "max_travel": 78.0,
         "smoothing": 0.62, "return_speed": 0.18, "deadzone": 0.008},
        {"enter_threshold": 0.030, "exit_threshold": 0.016, "enter_seconds": 5.0,
         "exit_seconds": 20.0},
    ),
    "Subtle": _preset(
        "auto",
        {"count": 8, "size": 6.0, "opacity": 0.30, "edges": ["left", "right"],
         "edge_padding": 16.0, "shape": "circle"},
        {"gain_x": 105.0, "gain_y": 90.0, "gyro_gain": 0.3, "max_travel": 28.0,
         "smoothing": 0.45, "return_speed": 0.5, "deadzone": 0.016},
    ),
    "Strong": _preset(
        "on",
        {"count": 18, "size": 12.0, "opacity": 0.8, "edges": ["left", "right", "top", "bottom"],
         "edge_padding": 30.0, "shape": "circle"},
        {"gain_x": 265.0, "gain_y": 235.0, "gyro_gain": 1.1, "max_travel": 90.0,
         "smoothing": 0.25, "return_speed": 0.6, "deadzone": 0.006},
    ),
}


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

def _atomic_write(path: str, payload: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=directory, prefix=".mc-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, sort_keys=True)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Store:
    """JSON-backed settings + preset storage.

    Falling back to defaults is the right behaviour when a file is damaged,
    but doing it *quietly* would mean a user's whole configuration vanishes
    with no explanation.  Every fallback is therefore reported through the
    optional problem log.
    """

    def __init__(self, directory: str, problems: Any = None) -> None:
        self.directory = directory
        self.config_path = os.path.join(directory, "settings.json")
        self.presets_path = os.path.join(directory, "presets.json")
        self.problems = problems

    def _report(self, title: str, detail: str = "", severity: str = "error",
                hint: str = "") -> None:
        if self.problems is not None:
            self.problems.record("settings", title, detail,
                                 severity=severity, hint=hint)

    # -- config ----------------------------------------------------------
    def load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as fp:
                config = validate(json.load(fp))
        except FileNotFoundError:
            return validate({})  # first run: not a problem
        except ValueError as exc:
            self._report(
                "Settings file is corrupt",
                f"{self.config_path} is not valid JSON ({exc}); defaults are "
                "being used instead.",
                hint="Change any setting to write a fresh, valid file.",
            )
            return validate({})
        except OSError as exc:
            self._report(
                "Settings file could not be read",
                f"{self.config_path}: {exc}. Defaults are being used, and "
                "changes may not persist.",
                hint="Check the permissions on the plugin's settings folder.",
            )
            return validate({})
        if self.problems is not None:
            self.problems.resolve("settings", "Settings file is corrupt")
            self.problems.resolve("settings", "Settings file could not be read")
        return config

    def save_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        clean = validate(cfg)
        try:
            _atomic_write(self.config_path, clean)
        except OSError as exc:
            self._report(
                "Settings could not be saved",
                f"{self.config_path}: {exc}. The change is active now but "
                "will be lost when the plugin restarts.",
                hint="Check free space and permissions on the settings folder.",
            )
            return clean
        if self.problems is not None:
            self.problems.resolve("settings", "Settings could not be saved")
        return clean

    # -- presets ---------------------------------------------------------
    def load_presets(self) -> Dict[str, Dict[str, Any]]:
        presets = copy.deepcopy(BUILTIN_PRESETS)
        try:
            with open(self.presets_path, "r", encoding="utf-8") as fp:
                stored = json.load(fp)
        except FileNotFoundError:
            stored = {}
        except (OSError, ValueError) as exc:
            stored = {}
            self._report(
                "Saved presets could not be read",
                f"{self.presets_path}: {exc}. The built-in presets are still "
                "available; your own saved presets are not loaded.",
                hint="Saving a preset will rewrite the file.",
            )
        if isinstance(stored, dict):
            for name, body in stored.items():
                if isinstance(name, str) and name and isinstance(body, dict):
                    presets[name] = body
        return presets

    def save_presets(self, presets: Dict[str, Dict[str, Any]]) -> None:
        # Only user presets are persisted; built-ins come from code so they can
        # be improved by updates.  A user preset that shadows a built-in name is
        # kept, since overriding "Car" is a legitimate thing to want.
        user = {name: body for name, body in presets.items()
                if name not in BUILTIN_PRESETS or body != BUILTIN_PRESETS[name]}
        try:
            _atomic_write(self.presets_path, user)
        except OSError as exc:
            self._report(
                "Presets could not be saved",
                f"{self.presets_path}: {exc}. The preset is available now but "
                "will be lost when the plugin restarts.",
                hint="Check free space and permissions on the settings folder.",
            )
            return
        if self.problems is not None:
            self.problems.resolve("settings", "Presets could not be saved")


def preset_from_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Capture the user-tunable half of a config as a preset body."""

    clean = validate(cfg)
    return {
        "mode": clean["mode"],
        "appearance": copy.deepcopy(clean["appearance"]),
        "motion": copy.deepcopy(clean["motion"]),
        "auto": copy.deepcopy(clean["auto"]),
    }


def is_builtin(name: str) -> bool:
    return name in BUILTIN_PRESETS
