"""The terminal app's single inflection engine, backed by the real model."""

from finnish_core.morphology import InflectionEngine, UralicNlpAdapter

ENGINE = InflectionEngine(UralicNlpAdapter())


def announce_download(language: str) -> None:
    print(
        f"Downloading the {language} model for UralicNLP. This may take a few minutes…"
    )


def ensure_model_downloaded(language: str = "fin") -> bool:
    return ENGINE.ensure_model_downloaded(language, on_download=announce_download)
