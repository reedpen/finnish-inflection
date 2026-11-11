# Finnish Inflection CLI

An interactive terminal drill for Finnish noun, adjective, and verb inflection.
Pick the cases, tenses, persons, or participles you want to work on, and the
drill quizzes you on real words. It uses UralicNLP's Finnish model to generate
the answers.

```text
--- Noun Drill ---
Progress: 3/10
Word: talo (house)
Target: Inessive (-ssa) Plural
h/hint · s/skip or Enter · b/back · q/quit · Ctrl+C back · Ctrl+D quit
Answer: taloisa
Incorrect, try again.
Answer: h
Hint: 'a' at position 7 is wrong
Answer: taloissa
```

## Features

- **Three drills:** nouns and adjectives, conjugated verbs, and declined
  participles.
- **All 14 cases**, singular and plural, including the rarer abessive,
  comitative, and instructive.
- **Verbs** in the present, past, and conditional, for all six persons and the
  passive. You can filter by verb type (1–6).
- **Participles:** VA, NUT, TAVA, TU, agent (MA), and negative (MATON),
  declined in any case.
- **Progressive hints.** A hint points out the first wrong letter in your last
  attempt. Without an attempt, each hint reveals one more letter.
- **Presets and saved setups.** Beginner and focused presets give one-step
  practice. Your last setup is remembered for each drill.
- **Vim-style `j`/`k` navigation** in every menu.
- **Custom vocabulary.** Install shared sets from
  [finnish-vocab-sets](https://github.com/reedpen/finnish-vocab-sets), or import
  your own lists from a file, a paste, or a Quizlet or Anki export.
  Every word is checked against the morphology model first.

## Quick start

Requires Python 3.11 or newer.

```bash
# with uv
uv tool install ./cli
finnish-drill

# or with pip (install the shared library first)
python -m pip install ./core ./cli
finnish-drill
```

> [!NOTE]
> On first launch, UralicNLP downloads the Finnish morphology model. This can
> take several minutes. If the download fails, see
> [Troubleshooting](#troubleshooting).

## Practicing

### Main menu

| Option | What it does |
| --- | --- |
| Beginner nouns / verbs — quick start | Starts a 10-question preset immediately |
| Resume last session | Repeats your most recent setup |
| Configure noun / verb / participle practice | Choose a preset, repeat or edit your last setup, or customize from scratch |
| Manage vocabulary | Import, browse online, update, select, and remove vocabulary sets |
| Reset all saved preferences | Clears every remembered setup |

When you customize, you pick the forms in checklists (each has an **All**
option). Then you choose a session length: 10, 20, 50, or endless.

### Presets

| Drill | Beginner (10 questions) | Focused (20 questions) |
| --- | --- | --- |
| Noun | Nominative, genitive, partitive; singular | The six locative cases; singular and plural |
| Verb | Type 1, present, singular persons | All types, present, all six persons |
| Participle | Present active (VA), nominative singular | VA and NUT, nominative singular and plural |

### Commands during a drill

| Input | Action |
| --- | --- |
| *your answer* | Check the answer (case-insensitive). Wrong answers can be retried. |
| `h`, `hint` | Show a progressive hint |
| `s`, `skip`, or Enter | Reveal the answer and move on |
| `b`, `back`, Ctrl+C | End the session and return to the drill menu |
| `q`, `quit`, Ctrl+D | End the session and quit |

Use ↑/↓ to recall earlier answers in the current run. Where Finnish allows more
than one correct form, any of them is accepted.

### Menu navigation

In every menu and checklist, `j`/`k`, the arrow keys, and Ctrl+N/Ctrl+P all
move down and up. Space toggles a checklist item, and Enter confirms.

After each session you get a summary of answers, first-try successes,
successes after retries, retries, hints, and skips. You can then replay,
reconfigure, go back to the menu, or quit.

## Vocabulary

The built-in starter set has 18 nouns, 6 adjectives, and 11 verbs, with every
entry reviewed by hand. To practice other words, import them as a named
vocabulary set and select it.

Drills use **only the selected set**. Importing doesn't add words to the
starter vocabulary; it creates a separate list. If you want the starter words
too, put them in your file as well. (To change the built-in list itself, see
[Maintaining the starter vocabulary](#maintaining-the-starter-vocabulary).)

### Online sets

Shared sets live in
[reedpen/finnish-vocab-sets](https://github.com/reedpen/finnish-vocab-sets).
The app lists that repository live, so a set appears here as soon as it's
pushed there.

```bash
finnish-drill vocab browse                 # list the online sets
finnish-drill vocab get starter-verbs      # preview, then confirm
finnish-drill vocab update                 # reinstall sets that changed online
```

In the interactive menu, use **Manage vocabulary → Browse online sets** and
**Update online sets**. Installed sets are marked `✓ installed`, or
`↻ update available` when their file changed online.

To use another repository with the same layout, pass `--repo owner/repo[@branch]`
or set `FINNISH_DRILL_SETS_REPO`. Without a token, GitHub allows 60 listings an
hour; set `GITHUB_TOKEN` if you hit that limit.

### Importing a word list

You only supply the Finnish word and an English hint. The part of speech
(noun, adjective, or verb) and the verb type are detected automatically.

Put one word per line: the Finnish word, then its English meaning. The
separator is detected, so Quizlet exports, Anki exports, spreadsheet copies,
and hand-typed lists all work:

```text
koira	dog              tab (Quizlet, Anki, spreadsheets)
koira;dog              semicolon (Anki CSV)
puhua,to speak, to talk    comma; later commas stay in the English
```

A header row (`Front;Back`, `Finnish,English`, `Suomi;Englanti`, …) is
optional, and lines starting with `#` are ignored. Files must be UTF-8. A line
that can't be split is reported in the preview instead of failing the import.

The Finnish words may be in either column. A header row says which one;
without one, the import checks a sample of the words against the Finnish
model (and looks for letters like ä and ö, and English hints like "to run") to
decide. The preview says which column it read as Finnish and why: from the
header row, detected, or unsure. If it guessed wrong, or wasn't sure, choose
the column yourself with `--finnish-column 1` or `--finnish-column 2`. (In a
comma-separated list with the Finnish word last, the earlier commas stay in
the English.)

```bash
finnish-drill vocab import lesson-3 english-first.txt --finnish-column 2
```

Ready-to-copy samples are in [`examples/vocabulary.csv`](examples/vocabulary.csv)
and [`examples/vocabulary.txt`](examples/vocabulary.txt).

```bash
finnish-drill vocab import lesson-1 examples/vocabulary.csv   # preview, then confirm
finnish-drill vocab import lesson-1 ~/Downloads/'My Words.txt'
wl-paste | finnish-drill vocab import lesson-1 -                # clipboard (pbpaste on macOS)
finnish-drill vocab list                                      # show all sets
finnish-drill vocab select lesson-1                           # use it for future drills
finnish-drill vocab select default                            # back to the starter set
finnish-drill vocab remove lesson-1
```

In the interactive menu, **Manage vocabulary** offers:

- **Import from a file.** Tab completes paths, and you can drag a file into
  the terminal.
- **Paste a word list.** Paste or type the words, then press Esc then Enter to
  finish.

### Adding more words later

There is no command to append to a set. Keep your word list as a file, add the
new words to it, and re-import it under the same name:

```bash
finnish-drill vocab import lesson-1 my-words.txt --replace
```

The replacement is atomic, and the set stays selected.

Before installing, the import analyzes every word. It reports how many entries
were accepted, corrected, ambiguous, excluded, and rejected, and asks for
confirmation. A cancelled or failed import never changes your existing sets.

| Flag | Purpose |
| --- | --- |
| `--replace` | Atomically replace an existing set with the same name |
| `--yes` | Install without the confirmation prompt (for reviewed automation) |
| `--overrides FILE` | Resolve ambiguous words (see below) |
| `--finnish-column 1\|2` | Which column holds the Finnish words (default: header row, or detected) |

### Resolving ambiguous words

Some words have more than one analysis. For example, *kuusi* means both "six"
and "spruce". These words are rejected until you resolve them in an overrides
file. The file maps each Finnish word to its lemma and part of speech (`N`,
`A`, or `V`), or to `null` to leave it out:

```json
{
  "kuusi": {"lemma": "kuusi", "pos": "N"},
  "pois": null
}
```

```bash
finnish-drill vocab import lesson-2 words.txt --overrides review.json
```

Imported sets are stored in your operating system's standard user-data
directory. Drill preferences are stored in its user-config directory.

## Command reference

```text
finnish-drill                      Start the interactive drill
finnish-drill --help               Show help
finnish-drill --version            Show the installed version
finnish-drill --debug              Show full tracebacks on startup errors
finnish-drill vocab import NAME PATH [--overrides FILE] [--finnish-column 1|2]
                                   [--replace] [--yes]
                                   (PATH may be - for standard input)
finnish-drill vocab browse [--repo OWNER/REPO]
finnish-drill vocab get SET [--name NAME] [--replace] [--yes] [--repo OWNER/REPO]
finnish-drill vocab update [--yes] [--repo OWNER/REPO]
finnish-drill vocab list
finnish-drill vocab select NAME    (use "default" for the built-in set)
finnish-drill vocab remove NAME
```

## Installation options

**pip**

```bash
python -m pip install ./core ./cli            # install from a checkout
python -m pip install dist/*.whl              # install built wheels (both)
python -m pip install --upgrade ./core ./cli  # upgrade
python -m pip uninstall finnish-inflection-cli finnish-inflection-core
```

**uv tool** (an isolated user-level install)

```bash
uv tool install ./cli
uv tool upgrade finnish-inflection-cli
uv tool uninstall finnish-inflection-cli
```

**uv project environment** (for development)

```bash
uv sync
uv run finnish-drill
```

## Troubleshooting

**The drill fails at startup or the model download fails.** UralicNLP must
download the Finnish model on first use. Check your network connection, free
disk space, and write permissions for the UralicNLP data directory, then try
again. For a full traceback, run `finnish-drill --debug` or set
`FINNISH_DRILL_DEBUG=1`.

**"No playable questions match that setup."** The selected forms produced no
answers for the current vocabulary. For example, you may have chosen a verb
type that has no verbs in the active set. Select more forms or switch
vocabulary sets.

**A saved setup is reported as invalid.** It was probably saved by an older
version. Choose **Reset saved setup** for that drill, or **Reset all saved
preferences** from the main menu.

## Development

```bash
uv sync
uv run pytest                    # fast hermetic suite; does not need the model
uv run pytest -m integration     # uses the real Finnish model (download it first)
uv run ruff check core cli
uv run ruff format --check core cli
uv run python -m finnish_cli     # run the drill from the checkout
```

CI runs ruff and the hermetic suite on Python 3.11 and 3.14. It also builds
both packages and smoke-tests the installed command outside the checkout.

### Project layout

The repository holds two packages, developed together as a uv workspace:

```text
core/       finnish-inflection-core (import finnish_core): the shared library
  morphology.py   UralicNLP wrapper with an injectable model
  forms.py        human-readable form labels → Omorfi tags (the stable form ids)
  paradigm.py     full inflection tables and form lookups
  vocab.py        the vocabulary document format and validation
  importer.py     word-list parsing, analysis, and the import preview
  questions.py    question pools for each drill
  session.py      session scheduling and statistics
  hints.py        answer checking and progressive hints
  settings.py     drill selections and presets
  learning.py     daily review: FSRS scheduling, skill mastery, word classes
  starter/        the packaged starter vocabulary and its build tool
cli/        finnish-inflection-cli (import finnish_cli): the terminal app
  cli.py          argparse entry point and `vocab` subcommands
  app.py          startup: model download, vocabulary load, menu
  store.py        named vocabulary sets in the user data directory
  sources.py      reading word lists from paths, standard input, or text
  remote.py       the online sets repository
  ui/             interactive menus, drill loop, vocabulary manager
examples/   sample import files
```

The core does no printing, file, or network access of its own; front ends pass
in the morphology model. Tests live in `core/tests` and `cli/tests`
(integration tests are marked `integration`).

### Maintaining the starter vocabulary

The canonical source is `core/src/finnish_core/starter/default_vocab.csv` (columns
`Front;Back;Lemma;POS;VerbType`). A deterministic build turns it into the
packaged `default_vocab.json` beside it. Analyzer ambiguities are resolved in
`default_vocab.overrides.json`. Those decisions, source fingerprints, and the
validation status are recorded in `default_vocab.review.json`.

To add a word, append a row to the CSV. Unlike user imports, you fill in the
lemma, part of speech (`N`, `A`, or `V`), and verb type (1–6, verbs only)
yourself. Then regenerate the JSON and review report, and verify them:

```bash
# Regenerate default_vocab.json and default_vocab.review.json
uv run python -m finnish_core.starter.build

# Verify the chain: source/override hashes, stale artifacts, duplicates,
# empty values, unsupported POS, and verbs without a type from 1 to 6
uv run python -m finnish_core.starter.build --check

# Also load the real model and check every lemma plus a generated form
uv run python -m finnish_core.starter.build --check --validate-model
```

Run the model check after any change to the canonical list. It is opt-in
because it needs the downloaded UralicNLP data. The checked-in report records
only the opt-in status and the command, not machine-specific results.

To build a reviewed vocabulary from an arbitrary word list:

```bash
uv run python -m finnish_cli.scripts.build_cache words.csv \
  --overrides review.json --output reviewed.json --report review-report.json
```

The build writes a review report and refuses to publish while any entries
remain rejected.

## License and data provenance

The software and the maintainer-authored starter vocabulary are licensed under
the [Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE) for attribution.

The Finnish morphology model that uralicNLP downloads on first run is
[Omorfi](https://github.com/flammie/omorfi), which is GPL-licensed. It isn't
part of this repository or its packages.

The repository also contains a historical `book_of_mormon_complete.csv` and an
old `data/vocab_cache.json`. Neither has a recorded source URL or
redistribution license. They are **not** covered by the license, **not** used as
the default vocabulary, and **not** included in built distributions.
