"""Build a validated, versioned vocabulary document from CSV or text."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from finnish_core.importer import preview_summary
from finnish_core.vocab import (
    SCHEMA_VERSION,
    VocabularyError,
    make_vocabulary_document,
)

from finnish_cli.sources import analyze_vocabulary_source, load_overrides
from finnish_cli.store import load_or_rebuild_vocabulary

if TYPE_CHECKING:
    from finnish_core.morphology import MorphologyAdapter


CACHE_BUILD_VERSION = 1


def _cache_inputs(source: bytes, overrides: bytes, strict: bool) -> tuple[bytes, dict]:
    """Fingerprint every input whose change requires a vocabulary rebuild."""
    manifest = {
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "overrides_sha256": hashlib.sha256(overrides).hexdigest(),
        "schema_version": SCHEMA_VERSION,
        "builder_version": CACHE_BUILD_VERSION,
        "strict": strict,
    }
    return json.dumps(manifest, sort_keys=True).encode(), manifest


def build_cache(
    input_filepath: str,
    output_filepath: str = "data/vocab_cache.json",
    *,
    morphology: "MorphologyAdapter | None" = None,
    overrides_path: str | None = None,
    report_path: str | None = None,
    strict: bool = True,
) -> bool:
    """Analyze a source and atomically publish it if the quality gate passes."""
    source = Path(input_filepath)
    if not source.exists():
        print(f"Error: could not find {source}")
        return False
    try:
        source_bytes = source.read_bytes()
        overrides = load_overrides(overrides_path)
        overrides_bytes = (
            Path(overrides_path).read_bytes() if overrides_path else b"{}\n"
        )
        fingerprint_input, input_manifest = _cache_inputs(
            source_bytes, overrides_bytes, strict
        )
        destination_report = (
            Path(report_path)
            if report_path
            else Path(output_filepath).with_suffix(".review.json")
        )

        def rebuild():
            preview = analyze_vocabulary_source(
                source,
                name=source.stem,
                overrides=overrides,
                morphology=morphology,
            )
            report = {
                "summary": preview_summary(preview),
                "cache_inputs": input_manifest,
                "corrected": preview.corrected,
                "ambiguous": preview.ambiguous,
                "rejected": preview.rejected,
                "excluded": preview.excluded,
            }
            destination_report.parent.mkdir(parents=True, exist_ok=True)
            destination_report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(report["summary"])
            if strict and (preview.ambiguous or preview.rejected):
                raise VocabularyError(
                    f"quality gate failed; review {destination_report} and add "
                    "explicit overrides or exclusions"
                )
            return make_vocabulary_document(
                preview.accepted,
                source_bytes=fingerprint_input,
                name=source.stem,
            )

        load_or_rebuild_vocabulary(
            output_filepath,
            source_bytes=fingerprint_input,
            rebuild=rebuild,
        )
        print(f"Vocabulary cache is current at {output_filepath}")
        return True
    except (VocabularyError, OSError) as exc:
        print(f"Build failed: {exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", default="data/vocab_cache.json")
    parser.add_argument("--overrides")
    parser.add_argument("--report")
    parser.add_argument("--allow-rejected", action="store_true")
    args = parser.parse_args(argv)
    success = build_cache(
        args.input,
        args.output,
        overrides_path=args.overrides,
        report_path=args.report,
        strict=not args.allow_rejected,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
