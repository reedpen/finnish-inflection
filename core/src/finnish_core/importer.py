"""Vocabulary import and review: parse a word list, analyze it, and preview it.

Everything here works on bytes and plain data. Reading files or standard input
is up to the caller.
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, TypedDict

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
    # Which column was read as Finnish, and why (see ColumnChoice).
    columns: ColumnChoice = field(
        default_factory=lambda: {"finnish": 0, "source": "auto", "confident": True}
    )


Overrides = dict[str, dict[str, str] | None]
# Column names recognised in an optional header row (compared case-insensitively).
_FINNISH_HEADERS = {
    "front",
    "finnish",
    "suomi",
    "suomeksi",
    "fin",
    "fi",
    "word",
    "term",
    "sana",
    "finnish word",
}
_ENGLISH_HEADERS = {
    "back",
    "english",
    "englanti",
    "englanniksi",
    "eng",
    "en",
    "definition",
    "meaning",
    "translation",
    "gloss",
    "english word",
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


def _check_column(finnish_column: int | None) -> None:
    if finnish_column not in (None, 0, 1):
        raise VocabularyError("the Finnish column must be the first or the second")


@dataclass(frozen=True)
class WordTable:
    """A word list split into cells, before deciding which column is Finnish.

    ``header`` holds the ``(finnish, english)`` cell indexes named by a
    recognised header row (which is not among ``lines``).
    """

    delimiter: str
    header: tuple[int, int] | None
    lines: list[tuple[int, list[str]]]

    @property
    def header_finnish_column(self) -> int | None:
        """Which of the two word columns the header names as Finnish (0 or 1)."""
        if self.header is None:
            return None
        fin, eng = self.header
        return 0 if fin < eng else 1

    def _pair(self, parts: list[str], finnish_column: int | None) -> tuple[str, str]:
        if self.header is not None:
            fin_col, eng_col = self.header
            if finnish_column is not None:
                first, second = sorted(self.header)
                fin_col, eng_col = (
                    (first, second) if finnish_column == 0 else (second, first)
                )
            fin = parts[fin_col] if fin_col < len(parts) else ""
            eng = parts[eng_col] if eng_col < len(parts) else ""
            return fin, eng
        if len(parts) < 2:
            return (parts[0] if parts else ""), ""
        if self.delimiter == "\t":
            # Tab exports (Anki, Quizlet) may carry extra columns such as tags.
            return (parts[1], parts[0]) if finnish_column == 1 else (parts[0], parts[1])
        if finnish_column == 1:
            # "to speak, to talk, puhua" keeps everything before the last separator.
            return parts[-1], self.delimiter.join(parts[:-1])
        # "puhua, to speak, to talk" keeps everything after the first separator.
        return parts[0], self.delimiter.join(parts[1:])

    def rows(
        self, finnish_column: int | None = None
    ) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
        """``(finnish, english)`` rows and per-line problems.

        ``finnish_column`` says which of the two word columns is Finnish: 0 (the
        first) or 1 (the second). ``None`` follows the header row, if there is
        one, or else takes the first.
        """
        _check_column(finnish_column)
        rows: list[tuple[str, str]] = []
        problems: list[dict[str, str]] = []
        for number, parts in self.lines:
            fin, eng = self._pair(parts, finnish_column)
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

    def column_cells(self) -> list[tuple[str, str]]:
        """For each line with two words: the word read as Finnish if the first
        column is Finnish, and the one read as Finnish if the second is.

        This is what :func:`detect_finnish_column` compares.
        """
        cells = []
        for _, parts in self.lines:
            first = self._pair(parts, 0)
            second = self._pair(parts, 1)
            if all(value.strip() for value in (*first, *second)):
                cells.append((first[0].strip(), second[0].strip()))
        return cells


def read_table(text: str) -> WordTable:
    """Split a word list into cells: the first step of :func:`parse_rows`."""
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

    header = _header_columns(cells(*lines[0]))
    if header is not None:
        lines = lines[1:]
    return WordTable(
        delimiter, header, [(number, cells(number, line)) for number, line in lines]
    )


def parse_rows(
    text: str, *, finnish_column: int | None = None
) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    """Split a word list into ``(finnish, english)`` rows and per-line problems.

    Accepts tab-, semicolon-, or comma-separated text with an optional header
    row, which covers Quizlet and Anki exports, spreadsheets, and hand-typed
    lists. Lines starting with ``#`` are comments (or Anki export directives).

    Without a header row the first column is Finnish, unless ``finnish_column``
    is 1 (see :meth:`WordTable.rows`).
    """
    return read_table(text).rows(finnish_column)


# --- Which column is Finnish -------------------------------------------------

# Words that mark a cell as English. None of them is also a common Finnish word
# ("he", "me", "on" and "se" are, so they are left out).
_ENGLISH_WORDS = frozenset(
    """a an the to of in at by for with from about into and or but not no
    is are was were be been am i you we they it its my your his her our their
    this that these those what which who how something someone sth sb""".split()
)
_FINNISH_LETTERS = frozenset("äöå")
# How much more Finnish-looking, per row, the second column has to be before it
# is taken as Finnish; and the first, for its choice to count as confident.
_CLEAR_LEAD = 0.5
DETECTION_SAMPLE = 40


@dataclass(frozen=True)
class ColumnGuess:
    """Which column :func:`detect_finnish_column` reads as Finnish.

    ``scores`` is how Finnish each column looked, on average per row: roughly
    -1 (English) to 2 (a known word with Finnish letters).
    """

    finnish: int
    confident: bool
    scores: tuple[float, float]


class ColumnChoice(TypedDict):
    """How the Finnish column was decided, as an import preview reports it.

    ``finnish`` is 0 for the first word column and 1 for the second.
    ``source`` is ``"header"`` (a header row named it), ``"chosen"`` (the caller
    passed it), or ``"auto"`` (detected; ``confident`` is false when the
    evidence was close and the first column was kept).
    """

    finnish: int
    source: str
    confident: bool


def _words(text: str) -> list[str]:
    return "".join(ch if ch.isalpha() else " " for ch in text).split()


def cell_score(cell: str, known: Callable[[str], bool] | None = None) -> float:
    """How Finnish one cell looks: known words, Finnish letters, English hints.

    ``known`` tells whether the Finnish model knows a word; without it only the
    spelling counts. Mirrored by ``cellScore`` in the web app's vocabParse.ts.
    """
    text = unicodedata.normalize("NFC", cell).strip()
    folded = text.casefold()
    words = _words(text)
    if not words:
        return 0.0
    recognised = sum(1 for word in words if known(word)) if known else 0
    score = recognised / len(words)
    if _FINNISH_LETTERS & set(folded):
        score += 1
    if folded.startswith("to ") or any(
        word.casefold() in _ENGLISH_WORDS for word in words
    ):
        score -= 1
    elif len(words) > 1 and recognised < len(words):
        score -= 0.5  # a multi-word gloss, not a known Finnish phrase
    return score


def _spread(rows: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    if len(rows) <= limit:
        return list(rows)
    return [rows[i * len(rows) // limit] for i in range(limit)]


def detect_finnish_column(
    rows: list[tuple[str, str]],
    morphology: MorphologyAdapter | None = None,
    *,
    limit: int = DETECTION_SAMPLE,
) -> ColumnGuess:
    """Guess which of two columns holds the Finnish words.

    ``rows`` pairs, per line, the cell each column would give as Finnish (see
    :meth:`WordTable.column_cells`). At most ``limit`` rows, spread over the
    list, are scored with :func:`cell_score`: words the model genuinely knows
    (it doesn't guess at unknown ones), Finnish letters, and English hints such
    as a leading "to ", function words, and multi-word glosses. Without
    ``morphology`` only the spelling counts.

    The second column is chosen only when it is clearly more Finnish. When the
    evidence is close, the first is kept but the guess is not confident.
    """
    sample = _spread(rows, limit)
    if not sample:
        return ColumnGuess(0, True, (0.0, 0.0))
    known = None
    if morphology is not None:
        from finnish_core.vocab import is_known_word

        cache: dict[str, bool] = {}

        def known(word: str) -> bool:
            if word not in cache:
                cache[word] = is_known_word(word, morphology)
            return cache[word]

    first = sum(cell_score(cell, known) for cell, _ in sample) / len(sample)
    second = sum(cell_score(cell, known) for _, cell in sample) / len(sample)
    lead = second - first
    if lead >= _CLEAR_LEAD:
        return ColumnGuess(1, True, (first, second))
    return ColumnGuess(0, lead <= -_CLEAR_LEAD, (first, second))


ColumnDetector = Callable[[list[tuple[str, str]]], ColumnGuess]


def choose_columns(
    table: WordTable,
    finnish_column: int | None = None,
    detect: ColumnDetector = detect_finnish_column,
) -> ColumnChoice:
    """Decide the Finnish column: the caller's choice, the header, or a guess."""
    _check_column(finnish_column)
    if finnish_column is not None:
        return {"finnish": finnish_column, "source": "chosen", "confident": True}
    if table.header_finnish_column is not None:
        return {
            "finnish": table.header_finnish_column,
            "source": "header",
            "confident": True,
        }
    guess = detect(table.column_cells())
    return {"finnish": guess.finnish, "source": "auto", "confident": guess.confident}


def column_summary(columns: ColumnChoice) -> str:
    """One line saying which column was read as Finnish, and why."""
    where = "first" if columns["finnish"] == 0 else "second"
    why = {
        "header": "named by the header row",
        "chosen": "as chosen",
        "auto": "detected" if columns["confident"] else "unsure: check the words",
    }.get(columns["source"], columns["source"])
    return f"Finnish words read from the {where} column ({why})"


def import_vocabulary(
    source_bytes: bytes,
    *,
    analyzer: Analyzer,
    name: str,
    overrides: Overrides | None = None,
    forms_validator: Callable[[dict[str, Any]], bool] | None = None,
    metadata: dict[str, str] | None = None,
    finnish_column: int | None = None,
    detect_columns: ColumnDetector = detect_finnish_column,
) -> ImportPreview:
    """Parse, analyze, and preview a word list without installing it.

    ``finnish_column`` (0 or 1) says which column is Finnish. Otherwise a
    header row decides, or else ``detect_columns`` (by default
    :func:`detect_finnish_column` going by spelling alone).
    """
    table = read_table(_decode(source_bytes))
    columns = choose_columns(table, finnish_column, detect_columns)
    rows, problems = table.rows(columns["finnish"])
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
        accepted, corrected, ambiguous, rejected, excluded, document, assumed, columns
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
    finnish_column: int | None = None,
) -> ImportPreview:
    """Analyze a word list with a real morphology model and preview it.

    The model must already be installed. Each accepted word is checked by
    generating one representative form. Unless ``finnish_column`` (0 or 1) or
    a header row says which column is Finnish, the model helps detect it (see
    :func:`detect_finnish_column`).
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
        finnish_column=finnish_column,
        detect_columns=lambda rows: detect_finnish_column(rows, morphology),
    )
