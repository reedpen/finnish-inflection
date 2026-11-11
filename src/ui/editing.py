"""Opt-in vi key bindings for every interactive prompt."""

import os

from prompt_toolkit.enums import EditingMode

ENV_VAR = "FINNISH_DRILL_VIM"
# InquirerPy treats any non-empty value as enabled, so it is only ever set.
INQUIRERPY_ENV_VAR = "INQUIRERPY_VI_MODE"


def vi_mode_requested() -> bool:
    return os.environ.get(ENV_VAR) == "1"


def enable_vi_mode() -> None:
    """Use vi editing in drill answers and j/k navigation in menus."""
    from src.ui import drill

    os.environ[INQUIRERPY_ENV_VAR] = "1"
    drill.session.editing_mode = EditingMode.VI
