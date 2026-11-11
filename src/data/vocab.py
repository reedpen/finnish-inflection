"""Validated vocabulary documents and named user vocabulary sets.

The JSON format in this module is the single interchange format used by the
offline builder, packaged vocabulary, and user imports.  Keeping validation at
this boundary means drill code never has to defend itself from partial records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import warnings
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, NotRequired, TypedDict, cast

from platformdirs import user_data_dir

if TYPE_CHECKING:
    from src.nlp.engine import MorphologyAdapter

APP_NAME = "finnish-inflection-cli"
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
    return cast(VocabularyEntry, item)


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


def load_vocabulary_document(
    path: Path | str, *, source_bytes: bytes | None = None
) -> VocabularyDocument:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            document = validate_vocabulary_document(json.load(handle))
        if source_bytes is not None:
            fingerprint = hashlib.sha256(source_bytes).hexdigest()
            if document["metadata"]["source_sha256"] != fingerprint:
                raise VocabularyError("vocabulary cache is stale for its source")
        return document
    except VocabularyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VocabularyError(f"could not read vocabulary: {exc}") from exc


def write_vocabulary_document(path: Path | str, document: Any) -> None:
    """Validate then atomically replace *path*, preserving an existing good file."""
    validated = validate_vocabulary_document(document)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(validated, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_or_rebuild_vocabulary(
    path: Path | str,
    *,
    source_bytes: bytes,
    rebuild: Callable[[], VocabularyDocument],
) -> VocabularyDocument:
    """Load a current cache or atomically rebuild corrupt, old, or stale data."""
    try:
        return load_vocabulary_document(path, source_bytes=source_bytes)
    except VocabularyError:
        document = rebuild()
        validated = validate_vocabulary_document(document)
        expected = hashlib.sha256(source_bytes).hexdigest()
        if validated["metadata"]["source_sha256"] != expected:
            raise VocabularyError(
                "rebuilt vocabulary does not match the current source"
            )
        write_vocabulary_document(path, validated)
        return load_vocabulary_document(path, source_bytes=source_bytes)


class VocabularyStore:
    """Manage named validated sets beneath a platform-specific user directory."""

    def __init__(self, root: Path | str | None = None):
        self.root = (
            Path(root)
            if root is not None
            else Path(user_data_dir(APP_NAME)) / "vocabularies"
        )
        self.selection_path = self.root / "selected"

    def _path(self, name: str) -> Path:
        if not _SET_NAME.fullmatch(name):
            raise VocabularyError(
                "set name must contain only letters, numbers, underscores, or hyphens"
            )
        return self.root / f"{name}.json"

    def install(self, name: str, document: Any, *, replace: bool = False) -> None:
        path = self._path(name)
        if path.exists() and not replace:
            raise VocabularyError(
                f"vocabulary set {name!r} already exists; use replace"
            )
        validated = validate_vocabulary_document(document)
        validated["metadata"]["name"] = name
        write_vocabulary_document(path, validated)

    def load(self, name: str) -> VocabularyDocument:
        path = self._path(name)
        if not path.exists():
            raise VocabularyError(f"vocabulary set {name!r} does not exist")
        return load_vocabulary_document(path)

    def list_sets(self) -> list[dict[str, Any]]:
        selected = self.selected_name()
        if not self.root.exists():
            return []
        result = []
        for path in sorted(self.root.glob("*.json")):
            try:
                document = load_vocabulary_document(path)
            except VocabularyError:
                continue
            result.append(
                {
                    "name": path.stem,
                    "selected": path.stem == selected,
                    "entries": len(document["entries"]),
                }
            )
        return result

    def select(self, name: str) -> None:
        if name == "default":
            self.root.mkdir(parents=True, exist_ok=True)
            self.selection_path.unlink(missing_ok=True)
            return
        self.load(name)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.selection_path.with_suffix(".tmp")
        temporary.write_text(name + "\n", encoding="utf-8")
        os.replace(temporary, self.selection_path)

    def selected_name(self) -> str | None:
        document, recovery_notice = self.load_selected()
        if recovery_notice:
            warnings.warn(recovery_notice, RuntimeWarning, stacklevel=2)
        return document["metadata"]["name"] if document is not None else None

    def load_selected(self) -> tuple[VocabularyDocument | None, str | None]:
        """Load the selected set or recover safely to the packaged default.

        Invalid selection pointers are removed. Invalid selected documents are
        moved aside so a later import cannot silently overwrite evidence that
        may help the user repair their set.
        """
        try:
            name = self.selection_path.read_text(encoding="utf-8").strip()
            self._path(name)
        except FileNotFoundError:
            return None, None
        except (OSError, UnicodeError, VocabularyError) as exc:
            self.selection_path.unlink(missing_ok=True)
            return (
                None,
                f"Invalid vocabulary selection was cleared ({exc}). Using the default set.",
            )
        path = self._path(name)
        if not path.exists():
            self.selection_path.unlink(missing_ok=True)
            return (
                None,
                f"Selected vocabulary {name!r} is missing. Selection was cleared; using the default set.",
            )
        try:
            return load_vocabulary_document(path), None
        except VocabularyError as exc:
            quarantine = path.with_suffix(path.suffix + ".invalid")
            counter = 1
            while quarantine.exists():
                quarantine = path.with_suffix(path.suffix + f".invalid-{counter}")
                counter += 1
            try:
                os.replace(path, quarantine)
                location = f" It was moved to {quarantine}."
            except OSError:
                location = (
                    " It could not be moved; inspect or remove it before reimporting."
                )
            self.selection_path.unlink(missing_ok=True)
            return None, (
                f"Selected vocabulary {name!r} is invalid ({exc}).{location} "
                "Using the default set."
            )

    def remove(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise VocabularyError(f"vocabulary set {name!r} does not exist")
        was_selected = self.selected_name() == name
        path.unlink()
        if was_selected:
            self.selection_path.unlink(missing_ok=True)


def categorize_word(
    word: str,
    english_hint: str = "",
    morphology: "MorphologyAdapter | None" = None,
) -> tuple[str, str]:
    """Categorize a word with complete UralicNLP analyzer strings."""
    if morphology is None:
        from src.nlp.engine import UralicNlpAdapter

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


def _packaged_document() -> VocabularyDocument:
    resource = files("src.data").joinpath("default_vocab.json")
    try:
        with resource.open(encoding="utf-8") as handle:
            return validate_vocabulary_document(json.load(handle))
    except (OSError, json.JSONDecodeError, VocabularyError) as exc:
        raise VocabularyError(
            f"packaged default vocabulary is unavailable or invalid: {exc}"
        ) from exc


def load_book_of_mormon_vocab(
    filepath: str | None = None,
) -> tuple[list[VocabularyEntry], list[VocabularyEntry]]:
    """Compatibility API returning nouns/adjectives and verbs from the active set."""
    if filepath:
        document = load_vocabulary_document(filepath)
    else:
        store = VocabularyStore()
        document, recovery_notice = store.load_selected()
        if recovery_notice:
            warnings.warn(recovery_notice, RuntimeWarning, stacklevel=2)
        document = document or _packaged_document()
    nouns = [item for item in document["entries"] if item["pos"] in {"N", "A"}]
    verbs = [item for item in document["entries"] if item["pos"] == "V"]
    return nouns, verbs


def get_nouns_list() -> list[VocabularyEntry]:
    return load_book_of_mormon_vocab()[0]


def get_verbs_list() -> list[VocabularyEntry]:
    return load_book_of_mormon_vocab()[1]


def get_verbs_by_type(verb_types: list[int]) -> list[VocabularyEntry]:
    allowed = set(verb_types)
    return [verb for verb in get_verbs_list() if verb["verb_type"] in allowed]
