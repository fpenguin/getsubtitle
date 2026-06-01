# Roadmap  · v1.9.x -> v2.0

What ships in v1.0, what's new in v1.1 / v1.2 / v1.3 / v1.4 / v1.5 /
v1.6 / v1.7 / v1.8 / v1.9, what's experimental, and what's on the horizon.

## Versioning direction

After v1.9, use smaller release steps for incremental improvements:

- **v1.9.1+**: small feature, docs, source, and UX batches that do not
  change the core workflow.
- **v1.9.1.1**: very small follow-ups, help text, tests, and bug fixes.
- **v2.0**: the next larger behavior milestone, aimed at an AI-based
  subtitle sync engine.

## v1.9.3 — what's new

- **Japanese romaji is now full-sentence learner text.** `ja:romaji`
  romanizes kana-only and mixed Japanese lines, emits normal subtitle-size
  rows in VTT, and avoids tiny `<rt>` ruby annotation text.
- **Japanese multi-variant VTT preserves true ruby where it helps.**
  `ja-hiragana` and `ja-katakana` prefer generated ruby VTT side files,
  so readings sit above kanji; `ja-romaji` stays a normal full sentence.
- **Merged files can include a credit/disclaimer.** Merge outputs now add
  a short GetSubtitle credit and rights-holder disclaimer at the beginning
  and end by default. Use `--no-watermark` or `[merge] watermark = false`
  to omit it.

## v1.9.2 — what's new

- **Saved TOML workflows are easier to reuse.** After saving from
  interactive mode, getsubtitle now shows how to rerun the TOML and how
  CLI flags can override saved settings for a new show, season, or
  output folder.
- **Pipeline translation is more predictable.** URL fetch + translate
  workflows now let the explicit translate step own machine translation,
  and local translate workflows inherit the intended language list.
- **Japanese reading aids reach final merged VTT files.** A single
  Japanese reading aid such as `ja:hiragana` is carried into merge output
  so the final multi-language subtitle includes ruby furigana.
- **Single-line cleanup removes decorative Japanese subtitle wrappers.**
  When `--single-line` is active, broadcast wrapper marks such as
  `《》〈〉` are stripped while speaker labels and normal quotes remain.

## v1.9.1 — what's new

- **`getsubtitle doctor`.** A quick install-health check for Python,
  config paths, optional reading-aid packages, ffmpeg/ffprobe, Ollama,
  and provider API keys.
- **Better missing-subtitle guidance.** Fetch now prints a gap report with
  next steps: manual community search, where to place downloaded files,
  machine-translation fallback, and the merge command to run afterwards.
- **Embedded subtitle extraction.** `getsubtitle modify PATH
  --extract-mkv-subs` uses local `ffprobe` + `ffmpeg` to extract embedded
  text subtitle streams from MKV/video files. Image subtitle streams such
  as PGS are reported and skipped.
- **Cantonese Jyutping reading aids.** `--reading yue:numbers` now ships
  via the optional `romanization-yue` extra (`pycantonese`).
- **Interactive wizard streamlined to ≤7 questions.** Five answers are
  now auto-filled by `_wizard_apply_smart_defaults` and surfaced in a
  "Smart defaults" block in the banner so the user sees what was
  picked:
    - Display order — derived from Q4 (typed language order).
    - Master timing — first language wins (CLI override: `--master`).
    - Cleanup preset — always on (single-line cues + strip broadcast
      noise; works in every player).
    - Output format — VTT when reading aids are picked, SRT otherwise.
    - Output folder — `~/Downloads/GetSubtitle` for URL/title sources;
      beside the source folder/file for local paths.
  A typical movie-with-furigana run goes from 12 → 5 questions.

## v1.9 — what's new

- **Manual community search fallback for Korean and Chinese.** Fetch still
  tries automatic providers first. If `ko` or `zh` is missing, it prints
  likely community search links and can open several browser tabs for the
  user. This intentionally does not bypass login, ads, CAPTCHA, or other
  site restrictions. Controls: `--manual-search off|on-missing|always`,
  `--manual-search-open ask|always|never`, `--no-manual-search`, and
  `--no-manual-download`.
- **Better manual-search next steps.** Suggestions now use scoped SMI
  conversion such as `getsubtitle modify ~/Downloads --convert
  ko:smi-to-srt`, point users at the expected show folder, and print a
  merge command for that folder.
- **Safer default output folder.** The built-in default changed from the
  user's Movies folder to `~/Downloads/GetSubtitle`, which works on macOS
  and Windows after normal `~` expansion.
- **ASSRT API smoke script.** `scripts/test_assrt_api.py` probes the
  ASSRT/Shooter API with `ASSRT_API_KEY`, so Chinese direct-provider
  viability can be checked before adding it to the main downloader.

## v1.8 — what's new

- **List-fallback `mt_source`.** TOML can now express source-language
  preference lists, and the translator picks the first source actually
  present for each episode:

  ```toml
  [translate]
  mt_source = { es = ["fr", "en"], ko = ["ja", "en"] }
  ```

  The equivalent CLI spelling uses `|` inside the source half:
  `--mt-source "es:fr|en,ko:ja|en"`.
- **Per-pair MT model on the CLI.** `--mt-model-pair
  ja:ko=qwen3:4b,en:es=llama3.2:3b` gives the existing
  `[translate.ollama_models]` per-pair selection a one-command override.
  `--model` still wins when both are present.
- **Native SAMI per-language scoping.** `--convert ko:smi-to-srt` (alias
  `kr:smi-to-srt`) converts only Korean streams from multi-language SAMI
  files. `--convert smi-to-srt` still converts every stream.
- **Canonical help/doc cleanup.** User-facing examples prefer
  `--engine`, `--model`, `--mt-source`, and `--reading`. Legacy
  `--mt-engine`, `--mt-model`, `--mt-source-lang`, and old reading names
  remain compatibility aliases where supported.

## v1.7 — what's new

- **Interactive step picker.** New Q1 asks which pipeline verbs to run
  (fetch / translate / modify / merge) up front, with
  fetch+modify+merge as the default. Subsequent questions are gated on
  the selected steps — merge-only on a folder skips the URL/title
  picker, episode scope, MT engine and reading-aid questions; modify-
  only on a single file skips merge order, master, and format. The
  emitter switches between pipeline form (`--fetch SOURCE`) and PATH
  form (positional source) based on whether fetch is selected.
- **Beginner-friendly wording.** Wizard text now says "AI translation"
  instead of "MT", "workflow file" instead of "TOML workflow", and
  drops "pipeline" from the intro. CLI help and code comments stay
  technical for power users.
- **Q6 (timing master) lists all languages directly** — no first/custom
  dichotomy. Q9 (reading aids) has "No reading aid (skip)" as option 1
  and the default value so beginners press Enter to skip.
- **Movie filename scan fix.** v1.6's movie filename layout
  (`Title.<lang>.srt` with no `SxxExx`) broke the scanner so modify and
  merge couldn't see the file. `parse_episode_marker` now treats
  `Title.<lang>.<ext>` shapes as the synthetic `(0, 0)` key (rendered
  as `movie` in progress lines) so the rest of the pipeline finds and
  groups them correctly. Combined outputs and reading-aid variants
  still return `None` so the scanner doesn't re-pick its own outputs.

## v1.6 — what's new

- **Interactive wizard polish.** Six rounds of UX touch-ups:
  - Q5 (episode scope) is skipped automatically for movies (TMDB
    `/movie/`, Letterboxd `/film/`, and AniList format=MOVIE /
    single-episode SPECIAL/OVA/ONA candidates).
  - Reading-aid labels and Q8 examples adapt to the user's primary
    script (`漢字（かんじ）` for ja, `한글 (hangeul)` for ko,
    `漢字 (pīnyīn)` for zh).
  - Q9 (cleanup preset) generalised beyond asbplayer — mentions VLC,
    mpv, IINA, Infuse, asbplayer, Plex web.
  - Q11 banner stretches to ~70 chars with section dividers between
    the CLI form and the workflow preview.
  - After a successful Run, the wizard offers to open the output
    folder in the OS file manager.
  - Deferred reading aids (th/ar/hi/ru) are stripped before Run so
    the modify step doesn't crash; the Save flow keeps them so the
    saved workflow re-runs cleanly once the backend ships.
  - Cross-provider Japanese fallback: when ja is requested and the
    anime-IDs DB lookup misses (common for anime movies), the wizard
    searches AniList by title (movie-biased) so Jimaku gets a chance
    at finding native Japanese subs.
  - Movie filenames flatten to `Title/<Title>.<lang>.srt` instead of
    `Title/Season Unknown/<Title> - S00E00.<lang>.srt`. (Note: the
    accompanying scanner fix landed in v1.7.)

## v1.5 — what's new

- **Multi-variant merge.** Stack the original language plus its
  reading-aid variants in a single file. Pass pseudo-lang codes to `-l`:

  ```sh
  getsubtitle merge FOLDER -l ja,ja-hiragana,ja-romaji,en
  # → Show.S01E01.ja-hiragana-romaji-en.srt with 4 stacked lines per cue
  ```

  Supported pseudo-langs: `ja-hiragana`, `ja-katakana`, `ja-romaji`,
  `ko-revised`, `ko-yale`, `zh-marks`, `zh-numbers`, `zh-letters`, and
  `yue-numbers`. Each resolves to the matching
  `.{base}.{infix}-{mode}.{srt|vtt|ass}` reading-aid side file produced
  by `modify --reading {lang}:{mode}`. Output filename collapses
  adjacent same-base tokens so the result is `ja-hiragana-romaji-en`
  rather than the redundant `ja-ja-hiragana-ja-romaji-en`. Default
  master prefers the base language when both base and variant are
  requested (variants share cue timing with their base by construction).
  Composes naturally with the pipeline form:
  `getsubtitle URL --modify --reading ja:hiragana --merge -l ja,ja-hiragana,en`
  generates the variants and stacks them in one call.

## v1.4 — what's new

- **`--reading` rename + ja:katakana mode.** `--reading` replaces
  `--romanization` / `--furigana` as the canonical CLI flag. Legacy
  names remain compatibility aliases where supported.
  Japanese now ships three reading modes: `ja:hiragana`, `ja:katakana`,
  and `ja:romaji`. TOML key `reading = "ja:hiragana,ko:revised"`.
- **Interactive wizard UX overhaul.** Q11 actions expanded to
  Run / Save / **Edit** / Restart / Quit (the Edit branch was previously
  unreachable). Run confirms once before dispatching; Restart confirms
  before discarding. Default action flips between Run (local sources) and
  Save (URL/title sources) to protect users from accidental long fetches.
  Banner now shows both the CLI form **and** the equivalent TOML before
  the action menu. Save loops on overwrite collisions instead of bailing.
  Dependency probe only fires for Run (so TOML saves are portable across
  machines). Title-search picker accepts `r) Re-enter` to abandon poor
  hits, and prints a TMDB-key hint when no candidates are found. Path
  input strips wrapping single/double quotes (Finder/Explorer drag-drop
  now works). Q1 default flips to "folder/file" when no TMDB key is
  configured. Q5 inline-explains what "Auto" actually infers. Q11 banner
  warns when a hiragana/furigana reading aid is paired with a non-VTT
  format. Better restart separator + intro re-print on loop.

## v1.3 — what's new

- **Chinese (Mandarin) pinyin backend.** `--reading zh:marks`,
  `--reading zh:numbers`, and `--reading zh:letters` now
  produce real side files. Uses `pypinyin` for per-character pinyin
  lookup with built-in polyphone handling (e.g. 长 in 长大 vs 长城)
  and tone sandhi. Three output styles share one library: tone marks
  (`nǐ hǎo`), numbered tones (`ni3 hao3`), and toneless (`ni hao`).
  Install with `pip install -e ".[romanization-zh]"`. The setup wizard
  now opt-ins this for any user who selects Chinese as a learning
  language. Filenames carry the `.romanization-{marks|numbers|letters}`
  infix.

## v1.2 — what's new

- **Korean romanization backend.** `--reading ko:revised` and
  `--reading ko:yale` now produce real side files. Revised uses
  `g2pk` for grapheme-to-phoneme preprocessing (so `같이`→`gachi`,
  `읽는`→`ingneun`, `한국어`→`hangugeo` come out correctly) and
  `korean-romanizer` for the Revised Romanization rules. Yale is
  in-tree, no external deps. Install with `pip install -e
  ".[romanization-ko]"`. The setup wizard now opt-ins this for any
  user who selects Korean as a learning language. Filenames carry the
  new `.romanization-{revised|yale}` infix (the ja-specific
  `.furigana-{mode}` infix is preserved for back-compat).

## v1.1 — what's new

- **Interactive workflow builder.** `getsubtitle -i` /
  `getsubtitle --interactive` / `getsubtitle interactive` walks 11
  learner-friendly questions and produces a CLI command, a reusable
  TOML, or a live run with a dry-run preview. Runs a dependency probe
  after Q10 and walks the user through fixing each gap (missing pip
  extras, unreachable Ollama daemon, missing API keys). Auto-saves a
  draft at `~/.cache/getsubtitle/wizard-draft.toml` so an interrupted
  wizard can resume.
- **Reading-aid umbrella.** `--reading` becomes the canonical CLI flag
  for phonetic guides. The spec covers Japanese (ships now), plus Korean, Mandarin,
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
- Topic-based help: `--help fetch | translate | modify | merge | pipeline | config | keys | reading | advanced`.

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
- Per-target source spec: `mt_source = { ko = "ja", es = ["fr", "en"] }` avoids wasteful en→ko / en→ja when better sources are on disk and can try fallback sources in order.
- Per-pair Ollama model overrides in `user_settings.toml`'s `[translate.ollama_models]`, or session-only in any `--config` TOML.
- Engine spec accepts `ollama:qwen3:8b` colon-form to pin a model on the CLI.
- Strip inline 漢字（かんじ） readings from `ja` sources before MT (default true) so translators don't see the readings as duplicate content.
- Auto source-language picker prefers grammatically close pairs (ko ← ja, es ← en, en ← anything).
- Explicit per-target overrides via `--mt-source "ko:ja,es:en"`.
- Cue-level progress + deduped error messages.

### Merge (stacking)

- Reads `.srt`, `.vtt`, `.ass/.ssa`, and `.smi` (multi-language SAMI) as input formats. Per-language `:format` hints in `-l ja:vtt,en,ko:smi` pick which source to use when multiple formats coexist.
- VTT ruby `<ruby><rt>` markup collapses to `漢字（かんじ）` parentheticals so furigana survives the read.
- Time-overlap matching with `--sync auto | strict | loose` presets.
- Master language: `--master` flag > `[merge].priority` config > first language in `-l`.
- Inline readings on the matching merged line via `reading = "ja:hiragana"` or the CLI `--reading ja:hiragana`.
- Output formats: `.srt` (default), `.vtt` (asbplayer ruby), `.smi`, `.ass`, and plain `.txt` without timestamps.

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

- 514 automated tests covering URL parsing, provider response shapes, TMDB / AniList resolution, SAMI parsing, VTT/ASS input parsing, MT helpers + auto_load/auto_unload, merge with format hints, pipeline orchestration, `--config` CLI overrides, config validation, source smoke diagnostics, help system, and dispatch routing.

## Planned (post-v1.0)

- **Reading-aid expansion (international)**: the v1.1 `[modify].reading`
  schema grows per language. Shipped: Japanese (furigana, v1.0), Korean
  (Revised + G2P + Yale, v1.2), Mandarin (pinyin marks / numbers /
  letters, v1.3), Cantonese Jyutping (`yue:numbers`, v1.9.1). Still to
  come: Thai (`th:royal-thai`), Arabic (`ar:ala-lc`), Hindi/Sanskrit
  (`hi:iast`), Russian (`ru:iso-9`), and Greek/Persian/Hebrew. Each
  language ships as a separate optional pip extra (`romanization-yue`,
  `romanization-th`, …) so users only install the backends they need.
  Filenames use the `.romanization-{mode}` infix (ja keeps
  `.furigana-{mode}` for back-compat).
- **`--pipeline run NAME`** registry: name a pipeline TOML and run it by short name without typing the path.

## Planned: v1.9.x smaller steps

- Optional subtitle labels and ordering for combined files.
- Integration tests using temporary SRT/VTT/SMI folders for end-to-end merge output.

## v2.0 target: AI-based subtitle sync engine

Aim: make multi-language subtitle files line up better when subtitle
files come from different releases, cuts, intros, ad breaks, fansub
timings, or streaming sources.

- Add an AI-assisted sync mode such as `--sync ai` or expanded
  `--sync smart`.
- Keep the deterministic matcher as the default until AI sync is proven.
- Start with a deterministic pre-pass: normalize text, split or merge
  cues where needed, find anchor windows, and detect simple offsets or
  drift.
- Use AI or semantic matching only for low-confidence windows instead
  of blindly rewriting the whole file.
- Prefer a local-first engine path such as Ollama, with any cloud engine
  requiring explicit opt-in.
- Print a confidence report per episode, including skipped sections and
  before/after timing diagnostics.
- Never overwrite source subtitle files; write new synced outputs only.

## Intentionally out of scope

- Bypassing DRM, account login, region locks, or any other access control of streaming services. The Netflix-browser-capture work in this roadmap is explicitly for tracks the user can already view in their logged-in browser.
- Redistribution of downloaded subtitles in violation of their original license.
- Subtitle conversion to/from proprietary container formats beyond what asbplayer and mpv consume.

## Responsible use

This tool searches and downloads subtitle files that are already publicly accessible through community subtitle databases. It does not bypass DRM, account login, region locks, or any other access control of streaming services. Don't redistribute downloaded subtitles in violation of their original license.
