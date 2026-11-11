"""
Mapping of human-readable grammatical forms to Omorfi tags for uralicNLP.
"""

NOUN_CASES = {
    "Nominative (---)": "+Nom",
    "Genitive (-n)": "+Gen",
    "Partitive (-a/-ta)": "+Par",
    "Inessive (-ssa)": "+Ine",
    "Elative (-sta)": "+Ela",
    "Illative (-aan/-iin)": "+Ill",
    "Adessive (-lla)": "+Ade",
    "Ablative (-lta)": "+Abl",
    "Allative (-lle)": "+All",
    "Essive (-na)": "+Ess",
    "Translative (-ksi)": "+Tra",
    "Abessive (-tta)": "+Abe",
    "Comitative (-ineen)": "+Com",
    "Instructive (-in)": "+Ins",
}

NOUN_NUMBERS = {"Singular": "+Sg", "Plural": "+Pl"}

VERB_TENSES_MOODS = {
    "Present": "+Ind+Prs",
    "Past": "+Ind+Prt",
    "Conditional": "+Cond+Prs",
}

VERB_PERSONS = {
    "1st Person Sg (I)": "+Sg1",
    "2nd Person Sg (You)": "+Sg2",
    "3rd Person Sg (He/She)": "+Sg3",
    "1st Person Pl (We)": "+Pl1",
    "2nd Person Pl (You)": "+Pl2",
    "3rd Person Pl (They)": "+Pl3",
    "Passive": "Passive",
}

VERB_TYPES = {
    "Type 1 (-a/-ä, puhua)": 1,
    "Type 2 (-da/-dä, juoda)": 2,
    "Type 3 (-lla/-nnä/-rra/-sta, tulla)": 3,
    "Type 4 (-Vta/-Vtä, haluta)": 4,
    "Type 5 (-ita/-itä, tarvita)": 5,
    "Type 6 (-eta/-etä, paeta)": 6,
}

VERB_PARTICIPLES = {
    "Present Active (VA)": "+V+Act+PrsPrc",
    "Past Active (NUT)": "+V+Act+PrfPrc",
    "Present Passive (TAVA)": "+V+Pss+PrsPrc",
    "Past Passive (TU)": "+V+Pss+PrfPrc",
    "Agent (MA)": "+V+AgPrc",
    "Negative (MATON)": "+V+NegPrc",
}


def _build_case_tag(pos_tag: str, case_tag: str, num_tag: str) -> str:
    """Builds the full Omorfi tag, handling cases with special number/suffix rules."""
    # Comitative: no number distinction, requires 3rd person possessive suffix
    if case_tag == "+Com":
        return f"{pos_tag}+Com+PxSg3"
    # Instructive: only exists in plural
    if case_tag == "+Ins":
        return f"{pos_tag}+Pl+Ins"
    return f"{pos_tag}{num_tag}{case_tag}"


def get_noun_tag(case: str, number: str, pos: str = "N") -> str:
    """Returns the combined Omorfi tag for a noun or adjective."""
    case_tag = NOUN_CASES.get(case, "+Nom")
    num_tag = NOUN_NUMBERS.get(number, "+Sg")
    return _build_case_tag(f"+{pos}", case_tag, num_tag)


def get_verb_tag(tense_mood: str, person: str) -> str:
    """Returns the combined Omorfi tag for a verb."""
    if person == "Passive":
        # Passives are formed differently (e.g. +V+Pss+Ind+Prs+Pe4)
        return f"+V+Pss{VERB_TENSES_MOODS.get(tense_mood, '+Ind+Prs')}+Pe4"
    else:
        # Action verbs (e.g., +V+Act+Ind+Prs+Sg1)
        return f"+V+Act{VERB_TENSES_MOODS.get(tense_mood, '+Ind+Prs')}{VERB_PERSONS.get(person, '+Sg3')}"


def get_participle_tag(participle: str, case: str, number: str) -> str:
    """Returns the combined Omorfi tag for a verb participle declined in a case."""
    prc_base = VERB_PARTICIPLES.get(participle, "+V+Act+PrsPrc")
    case_tag = NOUN_CASES.get(case, "+Nom")
    num_tag = NOUN_NUMBERS.get(number, "+Sg")
    return _build_case_tag(prc_base, case_tag, num_tag)


def noun_combinations(cases, numbers):
    """Yield each meaningful (case, number) label pair once.

    The instructive exists only in the plural. The comitative has no number
    contrast, but Omorfi needs one, so it is always asked as plural.
    """
    seen = set()
    numbers = tuple(numbers)
    for case in cases:
        if case.startswith("Instructive"):
            allowed_numbers = ("Plural",) if "Plural" in numbers else ()
        elif case.startswith("Comitative"):
            allowed_numbers = ("Plural",)
        else:
            allowed_numbers = numbers
        for number in allowed_numbers:
            combination = (case, number)
            if combination not in seen:
                seen.add(combination)
                yield combination
