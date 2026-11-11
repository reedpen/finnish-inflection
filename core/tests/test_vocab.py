import pytest

from finnish_core.vocab import (
    VocabularyError,
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


def test_analyzer_reads_complete_tag_strings_and_reports_ambiguity():
    class Morphology:
        def analyze(self, word, language):
            return [("kuusi+N+Sg+Nom", 0.1), ("kuusi+V+Act+Ind+Prs+Sg3", 0.2)]

        def lemmatize(self, word, language):
            return ["kuusi"]

    assert categorize_word("kuusi", morphology=Morphology()) == ("?", "kuusi")
    assert categorize_word("kuusi", "noun", Morphology()) == ("N", "kuusi")
