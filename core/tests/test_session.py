import random

from finnish_core.questions import Question
from finnish_core.session import AnswerOutcome, PracticeSession, SessionAction


def question(number):
    return Question(str(number), "Word", f"word-{number}", "", "target", ("answer",))


def test_bounded_session_does_not_repeat_and_stops_at_limit():
    session = PracticeSession(
        [question(1), question(2), question(3)], limit=3, rng=random.Random(2)
    )

    drawn = [session.next_question(), session.next_question(), session.next_question()]

    assert len({item.id for item in drawn}) == 3
    assert session.next_question() is None


def test_endless_session_avoids_an_immediate_repeat_between_cycles():
    session = PracticeSession(
        [question(1), question(2)], limit=None, rng=random.Random(4)
    )

    drawn = [session.next_question() for _ in range(6)]

    assert all(left.id != right.id for left, right in zip(drawn, drawn[1:]))


def test_session_summary_tracks_learning_outcomes():
    session = PracticeSession([question(1), question(2), question(3)], limit=3)
    session.record(AnswerOutcome.correct(attempts=2, hints=1))
    session.record(AnswerOutcome.correct(attempts=1))
    session.record(AnswerOutcome.skipped(attempts=2, hints=1))

    assert session.stats.answered == 3
    assert session.stats.first_try_correct == 1
    assert session.stats.eventual_correct == 1
    assert session.stats.incorrect_attempts == 3
    assert session.stats.hints == 2
    assert session.stats.skipped == 1
    assert session.progress == "3/3"
    assert "First try: 1" in session.summary()
    assert "After retries: 1" in session.summary()


def test_early_exit_preserves_attempts_and_hints_without_counting_an_answer():
    session = PracticeSession([question(1)], limit=1)

    session.record(AnswerOutcome.back(attempts=2, hints=1))

    assert session.stats.answered == 0
    assert session.stats.incorrect_attempts == 2
    assert session.stats.hints == 1


def test_summary_describes_completion_and_early_exit_accurately():
    session = PracticeSession([question(1)], limit=1)

    assert session.summary(SessionAction.COMPLETE).startswith("Session complete")
    assert session.summary(SessionAction.BACK).startswith("Session ended early")
    assert session.summary(SessionAction.QUIT).startswith("Session ended")
