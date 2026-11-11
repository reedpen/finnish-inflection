"""Full inflection tables: every form a drill can ask about, keyed by Omorfi tag.

A table maps a form id (the Omorfi tag, such as ``+N+Pl+Ine``) to its accepted
answers. Tables can be generated once and stored, so drills, hints, and answer
checking need no morphology model.
"""

from collections.abc import Callable, Sequence

from finnish_core.forms import (
    NOUN_CASES,
    NOUN_NUMBERS,
    VERB_PARTICIPLES,
    VERB_PERSONS,
    VERB_TENSES_MOODS,
    get_noun_tag,
    get_participle_tag,
    get_verb_tag,
    noun_combinations,
)
from finnish_core.morphology import InflectionEngine
from finnish_core.vocab import VocabularyEntry

FormLookup = Callable[[VocabularyEntry, str], Sequence[str]]
"""Return the accepted answers for one word and form id (empty if none)."""


def declension_form_ids(pos: str = "N") -> list[str]:
    """Form ids for every case and number of a noun or adjective."""
    return [
        get_noun_tag(case, number, pos)
        for case, number in noun_combinations(NOUN_CASES, NOUN_NUMBERS)
    ]


def conjugation_form_ids() -> list[str]:
    """Form ids for every finite verb form and every declined participle."""
    finite = [
        get_verb_tag(tense, person)
        for tense in VERB_TENSES_MOODS
        for person in VERB_PERSONS
    ]
    participles = [
        get_participle_tag(participle, case, number)
        for participle in VERB_PARTICIPLES
        for case, number in noun_combinations(NOUN_CASES, NOUN_NUMBERS)
    ]
    return finite + participles


def form_ids(entry: VocabularyEntry) -> list[str]:
    pos = entry.get("pos", "N")
    return conjugation_form_ids() if pos == "V" else declension_form_ids(pos)


def _lemma(entry: VocabularyEntry) -> str:
    return entry.get("lemma") or entry["fin"]


def build_table(
    entry: VocabularyEntry, engine: InflectionEngine
) -> dict[str, list[str]]:
    """Generate a word's full table, leaving out forms the model can't produce."""
    table = {}
    for form_id in form_ids(entry):
        answers = list(
            dict.fromkeys(engine.generate_inflection(_lemma(entry), form_id))
        )
        if answers:
            table[form_id] = answers
    return table


def table_lookup(entry: VocabularyEntry, form_id: str) -> Sequence[str]:
    """Read answers from the entry's stored ``forms`` table."""
    return entry.get("forms", {}).get(form_id, ())


def engine_lookup(engine: InflectionEngine) -> FormLookup:
    """Generate answers on demand; the engine caches repeated requests."""

    def lookup(entry: VocabularyEntry, form_id: str) -> Sequence[str]:
        return engine.generate_inflection(_lemma(entry), form_id)

    return lookup
