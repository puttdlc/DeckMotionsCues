"""Turns IMU samples into a dot displacement, in screen pixels.

The pipeline, per sample:

    raw accel (g) ─┬─> slow low-pass ──> gravity estimate
                   └─> minus gravity ──> linear acceleration
                                            │
                          gravity defines the horizontal plane
                                            ▼
                    longitudinal / lateral / vertical components
                                            │
                     deadzone, gain, yaw-rate term, radial clamp
                                            ▼
                    target displacement ──> response filter ──> leak to centre

Sign convention for the output: ``dx`` is positive to the right, ``dy`` is
positive *downward*, matching X11/CSS screen coordinates.  Dots move opposite
to the sensed acceleration, which is what produces the parallax cue: brake
hard (acceleration points backward) and the dots drift up the screen, the way
the world outside a window would.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from .filters import (
    EwmaRms,
    GravityEstimator,
    VehicleDetector,
    VehicleFrame,
    clamp_magnitude,
    dominant_axis,
    soft_deadzone,
    tilt_rate,
    vnorm,
)

# Sensor timestamps can jump (device wake, dropped bursts).  Anything outside
# this range is treated as a glitch and replaced with the nominal step.
MIN_DT = 1.0 / 2000.0
MAX_DT = 0.25


class MotionState:
    """Immutable-ish snapshot of the engine output."""

    __slots__ = ("dx", "dy", "alpha", "engaged", "visible", "longitudinal",
                 "lateral", "vertical", "yaw_rate", "gravity", "accel_energy",
                 "gyro_energy", "auto_progress", "rate_hz")

    def __init__(self) -> None:
        self.dx = 0.0
        self.dy = 0.0
        self.alpha = 0.0
        self.engaged = False
        self.visible = False
        self.longitudinal = 0.0
        self.lateral = 0.0
        self.vertical = 0.0
        self.yaw_rate = 0.0
        self.gravity = (0.0, 0.0, 0.0)
        self.accel_energy = 0.0
        self.gyro_energy = 0.0
        self.auto_progress = 0.0
        self.rate_hz = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
            "alpha": round(self.alpha, 4),
            "engaged": self.engaged,
            "visible": self.visible,
            "longitudinal": round(self.longitudinal, 5),
            "lateral": round(self.lateral, 5),
            "vertical": round(self.vertical, 5),
            "yaw_rate": round(self.yaw_rate, 3),
            "gravity": [round(component, 4) for component in self.gravity],
            "accel_energy": round(self.accel_energy, 5),
            "gyro_energy": round(self.gyro_energy, 3),
            "auto_progress": round(self.auto_progress, 3),
            "rate_hz": round(self.rate_hz, 1),
        }


class MotionEngine:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self._gravity = GravityEstimator()
        self._frame = VehicleFrame()
        self._detector = VehicleDetector()
        self._band = EwmaRms(2.0)
        self._rate = 0.0

        self._state = MotionState()
        self._x = 0.0
        self._y = 0.0
        self._alpha = 0.0
        self._target_x = 0.0
        self._target_y = 0.0
        self._last_t: Optional[float] = None

        self.cfg: Dict[str, Any] = {}
        self.apply_config(cfg)

    # ------------------------------------------------------------------
    def apply_config(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        motion = cfg["motion"]
        auto = cfg["auto"]

        self._gravity.tau = motion["gravity_tau"]
        self._frame.configure(
            motion["axis_right"], motion["axis_right_sign"],
            motion["axis_up"], motion["axis_up_sign"],
        )
        self._detector.configure(
            auto["enter_threshold"], auto["exit_threshold"],
            auto["enter_seconds"], auto["exit_seconds"],
            auto["handling_gyro_dps"],
        )

    def reset(self) -> None:
        self._gravity.reset()
        self._detector.reset()
        self._band.reset()
        self._x = self._y = self._alpha = 0.0
        self._last_t = None
        self._state = MotionState()

    # ------------------------------------------------------------------
    @property
    def state(self) -> MotionState:
        return self._state

    def autocalibrate(self) -> Optional[Dict[str, Any]]:
        """Derive the screen-up axis from the current gravity estimate.

        Called while the user holds the Deck normally: a resting accelerometer
        reads +1 g along whichever axis points up, so the dominant axis of the
        gravity estimate *is* screen up.  Returns a motion-config patch, or
        ``None`` if gravity has not converged yet.
        """

        gravity = self._gravity.gravity
        if not self._gravity.primed or vnorm(gravity) < 0.5:
            return None
        axis, sign = dominant_axis(gravity)
        up_sign = sign
        right_axis = self.cfg["motion"]["axis_right"]
        if right_axis == axis:
            # The configured right axis is now known to be vertical; pick any
            # remaining axis so the basis stays non-degenerate.
            right_axis = next(name for name in ("x", "y", "z") if name != axis)
        return {
            "axis_up": axis,
            "axis_up_sign": up_sign,
            "axis_right": right_axis,
        }

    # ------------------------------------------------------------------
    def ingest(self, timestamp: float, accel: Tuple[float, float, float],
               gyro: Tuple[float, float, float]) -> MotionState:
        """Feed one IMU sample. ``accel`` in g, ``gyro`` in degrees/second."""

        if self._last_t is None:
            dt = 1.0 / 250.0
        else:
            dt = timestamp - self._last_t
            if not (MIN_DT <= dt <= MAX_DT) or dt != dt:  # NaN-safe
                dt = 1.0 / 250.0
        self._last_t = timestamp
        self._rate += (1.0 / dt - self._rate) * min(1.0, dt / 0.5)

        return self._step(dt, accel, gyro)

    def step_only(self, dt: float) -> MotionState:
        """Advance the response filter without a new sample.

        Used by the renderer when it draws faster than the sensor delivers, so
        the dots keep easing toward the target instead of stepping.
        """

        dt = max(MIN_DT, min(MAX_DT, dt))
        self._integrate(dt)
        self._publish()
        return self._state

    # ------------------------------------------------------------------
    def _step(self, dt: float, accel: Tuple[float, float, float],
              gyro: Tuple[float, float, float]) -> MotionState:
        motion = self.cfg["motion"]

        rotation = math.sqrt(gyro[0] ** 2 + gyro[1] ** 2 + gyro[2] ** 2)
        # Adapt gravity tracking to tilt only, using the previous estimate as
        # the reference for "up".
        tilt = tilt_rate(gyro, self._gravity.gravity) if self._gravity.primed else rotation
        linear = self._gravity.update(accel, dt, tilt)
        gravity = self._gravity.gravity
        longitudinal, lateral, vertical = self._frame.resolve(linear, gravity)

        horizontal_magnitude = math.hypot(longitudinal, lateral)
        self._band.update(horizontal_magnitude, dt)

        # Yaw is rotation about the vertical axis; project the gyro vector onto
        # the gravity ("up") direction so it works however the Deck is held.
        # Negated so that a right-hand turn reads positive.
        gravity_magnitude = vnorm(gravity)
        if gravity_magnitude > 1e-6:
            yaw_rate = -(gyro[0] * gravity[0] + gyro[1] * gravity[1]
                         + gyro[2] * gravity[2]) / gravity_magnitude
        else:
            yaw_rate = 0.0
        gyro_magnitude = rotation

        engaged = self._detector.update(self._band.value, gyro_magnitude, dt)

        # -- target displacement ---------------------------------------
        deadzone = motion["deadzone"]
        lat = soft_deadzone(lateral, deadzone)
        lon = soft_deadzone(longitudinal, deadzone)
        vert = soft_deadzone(vertical, deadzone)

        # Dots move opposite to acceleration.  Lateral acceleration to the
        # right pushes them left; accelerating forward sends them down the
        # screen, the way scenery flows past a window.
        target_x = -motion["gain_x"] * lat
        target_y = motion["gain_y"] * (lon + motion["vertical_weight"] * vert)

        # A turn produces yaw before it produces much lateral acceleration, so
        # the yaw term makes the cue lead the corner slightly.
        target_x += -motion["gyro_gain"] * yaw_rate

        if motion["invert_x"]:
            target_x = -target_x
        if motion["invert_y"]:
            target_y = -target_y

        target_x, target_y = clamp_magnitude(target_x, target_y, motion["max_travel"])

        self._target_x = target_x
        self._target_y = target_y

        self._integrate(dt)

        state = self._state
        state.longitudinal = longitudinal
        state.lateral = lateral
        state.vertical = vertical
        state.yaw_rate = yaw_rate
        state.gravity = gravity
        state.accel_energy = self._detector.accel_energy
        state.gyro_energy = self._detector.gyro_energy
        state.auto_progress = self._detector.progress
        state.engaged = engaged
        state.rate_hz = self._rate
        self._publish()
        return state

    def _integrate(self, dt: float) -> None:
        motion = self.cfg["motion"]

        # Response: how quickly the dots chase the target.
        tau_response = 0.02 + 0.6 * motion["smoothing"]
        follow = 1.0 - math.exp(-dt / tau_response)
        self._x += (self._target_x - self._x) * follow
        self._y += (self._target_y - self._y) * follow

        # Return to centre: a slow leak so the dots settle back even while a
        # steady acceleration (a long sweeping bend) persists.
        tau_return = 0.20 + 3.0 * (1.0 - motion["return_speed"])
        leak = math.exp(-dt / tau_return)
        self._x *= leak
        self._y *= leak

        # Visibility envelope.
        mode = self.cfg["mode"]
        if mode == "off":
            target_alpha = 0.0
        elif mode == "on":
            target_alpha = 1.0
        else:
            target_alpha = 1.0 if self._detector.engaged else 0.0

        fade = self.cfg["auto"]["fade_seconds"]
        if fade <= 0.01:
            self._alpha = target_alpha
        else:
            self._alpha += (target_alpha - self._alpha) * (1.0 - math.exp(-dt / (fade / 3.0)))
            if abs(self._alpha - target_alpha) < 0.002:
                self._alpha = target_alpha

    def _publish(self) -> None:
        state = self._state
        state.dx = self._x
        state.dy = self._y
        state.alpha = self._alpha
        state.visible = self._alpha > 0.004
        state.rate_hz = self._rate
