import json

from finnish_core.settings import DrillSettings, get_preset
from finnish_cli.settings_store import SettingsStore


def test_settings_round_trip_uses_stable_grammar_ids(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = DrillSettings(
        drill="noun",
        selections={"cases": ["+Nom", "+Par"], "numbers": ["+Sg"]},
        session_length=20,
    )

    store.save(settings)

    assert store.load("noun") == settings
    assert store.load_recent() == settings
    payload = json.loads((tmp_path / "settings.json").read_text())
    assert payload["version"] == 1
    assert payload["last"]["noun"]["selections"]["cases"] == ["+Nom", "+Par"]


def test_corrupt_settings_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json")

    assert SettingsStore(path).load("noun") is None


def test_unknown_stable_ids_are_rejected_and_detectable_for_reset(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(
        DrillSettings("noun", {"cases": ["obsolete-case"], "numbers": ["+Sg"]}, 10)
    )

    assert store.load("noun") is None
    assert store.has_saved("noun") is True


def test_saved_setup_can_be_reset_without_removing_other_drills(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10))
    store.save(
        DrillSettings(
            "verb",
            {"types": ["1"], "tenses": ["+Ind+Prs"], "persons": ["+Sg1"]},
            20,
        )
    )

    store.reset("noun")

    assert store.load("noun") is None
    assert store.load("verb") is not None

    store.reset()
    assert store.load("verb") is None
    assert store.load_recent() is None


def test_beginner_preset_is_short_and_focused():
    preset = get_preset("noun", "beginner")

    assert preset.session_length == 10
    assert preset.selections == {"cases": ["+Nom", "+Gen", "+Par"], "numbers": ["+Sg"]}


def test_each_drill_has_a_focused_preset():
    assert get_preset("noun", "focused").drill == "noun"
    assert get_preset("verb", "focused").drill == "verb"
    assert get_preset("participle", "focused").drill == "participle"
