"""Build finite pools of questions from words and their inflection tables.

Builders read forms through a :data:`~finnish_core.paradigm.FormLookup`, so the
same pools come from stored tables (``table_lookup``) or from the model on
demand (``engine_lookup``).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import random

from finnish_core.forms import (
    get_noun_tag,
    get_participle_tag,
    get_verb_tag,
    noun_combinations,
)
from finnish_core.paradigm import FormLookup
from finnish_core.vocab import VocabularyEntry


@dataclass(frozen=True)
class Question:
    """A playable prompt and its accepted answers."""

    id: str
    kind: str
    word: str
    translation: str
    target: str
    answers: tuple[str, ...]


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
        answers = _answers(forms(word, get_noun_tag(case, number, pos)))
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
        answers = _answers(forms(word, get_verb_tag(tense, person)))
        if not answers:
            return None
        return Question(
            id=f"verb:{lemma}:{tense}:{person}",
            kind="Verb",
            word=word["fin"],
            translation=word.get("eng", ""),
            target=f"{tense}, {person}",
            answers=answers,
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
        answers = _answers(forms(word, get_participle_tag(participle, case, number)))
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
        )

    return _build_from_candidates(total, scan_limit, max_questions, rng, make_question)
