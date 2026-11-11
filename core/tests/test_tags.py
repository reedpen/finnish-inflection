from finnish_core.forms import get_noun_tag, get_participle_tag, get_verb_tag


def test_noun_tag_contains_part_of_speech_number_and_case() -> None:
    assert get_noun_tag("Illative (-aan/-iin)", "Singular", "N") == "+N+Sg+Ill"


def test_comitative_tag_uses_the_numberless_possessive_form() -> None:
    assert get_noun_tag("Comitative (-ineen)", "Singular") == "+N+Com+PxSg3"
    assert get_noun_tag("Comitative (-ineen)", "Plural") == "+N+Com+PxSg3"


def test_instructive_tag_is_always_plural() -> None:
    assert get_noun_tag("Instructive (-in)", "Singular") == "+N+Pl+Ins"


def test_active_and_passive_verb_tags_use_distinct_voice_tags() -> None:
    assert get_verb_tag("Past", "3rd Person Pl (They)") == "+V+Act+Ind+Prt+Pl3"
    assert get_verb_tag("Past", "Passive") == "+V+Pss+Ind+Prt+Pe4"


def test_participle_tag_combines_participle_number_and_case() -> None:
    assert (
        get_participle_tag("Past Active (NUT)", "Inessive (-ssa)", "Plural")
        == "+V+Act+PrfPrc+Pl+Ine"
    )
