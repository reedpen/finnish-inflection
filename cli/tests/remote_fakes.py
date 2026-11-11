"""A fake GitHub and analyzer shared by the online-sets tests."""

import json

from finnish_cli.remote import git_blob_sha
from finnish_core.importer import import_vocabulary
from finnish_core.vocab import VocabularyError


class FakeGitHub:
    """Serves a repository tree and raw files the way GitHub does."""

    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
        self.requests: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.requests.append(url)
        if url.startswith("https://api.github.com/repos/owner/sets/git/trees/main"):
            tree = [{"path": "sets", "type": "tree", "sha": "0" * 40}]
            tree += [
                {
                    "path": path,
                    "type": "blob",
                    "sha": git_blob_sha(data),
                    "size": len(data),
                }
                for path, data in self.files.items()
            ]
            return json.dumps({"tree": tree, "truncated": False}).encode()
        prefix = "https://raw.githubusercontent.com/owner/sets/main/"
        path = url.removeprefix(prefix).replace("%C3%A4", "ä")
        if url.startswith(prefix) and path in self.files:
            return self.files[path]
        raise VocabularyError(f"not found: {url}")


FILES = {
    "README.md": b"# Sets\n",
    "sets/starter/verbs.csv": "Front;Back\npuhua;to speak\n".encode(),
    "sets/starter/verbs.overrides.json": b'{"olla": null}',
    "sets/päivä.tsv": "päivä\tday\n".encode(),
    "sets/notes.md": b"not a set",
}


def fake_analyze(source, *, name, overrides=None, metadata=None):
    return import_vocabulary(
        source,
        analyzer=lambda fin, eng: ("V" if eng.startswith("to ") else "N", fin),
        name=name,
        overrides=overrides,
        metadata=metadata,
    )
