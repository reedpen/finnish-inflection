import os
import sys
import types

from prompt_toolkit.enums import EditingMode

from src.cli import main
from src.ui import drill
from src.ui.editing import enable_vi_mode, vi_mode_requested


def test_vim_flag_requests_vi_mode_for_interactive_application(monkeypatch):
    # setenv first so monkeypatch restores the variable's absence afterwards.
    monkeypatch.setenv("FINNISH_DRILL_VIM", "")
    monkeypatch.delenv("FINNISH_DRILL_VIM")
    seen = []
    application = types.ModuleType("src.main")
    application.main = lambda *, debug=False: seen.append(vi_mode_requested()) or 0
    monkeypatch.setitem(sys.modules, "src.main", application)

    assert main(["--vim"]) == 0
    assert seen == [True]


def test_vi_mode_is_off_without_flag_or_env(monkeypatch):
    monkeypatch.delenv("FINNISH_DRILL_VIM", raising=False)
    assert not vi_mode_requested()
    monkeypatch.setenv("FINNISH_DRILL_VIM", "0")
    assert not vi_mode_requested()


def test_enable_vi_mode_configures_menus_and_answer_prompt(monkeypatch):
    monkeypatch.setenv("INQUIRERPY_VI_MODE", "")
    monkeypatch.delenv("INQUIRERPY_VI_MODE")
    original = drill.session.editing_mode
    try:
        enable_vi_mode()
        assert drill.session.editing_mode == EditingMode.VI
        assert os.environ["INQUIRERPY_VI_MODE"] == "1"
    finally:
        drill.session.editing_mode = original
