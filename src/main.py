import os

os.environ["INQUIRERPY_MOUSE_SUPPORT"] = "true"

from rich.console import Console

# Redirect stdout temporarily during uralicNLP initialization if needed
console = Console()


def main(*, debug: bool = False):
    try:
        # Import inside try block so we can see loading message
        from src.data.vocab import load_book_of_mormon_vocab
        from src.nlp.engine import ensure_model_downloaded
        from src.ui.menu import run_menu

        with console.status(
            "[bold green]Loading NLP model & vocabulary...[/bold green]", spinner="dots"
        ):
            ensure_model_downloaded("fin")
            nouns, verbs = load_book_of_mormon_vocab()

        console.print(
            f"[dim]Loaded {len(nouns)} nouns/adjectives and {len(verbs)} verbs.[/dim]"
        )
        print("\n")
        run_menu()

    except KeyboardInterrupt:
        console.print("\n[yellow]Näkemiin![/yellow]")
        return 0
    except Exception as e:
        console.print("[bold red]Finnish Drill could not start.[/bold red]")
        console.print(str(e))
        console.print(
            "[yellow]Check your network connection, free disk space, and write "
            "permissions for the UralicNLP data directory, then retry.[/yellow]"
        )
        console.print(
            "[dim]Run with --debug or FINNISH_DRILL_DEBUG=1 for a traceback.[/dim]"
        )
        if debug or os.environ.get("FINNISH_DRILL_DEBUG") == "1":
            console.print_exception()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
