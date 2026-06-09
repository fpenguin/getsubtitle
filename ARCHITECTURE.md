# GetSubtitle — Architecture

A map for navigating the codebase. Read `AGENTS.md` for the rules and
conventions; this file is about *where things are*.

**Navigate by name, not by line.** `getsubtitle_core.py` is one large file
(~22k lines) by design. Line numbers in any doc go stale fast, so this map
references function and section names. To jump to something:

```sh
grep -n "def combine_cues" getsubtitle_core.py
```

## Layout

```text
getsubtitle.py          # console entry: calls core.main(), maps CliError → exit 2
getsubtitle_core.py     # everything else (single-file by design)
tests/
  test_core.py          # the suite
  conftest.py           # session fixture: isolates GETSUBTITLE_CONFIG_PATH
  wizard_harness.py     # drives the wizard like a terminal user
  wizard_scenarios/     # one persona/trap per file (the inputs)
  wizard_transcripts/   # golden transcripts (the expected output)
pyproject.toml          # deps + optional reading-aid extras; version
.github/workflows/ci.yml
```

Public surface (functions/classes tests import) must stay importable from
`getsubtitle_core` — don't split the module without updating the suite.

## Entry & dispatch

`getsubtitle.py` → `getsubtitle_core.main(argv)`. `main()` routes, in order:

1. **Wizard** — `-i` / `--interactive` / `interactive` → `interactive_main`.
2. **Standalone verbs** — `setup` → `setup_main`, `doctor` → `doctor_main`,
   `run` → `run_main` (named-pipeline registry).
3. **Topic help** — `--help <topic>` is handled before argparse.
4. **`--config FILE.toml`** (anywhere in argv) → `pipeline_from_config_main`.
5. **Inline pipeline** (`--fetch/--translate/--modify/--merge`) → `pipeline_main`.
6. **Subcommand sniff** — first positional: `merge`→`combine_main`,
   `translate`→`translate_main`, `modify`→`modify_main`, `fetch`→`fetch_main`,
   `config`→`config_main`, `sources`→`sources_main`.
7. **Bare URL** (no subcommand) → the URL download flow.

Each subcommand has a `build_*_parser()` (argparse) and a `*_main(argv)`.

## The pipeline (canonical order: fetch → translate → modify → merge)

Verbs always execute in this order regardless of how they're typed. `Rename`
is a separate maintenance mode, not part of the pipeline.

| Verb | Entry | Does | Key functions |
|---|---|---|---|
| **Fetch** | `fetch_main` / URL flow | Find + download human subtitles by URL/title/local scan | URL resolution + providers (below) |
| **Translate** | `translate_main` | Fill *missing* languages via MT | `translate_srt_file`, MT engines, `mt_source` picker |
| **Modify** | `modify_main` | Clean cues, add reading aids, SAMI→SRT, MKV extract | reading-aid generators, `_apply_reading_to_args` |
| **Merge** | `combine_main` (a.k.a. `merge`) | Stack 2+ languages into one synced file | `combine_cues`, `read_cues_from_file`, parsers |
| **Rename** | `_wizard_q_rename` (wizard-only) | Batch filename cleanup | `_rename_*` family |

`pipeline_main` chains verbs; `pipeline_from_config_main` loads a TOML, layers
CLI overrides, then calls `pipeline_main`. `split_pipeline_argv` splits a
chained argv into per-verb blocks.

## Cross-cutting layers

**URL & metadata resolution.** `infer_from_catalog_url` (IMDb/TMDB/…),
`fetch_anilist_info` (AniList, anime), plus bridges (AniList↔IMDb/TMDB/TVDB,
Netflix work-id→IMDb/TMDB via Wikidata). `is_movie` flattens the output layout.

**Providers.** Provider metadata/search JSON goes through `request_json` (mock
this for most provider tests). HTML pages use `request_text`; subtitle file
bodies use `download_bytes`. Jimaku (anime, AniList id), Wyzie (movie/TV by
IMDb/TMDB id), SubDL, and the experimental Subdivx/Addic7ed scrapers live here.

**Machine translation.** Engines argos / ollama / deepl. `translate_srt_file`
runs a file through the chosen engine; the per-target source picker honors
`mt_source` (e.g. `ko ← ja`). MT output is suffixed `.mt.` so it never masks
human subtitles.

**Reading aids.** Per-language generators: Japanese furigana
(`generate_furigana`, sudachipy), Korean (`romanize_korean`), Mandarin pinyin,
Cantonese jyutping. `_apply_reading_to_args` maps the `--reading LANG:MODE`
SPEC onto the per-language attrs the generators read. Ship status + modes live
in the `_READING_*` tables. Each backend is an optional pip extra.

**Subtitle I/O & merge engine.** `read_cues_from_file` dispatches on extension
to `parse_srt` / `parse_vtt` / `parse_smi_for_lang` / ASS parsing. `combine_cues`
is the heart of merge: the master language is the timing authority, each target
cue is matched by time overlap, and `lang_order` sets stack order. Output
filename is built by `combined_output_name` / `combined_output_path`.

**Config.** `config_path()` resolves the settings file (honors
`GETSUBTITLE_CONFIG_PATH`, then XDG/APPDATA). `load_user_config()` parses it;
`validate_user_config()` whitelists known keys per section. Sections mirror the
pipeline: `[fetch] [translate] [modify] [merge] [output] [experimental]`.

Precedence (low → high): **built-in defaults < user_settings.toml <
`--config` TOML < CLI flags**. Note: some argparse defaults are *derived* from
config (e.g. `build_combine_parser` reads `[merge].reading`) — which is exactly
why the test suite isolates config (see Tests).

**Interactive wizard.** `interactive_main` → `_run_wizard`, which walks
`_WIZARD_STEPS` (an ordered `(label, fn)` table; questions gate on
`state.steps`). Every menu routes through `_wizard_read_choice` (Enter→default,
invalid→re-prompt, never abort). `_wizard_apply_smart_defaults` fills the
answers the wizard no longer asks (display order, master, cleanup, format,
text size) and surfaces them in the banner. `_wizard_emit_cli` /
`_wizard_emit_toml` turn the answers into a runnable command / workflow file.

## Tests & CI

- `python -m pytest tests/test_core.py -q` runs everything. Network is mocked
  (patch `request_json`), so tests run offline.
- `tests/conftest.py` isolates `GETSUBTITLE_CONFIG_PATH` so the suite never
  reads a developer's real `~/.config/getsubtitle/` (config leaks would
  silently change argparse defaults — see Config above).
- **Wizard** behavior is pinned end-to-end: `wizard_scenarios/*.py` define
  inputs, `wizard_harness.py` drives `interactive_main`, and
  `wizard_transcripts/*.txt` are byte-compared. Re-bless with
  `WIZARD_UPDATE_SNAPSHOTS=1` and review the diff as a UX review.
- CI (`.github/workflows/ci.yml`) runs the suite on Python 3.10/3.11 per push/PR.

## Conventions that shape the code

- **Raise `CliError`** for expected failures — never let a traceback reach the
  user. `getsubtitle.py` turns it into one line + exit 2.
- **SRT is the production baseline.** VTT/ASS are secondary outputs.
- **Numeric menus** in the wizard; free text only for languages/paths/URLs/
  titles/season-episode.
- **Movies** have no `SxxExx`; `parse_episode_marker` returns synthetic
  `(0, 0)` so the scanner still finds them.
