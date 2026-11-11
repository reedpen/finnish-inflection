"""Daily review: when each word is due, how strong each skill is, and today's plan.

Two layers answer separate questions:

* **Scheduling** (one FSRS card per word): when should this word come back?
* **Mastery** (one cell per word class × form): which patterns are weak?

:func:`daily_plan` combines them. Everything here is pure: callers pass in the
attempt history, the time and a random generator, and store the returned
states however they like. Replaying the same attempts always gives the same
cards, mastery and plan, which is what makes retuning safe.
"""

from __future__ import annotations

import random
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fsrs import Card, Rating, Scheduler, State

from finnish_core.forms import (
    NOUN_CASES,
    NOUN_NUMBERS,
    VERB_PERSONS,
    VERB_TENSES_MOODS,
    VERB_TYPES,
    get_noun_tag,
    get_verb_tag,
    noun_combinations,
)
from finnish_core.vocab import VocabularyEntry, classify_verb_type

ENGINE_VERSION = "2"
"""Bump when a change here would give different cards, mastery or classes for
the same attempts. Callers that cache states rebuild them on a mismatch."""

WordId = Hashable

# --- Attempts --------------------------------------------------------------------


@dataclass(frozen=True)
class Attempt:
    """One answered or skipped question, as the learning engine sees it."""

    word: WordId
    word_class: str
    form_id: str
    outcome: Literal["correct", "skipped"]
    answered_at: datetime
    wrong_attempts: int = 0
    hints: int = 0
    duration_ms: int | None = None
    seq: int = 0
    """Breaks ties between attempts with the same ``answered_at``; callers
    pass a stable increasing id (the server uses its attempt row id)."""


def _order(attempt: Attempt) -> tuple[datetime, int]:
    return (_utc(attempt.answered_at), attempt.seq)


def rating(attempt: Attempt) -> Rating:
    """The FSRS grade for an attempt.

    Typed answers carry no "how easy was that" signal, so Easy is never given:
    a clean first try is Good, a correct answer that needed retries or hints is
    Hard, and a skip is Again.
    """
    if attempt.outcome != "correct":
        return Rating.Again
    if attempt.wrong_attempts or attempt.hints:
        return Rating.Hard
    return Rating.Good


def attempt_score(attempt: Attempt) -> float:
    """How well an attempt went, from 0 (skipped) to 1 (clean first try)."""
    if attempt.outcome != "correct":
        return 0.0
    penalty = 0.25 * attempt.wrong_attempts + 0.2 * attempt.hints
    return max(0.2, 1.0 - penalty)


# --- Scheduling ------------------------------------------------------------------

# A daily review has no use for minute-long learning steps, and fuzzing would
# draw from the global random module. Without either, replays are exact.
SCHEDULER = Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)


@dataclass(frozen=True)
class CardState:
    """When a word is next due, and FSRS's memory model of it."""

    due: datetime
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None
    reviews: int = 0
    lapses: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["due"] = self.due.isoformat()
        data["last_review"] = self.last_review.isoformat() if self.last_review else None
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CardState:
        last_review = data.get("last_review")
        return cls(
            due=datetime.fromisoformat(data["due"]),
            stability=data.get("stability"),
            difficulty=data.get("difficulty"),
            last_review=datetime.fromisoformat(last_review) if last_review else None,
            reviews=data.get("reviews", 0),
            lapses=data.get("lapses", 0),
        )

    def _fsrs(self) -> Card:
        return Card(
            card_id=0,
            state=State.Review if self.reviews else State.Learning,
            step=None if self.reviews else 0,
            stability=self.stability,
            difficulty=self.difficulty,
            due=self.due,
            last_review=self.last_review,
        )


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return moment.astimezone(timezone.utc)


def update_card(card: CardState | None, attempt: Attempt) -> CardState:
    """Schedule a word after an attempt. ``None`` is a word never seen before."""
    when = _utc(attempt.answered_at)
    current = card or CardState(due=when)
    grade = rating(attempt)
    updated, _ = SCHEDULER.review_card(current._fsrs(), grade, review_datetime=when)
    return CardState(
        due=updated.due,
        stability=updated.stability,
        difficulty=updated.difficulty,
        last_review=updated.last_review,
        reviews=current.reviews + 1,
        lapses=current.lapses + (grade == Rating.Again and current.reviews > 0),
    )


def retrievability(card: CardState, now: datetime) -> float:
    """FSRS's estimate of the chance of recalling the word right now."""
    return SCHEDULER.get_card_retrievability(card._fsrs(), _utc(now))


# --- Mastery ---------------------------------------------------------------------

HALF_LIFE_DAYS = 30.0
"""Evidence loses half its weight this many days after it was recorded."""
PRIOR_WEIGHT = 2.0
"""How many attempts' worth of the 0.5 prior a fresh cell starts with."""
MASTERED = 0.85
WEAK = 0.6
MIN_EVIDENCE = 3.0
"""Recency-weighted attempts a cell needs before it can count as mastered."""

Level = Literal["unseen", "weak", "learning", "mastered"]


def skill_form(form_id: str) -> str:
    """The form as a skill: adjectives decline like nouns, so ``+A`` reads ``+N``."""
    return "+N" + form_id[2:] if form_id.startswith("+A+") else form_id


def skill_id(word_class: str, form_id: str) -> str:
    return f"{word_class}|{skill_form(form_id)}"


@dataclass(frozen=True)
class Mastery:
    """A recency-weighted success rate for one skill cell."""

    score: float = 0.0
    weight: float = 0.0
    attempts: int = 0
    last_seen: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_seen"] = self.last_seen.isoformat() if self.last_seen else None
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Mastery:
        last_seen = data.get("last_seen")
        return cls(
            score=data.get("score", 0.0),
            weight=data.get("weight", 0.0),
            attempts=data.get("attempts", 0),
            last_seen=datetime.fromisoformat(last_seen) if last_seen else None,
        )


def _decayed(mastery: Mastery, now: datetime) -> float:
    if mastery.last_seen is None:
        return mastery.weight
    days = max(0.0, (_utc(now) - _utc(mastery.last_seen)).total_seconds() / 86400)
    return mastery.weight * 0.5 ** (days / HALF_LIFE_DAYS)


def update_mastery(mastery: Mastery | None, attempt: Attempt) -> Mastery:
    """Fold one attempt into its skill cell's running average."""
    mastery = mastery or Mastery()
    weight = _decayed(mastery, attempt.answered_at)
    total = weight + 1.0
    return Mastery(
        score=(mastery.score * weight + attempt_score(attempt)) / total,
        weight=total,
        attempts=mastery.attempts + 1,
        last_seen=_utc(attempt.answered_at),
    )


def strength(mastery: Mastery | None, now: datetime) -> float:
    """The cell's success rate, pulled toward 0.5 when evidence is thin or old."""
    if mastery is None:
        return 0.5
    weight = _decayed(mastery, now)
    return (mastery.score * weight + 0.5 * PRIOR_WEIGHT) / (weight + PRIOR_WEIGHT)


def level(mastery: Mastery | None, now: datetime) -> Level:
    if mastery is None or mastery.attempts == 0:
        return "unseen"
    value = strength(mastery, now)
    if value < WEAK:
        return "weak"
    if value >= MASTERED and _decayed(mastery, now) >= MIN_EVIDENCE:
        return "mastered"
    return "learning"


@dataclass
class LearnerState:
    """Every card and mastery cell, built by replaying attempts in order."""

    cards: dict[WordId, CardState] = field(default_factory=dict)
    mastery: dict[str, Mastery] = field(default_factory=dict)

    def record(self, attempt: Attempt) -> None:
        self.cards[attempt.word] = update_card(self.cards.get(attempt.word), attempt)
        skill = skill_id(attempt.word_class, attempt.form_id)
        self.mastery[skill] = update_mastery(self.mastery.get(skill), attempt)


def replay(attempts: Iterable[Attempt]) -> LearnerState:
    """Rebuild a learner's state from their whole history, oldest first.

    Attempts with the same time are applied in ``seq`` order, so the result
    never depends on the order they are passed in.
    """
    state = LearnerState()
    for attempt in sorted(attempts, key=_order):
        state.record(attempt)
    return state


# --- Word classes ----------------------------------------------------------------

_VOWELS = "aeiouyäö"
_NOMINAL_ENDINGS = {
    "nen": "-nen (nainen)",
    "ton": "-ton/-tön (rahaton)",
    "us": "-s → -ksen (vastaus)",
    "us:d": "-us/-ys → -uden (rakkaus)",
    "as": "-as/-äs/-es (rikas)",
    "is": "-is (kallis)",
    "in": "-in (puhelin)",
    "C": "other consonant (sydän)",
    "VV": "one syllable, long vowel or -i (maa, voi)",
    "ie": "one syllable, -ie/-uo/-yö (tie, työ)",
    "VV:2": "long vowel, two or more syllables (vapaa)",
    "e": "-e (huone)",
    "i:e": "-i, e-stem (kivi)",
    "i:t": "-i, e-stem, partitive -ta/-tä (kieli, lapsi)",
    "si": "-si → -den (vesi, käsi)",
    "i": "-i (paperi)",
    "a": "-a/-ä (kala)",
    "o": "-o/-ö/-u/-y (talo)",
}
GRADATION = ":grad"
_LONG_VOWELS = tuple(vowel * 2 for vowel in _VOWELS)
_OPENING_DIPHTHONGS = ("ie", "uo", "yö")


def _ending(lemma: str, genitive: str | None, partitive: str | None = None) -> str:
    """The word's ending class, refined by its genitive and partitive if known.

    Without a table, words are classed by their ending alone; the genitive and
    partitive then split endings that hide different patterns.
    """
    word = lemma.casefold()
    genitive = (genitive or "").casefold()
    partitive = (partitive or "").casefold()
    if word.endswith("nen"):
        return "nen"
    if word.endswith(("ton", "tön")):
        return "ton"
    if word.endswith("s") and genitive.endswith("ksen"):
        # vastaus → vastauksen, and likewise jänis → jäniksen.
        return "us"
    if word.endswith(("us", "ys", "os", "ös")):
        # rakkaus → rakkauden, ystävyys → ystävyyden.
        return "us:d" if genitive.endswith("den") else "us"
    if word.endswith(("as", "äs", "es")):
        return "as"
    if word.endswith("is"):
        return "is"
    if word.endswith("in"):
        return "in"
    if not word or word[-1] not in _VOWELS:
        return "C"
    if len(word) > 1 and word[-2] in _VOWELS:
        # Only the final pair is a vowel: a one-syllable word.
        one_syllable = not any(char in _VOWELS for char in word[:-2])
        if word.endswith(_LONG_VOWELS):
            return "VV" if one_syllable else "VV:2"
        if one_syllable:
            # tie → teitä, suo → soita; maa, voi and täi keep their vowels.
            return "ie" if word.endswith(_OPENING_DIPHTHONGS) else "VV"
        # korkea, radio, lattia: decline by their last vowel.
    if word.endswith("e"):
        return "e"
    if word.endswith("i"):
        stem = genitive.removesuffix("n")
        if not stem.endswith("e"):
            return "i"
        if word.endswith("si") and not stem[:-1].endswith("s"):
            # vesi → veden, käsi → käden, kynsi → kynnen.
            return "si"
        if len(partitive) > 1 and partitive[-2] not in _VOWELS:
            # kieli → kieltä, lapsi → lasta, uni → unta (not kivi → kiveä).
            return "i:t"
        return "i:e"
    if word.endswith(("a", "ä")):
        return "a"
    return "o"


def _skeleton(text: str) -> str:
    """The text up to its last consonant: kadu → kad."""
    return text.rstrip(_VOWELS)


def _drop_consonants(text: str) -> str:
    """The text without its final consonants: tytär → tytä."""
    end = len(text)
    while end and text[end - 1] not in _VOWELS:
        end -= 1
    return text[:end]


def _has_gradation(lemma: str, ending: str, genitive: str | None) -> bool:
    """Whether the genitive's stem consonants differ from the base form's.

    Catches both directions: katu → kadun and rikas → rikkaan. Each type's own
    stem change is set aside first, so vesi → veden, mies → miehen,
    puhelin → puhelimen or vastaus → vastauksen are not taken for gradation.
    """
    if not genitive:
        return False
    word = lemma.casefold()
    stem = genitive.casefold().removesuffix("n")
    if ending in {"a", "o", "e", "i", "i:e", "i:t"}:
        return _skeleton(word) != _skeleton(stem)
    if ending in {"as", "is", "in", "C"}:
        # Where the base form ends in a consonant, the stem may have only vowels
        # (kirves → kirvee-, rikas → rikkaa-) or a consonant of its own
        # (sydän → sydäme-, mies → miehe-, tytär → tyttäre-): compare the base
        # form's last consonants with the stem's either way.
        short = _skeleton(stem)
        readings = {short, _skeleton(_drop_consonants(short))}
        return _skeleton(_drop_consonants(word)) not in readings
    return False


def _first_form(entry: VocabularyEntry, case: str) -> str | None:
    tag = get_noun_tag(case, "Singular", entry.get("pos", "N"))
    answers = entry.get("forms", {}).get(tag)
    return answers[0] if answers else None


def word_class(entry: VocabularyEntry) -> str:
    """A stable id for the inflection pattern a word follows.

    Verbs use their type (``verb:4``). Nouns and adjectives decline alike, so
    they share classes by ending (``nominal:a``), split where the stored table's
    genitive or partitive shows a different pattern (``nominal:si`` for vesi →
    veden), with ``:grad`` added when the table shows consonant gradation
    (``nominal:a:grad``). Kotus declension types can replace the endings later;
    bump ``ENGINE_VERSION``.
    """
    lemma = entry.get("lemma") or entry["fin"]
    if entry.get("pos") == "V":
        return f"verb:{entry.get('verb_type') or classify_verb_type(lemma)}"
    genitive = _first_form(entry, "Genitive (-n)")
    partitive = _first_form(entry, "Partitive (-a/-ta)")
    ending = _ending(lemma, genitive, partitive)
    grade = GRADATION if _has_gradation(lemma, ending, genitive) else ""
    return f"nominal:{ending}{grade}"


def word_class_label(class_id: str) -> str:
    kind, _, rest = class_id.partition(":")
    if kind == "verb":
        for label, number in VERB_TYPES.items():
            if rest == str(number):
                return label
        return f"Type {rest}"
    ending, grade, _ = rest.partition(GRADATION)
    label = _NOMINAL_ENDINGS.get(ending, ending)
    return f"{label}, gradation" if grade else label


def word_class_order(class_id: str) -> tuple[int, int, int]:
    """Sort key: verbs by type, nominals in the endings' teaching order."""
    kind, _, rest = class_id.partition(":")
    if kind == "verb":
        return (1, int(rest) if rest.isdigit() else 99, 0)
    ending, grade, _ = rest.partition(GRADATION)
    endings = list(_NOMINAL_ENDINGS)
    return (0, endings.index(ending) if ending in endings else 99, bool(grade))


# --- Forms a daily review asks ---------------------------------------------------


def review_form_ids(pos: str) -> list[str]:
    """Forms the daily review draws from, in teaching order.

    Every case and number for nouns and adjectives, and every finite form for
    verbs. Participles stay in free practice: declined in every case they would
    add 156 cells per verb type, each too rarely seen to measure.
    """
    if pos == "V":
        return [
            get_verb_tag(tense, person)
            for tense in VERB_TENSES_MOODS
            for person in VERB_PERSONS
        ]
    return [
        get_noun_tag(case, number, pos)
        for case, number in noun_combinations(NOUN_CASES, NOUN_NUMBERS)
    ]


# --- The daily plan --------------------------------------------------------------

Reason = Literal["due", "weak", "new"]


@dataclass(frozen=True)
class ReviewWord:
    """A word the learner could be asked today.

    ``form_ids`` are the forms it can be asked in (its table, limited to what
    the learner wants reviewed). ``card`` is ``None`` for a word not yet seen.
    """

    id: WordId
    word_class: str
    form_ids: Sequence[str]
    card: CardState | None = None


@dataclass(frozen=True)
class PlanItem:
    word: WordId
    form_id: str
    reason: Reason

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanSettings:
    size: int = 20
    new_limit: int = 5
    due_share: float = 0.7
    weak_share: float = 0.2


MASTERED_WEIGHT = 0.05
"""Relative chance of asking a mastered cell when a due word comes up."""


def _due_weight(cell: Mastery | None, now: datetime) -> float:
    if level(cell, now) == "mastered":
        return MASTERED_WEIGHT
    return max(MASTERED_WEIGHT, 1.0 - strength(cell, now))


def _pick(rng: random.Random, options: Sequence[str], weights: Sequence[float]) -> str:
    return rng.choices(options, weights=weights, k=1)[0]


def daily_plan(
    words: Sequence[ReviewWord],
    mastery: Mapping[str, Mastery],
    now: datetime,
    rng: random.Random,
    *,
    due_by: datetime | None = None,
    settings: PlanSettings = PlanSettings(),
) -> list[PlanItem]:
    """Choose today's questions: one word and form each.

    * **Due**: words whose card is due by ``due_by`` (default ``now``), least
      likely to be remembered first. Each is asked in a form its class is weak
      at; mastered forms come up only rarely.
    * **Weak**: the weakest skill cells, each asked with a word already being
      learned that has that form.
    * **New**: unseen words in the order given, introduced in the forms their
      class is strongest at, so a new word and a hard form don't arrive
      together.

    When one group runs short, the others fill its place, so the plan reaches
    ``settings.size`` whenever there is enough material. Words appear once.
    """
    due_by = _utc(due_by or now)
    playable = [word for word in words if word.form_ids]
    due = sorted(
        (word for word in playable if word.card and _utc(word.card.due) <= due_by),
        key=lambda word: (retrievability(word.card, now), str(word.id)),
    )
    fresh = [word for word in playable if word.card is None][: settings.new_limit]
    learned = [word for word in playable if word.card is not None]

    size = max(0, settings.size)
    want_due = round(size * settings.due_share)
    want_weak = round(size * settings.weak_share)
    want_new = min(len(fresh), size - want_due - want_weak)

    weak_cells = sorted(
        (
            (strength(cell, now), skill)
            for skill, cell in mastery.items()
            if level(cell, now) == "weak"
        ),
    )

    plan: list[PlanItem] = []
    used: set[WordId] = set()

    def add_due(limit: int) -> None:
        for word in due:
            if len(plan) >= size or limit <= 0:
                return
            if word.id in used:
                continue
            weights = [
                _due_weight(mastery.get(skill_id(word.word_class, form)), now)
                for form in word.form_ids
            ]
            plan.append(PlanItem(word.id, _pick(rng, word.form_ids, weights), "due"))
            used.add(word.id)
            limit -= 1

    by_class: dict[str, list[ReviewWord]] = {}
    for word in learned:
        by_class.setdefault(word.word_class, []).append(word)

    def add_weak(limit: int) -> int:
        """One pass over the weak cells, weakest first, one word for each.

        Returns how many items it added.
        """
        added = 0
        for _, skill in weak_cells:
            if len(plan) >= size or added >= limit:
                break
            class_id, _, form_id = skill.partition("|")
            candidates = [
                (word, form)
                for word in by_class.get(class_id, ())
                if word.id not in used
                for form in word.form_ids
                if skill_form(form) == form_id
            ]
            if not candidates:
                continue
            word, form = rng.choice(candidates)
            plan.append(PlanItem(word.id, form, "weak"))
            used.add(word.id)
            added += 1
        return added

    def add_new(limit: int) -> None:
        for word in fresh:
            if len(plan) >= size or limit <= 0:
                return
            if word.id in used:
                continue
            weights = [
                max(
                    MASTERED_WEIGHT,
                    strength(mastery.get(skill_id(word.word_class, form)), now),
                )
                ** 2
                for form in word.form_ids
            ]
            plan.append(PlanItem(word.id, _pick(rng, word.form_ids, weights), "new"))
            used.add(word.id)
            limit -= 1

    add_due(want_due)
    add_weak(want_weak)
    add_new(want_new)
    # Fill any shortfall: more due words, then more weak spots (pass after pass,
    # so several words can practise one cell), then new words.
    add_due(size)
    while len(plan) < size and add_weak(size):
        pass
    add_new(size)

    rng.shuffle(plan)
    return plan


def end_of_day(now: datetime, tz) -> datetime:
    """The start of tomorrow in the learner's time zone, as an aware datetime."""
    local = _utc(now).astimezone(tz)
    tomorrow = (local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow


__all__ = [
    "ENGINE_VERSION",
    "Attempt",
    "CardState",
    "LearnerState",
    "Mastery",
    "PlanItem",
    "PlanSettings",
    "ReviewWord",
    "attempt_score",
    "daily_plan",
    "end_of_day",
    "level",
    "rating",
    "replay",
    "retrievability",
    "review_form_ids",
    "skill_form",
    "skill_id",
    "strength",
    "update_card",
    "update_mastery",
    "word_class",
    "word_class_label",
    "word_class_order",
]
