"""Shared command vocabulary for every drill."""

from enum import StrEnum


class InputAction(StrEnum):
    ANSWER = "answer"
    HINT = "hint"
    SKIP = "skip"
    BACK = "back"
    QUIT = "quit"


class NavigationAction(StrEnum):
    REPLAY = "replay"
    RECONFIGURE = "reconfigure"
    MENU = "menu"
    QUIT = "quit"


ALIASES = {
    "h": InputAction.HINT,
    "hint": InputAction.HINT,
    "": InputAction.SKIP,
    "s": InputAction.SKIP,
    "skip": InputAction.SKIP,
    "b": InputAction.BACK,
    "back": InputAction.BACK,
    "q": InputAction.QUIT,
    "quit": InputAction.QUIT,
}


def parse_input(value: str) -> InputAction:
    return ALIASES.get(value.strip().lower(), InputAction.ANSWER)
