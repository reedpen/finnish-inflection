from finnish_core.questions import build_noun_pool, build_participle_pool


def test_noun_pool_normalizes_numberless_and_plural_only_cases():
    calls = []

    def inflect(entry, form_id):
        calls.append((entry["lemma"], form_id))
        return [f"{entry['lemma']}{form_id}"]

    pool = build_noun_pool(
        [{"fin": "talo", "lemma": "talo", "eng": "house", "pos": "N"}],
        ["Comitative (-ineen)", "Instructive (-in)"],
        ["Singular", "Plural"],
        inflect,
    )

    assert calls == [("talo", "+N+Com+PxSg3"), ("talo", "+N+Pl+Ins")]
    assert len(pool) == 2


def test_noun_pool_omits_questions_without_answers():
    pool = build_noun_pool(
        [{"fin": "talo", "eng": "house", "pos": "N"}],
        ["Nominative (---)"],
        ["Singular"],
        lambda *_: [],
    )

    assert pool == []


def test_plural_only_case_is_not_generated_when_plural_is_filtered_out():
    pool = build_noun_pool(
        [{"fin": "talo", "eng": "house", "pos": "N"}],
        ["Instructive (-in)"],
        ["Singular"],
        lambda *_: ["taloin"],
    )

    assert pool == []


def test_pool_stops_inflecting_when_requested_number_is_playable():
    calls = 0

    def inflect(*_):
        nonlocal calls
        calls += 1
        return ["answer"]

    pool = build_noun_pool(
        [{"fin": f"word-{number}", "eng": "word"} for number in range(1000)],
        ["Nominative (---)"],
        ["Singular"],
        inflect,
        max_questions=12,
    )

    assert len(pool) == 12
    assert calls == 12


def test_participle_pool_keeps_only_supported_questions_from_partially_playable_vocabulary():
    pool = build_participle_pool(
        [{"fin": "puhua", "eng": "speak"}, {"fin": "olla", "eng": "be"}],
        ["Present Active (VA)"],
        ["Nominative (---)"],
        ["Singular"],
        lambda entry, _: ["puhuva"] if entry["fin"] == "puhua" else [],
    )

    assert [question.word for question in pool] == ["puhua"]


def test_empty_filters_create_an_empty_pool_without_inflection_calls():
    calls = 0

    def inflect(*_):
        nonlocal calls
        calls += 1
        return ["answer"]

    assert build_noun_pool([{"fin": "talo"}], [], ["Singular"], inflect) == []
    assert calls == 0


def test_duplicate_vocabulary_does_not_duplicate_an_equivalent_question():
    word = {"fin": "talo", "lemma": "talo", "eng": "house"}
    pool = build_noun_pool(
        [word, dict(word)],
        ["Nominative (---)"],
        ["Singular"],
        lambda *_: ["talo"],
    )

    assert len(pool) == 1


def test_sparse_pool_falls_back_until_a_playable_candidate_is_found():
    calls = 0

    def inflect(entry, _):
        nonlocal calls
        calls += 1
        return ["answer"] if entry["fin"] == "word-999" else []

    class FirstCandidates:
        def sample(self, _population, count):
            return list(range(count))

    pool = build_noun_pool(
        [{"fin": f"word-{number}"} for number in range(1000)],
        ["Nominative (---)"],
        ["Singular"],
        inflect,
        max_questions=10,
        max_candidates=10,
        rng=FirstCandidates(),
    )

    assert [question.word for question in pool] == ["word-999"]
    assert calls == 1000


def _words():
    return [
        {"fin": "talo", "lemma": "talo", "eng": "house", "pos": "N"},
        {"fin": "iso", "lemma": "iso", "eng": "big", "pos": "A"},
        {
            "fin": "puhua",
            "lemma": "puhua",
            "eng": "to speak",
            "pos": "V",
            "verb_type": 1,
        },
        {
            "fin": "juoda",
            "lemma": "juoda",
            "eng": "to drink",
            "pos": "V",
            "verb_type": 2,
        },
    ]


def _echo(entry, form_id):
    return [f"{entry['lemma']}{form_id}"]


def test_questions_carry_stable_word_and_form_ids():
    from finnish_core.settings import DrillSettings
    from finnish_core.questions import build_pool

    settings = DrillSettings("noun", {"cases": ["+Ine"], "numbers": ["+Pl"]}, 5)

    pool = build_pool(settings, _words(), _echo)

    assert {(q.lemma, q.pos, q.form_id) for q in pool} == {
        ("talo", "N", "+N+Pl+Ine"),
        ("iso", "A", "+A+Pl+Ine"),
    }
    assert all(q.answers == (f"{q.lemma}{q.form_id}",) for q in pool)


def test_build_pool_filters_verbs_by_type_and_maps_ids_to_forms():
    from finnish_core.questions import build_pool
    from finnish_core.settings import DrillSettings

    settings = DrillSettings(
        "verb",
        {"types": ["2"], "tenses": ["+Ind+Prt"], "persons": ["+Sg1", "Passive"]},
        None,
    )

    pool = build_pool(settings, _words(), _echo)

    assert sorted(q.form_id for q in pool) == [
        "+V+Act+Ind+Prt+Sg1",
        "+V+Pss+Ind+Prt+Pe4",
    ]
    assert {q.lemma for q in pool} == {"juoda"}


def test_build_pool_declines_participles_of_every_verb():
    from finnish_core.questions import build_pool
    from finnish_core.settings import DrillSettings

    settings = DrillSettings(
        "participle",
        {"participles": ["+V+Act+PrsPrc"], "cases": ["+Com"], "numbers": ["+Sg"]},
        10,
    )

    pool = build_pool(settings, _words(), _echo)

    assert {(q.lemma, q.form_id) for q in pool} == {
        ("puhua", "+V+Act+PrsPrc+Com+PxSg3"),
        ("juoda", "+V+Act+PrsPrc+Com+PxSg3"),
    }


def test_question_for_matches_the_pool_builders():
    from finnish_core.questions import build_pool, question_for
    from finnish_core.settings import parse_settings

    def inflect(entry, form_id):
        return [f"{entry['lemma']}{form_id}"]

    noun = {"fin": "talo", "lemma": "talo", "eng": "house", "pos": "N"}
    verb = {
        "fin": "puhua",
        "lemma": "puhua",
        "eng": "speak",
        "pos": "V",
        "verb_type": 1,
    }
    settings = [
        {
            "drill": "noun",
            "selections": {"cases": ["+Com", "+Ine"], "numbers": ["+Pl"]},
        },
        {
            "drill": "verb",
            "selections": {
                "types": ["1"],
                "tenses": ["+Ind+Prt"],
                "persons": ["Passive", "+Sg2"],
            },
        },
        {
            "drill": "participle",
            "selections": {
                "participles": ["+V+AgPrc"],
                "cases": ["+Ela"],
                "numbers": ["+Sg"],
            },
        },
    ]
    for raw in settings:
        pool = build_pool(parse_settings(raw), [noun, verb], inflect, max_questions=50)
        assert pool
        for question in pool:
            entry = noun if question.pos == "N" else verb
            assert question_for(entry, question.form_id, inflect) == question


def test_question_for_rejects_forms_of_another_part_of_speech_or_without_answers():
    from finnish_core.questions import question_for

    noun = {"fin": "talo", "lemma": "talo", "pos": "N"}
    assert question_for(noun, "+V+Act+Ind+Prs+Sg1", lambda *_: ["x"]) is None
    assert question_for(noun, "+N+Sg+Gen", lambda *_: []) is None
    assert (
        question_for(noun, "+N+Sg+Gen", lambda *_: ["talon"]).target
        == "Genitive (-n) Singular"
    )


def test_form_labels():
    from finnish_core.questions import form_label

    assert form_label("+N+Pl+Ine") == "Inessive (-ssa) Plural"
    assert form_label("+A+Com+PxSg3") == "Comitative (-ineen)"
    assert form_label("+V+Pss+Ind+Prt+Pe4") == "Past, Passive"
    assert form_label("+X") == "+X"
