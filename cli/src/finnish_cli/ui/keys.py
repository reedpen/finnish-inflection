"""Key bindings shared by every menu and checklist."""

# InquirerPy replaces an action's default keys when it is overridden, so the
# arrow and Emacs keys are listed alongside j/k.
NAV_KEYBINDINGS = {
    "down": [{"key": "down"}, {"key": "c-n"}, {"key": "j"}],
    "up": [{"key": "up"}, {"key": "c-p"}, {"key": "k"}],
}
