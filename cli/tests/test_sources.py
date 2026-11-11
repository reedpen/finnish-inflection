import io
import sys

import pytest

from finnish_cli.sources import normalize_path, read_source
from finnish_core.importer import import_vocabulary


def test_read_source_accepts_raw_bytes():
    assert read_source(b"koira,dog\n") == b"koira,dog\n"


def test_import_reads_standard_input(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"koira,dog\n")))

    preview = import_vocabulary(
        read_source("-"), analyzer=lambda *_: ("N", "koira"), name="x"
    )

    assert [item["fin"] for item in preview.accepted] == ["koira"]


@pytest.mark.parametrize(
    "typed",
    [
        "'{path}'",
        '"{path}"',
        "  {path}  ",
        "file://{url_path}",
        "{escaped}",
    ],
)
def test_normalize_path_handles_dragged_and_quoted_paths(tmp_path, typed):
    source = tmp_path / "my words.csv"
    source.write_text("koira;dog\n", encoding="utf-8")
    raw = typed.format(
        path=source,
        url_path=str(source).replace(" ", "%20"),
        escaped=str(source).replace(" ", "\\ "),
    )

    assert normalize_path(raw) == source


def test_normalize_path_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert normalize_path("~/words.csv") == tmp_path / "words.csv"
