# Roadmap  · v1.1

What ships in v1.0, what's new in v1.1, what's experimental, and what's
on the horizon.

## v1.1 — what's new

- **Interactive workflow builder.** `getsubtitle -i` /
  `getsubtitle --interactive` / `getsubtitle interactive` walks 11
  learner-friendly questions and produces a CLI command, a reusable
  TOML, or a live run with a dry-run preview. Runs a dependency probe
  after Q10 and walks the user through fixing each gap (missing pip
  extras, unreachable Ollama daemon, missing API keys). Auto-saves a
  draft at `~/.cache/getsubtitle/wizard-draft.toml` so an interrupted
  wizard can resume.
- **Reading-aid umbrella.** `--romanization` replaces `--furigana` as
  the canonical CLI flag (`--furigana` stays as a silent alias). The
  spec now covers Japanese (ships now), plus Korean, Mandarin,
  Cantonese, Thai, Arabic, Hindi, Russian (wired through to CLI/TOML
  with backends landing per the planned section below).
- **Naming-consistency renames** (Round 11): canonical TOML keys are
  `[translate].mt_source`, `[modify].reading_format`,
  `[output].retain_folder_structure`; canonical CLI flags are
  `--languages`, `--engine`, `--model`, `--mt-source`,
  `--reading-format`. Every legacy name is still accepted as a silent
  alias so existing scripts and configs keep working. Hyphens and
  underscores in TOML keys are now interchangeable
  (`dry-run` ≡ `dry_run`).
- **Source smoke diagnostics.** Developer scripts under `scripts/` probe
  Korean, Chinese, and European-language subtitle coverage before new
  providers are wired into the main downloader. They check Wyzie coverage,
  candidate community reachability, and local format support such as
  `.smi` conversion, `.ass/.ssa` input, and Unicode SRT parsing.
- **Provider source/status diagnostics.** `getsubtitle sources --check`
  reports Wyzie source availability for the user's configured key, and
  `--debug-providers` now prints a compact table of provider/source counts,
  language tags, formats, and quality flags.

## v1.0 — capabilities

### CLI surface

- Five verbs: `fetch`, `translate`, `modify`, `merge`, `config`.
- Bare URL shape: `getsubtitle URL ...` works as a shortcut for `fetch URL ...`.
- `--subdirectory` on every PATH-based verb walks one level of immediate subdirs and runs the verb per show.
- Pipeline form chains verbs in one call: `getsubtitle --fetch X --translate ollama --modify --merge -l ja,en`. Verbs always execute in canonical order (fetch → translate → modify → merge).
- Config-file form: `getsubtitle --config FILE.toml`. CLI flags layer over the TOML; per-verb inline blocks merge per-section. Two ship-with examples in the repo: `simpsons-s1-en-fr.toml`, `plex-movies-fill-merge.toml`.
- Layered config: built-in defaults < `user_settings.toml` < `--config` TOML < CLI flags.
- Topic-based help: `--help fetch | translate | modify | merge | pipeline | config | keys | furigana | advanced`.

### URL recognition

- **Streaming**: Crunchyroll, Netflix, Hulu, Max (HBO), Disney+, Apple TV+, Paramount+, Peacock, Prime Video.
- **Catalog**: IMDb, TMDB, AniList, MyAnimeList, TheTVDB, Letterboxd, Rotten Tomatoes, Trakt.
- **Metadata bridges**: AniList ↔ IMDb/TMDB/TVDB via Anime-IDs + Wikidata; Netflix work ID → IMDb/TMDB via Wikidata P1874; TheTVDB slug → numeric ID via page scrape.
- **Title-only inputs**: TMDB enrichment auto-resolves IMDb/TMDB IDs when only a title is known (`--set-key tmdb` once).
- **Release-source preference**: `--release-source auto` (default) infers from URL host; `any` disables; or pin to a specific source.
- **Episode-range expansion**: `-e all` works for anime (AniList) and live-action TV (TMDB). `--season` accepts ranges (`1-3`) and comma-lists.

### Subtitle providers

- **Jimaku** — Japanese anime via AniList ID.
- **Wyzie** — movies / TV by IMDb / TMDB ID. TMDB-ID retry when IMDb miss. Local language filter with cache + fallback.
- **SubDL** — direct API fallback by IMDb / TMDB ID when a separate `SUBDL_API_KEY` is configured.
- **Subdivx** (experimental) — Spanish fallback.
- **Addic7ed** (experimental) — Korean fallback. Localized title-alias search lets anime resolve from any of romanized / English / native Japanese / Korean.

### Machine translation

- **Argos** (offline, default), **Ollama** (offline LLM, auto-pull + auto-unload on by default), **DeepL** (online, free tier).
- Per-target source spec: `mt_source = { ko = "ja", es = "en" }` avoids wasteful en→ko / en→ja when better sources are on disk.
- Per-pair Ollama model overrides in `user_settings.toml`'s `[translate.ollama_models]`, or session-only in any `--config` TOML.
- Engine spec accepts `ollama:qwen3:8b` colon-form to pin a model on the CLI.
- Strip inline 漢字（かんじ） readings from `ja` sources before MT (default true) so translators don't see the readings as duplicate content.
- Auto source-language picker prefers grammatically close pairs (ko ← ja, es ← en, en ← anything).
- Explicit per-target overrides via `--mt-source-lang "ko:ja,es:en"`.
- Cue-level progress + deduped error messages.

### Merge (stacking)

- Reads `.srt`, `.vtt`, `.ass/.ssa`, and `.smi` (multi-language SAMI) as input formats. Per-language `:format` hints in `-l ja:vtt,en,ko:smi` pick which source to use when multiple formats coexist.
- VTT ruby `<ruby><rt>` markup collapses to `漢字（かんじ）` parentheticals so furigana survives the read.
- Time-overlap matching with `--sync auto | strict | loose` presets.
- Master language: `--master` flag > `[merge].priority` config > first language in `-l`.
- Inline 漢字（かんじ） readings on the merged Japanese line (`furigana = true`).
- Output formats: `.srt` (default), `.vtt` (asbplayer ruby), `.ass` (experimental).

### Modify (post-processing)

- SAMI `.smi` → SRT conversion. Per-class language mapping (KRCC→ko, ENCC→en, JPCC→ja, …); encoding auto-detect (UTF-8 / UTF-16-BOM / CP949); existing targets skipped unless `--force`.
- Broadcast-caption noise cleanup (currently the Japanese ➡ continuation arrow).
- Single-line cue flatten for asbplayer.
- Japanese furigana side files in srt / ass / vtt (or all three), with `hiragana` or `romaji` mode.

### Output

- Layouts: `archive` (Show/Season XX/), `flat`, `plex` (preserves Show/Season XX structure for in-place library use).
- Filename suffixes: Sonarr-style `.hi`/`.cc`/`.sdh`/`.forced` recognised on input.
- `[output].dry_run = false` (default) auto-triggers live runs for PATH-form fetch.

### Configuration

- `user_settings.toml` at `~/.config/getsubtitle/` (macOS/Linux) or `%APPDATA%\getsubtitle\` (Windows).
- Same section schema as `--config` TOML: `[fetch]`, `[translate]`, `[modify]`, `[merge]`, `[output]`, `[experimental]`.
- Three-tier TOML loader: stdlib `tomllib` (Python 3.11+) → `tomli` backport → in-tree minimal parser.
- `getsubtitle config --init / --path / --open / --show` for management.
- API keys NEVER read from TOML — macOS Keychain when available, otherwise env vars (`JIMAKU_API_KEY`, `WYZIE_API_KEY`, `SUBDL_API_KEY`, `DEEPL_API_KEY`, `TMDB_API_KEY`).
- Per-provider download headers (so Addic7ed can supply a Referer).

### Tests

- 380+ automated tests covering URL parsing, provider response shapes, TMDB / AniList resolution, SAMI parsing, VTT/ASS input parsing, MT helpers + auto_load/auto_unload, merge with format hints, pipeline orchestration, `--config` CLI overrides, config validation, source smoke diagnostics, help system, and dispatch routing.

## Planned (post-v1.0)

- **Per-pair MT model on the CLI**: `--mt-model-pair ja:ko=qwen3:4b,en:es=llama3.2:3b` so the per-pair selection from `[translate.ollama_models]` has a one-flag CLI equivalent.
- **List-fallback `mt_source`**: today `mt_source = { en = ["ko", "ja"] }` only uses the first; planned to walk the list and pick the first source actually on disk.
- **Romanization expansion (international)**: the v1.1 `[modify].romanization`
  schema is designed to grow per language. Korean (Revised Romanization with
  G2P) ships first; the same per-language entry point covers Chinese pinyin,
  Cantonese jyutping, Thai, Arabic, Hindi/Sanskrit, Russian, Greek, Persian,
  Hebrew, and other scripts where learners benefit from a phonetic guide
  alongside the original. Each language ships as a separate optional pip
  extra (`romanization-zh`, `romanization-yue`, `romanization-th`, …) so
  users only install the backends they need. Filename suffix stays
  language-native (`pinyin-marks`, `jyutping-numbers`, etc.) rather than
  unifying everything under "romanization".
- **Native SAMI per-language scoping**: `[modify].convert = "kr:smi-to-srt"` to convert only Korean SAMI streams.
- **Help/doc cleanup for canonical aliases**: `--engine` / `--model` are the
  canonical translate flags, while `--mt-engine` / `--mt-model` remain silent
  compatibility aliases for existing scripts.
- **`--pipeline run NAME`** registry: name a pipeline TOML and run it by short name without typing the path.

## Planned: merge improvements

- **Multi-variant merge** — combine the original language + its romanization
  variants in a single stacked file. Filenames already carry per-variant
  suffixes (`.ja.furigana-hiragana.srt`, `.ja.romaji.srt`,
  `.ko.romanization-revised.srt`, etc.), and the scanner is extended to
  expose each as a pseudo-lang code:

  ```sh
  getsubtitle merge FOLDER -l ja,ja-furigana,ja-romaji,en
  # → episode.ja-furigana-romaji-en.srt with 4 stacked lines per cue
  ```

  Lets one file carry the original Japanese, its furigana variant, its
  romaji variant, AND a native-language support line — the maximal study
  surface for kanji-heavy material. Same shape for Chinese
  (`zh,zh-pinyin,en`), Korean (`ko,ko-romanized,ja`), etc.
- Semantic alignment fallback when time-overlap matching is weak (`--sync smart --semantic-engine ollama`).
- Optional subtitle labels and ordering for combined files.
- Integration tests using temporary SRT/VTT/SMI folders for end-to-end merge output.

## Planned: UX polish

- Examples gallery (real downloaded folder layouts; multiple seasons; mixed sources).
- asbplayer visual QA notes for VTT ruby output.
- Better surface for "this provider matched but the file failed to download" failures.

## Intentionally out of scope

- Bypassing DRM, account login, region locks, or any other access control of streaming services. The Netflix-browser-capture work in this roadmap is explicitly for tracks the user can already view in their logged-in browser.
- Redistribution of downloaded subtitles in violation of their original license.
- Subtitle conversion to/from proprietary container formats beyond what asbplayer and mpv consume.

## Responsible use

This tool searches and downloads subtitle files that are already publicly accessible through community subtitle databases. It does not bypass DRM, account login, region locks, or any other access control of streaming services. Don't redistribute downloaded subtitles in violation of their original license.
