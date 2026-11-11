"""Inflection services backed by an injectable morphology adapter."""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any, Protocol

from finnish_core.forms import get_noun_tag, get_participle_tag, get_verb_tag

log = logging.getLogger(__name__)


class MorphologyAdapter(Protocol):
    """The external morphology operations used by the application."""

    def is_language_installed(self, language: str) -> bool: ...

    def download(self, language: str) -> Any: ...

    def generate(self, query: str, language: str) -> list[tuple[Any, ...]]: ...

    def analyze(self, word: str, language: str) -> list[tuple[Any, ...]]: ...

    def lemmatize(self, word: str, language: str) -> list[str]: ...


class UralicNlpAdapter:
    """Lazy boundary around :mod:`uralicNLP`'s module-level API."""

    def __init__(self, api: Any | None = None) -> None:
        self._configured_api = api

    @property
    def _api(self) -> Any:
        if self._configured_api is None:
            from uralicNLP import uralicApi

            self._configured_api = uralicApi
        return self._configured_api

    def is_language_installed(self, language: str) -> bool:
        return bool(self._api.is_language_installed(language))

    def download(self, language: str) -> Any:
        return self._api.download(language)

    def generate(self, query: str, language: str) -> list[tuple[Any, ...]]:
        return self._api.generate(query, language)

    def analyze(self, word: str, language: str) -> list[tuple[Any, ...]]:
        return self._api.analyze(word, language)

    def lemmatize(self, word: str, language: str) -> list[str]:
        return self._api.lemmatize(word, language)


class InflectionEngine:
    """Generate Finnish forms through a supplied morphology implementation."""

    def __init__(self, morphology: MorphologyAdapter) -> None:
        self.morphology = morphology

    def ensure_model_downloaded(
        self,
        language: str = "fin",
        on_download: Callable[[str], None] | None = None,
    ) -> bool:
        """Install a missing language model and report whether a download occurred.

        ``on_download`` is called with the language code before a download
        starts, so front ends can tell the user it may take a few minutes.
        """
        if self.morphology.is_language_installed(language):
            return False
        if on_download is not None:
            on_download(language)
        self.morphology.download(language)
        return True

    @lru_cache(maxsize=4096)
    def _cached_generate(self, query: str, language: str) -> tuple[str, ...]:
        """Run and cache one transducer query."""
        try:
            results = self.morphology.generate(query, language)
            return tuple(str(result[0]).split("@")[0] for result in results)
        except Exception:
            log.warning("could not generate %s", query, exc_info=True)
            return ()

    def generate_inflection(
        self, base_word: str, full_tag: str, language: str = "fin"
    ) -> list[str]:
        """Return all generated forms for a lemma and complete Omorfi tag."""
        return list(self._cached_generate(f"{base_word}{full_tag}", language))

    def inflect_noun(
        self, base_word: str, case: str, number: str, pos: str = "N"
    ) -> list[str]:
        """Generate forms for a noun or adjective."""
        return self.generate_inflection(base_word, get_noun_tag(case, number, pos))

    def inflect_verb(self, base_word: str, tense_mood: str, person: str) -> list[str]:
        """Generate finite forms for a verb."""
        return self.generate_inflection(base_word, get_verb_tag(tense_mood, person))

    def inflect_participle(
        self, base_word: str, participle: str, case: str, number: str
    ) -> list[str]:
        """Generate declined participle forms."""
        tag = get_participle_tag(participle, case, number)
        return self.generate_inflection(base_word, tag)
