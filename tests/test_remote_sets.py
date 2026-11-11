import json

import pytest

import src.cli as cli_module
from src.cli import main
from src.data.importer import import_vocabulary
from src.data.remote import (
    RemoteRepository,
    analyze_remote_set,
    find_updates,
    git_blob_sha,
    installed_remote_sets,
    remote_status,
)
from src.data.vocab import VocabularyError, VocabularyStore


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


def repository(github: FakeGitHub) -> RemoteRepository:
    return RemoteRepository("owner/sets", fetch=github)


def test_listing_reflects_word_lists_in_the_sets_folder():
    sets = repository(FakeGitHub(FILES)).list_sets()

    assert [(item.title, item.name) for item in sets] == [
        ("päivä", "paiva"),
        ("starter/verbs", "starter-verbs"),
    ]
    assert sets[1].overrides_path == "sets/starter/verbs.overrides.json"
    assert sets[0].overrides_path is None


def test_find_accepts_name_title_or_path():
    repo = repository(FakeGitHub(FILES))
    sets = repo.list_sets()

    for query in ("starter-verbs", "Starter/Verbs", "sets/starter/verbs.csv"):
        assert repo.find(query, sets).path == "sets/starter/verbs.csv"
    with pytest.raises(VocabularyError, match="no set named 'nope'"):
        repo.find("nope", sets)


@pytest.mark.parametrize("spec", ["not-a-repo", "owner/repo/extra", "../x"])
def test_repository_spec_is_validated(spec):
    with pytest.raises(VocabularyError, match="owner/repo"):
        RemoteRepository(spec)


def test_repository_spec_comes_from_environment(monkeypatch):
    monkeypatch.setenv("FINNISH_DRILL_SETS_REPO", "someone/words@dev")

    repo = RemoteRepository()

    assert (repo.repository, repo.ref) == ("someone/words", "dev")


def test_install_records_source_and_detects_updates(tmp_path):
    github = FakeGitHub(FILES)
    repo = repository(github)
    store = VocabularyStore(tmp_path)
    item = repo.find("starter-verbs")

    preview = analyze_remote_set(repo, item, name="verbs", analyze=fake_analyze)
    store.install("verbs", preview.document)

    metadata = store.load("verbs")["metadata"]
    assert metadata["source"] == "github:owner/sets/sets/starter/verbs.csv"
    assert metadata["remote_sha"] == item.sha
    assert remote_status(repo, item, installed_remote_sets(store)) == (
        "installed",
        "verbs",
    )
    assert find_updates(repo, store) == []

    github.files["sets/starter/verbs.csv"] += "olla;to be\nsanoa;to say\n".encode()
    changed = repo.find("starter-verbs")
    assert remote_status(repo, changed, installed_remote_sets(store))[0] == "update"
    [pending] = find_updates(repo, store)
    assert pending.local.name == "verbs" and pending.remote == changed

    del github.files["sets/starter/verbs.csv"]
    [gone] = find_updates(repo, store)
    assert gone.remote is None


def test_repository_overrides_are_applied(tmp_path):
    github = FakeGitHub(
        {
            **FILES,
            "sets/starter/verbs.csv": "puhua;to speak\nolla;to be\n".encode(),
        }
    )
    repo = repository(github)

    preview = analyze_remote_set(
        repo, repo.find("starter-verbs"), name="v", analyze=fake_analyze
    )

    assert [item["fin"] for item in preview.accepted] == ["puhua"]
    assert preview.excluded == ["olla"]


def test_cli_browse_get_and_update(monkeypatch, tmp_path, capsys):
    github = FakeGitHub(FILES)
    monkeypatch.setattr(
        cli_module, "RemoteRepository", lambda spec=None: repository(github)
    )
    monkeypatch.setattr(
        cli_module, "VocabularyStore", lambda: VocabularyStore(tmp_path)
    )
    monkeypatch.setattr(cli_module, "analyze_vocabulary_source", fake_analyze)

    assert main(["vocab", "browse"]) == 0
    assert "starter-verbs\tstarter/verbs" in capsys.readouterr().out

    assert main(["vocab", "get", "starter/verbs", "--yes"]) == 0
    assert "Installed vocabulary: starter-verbs" in capsys.readouterr().out

    assert main(["vocab", "browse"]) == 0
    assert "starter/verbs\tinstalled" in capsys.readouterr().out

    assert main(["vocab", "update"]) == 0
    assert "up to date" in capsys.readouterr().out

    github.files["sets/starter/verbs.csv"] += "sanoa;to say\n".encode()
    assert main(["vocab", "update", "--yes"]) == 0
    assert "Installed vocabulary: starter-verbs" in capsys.readouterr().out
    entries = VocabularyStore(tmp_path).load("starter-verbs")["entries"]
    assert [item["fin"] for item in entries] == ["puhua", "sanoa"]

    # Getting the same set again under its installed name replaces it in place.
    assert main(["vocab", "get", "starter-verbs", "--yes"]) == 0


def test_cli_get_reports_network_errors(monkeypatch, capsys):
    def offline(url, headers):
        raise VocabularyError("could not reach GitHub (offline)")

    monkeypatch.setattr(
        cli_module,
        "RemoteRepository",
        lambda spec=None: RemoteRepository("owner/sets", fetch=offline),
    )

    assert main(["vocab", "get", "anything"]) == 2
    assert "could not reach GitHub" in capsys.readouterr().err
