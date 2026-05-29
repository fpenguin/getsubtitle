# getsubtitle  · v1.3

Turn shows and movies into language-learning subtitle stacks.

`getsubtitle` helps you build the subtitle setup language learners usually want
but streaming apps rarely provide: Japanese with furigana, your native language
under it, English or Spanish as a bridge, and everything timed into one file for
players like asbplayer, VLC, IINA, MPV, Plex, and Jellyfin.

Use it to:

- **Watch with two, three, or four subtitle languages at once**
- **Add Japanese furigana** for kanji-heavy anime and dramas
- **Fill missing tracks with machine translation** when Korean, Spanish, or another language is unavailable
- **Clean messy captions** so subtitles are easier to read and mine
- **Convert and merge local files** from your Plex/media library into one study-friendly subtitle

```text
Japanese audio
日本語字幕 + ふりがな
Korean / English / Spanish support line
One synced SRT or WebVTT file
```

![asbplayer rendering Japanese ruby furigana from WebVTT](examples/asbplayer-ruby-vtt-preview.png)

One CLI can fetch, translate, clean, convert, and merge:

1. **Fetch** subtitles for a streaming/catalog URL — or scan a folder on disk.
2. **Translate** missing languages with offline or online MT (argos / ollama / deepl).
3. **Modify** files in place: SAMI→SRT conversion, broadcast-noise cleanup, Japanese furigana side files.
4. **Merge** two or more language tracks into one stacked, time-aligned study file.

Add `--subdirectory` to any PATH-based verb to walk a whole library and run it per show. Chain verbs in a pipeline (`--fetch X --translate ollama --merge -l ja,en`), or save a workflow once and re-run it (`--config FILE.toml`).

Primary output is **SRT** for maximum compatibility. WebVTT is supported for asbplayer's true ruby/furigana rendering; ASS/SSA can be read as merge input, with ASS output still experimental.

## Who it's for

| Learner goal | Useful workflow |
|---|---|
| Learn Japanese from anime/dramas | Download `ja`, add furigana, merge with `ko` or `en` |
| Use Korean as your native-language support line | Fetch/translate `ko`, then merge `ja,ko` |
| Learn Spanish from English media | Fetch `en,es`, or translate missing `es` from `en` |
| Prepare a Plex/Jellyfin library | Scan folders, convert `.smi`, fill gaps, merge per episode |
| Mine lines in asbplayer | Output single-line SRT or ruby WebVTT |

### Reading aids

Japanese **furigana** (`漢字（かんじ）`) ships today. The same code path
generalises to a `--reading` flag covering more languages — Korean
Revised Romanization (with G2P for `같이`/`읽는`/`한국어` cases), Chinese
pinyin, Cantonese jyutping, Thai/Arabic/Hindi/Russian/etc.
transliterations — landing per-language in v1.1+ (see [`ROADMAP.md`](ROADMAP.md)).
TOML form:

```toml
[modify]
romanization = "ja:hiragana, ko:true, zh:true"   # ja works now; ko/zh coming soon
```

## Install

### macOS / Linux

```sh
pip install -e .                                            # bare install
pip install -e ".[furigana]"                                # + Japanese furigana (pykakasi)
pip install -e ".[romanization-ko]"                         # + Korean Revised Romanization (g2pk + korean-romanizer)
pip install -e ".[romanization-zh]"                         # + Mandarin pinyin (pypinyin)
pip install -e ".[furigana,romanization-ko,romanization-zh]"  # all three (recommended for CJK learners)
```

### Windows

```powershell
py -m pip install -e .
py -m pip install -e ".[furigana]"
py -m pip install -e ".[romanization-ko]"
py -m pip install -e ".[romanization-zh]"
py -m pip install -e ".[furigana,romanization-ko,romanization-zh]"
```

## Quickstart

First-time setup starts with you, not with flags. It asks what languages
you already understand, what you are learning, what you watch, and where
you watch it. Then it recommends subtitle sources, API keys, player
settings, and optional dependencies with rough cost/setup time:

```sh
getsubtitle setup
```

After setup, use the workflow wizard when you want help building one
specific command:

```sh
getsubtitle -i
```

Or jump straight into the CLI:

```sh
# Easy: movie, TMDB link — Totoro, Japanese + English subtitles
getsubtitle "https://www.themoviedb.org/movie/8392" -l ja,en

# Medium: series, IMDb link — Midnight Diner, Japanese + Korean,
# with Japanese pronunciation guides for asbplayer
getsubtitle "https://www.imdb.com/title/tt6150576/" -s 1 -e all -l ja,ko --reading ja:hiragana --format vtt

# Hard: Friends S4E3-5, fill missing Spanish from French, then merge
getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 4 -e 3-5 -l fr,en,es
getsubtitle translate ~/Movies/Subtitles/Friends -s 4 -e 3-5 -l es --engine deepl --mt-source es:fr
getsubtitle merge ~/Movies/Subtitles/Friends -s 4 -e 3-5 -l fr,en,es
```

`-e all` on **non-anime TV** needs a TMDB key for episode-count expansion — set one once with `getsubtitle --set-key tmdb`, or pass an explicit range like `-e 1-22`.

Frequently used settings can be saved into a file:

```sh
getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 5 -e all --config ./friends.toml
```

For raw `.srt` with no learning helpers:

```sh
getsubtitle "URL" -l ja --no-reading --no-single-line --no-strip-cc-noise --no-mt-engine
```

`getsubtitle` (no args) prints a short overview and a topic-help index.

## First-time setup

```sh
getsubtitle setup
```

Setup asks:

- what languages you already understand
- what languages you are learning
- whether you mostly watch movies, TV shows, anime, or a mix
- whether you watch in a browser, tablet/TV app, Plex, or a local player
- whether you want no MT, free offline MT, or best-quality online MT

Then it explains recommendations before asking you to opt in:

- **Jimaku** — recommended for Japanese anime. Free, about 2 minutes.
- **Wyzie** — broad movie/TV subtitle search. Free tier available; paid tier unlocks more sources and AI-translated subtitles. About 2 minutes.
- **SubDL** — fallback when Wyzie misses. API key/account required; check SubDL account terms. About 2 minutes.
- **TMDB** — better title matching and full-season detection. Free API key, about 3 minutes.
- **DeepL** — best-quality online MT. Free API tier includes 500,000 characters/month, roughly 50-80 anime episodes depending on subtitle length. About 2 minutes.
- **Argos** — free offline MT. Lower quality, 0-5 minutes depending on language packages.

For selected web providers, setup can open the signup/API-key page in your
default browser and save pasted keys with the same secure flow as
`getsubtitle --set-key`. It also offers to create `user_settings.toml`.

## Interactive mode

The wizard walks you through a workflow without needing to memorise
flags or read a topic-help page first.

```sh
getsubtitle -i                # or: getsubtitle --interactive
                              # or: getsubtitle interactive
```

The wizard opens with a step picker so focused workflows skip
irrelevant questions:

```
Q1. What do you want getsubtitle to do?
    1) Fetch     — download subtitles from a URL or title
    2) Translate — fill any missing language with AI translation
    3) Modify    — clean up cues, add reading aids (furigana/pinyin/…)
    4) Merge     — stack multiple languages into one study file

    Default: fetch + modify + merge (no AI translation).
```

What it asks (up to 12 questions; many are skipped based on Q1):

| Q   | Topic                                        | Maps to                                       |
|-----|----------------------------------------------|-----------------------------------------------|
| 1   | Which steps to run (fetch/translate/modify/merge) | the verbs in the emitted command         |
| 2   | Source kind (title / URL / folder/file)      | `--fetch SOURCE`                              |
| 3   | URL or title or path                         | `--fetch ARG` / positional PATH               |
| 4   | Languages to collect                         | `--languages ja,ko,en,…`                      |
| 5   | Display order (top → bottom)                 | `--merge --languages …`                       |
| 6   | Which language controls timing               | `--master ja`                                 |
| 7   | Episode scope (URL/title, TV only)           | `--season`, `--episode`                       |
| 8   | AI-translation engine                        | `--translate argos\|ollama\|deepl`            |
| 9   | Reading aids (multi-select)                  | `--reading ja:hiragana,ko:revised,…`          |
| 10  | Cleanup preset                               | `--single-line --strip-cc-noise`              |
| 11  | Output format                                | `--format srt\|vtt\|ass\|smi\|txt`            |
| 12  | Output folder                                | `--output PATH`                               |

After Q12 the wizard prints both the terminal command and the
equivalent **workflow file** (in TOML, saveable as `.toml`) so you can
sanity-check before committing. The final-action menu offers:

- **Run** — dispatches immediately and offers to open the output folder
  in your file manager when finished. Defaults to *Run* for local
  sources, *Save* for URL/title sources (slow network jobs).
- **Save** — re-prompts on overwrite collisions; writes a self-contained
  `.toml` you can re-run via `getsubtitle --config FILE.toml`.
- **Edit** — list current answers, jump to one question, replay only that step.
- **Restart** — confirms before discarding all answers; otherwise returns
  you to the action menu.
- **Quit** — clears the draft.

When the action is **Run**, the wizard runs a dependency probe first and
points out anything missing — pykakasi for Japanese furigana, the Ollama
daemon if you picked ollama, the DeepL key if you picked DeepL, missing
Jimaku/Wyzie/SubDL/TMDB keys — and walks you through fixing each gap with
the right `--set-key` or `pip install` command before dispatching.
**Save** skips the probe so you can build workflow files on one machine
to run on another.

### Focused-subset workflows

The step picker unlocks three common one-off scenarios:

```sh
# Drop a folder of .srt files, merge into one .vtt:
#   Q1='4' (merge-only) → Q2 path → Q4 langs → Q5 order → Q6 master
#   → Q10 cleanup → Q11 format → Q12 output.
getsubtitle PATH --languages ja,en --merge --languages ja,en --format vtt

# Drop a single .ja.srt to add furigana:
#   Q1='3' (modify-only) → Q3 file → Q4 lang → Q9 reading aid.
getsubtitle FILE --languages ja --modify --reading ja:hiragana

# Translate-only on a folder of mixed-language files:
#   Q1='2' (translate-only) → Q3 path → Q4 langs → Q8 engine.
getsubtitle PATH --languages ja,ko --translate deepl
```

Reading-aid breadth (Q7) covers every language in the v1.1
romanization umbrella:

| Language | Modes | Status |
|---|---|---|
| Japanese (`ja`) | `hiragana`, `katakana`, `romaji` | Ships today (`pip install -e ".[furigana]"`) |
| Korean (`ko`) | `revised`, `yale` | Ships today (`pip install -e ".[romanization-ko]"`) |
| Mandarin (`zh`) | `marks`, `numbers`, `letters` | Ships today (`pip install -e ".[romanization-zh]"`) |
| Cantonese (`yue`) | `numbers` (jyutping) | Wired through; backend lands per ROADMAP |
| Thai, Arabic, Hindi, Russian | Royal Thai / ALA-LC / IAST / ISO-9 | Wired through; backend lands per ROADMAP |

For Korean, install the `romanization-ko` extra to pull `korean-romanizer` (Revised Romanization) and `g2pk` (G2P preprocessing — handles 같이→가치, 읽는→잉는, 한국어→hangugeo correctly). Yale mode is in-tree and needs no extras. For Mandarin, install the `romanization-zh` extra to pull `pypinyin` (handles polyphones and tone sandhi).

Deferred options are flagged with `☆` (vs `★` for ships-now) in the
wizard menu. The wizard happily saves a TOML referencing a deferred
backend so you can re-run the same workflow once the backend lands.

For full details: `getsubtitle --help interactive`.

## Example workflows (configs in this repo)

Save a TOML once, re-run it with one flag — and override any field on the command line:

```sh
getsubtitle --config simpsons-s1-en-fr.toml
getsubtitle --config plex-movies-fill-merge.toml

# Per-run overrides win over the TOML:
getsubtitle --source /Plex/Anime --config plex-movies-fill-merge.toml
getsubtitle --season 2 --config simpsons-s1-en-fr.toml
```

- [`simpsons-s1-en-fr.toml`](simpsons-s1-en-fr.toml) — URL: download Simpsons S1 in English + French → `/Download`.
- [`plex-movies-fill-merge.toml`](plex-movies-fill-merge.toml) — PATH: scan `/Plex/Movies`, fetch JP/KO/EN/ES, MT the gaps, merge in-place.

Layered config (lowest → highest priority):
**built-in defaults**  <  **user_settings.toml**  <  **--config FILE.toml**  <  **CLI flags**

## Pipeline form (inline)

Chain verbs in one command — verbs always run in canonical order (fetch → translate → modify → merge):

```sh
# Whole-library bilingual pass
getsubtitle --fetch /Plex/Anime --subdirectory \
            --translate ollama \
            --modify --strip-cc-noise --single-line \
            --merge -l ja,en --format vtt

# URL → study deck into an explicit output folder
getsubtitle --fetch "https://www.imdb.com/title/tt28299608/" -s 1 -e all \
            --translate deepl \
            --merge -l ja,en --format vtt \
            --output ~/Movies/StudyDeck
```

See `getsubtitle --help pipeline` for the full schema.

## Topic help

```sh
getsubtitle --help               # quick overview
getsubtitle --help fetch         # URL or PATH download flow
getsubtitle --help translate     # machine translation
getsubtitle --help modify        # cleanup, SAMI→SRT, furigana side files
getsubtitle --help merge         # stack languages into a study file
getsubtitle --help pipeline      # chain verbs / --config FILE.toml
getsubtitle --help setup         # first-time onboarding
getsubtitle --help config        # user_settings.toml defaults
getsubtitle --help keys          # API key setup
getsubtitle --help romanization  # reading aids: Japanese furigana, Korean romanization, …
getsubtitle --help advanced      # troubleshooting, experimental flags
```

## Configuration

Defaults live in `user_settings.toml`. The built-in defaults target Japanese learners with asbplayer: furigana on, single-line cues, ➡ broadcast noise stripped, offline `argos` MT, default Ollama model `qwen3:4b`, auto-load/auto-unload of Ollama models.

```sh
getsubtitle config --init        # write a fully-commented template
getsubtitle config --path        # print where it lives
getsubtitle config --open        # open in your default editor
getsubtitle config --show        # show the effective merged config
```

Sections mirror the pipeline TOML schema, so blocks copy-paste between `user_settings.toml` and any `--config FILE.toml`:

```
[fetch]         languages, release_source
[translate]     engine, model, mt_source, strip_furigana_before_mt
                [translate.ollama_models]  per-pair model + auto_load / auto_unload
[modify]        single_line, strip_cc_noise, furigana, reading_format
[merge]         languages, sync, preserve_lines, priority, furigana
[output]        target, layout, open_folder, force, debug_providers
[experimental]  subdivx, addic7ed
```

API keys never live in this file — they're stored in macOS Keychain or environment variables.

## API keys

Set keys once, before using providers that need them:

```sh
getsubtitle --set-key                # interactive: pick a provider
getsubtitle --set-key jimaku         # Japanese anime subtitles (Jimaku)
getsubtitle --set-key wyzie          # movies / TV (Wyzie)
getsubtitle --set-key subdl          # direct SubDL fallback when Wyzie misses
getsubtitle --set-key deepl          # DeepL MT (free 500K chars/month)
getsubtitle --set-key tmdb           # title → IMDb/TMDB ID resolution + `-e all` for TV
getsubtitle --reset-key -all         # remove all saved keys before uninstalling
```

Keys live in macOS Keychain when available; otherwise set `JIMAKU_API_KEY`, `WYZIE_API_KEY`, `SUBDL_API_KEY`, `DEEPL_API_KEY`, `TMDB_API_KEY` in your shell.

## Machine translation engines

| Engine | Offline? | Setup | Quality |
|---|---|---|---|
| `argos` (default) | Yes | `pip install argostranslate` | Gist-level |
| `ollama` | Yes | Ollama daemon + a model (auto-pulled by default) | Good |
| `deepl` | No | `--set-key deepl` (free 500K chars/month) | Best |

For per-language-pair Ollama model selection see the `[translate.ollama_models]` block in `user_settings.toml`. Engine spec accepts `ollama:qwen3:8b` (colon-form) to pin a model.

## Supported URLs

- **Streaming**: Crunchyroll · Netflix · Hulu · Max (HBO) · Disney+ · Apple TV+ · Paramount+ · Peacock · Prime Video
- **Catalog**: IMDb · TMDB · AniList · MyAnimeList · TheTVDB · Letterboxd · Rotten Tomatoes · Trakt
- **Bridges**: AniList ↔ IMDb/TMDB/TVDB (Anime-IDs + Wikidata) · Netflix work ID → IMDb/TMDB (Wikidata P1874)

For non-anime TV, `-e all` expansion needs a TMDB key (`getsubtitle --set-key tmdb`).

## Multi-variant merge (stack the original with its reading aids)

For kanji-heavy material, stack the original Japanese alongside its
reading-aid variants in one file:

```sh
# Original kanji + hiragana variant + English
getsubtitle merge FOLDER -l ja,ja-hiragana,en

# Maximum study surface: kanji + hiragana + romaji + English
getsubtitle merge FOLDER -l ja,ja-hiragana,ja-romaji,en
```

Output filename collapses adjacent same-base tokens:
`Show.S01E01.ja-hiragana-romaji-en.srt` (not the redundant
`ja-ja-hiragana-ja-romaji-en`). Same shape works for Korean and Chinese:

```sh
getsubtitle merge FOLDER -l ko,ko-revised,en        # 한글 + Revised Romanization + English
getsubtitle merge FOLDER -l zh,zh-marks,en          # 漢字 + nǐ hǎo pinyin + English
```

Recognised pseudo-lang codes:

| Code           | Resolves to                              |
|----------------|------------------------------------------|
| `ja-hiragana`  | `*.ja.furigana-hiragana.{srt,vtt,ass}`   |
| `ja-katakana`  | `*.ja.furigana-katakana.{srt,vtt,ass}`   |
| `ja-romaji`    | `*.ja.furigana-romaji.{srt,vtt,ass}`     |
| `ko-revised`   | `*.ko.romanization-revised.{srt,vtt,ass}`|
| `ko-yale`      | `*.ko.romanization-yale.{srt,vtt,ass}`   |
| `zh-marks`     | `*.zh.romanization-marks.{srt,vtt,ass}`  |
| `zh-numbers`   | `*.zh.romanization-numbers.{srt,vtt,ass}`|
| `zh-letters`   | `*.zh.romanization-letters.{srt,vtt,ass}`|

The variant files come from `modify --reading {lang}:{mode}`. To do both
steps in one call, chain them in a pipeline:

```sh
getsubtitle "URL" --modify --reading ja:hiragana,ja:romaji \
            --merge -l ja,ja-hiragana,ja-romaji,en
```

## asbplayer setup (for true furigana)

1. Open asbplayer settings.
2. `Settings > Misc > Subtitles > Subtitle HTML = Render`.

Then use `--format vtt`:

```sh
getsubtitle "URL" -l ja --format vtt
getsubtitle merge ~/Movies/Subtitles/... -l ja,en --format vtt
```

## Developer source smoke tests

These scripts are diagnostic only; they do not wire new providers into the
main downloader. Use them to decide whether a source is worth implementing:

```sh
.venv/bin/python scripts/test_korean_sources.py --live
.venv/bin/python scripts/test_chinese_sources.py --live
.venv/bin/python scripts/test_european_sources.py --live
.venv/bin/python scripts/test_all_sources.py --live
```

They summarize provider coverage, candidate community reachability, and local
format support such as Korean `.smi` conversion, Chinese `.ass/.ssa` parsing,
and Chinese/European Unicode SRT parsing. Add `--json` for machine-readable
output.

To check which internal sources your Wyzie key can access:

```sh
getsubtitle sources --check
```

If SubDL does not appear in that list, a direct SubDL key can still improve
coverage for Korean, Spanish, Chinese, and European-language subtitles:
`getsubtitle --set-key subdl`.

## Status

v1.1. Test suite covers URL parsing, provider response shapes, MT helpers, merge logic (incl. VTT/SAMI/ASS input), pipeline orchestration, --config CLI overrides, source smoke diagnostics, the help system, and dispatch routing.

## Responsible use

`getsubtitle` searches and downloads subtitle files from public community databases (Jimaku, Wyzie, optionally Subdivx and Addic7ed). It does **not** bypass DRM, account login, or region locks. Don't redistribute downloaded subtitles in violation of their original license.

## License

MIT. See [LICENSE](LICENSE).
