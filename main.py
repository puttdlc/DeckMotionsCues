"""Motion Cues - Decky Loader backend.

Responsibilities kept here:

* settings and preset persistence (the source of truth on disk);
* the lifecycle of the overlay helper process;
* a thin RPC surface for the React panel.

Deliberately *not* here: sensor reading and drawing.  Those live in the
overlay process so that nothing in the latency path can be blocked by a
plugin RPC call.  When the overlay cannot render (no X server, or gamescope's
overlay slot is unavailable) this backend can also stream motion samples to
the frontend for the Steam-UI fallback tier.
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PLUGIN_DIR, "py_modules"))

from motioncues import config as config_module  # noqa: E402
from motioncues import overlay as overlay_ipc  # noqa: E402
from motioncues import sensors, slot  # noqa: E402
from motioncues.problems import ProblemLog  # noqa: E402
from motioncues.engine import MotionEngine  # noqa: E402

OVERLAY_RESTART_BACKOFF = (0.5, 1.0, 2.0, 5.0, 10.0)


class OverlayClient:
    """Line-delimited JSON client for the overlay process' unix socket."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def request(self, payload: Dict[str, Any],
                      timeout: float = 2.0) -> Dict[str, Any]:
        def _call() -> Dict[str, Any]:
            with overlay_ipc.connect(self.path, timeout) as client:
                client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                buffer = b""
                while b"\n" not in buffer:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
                if not buffer:
                    return {"ok": False, "error": "no response"}
                return json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))

        try:
            return await asyncio.to_thread(_call)
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}


class Plugin:
    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def _main(self) -> None:
        self.loop = asyncio.get_event_loop()
        self.settings_dir = decky.DECKY_PLUGIN_SETTINGS_DIR
        self.runtime_dir = decky.DECKY_PLUGIN_RUNTIME_DIR
        os.makedirs(self.settings_dir, exist_ok=True)
        os.makedirs(self.runtime_dir, exist_ok=True)

        #: Failures raised on this side of the socket.  The overlay keeps its
        #: own log; get_status() merges the two so the panel sees one list.
        self.problems = ProblemLog()
        self.store = config_module.Store(self.settings_dir, problems=self.problems)
        first_run = not os.path.exists(self.store.config_path)
        self.cfg = self.store.load_config()
        self.presets = self.store.load_presets()
        if first_run:
            self._apply_installer_defaults()

        self.socket_path = os.path.join(self.runtime_dir, "overlay.sock")
        self.client = OverlayClient(self.socket_path)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._supervisor: Optional[asyncio.Task] = None
        self._restarts = 0
        self._last_error = ""

        # Fallback tier state (dots drawn by the React layer inside Steam's UI).
        self._fallback_task: Optional[asyncio.Task] = None
        self._fallback_engine: Optional[MotionEngine] = None
        self._fallback_sensor: Optional[sensors.SensorSource] = None
        self._fallback_subscribers = 0

        decky.logger.info("Motion Cues starting (mode=%s)", self.cfg["mode"])
        await self._ensure_overlay()

    def _apply_installer_defaults(self) -> None:
        """Seed settings from choices made in the setup wizard.

        The installer cannot write Decky's settings directory directly - only
        Decky knows where that is - so it drops the answers next to the plugin
        and they are applied here, once, on the very first launch.
        """

        path = os.path.join(PLUGIN_DIR, "defaults", "first_run.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                seed = json.load(handle)
        except (OSError, ValueError) as exc:
            self.problems.record(
                "plugin",
                "Installer defaults could not be applied",
                f"{path}: {exc}. The plugin's own defaults are being used.",
                severity="warning",
            )
            return

        preset = seed.pop("preset", None)
        if isinstance(preset, str) and preset in self.presets:
            self.cfg = config_module.merge(self.cfg, self.presets[preset])
            self.cfg["active_preset"] = preset
        self.cfg = self.store.save_config(config_module.merge(self.cfg, seed))
        decky.logger.info("applied installer defaults (preset=%s, mode=%s)",
                          preset, self.cfg["mode"])

    async def _unload(self) -> None:
        decky.logger.info("Motion Cues unloading")
        self._fallback_subscribers = 0
        await self._stop_fallback()
        await self._stop_overlay()

    async def _uninstall(self) -> None:
        await self._unload()

    # ------------------------------------------------------------------
    # overlay process management
    # ------------------------------------------------------------------
    def _overlay_command(self) -> List[str]:
        return [
            sys.executable or "python3",
            os.path.join(PLUGIN_DIR, "py_modules", "motioncues", "overlay.py"),
            "--settings-dir", self.settings_dir,
            "--socket", self.socket_path,
        ]

    async def _ensure_overlay(self) -> None:
        if self.cfg["mode"] == "off":
            await self._stop_overlay()
            return
        if self.process is not None and self.process.returncode is None:
            return
        await self._start_overlay()

    async def _start_overlay(self) -> None:
        environment = dict(os.environ)
        environment.setdefault("PYTHONPATH", os.path.join(PLUGIN_DIR, "py_modules"))
        environment.setdefault("PYTHONUNBUFFERED", "1")
        # The helper picks the right X display itself, but inheriting a sane
        # default helps when Decky's service environment has none.
        environment.setdefault("DISPLAY", ":0")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *self._overlay_command(),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=PLUGIN_DIR,
            )
        except OSError as exc:
            self._last_error = f"failed to spawn overlay: {exc}"
            decky.logger.error(self._last_error)
            self.problems.record(
                "plugin",
                "Overlay process could not be started",
                f"{exc}. No cues will be drawn.",
                hint="Use Restart overlay process under Advanced.",
            )
            return

        decky.logger.info("overlay process started (pid %s)", self.process.pid)
        self.problems.resolve("plugin", "Overlay process could not be started")
        self.problems.resolve("plugin", "Overlay process keeps failing")
        self._supervisor = self.loop.create_task(self._supervise(self.process))

        # Give it a moment to bind its socket, then push current settings.
        for _ in range(40):
            if os.path.exists(self.socket_path):
                break
            await asyncio.sleep(0.05)
        await self.client.request({"cmd": "config", "config": self.cfg})

    async def _supervise(self, process: asyncio.subprocess.Process) -> None:
        """Log the helper's output and restart it if it dies unexpectedly."""

        async def drain(stream: Any, level: Any) -> None:
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    return
                level("overlay: %s", line.decode("utf-8", "replace").rstrip())

        await asyncio.gather(
            drain(process.stdout, decky.logger.info),
            drain(process.stderr, decky.logger.warning),
            return_exceptions=True,
        )
        code = await process.wait()

        if self.process is not process:
            return  # superseded by a deliberate restart
        self.process = None

        if self.cfg["mode"] == "off":
            return
        self._last_error = f"overlay exited with code {code}"
        decky.logger.warning(self._last_error)
        self.problems.record(
            "plugin",
            "Overlay process stopped unexpectedly",
            f"It exited with code {code} and is being restarted "
            f"(attempt {self._restarts + 1}).",
            severity="warning",
            hint="If this repeats, check the plugin log via Decky's settings.",
        )

        delay = OVERLAY_RESTART_BACKOFF[min(self._restarts,
                                            len(OVERLAY_RESTART_BACKOFF) - 1)]
        self._restarts += 1
        if self._restarts > 12:
            decky.logger.error("overlay keeps failing; giving up until settings change")
            self.problems.record(
                "plugin",
                "Overlay process keeps failing",
                f"It has stopped {self._restarts} times in a row, so automatic "
                "restarts have been paused. The cues are not being drawn.",
                hint="Change any setting, or use Restart overlay process, to "
                     "try again.",
            )
            return
        await asyncio.sleep(delay)
        await self._ensure_overlay()

    async def _stop_overlay(self) -> None:
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        await self.client.request({"cmd": "quit"}, timeout=0.5)
        try:
            await asyncio.wait_for(process.wait(), timeout=1.5)
        except asyncio.TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                process.kill()

    # ------------------------------------------------------------------
    # RPC: settings
    # ------------------------------------------------------------------
    async def get_config(self) -> Dict[str, Any]:
        return self.cfg

    async def set_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Merge a partial config, persist it, and push it live."""

        previous_mode = self.cfg["mode"]
        self.cfg = self.store.save_config(config_module.merge(self.cfg, patch))
        self._restarts = 0

        if self.cfg["mode"] == "off" and previous_mode != "off":
            await self._stop_overlay()
        else:
            await self._ensure_overlay()
            await self.client.request({"cmd": "config", "config": self.cfg})
        return self.cfg

    async def set_mode(self, mode: str) -> Dict[str, Any]:
        return await self.set_config({"mode": mode})

    async def reset_config(self) -> Dict[str, Any]:
        self.cfg = self.store.save_config(config_module.validate({}))
        await self._ensure_overlay()
        await self.client.request({"cmd": "config", "config": self.cfg})
        return self.cfg

    # ------------------------------------------------------------------
    # RPC: presets
    # ------------------------------------------------------------------
    async def list_presets(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "builtin": config_module.is_builtin(name)}
            for name in sorted(self.presets, key=lambda item: item.lower())
        ]

    async def save_preset(self, name: str) -> Dict[str, Any]:
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "preset name cannot be empty"}
        if len(name) > 48:
            return {"ok": False, "error": "preset name is too long"}
        self.presets[name] = config_module.preset_from_config(self.cfg)
        self.store.save_presets(self.presets)
        self.cfg = self.store.save_config({**self.cfg, "active_preset": name})
        return {"ok": True, "name": name}

    async def load_preset(self, name: str) -> Dict[str, Any]:
        body = self.presets.get(name)
        if body is None:
            return {"ok": False, "error": f"no preset named {name!r}"}
        merged = config_module.merge(self.cfg, body)
        merged["active_preset"] = name
        self.cfg = self.store.save_config(merged)
        await self._ensure_overlay()
        await self.client.request({"cmd": "config", "config": self.cfg})
        return {"ok": True, "config": self.cfg}

    async def delete_preset(self, name: str) -> Dict[str, Any]:
        if name not in self.presets:
            return {"ok": False, "error": f"no preset named {name!r}"}
        del self.presets[name]
        self.store.save_presets(self.presets)
        # A deleted built-in reappears from code on the next load, which is the
        # intended way to restore one that has been overwritten.
        self.presets = self.store.load_presets()
        if self.cfg.get("active_preset") == name:
            self.cfg = self.store.save_config({**self.cfg, "active_preset": ""})
        return {"ok": True, "restored_builtin": config_module.is_builtin(name)}

    # ------------------------------------------------------------------
    # RPC: status and diagnostics
    # ------------------------------------------------------------------
    async def get_status(self) -> Dict[str, Any]:
        response = await self.client.request({"cmd": "status"}, timeout=1.0)
        overlay = response.get("status") if response.get("ok") else None
        running = self.process is not None and self.process.returncode is None

        if overlay is None and running:
            # The helper is alive but not answering - that is a real fault,
            # not a startup race, once the process has been up for a moment.
            self.problems.record(
                "plugin",
                "Overlay process is not responding",
                response.get("error", "no response on the control socket"),
                severity="warning",
                hint="Use Restart overlay process under Advanced.",
            )
        elif overlay is not None:
            self.problems.resolve("plugin", "Overlay process is not responding")

        return {
            "overlay_running": running,
            "overlay": overlay,
            "error": self._last_error or response.get("error", ""),
            "restarts": self._restarts,
            "slot": slot.describe(),
            "tier": (overlay or {}).get("tier", "none"),
            "problems": self._merged_problems(overlay),
        }

    def _merged_problems(self, overlay: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """One list for the panel: this process' failures plus the helper's."""

        problems = list(self.problems.snapshot())
        if overlay:
            problems.extend(overlay.get("problems") or [])
        problems.sort(key=lambda item: item.get("last_seen", 0.0), reverse=True)
        return problems

    async def get_problems(self) -> List[Dict[str, Any]]:
        response = await self.client.request({"cmd": "status"}, timeout=1.0)
        overlay = response.get("status") if response.get("ok") else None
        return self._merged_problems(overlay)

    async def clear_problems(self, key: Optional[str] = None) -> Dict[str, Any]:
        """Dismiss one problem, or all of them, on both sides of the socket."""

        cleared = self.problems.clear(key)
        payload: Dict[str, Any] = {"cmd": "clear_problems"}
        if key is not None:
            payload["key"] = key
        response = await self.client.request(payload, timeout=1.0)
        cleared += int(response.get("cleared", 0) or 0)
        return {"ok": True, "cleared": cleared}

    async def get_diagnostics(self) -> Dict[str, Any]:
        """Everything needed to work out why it is not working."""

        def _probe() -> Dict[str, Any]:
            result: Dict[str, Any] = {"sensors": sensors.probe()}
            try:
                from motioncues import x11

                result["displays"] = x11.probe_displays(self.cfg["runtime"]["display"])
            except Exception as exc:  # noqa: BLE001
                result["displays"] = []
                result["display_error"] = str(exc)
            return result

        data = await asyncio.to_thread(_probe)
        data["slot"] = slot.describe()
        data["python"] = sys.version.split()[0]
        data["settings_dir"] = self.settings_dir
        return data

    async def calibrate_orientation(self) -> Dict[str, Any]:
        """Ask the overlay to derive screen-up from the live gravity vector."""

        response = await self.client.request({"cmd": "calibrate"}, timeout=2.0)
        if not response.get("ok"):
            error = response.get("error", "calibration unavailable")
            self.problems.record(
                "plugin", "Orientation calibration failed", str(error),
                severity="warning",
                hint="Hold the Deck still in your normal playing position for "
                     "a few seconds, then try again.",
            )
            return {"ok": False, "error": error}
        await self.set_config(response.get("patch", {}))
        return {"ok": True, "config": self.cfg}

    async def claim_overlay_slot(self) -> Dict[str, Any]:
        result = await asyncio.to_thread(slot.stop_mangoapp)
        if result.get("ok"):
            await self._stop_overlay()
            await self._ensure_overlay()
        return result

    async def release_overlay_slot(self) -> Dict[str, Any]:
        return await asyncio.to_thread(slot.start_mangoapp)

    async def restart_overlay(self) -> Dict[str, Any]:
        self._restarts = 0
        self._last_error = ""
        await self._stop_overlay()
        await self._ensure_overlay()
        return await self.get_status()

    # ------------------------------------------------------------------
    # RPC: Steam-UI fallback tier
    # ------------------------------------------------------------------
    async def subscribe_motion(self) -> Dict[str, Any]:
        """Start streaming motion to the frontend (fallback renderer / debug)."""

        self._fallback_subscribers += 1
        if self._fallback_task is None or self._fallback_task.done():
            self._fallback_task = self.loop.create_task(self._stream_motion())
        return {"ok": True}

    async def unsubscribe_motion(self) -> Dict[str, Any]:
        self._fallback_subscribers = max(0, self._fallback_subscribers - 1)
        if self._fallback_subscribers == 0:
            await self._stop_fallback()
        return {"ok": True}

    async def _stop_fallback(self) -> None:
        task, self._fallback_task = self._fallback_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # expected: we just cancelled it
            except Exception as exc:  # noqa: BLE001
                decky.logger.warning("motion stream ended with an error: %s", exc)
                self.problems.record(
                    "plugin",
                    "Steam UI cue stream stopped",
                    str(exc),
                    severity="warning",
                )
        if self._fallback_sensor is not None:
            try:
                self._fallback_sensor.close()
            except Exception as exc:  # noqa: BLE001
                decky.logger.warning("fallback sensor did not close cleanly: %s", exc)
            self._fallback_sensor = None

    async def _stream_motion(self) -> None:
        """Drive a second engine for the in-Steam-UI renderer.

        This deliberately runs at 30 Hz rather than display rate: every sample
        crosses Decky's websocket, and the fallback tier is a consolation
        prize, not the main event.
        """

        runtime = self.cfg["runtime"]
        try:
            self._fallback_sensor = await asyncio.to_thread(
                sensors.create, runtime["sensor_source"], runtime["synthetic_profile"])
        except Exception as exc:  # noqa: BLE001
            decky.logger.warning("fallback sensor unavailable: %s", exc)
            self.problems.record(
                "plugin",
                "Steam UI cues have no sensor",
                f"{exc}. The fallback renderer cannot show motion.",
                severity="warning",
                hint="Set Sensor source to Demo in Advanced to test without "
                     "hardware.",
            )
            await decky.emit("motion_error", str(exc))
            return

        self._fallback_engine = MotionEngine(self.cfg)
        interval = 1.0 / 30.0
        next_emit = time.monotonic()

        try:
            while self._fallback_subscribers > 0:
                samples = await asyncio.to_thread(self._fallback_sensor.read, 0.01)
                for sample in samples:
                    self._fallback_engine.ingest(sample.t, sample.accel, sample.gyro)

                now = time.monotonic()
                if now >= next_emit:
                    self._fallback_engine.apply_config(self.cfg)
                    state = self._fallback_engine.state
                    await decky.emit("motion", state.as_dict())
                    next_emit = now + interval
                await asyncio.sleep(0.002)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            decky.logger.warning("motion stream stopped: %s", exc)
            self.problems.record(
                "plugin",
                "Steam UI cue stream stopped",
                str(exc),
                severity="warning",
            )
            await decky.emit("motion_error", str(exc))
        finally:
            if self._fallback_sensor is not None:
                try:
                    self._fallback_sensor.close()
                except Exception as exc:  # noqa: BLE001
                    decky.logger.warning("fallback sensor close failed: %s", exc)
                self._fallback_sensor = None

    # ------------------------------------------------------------------
    async def _migration(self) -> None:
        decky.migrate_settings(
            os.path.join(decky.DECKY_USER_HOME, ".config", "motion-cues"))
        decky.migrate_logs(os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "motion-cues.log"))
