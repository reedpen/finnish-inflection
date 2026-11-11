import pytest

from finnish_core.vocab import classify_verb_type


@pytest.mark.parametrize(
    ("lemma", "verb_type"),
    [
        ("puhua", 1),
        ("juoda", 2),
        ("tulla", 3),
        ("haluta", 4),
        ("tarvita", 5),
        ("paeta", 6),
        ("xyz", 0),
    ],
)
def test_classifies_canonical_finnish_verb_types(lemma: str, verb_type: int) -> None:
    assert classify_verb_type(lemma) == verb_type
