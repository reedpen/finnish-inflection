"""Interactive vocabulary-set management."""

from InquirerPy import inquirer
from rich.console import Console

from src.data.importer import (
    analyze_vocabulary_source,
    load_overrides,
    preview_rows,
    preview_summary,
)
from src.data.vocab import VocabularyError, VocabularyStore
from src.ui.keys import NAV_KEYBINDINGS


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


def _import_vocabulary_interactively(store: VocabularyStore) -> None:
    name = (inquirer.text(message="Set name:").execute() or "").strip()
    if not name:
        return
    path = (inquirer.text(message="CSV or text file path:").execute() or "").strip()
    if not path:
        return
    overrides_path = (
        inquirer.text(
            message="Optional overrides JSON path (leave blank for none):"
        ).execute()
        or ""
    ).strip()
    console.print("[cyan]Analyzing vocabulary and checking generated forms…[/cyan]")
    preview = analyze_vocabulary_source(
        path,
        name=name,
        overrides=load_overrides(overrides_path or None),
    )
    console.print(preview_summary(preview))
    styles = {
        "accepted": "green",
        "corrected": "cyan",
        "ambiguous": "yellow",
        "rejected": "red",
        "excluded": "dim",
    }
    for row in preview_rows(preview):
        style = styles[row["status"]]
        console.print(
            f"[{style}]{row['status'].title()} {row['fin']}: {row['detail']}[/{style}]"
        )
    if not preview.accepted:
        raise VocabularyError("no valid entries to install")
    existing = {item["name"] for item in store.list_sets()}
    replace = name in existing
    prompt = f"Replace existing set {name!r}?" if replace else f"Install set {name!r}?"
    if not inquirer.confirm(message=prompt, default=False).execute():
        console.print(
            "[yellow]Import cancelled; existing sets were not changed.[/yellow]"
        )
        return
    store.install(name, preview.document, replace=replace)
    console.print(f"[green]Installed vocabulary: {name}[/green]")


def manage_vocabulary(store: VocabularyStore | None = None) -> bool:
    """Interactively import, list, select, replace, and remove vocabulary sets."""
    store = store or VocabularyStore()
    while True:
        _print_vocabulary_listing(store)
        action = inquirer.select(
            keybindings=NAV_KEYBINDINGS,
            message="Manage vocabulary:",
            choices=[
                {"name": "Import or replace a set", "value": "import"},
                {"name": "Select active set", "value": "select"},
                {"name": "Remove a custom set", "value": "remove"},
                {"name": "Back", "value": "back"},
            ],
        ).execute()
        if action in {None, "back"}:
            return False
        try:
            custom = [item["name"] for item in store.list_sets()]
            if action == "import":
                _import_vocabulary_interactively(store)
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
