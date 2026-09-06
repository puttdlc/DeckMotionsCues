import struct

import pytest

from motioncues import sensors


def test_input_event_struct_is_24_bytes_on_64_bit():
    """evdev parsing depends on this; a wrong size silently garbles samples."""

    assert sensors.INPUT_EVENT_SIZE == 24


def test_evdev_scaling_constants_match_hid_steam():
    assert sensors.DEFAULT_ACCEL_RES_PER_G == 16384.0
    assert sensors.DEFAULT_GYRO_RES_PER_DPS == 16.0


def test_ioctl_number_encoding():
    # EVIOCGABS(ABS_X) = _IOR('E', 0x40, struct input_absinfo[24])
    expected = (2 << 30) | (24 << 16) | (ord("E") << 8) | 0x40
    assert sensors._ioctl_number(2, "E", 0x40, 24) == expected


def build_deck_report(accel, gyro):
    """Assemble a 64-byte Steam Deck input report with the given raw axes."""

    report = bytearray(64)
    report[0] = 0x01
    report[1] = 0x00
    report[2] = sensors.HidrawSensor.DECK_STATE
    report[3] = 56
    struct.pack_into("<6h", report, 24, *accel, *gyro)
    return bytes(report)


def test_hidraw_report_parsing_applies_the_kernel_axis_mapping():
    # hid-steam maps ABS_X=+b24, ABS_Z=-b26, ABS_Y=+b28,
    #                ABS_RX=+b30, ABS_RZ=-b32, ABS_RY=+b34.
    report = build_deck_report((100, 200, 300), (400, 500, 600))
    sample = sensors.HidrawSensor.parse_report(report, 1.0)

    assert sample is not None
    assert sample.accel[0] == pytest.approx(100 / 16384.0)   # ABS_X
    assert sample.accel[1] == pytest.approx(300 / 16384.0)   # ABS_Y from b28
    assert sample.accel[2] == pytest.approx(-200 / 16384.0)  # ABS_Z negated
    assert sample.gyro[0] == pytest.approx(400 / 16.0)       # ABS_RX
    assert sample.gyro[1] == pytest.approx(600 / 16.0)       # ABS_RY from b34
    assert sample.gyro[2] == pytest.approx(-500 / 16.0)      # ABS_RZ negated


def test_hidraw_rejects_foreign_reports():
    assert sensors.HidrawSensor.parse_report(b"\x00" * 64, 0.0) is None
    # Right header, wrong message type (0x01 is the Steam Controller frame).
    wrong_type = bytearray(build_deck_report((1, 2, 3), (4, 5, 6)))
    wrong_type[2] = 0x01
    assert sensors.HidrawSensor.parse_report(bytes(wrong_type), 0.0) is None
    assert sensors.HidrawSensor.parse_report(b"\x01\x00\x09", 0.0) is None


def test_synthetic_sensor_is_deterministic_and_scaled_like_hardware():
    source = sensors.SyntheticSensor("city", realtime=False)
    first = [source.sample_at(index * 0.004) for index in range(200)]
    source = sensors.SyntheticSensor("city", realtime=False)
    second = [source.sample_at(index * 0.004) for index in range(200)]

    assert [s.accel for s in first] == [s.accel for s in second]
    # Gravity must be present on the up axis, and accelerations must stay in a
    # physically sensible range for a vehicle.
    for sample in first:
        assert 0.8 < sample.accel[2] < 1.2
        assert abs(sample.accel[0]) < 0.5
        assert abs(sample.accel[1]) < 0.5


def test_synthetic_still_profile_is_almost_motionless():
    source = sensors.SyntheticSensor("still", realtime=False)
    samples = [source.sample_at(index * 0.004) for index in range(500)]
    assert max(abs(s.accel[0]) for s in samples) < 0.02
    assert max(abs(s.accel[1]) for s in samples) < 0.02


def test_synthetic_handling_profile_rotates_hard():
    source = sensors.SyntheticSensor("handling", realtime=False)
    samples = [source.sample_at(index * 0.004) for index in range(2000)]
    assert max(abs(s.gyro[2]) for s in samples) > 60.0


def test_unknown_profile_falls_back_rather_than_raising():
    assert sensors.SyntheticSensor("teleportation").profile == "city"


def test_unknown_source_is_rejected():
    with pytest.raises(sensors.SensorError):
        sensors.create("psychic")


def test_probe_always_reports_every_backend():
    results = sensors.probe()
    assert {entry["source"] for entry in results} == {"evdev", "iio", "hidraw", "synthetic"}
    synthetic = next(e for e in results if e["source"] == "synthetic")
    assert synthetic["available"] is True


def test_synthetic_source_can_always_be_created():
    source = sensors.create("synthetic", "boat")
    try:
        assert source.name == "synthetic"
        samples = source.read(0.05)
        assert all(len(sample.accel) == 3 for sample in samples)
    finally:
        source.close()
