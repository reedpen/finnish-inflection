"""Interactive vocabulary-set management."""

from InquirerPy import inquirer
from rich.console import Console

from finnish_core.importer import preview_rows, preview_summary
from finnish_cli.remote import (
    RemoteRepository,
    analyze_remote_set,
    find_updates,
    installed_remote_sets,
    remote_status,
)
from finnish_core.vocab import VocabularyError, is_valid_set_name, suggest_set_name
from finnish_cli.sources import (
    analyze_vocabulary_source,
    load_overrides,
    normalize_path,
)
from finnish_cli.store import VocabularyStore
from finnish_cli.ui.keys import NAV_KEYBINDINGS


console = Console()


def vocabulary_listing(store: VocabularyStore) -> list[dict]:
    """Return display-ready built-in and custom vocabulary set rows."""
    selected = store.selected_name()
    rows = [{"name": "default", "selected": selected is None, "entries": "built-in"}]
    rows.extend(store.list_sets())
    return rows


def _print_vocabulary_listing(store: VocabularyStore) -> None:
    console.print("\n[bold]Vocabulary sets[/bold]")
    for item in vocabulary_listing(store):
        marker = "[green]active[/green]" if item["selected"] else ""
        console.print(f"  {item['name']}: {item['entries']} {marker}")


_STYLES = {
    "accepted": "green",
    "corrected": "cyan",
    "ambiguous": "yellow",
    "rejected": "red",
    "excluded": "dim",
}
_ANALYZING = "[cyan]Analyzing vocabulary and checking generated forms…[/cyan]"


def _ask_name(default: str = "") -> str:
    return (
        inquirer.text(
            message="Set name:",
            default=default,
            validate=lambda value: (
                not value.strip() or is_valid_set_name(value.strip())
            ),
            invalid_message="Use only letters, numbers, underscores, and hyphens",
            mandatory=False,
        ).execute()
        or ""
    ).strip()


def _ask_path(message: str, instruction: str = "") -> str:
    return (
        inquirer.filepath(
            message=message,
            long_instruction=instruction,
            validate=lambda value: not value.strip() or normalize_path(value).is_file(),
            invalid_message="No file at that path",
            mandatory=False,
        ).execute()
        or ""
    ).strip()


def _review_and_install(store: VocabularyStore, name: str, preview) -> bool:
    console.print(preview_summary(preview))
    for row in preview_rows(preview):
        style = _STYLES[row["status"]]
        console.print(
            f"[{style}]{row['status'].title()} {row['fin']}: {row['detail']}[/{style}]"
        )
    if not preview.accepted:
        raise VocabularyError("no valid entries to install")
    replace = name in {item["name"] for item in store.list_sets()}
    prompt = f"Replace existing set {name!r}?" if replace else f"Install set {name!r}?"
    if not inquirer.confirm(message=prompt, default=False).execute():
        console.print(
            "[yellow]Import cancelled; existing sets were not changed.[/yellow]"
        )
        return False
    store.install(name, preview.document, replace=replace)
    console.print(f"[green]Installed vocabulary: {name}[/green]")
    return True


def _import_from_file(store: VocabularyStore) -> None:
    path = _ask_path(
        "Word list file:",
        "Tab completes paths; you can also drag a file into the terminal. "
        "Columns may be separated by tabs, semicolons, or commas.",
    )
    if not path:
        return
    name = _ask_name(default=suggest_set_name(normalize_path(path).stem))
    if not name:
        return
    overrides_path = _ask_path("Optional overrides JSON (leave blank for none):")
    console.print(_ANALYZING)
    preview = analyze_vocabulary_source(
        path, name=name, overrides=load_overrides(overrides_path or None)
    )
    _review_and_install(store, name, preview)


def _import_from_paste(store: VocabularyStore) -> None:
    text = (
        inquirer.text(
            message="Paste or type words:",
            multiline=True,
            long_instruction="One word per line: Finnish, then English, separated "
            "by a tab, semicolon, or comma. Press Esc then Enter to finish.",
            mandatory=False,
        ).execute()
        or ""
    )
    if not text.strip():
        return
    name = _ask_name()
    if not name:
        return
    console.print(_ANALYZING)
    preview = analyze_vocabulary_source(text.encode("utf-8"), name=name)
    _review_and_install(store, name, preview)


def _browse_online(
    store: VocabularyStore, repository: RemoteRepository | None = None
) -> None:
    repository = repository or RemoteRepository()
    with console.status(f"Fetching sets from {repository.repository}…"):
        sets = repository.list_sets()
    if not sets:
        console.print(f"[yellow]No sets found in {repository.repository}.[/yellow]")
        return
    installed = installed_remote_sets(store)
    labels = {"new": "", "installed": "  ✓ installed", "update": "  ↻ update available"}
    choices = [
        {
            "name": item.title + labels[remote_status(repository, item, installed)[0]],
            "value": item,
        }
        for item in sets
    ]
    item = inquirer.select(
        keybindings=NAV_KEYBINDINGS,
        message=f"Sets in {repository.repository}:",
        choices=[*choices, {"name": "Back", "value": None}],
    ).execute()
    if item is None:
        return
    _, local = remote_status(repository, item, installed)
    name = _ask_name(default=local or item.name)
    if not name:
        return
    console.print(_ANALYZING)
    preview = analyze_remote_set(
        repository, item, name=name, analyze=analyze_vocabulary_source
    )
    _review_and_install(store, name, preview)


def _update_online(
    store: VocabularyStore, repository: RemoteRepository | None = None
) -> None:
    repository = repository or RemoteRepository()
    with console.status("Checking online sets for updates…"):
        pending = find_updates(repository, store)
    if not pending:
        console.print("[green]All online sets are up to date.[/green]")
        return
    for update in pending:
        name = update.local.name
        if update.remote is None:
            console.print(
                f"[yellow]{name} is no longer in {repository.repository}; kept as is.[/yellow]"
            )
            continue
        console.print(f"\n[bold]{name}[/bold] changed online ({update.remote.path})")
        console.print(_ANALYZING)
        preview = analyze_remote_set(
            repository, update.remote, name=name, analyze=analyze_vocabulary_source
        )
        _review_and_install(store, name, preview)


def manage_vocabulary(store: VocabularyStore | None = None) -> bool:
    """Interactively import, list, select, replace, and remove vocabulary sets."""
    store = store or VocabularyStore()
    while True:
        _print_vocabulary_listing(store)
        action = inquirer.select(
            keybindings=NAV_KEYBINDINGS,
            message="Manage vocabulary:",
            choices=[
                {"name": "Import from a file", "value": "file"},
                {"name": "Paste a word list", "value": "paste"},
                {"name": "Browse online sets", "value": "browse"},
                {"name": "Update online sets", "value": "update"},
                {"name": "Select active set", "value": "select"},
                {"name": "Remove a custom set", "value": "remove"},
                {"name": "Back", "value": "back"},
            ],
        ).execute()
        if action in {None, "back"}:
            return False
        try:
            custom = [item["name"] for item in store.list_sets()]
            if action == "file":
                _import_from_file(store)
            elif action == "paste":
                _import_from_paste(store)
            elif action == "browse":
                _browse_online(store)
            elif action == "update":
                _update_online(store)
            elif action == "select":
                name = inquirer.select(
                    keybindings=NAV_KEYBINDINGS,
                    message="Select active vocabulary:",
                    choices=["default", *custom],
                ).execute()
                if name:
                    store.select(name)
                    console.print(f"[green]Selected vocabulary: {name}[/green]")
            elif action == "remove":
                if not custom:
                    console.print(
                        "[yellow]There are no custom sets to remove.[/yellow]"
                    )
                    continue
                name = inquirer.select(
                    keybindings=NAV_KEYBINDINGS,
                    message="Remove which set?",
                    choices=custom,
                ).execute()
                if (
                    name
                    and inquirer.confirm(
                        message=f"Remove {name!r}?", default=False
                    ).execute()
                ):
                    store.remove(name)
                    console.print(f"[green]Removed vocabulary: {name}[/green]")
        except (VocabularyError, OSError) as error:
            console.print(f"[red]Could not update vocabulary: {error}[/red]")
        except Exception as error:
            console.print(
                f"[red]Vocabulary model setup failed: {error}[/red]\n"
                "[yellow]Check the network, disk space, and data-directory permissions, then retry.[/yellow]"
            )
