import json
import os

from motioncues import config
from motioncues.problems import DEFAULT_LIMIT, ProblemLog


# --------------------------------------------------------------------------
# the log itself
# --------------------------------------------------------------------------

def test_empty_log_reports_nothing():
    log = ProblemLog()
    assert log.has_problems is False
    assert log.snapshot() == []


def test_recording_captures_the_context_needed_to_act():
    log = ProblemLog()
    log.record("sensor", "No motion sensor", "evdev node missing",
               hint="Enable gyro in the controller layout")

    entry = log.snapshot()[0]
    assert entry["source"] == "sensor"
    assert entry["title"] == "No motion sensor"
    assert entry["detail"] == "evdev node missing"
    assert entry["hint"] == "Enable gyro in the controller layout"
    assert entry["severity"] == "error"
    assert entry["count"] == 1


def test_repeats_are_folded_into_one_entry_with_a_count():
    """A failure in a 250 Hz loop must not produce 250 log entries."""

    log = ProblemLog()
    for index in range(250):
        log.record("sensor", "Read failed", f"attempt {index}")

    snapshot = log.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["count"] == 250
    # The newest detail wins, since that is the failure still happening.
    assert snapshot[0]["detail"] == "attempt 249"


def test_first_seen_is_preserved_across_repeats():
    log = ProblemLog()
    first = log.record("sensor", "Read failed")
    original = first.first_seen
    for _ in range(5):
        log.record("sensor", "Read failed")
    assert log.snapshot()[0]["first_seen"] == original


def test_distinct_problems_are_kept_separate():
    log = ProblemLog()
    log.record("sensor", "Read failed")
    log.record("overlay", "Window failed")
    assert len(log.snapshot()) == 2


def test_resolve_withdraws_a_recovered_condition():
    log = ProblemLog()
    log.record("sensor", "No motion sensor")
    assert log.has_problems is True

    assert log.resolve("sensor", "No motion sensor") is True
    assert log.has_problems is False
    # Resolving something absent is not an error.
    assert log.resolve("sensor", "No motion sensor") is False


def test_resolve_source_clears_a_whole_subsystem():
    log = ProblemLog()
    log.record("sensor", "One")
    log.record("sensor", "Two")
    log.record("overlay", "Three")

    assert log.resolve_source("sensor") == 2
    assert [entry["source"] for entry in log.snapshot()] == ["overlay"]


def test_clear_dismisses_one_or_all():
    log = ProblemLog()
    first = log.record("sensor", "One")
    log.record("overlay", "Two")

    assert log.clear(first.key) == 1
    assert len(log.snapshot()) == 1
    assert log.clear() == 1
    assert log.has_problems is False


def test_clearing_an_unknown_key_is_harmless():
    log = ProblemLog()
    log.record("sensor", "One")
    assert log.clear("nope:nothing") == 0
    assert len(log.snapshot()) == 1


def test_a_dismissed_problem_returns_if_it_happens_again():
    """Dismissing must not permanently hide a recurring fault."""

    log = ProblemLog()
    problem = log.record("sensor", "Read failed")
    log.clear(problem.key)
    assert log.has_problems is False

    log.record("sensor", "Read failed")
    assert log.has_problems is True
    assert log.snapshot()[0]["count"] == 1  # a fresh occurrence


def test_log_is_bounded_and_drops_the_oldest():
    log = ProblemLog()
    for index in range(DEFAULT_LIMIT + 15):
        log.record("source", f"problem {index}")

    snapshot = log.snapshot()
    assert len(snapshot) <= DEFAULT_LIMIT
    titles = {entry["title"] for entry in snapshot}
    assert "problem 0" not in titles          # oldest evicted
    assert f"problem {DEFAULT_LIMIT + 14}" in titles  # newest kept


def test_snapshot_is_newest_first():
    log = ProblemLog()
    log.record("a", "first")
    log.record("b", "second")
    log.record("c", "third")
    assert [entry["title"] for entry in log.snapshot()] == ["third", "second", "first"]


def test_unknown_severity_is_coerced_to_error():
    log = ProblemLog()
    log.record("sensor", "Odd", severity="catastrophe")
    assert log.snapshot()[0]["severity"] == "error"


def test_warnings_are_preserved():
    log = ProblemLog()
    log.record("sensor", "Degraded", severity="warning")
    assert log.snapshot()[0]["severity"] == "warning"


def test_explicit_key_groups_related_failures():
    log = ProblemLog()
    log.record("sensor", "Axis x failed", key="sensor:axis")
    log.record("sensor", "Axis y failed", key="sensor:axis")
    assert len(log.snapshot()) == 1


# --------------------------------------------------------------------------
# the settings store reports its fallbacks
# --------------------------------------------------------------------------

def test_missing_settings_file_is_not_a_problem(tmp_path):
    """First run must be silent - there is nothing wrong with it."""

    log = ProblemLog()
    store = config.Store(str(tmp_path), problems=log)
    store.load_config()
    assert log.has_problems is False


def test_corrupt_settings_are_reported_not_silently_replaced(tmp_path):
    log = ProblemLog()
    store = config.Store(str(tmp_path), problems=log)
    with open(store.config_path, "w", encoding="utf-8") as handle:
        handle.write("{ not json")

    cfg = store.load_config()
    assert cfg["mode"] == config.DEFAULTS["mode"]  # still recovers
    entry = log.snapshot()[0]
    assert entry["source"] == "settings"
    assert "corrupt" in entry["title"].lower()


def test_a_good_load_withdraws_an_earlier_settings_problem(tmp_path):
    log = ProblemLog()
    store = config.Store(str(tmp_path), problems=log)
    with open(store.config_path, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    store.load_config()
    assert log.has_problems is True

    store.save_config(config.validate({}))
    store.load_config()
    assert log.has_problems is False


def test_corrupt_presets_file_is_reported(tmp_path):
    log = ProblemLog()
    store = config.Store(str(tmp_path), problems=log)
    with open(store.presets_path, "w", encoding="utf-8") as handle:
        handle.write("[[[")

    presets = store.load_presets()
    assert "Car" in presets  # built-ins survive
    assert any("preset" in entry["title"].lower() for entry in log.snapshot())


def test_unwritable_settings_directory_is_reported(tmp_path, monkeypatch):
    log = ProblemLog()
    store = config.Store(str(tmp_path), problems=log)

    def explode(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(config, "_atomic_write", explode)
    store.save_config(config.validate({}))

    entry = log.snapshot()[0]
    assert "saved" in entry["title"].lower()
    assert "no space left" in entry["detail"]


def test_store_without_a_log_still_works(tmp_path):
    """The log is optional; the store must not require one."""

    store = config.Store(str(tmp_path))
    with open(store.config_path, "w", encoding="utf-8") as handle:
        handle.write("nonsense")
    assert store.load_config()["mode"] == config.DEFAULTS["mode"]


def test_settings_written_by_the_store_are_valid_json(tmp_path):
    store = config.Store(str(tmp_path))
    store.save_config(config.validate({}))
    with open(store.config_path, "r", encoding="utf-8") as handle:
        assert isinstance(json.load(handle), dict)
    assert os.path.exists(store.config_path)


# --------------------------------------------------------------------------
# sensor backends report degraded behaviour instead of faking data
# --------------------------------------------------------------------------

def test_iio_axis_failure_is_reported_not_reported_as_zero_motion(tmp_path):
    """Returning 0.0 silently is indistinguishable from 'perfectly still'."""

    from motioncues import sensors

    log = ProblemLog()
    sensor = sensors.IioSensor(str(tmp_path))
    sensor.problems = log

    # No in_accel_x_raw exists in this directory, so the read must fail.
    assert sensor._axis("in_accel", "x", 1.0) == 0.0
    entry = log.snapshot()[0]
    assert entry["source"] == "sensor/iio"
    assert "could not be read" in entry["title"].lower()


def test_iio_axis_recovery_withdraws_the_problem(tmp_path):
    from motioncues import sensors

    log = ProblemLog()
    sensor = sensors.IioSensor(str(tmp_path))
    sensor.problems = log
    sensor._axis("in_accel", "x", 1.0)
    assert log.has_problems is True

    with open(tmp_path / "in_accel_x_raw", "w", encoding="utf-8") as handle:
        handle.write("1234")
    assert sensor._axis("in_accel", "x", 2.0) == 2468.0
    assert log.has_problems is False


def test_non_numeric_iio_value_is_reported(tmp_path):
    from motioncues import sensors

    log = ProblemLog()
    sensor = sensors.IioSensor(str(tmp_path))
    sensor.problems = log
    with open(tmp_path / "in_accel_x_raw", "w", encoding="utf-8") as handle:
        handle.write("banana")

    assert sensor._axis("in_accel", "x", 1.0) == 0.0
    assert any("non-numeric" in entry["title"].lower() for entry in log.snapshot())


def test_sensor_backends_work_without_a_problem_log():
    """The log is optional everywhere it is used."""

    from motioncues import sensors

    source = sensors.create("synthetic", "city")
    try:
        assert source.problems is None
        assert source.read(0.02) is not None
    finally:
        source.close()
