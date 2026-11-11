"""Question scheduling and outcome accounting for practice sessions."""

import random
from dataclasses import dataclass
from enum import StrEnum

from finnish_core.questions import Question


class OutcomeAction(StrEnum):
    CORRECT = "correct"
    SKIP = "skip"
    BACK = "back"
    QUIT = "quit"


class SessionAction(StrEnum):
    COMPLETE = "complete"
    BACK = "back"
    QUIT = "quit"


@dataclass(frozen=True)
class AnswerOutcome:
    action: OutcomeAction
    attempts: int = 0
    hints: int = 0

    @classmethod
    def correct(cls, attempts: int = 1, hints: int = 0):
        return cls(OutcomeAction.CORRECT, attempts, hints)

    @classmethod
    def skipped(cls, attempts: int = 0, hints: int = 0):
        return cls(OutcomeAction.SKIP, attempts, hints)

    @classmethod
    def back(cls, attempts: int = 0, hints: int = 0):
        return cls(OutcomeAction.BACK, attempts, hints)

    @classmethod
    def quit(cls, attempts: int = 0, hints: int = 0):
        return cls(OutcomeAction.QUIT, attempts, hints)


@dataclass
class SessionStats:
    answered: int = 0
    first_try_correct: int = 0
    eventual_correct: int = 0
    incorrect_attempts: int = 0
    hints: int = 0
    skipped: int = 0


class PracticeSession:
    """Draw questions in shuffled cycles and collect session statistics."""

    def __init__(self, questions, limit: int | None = 10, rng=None):
        if not questions:
            raise ValueError("The selected filters produced no playable questions.")
        if limit is not None and limit < 1:
            raise ValueError("Session length must be at least one question.")
        self.questions = list(questions)
        self.limit = limit
        self.rng = rng or random.Random()
        self.stats = SessionStats()
        self._drawn = 0
        self._remaining = []
        self._last_id = None

    @property
    def progress(self) -> str:
        total = "∞" if self.limit is None else str(self.limit)
        current = self._drawn or self.stats.answered
        return f"{current}/{total}"

    def next_question(self) -> Question | None:
        if self.limit is not None and self._drawn >= self.limit:
            return None
        if not self._remaining:
            self._remaining = list(self.questions)
            self.rng.shuffle(self._remaining)
            if len(self._remaining) > 1 and self._remaining[-1].id == self._last_id:
                self._remaining[0], self._remaining[-1] = (
                    self._remaining[-1],
                    self._remaining[0],
                )
        question = self._remaining.pop()
        self._last_id = question.id
        self._drawn += 1
        return question

    def record(self, outcome: AnswerOutcome) -> None:
        self.stats.hints += outcome.hints
        self.stats.incorrect_attempts += max(
            0,
            outcome.attempts - 1
            if outcome.action == OutcomeAction.CORRECT
            else outcome.attempts,
        )
        if outcome.action in {OutcomeAction.BACK, OutcomeAction.QUIT}:
            return
        self.stats.answered += 1
        if outcome.action == OutcomeAction.CORRECT:
            if outcome.attempts == 1:
                self.stats.first_try_correct += 1
            else:
                self.stats.eventual_correct += 1
        else:
            self.stats.skipped += 1

    def summary(self, action: SessionAction = SessionAction.COMPLETE) -> str:
        stats = self.stats
        heading = {
            SessionAction.COMPLETE: "Session complete",
            SessionAction.BACK: "Session ended early",
            SessionAction.QUIT: "Session ended",
        }[action]
        return (
            f"{heading} — "
            f"Answered: {stats.answered} | First try: {stats.first_try_correct} | "
            f"After retries: {stats.eventual_correct} | "
            f"Retries: {stats.incorrect_attempts} | Hints: {stats.hints} | "
            f"Skipped: {stats.skipped}"
        )
