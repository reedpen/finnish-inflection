from finnish_cli.interaction import InputAction, parse_input
from finnish_core.questions import Question
from finnish_cli.ui.drill import ask_question, clear_terminal


class FakePrompt:
    def __init__(self, replies):
        self.replies = iter(replies)

    def prompt(self, _message):
        reply = next(self.replies)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class FakeOutput:
    def __init__(self):
        self.messages = []
        self.is_terminal = False
        self.was_cleared = False

    def print(self, message):
        self.messages.append(message)

    def clear(self):
        self.was_cleared = True


QUESTION = Question("noun:talo", "Word", "talo", "house", "Partitive", ("taloa",))


def test_drill_commands_have_consistent_long_and_short_aliases():
    assert parse_input("h") == InputAction.HINT
    assert parse_input("hint") == InputAction.HINT
    assert parse_input("") == InputAction.SKIP
    assert parse_input("s") == InputAction.SKIP
    assert parse_input("skip") == InputAction.SKIP
    assert parse_input("b") == InputAction.BACK
    assert parse_input("back") == InputAction.BACK
    assert parse_input("q") == InputAction.QUIT
    assert parse_input("quit") == InputAction.QUIT


def test_an_answer_that_starts_with_a_command_letter_is_still_an_answer():
    assert parse_input("haluan") == InputAction.ANSWER


def test_question_tracks_incorrect_attempt_hint_and_eventual_correct_answer():
    output = FakeOutput()
    outcome, _ = ask_question(
        QUESTION,
        prompt_session=FakePrompt(["wrong", "hint", "taloa"]),
        output=output,
    )

    assert outcome.action == "correct"
    assert outcome.attempts == 2
    assert outcome.hints == 1
    assert any("Incorrect" in message for message in output.messages)
    assert any("Hint" in message for message in output.messages)


def test_skip_reveals_answer_and_back_and_quit_are_distinct():
    skipped, message = ask_question(
        QUESTION, prompt_session=FakePrompt(["wrong", "skip"]), output=FakeOutput()
    )
    backed, _ = ask_question(
        QUESTION, prompt_session=FakePrompt(["back"]), output=FakeOutput()
    )
    quit_, _ = ask_question(
        QUESTION, prompt_session=FakePrompt(["quit"]), output=FakeOutput()
    )

    assert skipped.action == "skip"
    assert skipped.attempts == 1
    assert "taloa" in message
    assert backed.action == "back"
    assert quit_.action == "quit"


def test_interrupt_returns_back_and_eof_quits():
    interrupted, _ = ask_question(
        QUESTION, prompt_session=FakePrompt([KeyboardInterrupt()]), output=FakeOutput()
    )
    eof, _ = ask_question(
        QUESTION, prompt_session=FakePrompt([EOFError()]), output=FakeOutput()
    )

    assert interrupted.action == "back"
    assert eof.action == "quit"


def test_redirected_output_is_not_cleared():
    output = FakeOutput()

    clear_terminal(output)

    assert output.was_cleared is False
