import json
import os

from motioncues import config


def test_defaults_validate_to_themselves():
    result = config.validate({})
    assert result["version"] == config.SCHEMA_VERSION
    assert result["appearance"]["count"] == config.DEFAULTS["appearance"]["count"]
    assert result["motion"]["gain_x"] == config.DEFAULTS["motion"]["gain_x"]


def test_hostile_input_is_coerced_not_trusted():
    result = config.validate({
        "mode": "definitely-not-a-mode",
        "appearance": {"count": 10 ** 9, "size": -40, "color": "not a colour",
                       "edges": ["nope", "left", "left"], "shape": "blob"},
        "motion": {"gain_x": "abc", "invert_x": "yes", "axis_up": "w",
                   "axis_right_sign": -3},
        "auto": {"enter_threshold": 0.01, "exit_threshold": 5.0},
        "runtime": {"target_fps": 9000, "sensor_source": "telepathy"},
    })

    assert result["mode"] == "auto"
    assert 1 <= result["appearance"]["count"] <= 64
    assert result["appearance"]["size"] >= 2.0
    assert result["appearance"]["color"] == "#FFFFFF"
    assert result["appearance"]["edges"] == ["left"]
    assert result["appearance"]["shape"] == "circle"
    assert result["motion"]["gain_x"] == config.DEFAULTS["motion"]["gain_x"]
    assert result["motion"]["invert_x"] is True
    assert result["motion"]["axis_up"] == config.DEFAULTS["motion"]["axis_up"]
    assert result["motion"]["axis_right_sign"] == -1
    assert result["runtime"]["target_fps"] <= 144
    assert result["runtime"]["sensor_source"] == "auto"


def test_exit_threshold_stays_below_enter_threshold():
    result = config.validate({"auto": {"enter_threshold": 0.02, "exit_threshold": 0.09}})
    assert result["auto"]["exit_threshold"] < result["auto"]["enter_threshold"]


def test_short_hex_colour_is_expanded():
    assert config.validate({"appearance": {"color": "#3af"}})["appearance"]["color"] == "#33AAFF"


def test_merge_is_deep_and_leaves_siblings_alone():
    base = config.validate({})
    merged = config.merge(base, {"appearance": {"size": 14.0}})
    assert merged["appearance"]["size"] == 14.0
    assert merged["appearance"]["count"] == base["appearance"]["count"]
    assert merged["motion"] == base["motion"]


def test_store_roundtrip(tmp_path):
    store = config.Store(str(tmp_path))
    cfg = config.validate({})
    cfg["appearance"]["size"] = 13.5
    cfg["mode"] = "on"
    store.save_config(cfg)

    reloaded = config.Store(str(tmp_path)).load_config()
    assert reloaded["appearance"]["size"] == 13.5
    assert reloaded["mode"] == "on"


def test_store_survives_corrupt_settings_file(tmp_path):
    store = config.Store(str(tmp_path))
    with open(store.config_path, "w", encoding="utf-8") as handle:
        handle.write("{ this is not json")
    assert store.load_config()["mode"] == config.DEFAULTS["mode"]


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    store = config.Store(str(tmp_path))
    store.save_config(config.validate({}))
    leftovers = [name for name in os.listdir(tmp_path) if name.startswith(".mc-")]
    assert leftovers == []


def test_builtin_presets_are_complete_and_valid():
    assert set(config.BUILTIN_PRESETS) == {"Car", "Train/Bus", "Boat", "Subtle", "Strong"}
    base = config.validate({})
    for name, body in config.BUILTIN_PRESETS.items():
        merged = config.merge(base, body)
        assert merged["mode"] in config.MODES, name
        assert merged["motion"]["max_travel"] > 0, name


def test_presets_persist_only_user_entries(tmp_path):
    store = config.Store(str(tmp_path))
    presets = store.load_presets()
    presets["Mine"] = config.preset_from_config(config.validate({}))
    store.save_presets(presets)

    with open(store.presets_path, "r", encoding="utf-8") as handle:
        stored = json.load(handle)
    assert list(stored) == ["Mine"]

    # Built-ins still come back from code on the next load.
    reloaded = config.Store(str(tmp_path)).load_presets()
    assert "Car" in reloaded and "Mine" in reloaded


def test_user_preset_may_shadow_a_builtin_name(tmp_path):
    store = config.Store(str(tmp_path))
    presets = store.load_presets()
    custom = config.preset_from_config(config.validate({}))
    custom["motion"]["gain_x"] = 12.0
    presets["Car"] = custom
    store.save_presets(presets)

    reloaded = config.Store(str(tmp_path)).load_presets()
    assert reloaded["Car"]["motion"]["gain_x"] == 12.0


def test_preset_from_config_excludes_runtime_settings():
    cfg = config.validate({})
    cfg["runtime"]["sensor_source"] = "synthetic"
    body = config.preset_from_config(cfg)
    assert "runtime" not in body
    assert set(body) == {"mode", "appearance", "motion", "auto"}


def test_hex_to_rgb():
    assert config.hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert config.hex_to_rgb("#000000") == (0, 0, 0)
    assert config.hex_to_rgb("#3AF") == (51, 170, 255)


# --------------------------------------------------------------------------
# first-run seeding from the setup wizard
#
# The installer cannot write Decky's settings directory (only Decky knows
# where it is), so it drops the answers in defaults/first_run.json and the
# backend applies them once, on first launch. These cover that contract.
# --------------------------------------------------------------------------

def apply_seed(cfg, presets, seed):
    """Mirror of Plugin._apply_installer_defaults, minus the decky imports."""

    seed = dict(seed)
    preset = seed.pop("preset", None)
    if isinstance(preset, str) and preset in presets:
        cfg = config.merge(cfg, presets[preset])
        cfg["active_preset"] = preset
    return config.merge(cfg, seed)


def test_installer_seed_applies_preset_and_runtime_choices():
    presets = config.BUILTIN_PRESETS
    result = apply_seed(config.validate({}), presets, {
        "preset": "Boat",
        "mode": "on",
        "runtime": {"fallback_steam_ui": False, "debug_readout": True},
    })

    assert result["active_preset"] == "Boat"
    assert result["mode"] == "on"
    assert result["runtime"]["debug_readout"] is True
    assert result["runtime"]["fallback_steam_ui"] is False
    # The preset's own motion values must have come through too.
    assert result["motion"]["max_travel"] == presets["Boat"]["motion"]["max_travel"]
    assert result["appearance"]["edges"] == presets["Boat"]["appearance"]["edges"]


def test_installer_seed_mode_overrides_the_preset_mode():
    """The wizard asks for a mode separately, so it must win."""

    presets = config.BUILTIN_PRESETS
    assert presets["Car"]["mode"] == "auto"
    result = apply_seed(config.validate({}), presets, {"preset": "Car", "mode": "off"})
    assert result["mode"] == "off"


def test_installer_seed_ignores_an_unknown_preset():
    result = apply_seed(config.validate({}), config.BUILTIN_PRESETS,
                        {"preset": "Spaceship", "mode": "on"})
    assert result["mode"] == "on"
    assert result["active_preset"] == ""


def test_installer_seed_survives_a_junk_file():
    """A hand-edited first_run.json must not break startup."""

    for junk in ({}, {"preset": 12}, {"mode": "sideways"}, {"runtime": "yes"}):
        result = apply_seed(config.validate({}), config.BUILTIN_PRESETS, junk)
        assert result["mode"] in config.MODES
        assert isinstance(result["runtime"], dict)


def test_every_wizard_preset_choice_is_a_real_preset():
    """The names offered by install.sh must exist in the code."""

    offered = ["Car", "Train/Bus", "Boat", "Subtle", "Strong"]
    assert set(offered) == set(config.BUILTIN_PRESETS)
