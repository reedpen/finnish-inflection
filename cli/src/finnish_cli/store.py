"""Named vocabulary sets stored as JSON files in the user's data directory."""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from pathlib import Path
from typing import Any, Callable

from platformdirs import user_data_dir

from finnish_core.vocab import (
    VocabularyDocument,
    VocabularyEntry,
    VocabularyError,
    is_valid_set_name,
    packaged_default_document,
    validate_vocabulary_document,
)

APP_NAME = "finnish-inflection-cli"


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
        if not is_valid_set_name(name):
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
        document = document or packaged_default_document()
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
