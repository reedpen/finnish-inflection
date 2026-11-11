import random

import pytest

from finnish_core.morphology import InflectionEngine
from finnish_core.paradigm import (
    build_table,
    conjugation_form_ids,
    declension_form_ids,
    engine_lookup,
    form_ids,
    table_lookup,
)
from finnish_core.questions import build_noun_pool, build_verb_pool


class FakeMorphology:
    """Generates a form for every tag except the instructive, with a duplicate."""

    def generate(self, query, language):
        if "+Ins" in query:
            return []
        return [(f"{query}@",), (f"{query}@",)]


def test_declension_covers_each_meaningful_case_and_number_once():
    ids = declension_form_ids("A")

    assert len(ids) == len(set(ids)) == 26
    assert "+A+Pl+Ine" in ids and "+A+Com+PxSg3" in ids and "+A+Pl+Ins" in ids
    assert "+A+Sg+Ins" not in ids


def test_conjugation_covers_finite_forms_and_declined_participles():
    ids = conjugation_form_ids()

    assert "+V+Act+Ind+Prs+Sg1" in ids and "+V+Pss+Cond+Prs+Pe4" in ids
    assert "+V+Act+PrsPrc+Pl+Ine" in ids
    assert len(ids) == len(set(ids)) == 3 * 7 + 6 * 26
    assert form_ids({"fin": "puhua", "pos": "V"}) == ids


def test_build_table_drops_missing_forms_and_duplicate_answers():
    engine = InflectionEngine(FakeMorphology())

    table = build_table({"fin": "talo", "lemma": "talo", "pos": "N"}, engine)

    assert "+N+Pl+Ins" not in table
    assert table["+N+Sg+Ine"] == ["talo+N+Sg+Ine"]
    assert len(table) == 25


def test_stored_tables_and_live_generation_build_identical_pools():
    engine = InflectionEngine(FakeMorphology())
    words = [
        {"fin": "talo", "lemma": "talo", "eng": "house", "pos": "N"},
        {"fin": "puhua", "lemma": "puhua", "eng": "to speak", "pos": "V"},
    ]
    stored = [{**word, "forms": build_table(word, engine)} for word in words]
    cases = ["Inessive (-ssa)", "Instructive (-in)", "Comitative (-ineen)"]

    def pools(vocabulary, lookup):
        return (
            build_noun_pool(
                vocabulary[:1],
                cases,
                ["Singular", "Plural"],
                lookup,
                rng=random.Random(1),
            ),
            build_verb_pool(
                vocabulary[1:],
                ["Past"],
                ["Passive", "1st Person Sg (I)"],
                lookup,
                rng=random.Random(1),
            ),
        )

    assert pools(stored, table_lookup) == pools(words, engine_lookup(engine))


def test_table_lookup_without_a_table_finds_nothing():
    assert table_lookup({"fin": "talo"}, "+N+Sg+Nom") == ()


@pytest.mark.integration
def test_real_model_builds_a_full_verb_table():
    from finnish_core.morphology import UralicNlpAdapter

    engine = InflectionEngine(UralicNlpAdapter())
    table = build_table({"fin": "tavata", "lemma": "tavata", "pos": "V"}, engine)

    assert "tapasin" in table["+V+Act+Ind+Prt+Sg1"]
    assert "tavattiin" in table["+V+Pss+Ind+Prt+Pe4"]
    assert len(table) > 150
