"""IMU access for the Steam Deck, with layered fallbacks.

Four sources are supported, tried in this order:

1. **evdev** - the ``hid-steam`` kernel driver publishes a dedicated
   "Steam Deck Motion Sensors" input device (``INPUT_PROP_ACCELEROMETER``)
   carrying accelerometer on ABS_X/Y/Z and gyro on ABS_RX/RY/RZ.  Opening the
   node makes the driver ask the controller for raw IMU reports, so no
   special permissions, no root and no polling loop are needed - it is a
   blocking read on a file descriptor at the controller's native rate.
   This is the preferred path.
2. **IIO** - ``/sys/bus/iio/devices`` if some SteamOS build or another
   handheld exposes the IMU there.  Sysfs polling is slower and jitterier,
   so it is a fallback only.
3. **hidraw** - read the Valve controller's 64-byte input reports directly,
   the way SteamDeckGyroDSU does.  Used only if the kernel driver's sensor
   node is missing.
4. **synthetic** - a motion generator.  Not a fallback so much as a feature:
   it drives "Demo" mode in the UI (so the effect can be previewed and tuned
   indoors) and it makes the whole pipeline testable off-hardware.

Caveat that matters in practice: ``hid-steam`` only enables IMU reporting
when *no* userspace client has the HID device open exclusively.  In Game Mode
Steam does hold it, so whether raw IMU data flows can depend on the active
controller layout using gyro.  :func:`probe` reports this so the UI can tell
the user what to do instead of silently showing motionless dots.
"""

from __future__ import annotations

import array
import errno
import glob
import math
import os
import select
import struct
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

# The hardware backends are Linux-only, but the synthetic source, the report
# parser and the probe helpers are useful anywhere - keeping the module
# importable off-Deck is what makes the pipeline testable on a dev machine.
try:
    import fcntl
except ImportError:  # pragma: no cover - non-Linux dev machines
    fcntl = None  # type: ignore[assignment]

#: os.O_NONBLOCK is absent on some platforms; only the Linux paths use it.
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

# -- evdev constants --------------------------------------------------------
EV_SYN = 0x00
EV_ABS = 0x03
EV_MSC = 0x04
SYN_REPORT = 0x00
MSC_TIMESTAMP = 0x05

ABS_X, ABS_Y, ABS_Z = 0x00, 0x01, 0x02
ABS_RX, ABS_RY, ABS_RZ = 0x03, 0x04, 0x05

#: ``struct input_event`` on 64-bit Linux: a timeval of two 64-bit fields,
#: then ``__u16 type, __u16 code, __s32 value`` - 24 bytes total.
#:
#: The sizes are spelled out ("<qqHHi") rather than using the native "l",
#: because "l" follows the *host* C ABI: it is 8 bytes on Linux but 4 on
#: Windows, so a native format would silently mis-parse every event when the
#: parser is exercised anywhere other than the target.
INPUT_EVENT_FORMAT = "<qqHHi"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FORMAT)

CLOCK_MONOTONIC = 1

# Scaling published by hid-steam (STEAM_ACCEL_RES_PER_G / STEAM_GYRO_RES_PER_DPS).
DEFAULT_ACCEL_RES_PER_G = 16384.0
DEFAULT_GYRO_RES_PER_DPS = 16.0

VALVE_VENDOR_ID = 0x28DE

G_PER_MS2 = 1.0 / 9.80665
DPS_PER_RAD = 180.0 / math.pi


class Sample:
    """One IMU sample: acceleration in g, angular rate in degrees/second."""

    __slots__ = ("t", "accel", "gyro")

    def __init__(self, t: float, accel: Tuple[float, float, float],
                 gyro: Tuple[float, float, float]) -> None:
        self.t = t
        self.accel = accel
        self.gyro = gyro

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Sample(t={self.t:.4f}, accel={self.accel}, gyro={self.gyro})"


class SensorError(Exception):
    pass


class SensorSource:
    """Common interface for every sensor backend."""

    name = "none"
    description = "no sensor"

    #: Optional :class:`motioncues.problems.ProblemLog`.  Anything a backend
    #: has to paper over at runtime is reported through this instead of being
    #: absorbed, so degraded behaviour is visible rather than mysterious.
    problems: Any = None

    def _report(self, title: str, detail: str = "", severity: str = "error",
                hint: str = "") -> None:
        if self.problems is not None:
            self.problems.record(f"sensor/{self.name}", title, detail,
                                 severity=severity, hint=hint)

    def _resolve(self, title: str) -> None:
        if self.problems is not None:
            self.problems.resolve(f"sensor/{self.name}", title)

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def read(self, timeout: float = 0.05) -> List[Sample]:
        """Return zero or more samples, blocking at most ``timeout`` seconds."""

        raise NotImplementedError

    def fileno(self) -> Optional[int]:
        return None

    def __enter__(self) -> "SensorSource":
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# --------------------------------------------------------------------------
# evdev
# --------------------------------------------------------------------------

def _read_sysfs(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            return fp.read().strip()
    except OSError:
        return None


def find_motion_event_devices() -> List[Tuple[str, str]]:
    """Return ``(device_path, name)`` for plausible IMU event devices."""

    found: List[Tuple[str, str]] = []
    for sys_path in sorted(glob.glob("/sys/class/input/event*")):
        event_name = os.path.basename(sys_path)
        name = _read_sysfs(os.path.join(sys_path, "device", "name")) or ""
        lowered = name.lower()
        if "motion sensors" in lowered or (
            "steam" in lowered and ("sensor" in lowered or "imu" in lowered)
        ):
            found.append((os.path.join("/dev/input", event_name), name))
    # Prefer the Deck's own IMU when several motion devices are present.
    found.sort(key=lambda item: (0 if "deck" in item[1].lower() else 1, item[0]))
    return found


def _ioctl_number(direction: int, type_char: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(type_char) << 8) | number


def _abs_resolution(fd: int, axis: int) -> Optional[float]:
    """Read ``resolution`` from ``EVIOCGABS(axis)``.

    ``struct input_absinfo`` is six ``__s32`` fields; resolution is the last.
    Returns ``None`` if the value could not be read, so the caller can say so
    rather than silently assuming a scale factor - a wrong scale means every
    acceleration reading is off by a constant and the cues feel wrong for no
    visible reason.
    """

    if fcntl is None:
        return None
    request = _ioctl_number(2, "E", 0x40 + axis, 24)  # _IOR('E', 0x40+axis, input_absinfo)
    buffer = array.array("i", [0] * 6)
    try:
        fcntl.ioctl(fd, request, buffer, True)
    except OSError:
        return None
    resolution = float(buffer[5])
    return resolution if resolution > 0 else None


class EvdevSensor(SensorSource):
    name = "evdev"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.description = "hid-steam motion sensor node"
        self._fd: Optional[int] = None
        self._accel_scale = 1.0 / DEFAULT_ACCEL_RES_PER_G
        self._gyro_scale = 1.0 / DEFAULT_GYRO_RES_PER_DPS
        self._pending: Dict[int, int] = {}
        self._buffer = b""
        self._monotonic = False
        self._offset: Optional[float] = None

    def open(self) -> None:
        path = self.path
        if path is None:
            candidates = find_motion_event_devices()
            if not candidates:
                raise SensorError("no 'Steam Deck Motion Sensors' evdev node found")
            path, name = candidates[0]
            self.path = path
            self.description = name

        try:
            fd = os.open(path, os.O_RDONLY | O_NONBLOCK)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise SensorError(
                    f"{path} is not readable by this user; the plugin needs the "
                    "'_root' flag or a udev rule granting access"
                ) from exc
            raise SensorError(f"cannot open {path}: {exc}") from exc

        self._fd = fd
        # Timestamp against CLOCK_MONOTONIC so sample ages can be compared to
        # time.monotonic() without being disturbed by clock adjustments.
        try:
            if fcntl is None:
                raise OSError("fcntl unavailable")
            fcntl.ioctl(fd, _ioctl_number(1, "E", 0xA0, 4),
                        struct.pack("i", CLOCK_MONOTONIC))
            self._monotonic = True
        except OSError:
            self._monotonic = False

        accel_resolution = _abs_resolution(fd, ABS_X)
        gyro_resolution = _abs_resolution(fd, ABS_RX)
        if accel_resolution is None or gyro_resolution is None:
            self._report(
                "Sensor scale could not be read",
                f"EVIOCGABS failed on {path}; assuming the hid-steam defaults "
                f"of {DEFAULT_ACCEL_RES_PER_G:.0f} counts/g and "
                f"{DEFAULT_GYRO_RES_PER_DPS:.0f} counts/deg/s.",
                severity="warning",
                hint="Motion still works, but if the response feels uniformly "
                     "too strong or too weak, adjust the sensitivity sliders.",
            )
        else:
            self._resolve("Sensor scale could not be read")
        self._accel_scale = 1.0 / (accel_resolution or DEFAULT_ACCEL_RES_PER_G)
        self._gyro_scale = 1.0 / (gyro_resolution or DEFAULT_GYRO_RES_PER_DPS)

        if not self._monotonic:
            self._report(
                "Sensor timestamps are not monotonic",
                f"EVIOCSCLOCKID failed on {path}; event timestamps are being "
                "rebased onto the monotonic clock instead.",
                severity="warning",
                hint="Harmless unless the system clock jumps while driving.",
            )
        self._pending = {}
        self._buffer = b""
        self._offset = None

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def fileno(self) -> Optional[int]:
        return self._fd

    def _timestamp(self, seconds: int, microseconds: int) -> float:
        raw = seconds + microseconds * 1e-6
        if self._monotonic:
            return raw
        # Realtime-stamped events: convert once into the monotonic timebase so
        # downstream dt maths stays immune to wall-clock jumps.
        if self._offset is None:
            self._offset = time.monotonic() - raw
        return raw + self._offset

    def read(self, timeout: float = 0.05) -> List[Sample]:
        if self._fd is None:
            raise SensorError("sensor not open")

        readable, _, _ = select.select([self._fd], [], [], timeout)
        if not readable:
            return []

        try:
            chunk = os.read(self._fd, INPUT_EVENT_SIZE * 256)
        except BlockingIOError:
            return []
        except OSError as exc:
            raise SensorError(f"read failed on {self.path}: {exc}") from exc
        if not chunk:
            return []

        return self.decode(chunk)

    def decode(self, chunk: bytes) -> List[Sample]:
        """Turn raw evdev bytes into samples.

        Axis values accumulate until ``SYN_REPORT``, which is what marks a
        complete IMU reading; a partial trailing event is buffered for the
        next read, since a single ``read()`` is not guaranteed to end on an
        event boundary.
        """

        data = self._buffer + chunk
        usable = len(data) - (len(data) % INPUT_EVENT_SIZE)
        self._buffer = data[usable:]

        samples: List[Sample] = []
        for offset in range(0, usable, INPUT_EVENT_SIZE):
            seconds, microseconds, etype, code, value = struct.unpack_from(
                INPUT_EVENT_FORMAT, data, offset)
            if etype == EV_ABS:
                self._pending[code] = value
            elif etype == EV_SYN and code == SYN_REPORT:
                if self._pending:
                    samples.append(Sample(
                        self._timestamp(seconds, microseconds),
                        (
                            self._pending.get(ABS_X, 0) * self._accel_scale,
                            self._pending.get(ABS_Y, 0) * self._accel_scale,
                            self._pending.get(ABS_Z, 0) * self._accel_scale,
                        ),
                        (
                            self._pending.get(ABS_RX, 0) * self._gyro_scale,
                            self._pending.get(ABS_RY, 0) * self._gyro_scale,
                            self._pending.get(ABS_RZ, 0) * self._gyro_scale,
                        ),
                    ))
        return samples


# --------------------------------------------------------------------------
# IIO
# --------------------------------------------------------------------------

class IioSensor(SensorSource):
    name = "iio"

    def __init__(self, device_dir: Optional[str] = None, rate_hz: float = 100.0) -> None:
        self.device_dir = device_dir
        self.description = "IIO sysfs accelerometer"
        self.rate_hz = rate_hz
        self._accel_scale = 1.0
        self._gyro_scale = 0.0
        self._next = 0.0

    @staticmethod
    def find_devices() -> List[str]:
        devices = []
        for path in sorted(glob.glob("/sys/bus/iio/devices/iio:device*")):
            if glob.glob(os.path.join(path, "in_accel_*_raw")):
                devices.append(path)
        return devices

    def open(self) -> None:
        if self.device_dir is None:
            devices = self.find_devices()
            if not devices:
                raise SensorError("no IIO accelerometer found")
            self.device_dir = devices[0]
        name = _read_sysfs(os.path.join(self.device_dir, "name")) or "iio"
        self.description = f"IIO {name}"

        scale = _read_sysfs(os.path.join(self.device_dir, "in_accel_scale"))
        try:
            # IIO accel scale is in m/s^2 per raw count.
            self._accel_scale = float(scale) * G_PER_MS2 if scale else G_PER_MS2
        except ValueError:
            self._accel_scale = G_PER_MS2
            self._report(
                "IIO accelerometer scale is unreadable",
                f"in_accel_scale contained {scale!r}; assuming raw counts are "
                "already m/s^2.",
                severity="warning",
                hint="If the cues respond far too strongly or weakly, adjust "
                     "the sensitivity sliders.",
            )

        gyro_scale = _read_sysfs(os.path.join(self.device_dir, "in_anglvel_scale"))
        try:
            # IIO angular velocity scale is rad/s per raw count.
            self._gyro_scale = float(gyro_scale) * DPS_PER_RAD if gyro_scale else 0.0
        except ValueError:
            self._gyro_scale = 0.0

        if not self._gyro_scale:
            self._report(
                "No gyroscope on this IIO device",
                f"{self.device_dir} exposes no in_anglvel_scale, so turn "
                "detection will use acceleration only.",
                severity="warning",
                hint="Turns are still detected from lateral acceleration, but "
                     "the cue will lag slightly into a corner.",
            )
        self._next = 0.0

    def _axis(self, prefix: str, axis: str, scale: float) -> float:
        """Read one IIO axis.

        A failure here used to return 0.0, which is indistinguishable from
        "the device is perfectly still" - the cues would simply stop working
        with no indication why.  It is now reported.
        """

        path = os.path.join(self.device_dir or "", f"{prefix}_{axis}_raw")
        raw = _read_sysfs(path)
        if raw is None:
            self._report(
                "IIO axis could not be read",
                f"{path} is unreadable; that axis is being treated as zero.",
                hint="Switch Sensor source to Automatic or Demo in Advanced.",
            )
            return 0.0
        try:
            value = float(raw) * scale
        except ValueError:
            self._report(
                "IIO axis returned a non-numeric value",
                f"{path} contained {raw!r}.",
            )
            return 0.0
        self._resolve("IIO axis could not be read")
        self._resolve("IIO axis returned a non-numeric value")
        return value

    def read(self, timeout: float = 0.05) -> List[Sample]:
        now = time.monotonic()
        period = 1.0 / max(1.0, self.rate_hz)
        if now < self._next:
            time.sleep(min(timeout, self._next - now))
            now = time.monotonic()
        self._next = now + period

        accel = (
            self._axis("in_accel", "x", self._accel_scale),
            self._axis("in_accel", "y", self._accel_scale),
            self._axis("in_accel", "z", self._accel_scale),
        )
        if self._gyro_scale:
            gyro = (
                self._axis("in_anglvel", "x", self._gyro_scale),
                self._axis("in_anglvel", "y", self._gyro_scale),
                self._axis("in_anglvel", "z", self._gyro_scale),
            )
        else:
            gyro = (0.0, 0.0, 0.0)
        return [Sample(now, accel, gyro)]


# --------------------------------------------------------------------------
# hidraw
# --------------------------------------------------------------------------

def find_valve_hidraw() -> List[str]:
    """Return hidraw nodes belonging to Valve devices."""

    matches = []
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = _read_sysfs(os.path.join(path, "device", "uevent")) or ""
        if f"{VALVE_VENDOR_ID:04X}" in uevent.upper():
            matches.append(os.path.join("/dev", os.path.basename(path)))
    return matches


class HidrawSensor(SensorSource):
    """Read the Deck's 64-byte controller reports directly.

    Report layout (little-endian, confirmed against ``hid-steam`` and
    SteamDeckGyroDSU): bytes 0-1 are ``0x01 0x00``, byte 2 is the message
    type, and ``0x09`` marks a Steam Deck input frame.  Within that frame the
    accelerometer occupies bytes 24/26/28 and the gyro 30/32/34, with the sign
    conventions the kernel applies when it maps them onto ABS axes.
    """

    name = "hidraw"
    DECK_STATE = 0x09

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.description = "Valve hidraw controller reports"
        self._fd: Optional[int] = None

    def open(self) -> None:
        candidates = [self.path] if self.path else find_valve_hidraw()
        last_error: Optional[Exception] = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                self._fd = os.open(candidate, os.O_RDONLY | O_NONBLOCK)
                self.path = candidate
                self.description = f"hidraw {os.path.basename(candidate)}"
                return
            except OSError as exc:
                last_error = exc
        raise SensorError(f"no readable Valve hidraw node ({last_error})")

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def fileno(self) -> Optional[int]:
        return self._fd

    @staticmethod
    def parse_report(report: bytes, timestamp: float) -> Optional[Sample]:
        if len(report) < 36 or report[0] != 0x01 or report[1] != 0x00:
            return None
        if report[2] != HidrawSensor.DECK_STATE:
            return None
        values = struct.unpack_from("<6h", report, 24)
        accel = (
            values[0] / DEFAULT_ACCEL_RES_PER_G,
            values[2] / DEFAULT_ACCEL_RES_PER_G,
            -values[1] / DEFAULT_ACCEL_RES_PER_G,
        )
        gyro = (
            values[3] / DEFAULT_GYRO_RES_PER_DPS,
            values[5] / DEFAULT_GYRO_RES_PER_DPS,
            -values[4] / DEFAULT_GYRO_RES_PER_DPS,
        )
        return Sample(timestamp, accel, gyro)

    def read(self, timeout: float = 0.05) -> List[Sample]:
        if self._fd is None:
            raise SensorError("sensor not open")
        readable, _, _ = select.select([self._fd], [], [], timeout)
        if not readable:
            return []
        samples: List[Sample] = []
        while True:
            try:
                report = os.read(self._fd, 64)
            except BlockingIOError:
                break
            except OSError as exc:
                raise SensorError(f"read failed on {self.path}: {exc}") from exc
            if not report:
                break
            sample = HidrawSensor.parse_report(report, time.monotonic())
            if sample is not None:
                samples.append(sample)
            if len(samples) > 64:
                break
        return samples


# --------------------------------------------------------------------------
# synthetic
# --------------------------------------------------------------------------

class SyntheticSensor(SensorSource):
    """Generates plausible vehicle motion, for demo mode and for tests."""

    name = "synthetic"

    #: Each profile is a list of (amplitude in g, frequency in Hz, phase)
    #: triples per axis, plus a yaw-rate component.  They are deliberately
    #: multi-tone so the vehicle detector sees something less trivial than a
    #: pure sine.
    PROFILES: Dict[str, Dict[str, Any]] = {
        "still": {"long": [], "lat": [], "vert": [], "yaw": [], "noise": 0.002},
        "city": {
            "long": [(0.085, 0.11, 0.0), (0.04, 0.27, 1.1)],
            "lat": [(0.06, 0.08, 0.7), (0.03, 0.33, 2.2)],
            "vert": [(0.03, 1.7, 0.4)],
            "yaw": [(9.0, 0.06, 0.3)],
            "noise": 0.006,
        },
        "highway": {
            "long": [(0.03, 0.05, 0.0)],
            "lat": [(0.035, 0.07, 1.4), (0.012, 0.5, 0.2)],
            "vert": [(0.02, 2.3, 0.9)],
            "yaw": [(3.0, 0.03, 1.0)],
            "noise": 0.004,
        },
        "train": {
            "long": [(0.03, 0.04, 0.0)],
            "lat": [(0.07, 0.35, 0.5), (0.03, 0.9, 1.7)],
            "vert": [(0.05, 1.1, 0.2)],
            "yaw": [(2.0, 0.02, 0.0)],
            "noise": 0.005,
        },
        "boat": {
            "long": [(0.05, 0.16, 0.0)],
            "lat": [(0.09, 0.13, 0.9)],
            "vert": [(0.12, 0.19, 0.4)],
            "yaw": [(6.0, 0.12, 0.6)],
            "noise": 0.003,
        },
        "handling": {
            # Someone picking the Deck up: big rotation, short-lived accel.
            "long": [(0.10, 1.9, 0.0)],
            "lat": [(0.10, 2.3, 0.8)],
            "vert": [(0.15, 1.6, 0.3)],
            "yaw": [(120.0, 1.1, 0.2)],
            "noise": 0.02,
        },
    }

    def __init__(self, profile: str = "city", rate_hz: float = 250.0,
                 realtime: bool = True) -> None:
        self.profile = profile if profile in self.PROFILES else "city"
        self.description = f"synthetic '{self.profile}'"
        self.rate_hz = rate_hz
        self.realtime = realtime
        self._t = 0.0
        self._start = 0.0
        self._next = 0.0
        self._seed = 12345

    def open(self) -> None:
        self._t = 0.0
        self._start = time.monotonic()
        self._next = self._start

    def set_profile(self, profile: str) -> None:
        if profile in self.PROFILES:
            self.profile = profile
            self.description = f"synthetic '{profile}'"

    def _noise(self, scale: float) -> float:
        # Deterministic LCG so test runs are reproducible.
        self._seed = (1103515245 * self._seed + 12345) & 0x7FFFFFFF
        return ((self._seed / 0x7FFFFFFF) - 0.5) * 2.0 * scale

    def sample_at(self, t: float) -> Sample:
        """Generate the sample for time ``t`` without touching the clock."""

        spec = self.PROFILES[self.profile]

        def combine(components: Iterable[Tuple[float, float, float]]) -> float:
            return sum(amp * math.sin(2.0 * math.pi * freq * t + phase)
                       for amp, freq, phase in components)

        noise = spec["noise"]
        longitudinal = combine(spec["long"]) + self._noise(noise)
        lateral = combine(spec["lat"]) + self._noise(noise)
        vertical = combine(spec["vert"]) + self._noise(noise)
        yaw = combine(spec["yaw"]) + self._noise(noise * 40.0)

        # Emit in the Deck's default axis convention: ABS_X is right-to-left,
        # ABS_Y is front-to-back, ABS_Z is bottom-to-top and carries gravity.
        accel = (-lateral, longitudinal, 1.0 + vertical)
        gyro = (0.0, 0.0, yaw)
        return Sample(t, accel, gyro)

    def read(self, timeout: float = 0.05) -> List[Sample]:
        period = 1.0 / self.rate_hz
        samples: List[Sample] = []

        if not self.realtime:
            for _ in range(max(1, int(timeout / period))):
                self._t += period
                samples.append(self.sample_at(self._t))
            return samples

        now = time.monotonic()
        deadline = now + timeout
        while self._next <= now:
            self._t += period
            samples.append(self.sample_at(self._t))
            self._next += period
            if len(samples) >= 512:
                break
        if not samples:
            time.sleep(max(0.0, min(deadline, self._next) - now))
            now = time.monotonic()
            while self._next <= now:
                self._t += period
                samples.append(self.sample_at(self._t))
                self._next += period
        return samples


# --------------------------------------------------------------------------
# probing
# --------------------------------------------------------------------------

BUILDERS = {
    "evdev": EvdevSensor,
    "iio": IioSensor,
    "hidraw": HidrawSensor,
    "synthetic": SyntheticSensor,
}


def probe() -> List[Dict[str, Any]]:
    """Describe which sensor backends are usable on this machine."""

    results: List[Dict[str, Any]] = []

    devices = find_motion_event_devices()
    if devices:
        path, name = devices[0]
        readable = os.access(path, os.R_OK)
        results.append({
            "source": "evdev",
            "available": readable,
            "detail": f"{name} at {path}" + ("" if readable else " (not readable)"),
        })
    else:
        results.append({
            "source": "evdev",
            "available": False,
            "detail": "no 'Steam Deck Motion Sensors' node; kernel hid-steam may "
                      "predate IMU support",
        })

    iio_devices = IioSensor.find_devices()
    results.append({
        "source": "iio",
        "available": bool(iio_devices),
        "detail": iio_devices[0] if iio_devices else "no IIO accelerometer",
    })

    hidraw_nodes = find_valve_hidraw()
    readable_hidraw = [node for node in hidraw_nodes if os.access(node, os.R_OK)]
    results.append({
        "source": "hidraw",
        "available": bool(readable_hidraw),
        "detail": (readable_hidraw[0] if readable_hidraw
                   else ("found but not readable: " + ", ".join(hidraw_nodes)
                         if hidraw_nodes else "no Valve hidraw node")),
    })

    results.append({
        "source": "synthetic",
        "available": True,
        "detail": "always available (demo / testing)",
    })
    return results


def create(source: str = "auto", synthetic_profile: str = "city",
           problems: Any = None) -> SensorSource:
    """Build a sensor for ``source``, falling back through the chain for 'auto'.

    ``problems`` is an optional :class:`motioncues.problems.ProblemLog`.  In
    'auto' mode every backend that had to be skipped is recorded, so a Deck
    that quietly ends up on a degraded path says so instead of just working
    differently.
    """

    if source != "auto":
        builder = BUILDERS.get(source)
        if builder is None:
            raise SensorError(f"unknown sensor source '{source}'")
        sensor = (SyntheticSensor(synthetic_profile) if source == "synthetic"
                  else builder())
        sensor.problems = problems
        sensor.open()
        return sensor

    errors: List[str] = []
    for candidate in ("evdev", "iio", "hidraw"):
        try:
            sensor = BUILDERS[candidate]()
            sensor.problems = problems
            sensor.open()
            if candidate != "evdev" and problems is not None:
                problems.record(
                    "sensor",
                    "Using a fallback sensor backend",
                    f"The preferred kernel motion node was unavailable "
                    f"({errors[0] if errors else 'unknown reason'}), so "
                    f"'{candidate}' is being used instead.",
                    severity="warning",
                    hint="Motion still works; latency may be slightly higher.",
                )
            return sensor
        except (SensorError, OSError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise SensorError("no hardware IMU available -> " + "; ".join(errors))
