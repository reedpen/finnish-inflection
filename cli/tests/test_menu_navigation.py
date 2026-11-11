from contextlib import nullcontext

import pytest

from finnish_core.questions import Question
from finnish_cli.interaction import NavigationAction
from finnish_core.session import SessionAction
from finnish_core.settings import DrillSettings
from finnish_cli.ui import menu
from finnish_cli.ui.drill import SessionResult


class FakeConsole:
    def status(self, *_args, **_kwargs):
        return nullcontext()

    def print(self, *_args, **_kwargs):
        pass

    def input(self, *_args, **_kwargs):
        return ""


class FakeSelect:
    def __init__(self, replies):
        self.replies = iter(replies)

    def __call__(self, **_kwargs):
        reply = next(self.replies)

        class Prompt:
            def execute(self):
                return reply

        return Prompt()


class RecordingStore:
    def __init__(self):
        self.saved = []

    def save(self, settings):
        self.saved.append(settings)


def test_post_session_can_replay_then_return_to_configuration(monkeypatch):
    runs = 0
    store = RecordingStore()

    def run_session(*_args):
        nonlocal runs
        runs += 1
        return SessionResult("complete", "summary")

    monkeypatch.setattr(menu, "console", FakeConsole())
    monkeypatch.setattr(menu, "settings_store", store)
    monkeypatch.setattr(menu, "run_practice_session", run_session)
    monkeypatch.setattr(menu.inquirer, "select", FakeSelect(["replay", "reconfigure"]))
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)
    question = Question("id", "Word", "talo", "house", "target", ("talo",))

    action = menu._run_pool(configuration, lambda _: [question], "Noun Drill")

    assert runs == 2
    assert action == "reconfigure"
    assert store.saved == [configuration]


def test_quit_still_offers_post_session_actions(monkeypatch):
    store = RecordingStore()
    monkeypatch.setattr(menu, "console", FakeConsole())
    monkeypatch.setattr(menu, "settings_store", store)
    monkeypatch.setattr(
        menu, "run_practice_session", lambda *_: SessionResult("quit", "summary")
    )
    monkeypatch.setattr(menu.inquirer, "select", FakeSelect(["menu"]))
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)
    question = Question("id", "Word", "talo", "house", "target", ("talo",))

    assert menu._run_pool(configuration, lambda _: [question], "Noun Drill") == "menu"
    assert store.saved == [configuration]


def test_settings_are_saved_only_after_a_playable_session_returns(monkeypatch):
    saved = []

    class Store:
        def save(self, settings):
            saved.append(settings)

    monkeypatch.setattr(menu, "settings_store", Store())
    monkeypatch.setattr(menu, "console", FakeConsole())
    monkeypatch.setattr(
        menu, "run_practice_session", lambda *_: SessionResult("complete", "summary")
    )
    monkeypatch.setattr(menu.inquirer, "select", FakeSelect(["menu"]))
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)
    question = Question("id", "Word", "talo", "house", "target", ("talo",))

    menu._run_pool(configuration, lambda _: [question], "Noun Drill")

    assert saved == [configuration]


def test_post_session_choices_prioritize_the_action_the_user_requested():
    back = menu._post_session_choices(SessionAction.BACK)
    quit_ = menu._post_session_choices(SessionAction.QUIT)

    assert back[0]["value"] == NavigationAction.RECONFIGURE
    assert quit_[0]["value"] == NavigationAction.QUIT
    assert {choice["value"] for choice in back} == set(NavigationAction)
    assert {choice["value"] for choice in quit_} == set(NavigationAction)


def test_empty_pool_does_not_replace_last_settings(monkeypatch):
    saved = []

    class Store:
        def save(self, settings):
            saved.append(settings)

    monkeypatch.setattr(menu, "settings_store", Store())
    monkeypatch.setattr(menu, "console", FakeConsole())
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)

    assert menu._run_pool(configuration, lambda _: [], "Noun Drill") == "reconfigure"
    assert saved == []


def test_failed_session_start_does_not_replace_last_settings(monkeypatch):
    saved = []

    class Store:
        def save(self, settings):
            saved.append(settings)

    monkeypatch.setattr(menu, "settings_store", Store())
    monkeypatch.setattr(menu, "console", FakeConsole())
    monkeypatch.setattr(
        menu,
        "run_practice_session",
        lambda *_: (_ for _ in ()).throw(RuntimeError("terminal unavailable")),
    )
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)
    question = Question("id", "Word", "talo", "house", "target", ("talo",))

    with pytest.raises(RuntimeError, match="terminal unavailable"):
        menu._run_pool(configuration, lambda _: [question], "Noun Drill")

    assert saved == []


def test_back_to_configuration_reopens_the_same_drill_setup(monkeypatch):
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)
    configurations = iter([configuration, None])
    setup_visits = 0

    def choose_setup(*_args):
        nonlocal setup_visits
        setup_visits += 1
        return next(configurations)

    monkeypatch.setattr(menu, "_choose_setup", choose_setup)
    monkeypatch.setattr(menu, "_run_pool", lambda *_args: "reconfigure")

    assert menu.setup_noun_drill() is False
    assert setup_visits == 2


def test_generation_error_returns_to_configuration_without_a_traceback(monkeypatch):
    monkeypatch.setattr(menu, "console", FakeConsole())
    configuration = DrillSettings("noun", {"cases": ["+Nom"], "numbers": ["+Sg"]}, 10)

    action = menu._run_pool(
        configuration,
        lambda _: (_ for _ in ()).throw(RuntimeError("model unavailable")),
        "Noun Drill",
    )

    assert action == "reconfigure"
