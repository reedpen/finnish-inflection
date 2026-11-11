import json

import pytest

import finnish_cli.store as vocab_module
from finnish_cli.store import (
    VocabularyStore,
    load_or_rebuild_vocabulary,
    load_vocabulary_document,
    write_vocabulary_document,
)
from finnish_core.vocab import (
    SCHEMA_VERSION,
    VocabularyError,
    make_vocabulary_document,
)


def entry(fin="koira", lemma="koira", eng="dog", pos="N", **extra):
    return {"fin": fin, "lemma": lemma, "eng": eng, "pos": pos, **extra}


def test_versioned_document_round_trips_atomically(tmp_path):
    path = tmp_path / "words.json"
    document = make_vocabulary_document(
        [entry()], source_bytes=b"Front;Back\nkoira;dog\n", name="dogs"
    )

    write_vocabulary_document(path, document)

    loaded = load_vocabulary_document(path)
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["metadata"]["name"] == "dogs"
    assert len(loaded["metadata"]["source_sha256"]) == 64
    assert loaded["entries"] == [entry()]
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"nouns": [], "verbs": []}, "schema version"),
        (
            {
                "schema_version": SCHEMA_VERSION,
                "metadata": {"source_sha256": "0" * 64, "name": "partial"},
                "entries": [{"fin": "olla"}],
            },
            "missing",
        ),
        (
            {
                "schema_version": SCHEMA_VERSION,
                "metadata": {"source_sha256": "0" * 64, "name": "bad"},
                "entries": [
                    entry(fin="olla", lemma="olla", eng="be", pos="V", verb_type=0)
                ],
            },
            "verb_type",
        ),
    ],
)
def test_invalid_documents_are_rejected(payload, message, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VocabularyError, match=message):
        load_vocabulary_document(path)


def test_corrupt_replacement_does_not_destroy_existing_set(tmp_path):
    path = tmp_path / "words.json"
    valid = make_vocabulary_document([entry()], source_bytes=b"old", name="words")
    write_vocabulary_document(path, valid)

    with pytest.raises(VocabularyError):
        write_vocabulary_document(path, {"schema_version": SCHEMA_VERSION})

    assert load_vocabulary_document(path)["entries"] == [entry()]


def test_corrupt_json_and_stale_source_are_rejected(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{interrupted", encoding="utf-8")
    with pytest.raises(VocabularyError, match="could not read"):
        load_vocabulary_document(corrupt)

    cached = tmp_path / "cached.json"
    write_vocabulary_document(
        cached,
        make_vocabulary_document([entry()], source_bytes=b"old source", name="cached"),
    )
    with pytest.raises(VocabularyError, match="stale"):
        load_vocabulary_document(cached, source_bytes=b"new source")


@pytest.mark.parametrize("initial", ["{interrupted", None])
def test_corrupt_or_stale_cache_is_rebuilt_atomically(tmp_path, initial):
    path = tmp_path / "cache.json"
    if initial is None:
        write_vocabulary_document(
            path,
            make_vocabulary_document([entry()], source_bytes=b"old", name="cache"),
        )
    else:
        path.write_text(initial, encoding="utf-8")
    calls = []

    result = load_or_rebuild_vocabulary(
        path,
        source_bytes=b"current",
        rebuild=lambda: (
            calls.append(True)
            or make_vocabulary_document(
                [entry("kissa", "kissa", "cat")],
                source_bytes=b"current",
                name="cache",
            )
        ),
    )

    assert calls == [True]
    assert result["entries"][0]["fin"] == "kissa"
    assert load_vocabulary_document(path, source_bytes=b"current") == result
    assert not path.with_suffix(".json.tmp").exists()


def test_named_store_can_install_select_list_replace_and_remove(tmp_path):
    store = VocabularyStore(tmp_path)
    first = make_vocabulary_document([entry()], source_bytes=b"first", name="animals")
    replacement = make_vocabulary_document(
        [entry("kissa", "kissa", "cat")], source_bytes=b"second", name="animals"
    )

    store.install("animals", first)
    assert store.list_sets() == [{"name": "animals", "selected": False, "entries": 1}]
    store.select("animals")
    assert store.selected_name() == "animals"
    with pytest.raises(VocabularyError, match="already exists"):
        store.install("animals", replacement)
    store.install("animals", replacement, replace=True)
    assert store.load("animals")["entries"][0]["fin"] == "kissa"
    assert store.selected_name() == "animals"
    store.remove("animals")
    assert store.list_sets() == []
    assert store.selected_name() is None


def test_set_names_cannot_escape_the_store(tmp_path):
    store = VocabularyStore(tmp_path)
    with pytest.raises(VocabularyError, match="name"):
        store.install(
            "../escape",
            make_vocabulary_document([entry()], source_bytes=b"x", name="x"),
        )


def test_corrupt_selected_set_is_quarantined_and_recovers_to_default(tmp_path):
    store = VocabularyStore(tmp_path / "store")
    corrupt = store.root / "lesson.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{interrupted", encoding="utf-8")
    store.selection_path.write_text("lesson\n", encoding="utf-8")

    document, notice = store.load_selected()

    assert document is None
    assert "Using the default set" in notice
    assert "lesson.json.invalid" in notice
    assert not corrupt.exists()
    assert (store.root / "lesson.json.invalid").exists()
    assert not store.selection_path.exists()


def test_missing_selected_set_clears_pointer_with_actionable_notice(tmp_path):
    store = VocabularyStore(tmp_path / "store")
    store.root.mkdir(parents=True)
    store.selection_path.write_text("gone\n", encoding="utf-8")

    document, notice = store.load_selected()

    assert document is None
    assert "missing" in notice
    assert "default" in notice
    assert not store.selection_path.exists()


def test_runtime_warns_and_uses_packaged_default_after_selected_set_corruption(
    monkeypatch, tmp_path
):
    store = VocabularyStore(tmp_path / "store")
    store.root.mkdir(parents=True)
    (store.root / "broken.json").write_text("not json", encoding="utf-8")
    store.selection_path.write_text("broken\n", encoding="utf-8")
    monkeypatch.setattr(vocab_module, "VocabularyStore", lambda: store)

    with pytest.warns(RuntimeWarning, match="Using the default set"):
        nouns, verbs = vocab_module.load_book_of_mormon_vocab()

    assert nouns and verbs
