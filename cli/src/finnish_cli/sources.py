"""Where word lists come from: typed or dropped paths, standard input, raw text."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from finnish_core.importer import (
    ImportPreview,
    Overrides,
    analyze_vocabulary,
    validate_overrides,
)
from finnish_core.vocab import VocabularyError

Source = Path | str | bytes
"""A file path, ``"-"`` for standard input, or the raw bytes of a word list."""


def normalize_path(raw: str | Path) -> Path:
    """Turn a typed, pasted, or drag-and-dropped path into a usable ``Path``.

    Terminals deliver dropped files as ``'/quoted path.csv'``, ``file:///...``
    URIs, or with backslash-escaped spaces; users type ``~``. None of those
    work with ``Path`` directly.
    """
    text = str(raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    if text.startswith("file://"):
        text = unquote(urlparse(text).path)
    elif os.name != "nt":
        text = re.sub(r"\\(.)", r"\1", text)
    return Path(text).expanduser()


def read_source(source: Source) -> bytes:
    """Return the bytes of a path, standard input (``"-"``), or raw content."""
    if isinstance(source, bytes):
        return source
    if str(source).strip() == "-":
        return sys.stdin.buffer.read()
    path = normalize_path(source)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise VocabularyError(f"could not read {path}: {exc.strerror or exc}") from exc


def load_overrides(path: Path | str | None) -> Overrides | None:
    if path is None or str(path).strip() == "":
        return None
    source = normalize_path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VocabularyError(f"could not read overrides: {exc}") from exc
    return validate_overrides(value)


def analyze_vocabulary_source(
    source: Source,
    *,
    name: str,
    overrides: Overrides | None = None,
    morphology=None,
    metadata: dict[str, str] | None = None,
) -> ImportPreview:
    """Read a source, make sure the model is installed, and analyze it."""
    from finnish_core.morphology import InflectionEngine, UralicNlpAdapter

    from finnish_cli.engine import announce_download

    data = read_source(source)
    morphology = morphology or UralicNlpAdapter()
    InflectionEngine(morphology).ensure_model_downloaded(
        "fin", on_download=announce_download
    )
    return analyze_vocabulary(
        data, morphology, name=name, overrides=overrides, metadata=metadata
    )
