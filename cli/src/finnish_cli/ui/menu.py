"""Interactive configuration and navigation for practice drills."""

from collections.abc import Callable

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console

from finnish_core.paradigm import engine_lookup
from finnish_core.questions import (
    build_noun_pool,
    build_participle_pool,
    build_verb_pool,
)
from finnish_core.session import SessionAction
from finnish_core.settings import DrillSettings, get_preset
from finnish_core.forms import (
    NOUN_CASES,
    NOUN_NUMBERS,
    VERB_PARTICIPLES,
    VERB_PERSONS,
    VERB_TENSES_MOODS,
    VERB_TYPES,
)
from finnish_cli.engine import ENGINE
from finnish_cli.interaction import NavigationAction
from finnish_cli.settings_store import SettingsStore
from finnish_cli.store import get_nouns_list, get_verbs_by_type, get_verbs_list
from finnish_cli.ui.drill import clear_terminal, run_practice_session
from finnish_cli.ui.keys import NAV_KEYBINDINGS
from finnish_cli.ui.vocabulary import manage_vocabulary


console = Console()
settings_store = SettingsStore()
ALL_SENTINEL = "__ALL__"
FORMS = engine_lookup(ENGINE)


def checkbox_with_all(
    message: str, options: list[str], selected: list[str] | None = None
) -> list[str] | None:
    selected = selected or []
    choices = [
        {
            "name": "All",
            "value": ALL_SENTINEL,
            "enabled": set(selected) == set(options),
        },
        Separator("─" * 20),
        *(
            {"name": option, "value": option, "enabled": option in selected}
            for option in options
        ),
    ]
    result = inquirer.checkbox(
        keybindings=NAV_KEYBINDINGS,
        message=message,
        choices=choices,
        validate=lambda selected: len(selected) > 0,
        invalid_message="Select at least one option",
    ).execute()
    if result is None:
        return None
    return list(options) if ALL_SENTINEL in result else result


def run_menu():
    while True:
        clear_terminal(console)
        console.print("[bold blue]==============================[/bold blue]")
        console.print("[bold cyan]   Finnish Inflection Drill   [/bold cyan]")
        console.print("[bold blue]==============================[/bold blue]\n")
        console.print("[dim]Ctrl+C or Ctrl+D exits from the main menu.[/dim]")
        recent = settings_store.load_recent()
        choices = [
            {
                "name": "Beginner nouns — quick start",
                "value": lambda: _run_direct(get_preset("noun", "beginner")),
            },
            {
                "name": "Beginner verbs — quick start",
                "value": lambda: _run_direct(get_preset("verb", "beginner")),
            },
        ]
        if recent:
            choices.append(
                {
                    "name": f"Resume last {recent.drill} session",
                    "value": lambda: _run_direct(recent),
                }
            )
        choices.extend(
            [
                Separator("─" * 20),
                {"name": "Configure noun practice", "value": setup_noun_drill},
                {"name": "Configure verb practice", "value": setup_verb_drill},
                {
                    "name": "Configure participle practice",
                    "value": setup_participle_drill,
                },
                {"name": "Manage vocabulary", "value": manage_vocabulary},
                {"name": "Reset all saved preferences", "value": _reset_all},
                {"name": "Exit", "value": None},
            ]
        )
        try:
            choice = inquirer.select(
                keybindings=NAV_KEYBINDINGS,
                message="Choose a drill:",
                choices=choices,
            ).execute()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Näkemiin![/yellow]")
            return
        if choice is None:
            console.print("[yellow]Näkemiin![/yellow]")
            return
        try:
            if choice():
                console.print("[yellow]Näkemiin![/yellow]")
                return
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Returning to the main menu.[/yellow]")
        except Exception as error:
            console.print(f"\n[red]Could not run this drill: {error}[/red]")
            console.input("Press Enter to return to the main menu...")


def _choose_setup(drill: str, customize: Callable[..., DrillSettings | None]):
    previous = settings_store.load(drill)
    if previous is None and settings_store.has_saved(drill):
        console.print(
            "[yellow]The saved setup is invalid or from an older version. "
            "Choose Reset saved setup or create a new configuration.[/yellow]"
        )
    choices = [{"name": "Beginner quick start (10 questions)", "value": "beginner"}]
    choices.append({"name": "Focused practice (20 questions)", "value": "focused"})
    if previous:
        choices.append({"name": "Repeat last setup", "value": "last"})
        choices.append({"name": "Edit last setup", "value": "edit"})
    choices.extend(
        [
            {"name": "Customize", "value": "custom"},
            {"name": "Reset saved setup", "value": "reset"},
            {"name": "Back", "value": "back"},
        ]
    )
    action = inquirer.select(
        message="Choose a setup:", choices=choices, keybindings=NAV_KEYBINDINGS
    ).execute()
    if action in (None, "back"):
        return None
    if action == "reset":
        settings_store.reset(drill)
        console.print("[green]Saved setup reset.[/green]")
        return None
    if action == "last":
        configuration = previous
    elif action == "edit":
        configuration = customize(previous)
    elif action in {"beginner", "focused"}:
        configuration = get_preset(drill, action)
    else:
        configuration = customize()
    return configuration


def _session_length(initial: int | None = 10) -> int | None:
    value = inquirer.select(
        keybindings=NAV_KEYBINDINGS,
        message="Session length:",
        choices=[
            {"name": "10 questions", "value": 10},
            {"name": "20 questions", "value": 20},
            {"name": "50 questions", "value": 50},
            {"name": "Endless", "value": None},
        ],
        default=initial,
    ).execute()
    return value


def _ids(mapping: dict, labels: list[str]) -> list[str]:
    return [str(mapping[label]) for label in labels]


def _labels(mapping: dict, stable_ids: list[str]) -> list[str]:
    wanted = set(stable_ids)
    return [label for label, stable_id in mapping.items() if str(stable_id) in wanted]


def _noun_configuration(initial: DrillSettings | None = None):
    selections = initial.selections if initial else {}
    cases = checkbox_with_all(
        "Select noun cases:",
        list(NOUN_CASES),
        _labels(NOUN_CASES, selections.get("cases", [])),
    )
    if not cases:
        return None
    numbers = checkbox_with_all(
        "Select numbers:",
        list(NOUN_NUMBERS),
        _labels(NOUN_NUMBERS, selections.get("numbers", [])),
    )
    if not numbers:
        return None
    return DrillSettings(
        "noun",
        {"cases": _ids(NOUN_CASES, cases), "numbers": _ids(NOUN_NUMBERS, numbers)},
        _session_length(initial.session_length if initial else 10),
    )


def _verb_configuration(initial: DrillSettings | None = None):
    selections = initial.selections if initial else {}
    types = checkbox_with_all(
        "Select verb types:",
        list(VERB_TYPES),
        _labels(VERB_TYPES, selections.get("types", [])),
    )
    if not types:
        return None
    tenses = checkbox_with_all(
        "Select tenses and moods:",
        list(VERB_TENSES_MOODS),
        _labels(VERB_TENSES_MOODS, selections.get("tenses", [])),
    )
    if not tenses:
        return None
    persons = checkbox_with_all(
        "Select persons:",
        list(VERB_PERSONS),
        _labels(VERB_PERSONS, selections.get("persons", [])),
    )
    if not persons:
        return None
    return DrillSettings(
        "verb",
        {
            "types": _ids(VERB_TYPES, types),
            "tenses": _ids(VERB_TENSES_MOODS, tenses),
            "persons": _ids(VERB_PERSONS, persons),
        },
        _session_length(initial.session_length if initial else 10),
    )


def _participle_configuration(initial: DrillSettings | None = None):
    selections = initial.selections if initial else {}
    participles = checkbox_with_all(
        "Select participle types:",
        list(VERB_PARTICIPLES),
        _labels(VERB_PARTICIPLES, selections.get("participles", [])),
    )
    if not participles:
        return None
    cases = checkbox_with_all(
        "Select cases:",
        list(NOUN_CASES),
        _labels(NOUN_CASES, selections.get("cases", [])),
    )
    if not cases:
        return None
    numbers = checkbox_with_all(
        "Select numbers:",
        list(NOUN_NUMBERS),
        _labels(NOUN_NUMBERS, selections.get("numbers", [])),
    )
    if not numbers:
        return None
    return DrillSettings(
        "participle",
        {
            "participles": _ids(VERB_PARTICIPLES, participles),
            "cases": _ids(NOUN_CASES, cases),
            "numbers": _ids(NOUN_NUMBERS, numbers),
        },
        _session_length(initial.session_length if initial else 10),
    )


def _run_pool(configuration, builder, title: str) -> NavigationAction:
    try:
        with console.status("[green]Preparing playable questions...[/green]"):
            pool = builder(configuration)
    except Exception as error:
        console.print(
            f"[red]Could not prepare questions: {error}[/red]\n"
            "[yellow]Check the selected filters or model installation, then try again.[/yellow]"
        )
        console.input("Press Enter to reconfigure...")
        return NavigationAction.RECONFIGURE
    if not pool:
        console.print(
            "[yellow]No playable questions match that setup. Try broader filters.[/yellow]"
        )
        console.input("Press Enter to return...")
        return NavigationAction.RECONFIGURE
    settings_saved = False
    while True:
        result = run_practice_session(pool, configuration.session_length, title)
        if not settings_saved:
            settings_store.save(configuration)
            settings_saved = True
        action = inquirer.select(
            keybindings=NAV_KEYBINDINGS,
            message="What next?",
            choices=_post_session_choices(result.action),
        ).execute()
        if action != NavigationAction.REPLAY:
            return action or NavigationAction.MENU


def _post_session_choices(action: SessionAction) -> list[dict]:
    choices = {
        NavigationAction.REPLAY: {
            "name": "Replay this setup",
            "value": NavigationAction.REPLAY,
        },
        NavigationAction.RECONFIGURE: {
            "name": "Reconfigure",
            "value": NavigationAction.RECONFIGURE,
        },
        NavigationAction.MENU: {"name": "Main menu", "value": NavigationAction.MENU},
        NavigationAction.QUIT: {"name": "Quit", "value": NavigationAction.QUIT},
    }
    order = {
        SessionAction.COMPLETE: (
            NavigationAction.REPLAY,
            NavigationAction.RECONFIGURE,
            NavigationAction.MENU,
            NavigationAction.QUIT,
        ),
        SessionAction.BACK: (
            NavigationAction.RECONFIGURE,
            NavigationAction.REPLAY,
            NavigationAction.MENU,
            NavigationAction.QUIT,
        ),
        SessionAction.QUIT: (
            NavigationAction.QUIT,
            NavigationAction.MENU,
            NavigationAction.REPLAY,
            NavigationAction.RECONFIGURE,
        ),
    }[SessionAction(action)]
    return [choices[value] for value in order]


def _pool_size(configuration: DrillSettings) -> int:
    return max(20, configuration.session_length or 100)


def _noun_pool(settings):
    return build_noun_pool(
        get_nouns_list(),
        _labels(NOUN_CASES, settings.selections.get("cases", [])),
        _labels(NOUN_NUMBERS, settings.selections.get("numbers", [])),
        FORMS,
        max_questions=_pool_size(settings),
    )


def _verb_pool(settings):
    types = [int(value) for value in settings.selections.get("types", [])]
    vocabulary = get_verbs_by_type(types) if types else get_verbs_list()
    return build_verb_pool(
        vocabulary,
        _labels(VERB_TENSES_MOODS, settings.selections.get("tenses", [])),
        _labels(VERB_PERSONS, settings.selections.get("persons", [])),
        FORMS,
        max_questions=_pool_size(settings),
    )


def _participle_pool(settings):
    return build_participle_pool(
        get_verbs_list(),
        _labels(VERB_PARTICIPLES, settings.selections.get("participles", [])),
        _labels(NOUN_CASES, settings.selections.get("cases", [])),
        _labels(NOUN_NUMBERS, settings.selections.get("numbers", [])),
        FORMS,
        max_questions=_pool_size(settings),
    )


DRILLS = {
    "noun": (_noun_configuration, _noun_pool, "Noun Drill"),
    "verb": (_verb_configuration, _verb_pool, "Verb Drill"),
    "participle": (_participle_configuration, _participle_pool, "Participle Drill"),
}


def _run_direct(configuration: DrillSettings) -> bool:
    customize, builder, title = DRILLS[configuration.drill]
    action = _run_pool(configuration, builder, title)
    if action == NavigationAction.RECONFIGURE:
        return _setup_drill(configuration.drill)
    return action == NavigationAction.QUIT


def _setup_drill(drill: str) -> bool:
    customize, builder, title = DRILLS[drill]
    while configuration := _choose_setup(drill, customize):
        action = _run_pool(configuration, builder, title)
        if action == NavigationAction.QUIT:
            return True
        if action != NavigationAction.RECONFIGURE:
            return False
    return False


def setup_noun_drill() -> bool:
    return _setup_drill("noun")


def setup_verb_drill() -> bool:
    return _setup_drill("verb")


def setup_participle_drill() -> bool:
    return _setup_drill("participle")


def _reset_all() -> bool:
    settings_store.reset()
    console.print("[green]All saved preferences were reset.[/green]")
    console.input("Press Enter to continue...")
    return False
