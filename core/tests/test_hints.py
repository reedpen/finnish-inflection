from finnish_core.hints import check_answer, get_hint


def test_answers_match_ignoring_case_and_surrounding_space():
    assert check_answer("  Taloissa ", ["taloissa"])
    assert check_answer("lapsissa", ["lapsissa", "lapsisa"])
    assert not check_answer("taloisa", ["taloissa"])


def test_hint_reveals_one_more_letter_without_an_attempt():
    assert get_hint(2, "", ["taloissa"]) == "ta______  (8 letters)"


def test_hint_points_at_the_first_wrong_letter_of_the_closest_answer():
    assert get_hint(1, "taloisa", ["kissa", "taloissa"]) == "'a' at position 7 is wrong"
