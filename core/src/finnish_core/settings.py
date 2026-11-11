"""Drill selections and presets, using stable Omorfi tag ids."""

from dataclasses import dataclass
from typing import Any

from finnish_core.forms import (
    NOUN_CASES,
    NOUN_NUMBERS,
    VERB_PARTICIPLES,
    VERB_PERSONS,
    VERB_TENSES_MOODS,
    VERB_TYPES,
)


CASE_IDS = frozenset(NOUN_CASES.values())
NUMBER_IDS = frozenset(NOUN_NUMBERS.values())

VALID_SELECTION_IDS = {
    "noun": {
        "cases": CASE_IDS,
        "numbers": NUMBER_IDS,
    },
    "verb": {
        "types": frozenset(str(value) for value in VERB_TYPES.values()),
        "tenses": frozenset(VERB_TENSES_MOODS.values()),
        "persons": frozenset(VERB_PERSONS.values()),
    },
    "participle": {
        "participles": frozenset(VERB_PARTICIPLES.values()),
        "cases": CASE_IDS,
        "numbers": NUMBER_IDS,
    },
}


@dataclass(eq=True)
class DrillSettings:
    drill: str
    selections: dict[str, list[str]]
    session_length: int | None = 10


class SettingsError(ValueError):
    """Drill settings are malformed or use unknown ids."""


def parse_settings(raw: Any) -> DrillSettings:
    """Validate plain data (such as decoded JSON) into drill settings.

    Every selection group of the drill must be present and non-empty, and use
    ids from :data:`VALID_SELECTION_IDS`.
    """
    if not isinstance(raw, dict):
        raise SettingsError("settings must be an object")
    drill = raw.get("drill")
    schema = VALID_SELECTION_IDS.get(drill) if isinstance(drill, str) else None
    if schema is None:
        raise SettingsError(f"unknown drill {drill!r}")
    selections = raw.get("selections")
    if not isinstance(selections, dict) or set(selections) != set(schema):
        raise SettingsError(
            f"{drill} selections must have exactly: {', '.join(sorted(schema))}"
        )
    for key, values in selections.items():
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) for value in values)
        ):
            raise SettingsError(f"{key} must be a non-empty list of ids")
        unknown = sorted(set(values) - schema[key])
        if unknown:
            raise SettingsError(f"unknown {key}: {', '.join(unknown)}")
    length = raw.get("session_length", 10)
    if length is not None and (
        not isinstance(length, int) or isinstance(length, bool) or length < 1
    ):
        raise SettingsError("session_length must be a positive whole number or null")
    return DrillSettings(drill, {key: list(v) for key, v in selections.items()}, length)


PRESETS = {
    ("noun", "beginner"): DrillSettings(
        "noun", {"cases": ["+Nom", "+Gen", "+Par"], "numbers": ["+Sg"]}, 10
    ),
    ("verb", "beginner"): DrillSettings(
        "verb",
        {"types": ["1"], "tenses": ["+Ind+Prs"], "persons": ["+Sg1", "+Sg2", "+Sg3"]},
        10,
    ),
    ("participle", "beginner"): DrillSettings(
        "participle",
        {"participles": ["+V+Act+PrsPrc"], "cases": ["+Nom"], "numbers": ["+Sg"]},
        10,
    ),
    ("noun", "focused"): DrillSettings(
        "noun",
        {
            "cases": ["+Ine", "+Ela", "+Ill", "+Ade", "+Abl", "+All"],
            "numbers": ["+Sg", "+Pl"],
        },
        20,
    ),
    ("verb", "focused"): DrillSettings(
        "verb",
        {
            "types": ["1", "2", "3", "4", "5", "6"],
            "tenses": ["+Ind+Prs"],
            "persons": ["+Sg1", "+Sg2", "+Sg3", "+Pl1", "+Pl2", "+Pl3"],
        },
        20,
    ),
    ("participle", "focused"): DrillSettings(
        "participle",
        {
            "participles": ["+V+Act+PrsPrc", "+V+Act+PrfPrc"],
            "cases": ["+Nom"],
            "numbers": ["+Sg", "+Pl"],
        },
        20,
    ),
}


def get_preset(drill: str, name: str) -> DrillSettings:
    try:
        preset = PRESETS[(drill, name)]
    except KeyError as error:
        raise ValueError(f"Unknown {drill} preset: {name}") from error
    return DrillSettings(
        preset.drill,
        {key: list(value) for key, value in preset.selections.items()},
        preset.session_length,
    )
