"""Shared terminal interaction for all practice drills."""

from dataclasses import dataclass

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from finnish_cli.interaction import InputAction, parse_input
from finnish_core.hints import check_answer, get_hint
from finnish_core.questions import Question
from finnish_core.session import (
    AnswerOutcome,
    OutcomeAction,
    PracticeSession,
    SessionAction,
)


console = Console()
session = PromptSession(history=InMemoryHistory())
COMMAND_HELP = "h/hint · s/skip or Enter · b/back · q/quit · Ctrl+C back · Ctrl+D quit"


@dataclass(frozen=True)
class SessionResult:
    action: SessionAction
    summary: str


def clear_terminal(output: Console | None = None) -> None:
    """Clear terminals without writing control codes to redirected output."""
    output = output or console
    if output.is_terminal:
        output.clear()


def ask_question(
    question: Question,
    *,
    prompt_session: PromptSession | None = None,
    output: Console | None = None,
) -> tuple[AnswerOutcome, str]:
    """Ask one question using the command vocabulary shared by every drill."""
    prompt_session = prompt_session or session
    output = output or console
    output.print(
        f"\n[bold blue]{question.kind}:[/bold blue] {question.word} ({question.translation})"
    )
    output.print(f"[bold blue]Target:[/bold blue] {question.target}")
    output.print(f"[dim]{COMMAND_HELP}[/dim]")

    hints = 0
    attempts = 0
    last_attempt = ""
    while True:
        try:
            raw = prompt_session.prompt("Answer: ")
        except KeyboardInterrupt:
            return AnswerOutcome.back(attempts, hints), "Returning to the drill menu."
        except EOFError:
            return AnswerOutcome.quit(attempts, hints), "Goodbye."

        value = "" if raw is None else raw.strip()
        action = parse_input(value)
        if action == InputAction.HINT:
            hints += 1
            output.print(
                f"[yellow]Hint: {get_hint(hints, last_attempt, question.answers)}[/yellow]"
            )
        elif action == InputAction.SKIP:
            return AnswerOutcome.skipped(attempts, hints), _answer_message(question)
        elif action == InputAction.BACK:
            return AnswerOutcome.back(attempts, hints), "Returning to the drill menu."
        elif action == InputAction.QUIT:
            return AnswerOutcome.quit(attempts, hints), "Goodbye."
        elif check_answer(value, question.answers):
            return AnswerOutcome.correct(
                attempts + 1, hints
            ), "[bold green]Correct![/bold green] 🎉"
        else:
            attempts += 1
            last_attempt = value
            output.print("[red]Incorrect, try again.[/red]")


def _answer_message(question: Question) -> str:
    return (
        f"The correct form(s): [bold green]{', '.join(question.answers)}[/bold green]"
    )


def run_practice_session(
    questions: list[Question],
    length: int | None,
    title: str,
) -> SessionResult:
    """Run a bounded or endless practice session and display its outcome."""
    practice = PracticeSession(questions, length)
    feedback = ""
    exit_action = SessionAction.COMPLETE
    while question := practice.next_question():
        clear_terminal()
        console.print(f"[bold magenta]--- {title} ---[/bold magenta]")
        console.print(f"[dim]Progress: {practice.progress}[/dim]")
        if feedback:
            console.print(feedback)
        outcome, feedback = ask_question(question)
        practice.record(outcome)
        if outcome.action in {OutcomeAction.BACK, OutcomeAction.QUIT}:
            exit_action = SessionAction(outcome.action.value)
            break

    summary = practice.summary(exit_action)
    console.print(f"\n[bold cyan]{summary}[/bold cyan]")
    return SessionResult(exit_action, summary)
