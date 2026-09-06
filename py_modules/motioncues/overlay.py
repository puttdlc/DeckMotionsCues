"""The overlay helper process: sensors in, dots on the screen out.

This runs as its own process rather than inside the Decky backend for three
reasons: it needs its own X connection and event loop, it must keep drawing at
display rate without being blocked by plugin RPC, and if it ever crashes it
should take nothing else down with it.  The Decky backend owns its lifecycle.

The motion pipeline lives here too, deliberately: putting sensor reading,
filtering and drawing in one process means no IPC hop in the latency path.
The socket carries only configuration changes and status queries.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import select
import signal
import socket
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):  # allow `python overlay.py` for debugging
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motioncues import config as config_module
from motioncues import layout, sensors, sprites
from motioncues.engine import MotionEngine
from motioncues.problems import ProblemLog

#: Alpha is quantised before re-rasterising the sprite, so a slow fade costs a
#: few dozen rasterisations rather than one per frame.
ALPHA_STEPS = 48

#: Transparent border baked into every sprite tile.  A single blit then both
#: draws the dot and erases where it was last frame, as long as the dot moved
#: less than this - which the response filter guarantees at normal frame rates.
TILE_PADDING = 6


def has_unix_sockets() -> bool:
    """AF_UNIX is always present on the Deck; absent on some dev platforms."""

    return hasattr(socket, "AF_UNIX")


def connect(socket_path: str, timeout: float = 2.0) -> socket.socket:
    """Open a client connection to an overlay control socket."""

    if has_unix_sockets():
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        client.connect(socket_path)
        return client
    with open(socket_path, "r", encoding="utf-8") as handle:
        port = int(handle.read().strip())
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(("127.0.0.1", port))
    return client


def log(message: str) -> None:
    sys.stderr.write(f"[motion-cues-overlay] {message}\n")
    sys.stderr.flush()


class OverlayService:
    def __init__(self, settings_dir: str, socket_path: str,
                 headless: bool = False) -> None:
        #: Every failure in this process lands here and is handed to the panel
        #: with the status payload.
        self.problems = ProblemLog()
        self.store = config_module.Store(settings_dir, problems=self.problems)
        self.cfg = self.store.load_config()
        self.socket_path = socket_path
        self.headless = headless

        self.engine = MotionEngine(self.cfg)
        self.sensor: Optional[sensors.SensorSource] = None
        self.sensor_error = ""
        self.window: Optional[Any] = None
        self.window_error = ""

        self._sprite: Optional[sprites.Sprite] = None
        self._alpha_cache: Dict[int, sprites.Sprite] = {}
        self._blank: bytes = b""
        self._base_points: List[Tuple[float, float]] = []
        self._last_tiles: List[Tuple[int, int]] = []
        self._last_alpha_step = -1

        self._server: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._buffers: Dict[int, bytes] = {}

        self.running = True
        self.frames = 0
        self.draws = 0
        self.fps = 0.0
        self._fps_mark = time.monotonic()
        self._fps_frames = 0
        self.started = time.monotonic()

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._start_server()
        self._open_sensor()
        if not self.headless:
            self._open_window()
        self._rebuild_visuals()

    def _open_sensor(self) -> None:
        runtime = self.cfg["runtime"]
        try:
            self.sensor = sensors.create(runtime["sensor_source"],
                                         runtime["synthetic_profile"],
                                         problems=self.problems)
            self.sensor_error = ""
            log(f"sensor: {self.sensor.name} ({self.sensor.description})")
            # The sensor is working, so withdraw any earlier complaint.
            self.problems.resolve("sensor", "No motion sensor available")
            self.problems.resolve("sensor", "Lost contact with the motion sensor")
        except Exception as exc:  # noqa: BLE001 - report anything as a status
            self.sensor = None
            self.sensor_error = str(exc)
            log(f"sensor unavailable: {exc}")
            self.problems.record(
                "sensor",
                "No motion sensor available",
                str(exc),
                hint="In Game Mode the IMU is only enabled when the active "
                     "controller layout uses gyro - set Gyro Behaviour to "
                     "anything other than None. Or set Sensor source to Demo "
                     "in Advanced to test without hardware.",
            )

    def _open_window(self) -> None:
        try:
            from motioncues.x11 import OverlayWindow

            window = OverlayWindow(self.cfg["runtime"]["display"],
                                   problems=self.problems)
            window.open()
            self.window = window
            self.window_error = ""
            self.problems.resolve("overlay", "Overlay window could not be created")
            log(f"overlay window on {window.display_name} "
                f"({window.width}x{window.height}, "
                f"gamescope={window.is_gamescope})")
        except Exception as exc:  # noqa: BLE001
            self.window = None
            self.window_error = str(exc)
            log(f"overlay window unavailable: {exc}")
            self.problems.record(
                "overlay",
                "Overlay window could not be created",
                str(exc),
                hint="The cues cannot be drawn over games. If the Steam UI "
                     "fallback is enabled they will still show inside Steam's "
                     "own screens.",
            )

    def _start_server(self) -> None:
        try:
            os.unlink(self.socket_path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                log(f"could not clear stale socket: {exc}")
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)

        if has_unix_sockets():
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(self.socket_path)
        else:
            # Development fallback for platforms without AF_UNIX: bind
            # loopback and publish the port where the socket path would be.
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(("127.0.0.1", 0))
            with open(self.socket_path, "w", encoding="utf-8") as handle:
                handle.write(str(server.getsockname()[1]))
        server.listen(4)
        server.setblocking(False)
        try:
            os.chmod(self.socket_path, 0o660)
        except OSError as exc:
            # Not fatal, but worth saying: the control socket may be readable
            # by other local users than intended.
            self.problems.record(
                "overlay",
                "Control socket permissions could not be set",
                f"{self.socket_path}: {exc}",
                severity="warning",
            )
        self._server = server

    # ------------------------------------------------------------------
    # visuals
    # ------------------------------------------------------------------
    def _screen_size(self) -> Tuple[int, int]:
        if self.window is not None:
            return self.window.width, self.window.height
        return 1280, 800  # Deck LCD/OLED default, used in headless mode

    def _rebuild_visuals(self) -> None:
        appearance = self.cfg["appearance"]
        self._sprite = sprites.sprite_for(appearance, padding=TILE_PADDING)
        self._alpha_cache = {}
        width, height = self._screen_size()
        self._base_points = layout.dot_positions(width, height, appearance)
        self._blank = bytes(self._sprite.width * self._sprite.height * 4)
        self._clear_all()
        self._last_tiles = []
        self._last_alpha_step = -1

    def _sprite_for_alpha(self, alpha: float) -> Tuple[int, sprites.Sprite]:
        step = max(0, min(ALPHA_STEPS, int(round(alpha * ALPHA_STEPS))))
        cached = self._alpha_cache.get(step)
        if cached is None:
            assert self._sprite is not None
            cached = sprites.scale_sprite_alpha(self._sprite, step / ALPHA_STEPS)
            self._alpha_cache[step] = cached
        return step, cached

    def _clear_all(self) -> None:
        if self.window is None or not self._last_tiles or not self._sprite:
            return
        for x, y in self._last_tiles:
            self.window.blit(x, y, self._sprite.width, self._sprite.height, self._blank)
        self.window.flush()

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def render(self) -> None:
        if self.window is None or self._sprite is None:
            return

        state = self.engine.state
        alpha = state.alpha
        step, sprite = self._sprite_for_alpha(alpha)

        if step <= 0:
            # Nothing to show: erase and unmap so the overlay plane costs
            # gamescope nothing at all while the cues are inactive.
            if self._last_tiles:
                self._clear_all()
                self._last_tiles = []
            self.window.unmap()
            self._last_alpha_step = 0
            return

        self.window.map()

        half_w = sprite.center_x
        half_h = sprite.center_y
        tiles: List[Tuple[int, int]] = []
        for base_x, base_y in self._base_points:
            tiles.append((int(round(base_x + state.dx - half_w)),
                          int(round(base_y + state.dy - half_h))))

        if tiles == self._last_tiles and step == self._last_alpha_step:
            return  # nothing moved and nothing faded: no X traffic at all

        width = sprite.width
        height = sprite.height

        # If a dot jumped further than the tile padding, its old position is
        # outside the new tile and needs an explicit erase.
        if self._last_tiles and len(self._last_tiles) == len(tiles):
            for (old_x, old_y), (new_x, new_y) in zip(self._last_tiles, tiles):
                if abs(new_x - old_x) > TILE_PADDING or abs(new_y - old_y) > TILE_PADDING:
                    self.window.blit(old_x, old_y, width, height, self._blank)
        elif self._last_tiles:
            for old_x, old_y in self._last_tiles:
                self.window.blit(old_x, old_y, width, height, self._blank)

        data = bytes(sprite.data)
        for x, y in tiles:
            self.window.blit(x, y, width, height, data)

        self.window.flush()
        self._last_tiles = tiles
        self._last_alpha_step = step
        self.draws += 1

    # ------------------------------------------------------------------
    # IPC
    # ------------------------------------------------------------------
    def _accept(self) -> None:
        assert self._server is not None
        try:
            client, _ = self._server.accept()
        except OSError:
            return
        client.setblocking(False)
        self._clients.append(client)
        self._buffers[client.fileno()] = b""

    def _drop(self, client: socket.socket) -> None:
        self._buffers.pop(client.fileno(), None)
        if client in self._clients:
            self._clients.remove(client)
        try:
            client.close()
        except OSError as exc:
            log(f"control client did not close cleanly: {exc}")

    def _serve(self, client: socket.socket) -> None:
        try:
            chunk = client.recv(65536)
        except OSError:
            self._drop(client)
            return
        if not chunk:
            self._drop(client)
            return

        fd = client.fileno()
        buffer = self._buffers.get(fd, b"") + chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                request = json.loads(line.decode("utf-8"))
            except ValueError:
                response: Dict[str, Any] = {"ok": False, "error": "bad json"}
            else:
                response = self.handle(request)
            try:
                client.sendall((json.dumps(response) + "\n").encode("utf-8"))
            except OSError:
                self._drop(client)
                return
        self._buffers[fd] = buffer

    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        command = request.get("cmd")

        if command == "status":
            return {"ok": True, "status": self.status()}

        if command == "config":
            incoming = config_module.validate(request.get("config"))
            self.apply_config(incoming)
            return {"ok": True, "status": self.status()}

        if command == "calibrate":
            patch = self.engine.autocalibrate()
            if patch is None:
                return {"ok": False, "error": "gravity estimate has not settled yet"}
            return {"ok": True, "patch": {"motion": patch}}

        if command == "clear_problems":
            key = request.get("key")
            cleared = self.problems.clear(key if isinstance(key, str) else None)
            return {"ok": True, "cleared": cleared}

        if command == "reset":
            self.engine.reset()
            return {"ok": True}

        if command == "quit":
            self.running = False
            return {"ok": True}

        return {"ok": False, "error": f"unknown command {command!r}"}

    def apply_config(self, new_cfg: Dict[str, Any]) -> None:
        old = self.cfg
        self.cfg = new_cfg
        self.engine.apply_config(new_cfg)

        if (old["appearance"] != new_cfg["appearance"]):
            self._rebuild_visuals()

        old_runtime = old["runtime"]
        new_runtime = new_cfg["runtime"]
        if (old_runtime["sensor_source"] != new_runtime["sensor_source"]
                or old_runtime["synthetic_profile"] != new_runtime["synthetic_profile"]):
            if self.sensor is not None:
                self.sensor.close()
            self._open_sensor()
            self.engine.reset()

    def status(self) -> Dict[str, Any]:
        state = self.engine.state.as_dict()
        window = self.window.describe() if self.window is not None else None
        return {
            "running": self.running,
            "uptime": round(time.monotonic() - self.started, 1),
            "fps": round(self.fps, 1),
            "frames": self.frames,
            "draws": self.draws,
            "mode": self.cfg["mode"],
            "sensor": {
                "source": self.sensor.name if self.sensor else "none",
                "detail": self.sensor.description if self.sensor else self.sensor_error,
                "ok": self.sensor is not None,
            },
            "window": window,
            "window_error": self.window_error,
            "tier": self.tier(),
            "motion": state,
            "problems": self.problems.snapshot(),
        }

    def tier(self) -> str:
        """Which capability tier is actually live right now."""

        if self.window is None:
            return "none"
        if self.window.is_gamescope:
            return "gamescope-overlay"
        return "x11-overlay"

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self) -> int:
        period = 1.0 / max(15, self.cfg["runtime"]["target_fps"])
        next_frame = time.monotonic()
        last_step = time.monotonic()

        while self.running:
            now = time.monotonic()
            timeout = max(0.0, next_frame - now)

            watch: List[Any] = []
            if self._server is not None:
                watch.append(self._server)
            watch.extend(self._clients)
            sensor_fd = self.sensor.fileno() if self.sensor is not None else None
            if sensor_fd is not None:
                watch.append(sensor_fd)

            try:
                readable, _, _ = select.select(watch, [], [], timeout)
            except (OSError, ValueError):
                readable = []

            for item in readable:
                if item is self._server:
                    self._accept()
                elif isinstance(item, socket.socket):
                    self._serve(item)

            # Pull sensor samples.  Sources without a pollable fd (sysfs, the
            # synthetic generator) are read on every pass with no timeout.
            if self.sensor is not None:
                try:
                    if sensor_fd is not None:
                        samples = (self.sensor.read(0.0)
                                   if sensor_fd in readable else [])
                    else:
                        samples = self.sensor.read(min(timeout, 0.004))
                    for sample in samples:
                        self.engine.ingest(sample.t, sample.accel, sample.gyro)
                    if samples:
                        last_step = time.monotonic()
                except sensors.SensorError as exc:
                    self.sensor_error = str(exc)
                    log(f"sensor read failed: {exc}")
                    self.problems.record(
                        "sensor",
                        "Lost contact with the motion sensor",
                        f"{exc}. The cues have stopped responding to motion.",
                        hint="Use Restart overlay process under Advanced to "
                             "reconnect.",
                    )
                    try:
                        self.sensor.close()
                    except Exception as close_exc:  # noqa: BLE001
                        log(f"sensor close after failure also failed: {close_exc}")
                    self.sensor = None

            now = time.monotonic()
            if now >= next_frame:
                # Keep easing between sensor bursts so motion stays smooth even
                # if the IMU delivers slower than the display refreshes.
                gap = now - last_step
                if gap > 0.0005:
                    self.engine.step_only(gap)
                    last_step = now

                try:
                    self.render()
                except Exception as exc:  # noqa: BLE001
                    log(f"render failed: {exc}\n{traceback.format_exc()}")
                    self.running = False
                    return 1

                if self.window is not None:
                    self.window.drain_events()

                self.frames += 1
                self._fps_frames += 1
                if now - self._fps_mark >= 1.0:
                    self.fps = self._fps_frames / (now - self._fps_mark)
                    self._fps_mark = now
                    self._fps_frames = 0

                period = 1.0 / max(15, self.cfg["runtime"]["target_fps"])
                next_frame += period
                if next_frame < now - period:  # fell far behind; resynchronise
                    next_frame = now + period

        return 0

    def shutdown(self) -> None:
        try:
            if self.window is not None:
                self._clear_all()
                self.window.close()
        except Exception as exc:  # noqa: BLE001
            log(f"overlay window did not close cleanly: {exc}")
        if self.sensor is not None:
            try:
                self.sensor.close()
            except Exception as exc:  # noqa: BLE001
                log(f"sensor did not close cleanly: {exc}")
        for client in list(self._clients):
            self._drop(client)
        if self._server is not None:
            self._server.close()
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Motion Cues overlay renderer")
    parser.add_argument("--settings-dir", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--headless", action="store_true",
                        help="run the pipeline without opening an X window")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="exit after N seconds (used by the test harness)")
    args = parser.parse_args(argv)

    service = OverlayService(args.settings_dir, args.socket, headless=args.headless)

    def stop(_signum: int, _frame: Any) -> None:
        service.running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        service.start()
    except Exception as exc:  # noqa: BLE001
        log(f"startup failed: {exc}\n{traceback.format_exc()}")
        service.shutdown()
        return 1

    if args.seconds > 0.0:
        deadline = time.monotonic() + args.seconds

        original_render = service.render

        def render_with_deadline() -> None:
            original_render()
            if time.monotonic() >= deadline:
                service.running = False

        service.render = render_with_deadline  # type: ignore[method-assign]

    try:
        return service.run()
    finally:
        service.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
