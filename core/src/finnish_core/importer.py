"""Vocabulary import and review: parse a word list, analyze it, and preview it.

Everything here works on bytes and plain data. Reading files or standard input
is up to the caller.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from finnish_core.vocab import (
    VocabularyEntry,
    VocabularyDocument,
    VocabularyError,
    WordAnalysis,
    classify_verb_type,
    make_vocabulary_document,
)

if TYPE_CHECKING:
    from finnish_core.morphology import MorphologyAdapter

Analyzer = Callable[[str, str], "tuple[str, str] | WordAnalysis"]
"""Decide ``(pos, lemma)`` for a Finnish word and its gloss; ``"?"`` if unsure.

Returning a :class:`~finnish_core.vocab.WordAnalysis` can also flag the
decision as an assumption for review.
"""


@dataclass(frozen=True)
class ImportPreview:
    accepted: list[VocabularyEntry]
    corrected: list[VocabularyEntry]
    ambiguous: list[dict[str, str]]
    rejected: list[dict[str, str]]
    excluded: list[str]
    document: VocabularyDocument
    # Accepted words whose part of speech was assumed from the base form.
    assumed: list[VocabularyEntry] = field(default_factory=list)


Overrides = dict[str, dict[str, str] | None]
# Column names recognised in an optional header row (compared case-insensitively).
_FINNISH_HEADERS = {"front", "finnish", "suomi", "fin", "word", "term", "sana"}
_ENGLISH_HEADERS = {
    "back",
    "english",
    "englanti",
    "eng",
    "definition",
    "meaning",
    "translation",
}
# Detection order doubles as the tie-break: a tab beats a semicolon beats a comma,
# because English definitions often contain commas but rarely tabs.
_DELIMITERS = ("\t", ";", ",")
# Values for Anki's "#separator:" export directive.
_SEPARATOR_NAMES = {
    "tab": "\t",
    "semicolon": ";",
    "comma": ",",
    "pipe": "|",
    "space": " ",
}
_ROW_HINT = "expected Finnish and English separated by a tab, semicolon, or comma"


def _decode(data: bytes) -> str:
    try:
        # utf-8-sig drops the byte-order mark Excel puts on exported CSVs.
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VocabularyError("vocabulary must be valid UTF-8 text") from exc


def _detect_delimiter(lines: list[str]) -> str:
    counts = {d: sum(d in line for line in lines) for d in _DELIMITERS}
    best = max(_DELIMITERS, key=lambda d: counts[d])  # max keeps the first on ties
    if counts[best] == 0:
        raise VocabularyError(f"could not find columns: {_ROW_HINT}")
    return best


def _header_columns(cells: list[str]) -> tuple[int, int] | None:
    folded = [cell.strip().casefold() for cell in cells]
    fin = next((i for i, cell in enumerate(folded) if cell in _FINNISH_HEADERS), None)
    eng = next((i for i, cell in enumerate(folded) if cell in _ENGLISH_HEADERS), None)
    return (fin, eng) if fin is not None and eng is not None else None


def parse_rows(text: str) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    """Split a word list into ``(finnish, english)`` rows and per-line problems.

    Accepts tab-, semicolon-, or comma-separated text with an optional header
    row, which covers Quizlet and Anki exports, spreadsheets, and hand-typed
    lists. Lines starting with ``#`` are comments (or Anki export directives).
    """
    delimiter = None
    lines: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            key, _, value = stripped[1:].partition(":")
            if key.strip().casefold() == "separator":
                value = value.strip()
                delimiter = _SEPARATOR_NAMES.get(value.casefold(), value[:1] or None)
        elif stripped:
            lines.append((number, line))
    if not lines:
        raise VocabularyError("no vocabulary rows found")
    delimiter = delimiter or _detect_delimiter([line for _, line in lines])

    def cells(number: int, line: str) -> list[str]:
        try:
            return next(csv.reader([line], delimiter=delimiter))
        except csv.Error as error:  # e.g. a field over csv's size limit
            raise VocabularyError(
                f"line {number}: could not read it ({error})"
            ) from error

    columns = _header_columns(cells(*lines[0]))
    if columns is not None:
        lines = lines[1:]

    rows: list[tuple[str, str]] = []
    problems: list[dict[str, str]] = []
    for number, line in lines:
        parts = cells(number, line)
        if columns is not None:
            fin_col, eng_col = columns
            fin = parts[fin_col] if fin_col < len(parts) else ""
            eng = parts[eng_col] if eng_col < len(parts) else ""
        elif len(parts) < 2:
            fin, eng = (parts[0] if parts else ""), ""
        elif delimiter == "\t":
            # Tab exports (Anki, Quizlet) may carry extra columns such as tags.
            fin, eng = parts[0], parts[1]
        else:
            # "puhua, to speak, to talk" keeps everything after the first separator.
            fin, eng = parts[0], delimiter.join(parts[1:])
        fin, eng = fin.strip(), eng.strip()
        if not fin or not eng:
            problems.append(
                {
                    "fin": fin or f"(line {number})",
                    "reason": f"line {number}: {_ROW_HINT}",
                }
            )
            continue
        rows.append((fin, eng))
    return rows, problems


def import_vocabulary(
    source_bytes: bytes,
    *,
    analyzer: Analyzer,
    name: str,
    overrides: Overrides | None = None,
    forms_validator: Callable[[dict[str, Any]], bool] | None = None,
    metadata: dict[str, str] | None = None,
) -> ImportPreview:
    """Parse, analyze, and preview a word list without installing it."""
    rows, problems = parse_rows(_decode(source_bytes))
    accepted: list[VocabularyEntry] = []
    corrected: list[VocabularyEntry] = []
    ambiguous: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = list(problems)
    excluded: list[str] = []
    assumed: list[VocabularyEntry] = []
    seen: set[tuple[str, str]] = set()
    overrides = overrides or {}

    for fin, eng in rows:
        if not fin or not eng:
            rejected.append(
                {
                    "fin": fin or "(empty)",
                    "reason": "Finnish and English values are required",
                }
            )
            continue
        if fin in overrides:
            override = overrides[fin]
            if override is None:
                excluded.append(fin)
                continue
            if not isinstance(override, dict):
                raise VocabularyError(f"override for {fin!r} must be an object or null")
            pos, lemma = override.get("pos", "?"), override.get("lemma", fin)
            if not isinstance(pos, str) or not isinstance(lemma, str):
                raise VocabularyError(
                    f"override for {fin!r} must contain text lemma and pos values"
                )
            was_corrected, was_assumed = True, False
        else:
            result = analyzer(fin, eng)
            if isinstance(result, WordAnalysis):
                pos, lemma, was_assumed = result.pos, result.lemma, result.assumed
            else:
                pos, lemma = result
                was_assumed = False
            was_corrected = False
        if pos not in {"N", "A", "V"} or not lemma:
            problem = {
                "fin": fin,
                "reason": "unknown or ambiguous analysis; add an override or exclusion",
            }
            ambiguous.append(problem)
            continue
        item: VocabularyEntry = {
            "fin": fin,
            "lemma": lemma,
            "eng": eng,
            "pos": pos,
        }
        if pos == "V":
            item["verb_type"] = classify_verb_type(lemma)
            if item["verb_type"] not in range(1, 7):
                rejected.append(
                    {"fin": fin, "reason": "recognized verb has no valid verb type"}
                )
                continue
        key = (lemma.casefold(), pos)
        if key in seen:
            rejected.append(
                {"fin": fin, "reason": "duplicate lemma and part of speech"}
            )
            continue
        if forms_validator is not None and not forms_validator(item):
            rejected.append({"fin": fin, "reason": "no generated forms"})
            continue
        seen.add(key)
        accepted.append(item)
        if was_corrected:
            corrected.append(item)
        if was_assumed:
            assumed.append(item)

    document = make_vocabulary_document(
        accepted, source_bytes=source_bytes, name=name, extra_metadata=metadata
    )
    return ImportPreview(
        accepted, corrected, ambiguous, rejected, excluded, document, assumed
    )


def preview_summary(preview: ImportPreview) -> str:
    return (
        f"Accepted: {len(preview.accepted)}; corrected: {len(preview.corrected)}; "
        f"assumed base form: {len(preview.assumed)}; "
        f"ambiguous: {len(preview.ambiguous)}; rejected: {len(preview.rejected)}; "
        f"excluded: {len(preview.excluded)}"
    )


def preview_rows(preview: ImportPreview) -> list[dict[str, str]]:
    """Return display-neutral detailed rows for CLI and interactive renderers."""
    corrected = {id(item) for item in preview.corrected}
    assumed = {id(item) for item in preview.assumed}
    ambiguous = {(item["fin"], item["reason"]) for item in preview.ambiguous}
    rows = []
    for item in preview.accepted:
        status = (
            "corrected"
            if id(item) in corrected
            else "assumed"
            if id(item) in assumed
            else "accepted"
        )
        rows.append(
            {
                "status": status,
                "fin": item["fin"],
                "detail": f"{item['lemma']} ({item['pos']}) — {item['eng']}",
            }
        )
    rows.extend(
        {"status": "ambiguous", "fin": item["fin"], "detail": item["reason"]}
        for item in preview.ambiguous
    )
    rows.extend(
        {"status": "rejected", "fin": item["fin"], "detail": item["reason"]}
        for item in preview.rejected
        if (item["fin"], item["reason"]) not in ambiguous
    )
    rows.extend(
        {
            "status": "excluded",
            "fin": fin,
            "detail": "explicitly excluded by review",
        }
        for fin in preview.excluded
    )
    return rows


def validate_overrides(value: Any) -> Overrides:
    """Check the shape of a decoded overrides document."""
    if not isinstance(value, dict):
        raise VocabularyError("overrides must be a JSON object")
    return value


def analyze_vocabulary(
    source_bytes: bytes,
    morphology: MorphologyAdapter,
    *,
    name: str,
    overrides: Overrides | None = None,
    metadata: dict[str, str] | None = None,
) -> ImportPreview:
    """Analyze a word list with a real morphology model and preview it.

    The model must already be installed. Each accepted word is checked by
    generating one representative form.
    """
    from finnish_core.forms import get_noun_tag, get_verb_tag
    from finnish_core.morphology import InflectionEngine
    from finnish_core.vocab import analyze_word

    engine = InflectionEngine(morphology)

    def has_forms(entry):
        tag = (
            get_verb_tag("Present", "1st Person Sg (I)")
            if entry["pos"] == "V"
            else get_noun_tag("Nominative (---)", "Singular", entry["pos"])
        )
        return bool(engine.generate_inflection(entry["lemma"], tag))

    return import_vocabulary(
        source_bytes,
        analyzer=lambda fin, eng: analyze_word(fin, eng, morphology),
        name=name,
        overrides=overrides,
        forms_validator=has_forms,
        metadata=metadata,
    )
