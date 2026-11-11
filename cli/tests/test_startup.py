import sys
import types

from finnish_cli import app as application


def test_startup_failure_is_actionable_without_a_traceback(monkeypatch, capsys):
    data_module = types.ModuleType("finnish_cli.store")
    data_module.load_book_of_mormon_vocab = lambda: (_ for _ in ()).throw(
        OSError("disk full")
    )
    engine_module = types.ModuleType("finnish_cli.engine")
    engine_module.ensure_model_downloaded = lambda language: None
    menu_module = types.ModuleType("finnish_cli.ui.menu")
    menu_module.run_menu = lambda: None
    monkeypatch.setitem(sys.modules, "finnish_cli.store", data_module)
    monkeypatch.setitem(sys.modules, "finnish_cli.engine", engine_module)
    monkeypatch.setitem(sys.modules, "finnish_cli.ui.menu", menu_module)

    assert application.main() == 1

    output = capsys.readouterr()
    assert "could not start" in output.out
    assert "network connection" in output.out
    assert "Traceback" not in output.out + output.err
