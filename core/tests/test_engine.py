from finnish_core.morphology import InflectionEngine


class FakeMorphology:
    def __init__(self, forms: dict[str, list[tuple[str, float]]]) -> None:
        self.forms = forms
        self.generated_queries: list[tuple[str, str]] = []
        self.downloaded_languages: list[str] = []

    def is_language_installed(self, language: str) -> bool:
        return False

    def download(self, language: str) -> None:
        self.downloaded_languages.append(language)

    def generate(self, query: str, language: str):
        self.generated_queries.append((query, language))
        return self.forms.get(query, [])

    def analyze(self, word: str, language: str):
        return []

    def lemmatize(self, word: str, language: str):
        return []


def test_engine_generates_a_noun_through_an_injected_morphology() -> None:
    morphology = FakeMorphology(
        {"koira+N+Sg+Ill": [("koiraan@guess", 0.0), ("koiraan", 1.0)]}
    )
    engine = InflectionEngine(morphology)

    assert engine.inflect_noun("koira", "Illative (-aan/-iin)", "Singular") == [
        "koiraan",
        "koiraan",
    ]
    assert morphology.generated_queries == [("koira+N+Sg+Ill", "fin")]


def test_engine_caches_identical_generation_requests() -> None:
    morphology = FakeMorphology({"puhua+V+Act+Ind+Prs+Sg1": [("puhun", 0.0)]})
    engine = InflectionEngine(morphology)

    first = engine.inflect_verb("puhua", "Present", "1st Person Sg (I)")
    second = engine.inflect_verb("puhua", "Present", "1st Person Sg (I)")

    assert first == second == ["puhun"]
    assert morphology.generated_queries == [("puhua+V+Act+Ind+Prs+Sg1", "fin")]


def test_engine_downloads_only_a_missing_language() -> None:
    morphology = FakeMorphology({})
    engine = InflectionEngine(morphology)

    downloaded = engine.ensure_model_downloaded("fin")

    assert downloaded is True
    assert morphology.downloaded_languages == ["fin"]
