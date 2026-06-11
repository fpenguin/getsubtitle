# Roadmap  · v0.9.x -> v1.0

What is shipping before v1.0, what's experimental, and what's on the
horizon. Marketing-ready v1.0 is still ahead.

## Versioning direction

Until the app is marketing-ready for v1.0, use pre-1.0 release steps:

- **v0.9.1+**: small feature, docs, source, and UX batches that do not
  change the core workflow.
- **v0.9.x.1**: very small follow-ups, help text, tests, and bug fixes.
- **v1.0**: the marketing-ready milestone: safer downloads, cleaner inputs,
  smarter merges, and broader reading aids.
- **v2.0**: a later larger behavior milestone, aimed at an AI-assisted
  subtitle sync engine.

## v1.0 readiness roadmap

Before calling GetSubtitle "1.0", prioritize trust and learner value over
new surface area. The user should feel that the first downloaded files are
probably the right files, the files are cleaned before stacking, and the
final multi-language subtitle is readable enough to use for study.

### 1. Get accurate files from the start

- **Provider-result confidence gate.** Strengthen title, year, season,
  episode, release-source, and language checks before saving a subtitle.
  Obvious mismatches should ask before download or auto-try the next result.
- **Wrong-language detection.** Add lightweight script checks for CJK,
  Korean, Arabic, Thai, Russian, etc. Keep heavier Latin-script detection
  optional via a `language-check` extra so the base install stays small.
- **Better alternate-title search.** Search with localized titles,
  romanized titles, native titles, translated titles, and known aliases
  before declaring "not found"; especially important for Japanese anime,
  Korean shows, and Chinese/Cantonese media.
- **Provider provenance in the review.** Show enough detail for trust:
  provider, matched title, episode, language, release name, confidence, and
  why another candidate was skipped.
- **Manual search as an honest fallback.** If automation is weak, surface
  targeted community-search links and clear next steps instead of pretending
  the automatic search was complete.

### 2. Clean up properly before merging

- **Pre-merge cleanup pipeline.** Normalize encoding, line breaks, HTML tags,
  broadcast-caption noise, decorative wrappers, duplicated speaker labels,
  and obvious replacement-character corruption before merge.
- **Language-aware cleanup rules.** Keep Japanese bracket/wrapper cleanup,
  Korean SMI quirks, Chinese punctuation, and Western caption tags separate
  so one language's cleanup does not damage another.
- **Embedded subtitle extraction polish.** When online fetch misses for MKV
  or video files, clearly offer extraction of embedded text tracks as a
  source for translate/modify/merge.
- **Quality report before merge.** Show what exists per episode/language,
  what was cleaned, what was converted, and what is still missing.

### 3. Improve merging accuracy and timing intelligence

- **Subtitle ownership / overlap handling.** Prevent one language from
  "taking over" too early when another language's cue is still being read.
  The merge should respect cue duration, reading time, overlap windows, and
  master-track intent.
- **Smarter deterministic sync.** Add better offset/drift detection, cue
  split/merge heuristics, anchor matching, and confidence reporting before
  reaching for AI.
- **Per-language layout policy.** Let the merger decide when to preserve
  lines, stack lines, label languages, shrink text, or refuse an unreadable
  4+ language stack.
- **Human-readable diagnostics.** For skipped/low-confidence episodes, show
  the match rate, which language failed, and the exact next command to retry
  with `--sync loose`, `--force`, another master, or manual cleanup.

### 4. Expand reading aids for more learners

- **Finish shipped-language polish.** Japanese, Korean, Mandarin, and
  Cantonese should have clear install/setup checks, examples, output naming,
  and format guidance.
- **Add the next reading-aid languages carefully.** Candidates:
  Thai (`th:royal-thai`), Arabic (`ar:ala-lc` / DMG), Hindi/Sanskrit
  (`hi:iast`), Russian (`ru:iso-9`), plus Greek, Persian, and Hebrew if
  reliable libraries or deterministic rules are available.
- **Keep optional extras small.** Each reading backend should be installable
  as its own extra (`romanization-th`, `romanization-ar`, etc.) so the base
  app does not become heavy.
- **Format guidance by environment.** Explain what reading aids look like in
  SRT, ASS, VTT, and SMI based on where the user watches: browser/asbplayer,
  desktop player, Plex/Jellyfin, TV, tablet, or phone.

### 5. v1.0 launch checklist

- README should sell the learner outcome first, then installation and CLI
  detail later.
- `getsubtitle --help`, topic help, README, example TOMLs, and ROADMAP
  should use the same names and defaults.
- Interactive wizard transcripts should cover happy paths, common paths,
  edge cases, and failure paths.
- v1.0 should not require users to understand provider internals, subtitle
  formats, or TOML before getting one useful multi-language subtitle file.

## v0.9.8.1 — what's new

- **PATH fetch timeout cleanup.** Timed-out local fetch searches now terminate
  the whole child process group, so provider calls do not keep running in the
  background after GetSubtitle reports a clean timeout.
- **Inspect is scriptable.** `getsubtitle inspect PATH --no-interactive`
  prints the local subtitle report without opening the follow-up menu, making
  it safer for QA and automation.
- **Better local title guesses.** Automatic PATH fetches now skip weak fallback
  titles such as `Season 01`, `STREAM`, and `BDMV`, and keep dotted movie
  titles like `Once Upon a Time. in Hollywood (2019)` intact.
- **More recovery guidance.** Merge failures caused by missing requested
  languages now show detected languages and concrete next commands.
- **Validation.** Full suite passes, and a final 100-case random Plex QA pass
  completed with no crashes, no harness timeouts, and clean bounded provider
  timeouts.

## v0.9.8 — what's new

- **Safer subtitle fetching.** Provider results now get stronger title,
  episode, and language checks before saving. Obvious mismatches are rejected
  instead of silently producing the wrong subtitle file.
- **Bounded local fetch attempts.** Local PATH fetches cap each online search
  attempt at about two minutes, returning a clean retry/manual-search path
  instead of a long silent wait.
- **Bad-download guardrails.** HTML error pages, heavily corrupted text, and
  malformed local subtitles are detected earlier so they do not flow into
  cleanup, translation, or merge.
- **Local-source-first polish.** Local video workflows check existing sidecar
  subtitles and embedded text tracks before falling back to online subtitle
  search. Embedded extraction writes via temporary files so failed extraction
  cannot damage existing sidecars.
- **Inspect-to-wizard bridge.** `getsubtitle inspect PATH` lists embedded
  tracks, matching sidecar subtitles, and other subtitle files, then can hand
  off to the guided workflow with path/language context prefilled.
- **Safer workflow writes.** Saved workflows and subtitle outputs now use
  overwrite checks or atomic writes in more places, reducing partial-file and
  accidental-overwrite risk.
- **QA coverage.** Added focused tests around provider mismatch handling,
  corrupt subtitle parsing, local embedded/sidecar subtitle handling, and
  optional reading-aid backends.

## v0.9.7 — what's new

- **Beginner-facing wording pass.** Public help, README, docs, setup text,
  wizard transcripts, and `user_settings.example.toml` now say "AI
  translation," "workflow," "subtitle source," "timing language," and
  "subtitle lines" instead of developer shorthand such as MT, pipeline,
  provider, master, and cues.
- **Broader language and Chinese-variant UX.** The v0.9.6.5/6 local work is
  now part of the public release: Netflix-style language names, simplified /
  traditional Chinese aliases, Mandarin pinyin vs Cantonese Jyutping guidance,
  and `g=guide` language help.
- **Setup and recovery polish.** First-time setup is more personalized, source
  recovery points streaming users toward proven subtitle download tools, and
  source diagnostics cover the wider language set.
- **Documentation hygiene.** Generated UX audit artifacts, wizard transcripts,
  source docs, reading-aid docs, and API-key docs are synced with current
  behavior. `.gitignore` now covers common local Python/test artifacts and
  scratch release files.

## v0.9.6.6 — local follow-up

- **Docs and example audit cleanup.** README hero copy now matches the current
  multi-language graphic, and previously orphaned Korean, Cantonese, and SMI
  example images are surfaced in the learner-facing README.
- **Canonical help examples.** Public help now teaches `--reading ja:hiragana`
  and `--single-line` instead of legacy compatibility aliases.
- **Safer UX audit generator.** `scripts/generate_wizard_ux_audit.py --help`
  now behaves like help, and `--check` verifies generated UX artifacts without
  rewriting files.
- **Broader source diagnostics.** The combined source-smoke script now probes
  the common subtitle language set that setup/interactive language prompts
  accept.
- **Streaming helper suggestions are contextual.** Netflix/Crunchyroll
  downloader suggestions appear for streaming-source recovery, not every
  generic manual-recovery path.

## v0.9.6.5 — local follow-up

- **Chinese text variants.** Simplified/Traditional labels such as
  `zh-Hans`, `zh-Hant`, `zh-CN`, `zh-TW`, `chs`, and `cht` are accepted as
  Chinese subtitle sources and normalized to `zh` for merge/modify.
- **Mandarin vs Cantonese reading aids.** Mandarin pinyin remains `zh:*`;
  Cantonese Jyutping remains `yue:*`. The wizard explains that Cantonese
  workflows usually search/download Chinese text (`zh`) and derive a Jyutping
  row from it.
- **Chinese-friendly filenames.** Pinyin/Jyutping generators now handle
  script-labelled Chinese sidecars and produce merge-discoverable reading-aid
  outputs.
- **Netflix-style language choices.** Setup and interactive language entry
  now accept the broader common subtitle set: English, Korean, Japanese,
  Spanish variants, French, German, Italian, Portuguese (Brazil), Chinese
  variants, Thai, Turkish, Polish, Russian, Dutch, Swedish, Norwegian, Danish,
  Finnish, Arabic, Hindi, Vietnamese, Romanian, Hebrew, Indonesian, Ukrainian,
  Croatian, Czech, Filipino/Tagalog, Greek, Hungarian, Malay, Tamil, and Telugu.
  Language prompts also support `g=guide` to show the full code/name list.
  Regional labels currently normalize to broad internal buckets (`es`, `pt`,
  `zh`, `ar`) unless a provider exposes a finer distinction.
- **Setup UX polish.** `getsubtitle setup` now uses a more personal final
  summary, clearer recommended/advanced setup grouping, "time needed" wording,
  explicit format guidance/selection, and a stronger quick subtitle search
  using *Spirited Away* for broad multilingual coverage.
- **Contributor and agent docs.** Added durable project guidance for agents,
  contributors, UX philosophy, and architecture navigation without stale line
  numbers.

## v0.9.6.4 — what's new

- **Local sources first.** `getsubtitle fetch PATH` now checks embedded text
  subtitle tracks and sidecar subtitles before online providers, then searches
  online only for requested languages that are still missing. Image subtitle
  streams are reported but skipped because they need OCR first.
- **Cleaner local-file scanning.** macOS AppleDouble metadata files such as
  `._Movie.mkv` are ignored across video, SRT, SMI, and wizard scans so they
  no longer appear as fake media or trigger probe errors.
- **More human wizard review and recovery.** The final review, preflight
  coverage messages, partial-success summaries, and post-run success output
  use learner-facing language and hide diagnostics until they are useful.
- **Chinese/Cantonese reading-aid bridge.** Cantonese Jyutping workflows can
  fetch ordinary Chinese subtitle files (`zh`) and derive `yue:numbers`
  reading-aid tracks from them, because providers rarely expose Cantonese as a
  separate downloadable language.
- **Streaming subtitle tool resources.** Docs now point users to existing
  streaming subtitle downloaders, then route those files back into GetSubtitle
  for cleanup, reading aids, translation, and merging.

## v0.9.6.3 — what's new

- **Safer local-folder merge repair.** Merge can now conservatively use
  release-style subtitle filenames such as `Show - 01 (...).srt` when the
  folder already contains parseable episode context and the requested
  language can be inferred confidently from script. This fixes common
  Japanese/Korean local folders where one language is named cleanly and the
  other came from a release archive without `.ko.srt` / `.ja.srt` tokens.
- **Better timing guardrails.** Added regression coverage for realistic
  subtitle pairs with a small constant offset, different cue counts, and
  extra target-only cues so auto-sync keeps accepting good merges without
  lowering thresholds for bad matches.
- **Transparent auto-detection.** Merge reports the repaired subtitle files
  it used before planning outputs, so users can see when GetSubtitle inferred
  an episode or language from local files.

## v0.9.6.2 — what's new

- **Streaming-resource documentation.** README and docs describe streaming
  pages as metadata/workflow starters and point users to existing downloader
  projects for subtitles they can already access, then back to GetSubtitle for
  local cleanup/merge workflows.
- **Interactive wizard copy polish.** The final review now says "Change a
  setting", "Before you run", and "What you can do" in recovery flows, with
  transcripts and UX audit artifacts regenerated from the harness.

## v0.9.6.1 — what's new

- **Crunchyroll watch URL metadata.** Crunchyroll watch/series URLs now use
  Crunchyroll's anonymous metadata endpoint through `curl_cffi`, so the
  wizard and CLI can identify titles without a Brave Search API key.
- **Cleaner generated pipeline commands.** Wizard-generated full pipelines
  now show `--season` / `--episode` once on the fetch block; translate,
  modify, and merge inherit that scope internally unless they explicitly
  override it.
- **Docs split and install polish.** README stays shorter while install,
  workflow, reading-aid, source, API-key, and troubleshooting details live
  under `docs/`.

## v0.9.6 — what's new

- **Named pipeline registry.** `getsubtitle run --save NAME workflow.toml`
  stores a workflow under a short name; `getsubtitle run NAME` runs it
  (with optional `--source` / `--output` / ... overrides). `run --list` and
  `run --remove NAME` manage saved pipelines. Names are validated so they
  cannot escape the registry folder.
- **`--label-langs` for merge.** Prefix each language's line in a stacked
  cue with `[JA]` / `[KO]` / ... so tracks are easy to tell apart. Also
  available as `[merge] label_langs = true`.
- **Rename mode is safer.** Episode-range renumbering keeps language
  variants of the same episode paired (E01.ja and E01.en renumber
  together) and renumbers each season independently. Files that don't
  match the expected `Title - S03E05.lang.ext` shape are reported as
  skipped instead of silently ignored; a discarded change no longer locks
  the field; and a filesystem error mid-apply is reported cleanly (no
  traceback) with a partial-state warning.
- **Clearer wizard summary.** The action banner leads with a plain-language
  "Here's the plan" summary before the exact command and the workflow
  file, so you can sanity-check intent without reading the flag string.
- **Interactive wizard polish.** Language selection now warns when a merged
  file is likely to become too crowded, fetch-only multi-language runs can
  opt into merge before format questions, and back-navigation no longer gets
  stuck on the format step.
- **Format-aware text sizing.** Merged SRT and ASS outputs expose
  smaller/regular/larger presets calibrated from local playback tests; VTT
  and SMI remain mostly player-controlled and are described that way.
- **Better Spanish lookups.** Spanish aliases accept regional spellings such
  as `spanish`, `es-mx`, and `latin american spanish`, while provider queries
  avoid invalid Wyzie language variants.
- **Safer subtitle choice.** Fetch ranking now prefers subtitle filenames that
  match the requested title and episode, reducing false-positive downloads
  from similarly named media.

- **Wizard save-path guardrails.** Saved workflow filenames now reject
  accidental menu answers such as `b`, `y`, or `0`, require `.toml`, and
  auto-append `.toml` for friendly names like `fena`.
- **Editable smart defaults.** The final "Change a setting" menu now
  exposes display order, timing master, cleanup preset, output format, text
  size, and output folder directly.
- **Recoverable subtitle download failures.** Download timeouts now become
  clean errors, and wizard runs can retry the same result, try an alternate
  provider/result, skip the failed subtitle, or cancel.
- **Wizard preflight coverage.** Local workflows now warn before Run when
  no local subtitles are present, requested languages are only partially
  covered, or selected merge outputs already exist.
- **UX audit artifacts.** Added harness-backed wizard structure,
  representative transcripts, and metadata files for copywriting and
  beginner-flow reviews.

## Interactive rename maintenance mode

`getsubtitle -i` includes `5) Rename` for subtitle filename cleanup. It
groups matching patterns such as `Title - S03E**.ja.srt`, previews
old -> new filenames, checks collisions, and defaults to copy-and-apply
so originals stay untouched. The preview asks whether to apply now, keep
editing, discard the current change, or cancel; apply now then asks copy
vs original-file rename.

## v0.9.5 — what's new

- **Interactive wizard backtracking and cleaner ordering.** The wizard now
  advertises `back`, asks fetch/source/scope questions before translation
  and reading-aid choices, and includes regression transcripts for the
  Crunchyroll scope traps.
- **Crunchyroll episode-number help.** The wizard separates season and
  episode/range input, supports filename episode offsets such as saving
  provider E01 as S03E25, and avoids silent "auto" surprises on series pages.
- **Local video/folder fetch fixes.** A season folder is treated as one show
  season, a single video file is scoped to that episode, explicit languages
  override profile defaults, and inline PATH pipelines run live when the user
  chooses to run.
- **MKV fallback after online fetch misses.** Local MKV/video files can expose
  embedded text subtitles as source tracks for later translation/merge, with
  ASS/VTT text tracks converted to SRT when needed.
- **Better missing-Japanese guidance.** Manual search suggestions now include
  Japanese options such as Jimaku web search, Kitsunekko, and alternate-title
  Japanese subtitle searches.
- **DeepL usage summary.** DeepL runs can show character usage/remaining
  balance after translation.

## v0.9.4 — what's new

- **Interactive wizard is easier to follow.** Menus now use numeric
  choices consistently, questions are numbered contiguously, and the
  wizard scenario harness pins 26 beginner/persona transcripts.

## v0.9.3 — what's new

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

## v0.9.2 — what's new

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

## v0.9.1 — what's new

- **`getsubtitle doctor`.** A quick install-health check for Python,
  config paths, optional reading-aid packages, ffmpeg/ffprobe, Ollama,
  and provider API keys.
- **Better missing-subtitle guidance.** Fetch now prints a gap report with
  next steps: manual community search, where to place downloaded files,
  machine-translation fallback, and the merge command to run afterwards.
- **Embedded subtitle extraction.** `getsubtitle modify PATH
  --extract-mkv-subs` uses local `ffprobe` + `ffmpeg` to extract embedded
  text subtitle streams from MKV/video files. Newer `fetch PATH` workflows
  check embedded tracks automatically before online search; the modify flag
  remains a manual utility. Image subtitle streams such as PGS are reported
  and skipped.
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
    - Output format — guided by viewing environment and reading-aid needs.
    - Output folder — `~/Downloads/GetSubtitle` for URL/title sources;
      beside the source folder/file for local paths.
  A typical movie-with-furigana run goes from 12 → 5 questions.

## v0.9.0 — what's new

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

## v0.8 — what's new

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

## v0.7 — what's new

- **Interactive step picker.** New Q1 asks which pipeline verbs to run
  (fetch / translate / modify / merge) up front, with
  `1-4` (fetch+translate+modify+merge) as the current default. The
  translation question still defaults to "Skip", so pressing Enter does
  not silently start AI translation. Subsequent questions are gated on
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
- **Movie filename scan fix.** v0.6's movie filename layout
  (`Title.<lang>.srt` with no `SxxExx`) broke the scanner so modify and
  merge couldn't see the file. `parse_episode_marker` now treats
  `Title.<lang>.<ext>` shapes as the synthetic `(0, 0)` key (rendered
  as `movie` in progress lines) so the rest of the pipeline finds and
  groups them correctly. Combined outputs and reading-aid variants
  still return `None` so the scanner doesn't re-pick its own outputs.

## v0.6 — what's new

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
    accompanying scanner fix landed in v0.7.)

## v0.5 — what's new

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

## v0.4 — what's new

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

## v0.3 — what's new

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

## v0.2 — what's new

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

## v0.1 — what's new

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
  common international subtitle coverage before new providers are wired into
  the main downloader. They check Wyzie coverage, candidate community
  reachability, and local format support such as `.smi` conversion,
  `.ass/.ssa` input, and Unicode SRT parsing.
- **Provider source/status diagnostics.** `getsubtitle sources --check`
  reports Wyzie source availability for the user's configured key, and
  `--debug-providers` now prints a compact table of provider/source counts,
  language tags, formats, and quality flags.

## Initial capabilities

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
- Output formats: `.srt` (default), `.vtt` (browser/asbplayer Japanese ruby),
  `.smi`, `.ass`, and plain `.txt` without timestamps.

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

- 765 automated tests covering URL parsing, provider response shapes, TMDB / AniList resolution, low-confidence subtitle match gating, subtitle download sanity checks, SAMI parsing, VTT/ASS input parsing, MT helpers + auto_load/auto_unload, Argos direct/pivot package preflight, wizard run summaries, output/provider/coverage preflight, in-wizard pip dependency setup, setup onboarding UX, recoverable download timeouts, workflow save-path guardrails, editable smart defaults, explicit format selection, merge with format hints and font-size styling, Crunchyroll watch-URL metadata resolution, shared pipeline episode-scope inheritance, the wizard scenario harness, rename mode, the named pipeline registry, pipeline orchestration, `--config` CLI overrides, config validation, source smoke diagnostics, help system, and dispatch routing.

## v2.0 target: AI-assisted subtitle sync engine

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

- Bypassing DRM, account login, region locks, or any other access control of streaming services.
- Redistribution of downloaded subtitles in violation of their original license.
- Subtitle conversion to/from proprietary container formats beyond what asbplayer and mpv consume.

## Responsible use

This tool searches and downloads subtitle files that are already publicly accessible through community subtitle databases. It does not bypass DRM, account login, region locks, or any other access control of streaming services. Don't redistribute downloaded subtitles in violation of their original license.
