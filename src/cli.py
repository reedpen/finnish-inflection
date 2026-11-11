"""Command-line entry point and vocabulary management commands."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version

from src.data.importer import (
    analyze_vocabulary_source,
    load_overrides,
    preview_rows,
    preview_summary,
)
from src.data.remote import (
    RemoteRepository,
    analyze_remote_set,
    find_updates,
    installed_remote_sets,
    remote_status,
)
from src.data.vocab import VocabularyError, VocabularyStore


def package_version() -> str:
    try:
        return version("finnish-inflection-cli")
    except PackageNotFoundError:
        return "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finnish-drill",
        description="Practice Finnish noun, adjective, and verb inflections.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {package_version()}"
    )
    parser.add_argument(
        "--debug", action="store_true", help="show tracebacks for troubleshooting"
    )
    commands = parser.add_subparsers(dest="command")
    vocab = commands.add_parser("vocab", help="manage custom vocabulary sets")
    actions = vocab.add_subparsers(dest="vocab_command", required=True)

    import_parser = actions.add_parser(
        "import",
        help="preview and install a word list (tab, semicolon, or comma separated)",
    )
    import_parser.add_argument(
        "name", help="set name (letters, numbers, underscores, and hyphens)"
    )
    import_parser.add_argument(
        "path", help="UTF-8 word list file, or - to read from standard input"
    )
    import_parser.add_argument(
        "--overrides",
        help="JSON mapping words to a lemma/POS or null exclusion",
    )
    import_parser.add_argument(
        "--replace", action="store_true", help="replace an existing set atomically"
    )
    import_parser.add_argument(
        "--yes", action="store_true", help="install after preview without prompting"
    )

    browse = actions.add_parser("browse", help="list sets in the online sets repository")
    browse.add_argument("--repo", help="owner/repo[@branch] to use instead of the default")

    get = actions.add_parser("get", help="preview and install a set from the online repository")
    get.add_argument("set", help="set name or path as shown by 'vocab browse'")
    get.add_argument("--name", help="local set name (defaults to the online name)")
    get.add_argument("--repo", help="owner/repo[@branch] to use instead of the default")
    get.add_argument(
        "--replace", action="store_true", help="replace an existing set with this name"
    )
    get.add_argument(
        "--yes", action="store_true", help="install after preview without prompting"
    )

    update = actions.add_parser(
        "update", help="reinstall online sets that changed in the repository"
    )
    update.add_argument("--repo", help="owner/repo[@branch] to use instead of the default")
    update.add_argument(
        "--yes", action="store_true", help="install each update without prompting"
    )

    actions.add_parser("list", help="list the built-in and custom vocabulary sets")
    select = actions.add_parser("select", help="select a set for future drills")
    select.add_argument("name", help="set name, or default")
    remove = actions.add_parser("remove", help="remove a custom set")
    remove.add_argument("name")
    return parser


def _confirm(prompt: str, *, from_terminal: bool = False) -> bool:
    """Ask yes/no; read the terminal directly when stdin carried the word list."""
    if not from_terminal:
        return input(prompt).strip().casefold() in {"y", "yes"}
    try:
        with open("/dev/tty", encoding="utf-8") as terminal:
            print(prompt, end="", flush=True)
            answer = terminal.readline()
    except OSError as exc:
        raise VocabularyError(
            "cannot ask for confirmation while reading words from standard input; "
            "add --yes"
        ) from exc
    return answer.strip().casefold() in {"y", "yes"}


def _analyze(run):
    print("Analyzing vocabulary with the Finnish morphology model…")
    try:
        return run()
    except VocabularyError:
        raise
    except Exception as exc:
        raise VocabularyError(
            "Finnish model setup failed. Check your network connection, free disk space, "
            f"and write permissions, then retry. Details: {exc}"
        ) from exc


def _review_and_install(
    store: VocabularyStore,
    name: str,
    preview,
    *,
    yes: bool,
    replace: bool,
    from_terminal: bool = False,
) -> bool:
    print(preview_summary(preview))
    for row in preview_rows(preview):
        print(f"{row['status'].title()} {row['fin']}: {row['detail']}")
    if not preview.accepted:
        raise VocabularyError("no valid entries to install")
    if not yes and not _confirm(
        "Install this vocabulary set? [y/N] ", from_terminal=from_terminal
    ):
        print("Import cancelled; no files were changed.")
        return False
    store.install(name, preview.document, replace=replace)
    print(f"Installed vocabulary: {name}")
    return True


def _run_browse(args: argparse.Namespace) -> int:
    repository = RemoteRepository(args.repo)
    sets = repository.list_sets()
    if not sets:
        print(f"No sets found in {repository.repository}.")
        return 0
    installed = installed_remote_sets(VocabularyStore())
    labels = {"new": "", "installed": "installed", "update": "update available"}
    print(f"Sets in {repository.repository}:")
    for item in sets:
        status, local = remote_status(repository, item, installed)
        note = labels[status] + (f" as {local}" if local and local != item.name else "")
        print(f"{item.name}\t{item.title}\t{note}".rstrip())
    print("Install one with: finnish-drill vocab get NAME")
    return 0


def _run_get(args: argparse.Namespace) -> int:
    store = VocabularyStore()
    repository = RemoteRepository(args.repo)
    item = repository.find(args.set)
    name = args.name or item.name
    status, local = remote_status(repository, item, installed_remote_sets(store))
    # Reinstalling the same online set under its existing name is an update.
    replace = args.replace or (status != "new" and local == name)
    preview = _analyze(lambda: analyze_remote_set(
            repository, item, name=name, analyze=analyze_vocabulary_source
        ))
    _review_and_install(store, name, preview, yes=args.yes, replace=replace)
    return 0


def _run_update(args: argparse.Namespace) -> int:
    store = VocabularyStore()
    repository = RemoteRepository(args.repo)
    pending = find_updates(repository, store)
    if not pending:
        print("All online sets are up to date.")
        return 0
    for update in pending:
        name = update.local.name
        if update.remote is None:
            print(f"{name}: no longer in {repository.repository}; kept as is.")
            continue
        print(f"\nUpdating {name} from {update.remote.path}")
        preview = _analyze(
            lambda: analyze_remote_set(
                repository,
                update.remote,
                name=name,
                analyze=analyze_vocabulary_source,
            )
        )
        _review_and_install(store, name, preview, yes=args.yes, replace=True)
    return 0


def _run_vocab(args: argparse.Namespace) -> int:
    if args.vocab_command == "browse":
        return _run_browse(args)
    if args.vocab_command == "get":
        return _run_get(args)
    if args.vocab_command == "update":
        return _run_update(args)
    store = VocabularyStore()
    if args.vocab_command == "list":
        print(
            f"default\t{'selected' if store.selected_name() is None else ''}\tbuilt-in"
        )
        for item in store.list_sets():
            state = "selected" if item["selected"] else ""
            print(f"{item['name']}\t{state}\t{item['entries']} entries")
        return 0
    if args.vocab_command == "select":
        store.select(args.name)
        print(f"Selected vocabulary: {args.name}")
        return 0
    if args.vocab_command == "remove":
        if args.name == "default":
            raise VocabularyError("the built-in default vocabulary cannot be removed")
        store.remove(args.name)
        print(f"Removed vocabulary: {args.name}")
        return 0

    overrides = load_overrides(args.overrides)
    from_stdin = args.path.strip() == "-"
    preview = _analyze(
        lambda: analyze_vocabulary_source(
            args.path, name=args.name, overrides=overrides
        )
    )
    _review_and_install(
        store,
        args.name,
        preview,
        yes=args.yes,
        replace=args.replace,
        from_terminal=from_stdin and not sys.stdin.isatty(),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "vocab":
            return _run_vocab(args)
        from src.main import main as interactive_main

        return interactive_main(debug=args.debug) or 0
    except VocabularyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
