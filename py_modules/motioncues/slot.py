"""Contention for gamescope's single external-overlay slot.

gamescope exposes exactly one external overlay layer.  On SteamOS that slot is
normally occupied by ``mangoapp`` (the performance overlay), which is started
with the session and does not release the slot even when the overlay level is
set to 0 - see MangoHud issue #775.

Two things follow:

* Current gamescope ranks competing untagged external-overlay windows by
  ``_NET_WM_WINDOW_OPACITY``, so a fully opaque window can win the slot from a
  mangoapp that has faded itself out.  That costs nothing and is always done.
* If that is not enough, the only remaining lever is to stop mangoapp.  That
  disables the performance overlay until the session restarts, so it is
  strictly opt-in and never done automatically.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Any, Dict, List

MANGOAPP_NAMES = ("mangoapp",)


def _proc_name(pid: str) -> str:
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def mangoapp_pids() -> List[int]:
    """PIDs of running mangoapp processes."""

    pids: List[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for entry in entries:
        if not entry.isdigit():
            continue
        if _proc_name(entry) in MANGOAPP_NAMES:
            pids.append(int(entry))
    return pids


def stop_mangoapp() -> Dict[str, Any]:
    """Terminate mangoapp so the overlay slot becomes free."""

    pids = mangoapp_pids()
    if not pids:
        return {"ok": True, "stopped": [], "detail": "mangoapp was not running"}

    stopped: List[int] = []
    errors: List[str] = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except OSError as exc:
            errors.append(f"pid {pid}: {exc}")

    return {
        "ok": bool(stopped) and not errors,
        "stopped": stopped,
        "detail": ("stopped mangoapp; the Steam performance overlay stays off "
                   "until the session restarts"
                   if stopped else "; ".join(errors)),
    }


def start_mangoapp(display: str = ":0") -> Dict[str, Any]:
    """Best-effort relaunch of mangoapp.

    SteamOS starts mangoapp from the gamescope session script rather than from
    a unit, so there is nothing to "restart" cleanly.  Re-exec it directly and
    say plainly that a session restart is the reliable route.
    """

    if mangoapp_pids():
        return {"ok": True, "detail": "mangoapp already running"}
    environment = dict(os.environ)
    environment.setdefault("DISPLAY", display)
    try:
        subprocess.Popen(
            ["mangoapp"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False,
                "detail": f"could not relaunch mangoapp ({exc}); restart the "
                          "Steam session to restore the performance overlay"}
    return {"ok": True, "detail": "relaunched mangoapp"}


def describe() -> Dict[str, Any]:
    pids = mangoapp_pids()
    return {
        "mangoapp_running": bool(pids),
        "mangoapp_pids": pids,
        "detail": ("mangoapp holds gamescope's external-overlay slot; Motion "
                   "Cues competes for it by opacity"
                   if pids else "external-overlay slot appears free"),
    }
