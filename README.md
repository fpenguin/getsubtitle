# getsubtitle  · v1.0

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

Primary output is **SRT** for maximum compatibility. WebVTT is supported for asbplayer's true ruby/furigana rendering; ASS is experimental.

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
generalises to a `--romanization` flag covering more languages — Korean
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
pip install -e .                    # bare install
pip install -e ".[furigana]"        # + Japanese furigana via pykakasi (recommended for JA learners)
```

### Windows

```powershell
py -m pip install -e .
py -m pip install -e ".[furigana]"
```

## Quickstart

Start with the language pair you actually want to watch with:

```sh
# 1. Japanese movie night: Japanese + English
getsubtitle "https://www.imdb.com/title/tt0096283/" -l ja,en

# 2. Preview a full anime season in Japanese, Korean, English, and Spanish
#    Anime episode count comes from AniList automatically.
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ja,ko,en,es --dry-run

# 3. Download a season and fill missing Korean/Spanish with MT
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ja,ko,en,es --mt-engine argos

# 4. Add Japanese furigana for asbplayer
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e 1 -l ja --format vtt

# 5. Merge downloaded subtitle files into one study stack
getsubtitle merge ~/Movies/Subtitles/MF\ Ghost -l ja,ko,en,es --format vtt
```

`-e all` on **non-anime TV** needs a TMDB key for episode-count expansion — set one once with `getsubtitle --set-key tmdb`, or pass an explicit range like `-e 1-22`.

For raw `.srt` with no learning helpers:

```sh
getsubtitle "URL" -l ja --no-furigana --no-single-line --no-strip-cc-noise --no-mt-engine
```

`getsubtitle` (no args) prints a short overview and a topic-help index.

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
getsubtitle --help config        # user_settings.toml defaults
getsubtitle --help keys          # API key setup
getsubtitle --help furigana      # Japanese readings
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
getsubtitle --set-key deepl          # DeepL MT (free 500K chars/month)
getsubtitle --set-key tmdb           # title → IMDb/TMDB ID resolution + `-e all` for TV
```

Keys live in macOS Keychain when available; otherwise set `JIMAKU_API_KEY`, `WYZIE_API_KEY`, `DEEPL_API_KEY`, `TMDB_API_KEY` in your shell.

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

## asbplayer setup (for true furigana)

1. Open asbplayer settings.
2. `Settings > Misc > Subtitles > Subtitle HTML = Render`.

Then use `--format vtt`:

```sh
getsubtitle "URL" -l ja --format vtt
getsubtitle merge ~/Movies/Subtitles/... -l ja,en --format vtt
```

## Status

v1.0. Test suite covers URL parsing, provider response shapes, MT helpers, merge logic (incl. VTT/SAMI input), pipeline orchestration, --config CLI overrides, the help system, and dispatch routing.

## Responsible use

`getsubtitle` searches and downloads subtitle files from public community databases (Jimaku, Wyzie, optionally Subdivx and Addic7ed). It does **not** bypass DRM, account login, or region locks. Don't redistribute downloaded subtitles in violation of their original license.

## License

MIT. See [LICENSE](LICENSE).
