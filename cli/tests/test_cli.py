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
