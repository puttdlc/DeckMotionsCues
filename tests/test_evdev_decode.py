"""Decode tests for the primary sensor path.

The device itself cannot be opened off-hardware, but the byte-level decoding
is where the real risk lives, so it is exercised directly.
"""

import struct
import time

import pytest

from motioncues import sensors


def event(etype, code, value, seconds=1, microseconds=0):
    return struct.pack(sensors.INPUT_EVENT_FORMAT, seconds, microseconds,
                       etype, code, value)


def imu_frame(accel, gyro, seconds=1, microseconds=0):
    """A full IMU report: six axis events terminated by SYN_REPORT."""

    codes = [sensors.ABS_X, sensors.ABS_Y, sensors.ABS_Z,
             sensors.ABS_RX, sensors.ABS_RY, sensors.ABS_RZ]
    payload = b"".join(
        event(sensors.EV_ABS, code, value, seconds, microseconds)
        for code, value in zip(codes, list(accel) + list(gyro))
    )
    return payload + event(sensors.EV_SYN, sensors.SYN_REPORT, 0,
                           seconds, microseconds)


def make_sensor():
    sensor = sensors.EvdevSensor("/dev/null")
    sensor._monotonic = True
    return sensor


def test_decodes_a_full_frame_with_hardware_scaling():
    sensor = make_sensor()
    samples = sensor.decode(imu_frame((16384, 0, -8192), (160, 0, -32)))

    assert len(samples) == 1
    sample = samples[0]
    assert sample.accel[0] == pytest.approx(1.0)     # 16384 counts = 1 g
    assert sample.accel[2] == pytest.approx(-0.5)
    assert sample.gyro[0] == pytest.approx(10.0)     # 16 counts = 1 deg/s
    assert sample.gyro[2] == pytest.approx(-2.0)


def test_no_sample_is_emitted_before_syn_report():
    sensor = make_sensor()
    assert sensor.decode(event(sensors.EV_ABS, sensors.ABS_X, 1000)) == []


def test_partial_event_is_buffered_across_reads():
    sensor = make_sensor()
    frame = imu_frame((16384, 0, 0), (0, 0, 0))
    split = len(frame) - 7  # cut mid-event

    assert sensor.decode(frame[:split]) == []
    samples = sensor.decode(frame[split:])
    assert len(samples) == 1
    assert samples[0].accel[0] == pytest.approx(1.0)


def test_multiple_frames_in_one_read_all_decode():
    sensor = make_sensor()
    stream = (imu_frame((16384, 0, 0), (0, 0, 0))
              + imu_frame((0, 16384, 0), (0, 0, 0))
              + imu_frame((0, 0, 16384), (0, 0, 0)))
    samples = sensor.decode(stream)

    assert len(samples) == 3
    assert samples[0].accel[0] == pytest.approx(1.0)
    assert samples[1].accel[1] == pytest.approx(1.0)
    assert samples[2].accel[2] == pytest.approx(1.0)


def test_axis_values_persist_between_frames():
    """evdev only reports axes that changed, so state must carry over."""

    sensor = make_sensor()
    sensor.decode(imu_frame((16384, 0, 0), (0, 0, 0)))
    # Second frame updates only ABS_Y.
    stream = (event(sensors.EV_ABS, sensors.ABS_Y, 8192)
              + event(sensors.EV_SYN, sensors.SYN_REPORT, 0))
    samples = sensor.decode(stream)

    assert samples[0].accel[0] == pytest.approx(1.0)  # retained
    assert samples[0].accel[1] == pytest.approx(0.5)  # updated


def test_unrelated_event_types_are_ignored():
    sensor = make_sensor()
    stream = (event(sensors.EV_MSC, sensors.MSC_TIMESTAMP, 123456)
              + imu_frame((16384, 0, 0), (0, 0, 0)))
    samples = sensor.decode(stream)
    assert len(samples) == 1


def test_timestamps_are_reconstructed_from_the_event_clock():
    sensor = make_sensor()
    samples = sensor.decode(imu_frame((0, 0, 16384), (0, 0, 0),
                                      seconds=42, microseconds=500000))
    assert samples[0].t == pytest.approx(42.5)


def test_realtime_stamps_are_rebased_onto_the_monotonic_clock():
    """Wall-clock stamps must not leak into dt maths."""

    sensor = sensors.EvdevSensor("/dev/null")
    sensor._monotonic = False

    first = sensor.decode(imu_frame((0, 0, 16384), (0, 0, 0),
                                    seconds=1_700_000_000))[0]
    second = sensor.decode(imu_frame((0, 0, 16384), (0, 0, 0),
                                     seconds=1_700_000_001))[0]

    assert second.t - first.t == pytest.approx(1.0)
    # Rebased onto time.monotonic(), not left as a raw epoch value.
    assert abs(first.t - time.monotonic()) < 5.0
