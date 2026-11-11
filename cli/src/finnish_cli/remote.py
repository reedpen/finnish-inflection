"""Browse and install vocabulary sets published in a public GitHub repository.

The repository is listed live through the GitHub trees API, so a set appears
in the app as soon as its file is pushed. Every word list under ``sets/``
(``.csv``, ``.tsv``, or ``.txt``) is one set; folders group sets, and an
optional ``<set>.overrides.json`` beside a list supplies review overrides.

Installed sets remember their repository path and git blob SHA, which lets
``updates`` spot changed files from the listing alone, without downloading
anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from finnish_core.vocab import VocabularyError, suggest_set_name

from finnish_cli.store import VocabularyStore

DEFAULT_REPOSITORY = "reedpen/finnish-vocab-sets"
REPOSITORY_ENV = "FINNISH_DRILL_SETS_REPO"
SETS_DIRECTORY = "sets"
SET_SUFFIXES = (".csv", ".tsv", ".txt")
OVERRIDES_SUFFIX = ".overrides.json"
SOURCE_PREFIX = "github:"
_TIMEOUT_SECONDS = 15
_MAX_SET_BYTES = 2_000_000

Fetch = Callable[[str, dict[str, str]], bytes]


class RemoteNotFound(VocabularyError):
    """GitHub has no repository, branch, or file at the requested location."""


def _http_fetch(url: str, headers: dict[str, str]) -> bytes:
    request = Request(url, headers={"User-Agent": "finnish-inflection-cli", **headers})
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return response.read(_MAX_SET_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise RemoteNotFound(f"not found: {url}") from exc
        if exc.code == 409:  # GitHub's answer for a repository with no commits
            raise VocabularyError("the sets repository has no commits yet") from exc
        if exc.code in {403, 429} and exc.headers.get("X-RateLimit-Remaining") == "0":
            reset = exc.headers.get("X-RateLimit-Reset")
            when = (
                datetime.fromtimestamp(int(reset)).strftime("%H:%M")
                if reset and reset.isdigit()
                else "later"
            )
            raise VocabularyError(
                f"GitHub's hourly request limit was reached; try again after {when} "
                "(or set GITHUB_TOKEN to raise the limit)"
            ) from exc
        raise VocabularyError(f"GitHub returned HTTP {exc.code} for {url}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise VocabularyError(
            f"could not reach GitHub ({reason}); check your network connection"
        ) from exc


def git_blob_sha(data: bytes) -> str:
    """Return the SHA git assigns to a file with these exact bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass(frozen=True)
class RemoteSet:
    """One word list in the repository."""

    path: str
    sha: str
    size: int
    overrides_path: str | None = None

    @property
    def title(self) -> str:
        """Path below ``sets/`` without its extension, e.g. ``starter/verbs``."""
        relative = self.path.removeprefix(f"{SETS_DIRECTORY}/")
        return relative.rsplit(".", 1)[0]

    @property
    def name(self) -> str:
        """A valid local set name derived from the title."""
        return suggest_set_name(self.title.replace("/", "-"))


class RemoteRepository:
    """A GitHub repository of vocabulary sets, ``owner/repo`` or ``owner/repo@ref``."""

    def __init__(self, spec: str | None = None, *, fetch: Fetch | None = None):
        spec = (spec or os.environ.get(REPOSITORY_ENV) or DEFAULT_REPOSITORY).strip()
        repository, _, ref = spec.partition("@")
        owner, _, name = repository.partition("/")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", owner)
            or not re.fullmatch(r"[A-Za-z0-9._-]+", name)
            or name in {".", ".."}
        ):
            raise VocabularyError(
                f"sets repository must look like owner/repo or owner/repo@branch, not {spec!r}"
            )
        self.repository = repository
        self.ref = ref or "main"
        self._fetch = fetch or _http_fetch

    def source_id(self, path: str) -> str:
        return f"{SOURCE_PREFIX}{self.repository}/{path}"

    def _api_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def list_sets(self) -> list[RemoteSet]:
        url = (
            f"https://api.github.com/repos/{self.repository}/git/trees/"
            f"{quote(self.ref)}?recursive=1"
        )
        try:
            body = self._fetch(url, self._api_headers())
        except RemoteNotFound as exc:
            raise RemoteNotFound(
                f"sets repository {self.repository} (branch {self.ref}) was not found"
            ) from exc
        try:
            tree = json.loads(body)["tree"]
        except (ValueError, KeyError, TypeError) as exc:
            raise VocabularyError(
                "GitHub returned an unexpected repository listing"
            ) from exc
        blobs = {
            item["path"]: item
            for item in tree
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and str(item.get("path", "")).startswith(f"{SETS_DIRECTORY}/")
        }
        sets = []
        for path, item in blobs.items():
            if not path.casefold().endswith(SET_SUFFIXES):
                continue
            overrides = path.rsplit(".", 1)[0] + OVERRIDES_SUFFIX
            sets.append(
                RemoteSet(
                    path=path,
                    sha=item["sha"],
                    size=int(item.get("size") or 0),
                    overrides_path=overrides if overrides in blobs else None,
                )
            )
        return sorted(sets, key=lambda item: item.title.casefold())

    def find(self, query: str, sets: list[RemoteSet] | None = None) -> RemoteSet:
        sets = self.list_sets() if sets is None else sets
        wanted = query.strip().casefold()
        for item in sets:
            if wanted in {
                item.name.casefold(),
                item.title.casefold(),
                item.path.casefold(),
            }:
                return item
        raise VocabularyError(
            f"no set named {query!r} in {self.repository}; run 'finnish-drill vocab browse'"
        )

    def _raw(self, path: str) -> bytes:
        url = (
            f"https://raw.githubusercontent.com/{self.repository}/"
            f"{quote(self.ref)}/{quote(path)}"
        )
        data = self._fetch(url, {})
        if len(data) > _MAX_SET_BYTES:
            raise VocabularyError(
                f"{path} is larger than {_MAX_SET_BYTES // 1_000_000} MB"
            )
        return data

    def download(self, item: RemoteSet) -> bytes:
        return self._raw(item.path)

    def download_overrides(self, item: RemoteSet) -> dict[str, Any] | None:
        if item.overrides_path is None:
            return None
        try:
            value = json.loads(self._raw(item.overrides_path).decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise VocabularyError(f"{item.overrides_path} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise VocabularyError(f"{item.overrides_path} must be a JSON object")
        return value

    def metadata_for(self, item: RemoteSet, data: bytes) -> dict[str, str]:
        # Hash what was downloaded, not what was listed, so a push between the
        # two requests is caught by the next update check instead of hidden.
        return {"source": self.source_id(item.path), "remote_sha": git_blob_sha(data)}


@dataclass(frozen=True)
class InstalledRemote:
    name: str
    source: str
    remote_sha: str


def installed_remote_sets(store: VocabularyStore) -> list[InstalledRemote]:
    """Local sets that were installed from a sets repository."""
    result = []
    for row in store.list_sets():
        try:
            metadata = store.load(row["name"])["metadata"]
        except VocabularyError:
            continue
        source = metadata.get("source", "")
        if source.startswith(SOURCE_PREFIX):
            result.append(
                InstalledRemote(row["name"], source, metadata.get("remote_sha", ""))
            )
    return result


def remote_status(
    repository: RemoteRepository, item: RemoteSet, installed: list[InstalledRemote]
) -> tuple[str, str | None]:
    """Return (``new``/``installed``/``update``, local set name or None)."""
    source = repository.source_id(item.path)
    for local in installed:
        if local.source == source:
            return (
                "installed" if local.remote_sha == item.sha else "update"
            ), local.name
    return "new", None


@dataclass(frozen=True)
class PendingUpdate:
    local: InstalledRemote
    remote: RemoteSet | None  # None when the file was removed from the repository


def find_updates(
    repository: RemoteRepository, store: VocabularyStore
) -> list[PendingUpdate]:
    """Installed sets whose repository file changed or disappeared."""
    installed = [
        item
        for item in installed_remote_sets(store)
        if item.source.startswith(repository.source_id(""))
    ]
    if not installed:
        return []
    by_source = {
        repository.source_id(item.path): item for item in repository.list_sets()
    }
    pending = []
    for local in installed:
        remote = by_source.get(local.source)
        if remote is None or remote.sha != local.remote_sha:
            pending.append(PendingUpdate(local, remote))
    return pending


def analyze_remote_set(
    repository: RemoteRepository, item: RemoteSet, *, name: str, analyze=None
):
    """Download a set and its overrides, then run the normal import analysis."""
    if analyze is None:
        from finnish_cli.sources import analyze_vocabulary_source as analyze

    data = repository.download(item)
    return analyze(
        data,
        name=name,
        overrides=repository.download_overrides(item),
        metadata=repository.metadata_for(item, data),
    )
