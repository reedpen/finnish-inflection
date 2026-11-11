import pytest

from finnish_core.morphology import InflectionEngine, UralicNlpAdapter

pytestmark = pytest.mark.integration

ENGINE = InflectionEngine(UralicNlpAdapter())
inflect_noun = ENGINE.inflect_noun
inflect_verb = ENGINE.inflect_verb


def test_inflect_noun_basic():
    # Test Illative Singular of "koira"
    results = inflect_noun("koira", "Illative (-aan/-iin)", "Singular")
    # "koiraan" should be in the results
    assert any("koiraan" == r.lower() for r in results)


def test_inflect_noun_plural():
    # Test Inessive Plural of "lapsi" (lapsissa)
    results = inflect_noun("lapsi", "Inessive (-ssa)", "Plural")
    assert any("lapsissa" == r.lower() for r in results)


def test_inflect_verb_present():
    # Test Present Tense 1st Person Singular of "puhua" (puhun)
    results = inflect_verb("puhua", "Present", "1st Person Sg (I)")
    assert any("puhun" == r.lower() for r in results)


def test_inflect_verb_past():
    # Test Past Tense 3rd Person Plural of "mennä" (menivät)
    results = inflect_verb("mennä", "Past", "3rd Person Pl (They)")
    assert any("menivät" == r.lower() for r in results)


def test_inflect_verb_passive():
    # Test Passive Past of "tehdä" (tehtiin)
    results = inflect_verb("tehdä", "Past", "Passive")
    assert any("tehtiin" == r.lower() for r in results)
