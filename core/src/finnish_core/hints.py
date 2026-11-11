"""Answer checking and progressive hints."""

from collections.abc import Sequence


def check_answer(value: str, answers: Sequence[str]) -> bool:
    """Whether a typed answer matches any accepted form, ignoring case and edges."""
    typed = value.strip().casefold()
    return any(typed == answer.casefold() for answer in answers)


def get_hint(
    hint_level: int, last_attempt: str, answers: list[str] | tuple[str, ...]
) -> str:
    """Return a progressive hint, using the answer closest to the last attempt."""
    answer = answers[0]
    if last_attempt:
        best_answer = answers[0]
        best_prefix_len = 0
        for candidate in answers:
            prefix_len = 0
            for actual, expected in zip(last_attempt.casefold(), candidate.casefold()):
                if actual != expected:
                    break
                prefix_len += 1
            if prefix_len > best_prefix_len:
                best_prefix_len = prefix_len
                best_answer = candidate
        if len(last_attempt) > best_prefix_len:
            return f"'{last_attempt[best_prefix_len]}' at position {best_prefix_len + 1} is wrong"
        answer = best_answer
    reveal_count = min(hint_level, len(answer))
    return f"{answer[:reveal_count]}{'_' * (len(answer) - reveal_count)}  ({len(answer)} letters)"
