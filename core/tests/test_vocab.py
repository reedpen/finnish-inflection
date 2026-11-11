import pytest

from finnish_core.vocab import (
    VocabularyError,
    WordAnalysis,
    analysis_candidates,
    analyze_word,
    categorize_word,
    make_vocabulary_document,
    packaged_default_document,
    validate_vocabulary_document,
)


def entry(**extra):
    return {"fin": "koira", "lemma": "koira", "eng": "dog", "pos": "N", **extra}


def test_entries_may_carry_a_stored_inflection_table():
    document = make_vocabulary_document(
        [entry(forms={"+N+Sg+Ine": ["koirassa"]})], source_bytes=b"x", name="dogs"
    )

    assert document["entries"][0]["forms"] == {"+N+Sg+Ine": ["koirassa"]}


@pytest.mark.parametrize(
    "forms",
    [["koirassa"], {"+N+Sg+Ine": "koirassa"}, {"+N+Sg+Ine": [""]}, {1: ["x"]}],
)
def test_malformed_tables_are_rejected(forms):
    with pytest.raises(VocabularyError, match="forms must map form ids"):
        make_vocabulary_document([entry(forms=forms)], source_bytes=b"x", name="d")


def test_packaged_default_document_is_valid():
    document = packaged_default_document()

    assert validate_vocabulary_document(document) == document
    assert {item["pos"] for item in document["entries"]} == {"N", "A", "V"}


class Morphology:
    """Reads "kuusi" as kuu + possessive, the noun kuusi, or a form of kusta."""

    def analyze(self, word, language):
        return [
            ("kuu+N+Sg+Nom+PxSg2", 0.1),
            ("kuusi+N+Sg+Nom", 0.1),
            ("kusta+V+Act+Ind+Prt+Sg3", 0.2),
            ("kuusi+V+Act+PrsPrc+Sg+Nom", 0.3),
        ]

    def lemmatize(self, word, language):
        return ["kuu", "kuusi"]


def test_candidates_prefer_the_reading_whose_lemma_is_the_word_itself():
    assert analysis_candidates("kuusi", Morphology()) == {"V": "kusta", "N": "kuusi"}


def test_candidates_fall_back_to_the_first_reading_for_inflected_input():
    class Inflected:
        def analyze(self, word, language):
            return [("kirja+N+Pl+Nom", 0.1), ("kirja#kauppa+N+Sg+Nom", 0.2)]

    assert analysis_candidates("kirjat", Inflected()) == {"N": "kirja"}


class Analyses:
    """Answers analyze() from a fixed table of analysis strings."""

    def __init__(self, **table):
        self.table = table

    def analyze(self, word, language):
        return [(analysis, 0.0) for analysis in self.table.get(word, [])]


def test_the_gloss_decides_first():
    assert categorize_word("kuusi", "noun", Morphology()) == ("N", "kuusi")
    assert categorize_word("kuusi", "to pee (past)", Morphology()) == ("V", "kusta")


def test_ambiguous_words_are_assumed_to_be_given_in_their_base_form():
    tuli = Analyses(tuli=["tulla+V+Act+Ind+Prt+Sg3", "tuli+N+Sg+Nom"])

    assert analyze_word("tuli", "fire", tuli) == WordAnalysis(
        "N", "tuli", {"V": "tulla", "N": "tuli"}, assumed=True
    )
    assert analyze_word("kuusi", "", Morphology()).assumed


def test_a_verb_infinitive_is_a_base_form():
    sataa = Analyses(
        sataa=["sataa+V+Act+Ind+Prs+Sg3", "sataa+V+Act+InfA+Sg+Lat", "sata+N+Sg+Par"]
    )

    assert categorize_word("sataa", "", sataa) == ("V", "sataa")


def test_adjective_wins_when_noun_and_adjective_are_both_base_forms():
    hyva = Analyses(hyvä=["hyvä+N+Sg+Nom", "hyvä+A+Sg+Nom"])

    assert analyze_word("hyvä", "good", hyva) == WordAnalysis(
        "A", "hyvä", {"A": "hyvä", "N": "hyvä"}, assumed=True
    )


def test_words_with_no_base_form_reading_stay_ambiguous():
    palaa = Analyses(palaa=["palata+V+Act+Ind+Prs+Sg3", "pala+N+Sg+Par"])

    assert categorize_word("palaa", "", palaa) == ("?", "palaa")
    assert analyze_word("xyzzy", "", Analyses()) == WordAnalysis("?", "xyzzy")


def test_possessive_and_comparative_forms_are_not_base_forms():
    kuu = Analyses(kuusi=["kuu+N+Sg+Nom+PxSg2", "kusta+V+Act+Ind+Prt+Sg3"])
    isompi = Analyses(isompi=["iso+A+Comp+Sg+Nom", "isompi+N+Sg+Gen"])

    assert categorize_word("kuusi", "", kuu) == ("?", "kuusi")
    assert categorize_word("isompi", "", isompi) == ("?", "isompi")


def test_compound_lemmas_join_their_parts():
    compound = Analyses(kirjakauppa=["kirja+N+Sg+Nom+Cmp#kauppa+N+Sg+Nom"])

    assert analyze_word("kirjakauppa", "bookshop", compound) == WordAnalysis(
        "N", "kirjakauppa", {"N": "kirjakauppa"}
    )


def test_inflected_compounds_prefer_the_whole_word_reading():
    # Rebuilding the compound from its parts drops "kirjan"'s genitive -n and
    # keeps the prefix's hyphen; the whole-word readings are the real lemmas.
    compounds = Analyses(
        kirjanpitäjät=[
            "kirja+N+Sg+Gen+Cmp#pitäjä+N+Pl+Nom",
            "kirjanpitäjä+N+Pl+Nom",
        ],
        suurkaupungissa=[
            "suur-+N+Cmp#kaupunki+N+Sg+Ine",
            "suur+N+Pref+Cmp#kaupunki+N+Sg+Ine",
            "suurkaupunki+N+Sg+Ine",
        ],
        kissakaupassa=["kissa+N+Sg+Nom+Cmp#kauppa+N+Sg+Ine"],
    )

    assert categorize_word("kirjanpitäjät", "", compounds) == ("N", "kirjanpitäjä")
    assert categorize_word("suurkaupungissa", "", compounds) == ("N", "suurkaupunki")
    # With no whole-word reading, the rebuilt compound is still used.
    assert categorize_word("kissakaupassa", "", compounds) == ("N", "kissakauppa")


@pytest.mark.integration
def test_real_model_reads_dictionary_forms_as_themselves():
    from finnish_core.morphology import UralicNlpAdapter

    morphology = UralicNlpAdapter()

    assert analysis_candidates("kuusi", morphology)["N"] == "kuusi"
    assert analysis_candidates("tuli", morphology) == {"V": "tulla", "N": "tuli"}
    assert categorize_word("tuli", "fire", morphology) == ("N", "tuli")
    assert categorize_word("voi", "butter", morphology) == ("N", "voi")
    assert categorize_word("palaa", "burns", morphology) == ("V", "palaa")
    assert categorize_word("kirjakauppa", "bookshop", morphology) == (
        "N",
        "kirjakauppa",
    )
    assert categorize_word("kuusi", "six", morphology) == ("N", "kuusi")


@pytest.mark.integration
def test_real_model_lemmatizes_inflected_compounds():
    from finnish_core.morphology import UralicNlpAdapter

    morphology = UralicNlpAdapter()

    for word, lemma in [
        ("kirjanpitäjät", "kirjanpitäjä"),
        ("kirjanpitäjä", "kirjanpitäjä"),
        ("suurkaupungissa", "suurkaupunki"),
        ("suurkaupunki", "suurkaupunki"),
        ("kirjakaupassa", "kirjakauppa"),
        ("kuusi", "kuusi"),
    ]:
        assert analyze_word(word, "", morphology).lemma == lemma, word
