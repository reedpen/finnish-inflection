"""Drill selections and presets, using stable Omorfi tag ids."""

from dataclasses import dataclass

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
