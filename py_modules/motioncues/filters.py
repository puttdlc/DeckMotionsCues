"""Signal processing primitives for the motion pipeline.

Everything here is time-step aware: filter coefficients are derived from the
measured ``dt`` rather than assuming a fixed sample rate, because the Steam
Deck IMU delivers samples in bursts and the effective rate changes with
system load.  Assuming a fixed rate is the classic way to get a filter that
feels fine on the bench and sluggish in a car.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

Vec3 = Tuple[float, float, float]


# --------------------------------------------------------------------------
# vector helpers
# --------------------------------------------------------------------------

def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vnorm(a: Vec3) -> float:
    return math.sqrt(vdot(a, a))


def vunit(a: Vec3, fallback: Vec3 = (0.0, 0.0, 1.0)) -> Vec3:
    length = vnorm(a)
    if length < 1e-9:
        return fallback
    return (a[0] / length, a[1] / length, a[2] / length)


def alpha_for(dt: float, tau: float) -> float:
    """One-pole smoothing coefficient for a time constant ``tau``."""

    if tau <= 1e-6:
        return 1.0
    if dt <= 0.0:
        return 0.0
    return 1.0 - math.exp(-dt / tau)


# --------------------------------------------------------------------------
# scalar / vector filters
# --------------------------------------------------------------------------

class OnePole:
    """Time-constant based one-pole low-pass over a scalar."""

    __slots__ = ("tau", "value", "primed")

    def __init__(self, tau: float, initial: float = 0.0) -> None:
        self.tau = tau
        self.value = initial
        self.primed = False

    def reset(self, value: float = 0.0) -> None:
        self.value = value
        self.primed = False

    def update(self, sample: float, dt: float) -> float:
        if not self.primed:
            self.value = sample
            self.primed = True
            return self.value
        self.value += (sample - self.value) * alpha_for(dt, self.tau)
        return self.value


class OnePole3:
    """One-pole low-pass over a 3-vector."""

    __slots__ = ("tau", "value", "primed")

    def __init__(self, tau: float, initial: Vec3 = (0.0, 0.0, 0.0)) -> None:
        self.tau = tau
        self.value = initial
        self.primed = False

    def reset(self, value: Vec3 = (0.0, 0.0, 0.0)) -> None:
        self.value = value
        self.primed = False

    def update(self, sample: Vec3, dt: float) -> Vec3:
        if not self.primed:
            self.value = sample
            self.primed = True
            return self.value
        a = alpha_for(dt, self.tau)
        self.value = (
            self.value[0] + (sample[0] - self.value[0]) * a,
            self.value[1] + (sample[1] - self.value[1]) * a,
            self.value[2] + (sample[2] - self.value[2]) * a,
        )
        return self.value


class EwmaRms:
    """Exponentially weighted RMS - a windowed energy estimate without a buffer."""

    __slots__ = ("tau", "mean_square", "primed")

    def __init__(self, tau: float) -> None:
        self.tau = tau
        self.mean_square = 0.0
        self.primed = False

    def reset(self) -> None:
        self.mean_square = 0.0
        self.primed = False

    def update(self, sample: float, dt: float) -> float:
        square = sample * sample
        if not self.primed:
            self.mean_square = square
            self.primed = True
        else:
            self.mean_square += (square - self.mean_square) * alpha_for(dt, self.tau)
        return self.value

    @property
    def value(self) -> float:
        return math.sqrt(max(self.mean_square, 0.0))


class GravityEstimator:
    """Separates the gravity vector from linear acceleration.

    A slow low-pass on the raw accelerometer converges to gravity because
    sustained non-gravitational acceleration is rare; whatever is left is
    linear acceleration.  ``tau`` trades convergence speed against how much
    genuine low-frequency vehicle motion leaks into the gravity estimate.

    The time constant is *adaptive*, which is what makes this a complementary
    filter rather than a plain low-pass.  The gyro says whether the Deck is
    actually rotating:

    * rotating - the gravity direction really is changing, so track it fast;
    * not rotating - any acceleration must be linear, so hold the estimate
      still and let the vehicle band through.

    Without this, repositioning the Deck injects up to 1 g of apparent linear
    acceleration that takes several seconds to decay, and the dots swing to
    full travel for no good reason.
    """

    __slots__ = ("_lp", "rotation_reference")

    def __init__(self, tau: float = 1.6, rotation_reference: float = 10.0) -> None:
        self._lp = OnePole3(tau)
        #: Tilt rate (deg/s) at which the time constant is halved.  This is
        #: deliberately small because the caller passes only the *tilt*
        #: component of rotation - see :meth:`update`.
        self.rotation_reference = rotation_reference

    @property
    def tau(self) -> float:
        return self._lp.tau

    @tau.setter
    def tau(self, value: float) -> None:
        self._lp.tau = value

    @property
    def gravity(self) -> Vec3:
        return self._lp.value

    @property
    def primed(self) -> bool:
        return self._lp.primed

    def reset(self) -> None:
        self._lp.reset()

    #: The estimate never tracks faster than this, so a sharp jolt is still
    #: reported as linear acceleration rather than being absorbed as gravity.
    MIN_TAU = 0.15

    def update(self, accel: Vec3, dt: float, rotation_dps: float = 0.0) -> Vec3:
        """Feed a raw accelerometer sample (in g); returns linear accel (in g).

        ``rotation_dps`` must be the *tilt* rate - the component of angular
        velocity perpendicular to gravity, from :func:`tilt_rate`.  Rotation
        about the gravity axis (a car turning a corner) leaves the gravity
        direction unchanged in the device frame, so feeding it total gyro
        magnitude would make the estimator chase gravity through every turn
        and cancel the very cue the turn should produce.
        """

        base_tau = self._lp.tau
        if rotation_dps > 0.0 and self.rotation_reference > 0.0:
            ratio = rotation_dps / self.rotation_reference
            effective = base_tau / (1.0 + ratio * ratio)
            self._lp.tau = max(self.MIN_TAU, effective)
        try:
            gravity = self._lp.update(accel, dt)
        finally:
            self._lp.tau = base_tau
        return vsub(accel, gravity)


class VehicleFrame:
    """Resolves device-frame acceleration into vehicle-frame components.

    The device axes that correspond to "screen right" and "screen up" are
    configurable because the mapping between the Deck's IMU axes and the
    screen is exactly the thing that cannot be verified without hardware.
    The third axis (the screen normal, pointing out of the screen toward the
    user) is derived so the basis stays right-handed.

    Given gravity, the horizontal plane is known, and:

    * **forward** is the horizontal direction pointing away from the user,
      i.e. the screen normal flattened into the horizontal plane;
    * **right** is the horizontal direction to the user's right;
    * **up** is straight up.

    When the Deck is held flat (screen toward the sky) the screen normal is
    nearly parallel to gravity and cannot define "forward", so the screen-up
    axis is used as the reference direction instead.
    """

    AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

    def __init__(self, axis_right: str = "x", right_sign: int = 1,
                 axis_up: str = "y", up_sign: int = 1) -> None:
        self.configure(axis_right, right_sign, axis_up, up_sign)

    def configure(self, axis_right: str, right_sign: int,
                  axis_up: str, up_sign: int) -> None:
        ri = self.AXIS_INDEX.get(axis_right, 0)
        ui = self.AXIS_INDEX.get(axis_up, 1)
        if ri == ui:  # degenerate mapping - fall back to a sane basis
            ri, ui = 0, 1
            right_sign = up_sign = 1
        right = [0.0, 0.0, 0.0]
        right[ri] = 1.0 if right_sign >= 0 else -1.0
        up = [0.0, 0.0, 0.0]
        up[ui] = 1.0 if up_sign >= 0 else -1.0
        self.device_right: Vec3 = (right[0], right[1], right[2])
        self.device_up: Vec3 = (up[0], up[1], up[2])
        # Right-handed: right x up = out of the screen, toward the user.
        self.device_normal: Vec3 = vcross(self.device_right, self.device_up)

    def resolve(self, linear: Vec3, gravity: Vec3) -> Tuple[float, float, float]:
        """Return ``(longitudinal, lateral, vertical)`` acceleration.

        Longitudinal is positive when accelerating forward (away from the
        user), lateral is positive to the user's right, vertical is positive
        upward.
        """

        # An accelerometer at rest measures specific force: +1 g along the axis
        # pointing *up*, not down.  So the low-passed vector is "up".
        up = vunit(gravity, (0.0, 0.0, 1.0))
        # "Away from the user" is the negated screen normal.
        reference = vscale(self.device_normal, -1.0)
        horizontal = vsub(reference, vscale(up, vdot(reference, up)))
        if vnorm(horizontal) < 0.25:
            # Deck lying flat: the screen normal is useless as a heading, so
            # use the screen-up axis (which now points roughly forward).
            reference = self.device_up
            horizontal = vsub(reference, vscale(up, vdot(reference, up)))
        forward = vunit(horizontal, (0.0, 1.0, 0.0))
        right = vcross(forward, up)

        return vdot(linear, forward), vdot(linear, right), vdot(linear, up)


class VehicleDetector:
    """Heuristic "are we in a moving vehicle?" classifier.

    Vehicle travel shows up as *sustained, low-frequency* linear acceleration
    with comparatively little rotation: a car sways, brakes and turns over
    seconds, while a person picking the Deck up produces a short burst of
    large rotation.  The detector therefore requires accelerometer energy in
    the vehicle band to stay above a threshold for several seconds *while*
    rotation stays modest, and uses separate enter/exit thresholds and dwell
    times so it does not chatter at the boundary.

    Known limitations (documented in the README):

    * A perfectly smooth ride (highway cruise, modern train on welded rail)
      can fall below the enter threshold and disengage.
    * Vigorous handheld play - shaking the Deck while gaming - can look like
      rough road and trigger a false positive.
    * It cannot distinguish a stopped car from standing still, so cues fade
      out at long traffic lights.
    """

    def __init__(self, enter_threshold: float = 0.040, exit_threshold: float = 0.022,
                 enter_seconds: float = 4.0, exit_seconds: float = 12.0,
                 handling_gyro_dps: float = 55.0) -> None:
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.enter_seconds = enter_seconds
        self.exit_seconds = exit_seconds
        self.handling_gyro_dps = handling_gyro_dps

        # ~2 s energy window: long enough to ignore a single pothole, short
        # enough to react within the dwell time.
        self._accel_rms = EwmaRms(2.0)
        self._gyro_rms = EwmaRms(1.5)
        self.engaged = False
        self._evidence = 0.0
        self._absence = 0.0

    def configure(self, enter_threshold: float, exit_threshold: float,
                  enter_seconds: float, exit_seconds: float,
                  handling_gyro_dps: float) -> None:
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.enter_seconds = enter_seconds
        self.exit_seconds = exit_seconds
        self.handling_gyro_dps = handling_gyro_dps

    def reset(self) -> None:
        self._accel_rms.reset()
        self._gyro_rms.reset()
        self.engaged = False
        self._evidence = 0.0
        self._absence = 0.0

    @property
    def accel_energy(self) -> float:
        return self._accel_rms.value

    @property
    def gyro_energy(self) -> float:
        return self._gyro_rms.value

    @property
    def progress(self) -> float:
        """0..1 progress toward the next state change - drives the UI meter."""

        if self.engaged:
            return min(1.0, self._absence / self.exit_seconds) if self.exit_seconds > 0 else 0.0
        return min(1.0, self._evidence / self.enter_seconds) if self.enter_seconds > 0 else 0.0

    def update(self, linear_horizontal: float, gyro_magnitude: float, dt: float) -> bool:
        accel_energy = self._accel_rms.update(linear_horizontal, dt)
        gyro_energy = self._gyro_rms.update(gyro_magnitude, dt)

        calm_enough = gyro_energy < self.handling_gyro_dps
        if not self.engaged:
            if accel_energy > self.enter_threshold and calm_enough:
                self._evidence += dt
                if self._evidence >= self.enter_seconds:
                    self.engaged = True
                    self._absence = 0.0
            else:
                # Decay rather than reset: stop-and-go traffic should still
                # accumulate toward engagement across brief calm stretches.
                self._evidence = max(0.0, self._evidence - dt * 0.5)
        else:
            if accel_energy < self.exit_threshold:
                self._absence += dt
                if self._absence >= self.exit_seconds:
                    self.engaged = False
                    self._evidence = 0.0
            else:
                self._absence = max(0.0, self._absence - dt * 2.0)

        return self.engaged


def tilt_rate(gyro: Vec3, gravity: Vec3) -> float:
    """Angular rate perpendicular to gravity, i.e. how fast tilt is changing.

    Rotation about the vertical axis (yaw) is excluded, because it does not
    change where gravity points relative to the device.
    """

    magnitude = vnorm(gravity)
    if magnitude < 1e-6:
        return vnorm(gyro)
    up = vscale(gravity, 1.0 / magnitude)
    parallel = vdot(gyro, up)
    perpendicular = vsub(gyro, vscale(up, parallel))
    return vnorm(perpendicular)


def soft_deadzone(value: float, width: float) -> float:
    """Subtractive deadzone - preserves sign and stays continuous at the edge."""

    if width <= 0.0:
        return value
    if value > width:
        return value - width
    if value < -width:
        return value + width
    return 0.0


def clamp_magnitude(x: float, y: float, limit: float) -> Tuple[float, float]:
    """Clamp a 2-vector radially so diagonal travel is not longer than axial."""

    magnitude = math.hypot(x, y)
    if magnitude <= limit or magnitude < 1e-9:
        return x, y
    scale = limit / magnitude
    return x * scale, y * scale


def dominant_axis(vector: Sequence[float]) -> Tuple[str, int]:
    """Return the axis name and sign of the largest component."""

    names = ("x", "y", "z")
    index = 0
    best = 0.0
    for i, component in enumerate(vector[:3]):
        if abs(component) > best:
            best = abs(component)
            index = i
    sign = 1 if vector[index] >= 0 else -1
    return names[index], sign
