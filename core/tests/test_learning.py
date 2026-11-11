import random
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Rating

from finnish_core.learning import (
    Attempt,
    CardState,
    Mastery,
    PlanSettings,
    ReviewWord,
    attempt_score,
    daily_plan,
    end_of_day,
    level,
    rating,
    replay,
    retrievability,
    review_form_ids,
    skill_id,
    strength,
    update_card,
    update_mastery,
    word_class,
    word_class_label,
    word_class_order,
)

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
GEN = "+N+Sg+Gen"


def attempt(
    *,
    word=1,
    word_class="verb:1",
    form_id="+V+Act+Ind+Prs+Sg1",
    outcome="correct",
    at=T0,
    wrong=0,
    hints=0,
):
    return Attempt(
        word=word,
        word_class=word_class,
        form_id=form_id,
        outcome=outcome,
        answered_at=at,
        wrong_attempts=wrong,
        hints=hints,
    )


# --- Grading -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "wrong", "hints", "expected"),
    [
        ("correct", 0, 0, Rating.Good),
        ("correct", 1, 0, Rating.Hard),
        ("correct", 0, 2, Rating.Hard),
        ("skipped", 0, 0, Rating.Again),
        ("skipped", 3, 1, Rating.Again),
    ],
)
def test_rating_never_gives_easy(outcome, wrong, hints, expected):
    assert rating(attempt(outcome=outcome, wrong=wrong, hints=hints)) == expected


def test_attempt_score_rewards_clean_answers_and_floors_struggles():
    assert attempt_score(attempt()) == 1.0
    assert attempt_score(attempt(wrong=1)) == 0.75
    assert attempt_score(attempt(wrong=10, hints=10)) == 0.2
    assert attempt_score(attempt(outcome="skipped")) == 0.0


# --- Scheduling --------------------------------------------------------------------


def test_successful_reviews_space_out_and_a_skip_pulls_the_word_back():
    first = update_card(None, attempt())
    assert first.reviews == 1 and first.lapses == 0
    assert first.due - T0 >= timedelta(days=1)

    second = update_card(first, attempt(at=first.due))
    assert second.due - first.due > first.due - T0

    lapsed = update_card(second, attempt(outcome="skipped", at=second.due))
    assert lapsed.lapses == 1
    assert lapsed.due - second.due < second.due - first.due


def test_card_round_trips_through_plain_data():
    card = update_card(update_card(None, attempt()), attempt(at=T0 + timedelta(days=3)))
    assert CardState.from_dict(card.to_dict()) == card


def test_retrievability_falls_with_time():
    card = update_card(None, attempt())
    assert retrievability(card, T0 + timedelta(days=1)) > retrievability(
        card, T0 + timedelta(days=30)
    )


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        update_card(None, attempt(at=datetime(2026, 11, 1, 9)))


# --- Mastery -----------------------------------------------------------------------


def test_mastery_starts_neutral_and_moves_with_evidence():
    assert strength(None, T0) == 0.5
    assert level(None, T0) == "unseen"

    good = None
    for day in range(6):
        good = update_mastery(good, attempt(at=T0 + timedelta(days=day)))
    now = T0 + timedelta(days=6)
    assert strength(good, now) > 0.85
    assert level(good, now) == "mastered"

    bad = None
    for day in range(3):
        bad = update_mastery(
            bad, attempt(outcome="skipped", at=T0 + timedelta(days=day))
        )
    assert level(bad, T0 + timedelta(days=3)) == "weak"


def test_one_lucky_answer_is_not_mastery():
    cell = update_mastery(None, attempt())
    assert level(cell, T0) == "learning"


def test_old_evidence_fades_back_toward_the_prior():
    cell = None
    for day in range(10):
        cell = update_mastery(cell, attempt(at=T0 + timedelta(days=day)))
    fresh = strength(cell, T0 + timedelta(days=10))
    stale = strength(cell, T0 + timedelta(days=400))
    assert fresh > stale > 0.5
    assert stale == pytest.approx(0.5, abs=0.01)


def test_recent_attempts_outweigh_old_ones():
    cell = None
    for day in range(5):
        cell = update_mastery(cell, attempt(at=T0 + timedelta(days=day)))
    for day in range(60, 63):
        cell = update_mastery(
            cell, attempt(outcome="skipped", at=T0 + timedelta(days=day))
        )
    assert level(cell, T0 + timedelta(days=63)) == "weak"


def test_mastery_round_trips_through_plain_data():
    cell = update_mastery(update_mastery(None, attempt()), attempt(wrong=1))
    assert Mastery.from_dict(cell.to_dict()) == cell


def test_replay_orders_attempts_by_time_and_tracks_each_cell():
    attempts = [
        attempt(word=2, at=T0 + timedelta(days=2)),
        attempt(word=1, at=T0),
        attempt(word=1, form_id="+V+Act+Ind+Prt+Sg1", at=T0 + timedelta(days=1)),
    ]
    in_order = replay(sorted(attempts, key=lambda a: a.answered_at))
    shuffled = replay(attempts)

    assert shuffled.cards == in_order.cards
    assert shuffled.mastery == in_order.mastery
    assert set(shuffled.cards) == {1, 2}
    assert set(shuffled.mastery) == {
        skill_id("verb:1", "+V+Act+Ind+Prs+Sg1"),
        skill_id("verb:1", "+V+Act+Ind+Prt+Sg1"),
    }
    assert shuffled.cards[1].reviews == 2


# --- Word classes ------------------------------------------------------------------


def nominal(lemma, genitive, partitive=None, pos="N"):
    forms = {f"+{pos}+Sg+Gen": [genitive], f"+{pos}+Sg+Par": [partitive]}
    forms = {tag: answers for tag, answers in forms.items() if answers[0]}
    return {"fin": lemma, "lemma": lemma, "pos": pos, "forms": forms}


# Genitives and partitives as the Finnish model generates them (checked by
# test_real_model_gives_the_tables_the_class_tests_assume).
NOUN_CLASSES = [
    ("talo", "talon", "taloa", "nominal:o"),
    ("radio", "radion", "radiota", "nominal:o"),
    ("katu", "kadun", "katua", "nominal:o:grad"),
    ("kukka", "kukan", "kukkaa", "nominal:a:grad"),
    ("koira", "koiran", "koiraa", "nominal:a"),
    ("lattia", "lattian", "lattiaa", "nominal:a"),
    ("ruoka", "ruuan", "ruokaa", "nominal:a:grad"),
    ("paperi", "paperin", "paperia", "nominal:i"),
    ("pankki", "pankin", "pankkia", "nominal:i:grad"),
    # -i words with an e-stem: kivi → kiveä, kieli → kieltä, vesi → vettä.
    ("kivi", "kiven", "kiveä", "nominal:i:e"),
    ("sormi", "sormen", "sormea", "nominal:i:e"),
    ("lahti", "lahden", "lahtea", "nominal:i:e:grad"),
    ("kieli", "kielen", "kieltä", "nominal:i:t"),
    ("lapsi", "lapsen", "lasta", "nominal:i:t"),
    ("kuusi", "kuusen", "kuusta", "nominal:i:t"),
    ("veitsi", "veitsen", "veistä", "nominal:i:t"),
    ("vesi", "veden", "vettä", "nominal:si"),
    ("käsi", "käden", "kättä", "nominal:si"),
    ("kynsi", "kynnen", "kynttä", "nominal:si"),
    ("huone", "huoneen", "huonetta", "nominal:e"),
    ("liike", "liikkeen", "liikettä", "nominal:e:grad"),
    # One-syllable long vowels and -i diphthongs vs ie/uo/yö vs vapaa.
    ("maa", "maan", "maata", "nominal:VV"),
    ("puu", "puun", "puuta", "nominal:VV"),
    ("voi", "voin", "voita", "nominal:VV"),
    ("tie", "tien", "tietä", "nominal:ie"),
    ("työ", "työn", "työtä", "nominal:ie"),
    ("suo", "suon", "suota", "nominal:ie"),
    ("vapaa", "vapaan", "vapaata", "nominal:VV:2"),
    ("nainen", "naisen", "naista", "nominal:nen"),
    # -s words: vastaus → vastauksen vs rakkaus → rakkauden.
    ("vastaus", "vastauksen", "vastausta", "nominal:us"),
    ("kysymys", "kysymyksen", "kysymystä", "nominal:us"),
    ("jänis", "jäniksen", "jänistä", "nominal:us"),
    ("rakkaus", "rakkauden", "rakkautta", "nominal:us:d"),
    ("ystävyys", "ystävyyden", "ystävyyttä", "nominal:us:d"),
    ("kangas", "kankaan", "kangasta", "nominal:as:grad"),
    ("mies", "miehen", "miestä", "nominal:as"),
    ("kirves", "kirveen", "kirvestä", "nominal:as"),
    ("kallis", "kalliin", "kallista", "nominal:is"),
    # -in: lämmin and otin grade; puhelin, avain and sisin only add -m-.
    ("puhelin", "puhelimen", "puhelinta", "nominal:in"),
    ("avain", "avaimen", "avainta", "nominal:in"),
    ("sisin", "sisimmän", "sisintä", "nominal:in"),
    ("otin", "ottimen", "otinta", "nominal:in:grad"),
    ("sydän", "sydämen", "sydäntä", "nominal:C"),
    ("olut", "oluen", "olutta", "nominal:C"),
    ("askel", "askelen", "askelta", "nominal:C"),
    ("tytär", "tyttären", "tytärtä", "nominal:C:grad"),
    ("kuningatar", "kuningattaren", "kuningatarta", "nominal:C:grad"),
]
ADJECTIVE_CLASSES = [
    ("rikas", "rikkaan", "rikasta", "nominal:as:grad"),
    ("uusi", "uuden", "uutta", "nominal:si"),
    ("suuri", "suuren", "suurta", "nominal:i:t"),
    ("lämmin", "lämpimän", "lämmintä", "nominal:in:grad"),
    ("vapaa", "vapaan", "vapaata", "nominal:VV:2"),
    ("korkea", "korkean", "korkeaa", "nominal:a"),
    ("kaunis", "kaunin", "kaunsta", "nominal:is"),
]


@pytest.mark.parametrize(("lemma", "genitive", "partitive", "expected"), NOUN_CLASSES)
def test_nominal_classes_come_from_the_ending_and_the_table(
    lemma, genitive, partitive, expected
):
    assert word_class(nominal(lemma, genitive, partitive)) == expected


@pytest.mark.parametrize(
    ("lemma", "genitive", "partitive", "expected"), ADJECTIVE_CLASSES
)
def test_adjectives_share_classes_with_nouns(lemma, genitive, partitive, expected):
    assert word_class(nominal(lemma, genitive, partitive, pos="A")) == expected


@pytest.mark.integration
def test_real_model_gives_the_tables_the_class_tests_assume():
    from finnish_core.morphology import InflectionEngine, UralicNlpAdapter

    engine = InflectionEngine(UralicNlpAdapter())
    cases = [("N", *case) for case in NOUN_CLASSES]
    cases += [("A", *case) for case in ADJECTIVE_CLASSES]
    for pos, lemma, genitive, partitive, _ in cases:
        generated = [
            engine.generate_inflection(lemma, f"+{pos}+Sg+{case}")[:1]
            for case in ("Gen", "Par")
        ]
        assert generated == [[genitive], [partitive]], lemma


def test_a_missing_partitive_falls_back_to_the_genitive():
    assert word_class(nominal("kivi", "kiven")) == "nominal:i:e"
    assert word_class(nominal("vesi", "veden")) == "nominal:si"


@pytest.mark.parametrize(
    ("lemma", "expected"),
    [
        ("kala", "nominal:a"),
        ("vesi", "nominal:i"),
        ("vastaus", "nominal:us"),
        ("maa", "nominal:VV"),
        ("tie", "nominal:ie"),
        ("vapaa", "nominal:VV:2"),
        ("korkea", "nominal:a"),
        ("mies", "nominal:as"),
        ("sydän", "nominal:C"),
    ],
)
def test_words_without_a_table_still_get_an_ending_class(lemma, expected):
    assert word_class({"fin": lemma, "pos": "N"}) == expected


def test_every_class_has_a_label_with_an_example():
    from finnish_core.learning import _NOMINAL_ENDINGS

    for ending in _NOMINAL_ENDINGS:
        label = word_class_label(f"nominal:{ending}")
        assert label != ending and "(" in label


def test_verbs_use_their_type():
    assert (
        word_class({"fin": "haluta", "lemma": "haluta", "pos": "V", "verb_type": 4})
        == "verb:4"
    )
    assert word_class({"fin": "puhua", "lemma": "puhua", "pos": "V"}) == "verb:1"


def test_class_labels_and_order():
    assert word_class_label("verb:4").startswith("Type 4")
    assert word_class_label("nominal:a:grad") == "-a/-ä (kala), gradation"
    classes = ["verb:2", "nominal:a:grad", "verb:1", "nominal:nen", "nominal:a"]
    assert sorted(classes, key=word_class_order) == [
        "nominal:nen",
        "nominal:a",
        "nominal:a:grad",
        "verb:1",
        "verb:2",
    ]
    assert word_class_label("nominal:si") == "-si → -den (vesi, käsi)"
    e_stems = ["nominal:si", "nominal:i:t:grad", "nominal:i:e", "nominal:i:t"]
    assert sorted(e_stems, key=word_class_order) == [
        "nominal:i:e",
        "nominal:i:t",
        "nominal:i:t:grad",
        "nominal:si",
    ]


def test_review_forms_cover_declension_and_finite_verbs_only():
    nouns = review_form_ids("N")
    verbs = review_form_ids("V")
    assert len(nouns) == 26 and len(set(nouns)) == 26
    assert all(form.startswith("+N") for form in nouns)
    assert len(verbs) == 21
    assert not any("Prc" in form for form in verbs)


# --- Daily plan --------------------------------------------------------------------

NOUN_FORMS = review_form_ids("N")


def word(id, *, due_in=None, forms=NOUN_FORMS, cls="nominal:a"):
    card = None
    if due_in is not None:
        card = update_card(None, attempt(word=id, at=T0 - timedelta(days=5)))
        card = CardState.from_dict({**card.to_dict(), "due": (T0 + due_in).isoformat()})
    return ReviewWord(id=id, word_class=cls, form_ids=forms, card=card)


def plan(words, mastery=None, seed=1, **settings):
    return daily_plan(
        words,
        mastery or {},
        T0,
        random.Random(seed),
        settings=PlanSettings(**settings),
    )


def weak_cell():
    cell = None
    for day in range(3):
        cell = update_mastery(
            cell, attempt(outcome="skipped", at=T0 - timedelta(days=day))
        )
    return cell


def mastered_cell():
    cell = None
    for day in range(8):
        cell = update_mastery(cell, attempt(at=T0 - timedelta(days=day)))
    return cell


def test_plan_mixes_due_weak_and_new_words():
    due = [word(i, due_in=-timedelta(days=1)) for i in range(30)]
    later = [word(100 + i, due_in=timedelta(days=5)) for i in range(10)]
    new = [word(200 + i) for i in range(10)]
    mastery = {skill_id("nominal:a", NOUN_FORMS[3]): weak_cell()}

    items = plan(due + later + new, mastery, size=20, new_limit=5)

    reasons = Counter(item.reason for item in items)
    assert len(items) == 20
    # 70/20/10 of 20 is 14/4/2; the three missing weak spots go to due words.
    assert reasons == {"due": 17, "weak": 1, "new": 2}
    assert len({item.word for item in items}) == 20
    weak = next(item for item in items if item.reason == "weak")
    assert weak.form_id == NOUN_FORMS[3]
    assert weak.word in {w.id for w in due + later}


def test_most_forgotten_due_words_come_first():
    long_overdue = word("old", due_in=-timedelta(days=20))
    just_due = word("recent", due_in=-timedelta(hours=1))
    items = plan([just_due, long_overdue], size=1, due_share=1.0, weak_share=0.0)
    assert [item.word for item in items] == ["old"]


def test_words_due_later_today_count_with_due_by():
    later_today = word(1, due_in=timedelta(hours=6))
    assert plan([later_today], size=5) == []
    items = daily_plan(
        [later_today],
        {},
        T0,
        random.Random(1),
        due_by=T0 + timedelta(hours=12),
        settings=PlanSettings(size=5),
    )
    assert [(item.word, item.reason) for item in items] == [(1, "due")]


def test_shortfalls_are_filled_from_the_other_groups():
    new = [word(i) for i in range(10)]
    items = plan(new, size=8, new_limit=8)
    assert len(items) == 8
    assert {item.reason for item in items} == {"new"}

    due = [word(i, due_in=-timedelta(days=1)) for i in range(10)]
    items = plan(due, size=8, new_limit=0)
    assert len(items) == 8
    assert {item.reason for item in items} == {"due"}


def test_weak_practice_fills_the_plan_from_one_shared_cell():
    # Nothing due or new: ten learned words share the one weak cell.
    form = NOUN_FORMS[3]
    learned = [word(i, due_in=timedelta(days=5)) for i in range(10)]
    mastery = {skill_id("nominal:a", form): weak_cell()}

    items = plan(learned, mastery, size=10, new_limit=0)

    assert len(items) == 10
    assert {(item.form_id, item.reason) for item in items} == {(form, "weak")}
    assert len({item.word for item in items}) == 10


def test_weak_passes_take_the_weakest_cell_first_and_alternate():
    weaker, weak = NOUN_FORMS[3], NOUN_FORMS[4]
    weakest = weak_cell()
    for day in range(3, 6):
        weakest = update_mastery(
            weakest, attempt(outcome="skipped", at=T0 - timedelta(hours=day))
        )
    mastery = {
        skill_id("nominal:a", weaker): weakest,
        skill_id("nominal:a", weak): weak_cell(),
    }
    learned = [word(i, due_in=timedelta(days=5)) for i in range(10)]

    # One weak item in the first pass, then the shortfall alternates cells.
    for size, expected in [(1, {weaker: 1}), (3, {weaker: 2, weak: 1})]:
        items = plan(learned, mastery, size=size, new_limit=0)
        assert Counter(item.form_id for item in items) == expected


def test_new_words_respect_the_daily_limit_and_list_order():
    new = [word(i) for i in range(10)]
    items = plan(new, size=20, new_limit=3)
    assert sorted(item.word for item in items) == [0, 1, 2]


def test_due_words_rarely_land_on_mastered_forms():
    two_forms = NOUN_FORMS[:2]
    mastery = {skill_id("nominal:a", two_forms[0]): mastered_cell()}
    due = [word(i, due_in=-timedelta(days=1), forms=two_forms) for i in range(200)]

    items = plan(due, mastery, size=200, due_share=1.0, weak_share=0.0)

    asked = Counter(item.form_id for item in items)
    assert asked[two_forms[0]] < asked[two_forms[1]] / 5


def test_new_words_start_in_forms_their_class_knows():
    two_forms = NOUN_FORMS[:2]
    mastery = {
        skill_id("nominal:a", two_forms[0]): mastered_cell(),
        skill_id("nominal:a", two_forms[1]): weak_cell(),
    }
    new = [word(i, forms=two_forms) for i in range(200)]

    items = plan(new, mastery, size=200, new_limit=200)

    asked = Counter(item.form_id for item in items)
    assert asked[two_forms[0]] > asked[two_forms[1]] * 3


def test_weak_cells_are_only_asked_with_words_that_have_the_form():
    form = NOUN_FORMS[5]
    mastery = {skill_id("nominal:a", form): weak_cell()}
    lacks_form = word(1, due_in=timedelta(days=9), forms=NOUN_FORMS[:5])
    other_class = word(2, due_in=timedelta(days=9), cls="nominal:o")
    assert plan([lacks_form, other_class], mastery, size=5) == []


def test_words_with_nothing_to_ask_are_skipped():
    assert plan([word(1, forms=())], size=5) == []


def test_the_same_seed_gives_the_same_plan():
    words = [word(i, due_in=-timedelta(days=i % 3)) for i in range(20)] + [
        word(100 + i) for i in range(5)
    ]
    assert plan(words, seed=7) == plan(words, seed=7)


def test_end_of_day_uses_the_learners_time_zone():
    from zoneinfo import ZoneInfo

    helsinki = ZoneInfo("Europe/Helsinki")
    # 23:30 UTC on 1 Nov is already 01:30 on 2 Nov in Helsinki.
    late = datetime(2026, 11, 1, 23, 30, tzinfo=timezone.utc)
    assert end_of_day(late, helsinki) == datetime(2026, 11, 3, tzinfo=helsinki)
    assert end_of_day(late, timezone.utc) == datetime(2026, 11, 2, tzinfo=timezone.utc)


def test_adjectives_and_nouns_share_skill_cells():
    from finnish_core.learning import skill_form

    assert skill_form("+A+Pl+Ine") == "+N+Pl+Ine"
    assert skill_form("+V+Act+Ind+Prs+Sg1") == "+V+Act+Ind+Prs+Sg1"
    assert skill_id("nominal:as", "+A+Sg+Gen") == skill_id("nominal:as", "+N+Sg+Gen")

    adjective = word("rikas", due_in=timedelta(days=9), forms=review_form_ids("A"))
    mastery = {skill_id("nominal:a", "+N+Pl+Ine"): weak_cell()}
    items = plan([adjective], mastery, size=5)
    assert [(item.word, item.form_id, item.reason) for item in items] == [
        ("rikas", "+A+Pl+Ine", "weak")
    ]


def test_replay_breaks_timestamp_ties_by_seq():
    first = Attempt(1, "verb:1", "+V+Act+Ind+Prs+Sg1", "correct", T0, seq=1)
    second = Attempt(1, "verb:1", "+V+Act+Ind+Prs+Sg1", "skipped", T0, seq=2)
    assert replay([first, second]).cards == replay([second, first]).cards
    assert replay([second, first]).cards[1].lapses == 1
