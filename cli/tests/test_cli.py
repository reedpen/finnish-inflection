import sys
import types

import pytest

from finnish_core.importer import ImportPreview
from finnish_core.vocab import make_vocabulary_document
import finnish_cli.cli as cli_module
from finnish_cli.cli import main


def test_help_exposes_debug_option(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "--debug" in capsys.readouterr().out


def test_debug_flag_is_forwarded_to_interactive_application(monkeypatch):
    calls = []
    application = types.ModuleType("finnish_cli.app")
    application.main = lambda *, debug=False: calls.append(debug) or 0
    monkeypatch.setitem(sys.modules, "finnish_cli.app", application)

    assert main(["--debug"]) == 0
    assert calls == [True]


def test_import_prints_detailed_preview_rows_before_install(monkeypatch, capsys):
    accepted = {"fin": "koira", "lemma": "koira", "eng": "dog", "pos": "N"}
    preview = ImportPreview(
        accepted=[accepted],
        corrected=[],
        ambiguous=[{"fin": "kuusi", "reason": "multiple analyses"}],
        rejected=[{"fin": "(empty)", "reason": "required"}],
        excluded=[],
        document=make_vocabulary_document([accepted], source_bytes=b"x", name="lesson"),
    )

    class Store:
        def install(self, name, document, replace=False):
            assert name == "lesson"

    monkeypatch.setattr(cli_module, "VocabularyStore", Store)
    monkeypatch.setattr(
        cli_module, "analyze_vocabulary_source", lambda *_, **__: preview
    )

    assert main(["vocab", "import", "lesson", "words.csv", "--yes"]) == 0
    output = capsys.readouterr().out
    assert "Accepted koira: koira (N) — dog" in output
    assert "Ambiguous kuusi: multiple analyses" in output
    assert "Rejected (empty): required" in output


def _preview(columns):
    accepted = {"fin": "talo", "lemma": "talo", "eng": "house", "pos": "N"}
    return ImportPreview(
        accepted=[accepted],
        corrected=[],
        ambiguous=[],
        rejected=[],
        excluded=[],
        document=make_vocabulary_document([accepted], source_bytes=b"x", name="l"),
        columns=columns,
    )


class _Store:
    def install(self, name, document, replace=False):
        pass


@pytest.mark.parametrize(
    ("flag", "column"),
    [([], None), (["--finnish-column", "1"], 0), (["--finnish-column", "2"], 1)],
)
def test_import_passes_the_chosen_finnish_column(monkeypatch, flag, column):
    calls = []

    def analyze(*_, **kwargs):
        calls.append(kwargs["finnish_column"])
        return _preview({"finnish": column or 0, "source": "chosen", "confident": True})

    monkeypatch.setattr(cli_module, "VocabularyStore", _Store)
    monkeypatch.setattr(cli_module, "analyze_vocabulary_source", analyze)

    assert main(["vocab", "import", "l", "words.csv", "--yes", *flag]) == 0
    assert calls == [column]


def test_import_refuses_a_column_other_than_1_or_2(capsys):
    with pytest.raises(SystemExit):
        main(["vocab", "import", "l", "words.csv", "--finnish-column", "3"])

    assert "--finnish-column" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("columns", "line"),
    [
        (
            {"finnish": 1, "source": "auto", "confident": True},
            "Finnish words read from the second column (detected); "
            "use --finnish-column 1 to read the other column.",
        ),
        (
            {"finnish": 0, "source": "auto", "confident": False},
            "Finnish words read from the first column (unsure: check the words); "
            "if the words below are English, re-run with --finnish-column 2.",
        ),
        (
            {"finnish": 1, "source": "header", "confident": True},
            "Finnish words read from the second column (named by the header row); "
            "use --finnish-column 1 to read the other column.",
        ),
        (
            {"finnish": 0, "source": "chosen", "confident": True},
            "Finnish words read from the first column (as chosen).",
        ),
    ],
)
def test_import_says_which_column_was_read_as_finnish(
    monkeypatch, capsys, columns, line
):
    monkeypatch.setattr(cli_module, "VocabularyStore", _Store)
    monkeypatch.setattr(
        cli_module, "analyze_vocabulary_source", lambda *_, **__: _preview(columns)
    )

    assert main(["vocab", "import", "l", "words.csv", "--yes"]) == 0
    assert capsys.readouterr().out.splitlines()[1] == line
