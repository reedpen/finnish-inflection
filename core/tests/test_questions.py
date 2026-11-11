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
