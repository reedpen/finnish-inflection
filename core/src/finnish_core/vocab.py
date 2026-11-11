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


def categorize_word(
    word: str,
    english_hint: str = "",
    morphology: "MorphologyAdapter | None" = None,
) -> tuple[str, str]:
    """Categorize a word with complete UralicNLP analyzer strings."""
    if morphology is None:
        from finnish_core.morphology import UralicNlpAdapter

        morphology = UralicNlpAdapter()

    try:
        analyses = morphology.analyze(word, "fin") or []
        lemmas = morphology.lemmatize(word, "fin") or []
    except Exception:
        return "?", word
    primary_lemma = lemmas[0] if lemmas else word
    candidates: dict[str, str] = {}
    for analysis in analyses:
        analysis_string = (
            analysis[0] if isinstance(analysis, (tuple, list)) else str(analysis)
        )
        tags = analysis_string.split("+")[1:]
        lemma = analysis_string.split("+", 1)[0].replace("#", "") or primary_lemma
        if "V" in tags and not {"PrfPrc", "PrsPrc", "NegPrc", "AgPrc"}.intersection(
            tags
        ):
            candidates.setdefault("V", lemma)
        if "A" in tags:
            candidates.setdefault("A", primary_lemma)
        if "N" in tags:
            candidates.setdefault("N", primary_lemma)
    hint = english_hint.casefold()
    preferred = (
        "V"
        if hint.startswith("to ") or "verb" in hint
        else "N"
        if "noun" in hint
        else "A"
        if "adjective" in hint
        else None
    )
    if preferred in candidates:
        return preferred, candidates[preferred]
    if len(candidates) == 1:
        pos = next(iter(candidates))
        return pos, candidates[pos]
    return "?", word


def packaged_default_document() -> VocabularyDocument:
    resource = files("finnish_core.starter").joinpath("default_vocab.json")
    try:
        with resource.open(encoding="utf-8") as handle:
            return validate_vocabulary_document(json.load(handle))
    except (OSError, json.JSONDecodeError, VocabularyError) as exc:
        raise VocabularyError(
            f"packaged default vocabulary is unavailable or invalid: {exc}"
        ) from exc
