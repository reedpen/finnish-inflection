from importlib.resources import files
import json
from pathlib import Path

from finnish_core.starter.build import (
    build_document,
    checked_report_is_current,
    main,
    serialized,
    structural_review,
    validate_with_model,
)


def test_packaged_default_is_reproducible_from_canonical_source():
    data = files("finnish_core.starter")
    source = Path(str(data.joinpath("default_vocab.csv")))
    packaged = Path(str(data.joinpath("default_vocab.json")))
    overrides = Path(str(data.joinpath("default_vocab.overrides.json")))
    report = Path(str(data.joinpath("default_vocab.review.json")))

    assert serialized(build_document(source)) == packaged.read_text(encoding="utf-8")
    generated_report = structural_review(source, overrides)
    checked_report = json.loads(report.read_text(encoding="utf-8"))
    assert checked_report_is_current(checked_report, generated_report)


def test_structural_review_records_each_publish_blocker(tmp_path):
    source = tmp_path / "words.csv"
    source.write_text(
        "Front;Back;Lemma;POS;VerbType\n"
        "koira;dog;koira;N;\n"
        "koirat;dogs;koira;N;\n"
        "x;letter;x;X;\n"
        "tyhjä;;tyhjä;N;\n",
        encoding="utf-8",
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text("{}\n", encoding="utf-8")

    report = structural_review(source, overrides)

    assert report["duplicates"] == [{"line": 3, "lemma": "koira", "pos": "N"}]
    assert report["unknown_parts_of_speech"] == [{"line": 4, "fin": "x", "pos": "X"}]
    assert report["empty_values"] == [{"line": 5, "fields": ["Back"]}]
    assert report["review_status"] == "failed"
    assert (
        main(
            [
                "--source",
                str(source),
                "--overrides",
                str(overrides),
                "--output",
                str(tmp_path / "output.json"),
                "--report",
                str(tmp_path / "report.json"),
                "--check",
            ]
        )
        == 1
    )


def test_check_fails_when_review_report_is_stale(tmp_path):
    data = files("finnish_core.starter")
    source = Path(str(data.joinpath("default_vocab.csv")))
    overrides = Path(str(data.joinpath("default_vocab.overrides.json")))
    output = tmp_path / "default.json"
    report = tmp_path / "review.json"
    output.write_text(serialized(build_document(source)), encoding="utf-8")
    report.write_text("{}\n", encoding="utf-8")

    assert (
        main(
            [
                "--source",
                str(source),
                "--overrides",
                str(overrides),
                "--output",
                str(output),
                "--report",
                str(report),
                "--check",
            ]
        )
        == 1
    )


def test_opt_in_model_review_records_analysis_and_generation_failures(tmp_path):
    data = files("finnish_core.starter")
    source = Path(str(data.joinpath("default_vocab.csv")))
    overrides = Path(str(data.joinpath("default_vocab.overrides.json")))
    document = build_document(source)
    report = structural_review(source, overrides)

    class FailingMorphology:
        def is_language_installed(self, language):
            return True

        def download(self, language):
            raise AssertionError

        def analyze(self, word, language):
            return []

        def lemmatize(self, word, language):
            return []

        def generate(self, query, language):
            return []

    empty_overrides = tmp_path / "overrides.json"
    empty_overrides.write_text("{}\n", encoding="utf-8")
    reviewed = validate_with_model(
        document, report, empty_overrides, morphology=FailingMorphology()
    )

    assert reviewed["model_verification"]["status"] == "failed"
    assert len(reviewed["ambiguous_analyses"]) == len(document["entries"])
    assert len(reviewed["generated_form_failures"]) == len(document["entries"])
    assert reviewed["review_status"] == "failed"
