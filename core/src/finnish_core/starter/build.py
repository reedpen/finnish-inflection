"""Deterministically build and review the packaged starter vocabulary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from copy import deepcopy
from importlib.resources import files
from io import StringIO
from pathlib import Path

from finnish_core.vocab import (
    SUPPORTED_POS,
    categorize_word,
    make_vocabulary_document,
    validate_vocabulary_document,
)

REVIEW_FAILURE_FIELDS = (
    "duplicates",
    "empty_values",
    "unknown_parts_of_speech",
    "ambiguous_analyses",
    "generated_form_failures",
)


def _rows(source: Path) -> tuple[bytes, list[tuple[int, dict[str, str]]]]:
    source_bytes = source.read_bytes()
    text = source_bytes.decode("utf-8")
    reader = csv.DictReader(StringIO(text), delimiter=";")
    required = {"Front", "Back", "Lemma", "POS", "VerbType"}
    if reader.fieldnames is None or set(reader.fieldnames) != required:
        raise ValueError(f"canonical source headers must be {sorted(required)}")
    return source_bytes, [(line, dict(row)) for line, row in enumerate(reader, 2)]


def structural_review(source: Path, overrides: Path) -> dict:
    """Create the deterministic checked-in review report without loading a model."""
    source_bytes, rows = _rows(source)
    override_bytes = overrides.read_bytes()
    override_data = json.loads(override_bytes.decode("utf-8"))
    if not isinstance(override_data, dict):
        raise ValueError("default vocabulary overrides must be a JSON object")
    for fin, override in override_data.items():
        if not isinstance(fin, str) or not isinstance(override, dict):
            raise ValueError("default overrides must map words to review objects")
        if set(override) != {"lemma", "pos"} or not all(
            isinstance(value, str) and value for value in override.values()
        ):
            raise ValueError("each default override requires text lemma and pos values")
    report = {
        "source": source.name,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "overrides": overrides.name,
        "overrides_sha256": hashlib.sha256(override_bytes).hexdigest(),
        "transformation": "python -m finnish_core.starter.build --check --validate-model",
        "accepted": 0,
        "duplicates": [],
        "empty_values": [],
        "unknown_parts_of_speech": [],
        "ambiguous_analyses": [],
        "resolved_ambiguities": [],
        "generated_form_failures": [],
        "model_verification": {
            "status": "not-run",
            "command": "python -m finnish_core.starter.build --check --validate-model",
        },
    }
    seen = set()
    source_words = set()
    for line, row in rows:
        values = {key: (value or "").strip() for key, value in row.items()}
        source_words.add(values["Front"])
        empty = [
            field for field in ("Front", "Back", "Lemma", "POS") if not values[field]
        ]
        if empty:
            report["empty_values"].append({"line": line, "fields": empty})
            continue
        if values["POS"] not in SUPPORTED_POS:
            report["unknown_parts_of_speech"].append(
                {"line": line, "fin": values["Front"], "pos": values["POS"]}
            )
            continue
        key = (values["Lemma"].casefold(), values["POS"])
        if key in seen:
            report["duplicates"].append(
                {"line": line, "lemma": values["Lemma"], "pos": values["POS"]}
            )
            continue
        seen.add(key)
        override = override_data.get(values["Front"])
        if override and (override["lemma"], override["pos"]) != (
            values["Lemma"],
            values["POS"],
        ):
            raise ValueError(
                f"override for {values['Front']!r} disagrees with the canonical CSV"
            )
        report["accepted"] += 1
    unknown_overrides = sorted(set(override_data) - source_words)
    if unknown_overrides:
        raise ValueError(
            f"overrides reference unknown words: {', '.join(unknown_overrides)}"
        )
    report["review_status"] = (
        "failed" if any(report[field] for field in REVIEW_FAILURE_FIELDS) else "passed"
    )
    return report


def build_document(source: Path) -> dict:
    source_bytes, rows = _rows(source)
    entries = []
    for line_number, row in rows:
        item = {
            "fin": row["Front"].strip(),
            "lemma": row["Lemma"].strip(),
            "eng": row["Back"].strip(),
            "pos": row["POS"].strip(),
        }
        verb_type = row["VerbType"].strip()
        if verb_type:
            try:
                item["verb_type"] = int(verb_type)
            except ValueError as exc:
                raise ValueError(
                    f"line {line_number} has a non-numeric verb type"
                ) from exc
        entries.append(item)
    return make_vocabulary_document(entries, source_bytes=source_bytes, name="default")


def validate_with_model(
    document: dict, report: dict, overrides: Path, morphology=None
) -> dict:
    """Run opt-in analyzer and representative generation checks."""
    from finnish_core.morphology import InflectionEngine, UralicNlpAdapter
    from finnish_core.forms import get_noun_tag, get_verb_tag

    morphology = morphology or UralicNlpAdapter()
    engine = InflectionEngine(morphology)
    engine.ensure_model_downloaded("fin")
    result = deepcopy(report)
    override_data = json.loads(overrides.read_text(encoding="utf-8"))
    result["ambiguous_analyses"] = []
    result["resolved_ambiguities"] = []
    result["generated_form_failures"] = []
    for item in document["entries"]:
        analyzed_pos, analyzed_lemma = categorize_word(
            item["fin"], item["eng"], morphology
        )
        if analyzed_pos == "?" or (analyzed_pos, analyzed_lemma) != (
            item["pos"],
            item["lemma"],
        ):
            finding = {
                "fin": item["fin"],
                "reviewed": f"{item['lemma']} ({item['pos']})",
                "analyzed": f"{analyzed_lemma} ({analyzed_pos})",
            }
            override = override_data.get(item["fin"])
            if override == {"lemma": item["lemma"], "pos": item["pos"]}:
                result["resolved_ambiguities"].append(finding)
            else:
                result["ambiguous_analyses"].append(finding)
        tag = (
            get_verb_tag("Present", "1st Person Sg (I)")
            if item["pos"] == "V"
            else get_noun_tag("Nominative (---)", "Singular", item["pos"])
        )
        if not engine.generate_inflection(item["lemma"], tag):
            result["generated_form_failures"].append(item["fin"])
    failed = any(result[field] for field in REVIEW_FAILURE_FIELDS)
    result["model_verification"] = {
        "status": "failed" if failed else "passed",
        "adapter": type(morphology).__name__,
    }
    result["review_status"] = "failed" if failed else "passed"
    return result


def serialized(document: dict) -> str:
    validate_vocabulary_document(document)
    metadata = json.dumps(document["metadata"], ensure_ascii=False, indent=4)
    metadata = metadata[:-1] + "  }"
    entries = ",\n".join(
        "    " + json.dumps(item, ensure_ascii=False, separators=(", ", ": "))
        for item in document["entries"]
    )
    return (
        "{\n"
        f'  "schema_version": {document["schema_version"]},\n'
        '  "metadata": ' + metadata + ",\n"
        '  "entries": [\n' + entries + "\n  ]\n}\n"
    )


def serialized_report(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def checked_report_is_current(actual: dict, structural: dict) -> bool:
    """Verify source facts and the last model quality gate without rerunning it."""
    structural_fields = (
        "source",
        "source_sha256",
        "overrides",
        "overrides_sha256",
        "accepted",
        "duplicates",
        "empty_values",
        "unknown_parts_of_speech",
    )
    return (
        all(actual.get(field) == structural[field] for field in structural_fields)
        and actual.get("review_status") == "passed"
        and actual.get("model_verification", {}).get("status") == "passed"
        and not any(actual.get(field) for field in REVIEW_FAILURE_FIELDS)
    )


def main(argv: list[str] | None = None) -> int:
    package_data = files("finnish_core.starter")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(str(package_data.joinpath("default_vocab.csv"))),
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path(str(package_data.joinpath("default_vocab.overrides.json"))),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(str(package_data.joinpath("default_vocab.json"))),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(str(package_data.joinpath("default_vocab.review.json"))),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in artifacts differ or record failures",
    )
    parser.add_argument(
        "--validate-model",
        action="store_true",
        help="also validate analyses/forms with UralicNLP",
    )
    args = parser.parse_args(argv)
    try:
        structural = structural_review(args.source, args.overrides)
        document = build_document(args.source)
        expected = serialized(document)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Default vocabulary review failed: {exc}")
        return 1
    if structural["review_status"] != "passed":
        print("Default vocabulary review records failures; inspect the report.")
        return 1
    report = structural
    if args.validate_model:
        try:
            report = validate_with_model(document, structural, args.overrides)
        except Exception as exc:
            print(f"Model verification could not run: {exc}")
            return 1
        if report["review_status"] != "passed":
            print(serialized_report(report), end="")
            return 1
    if args.check:
        try:
            checked_report = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            checked_report = {}
        stale = (
            not args.output.exists()
            or args.output.read_text(encoding="utf-8") != expected
        )
        stale = stale or not checked_report_is_current(checked_report, structural)
        if args.validate_model:
            stale = stale or checked_report != report
        if stale:
            print("Default vocabulary output or review report is stale; rebuild it.")
            return 1
    else:
        args.output.write_text(expected, encoding="utf-8")
        args.report.write_text(serialized_report(report), encoding="utf-8")
        print(f"Wrote {args.output} and {args.report}")
    if args.check:
        print(
            "Packaged default vocabulary and review report are reproducible and current."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
