"""Validated vocabulary documents: the word-list format every front end shares.

The JSON format in this module is the single interchange format used by the
offline builder, packaged vocabulary, and user imports.  Keeping validation at
this boundary means drill code never has to defend itself from partial records.

An entry may carry ``forms``, its full inflection table (form id → accepted
answers, see :mod:`finnish_core.paradigm`). Front ends that store tables use
them; others generate forms on demand.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import dataclasses
from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING, Any, Iterable, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    from finnish_core.morphology import MorphologyAdapter

SCHEMA_VERSION = 1
SUPPORTED_POS = {"N", "A", "V"}
_SET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def is_valid_set_name(name: str) -> bool:
    return bool(_SET_NAME.fullmatch(name))


def suggest_set_name(text: str) -> str:
    """Derive a valid set name from a file name or title (``päivä/1`` → ``paiva-1``)."""
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_text).strip("-_")
    return slug[:64].rstrip("-_") or "set"


class VocabularyError(ValueError):
    """A vocabulary file is invalid or a requested set operation is unsafe."""


class VocabularyEntry(TypedDict):
    """One validated word available to question builders."""

    fin: str
    lemma: str
    eng: str
    pos: str
    verb_type: NotRequired[int]
    forms: NotRequired[dict[str, list[str]]]


class VocabularyMetadata(TypedDict):
    name: str
    source_sha256: str
    source: NotRequired[str]
    remote_sha: NotRequired[str]


class VocabularyDocument(TypedDict):
    schema_version: int
    metadata: VocabularyMetadata
    entries: list[VocabularyEntry]


def classify_verb_type(lemma: str) -> int:
    """Classify a canonical Finnish verb lemma into verb types 1–6."""
    if lemma.endswith(("eta", "etä")):
        return 6
    if lemma.endswith(("ita", "itä")):
        return 5
    if lemma.endswith(("lla", "llä", "nna", "nnä", "rra", "rrä", "sta", "stä")):
        return 3
    if lemma.endswith(("da", "dä")):
        return 2
    if (
        len(lemma) >= 3
        and lemma[-2] == "t"
        and lemma[-1] in "aä"
        and lemma[-3] in "aeiouyäö"
    ):
        return 4
    if lemma.endswith(("a", "ä")):
        return 1
    return 0


def _validate_entry(raw: Any, index: int) -> VocabularyEntry:
    if not isinstance(raw, dict):
        raise VocabularyError(f"entry {index} must be an object")
    required = {"fin", "lemma", "eng", "pos"}
    missing = sorted(required - raw.keys())
    if missing:
        raise VocabularyError(f"entry {index} is missing: {', '.join(missing)}")
    item = dict(raw)
    for field in required:
        if not isinstance(item[field], str):
            raise VocabularyError(f"entry {index} field {field} must be text")
    if not item["fin"].strip() or not item["lemma"].strip() or not item["eng"].strip():
        raise VocabularyError(f"entry {index} has an empty required value")
    if item["pos"] not in SUPPORTED_POS:
        raise VocabularyError(
            f"entry {index} has unsupported part of speech {item['pos']!r}"
        )
    if item["pos"] == "V":
        if item.get("verb_type") not in range(1, 7):
            raise VocabularyError(f"entry {index} has invalid verb_type")
    else:
        item.pop("verb_type", None)
    if "forms" in item and not _is_form_table(item["forms"]):
        raise VocabularyError(
            f"entry {index} forms must map form ids to lists of non-empty text"
        )
    return cast(VocabularyEntry, item)


def _is_form_table(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(form_id, str)
        and isinstance(answers, list)
        and all(isinstance(answer, str) and answer for answer in answers)
        for form_id, answers in value.items()
    )


def validate_vocabulary_document(document: Any) -> VocabularyDocument:
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise VocabularyError(
            f"unsupported or missing schema version (expected {SCHEMA_VERSION})"
        )
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        raise VocabularyError("metadata must be an object")
    fingerprint = metadata.get("source_sha256")
    if not isinstance(fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", fingerprint
    ):
        raise VocabularyError("metadata source_sha256 must be a SHA-256 fingerprint")
    if not isinstance(metadata.get("name"), str) or not metadata["name"].strip():
        raise VocabularyError("metadata name is required")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise VocabularyError("entries must be a list")
    validated = [_validate_entry(item, index) for index, item in enumerate(entries, 1)]
    keys: set[tuple[str, str]] = set()
    for index, item in enumerate(validated, 1):
        key = (item["lemma"].casefold(), item["pos"])
        if key in keys:
            raise VocabularyError(
                f"entry {index} duplicates lemma {item['lemma']!r} and part of speech"
            )
        keys.add(key)
    return cast(
        VocabularyDocument,
        {
            "schema_version": SCHEMA_VERSION,
            "metadata": dict(metadata),
            "entries": validated,
        },
    )


def make_vocabulary_document(
    entries: Iterable[VocabularyEntry],
    *,
    source_bytes: bytes,
    name: str,
    extra_metadata: dict[str, str] | None = None,
) -> VocabularyDocument:
    document = {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            **(extra_metadata or {}),
            "name": name,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
        "entries": list(entries),
    }
    return validate_vocabulary_document(document)


_PARTICIPLE_TAGS = {"PrfPrc", "PrsPrc", "NegPrc", "AgPrc"}
_POS_ORDER = "VAN"


@dataclass(frozen=True)
class Reading:
    """One way the model can read a word: part of speech, lemma, and whether
    the word is that lemma's base form (nominative singular, or the verb's
    dictionary infinitive). ``compound`` marks a lemma rebuilt from a compound's
    parts, which can be malformed for inflected input."""

    pos: str
    lemma: str
    base_form: bool
    compound: bool = False


def _parse_analysis(word: str, analysis: str) -> Reading | None:
    # Compounds arrive as "kirja+N+Sg+Nom+Cmp#kauppa+N+Sg+Nom": the lemma is the
    # parts joined, and the last part's tags describe the word.
    parts = analysis.split("#")
    lemma = "".join(part.split("+", 1)[0] for part in parts) or word
    tags = set(parts[-1].split("+")[1:])
    if "V" in tags and not _PARTICIPLE_TAGS & tags:
        pos = "V"
        base = {"Act", "InfA", "Sg", "Lat"} <= tags
    elif "A" in tags or "N" in tags:
        pos = "A" if "A" in tags else "N"
        base = (
            {"Sg", "Nom"} <= tags
            and not {"Comp", "Superl"} & tags
            and not any(tag.startswith("Px") for tag in tags)
        )
    else:
        return None
    return Reading(
        pos, lemma, base and lemma.casefold() == word.casefold(), len(parts) > 1
    )


def word_readings(word: str, morphology: "MorphologyAdapter") -> list[Reading]:
    """Every supported reading of ``word``, in the model's order."""
    readings = []
    for analysis in morphology.analyze(word, "fin") or []:
        text = analysis[0] if isinstance(analysis, (tuple, list)) else str(analysis)
        reading = _parse_analysis(word, text)
        if reading is not None and reading not in readings:
            readings.append(reading)
    return readings


# Readings that don't show the model knows a word: English "it", "ok" and "I"
# have them (as acronyms, abbreviations and a Roman numeral).
_WEAK_TAGS = {"ACR", "ABBR", "Rom"}


def is_known_word(word: str, morphology: "MorphologyAdapter") -> bool:
    """Whether the model's lexicon has ``word``, as any part of speech.

    The model doesn't guess: a word it doesn't know gets no analysis, or itself
    back with no tags. A word in capitals is also tried in lower case. Readings
    only as an acronym, abbreviation or Roman numeral don't count.
    """
    for candidate in dict.fromkeys((word, word.casefold())):
        try:
            analyses = morphology.analyze(candidate, "fin") or []
        except Exception:
            continue
        for analysis in analyses:
            text = analysis[0] if isinstance(analysis, (tuple, list)) else analysis
            tags = set(str(text).split("#")[-1].split("+")[1:])
            if tags and not tags & _WEAK_TAGS:
                return True
    return False


def _best_lemmas(word: str, readings: list[Reading]) -> dict[str, str]:
    """One lemma per part of speech: the word itself if possible, else the first
    whole-word reading, else the first reading.

    A capitalised word ("Talo", as flashcard exports often write it) prefers
    its lowercase common-word lemma over a proper-noun reading of the same
    spelling, which the model can't inflect as a drill word.

    Compound lemmas are rebuilt by joining the parts' lemmas, which drops a
    part's own inflection: "kirjanpitäjät" would give "kirjapitäjä", where the
    model's whole-word reading gives "kirjanpitäjä".
    """
    lowered = word[:1].lower() + word[1:]
    choices: dict[str, str] = {}
    for pos in sorted({r.pos for r in readings}, key=_POS_ORDER.index):
        ours = [r for r in readings if r.pos == pos]
        preferences = (
            lambda r: r.lemma == lowered,
            lambda r: r.lemma == word,
            lambda r: r.lemma.casefold() == word.casefold(),
            lambda r: not r.compound,
        )
        choices[pos] = next(
            (r.lemma for wanted in preferences for r in ours if wanted(r)),
            ours[0].lemma,
        )
    return choices


def analysis_candidates(word: str, morphology: "MorphologyAdapter") -> dict[str, str]:
    """Each part of speech the model can read ``word`` as, mapped to its lemma.

    When a part of speech has several readings, the one whose lemma is the word
    itself wins, since word lists give dictionary forms: "kuusi" is the noun
    kuusi (spruce), not kuu (moon) with a possessive suffix. Participles are
    not offered as verbs. An empty result means the model doesn't know the word.
    """
    return _best_lemmas(word, word_readings(word, morphology))


@dataclass(frozen=True)
class WordAnalysis:
    """The analyzer's decision for one word.

    ``pos`` is ``"?"`` when it couldn't decide. ``assumed`` marks a decision made
    only by assuming the word was given in its base form, which a reviewer may
    want to check. ``candidates`` lists every part of speech it could be.
    """

    pos: str
    lemma: str
    candidates: dict[str, str] = dataclasses.field(default_factory=dict)
    assumed: bool = False


def _gloss_preference(english_hint: str) -> str | None:
    hint = english_hint.casefold()
    if hint.startswith("to ") or "verb" in hint:
        return "V"
    if "noun" in hint:
        return "N"
    if "adjective" in hint:
        return "A"
    return None


def analyze_word(
    word: str, english_hint: str, morphology: "MorphologyAdapter"
) -> WordAnalysis:
    """Decide a word's part of speech and lemma.

    In order: the English gloss ("to ..." means a verb); a single possible part
    of speech; then, assuming word lists give base forms, the only part of
    speech the word is a base form of (with adjective winning a tie with noun,
    as in "hyvä"). Anything else is left undecided (``"?"``).
    """
    try:
        readings = word_readings(word, morphology)
    except Exception:
        return WordAnalysis("?", word)
    candidates = _best_lemmas(word, readings)
    preferred = _gloss_preference(english_hint)
    if preferred in candidates:
        return WordAnalysis(preferred, candidates[preferred], candidates)
    if len(candidates) == 1:
        [(pos, lemma)] = candidates.items()
        return WordAnalysis(pos, lemma, candidates)
    base = {r.pos: r.lemma for r in readings if r.base_form}
    if len(base) == 1 or set(base) == {"N", "A"}:
        pos = "A" if "A" in base else next(iter(base))
        return WordAnalysis(pos, base[pos], candidates, assumed=True)
    return WordAnalysis("?", word, candidates)


def categorize_word(
    word: str,
    english_hint: str = "",
    morphology: "MorphologyAdapter | None" = None,
) -> tuple[str, str]:
    """Pick one part of speech and lemma, or ``("?", word)`` if it's ambiguous.

    See :func:`analyze_word` for how ties are broken.
    """
    if morphology is None:
        from finnish_core.morphology import UralicNlpAdapter

        morphology = UralicNlpAdapter()
    analysis = analyze_word(word, english_hint, morphology)
    return analysis.pos, analysis.lemma


def packaged_default_document() -> VocabularyDocument:
    resource = files("finnish_core.starter").joinpath("default_vocab.json")
    try:
        with resource.open(encoding="utf-8") as handle:
            return validate_vocabulary_document(json.load(handle))
    except (OSError, json.JSONDecodeError, VocabularyError) as exc:
        raise VocabularyError(
            f"packaged default vocabulary is unavailable or invalid: {exc}"
        ) from exc
