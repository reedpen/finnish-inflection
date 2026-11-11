from src.data.importer import ImportPreview
from src.data.remote import RemoteRepository
from src.data.vocab import VocabularyStore, make_vocabulary_document
from src.ui import vocabulary as menu


def document(fin="koira"):
    return make_vocabulary_document(
        [{"fin": fin, "lemma": fin, "eng": "dog", "pos": "N"}],
        source_bytes=fin.encode(),
        name="lesson",
    )


class Answer:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


def test_listing_marks_default_or_selected_custom_set(tmp_path):
    store = VocabularyStore(tmp_path)
    store.install("lesson", document())

    assert menu.vocabulary_listing(store) == [
        {"name": "default", "selected": True, "entries": "built-in"},
        {"name": "lesson", "selected": False, "entries": 1},
    ]

    store.select("lesson")
    assert [
        row["name"] for row in menu.vocabulary_listing(store) if row["selected"]
    ] == ["lesson"]


def test_interactive_manager_selects_a_custom_set(monkeypatch, tmp_path):
    store = VocabularyStore(tmp_path)
    store.install("lesson", document())
    replies = iter(["select", "lesson", "back"])
    monkeypatch.setattr(menu.inquirer, "select", lambda **_: Answer(next(replies)))

    assert menu.manage_vocabulary(store) is False
    assert store.selected_name() == "lesson"


def test_interactive_file_import_previews_confirms_and_installs(monkeypatch, tmp_path):
    store = VocabularyStore(tmp_path / "store")
    source = tmp_path / "Kappale 1.csv"
    source.write_text("koira;dog\n", encoding="utf-8")
    imported = document("kissa")
    preview = ImportPreview(imported["entries"], [], [], [], [], imported)
    paths = iter([f"'{source}'", ""])
    names = []
    analyzed = []
    monkeypatch.setattr(menu.inquirer, "filepath", lambda **kw: Answer(next(paths)))
    monkeypatch.setattr(
        menu.inquirer,
        "text",
        lambda **kw: names.append(kw["default"]) or Answer("lesson"),
    )
    monkeypatch.setattr(menu.inquirer, "confirm", lambda **_: Answer(True))
    monkeypatch.setattr(
        menu,
        "analyze_vocabulary_source",
        lambda source, **_: analyzed.append(source) or preview,
    )

    menu._import_from_file(store)

    assert names == ["Kappale-1"]
    assert analyzed == [f"'{source}'"]
    assert store.load("lesson")["entries"][0]["fin"] == "kissa"


def test_interactive_paste_analyzes_the_pasted_text(monkeypatch, tmp_path):
    store = VocabularyStore(tmp_path)
    imported = document("kissa")
    preview = ImportPreview(imported["entries"], [], [], [], [], imported)
    replies = iter(["kissa\tcat\n", "pasted"])
    analyzed = []
    monkeypatch.setattr(menu.inquirer, "text", lambda **_: Answer(next(replies)))
    monkeypatch.setattr(menu.inquirer, "confirm", lambda **_: Answer(True))
    monkeypatch.setattr(
        menu,
        "analyze_vocabulary_source",
        lambda source, **_: analyzed.append(source) or preview,
    )

    menu._import_from_paste(store)

    assert analyzed == [b"kissa\tcat\n"]
    assert store.load("pasted")["entries"][0]["fin"] == "kissa"


def test_interactive_browse_installs_an_online_set(monkeypatch, tmp_path):
    from tests.test_remote_sets import FILES, FakeGitHub, fake_analyze

    store = VocabularyStore(tmp_path)
    repository = RemoteRepository("owner/sets", fetch=FakeGitHub(FILES))
    shown = []

    def select(**kw):
        shown.append([choice["name"] for choice in kw["choices"]])
        return Answer(kw["choices"][1]["value"])

    monkeypatch.setattr(menu.inquirer, "select", select)
    monkeypatch.setattr(menu.inquirer, "text", lambda **kw: Answer(kw["default"]))
    monkeypatch.setattr(menu.inquirer, "confirm", lambda **_: Answer(True))
    monkeypatch.setattr(menu, "analyze_vocabulary_source", fake_analyze)

    menu._browse_online(store, repository)
    menu._browse_online(store, repository)

    assert shown[0] == ["päivä", "starter/verbs", "Back"]
    assert shown[1][1] == "starter/verbs  ✓ installed"
    assert store.load("starter-verbs")["metadata"]["source"].endswith(
        "sets/starter/verbs.csv"
    )
