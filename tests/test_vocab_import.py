import io
import sys

import pytest

from src.data.importer import (
    ImportPreview,
    import_vocabulary,
    normalize_path,
    parse_rows,
    preview_rows,
)
from src.data.vocab import VocabularyError


def test_csv_import_previews_accepted_duplicates_and_unknown_words(tmp_path):
    source = tmp_path / "words.csv"
    source.write_text(
        "Front;Back\nkoira;dog\nkoira;hound\nxyz;unknown\n", encoding="utf-8"
    )

    preview = import_vocabulary(
        source,
        analyzer=lambda fin, eng: ("N", "koira") if fin == "koira" else ("?", fin),
        name="lesson",
    )

    assert [item["fin"] for item in preview.accepted] == ["koira"]
    assert preview.rejected == [
        {"fin": "koira", "reason": "duplicate lemma and part of speech"},
    ]
    assert preview.ambiguous == [
        {
            "fin": "xyz",
            "reason": "unknown or ambiguous analysis; add an override or exclusion",
        },
    ]
    assert preview.document["metadata"]["name"] == "lesson"


def test_ambiguous_word_requires_checked_override_or_exclusion(tmp_path):
    source = tmp_path / "words.txt"
    source.write_text("kuusi,six or spruce\npois,away\n", encoding="utf-8")

    preview = import_vocabulary(
        source,
        analyzer=lambda *_: ("?", ""),
        overrides={"kuusi": {"pos": "N", "lemma": "kuusi"}, "pois": None},
        name="reviewed",
    )

    assert preview.corrected == [
        {"fin": "kuusi", "lemma": "kuusi", "eng": "six or spruce", "pos": "N"}
    ]
    assert preview.excluded == ["pois"]
    assert preview.rejected == []


def test_import_rejects_text_without_columns_and_invalid_utf8(tmp_path):
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("koira\nkissa\n", encoding="utf-8")
    with pytest.raises(VocabularyError, match="tab, semicolon, or comma"):
        import_vocabulary(wrong, analyzer=lambda *_: ("N", "koira"), name="x")

    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"koira,\xff")
    with pytest.raises(VocabularyError, match="UTF-8"):
        import_vocabulary(invalid, analyzer=lambda *_: ("N", "koira"), name="x")


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("koira\tdog\npuhua\tto speak, to talk\n", id="quizlet-tab"),
        pytest.param("Front;Back\nkoira;dog\npuhua;to speak, to talk\n", id="anki-csv"),
        pytest.param("koira,dog\npuhua,to speak, to talk\n", id="comma-text"),
        pytest.param(
            'English,Finnish\ndog,koira\n"to speak, to talk",puhua\n',
            id="header-any-order-quoted",
        ),
        pytest.param(
            "#separator:tab\n#html:false\nkoira\tdog\tanimals\n"
            "puhua\tto speak, to talk\tverbs\n",
            id="anki-notes-with-tags",
        ),
        pytest.param(
            "\ufeffSuomi;Englanti\r\nkoira;dog\r\n\r\npuhua;to speak, to talk\r\n",
            id="excel-bom-crlf",
        ),
    ],
)
def test_parse_rows_detects_common_export_formats(text):
    rows, problems = parse_rows(text.removeprefix("\ufeff"))

    assert rows == [("koira", "dog"), ("puhua", "to speak, to talk")]
    assert problems == []


def test_parse_rows_reports_a_bad_line_without_failing_the_list():
    rows, problems = parse_rows("koira;dog\nkissa\ntalo;house\n")

    assert rows == [("koira", "dog"), ("talo", "house")]
    assert problems == [
        {
            "fin": "kissa",
            "reason": "line 2: expected Finnish and English separated by a tab, "
            "semicolon, or comma",
        }
    ]


def test_import_accepts_raw_bytes_with_a_byte_order_mark():
    preview = import_vocabulary(
        "\ufeffkoira\tdog\n".encode("utf-8"),
        analyzer=lambda *_: ("N", "koira"),
        name="pasted",
    )

    assert [item["eng"] for item in preview.accepted] == ["dog"]


def test_import_reads_standard_input(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"koira,dog\n")))

    preview = import_vocabulary("-", analyzer=lambda *_: ("N", "koira"), name="x")

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


def test_unproducible_forms_are_reported(tmp_path):
    source = tmp_path / "words.txt"
    source.write_text("koira,dog\n", encoding="utf-8")

    preview = import_vocabulary(
        source,
        analyzer=lambda *_: ("N", "koira"),
        forms_validator=lambda entry: False,
        name="x",
    )

    assert preview.accepted == []
    assert preview.rejected == [{"fin": "koira", "reason": "no generated forms"}]


@pytest.mark.parametrize("override", ["noun", {"lemma": 42, "pos": "N"}])
def test_malformed_overrides_are_actionable(tmp_path, override):
    source = tmp_path / "words.txt"
    source.write_text("koira,dog\n", encoding="utf-8")

    with pytest.raises(VocabularyError, match="override.*koira"):
        import_vocabulary(
            source,
            analyzer=lambda *_: ("N", "koira"),
            overrides={"koira": override},
            name="x",
        )


def test_preview_rows_detail_each_review_category():
    accepted = {"fin": "koira", "lemma": "koira", "eng": "dog", "pos": "N"}
    corrected = {
        "fin": "puhun",
        "lemma": "puhua",
        "eng": "speak",
        "pos": "V",
        "verb_type": 1,
    }
    preview = ImportPreview(
        accepted=[accepted, corrected],
        corrected=[corrected],
        ambiguous=[{"fin": "kuusi", "reason": "multiple analyses"}],
        rejected=[{"fin": "(empty)", "reason": "required"}],
        excluded=["pois"],
        document={},
    )

    assert preview_rows(preview) == [
        {"status": "accepted", "fin": "koira", "detail": "koira (N) — dog"},
        {
            "status": "corrected",
            "fin": "puhun",
            "detail": "puhua (V) — speak",
        },
        {"status": "ambiguous", "fin": "kuusi", "detail": "multiple analyses"},
        {"status": "rejected", "fin": "(empty)", "detail": "required"},
        {
            "status": "excluded",
            "fin": "pois",
            "detail": "explicitly excluded by review",
        },
    ]


def test_preview_rows_does_not_repeat_an_ambiguous_rejection():
    problem = {"fin": "kuusi", "reason": "multiple analyses"}
    preview = ImportPreview(
        accepted=[],
        corrected=[],
        ambiguous=[problem],
        rejected=[problem],
        excluded=[],
        document={},
    )

    assert preview_rows(preview) == [
        {"status": "ambiguous", "fin": "kuusi", "detail": "multiple analyses"}
    ]
