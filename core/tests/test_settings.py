import pytest

from finnish_core.settings import (
    PRESETS,
    DrillSettings,
    SettingsError,
    parse_settings,
)


@pytest.mark.parametrize("preset", PRESETS.values())
def test_every_preset_is_valid(preset):
    raw = {
        "drill": preset.drill,
        "selections": preset.selections,
        "session_length": preset.session_length,
    }

    assert parse_settings(raw) == preset


def test_endless_sessions_are_allowed():
    raw = {
        "drill": "noun",
        "selections": {"cases": ["+Nom"], "numbers": ["+Sg"]},
        "session_length": None,
    }

    assert parse_settings(raw) == DrillSettings("noun", raw["selections"], None)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "must be an object"),
        ({"drill": "adverb"}, "unknown drill"),
        ({"drill": "noun", "selections": {"cases": ["+Nom"]}}, "exactly"),
        (
            {"drill": "noun", "selections": {"cases": [], "numbers": ["+Sg"]}},
            "non-empty",
        ),
        (
            {"drill": "noun", "selections": {"cases": ["+Foo"], "numbers": ["+Sg"]}},
            r"unknown cases: \+Foo",
        ),
        (
            {
                "drill": "noun",
                "selections": {"cases": ["+Nom"], "numbers": ["+Sg"]},
                "session_length": 0,
            },
            "session_length",
        ),
        (
            {
                "drill": "noun",
                "selections": {"cases": ["+Nom"], "numbers": ["+Sg"]},
                "session_length": True,
            },
            "session_length",
        ),
    ],
)
def test_malformed_settings_are_rejected(raw, message):
    with pytest.raises(SettingsError, match=message):
        parse_settings(raw)
