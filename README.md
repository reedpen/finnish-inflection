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
- **Optional vim key bindings** for menus and answers.
- **Custom vocabulary.** Import your own word lists from CSV or plain text.
  Every word is checked against the morphology model first.

## Quick start

Requires Python 3.11 or newer.

```bash
# with uv
uv tool install .
finnish-drill

# or with pip
python -m pip install .
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
| Manage vocabulary | Import, preview, select, and remove vocabulary sets |
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

### Vim key bindings

Start with `finnish-drill --vim`, or set `FINNISH_DRILL_VIM=1` in your shell
profile, to use vi key bindings throughout:

- **Menus and checklists:** `j`/`k` move down and up. The arrow keys still work.
- **Answer prompt and text fields:** full vi line editing. You start in insert
  mode, and Esc switches to normal mode (`0`, `$`, `w`, `b`, `x`, `D`, `cw`, and
  so on). Enter submits from either mode.

The drill commands (`h`, `s`, `b`, `q`) are unchanged. You type them as an
answer in insert mode.

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

### Importing a word list

You only supply the Finnish word and an English hint. The part of speech
(noun, adjective, or verb) and the verb type are detected automatically.

Files must be UTF-8 and use the `.csv` or `.txt` extension, which determines
the format:

- **CSV**, semicolon-delimited, with the exact header `Front;Back`:

  ```text
  Front;Back
  koira;dog
  puhua;to speak
  ```

- **Plain text**, one `Finnish,English` pair per line:

  ```text
  koira,dog
  puhua,to speak
  ```

Ready-to-copy samples are in [`examples/vocabulary.csv`](examples/vocabulary.csv)
and [`examples/vocabulary.txt`](examples/vocabulary.txt).

```bash
finnish-drill vocab import lesson-1 examples/vocabulary.csv   # preview, then confirm
finnish-drill vocab list                                      # show all sets
finnish-drill vocab select lesson-1                           # use it for future drills
finnish-drill vocab select default                            # back to the starter set
finnish-drill vocab remove lesson-1
```

The same workflow is available under **Manage vocabulary** in the interactive
menu.

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
finnish-drill --vim                Use vi key bindings (or FINNISH_DRILL_VIM=1)
finnish-drill vocab import NAME PATH [--overrides FILE] [--replace] [--yes]
finnish-drill vocab list
finnish-drill vocab select NAME    (use "default" for the built-in set)
finnish-drill vocab remove NAME
```

## Installation options

**pip**

```bash
python -m pip install .                       # install from a checkout
python -m pip install dist/finnish_inflection_cli-*.whl   # install a built wheel
python -m pip install --upgrade .             # upgrade
python -m pip uninstall finnish-inflection-cli
```

**uv tool** (an isolated user-level install)

```bash
uv tool install .
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
uv run ruff check src tests main.py
uv run ruff format --check src tests main.py
```

CI runs ruff and the hermetic suite on Python 3.11 and 3.14. It also builds the
wheel and sdist and smoke-tests the installed command outside the checkout.

### Project layout

```text
src/
  cli.py          argparse entry point and `vocab` subcommands
  main.py         startup: model download, vocabulary load, menu
  ui/             interactive menus, drill loop, vocabulary manager
  domain/         question pools, session scheduling and stats, saved settings
  nlp/            UralicNLP wrapper and human-readable → Omorfi tag mapping
  data/           vocabulary store, importer, packaged starter vocabulary
  scripts/        maintainer tools for building and checking vocabulary
tests/            pytest suite (integration tests are marked `integration`)
examples/         sample import files
```

### Maintaining the starter vocabulary

The canonical source is `src/data/default_vocab.csv` (columns
`Front;Back;Lemma;POS;VerbType`). A deterministic build turns it into the
packaged `src/data/default_vocab.json`. Analyzer ambiguities are resolved in
`default_vocab.overrides.json`. Those decisions, source fingerprints, and the
validation status are recorded in `default_vocab.review.json`.

To add a word, append a row to the CSV. Unlike user imports, you fill in the
lemma, part of speech (`N`, `A`, or `V`), and verb type (1–6, verbs only)
yourself. Then regenerate the JSON and review report, and verify them:

```bash
# Regenerate default_vocab.json and default_vocab.review.json
python -m src.scripts.build_default_vocab

# Verify the chain: source/override hashes, stale artifacts, duplicates,
# empty values, unsupported POS, and verbs without a type from 1 to 6
python -m src.scripts.build_default_vocab --check

# Also load the real model and check every lemma plus a generated form
python -m src.scripts.build_default_vocab --check --validate-model
```

Run the model check after any change to the canonical list. It is opt-in
because it needs the downloaded UralicNLP data. The checked-in report records
only the opt-in status and the command, not machine-specific results.

To build a reviewed vocabulary from an arbitrary word list:

```bash
uv run python -m src.scripts.build_cache words.csv \
  --overrides review.json --output reviewed.json --report review-report.json
```

The build writes a review report and refuses to publish while any entries
remain rejected.

## License and data provenance

The software and the maintainer-authored starter vocabulary are **all rights
reserved** (`LicenseRef-Proprietary`); see [`LICENSE`](LICENSE).

The repository also contains a historical `book_of_mormon_complete.csv` and an
old `data/vocab_cache.json`. Neither has a recorded source URL or
redistribution license. They are **not** covered by the license, **not** used as
the default vocabulary, and **not** included in built distributions.
