"""Behavioural tests for the motion pipeline.

These encode the direction conventions that make the effect feel right rather
than inverted, which is the single easiest thing to get wrong here.
"""

import math

import pytest

from motioncues import config, sensors
from motioncues.engine import MotionEngine
from motioncues.filters import (
    EwmaRms,
    GravityEstimator,
    OnePole,
    VehicleDetector,
    VehicleFrame,
    clamp_magnitude,
    dominant_axis,
    soft_deadzone,
    tilt_rate,
)

RATE = 250.0
DT = 1.0 / RATE

#: Deck axis convention as published by hid-steam: ABS_X right-to-left,
#: ABS_Y front-to-back, ABS_Z bottom-to-top (which carries gravity at rest).
AT_REST = (0.0, 0.0, 1.0)
NO_ROTATION = (0.0, 0.0, 0.0)


def make_engine(mode="on", **motion):
    cfg = config.validate({})
    cfg["mode"] = mode
    cfg["motion"].update(motion)
    return MotionEngine(cfg)


def settle(engine, seconds=5.0, start=0.0):
    """Let the gravity estimate converge while the Deck sits still."""

    t = start
    for _ in range(int(RATE * seconds)):
        t += DT
        engine.ingest(t, AT_REST, NO_ROTATION)
    return t


def drive(engine, accel, gyro=NO_ROTATION, seconds=1.0, start=0.0):
    t = start
    state = engine.state
    for _ in range(int(RATE * seconds)):
        t += DT
        state = engine.ingest(t, accel, gyro)
    return state, t


# --------------------------------------------------------------------------
# filter primitives
# --------------------------------------------------------------------------

def test_one_pole_reaches_63_percent_after_one_tau():
    pole = OnePole(1.0)
    pole.update(0.0, DT)
    pole.primed = True
    pole.value = 0.0
    for _ in range(int(RATE)):
        pole.update(1.0, DT)
    assert 0.60 < pole.value < 0.66


def test_ewma_rms_of_constant_equals_that_constant():
    rms = EwmaRms(0.5)
    for _ in range(int(RATE * 5)):
        rms.update(3.0, DT)
    assert rms.value == pytest.approx(3.0, abs=0.01)


def test_soft_deadzone_is_continuous_and_keeps_sign():
    assert soft_deadzone(0.005, 0.01) == 0.0
    assert soft_deadzone(0.015, 0.01) == pytest.approx(0.005)
    assert soft_deadzone(-0.015, 0.01) == pytest.approx(-0.005)
    assert soft_deadzone(0.5, 0.0) == 0.5


def test_clamp_magnitude_is_radial():
    x, y = clamp_magnitude(30.0, 40.0, 10.0)
    assert math.hypot(x, y) == pytest.approx(10.0)
    # A diagonal must not travel further than an axial move.
    assert clamp_magnitude(3.0, 4.0, 10.0) == (3.0, 4.0)


def test_dominant_axis_reports_axis_and_sign():
    assert dominant_axis((0.1, -0.9, 0.2)) == ("y", -1)
    assert dominant_axis((0.0, 0.0, 1.0)) == ("z", 1)


def test_tilt_rate_ignores_rotation_about_gravity():
    gravity = (0.0, 0.0, 1.0)
    # Pure yaw about the vertical axis: gravity does not move in the device
    # frame, so this must not count as tilting.
    assert tilt_rate((0.0, 0.0, 50.0), gravity) == pytest.approx(0.0, abs=1e-9)
    # Pitch about a horizontal axis does.
    assert tilt_rate((50.0, 0.0, 0.0), gravity) == pytest.approx(50.0)


def test_gravity_estimator_separates_gravity_from_linear_acceleration():
    estimator = GravityEstimator(tau=1.0)
    for _ in range(int(RATE * 6)):
        linear = estimator.update(AT_REST, DT)
    assert estimator.gravity[2] == pytest.approx(1.0, abs=0.01)
    assert abs(linear[2]) < 0.01


def test_gravity_estimator_tracks_faster_while_tilting():
    slow = GravityEstimator(tau=3.0)
    fast = GravityEstimator(tau=3.0)
    for _ in range(int(RATE * 4)):
        slow.update(AT_REST, DT)
        fast.update(AT_REST, DT, 0.0)

    tilted = (0.0, 0.5, 0.866)
    for _ in range(int(RATE * 0.6)):
        slow.update(tilted, DT, 0.0)
        fast.update(tilted, DT, 50.0)  # 50 deg/s of genuine tilt

    # The gyro-informed estimator has moved much closer to the new gravity.
    assert fast.gravity[1] > slow.gravity[1] * 2


# --------------------------------------------------------------------------
# frame resolution
# --------------------------------------------------------------------------

def test_vehicle_frame_returns_orthogonal_components():
    frame = VehicleFrame("x", 1, "z", 1)
    gravity = (0.0, 0.0, 1.0)
    longitudinal, lateral, vertical = frame.resolve((0.0, 0.0, 0.3), gravity)
    assert vertical == pytest.approx(0.3)
    assert longitudinal == pytest.approx(0.0, abs=1e-9)
    assert lateral == pytest.approx(0.0, abs=1e-9)


def test_vehicle_frame_handles_deck_lying_flat():
    """Screen pointing at the sky: the screen normal cannot define forward."""

    frame = VehicleFrame("x", 1, "z", 1)
    gravity = (0.0, 1.0, 0.0)  # "up" is now the front-to-back axis
    longitudinal, lateral, vertical = frame.resolve((0.0, 0.2, 0.0), gravity)
    assert vertical == pytest.approx(0.2)
    assert not math.isnan(longitudinal)
    assert not math.isnan(lateral)


# --------------------------------------------------------------------------
# direction conventions - dots move opposite to acceleration
# --------------------------------------------------------------------------

def test_braking_moves_dots_up_the_screen():
    engine = make_engine()
    t = settle(engine)
    state, _ = drive(engine, (0.0, -0.4, 1.0), seconds=1.0, start=t)
    assert state.longitudinal < 0
    assert state.dy < -1.0  # negative dy is upward in screen coordinates


def test_accelerating_moves_dots_down_the_screen():
    engine = make_engine()
    t = settle(engine)
    state, _ = drive(engine, (0.0, 0.4, 1.0), seconds=1.0, start=t)
    assert state.longitudinal > 0
    assert state.dy > 1.0


def test_rightward_acceleration_moves_dots_left():
    engine = make_engine()
    t = settle(engine)
    # Default orientation assumes ABS_X points to the user's right; see the
    # axis notes in config.DEFAULTS.  "Invert sideways" flips this if the
    # hardware disagrees.
    state, _ = drive(engine, (0.3, 0.0, 1.0), seconds=1.0, start=t)
    assert state.lateral > 0
    assert state.dx < -1.0


def test_lateral_and_longitudinal_axes_are_independent():
    """A pure fore/aft input must not bleed into sideways travel."""

    engine = make_engine()
    t = settle(engine)
    state, _ = drive(engine, (0.0, 0.4, 1.0), seconds=1.0, start=t)
    assert abs(state.lateral) < 0.01
    assert abs(state.dx) < abs(state.dy) * 0.1


def test_turning_right_moves_dots_left_from_gyro_alone():
    engine = make_engine()
    t = settle(engine)
    # Yaw about the up axis; negative Z rotation is a right-hand turn.
    state, _ = drive(engine, AT_REST, (0.0, 0.0, -30.0), seconds=1.0, start=t)
    assert state.yaw_rate > 0
    assert state.dx < -1.0


def test_invert_flags_mirror_the_response():
    plain = make_engine()
    t = settle(plain)
    normal, _ = drive(plain, (0.0, -0.4, 1.0), seconds=1.0, start=t)

    inverted = make_engine(invert_y=True)
    t = settle(inverted)
    flipped, _ = drive(inverted, (0.0, -0.4, 1.0), seconds=1.0, start=t)

    assert normal.dy * flipped.dy < 0


# --------------------------------------------------------------------------
# dynamics
# --------------------------------------------------------------------------

def test_travel_never_exceeds_max_travel():
    engine = make_engine(max_travel=30.0)
    t = settle(engine)
    peak = 0.0
    for _ in range(int(RATE * 6)):
        t += DT
        state = engine.ingest(t, (-2.0, 2.0, 1.0), (0.0, 0.0, -200.0))
        peak = max(peak, math.hypot(state.dx, state.dy))
    assert peak <= 30.0 + 1e-6


def test_dots_return_to_centre_when_motion_stops():
    engine = make_engine()
    t = settle(engine)
    _, t = drive(engine, (0.0, 0.4, 1.0), seconds=2.0, start=t)
    state, _ = drive(engine, AT_REST, seconds=10.0, start=t)
    assert abs(state.dx) < 0.5
    assert abs(state.dy) < 0.5


def test_stationary_device_produces_no_movement():
    engine = make_engine()
    t = settle(engine)
    state, _ = drive(engine, AT_REST, seconds=3.0, start=t)
    assert abs(state.dx) < 0.05
    assert abs(state.dy) < 0.05


def test_smoothing_slows_the_response():
    quick = make_engine(smoothing=0.0)
    slow = make_engine(smoothing=0.95)
    for engine in (quick, slow):
        engine._settled_t = settle(engine)

    quick_state, _ = drive(quick, (0.0, 0.4, 1.0), seconds=0.15,
                           start=quick._settled_t)
    slow_state, _ = drive(slow, (0.0, 0.4, 1.0), seconds=0.15,
                          start=slow._settled_t)
    assert abs(quick_state.dy) > abs(slow_state.dy)


def test_deadzone_suppresses_small_motion():
    engine = make_engine(deadzone=0.05)
    t = settle(engine)
    state, _ = drive(engine, (0.0, 0.02, 1.0), seconds=1.0, start=t)
    assert abs(state.dy) < 0.5


def test_glitched_timestamps_do_not_explode_the_filter():
    engine = make_engine()
    settle(engine)
    for timestamp in (0.0, -5.0, 1e12, float("nan")):
        state = engine.ingest(timestamp, (0.0, 0.2, 1.0), NO_ROTATION)
        assert math.isfinite(state.dx) and math.isfinite(state.dy)


def test_step_only_keeps_easing_between_sensor_bursts():
    engine = make_engine()
    t = settle(engine)
    drive(engine, (0.0, 0.4, 1.0), seconds=0.05, start=t)
    before = engine.state.dy
    for _ in range(10):
        engine.step_only(1.0 / 60.0)
    assert engine.state.dy != before


# --------------------------------------------------------------------------
# modes and fading
# --------------------------------------------------------------------------

def test_mode_off_hides_the_cues():
    engine = make_engine(mode="off")
    t = settle(engine)
    state, _ = drive(engine, (0.0, 0.4, 1.0), seconds=3.0, start=t)
    assert state.alpha == 0.0
    assert state.visible is False


def test_mode_on_shows_cues_without_waiting_for_detection():
    engine = make_engine(mode="on")
    state, _ = drive(engine, AT_REST, seconds=3.0)
    assert state.alpha > 0.99
    assert state.engaged is False  # visible, but detection is independent


def test_autocalibration_finds_the_up_axis():
    engine = make_engine()
    # Hold the Deck so that gravity lands on the front-to-back axis instead.
    t = 0.0
    for _ in range(int(RATE * 6)):
        t += DT
        engine.ingest(t, (0.0, 1.0, 0.0), NO_ROTATION)
    patch = engine.autocalibrate()
    assert patch is not None
    assert patch["axis_up"] == "y"
    assert patch["axis_up_sign"] == 1
    assert patch["axis_right"] != "y"


def test_autocalibration_declines_before_gravity_settles():
    assert make_engine().autocalibrate() is None


# --------------------------------------------------------------------------
# automatic detection
# --------------------------------------------------------------------------

def run_profile(profile, seconds=60.0, mode="auto"):
    cfg = config.validate({})
    cfg["mode"] = mode
    engine = MotionEngine(cfg)
    source = sensors.SyntheticSensor(profile, rate_hz=RATE, realtime=False)
    t = 0.0
    for _ in range(int(RATE * seconds)):
        t += DT
        sample = source.sample_at(t)
        engine.ingest(t, sample.accel, sample.gyro)
    return engine.state


@pytest.mark.parametrize("profile", ["city", "train", "boat"])
def test_vehicle_profiles_engage_automatic_mode(profile):
    assert run_profile(profile).engaged is True


@pytest.mark.parametrize("profile", ["still", "handling"])
def test_non_vehicle_profiles_do_not_engage(profile):
    assert run_profile(profile).engaged is False


def test_detector_uses_hysteresis():
    detector = VehicleDetector(enter_threshold=0.04, exit_threshold=0.02,
                               enter_seconds=2.0, exit_seconds=4.0)
    for _ in range(int(RATE * 6)):
        detector.update(0.08, 2.0, DT)
    assert detector.engaged is True

    # Energy between the two thresholds must not immediately disengage.
    for _ in range(int(RATE * 6)):
        detector.update(0.03, 2.0, DT)
    assert detector.engaged is True

    for _ in range(int(RATE * 8)):
        detector.update(0.001, 2.0, DT)
    assert detector.engaged is False


def test_detector_rejects_handling_even_with_high_energy():
    detector = VehicleDetector(enter_threshold=0.04, enter_seconds=2.0,
                               handling_gyro_dps=55.0)
    for _ in range(int(RATE * 20)):
        detector.update(0.20, 150.0, DT)
    assert detector.engaged is False


def test_detector_progress_is_bounded():
    detector = VehicleDetector(enter_seconds=3.0)
    for _ in range(int(RATE * 10)):
        detector.update(0.08, 1.0, DT)
        assert 0.0 <= detector.progress <= 1.0
