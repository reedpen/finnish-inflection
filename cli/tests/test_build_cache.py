from finnish_cli.store import load_vocabulary_document
from finnish_cli.scripts.build_cache import build_cache


class Morphology:
    def __init__(self):
        self.generated = []

    def is_language_installed(self, language):
        return True

    def download(self, language):
        raise AssertionError("installed models must not download")

    def analyze(self, word, language):
        return [(f"{word}+N+Sg+Nom", 0.0)]

    def lemmatize(self, word, language):
        return [word]

    def generate(self, query, language):
        self.generated.append(query)
        return [(query.split("+")[0], 0.0)]


def test_builder_uses_injected_morphology_and_publishes_shared_schema(tmp_path):
    source = tmp_path / "lesson.csv"
    source.write_text("Front;Back\nkoira;dog\n", encoding="utf-8")
    output = tmp_path / "lesson.json"
    morphology = Morphology()

    assert build_cache(str(source), str(output), morphology=morphology)

    assert morphology.generated == ["koira+N+Sg+Nom"]
    assert load_vocabulary_document(output)["entries"] == [
        {"fin": "koira", "lemma": "koira", "eng": "dog", "pos": "N"}
    ]
    assert output.with_suffix(".review.json").exists()


def test_builder_rebuilds_a_cache_when_its_source_changes(tmp_path):
    source = tmp_path / "lesson.csv"
    output = tmp_path / "lesson.json"
    morphology = Morphology()
    source.write_text("Front;Back\nkoira;dog\n", encoding="utf-8")
    assert build_cache(str(source), str(output), morphology=morphology)

    source.write_text("Front;Back\nkissa;cat\n", encoding="utf-8")
    assert build_cache(str(source), str(output), morphology=morphology)

    assert load_vocabulary_document(output)["entries"] == [
        {"fin": "kissa", "lemma": "kissa", "eng": "cat", "pos": "N"}
    ]


def test_builder_rebuilds_when_review_overrides_change(tmp_path):
    source = tmp_path / "lesson.csv"
    output = tmp_path / "lesson.json"
    overrides = tmp_path / "overrides.json"
    morphology = Morphology()
    source.write_text("Front;Back\nkoira;dog\n", encoding="utf-8")
    overrides.write_text("{}\n", encoding="utf-8")
    assert build_cache(
        str(source),
        str(output),
        morphology=morphology,
        overrides_path=str(overrides),
    )

    overrides.write_text(
        '{"koira": {"lemma": "koira", "pos": "A"}}\n', encoding="utf-8"
    )
    assert build_cache(
        str(source),
        str(output),
        morphology=morphology,
        overrides_path=str(overrides),
    )

    assert load_vocabulary_document(output)["entries"][0]["pos"] == "A"
