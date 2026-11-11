"""Finding the Finnish column of a word list that has no header row."""

import pytest

from finnish_core.importer import (
    ImportPreview,
    analyze_vocabulary,
    cell_score,
    choose_columns,
    column_summary,
    detect_finnish_column,
    import_vocabulary,
    parse_rows,
    read_table,
)
from finnish_core.vocab import VocabularyError, is_known_word

REVERSED = (
    "house, talo\nroad, tie\nwe, me\nwater, vesi\nto run, juosta\n"
    "love, rakkaus\nit, se\nsix, kuusi\nstation, asema\nhotel, hotelli\n"
)
NORMAL = "".join(
    f"{fin}, {eng}\n"
    for eng, fin in (line.split(", ") for line in REVERSED.splitlines())
)


class FakeMorphology:
    """A lexicon like the real model's: unknown words get nothing, or
    themselves back untagged; some English words have weak readings."""

    LEXICON = {
        "talo": ["talo+N+Sg+Nom"],
        "tie": ["tie+N+Sg+Nom"],
        "me": ["me+Pron+Pers+Pl1+Nom"],
        "vesi": ["vesi+N+Sg+Nom"],
        "juosta": ["juosta+V+Act+InfA+Sg+Lat"],
        "rakkaus": ["rakkaus+N+Sg+Nom"],
        "se": ["se+Pron+Sg+Nom"],
        "kuusi": ["kuusi+Num+Card+Sg+Nom", "kuusi+N+Sg+Nom"],
        "asema": ["asema+N+Sg+Nom"],
        "hotelli": ["hotelli+N+Sg+Nom"],
        "koira": ["koira+N+Sg+Nom"],
        "puhua": ["puhua+V+Act+InfA+Sg+Lat"],
        "olla": ["olla+V+Act+InfA+Sg+Lat"],
        "kotona": ["kotona+Adv"],
        "radio": ["radio+N+Sg+Nom"],
        "sauna": ["sauna+N+Sg+Nom"],
        # English words the real model has readings for.
        "house": ["house+N+Sg+Nom"],
        "it": ["it+ACR+Sg+Nom"],
        "the": ["the"],
    }

    def __init__(self):
        self.calls = []

    def analyze(self, word, language):
        self.calls.append(word)
        return [(analysis, 0.0) for analysis in self.LEXICON.get(word, [])]


def guess(text, morphology=None):
    return detect_finnish_column(read_table(text).column_cells(), morphology)


def test_only_tagged_readings_that_are_not_acronyms_count_as_known():
    morphology = FakeMorphology()

    assert is_known_word("talo", morphology)
    assert is_known_word("Talo", morphology)  # tried in lower case too
    assert is_known_word("me", morphology)  # a pronoun is still Finnish
    assert not is_known_word("it", morphology)  # only an acronym
    assert not is_known_word("the", morphology)  # echoed back untagged
    assert not is_known_word("water", morphology)


def test_a_failing_model_knows_nothing():
    class Broken:
        def analyze(self, word, language):
            raise RuntimeError("no model")

    assert not is_known_word("talo", Broken())


@pytest.mark.parametrize(
    ("cell", "known", "score"),
    [
        ("talo", True, 1.0),
        ("päivä", True, 2.0),
        ("päivä", False, 1.0),
        ("to run", False, -1.0),
        ("the dog", False, -1.0),
        ("big dog", False, -0.5),
        ("olla kotona", True, 1.0),
        ("water", False, 0.0),
        ("123", True, 0.0),
    ],
)
def test_cell_scores_weigh_known_words_letters_and_english_hints(cell, known, score):
    assert cell_score(cell, lambda word: known) == score


def test_without_the_model_only_spelling_counts():
    assert cell_score("talo") == 0.0
    assert cell_score("Päivä") == 1.0
    # Decomposed ä (a + combining diaeresis) counts too.
    assert cell_score("päivä") == 1.0
    assert cell_score("To speak") == -1.0


def test_a_reversed_list_is_read_from_the_second_column():
    result = guess(REVERSED, FakeMorphology())

    assert (result.finnish, result.confident) == (1, True)
    assert result.scores[1] - result.scores[0] >= 1


def test_a_normal_list_keeps_the_first_column_confidently():
    result = guess(NORMAL, FakeMorphology())

    assert (result.finnish, result.confident) == (0, True)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("house, talo\n", id="one-row-both-known"),
        pytest.param("radio, radio\nsauna, sauna\n", id="same-words"),
        pytest.param(
            "talo, house\nwater, vesi\ntie, road\nlove, rakkaus\n", id="half-reversed"
        ),
        pytest.param("xyzzy, plugh\n", id="nothing-known"),
    ],
)
def test_close_evidence_keeps_the_first_column_but_is_unsure(text):
    result = guess(text, FakeMorphology())

    assert (result.finnish, result.confident) == (0, False)


def test_spelling_alone_can_swap_columns():
    assert (guess("to run, juosta\n").finnish, guess("to run, juosta\n").confident) == (
        1,
        True,
    )
    assert guess("dog\tpäivä\n").finnish == 1
    assert not guess("koira, dog\n").confident


def test_detection_scores_a_bounded_spread_sample():
    morphology = FakeMorphology()
    # Letters only: digits would split a cell into words.
    rows = [("".join(chr(97 + int(d)) for d in f"{i:04}"), "talo") for i in range(1000)]

    result = detect_finnish_column(rows, morphology, limit=40)

    assert result.finnish == 1
    # One lookup per distinct word: 40 sampled first cells, and "talo" once.
    assert len(set(morphology.calls)) == 41


def test_a_list_without_two_columns_has_nothing_to_decide():
    assert guess("talo,\nkoira\n", FakeMorphology()).confident


def test_column_cells_pair_what_each_choice_reads_as_finnish():
    table = read_table("puhua, to speak, to talk\nto run, juosta\nkissa\n,dog\n")

    assert table.column_cells() == [
        ("puhua", "to talk"),
        ("to run", "juosta"),
    ]


def test_parse_rows_can_read_finnish_from_the_second_column():
    text = "to speak, to talk, puhua\nhouse,talo\nkoira\n"

    rows, problems = parse_rows(text, finnish_column=1)

    assert rows == [("puhua", "to speak, to talk"), ("talo", "house")]
    assert [problem["fin"] for problem in problems] == ["koira"]
    assert parse_rows(text) == parse_rows(text, finnish_column=0)


def test_a_tab_list_reversed_ignores_extra_columns():
    rows, _ = parse_rows("dog\tkoira\tanimals\n", finnish_column=1)

    assert rows == [("koira", "dog")]


def test_a_choice_swaps_the_two_header_columns():
    text = "id;English;notes;Finnish\n1;dog;x;koira\n"

    assert parse_rows(text) == ([("koira", "dog")], [])
    assert parse_rows(text, finnish_column=1) == ([("koira", "dog")], [])
    assert parse_rows(text, finnish_column=0) == ([("dog", "koira")], [])


def test_only_the_first_or_second_column_can_be_chosen():
    with pytest.raises(VocabularyError, match="first or the second"):
        parse_rows("a,b\n", finnish_column=2)


@pytest.mark.parametrize(
    ("header", "finnish"),
    [
        ("Suomeksi;Englanniksi", 0),
        ("en;fi", 1),
        ("Gloss;Finnish word", 1),
    ],
)
def test_more_header_names_are_recognised(header, finnish):
    table = read_table(f"{header}\nx;y\n")

    assert table.header_finnish_column == finnish


def test_choose_columns_prefers_a_choice_then_the_header_then_detection():
    def never(rows):
        raise AssertionError("must not detect")

    headed = read_table("English,Finnish\ndog,koira\n")
    plain = read_table("to run, juosta\n")

    assert choose_columns(headed, 0, never) == {
        "finnish": 0,
        "source": "chosen",
        "confident": True,
    }
    assert choose_columns(headed, None, never) == {
        "finnish": 1,
        "source": "header",
        "confident": True,
    }
    assert choose_columns(plain) == {"finnish": 1, "source": "auto", "confident": True}


def test_import_reports_and_follows_the_column_decision():
    seen = []

    def analyzer(fin, eng):
        seen.append((fin, eng))
        return ("N", fin)

    preview = import_vocabulary(
        b"to run, juosta\nhouse, talo\n", analyzer=analyzer, name="x"
    )

    assert preview.columns == {"finnish": 1, "source": "auto", "confident": True}
    assert seen == [("juosta", "to run"), ("talo", "house")]

    chosen = import_vocabulary(
        b"to run, juosta\n", analyzer=lambda *_: ("N", "x"), name="x", finnish_column=0
    )
    assert chosen.columns["source"] == "chosen"
    assert chosen.accepted[0]["fin"] == "to run"


def test_hand_made_previews_default_to_the_first_column():
    preview = ImportPreview([], [], [], [], [], {})  # type: ignore[arg-type]

    assert preview.columns == {"finnish": 0, "source": "auto", "confident": True}


@pytest.mark.parametrize(
    ("columns", "text"),
    [
        (
            {"finnish": 1, "source": "header", "confident": True},
            "Finnish words read from the second column (named by the header row)",
        ),
        (
            {"finnish": 0, "source": "auto", "confident": False},
            "Finnish words read from the first column (unsure: check the words)",
        ),
        (
            {"finnish": 1, "source": "auto", "confident": True},
            "Finnish words read from the second column (detected)",
        ),
        (
            {"finnish": 0, "source": "chosen", "confident": True},
            "Finnish words read from the first column (as chosen)",
        ),
    ],
)
def test_column_summary(columns, text):
    assert column_summary(columns) == text


# --- With the real model -----------------------------------------------------


@pytest.fixture(scope="module")
def real_morphology():
    from finnish_core.morphology import UralicNlpAdapter

    return UralicNlpAdapter()


@pytest.mark.integration
def test_real_model_reads_a_reversed_list_from_the_second_column(real_morphology):
    preview = analyze_vocabulary(REVERSED.encode(), real_morphology, name="x")

    assert preview.columns == {"finnish": 1, "source": "auto", "confident": True}
    accepted = {item["fin"]: item["eng"] for item in preview.accepted}
    assert accepted["talo"] == "house" and accepted["juosta"] == "to run"
    assert "house" not in accepted
    # Only the pronouns are left for review.
    assert {item["fin"] for item in preview.ambiguous} == {"me", "se"}


@pytest.mark.integration
def test_real_model_keeps_a_normal_list_confidently(real_morphology):
    preview = analyze_vocabulary(NORMAL.encode(), real_morphology, name="x")

    assert preview.columns == {"finnish": 0, "source": "auto", "confident": True}
    assert {item["fin"] for item in preview.ambiguous} == {"me", "se"}


@pytest.mark.integration
def test_real_model_follows_a_reversed_header(real_morphology):
    preview = analyze_vocabulary(
        b'English;Finnish\nhouse;talo\n"to speak, to talk";puhua\n',
        real_morphology,
        name="x",
    )

    assert preview.columns == {"finnish": 1, "source": "header", "confident": True}
    assert [(item["fin"], item["eng"]) for item in preview.accepted] == [
        ("talo", "house"),
        ("puhua", "to speak, to talk"),
    ]


@pytest.mark.integration
@pytest.mark.parametrize(
    "text",
    [
        pytest.param("house, talo\n", id="one-row-both-known"),
        pytest.param(
            "talo, house\nwater, vesi\ntie, road\nlove, rakkaus\n"
            "kuusi, six\nstation, asema\n",
            id="half-reversed",
        ),
        pytest.param("radio, radio\nsauna, sauna\npizza, pizza\n", id="loanwords"),
    ],
)
def test_real_model_is_unsure_about_close_lists(real_morphology, text):
    preview = analyze_vocabulary(text.encode(), real_morphology, name="x")

    assert preview.columns == {"finnish": 0, "source": "auto", "confident": False}


@pytest.mark.integration
@pytest.mark.parametrize(
    "text",
    [
        pytest.param("house, talo\nwater, vesi\n", id="two-rows"),
        pytest.param("to speak, to talk, puhua\nbeautiful, kaunis\n", id="commas"),
        pytest.param("dog\tkoira\tanimals\nday\tpäivä\tx\n", id="tabs"),
    ],
)
def test_real_model_swaps_short_reversed_lists(real_morphology, text):
    preview = analyze_vocabulary(text.encode(), real_morphology, name="x")

    assert preview.columns["finnish"] == 1 and preview.columns["confident"]


@pytest.mark.integration
def test_real_model_obeys_an_explicit_choice(real_morphology):
    preview = analyze_vocabulary(
        REVERSED.encode(), real_morphology, name="x", finnish_column=0
    )

    assert preview.columns == {"finnish": 0, "source": "chosen", "confident": True}
    assert [item["fin"] for item in preview.accepted] == ["house"]
