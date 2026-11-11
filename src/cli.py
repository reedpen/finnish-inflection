"""Command-line entry point and vocabulary management commands."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from src.data.importer import (
    analyze_vocabulary_source,
    load_overrides,
    preview_rows,
    preview_summary,
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
        "import", help="preview and install a UTF-8 CSV or text file"
    )
    import_parser.add_argument(
        "name", help="set name (letters, numbers, underscores, and hyphens)"
    )
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument(
        "--overrides",
        type=Path,
        help="JSON mapping words to a lemma/POS or null exclusion",
    )
    import_parser.add_argument(
        "--replace", action="store_true", help="replace an existing set atomically"
    )
    import_parser.add_argument(
        "--yes", action="store_true", help="install after preview without prompting"
    )

    actions.add_parser("list", help="list the built-in and custom vocabulary sets")
    select = actions.add_parser("select", help="select a set for future drills")
    select.add_argument("name", help="set name, or default")
    remove = actions.add_parser("remove", help="remove a custom set")
    remove.add_argument("name")
    return parser


def _run_vocab(args: argparse.Namespace) -> int:
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
    print("Analyzing vocabulary with the Finnish morphology model…")
    try:
        preview = analyze_vocabulary_source(
            args.path,
            name=args.name,
            overrides=overrides,
        )
    except VocabularyError:
        raise
    except Exception as exc:
        raise VocabularyError(
            "Finnish model setup failed. Check your network connection, free disk space, "
            f"and write permissions, then retry. Details: {exc}"
        ) from exc
    print(preview_summary(preview))
    for row in preview_rows(preview):
        print(f"{row['status'].title()} {row['fin']}: {row['detail']}")
    if not preview.accepted:
        raise VocabularyError("no valid entries to install")
    if not args.yes and input(
        "Install this vocabulary set? [y/N] "
    ).strip().casefold() not in {"y", "yes"}:
        print("Import cancelled; no files were changed.")
        return 0
    store.install(args.name, preview.document, replace=args.replace)
    print(f"Installed vocabulary: {args.name}")
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
