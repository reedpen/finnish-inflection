"""Build finite pools of questions from words and their inflection tables.

Builders read forms through a :data:`~finnish_core.paradigm.FormLookup`, so the
same pools come from stored tables (``table_lookup``) or from the model on
demand (``engine_lookup``).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import random

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
from finnish_core.paradigm import FormLookup
from finnish_core.settings import DrillSettings
from finnish_core.vocab import VocabularyEntry


@dataclass(frozen=True)
class Question:
    """A playable prompt and its accepted answers.

    ``lemma`` and ``pos`` identify the word (the same key vocabulary documents
    use) and ``form_id`` the form, so attempts can be recorded against stable
    ids rather than display text.
    """

    id: str
    kind: str
    word: str
    translation: str
    target: str
    answers: tuple[str, ...]
    lemma: str = ""
    pos: str = ""
    form_id: str = ""


def _answers(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _candidate_indices(total: int, maximum: int, rng) -> Iterable[int]:
    if total <= maximum:
        return range(total)
    return (rng or random.Random()).sample(range(total), maximum)


def _build_from_candidates(
    total: int,
    scan_limit: int,
    max_questions: int,
    rng,
    make_question: Callable[[int], Question | None],
) -> list[Question]:
    """Scan a bounded sample, falling back only to avoid a false empty pool."""
    primary = tuple(_candidate_indices(total, scan_limit, rng))
    pool = []
    seen_ids = set()

    def scan(indices, *, stop_after_first: bool = False) -> bool:
        for index in indices:
            question = make_question(index)
            if question is None or question.id in seen_ids:
                continue
            seen_ids.add(question.id)
            pool.append(question)
            if len(pool) >= max_questions or stop_after_first:
                return True
        return False

    if scan(primary):
        return pool
    if not pool and len(primary) < total:
        sampled = set(primary)
        scan(
            (index for index in range(total) if index not in sampled),
            stop_after_first=True,
        )
    return pool


def build_noun_pool(
    vocabulary: Iterable[VocabularyEntry],
    cases: Iterable[str],
    numbers: Iterable[str],
    forms: FormLookup,
    *,
    max_questions: int = 100,
    max_candidates: int | None = None,
    rng=None,
) -> list[Question]:
    combinations = list(noun_combinations(cases, numbers))
    words = list(vocabulary)
    total = len(words) * len(combinations)
    scan_limit = max_candidates or max(100, max_questions * 10)

    def make_question(index):
        word = words[index // len(combinations)]
        case, number = combinations[index % len(combinations)]
        lemma = word.get("lemma", word["fin"])
        pos = word.get("pos", "N")
        form_id = get_noun_tag(case, number, pos)
        answers = _answers(forms(word, form_id))
        if not answers:
            return None
        question_id = f"noun:{lemma}:{pos}:{case}:{number}"
        display_number = "" if case.startswith("Comitative") else f" {number}"
        return Question(
            id=question_id,
            kind="Word",
            word=word["fin"],
            translation=word.get("eng", ""),
            target=f"{case}{display_number}",
            answers=answers,
            lemma=lemma,
            pos=pos,
            form_id=form_id,
        )

    return _build_from_candidates(total, scan_limit, max_questions, rng, make_question)


def build_verb_pool(
    vocabulary: Iterable[VocabularyEntry],
    tenses: Iterable[str],
    persons: Iterable[str],
    forms: FormLookup,
    *,
    max_questions: int = 100,
    max_candidates: int | None = None,
    rng=None,
) -> list[Question]:
    words = list(vocabulary)
    combinations = [(tense, person) for tense in tenses for person in persons]
    total = len(words) * len(combinations)
    scan_limit = max_candidates or max(100, max_questions * 10)

    def make_question(index):
        word = words[index // len(combinations)]
        tense, person = combinations[index % len(combinations)]
        lemma = word.get("lemma", word["fin"])
        form_id = get_verb_tag(tense, person)
        answers = _answers(forms(word, form_id))
        if not answers:
            return None
        return Question(
            id=f"verb:{lemma}:{tense}:{person}",
            kind="Verb",
            word=word["fin"],
            translation=word.get("eng", ""),
            target=f"{tense}, {person}",
            answers=answers,
            lemma=lemma,
            pos="V",
            form_id=form_id,
        )

    return _build_from_candidates(total, scan_limit, max_questions, rng, make_question)


def build_participle_pool(
    vocabulary: Iterable[VocabularyEntry],
    participles: Iterable[str],
    cases: Iterable[str],
    numbers: Iterable[str],
    forms: FormLookup,
    *,
    max_questions: int = 100,
    max_candidates: int | None = None,
    rng=None,
) -> list[Question]:
    declensions = list(noun_combinations(cases, numbers))
    combinations = [
        (participle, case, number)
        for participle in participles
        for case, number in declensions
    ]
    words = list(vocabulary)
    total = len(words) * len(combinations)
    scan_limit = max_candidates or max(100, max_questions * 10)

    def make_question(index):
        word = words[index // len(combinations)]
        participle, case, number = combinations[index % len(combinations)]
        lemma = word.get("lemma", word["fin"])
        form_id = get_participle_tag(participle, case, number)
        answers = _answers(forms(word, form_id))
        if not answers:
            return None
        question_id = f"participle:{lemma}:{participle}:{case}:{number}"
        display_number = "" if case.startswith("Comitative") else f" {number}"
        return Question(
            id=question_id,
            kind="Verb",
            word=word["fin"],
            translation=word.get("eng", ""),
            target=f"{participle}, {case}{display_number}",
            answers=answers,
            lemma=lemma,
            pos="V",
            form_id=form_id,
        )

    return _build_from_candidates(total, scan_limit, max_questions, rng, make_question)


def _labels(mapping: dict, stable_ids: Iterable[str]) -> list[str]:
    """Display labels for stable ids, in the mapping's (teaching) order."""
    wanted = set(stable_ids)
    return [label for label, stable_id in mapping.items() if str(stable_id) in wanted]


def build_pool(
    settings: DrillSettings,
    vocabulary: Iterable[VocabularyEntry],
    forms: FormLookup,
    *,
    max_questions: int | None = None,
    rng=None,
) -> list[Question]:
    """Build the question pool for validated drill settings.

    Picks the words each drill uses (nouns and adjectives, or verbs of the
    selected types) and translates the settings' stable ids into the builders'
    arguments. ``max_questions`` defaults to enough for the session length.
    """
    selected = settings.selections
    size = max_questions or max(20, settings.session_length or 100)
    words = list(vocabulary)
    if settings.drill == "noun":
        return build_noun_pool(
            [word for word in words if word.get("pos", "N") in {"N", "A"}],
            _labels(NOUN_CASES, selected["cases"]),
            _labels(NOUN_NUMBERS, selected["numbers"]),
            forms,
            max_questions=size,
            rng=rng,
        )
    verbs = [word for word in words if word.get("pos") == "V"]
    if settings.drill == "verb":
        types = {int(value) for value in selected["types"]}
        return build_verb_pool(
            [verb for verb in verbs if verb.get("verb_type") in types],
            _labels(VERB_TENSES_MOODS, selected["tenses"]),
            _labels(VERB_PERSONS, selected["persons"]),
            forms,
            max_questions=size,
            rng=rng,
        )
    if settings.drill == "participle":
        return build_participle_pool(
            verbs,
            _labels(VERB_PARTICIPLES, selected["participles"]),
            _labels(NOUN_CASES, selected["cases"]),
            _labels(NOUN_NUMBERS, selected["numbers"]),
            forms,
            max_questions=size,
            rng=rng,
        )
    raise ValueError(f"unknown drill {settings.drill!r}")


def _form_targets(pos: str) -> dict[str, tuple[str, str, str]]:
    """Map each form id of a part of speech to (kind, target, question-id tail)."""
    if pos == "V":
        targets = {
            get_verb_tag(tense, person): (
                "Verb",
                f"{tense}, {person}",
                f"{tense}:{person}",
            )
            for tense in VERB_TENSES_MOODS
            for person in VERB_PERSONS
        }
        for participle in VERB_PARTICIPLES:
            for case, number in noun_combinations(NOUN_CASES, NOUN_NUMBERS):
                shown = "" if case.startswith("Comitative") else f" {number}"
                targets[get_participle_tag(participle, case, number)] = (
                    "Verb",
                    f"{participle}, {case}{shown}",
                    f"{participle}:{case}:{number}",
                )
        return targets
    targets = {}
    for case, number in noun_combinations(NOUN_CASES, NOUN_NUMBERS):
        shown = "" if case.startswith("Comitative") else f" {number}"
        targets[get_noun_tag(case, number, pos)] = (
            "Word",
            f"{case}{shown}",
            f"{case}:{number}",
        )
    return targets


def question_for(
    entry: VocabularyEntry, form_id: str, forms: FormLookup
) -> Question | None:
    """One question asking ``entry`` in ``form_id``, as the pool builders make it.

    Returns ``None`` when the form id doesn't belong to the word's part of
    speech or the word has no answers for it.
    """
    pos = entry.get("pos", "N")
    target = _form_targets(pos).get(form_id)
    answers = _answers(forms(entry, form_id))
    if target is None or not answers:
        return None
    kind, label, tail = target
    lemma = entry.get("lemma", entry["fin"])
    if pos == "V":
        prefix = "participle" if "Prc" in form_id else "verb"
        question_id = f"{prefix}:{lemma}:{tail}"
    else:
        question_id = f"noun:{lemma}:{pos}:{tail}"
    return Question(
        id=question_id,
        kind=kind,
        word=entry["fin"],
        translation=entry.get("eng", ""),
        target=label,
        answers=answers,
        lemma=lemma,
        pos=pos,
        form_id=form_id,
    )
