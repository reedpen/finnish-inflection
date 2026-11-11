from InquirerPy import inquirer

import finnish_cli.ui.menu as menu
from finnish_cli.ui.keys import NAV_KEYBINDINGS


def _keys(prompt, action):
    return {binding["key"] for binding in prompt.kb_maps[action]}


def test_nav_keybindings_add_j_k_without_dropping_defaults():
    for build in (inquirer.select, inquirer.checkbox):
        prompt = build(message="x", choices=["a", "b"], keybindings=NAV_KEYBINDINGS)
        assert _keys(prompt, "down") == {"down", "c-n", "j"}
        assert _keys(prompt, "up") == {"up", "c-p", "k"}
        # Unrelated defaults such as toggling are untouched.
        assert "toggle" in prompt.kb_maps


def test_menus_pass_nav_keybindings(monkeypatch):
    seen = []

    class Prompt:
        def __init__(self, value):
            self.value = value

        def execute(self):
            return self.value

    def fake(**kwargs):
        seen.append(kwargs.get("keybindings"))
        return Prompt(kwargs["choices"][-1])

    monkeypatch.setattr(menu.inquirer, "select", fake)
    monkeypatch.setattr(menu.inquirer, "checkbox", fake)

    menu._session_length()
    menu.checkbox_with_all("Pick:", ["a", "b"])

    assert seen == [NAV_KEYBINDINGS, NAV_KEYBINDINGS]
