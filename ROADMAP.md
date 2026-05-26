# Roadmap

What's shipped, what's experimental, what's planned next, and what's intentionally out of scope.

## Recently shipped

Highlights from the most recent round of work:

- **Hulu / Max (HBO) / Disney+ / Apple TV+ / Paramount+ / Peacock / Prime Video URL recognition.** Single generic handler that pulls a title from the URL slug and (where available) scrapes `og:title` from the page. The TMDB enrichment hook then resolves the title to IMDb/TMDB IDs so the existing Wyzie path lights up. Auth-wall boilerplate ("Sign in to Hulu" etc.) is filtered out — never used as a show title.
- **`--release-source` understands the new services.** `normalized_release_source()` now detects HULU / HMAX / MAX / DSNP / ATVP / PMTP / PCOK release tags. `--release-source auto` (the default) infers from the URL host, so pasting a `hulu.com` URL automatically prefers HULU-tagged subs over generic web-dl rips.
- **TMDB title-resolution support in the main app.** `getsubtitle --set-key tmdb` adds TMDB to the keyring alongside Jimaku/Wyzie/DeepL. When you pass `--title "..."` without a URL or IDs, the main flow auto-resolves IMDb/TMDB IDs from TMDB so Wyzie has solid IDs to search. Japanese-origin results are skipped when `ja` is requested, preserving the AniList → Jimaku path for anime.
- **`-e all` works for live-action TV.** When AniList can't supply an episode count, the main download flow asks TMDB via `tmdb_tv_season_episode_count()`. Lifts the long-standing "Episode count is unknown" error for non-anime shows.
- **Crunchyroll: series ID + season suffix parsing.** Captures the alphanumeric series ID (e.g. `GEXH3W2W7`) onto the MediaInfo. Strips trailing `Season N` / `Sn` / `Part N` / `Cour N` markers from slug-derived titles so AniList search hits the right base title, and the parsed season number becomes the default `-s`. URLs like `.../mashle-magic-and-muscles-season-2` now default to `-s 2`.
- **Netflix: `og:title` fallback when Wikidata misses.** Even on `/watch/` URLs (where the scraped title is the episode title), we keep it as a last-resort fallback if `external_ids_from_netflix_id()` returns nothing. Better than printing "unknown" and forcing the AniList prompt. Same auth-wall filter applies.
- **Default flip to language-learner-friendly settings**: `[download].single_line`, `[download].strip_cc_noise`, `[furigana].enabled`, and `[furigana].combine` now default to `true`; `[translate].engine` defaults to `"argos"`; `DEFAULT_OLLAMA_MODEL` is `"qwen3:4b"`. Added opt-out flags (`--no-single-line`/`--preserve-lines`, `--no-strip-cc-noise`, `--no-mt-engine`) so the on-by-default behavior can still be turned off at the CLI.
- **`user_settings.example.toml` rewritten in active-value style** — every setting uncommented at its default with a descriptive "Default: X" comment, quickstart recipes block at the top, expanded per-language model recommendations, fuller `[combine].priority` worked example.
- **`modify --convert smi-to-srt`** — parse Microsoft SAMI `.smi` files and emit one sibling `.<lang>.srt` per language found inside. Class → ISO-639-1 mapping (KRCC→ko, ENCC→en, JPCC→ja, …, KOKRCC→ko); unknown classes default to `ko`. Encoding auto-detect (UTF-8 / UTF-16-BOM / CP949). Existing targets protected unless `--force` is passed.
- **`[furigana].strip_before_mt`** (default `true`) — strips inline `漢字（かんじ）` readings from `ja` source cues before passing to the translator, preventing duplicated MT output on furigana-laden third-party sources.
- **`[translate.ollama_models].auto_load` / `auto_unload`** (both default `true`) — auto-pull missing Ollama models, and free them from RAM/VRAM (`keep_alive=0`) as soon as the MT pass finishes rather than waiting Ollama's 5-minute default.
- `combine` subcommand — stack 2+ language SRTs into one timed file, with language-order preservation, time-overlap matching, master override, sync presets (auto/strict/loose), and dry-run summaries
- Machine translation fallback (`--mt-engine argos|ollama|deepl`) for filling missing languages from what's already downloaded; smart source-language auto-pick (e.g. `ko` from `ja`, `es` from `en`)
- Topic-based help system (`getsubtitle --help download|combine|keys|furigana|translate|advanced`) replacing the wall-of-flags help
- Broadcast-caption cleanup (`--strip-cc-noise`) and asbplayer-friendly single-line flatten
- Netflix `jbv=` ID extraction + Wikidata P1874 bridge to IMDb/TMDB/TVDB
- TheTVDB slug → numeric ID extraction (artworks CDN scrape + fallbacks)
- AniList prefix-trim fallback for slug-derived titles like "Frieren Beyond Journeys End"
- Per-provider download headers (so Addic7ed downloads can supply a Referer)
- Experimental Spanish (Subdivx) and Korean (Addic7ed) fallback scrapers
- Localized title-alias search for fallback providers, so anime can be searched
  by romanized, English, native Japanese, or Korean titles when metadata exposes
  them
- Timing offset estimation now ignores obvious subtitle credit, URL, and music
  cues before trying to sync mixed-source subtitle files

## Implemented

### CLI

- Cross-platform Python CLI with editable install support
- Subcommands: `combine` (with internal dispatch; existing `getsubtitle URL ...` shape unchanged)
- Topic-based help: `--help`, `--help download|combine|translate|modify|config|keys|furigana|batch|advanced`
- Guided API key setup/reset for Jimaku, Wyzie, DeepL, TMDB (`--set-key`, `--reset-key`)
- macOS Keychain for API keys; env-var fallback on Linux/Windows
- Smart AniList prompt — accepts a title, AniList ID, or AniList URL
- Compact search summaries, red-block warnings, no tracebacks for expected errors

### URL recognition

- Streaming services:
  - Crunchyroll (`/watch/`, `/series/<ID>/<slug>`) — captures series ID, strips trailing `Season N` markers from the slug
  - Netflix (`/watch/<id>`, `/title/<id>`, `?jbv=<id>`)
  - Hulu, Max (HBO), Disney+, Apple TV+, Paramount+, Peacock, Prime Video — generic handler with slug parsing + `og:title` scrape + auth-wall filtering
- Catalog sites:
  - IMDb, TMDB, AniList, MyAnimeList, TheTVDB, Letterboxd, Rotten Tomatoes, Trakt
- Metadata bridges:
  - AniList ↔ IMDb/TMDB/TVDB via Anime-IDs + Wikidata
  - MyAnimeList → AniList directly via Anime-IDs
  - Netflix work ID → IMDb/TMDB/TVDB via Wikidata P1874
  - TheTVDB slug → ID via page scrape, then Wikidata bridge to IMDb/TMDB
  - TMDB title → IMDb/TMDB IDs (powers title-only fallback for every streaming service)
- Episode-count expansion for `-e all`:
  - Anime: AniList (no extra setup)
  - Live-action TV: TMDB (requires a TMDB key)
  - IMDb anime URLs expand via reverse AniList bridge
- Slug-to-title preserves common acronyms ("mf-ghost" → "MF Ghost")

### Providers

- Jimaku (Japanese anime by AniList ID)
- Wyzie (movie/TV by IMDb/TMDB ID)
  - Single broad call per episode with local language matching (catches files tagged with non-ISO codes like "Korean", "es-LA")
  - Tries TMDB ID when IMDb returns empty
  - Cache per `(id, season, episode)` so multi-language requests don't re-hit the API
- Experimental: Subdivx (Spanish), Addic7ed (Korean)
- Fallback providers try known title aliases from AniList/Wikidata, improving
  searches for titles like `Shingeki no Kyojin` / `Attack on Titan` /
  `進撃の巨人` / `진격의 거인`
- Source/release scoring (Netflix/Crunchyroll/Amazon/BluRay/WEB-DL/HDTV/DVD)

### Output processing

- Furigana from `.ja.srt`: SRT with inline `（よみがな）`, ruby VTT (`<ruby><rt>`), stacked-line ASS, single-line ASS
- `--single-line` flatten for asbplayer (Japanese full-width separator; regular space otherwise); on by default
- `--strip-cc-noise` removes Japanese broadcast continuation arrows (➡); umbrella name so future categories can be added without a CLI rename; on by default
- `modify --convert smi-to-srt` parses Microsoft SAMI `.smi` files and emits one sibling `.<lang>.srt` per language (KRCC/ENCC/JPCC/... → ko/en/ja/...; unknown class → ko). Auto-detects UTF-8 / UTF-16-BOM / CP949. `--force` overwrites existing siblings.
- Machine translation outputs as `.<lang>.mt.srt` via Argos / Ollama / DeepL with smart source-language auto-pick. Default engine is `argos` (offline); `--no-mt-engine` opts out per-run.
- `[furigana].strip_before_mt` (default on) strips inline `漢字（かんじ）` readings from `ja` source cues before MT
- `[translate.ollama_models].auto_load` / `auto_unload` (both default on) auto-pull missing Ollama models and free them from RAM/VRAM (`keep_alive=0`) as soon as the MT pass completes
- `combine` subcommand: stack multiple language SRTs into one timed file
  - Recursive SRT scan; ignores combined outputs (`.ja-ko.srt`) and furigana variants
  - Language order from `-l` is preserved top-to-bottom
  - `--master` override for timing authority
  - `--sync auto|strict|loose` presets with tunable overlap thresholds
  - `--preserve-lines` to keep original cue line breaks
  - `--force` to overwrite and bypass match-rate threshold
  - `-furigana` inlines readings before combining
  - constant-offset estimation ignores obvious non-dialogue credits/URLs/music
    cues before scoring overlap

### User configuration

- `user_settings.toml` for non-secret defaults; secrets stay in macOS Keychain / env vars / future OS keyring backends
- Sections: `[download]`, `[combine]`, `[furigana]`, `[translate]`, `[translate.ollama_models]`, `[experimental]`
- `getsubtitle config --path | --init | --open | --show` to manage and inspect
- `BUILTIN_CONFIG_DEFAULTS` is the single source of truth: both `config --show` and the runtime argparse defaults merge user TOML over the same dict, so flips take effect with or without a user config file
- Active-value example template (every key uncommented at its default) with quickstart recipes at the top
- Three-tier TOML parser: Python 3.11 `tomllib` → `tomli` backport on 3.10 → in-tree minimal parser

### Diagnostics

- `--debug-providers` shows raw counts and per-language tags for each provider call
- Clean clear errors (no tracebacks) for expected failure modes (network, missing IDs, missing API keys)

### Testing

- 275+ automated tests covering URL parsing (incl. Crunchyroll season suffix + the generic streaming handler for Hulu/Max/Disney+/Apple/Paramount+/Peacock), TMDB title resolution + `-e all` expansion, slug-to-ID extraction, provider response parsing (Wyzie/Subdivx/Addic7ed), SAMI parsing + smi-to-srt conversion (encoding sniff, multi-language, blank-line collapse, stem-strip), combine logic (file scanning/grouping, time overlap, sync presets, language ordering, missing-language skip, master override, force overwrite), MT helpers (round-trip, source-pick, Ollama response parsing, release_resources, auto_load/auto_unload, strip-before-MT), config validation (mixed-schema ollama_models, BUILTIN-default merge), help system, and dispatch routing

## In progress / first-release polish

- [ ] CHANGELOG
- [ ] PyPI package metadata polish
- [ ] Clean-install verification in a fresh virtual env
- [ ] Manual smoke tests on macOS from the installed command (not just source)

## Planned: provider expansion

- [ ] Direct OpenSubtitles support (independent of Wyzie's proxy)
- [ ] Direct SubDL support
- [ ] Harden Subdivx scraper
  - better diagnostics on parse failures (currently silent on 0 results)
  - rate-limit / backoff behaviour
  - fixture-based parser tests for more page variants
- [ ] Harden Addic7ed scraper
  - clearer anti-bot/rate-limit warnings (HTTP status now visible via `--debug-providers`)
  - better title-to-show matching
  - fixture-based parser tests
- [ ] Improve source/release scoring with stronger heuristics
- [ ] Cache provider responses during bulk searches where allowed

## Planned: Korean coverage

Korean is the weakest language in current default coverage because Wyzie Free only covers OpenSubtitles, which is thin for KR anime. Improvements:

- [ ] Investigate Korean-focused legal sources (GOM Lab, Cineaste) where technically and legally feasible
- [ ] Improve Korean title-alias search when public metadata exposes localised titles
- [ ] Document the Wyzie Pro upgrade path (adds Subf2m) as a low-friction option

## Planned: modify --convert (format conversion)

A general format-conversion mode on the `modify` subcommand. Self-documenting `X-to-Y` syntax so direction is always visible in shell history / logs / docs.

```sh
getsubtitle modify FOLDER --convert smi-to-srt
getsubtitle modify FOLDER --convert ass-to-srt
getsubtitle modify FOLDER --convert srt-to-vtt
```

Initial pair (motivated by the Korean coverage gap):

- [x] `--convert smi-to-srt` — parse Microsoft SAMI `.smi` files (`<SYNC Start=...>` blocks) and emit one `.srt` sibling per language found inside. Class-attribute → ISO-639-1 mapping (KRCC→ko, ENCC→en, JPCC→ja, …); unknown classes default to `ko`. Encoding auto-detect (UTF-8/UTF-16-BOM/CP949). Existing targets are protected (skipped) unless `--force` is passed. Unlocks the rest of the pipeline (combine, translate, modify) for `.smi` files already on disk.

Follow-on directions (whitelist as concrete need appears):

- [ ] `srt-to-vtt` — for browser `<track>` playback (separate from the furigana VTT variant)
- [ ] `srt-to-ass` / `ass-to-srt` — basic styling stripping/round-trip
- [ ] `vtt-to-srt` — strip cues from VTT-only sources

Validation: unknown pairs error cleanly with the supported whitelist listed. Multi-pair via comma list (`--convert smi-to-srt,srt-to-vtt`) reserved for when more than one direction lands.

## Planned: Netflix browser capture

For subtitle tracks the user can already view in their logged-in Netflix browser — explicitly NOT for bypassing DRM, account login, or region locks.

- [ ] Browser-session helper to save visible `ja`/`ko`/`en`/`es` tracks from a Netflix watch page
- [ ] Prefer captured same-session tracks when combining multiple languages
- [ ] Clear docs that this only saves tracks the user has access to

## Planned: combine improvements

- [ ] Stronger timing diagnostics
  - cue match counts
  - average per-cue offset
  - detection of likely constant drift
- [ ] Optional auto-shift when a consistent offset is detected
- [ ] Same-origin/same-release preference when multiple candidate SRTs exist for a language
- [ ] Examples using real downloaded folder layouts (multiple seasons, mixed sources)
- [ ] asbplayer visual QA notes for combined output
- [ ] Optional `--label-langs` for prefixed cues (e.g. `[JA] ...` / `[KO] ...`)

## Planned: smart subtitle sync

Real-world multi-language subtitle sync is harder than a single global offset.
Even subtitles from the same platform can differ by language because each locale
uses different segmentation, condensation, speaker-label rules, and reading-speed
constraints. Mixed-source workflows are harder still:

```text
EN: Netflix
JA: Jimaku
KR: Korean community SMI
ES: machine-translated from EN
```

Likely mismatch sources:

- intro/ending credits that exist in one file but not another
- translator/team credit captions
- skipped opening/ending sequences
- recap or sponsor-card differences
- one language splitting one sentence into multiple cues
- another language merging multiple short cues into one cue
- community files with a constant offset plus later drift
- machine-translated subtitles inheriting the source timing

Future sync should use a staged alignment pipeline rather than trusting overlap
alone.

### Stage 1: normalize

- [ ] Convert every subtitle into a common internal cue model:
  `start, end, language, text, source, episode, cue_id`.
- [ ] Convert `.smi` and other inputs into the same internal cue model.
- [ ] Strip or mark non-dialogue cues before sync:
  - music-only cues (`♪`, `♬`, `～`)
  - translator/group credits
  - URLs, Discord links, release notes
  - caption notes that are not dialogue
- [ ] Normalize text for matching:
  - remove styling/markup
  - optionally remove furigana readings for alignment only
  - keep original text for output

### Stage 2: deterministic alignment

- [ ] Keep first-language timing as the default output master, but align target
  languages against it locally.
- [ ] Detect global constant offsets where they clearly exist.
- [ ] Add segmented offsets:
  - estimate offset in rolling windows
  - allow offset jumps around OP/ED/recap regions
  - avoid assuming one intro offset applies to the whole episode
- [ ] Detect skipped intro/ending blocks using timing gaps and cue-pattern
  changes.
- [ ] Match cue windows using non-text fingerprints:
  - cue duration sequences
  - gap patterns
  - local density of short/long cues
  - stable punctuation/music anchors when both files have them
- [ ] Support one-to-one, one-to-many, and many-to-one mappings so merged/split
  cues do not duplicate the wrong translation.
- [ ] Treat machine-translated files as timing-linked to their source subtitle
  when their filenames or metadata indicate `.mt.srt`.

### Stage 3: semantic alignment

- [ ] Add a `--sync smart` mode that combines deterministic timing with semantic
  checks for low-confidence windows.
- [ ] Use semantic matching only on ambiguous local windows, not the whole
  episode.
- [ ] Candidate signals before any LLM:
  - text length similarity
  - numbers and named entities
  - speaker markers
  - transliterated proper nouns
  - punctuation shape
  - multilingual embeddings if a lightweight local option is practical
- [ ] Add optional LLM review:

```sh
getsubtitle combine PATH -l ja,en,ko --sync smart --semantic-engine ollama
```

The LLM should receive small local windows, e.g. 8 master cues and 10 candidate
target cues, and return structured JSON mappings. It should not be asked to
freeform rewrite a full episode.

Example intended prompt shape:

```text
Align these subtitle cues by meaning.
Return JSON mapping master cue IDs to target cue IDs.
Do not invent missing lines.
Do not translate unless explicitly asked.
```

### Stage 4: confidence and reports

- [ ] Assign per-match confidence:
  - timing score
  - fingerprint score
  - semantic score
  - source/release score
- [ ] Print concise sync summaries:

```text
S01E10:
  en: segmented sync, match 91%, offset +9.75s after intro
  ko: smart sync, match 84%, 19 low-confidence cues
  es: timing linked to en.mt.srt
```

- [ ] Add `--sync-report` to write a human-review file:
  - Markdown first
  - HTML later if useful
  - include low-confidence cues, candidates, scores, and reason
- [ ] Skip outputs by default when confidence is too low.
- [ ] Allow `--force` to write anyway, but make the risk obvious.

### AI policy

AI should not be the default timing engine. Timing and offsets are measurable,
deterministic, faster, and easier to debug. Use AI as an optional reviewer or
repair layer for low-confidence windows:

- good use: semantic cue mapping in a 20-30 second ambiguous window
- good use: deciding whether two nearby cues express the same meaning
- good use: retranslating missing target cues from the chosen master
- poor use: full-episode freeform sync
- poor use: replacing timestamp math
- poor use: silently rewriting all subtitle text

## Planned: learning output

- [ ] Keep SRT as primary asbplayer-compatible output
- [ ] Improve Japanese furigana variants without assuming player ruby support
- [ ] Clean Japanese output optimised for Yomitan lookup
- [ ] Optional subtitle labels and ordering for combined files
- [ ] Revisit ASS/VTT ruby output after real player testing

## Planned: testing

- [ ] Mocked network tests for AniList / IMDb / TMDB / TVDB bridge paths
- [ ] More fixtures for provider response parsing
- [ ] CLI snapshot tests for help topics
- [ ] Cross-platform path tests (Windows-style paths)
- [ ] Integration tests with temporary SRT folders for combine output
- [ ] Key-setup tests that don't require touching real Keychain state

## Not planned (out of scope)

To keep maintenance focus tight:

- DRM bypass of any streaming service
- Streaming-service login automation
- Region restriction circumvention
- Hosting or redistributing community subtitle files
- Real-time auto-translation of streaming video
- Heavyweight GUI; this is a CLI by design

## Responsible use

This tool searches and downloads subtitle files that are already publicly accessible through community subtitle databases. It does not bypass DRM, account login, region locks, or any other access control of streaming services. Don't redistribute downloaded subtitles in violation of their original license.

When using experimental scrapers (`--experimental-subdivx`, `--experimental-addic7ed`), avoid hammering — they're community sites that can rate-limit or block IPs.

When using `--mt-engine deepl`, watch your free-tier quota.
