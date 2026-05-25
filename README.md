# GetSubtitle

```text
   ______     __  _____       __    __  _ __  __
  / ____/__  / /_/ ___/__  __/ /_  / /_(_) /_/ /__
 / / __/ _ \/ __/\__ \/ / / / __ \/ __/ / __/ / _ \
/ /_/ /  __/ /_ ___/ / /_/ / /_/ / /_/ / /_/ /  __/
\____/\___/\__//____/\__,_/_.___/\__/_/\__/_/\___/
```


A cross-platform Python CLI for **language-learning subtitle workflows**.

Built for people who watch foreign-language shows or movies and want predictable, scriptable subtitle prep: download in multiple languages, stack them into one timed file, and optionally fill the gaps with machine translation. Designed around Japanese learning but works for any language pair the underlying providers cover.

Primary output is **SRT**. That is the format used for downloads, machine
translation, and combined study subtitles because it is the most broadly
compatible format. Ruby **VTT** file format is supported for Japanese learners (Furigana compatible with asbplayer when Subtitle HTML is set to Render)

Three primary workflows:

1. **Download** subtitles for any show or movie from a streaming or catalog URL
2. **Modify** or convert subtitle file formats, add Japanese furigana, and remove odd characters.
3. **Translate** missing languages from what you already have, with an offline or online engine
4. **Combine** multiple language subtitle files into one stacked, time-aligned file (great for asbplayer)

## Keywords

Subtitle downloader, multi-language subtitles, dual subtitles, double subtitles,
bilingual subtitles, trilingual subtitles, multilingual subtitles, parallel
subtitles, stacked subtitles, language-learning subtitles, anime subtitles,
Japanese subtitles, Korean subtitles, English subtitles, Spanish subtitles,
furigana subtitles, ruby subtitles, asbplayer subtitles, Netflix subtitles,
Crunchyroll subtitles, Plex subtitles, SRT, WebVTT, VTT, subtitle translator,
machine-translated subtitles.

[More projects by fpenguin](https://github.com/fpenguin)

## Install

Requirements: Python 3.10 or newer.

### macOS and Linux

```sh
# Recommended for most users
python -m pip install --user pipx
pipx install .

# From a clone, for development
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Windows

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Recommended for Japanese Learners

Install the `furigana` extra if you want Japanese reading helpers:

```sh
# End-user install with furigana support
pipx install ".[furigana]"

# Development install with furigana and tests
python -m pip install -e ".[furigana,dev]"
```

The `furigana` extra installs `pykakasi`. Without it, normal SRT download,
combine, and machine-translation workflows still work.

## Quickstart

Five commands that cover most language-learning subtitle workflows:

```sh
# 1. Download Japanese and English subtitles for a Japanese movie
getsubtitle "https://www.imdb.com/title/tt0096283/" -l ja,en

# 2. Preview availability before downloading all episodes of season 1
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ja,ko,en,es --dry-run

# 3. Download a full season with Japanese furigana and subtitle cleanup
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ja,en --furigana --strip-cc-noise

# 4. AI-translate missing languages from online results or an existing folder
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ko,es --mt-engine deepl --mt-source-lang ko:ja,es:en
getsubtitle translate ~/Movies/Subtitles/... -l es,fr --mt-engine argos
getsubtitle translate ~/Movies/Subtitles/... -l ko,zh --mt-engine ollama

# 5. Combine subtitles into a study stack
getsubtitle combine ~/Movies/Subtitles/... -s 1 -e 1-3 -l ja,ko,en,es --furigana --format vtt
```

Run `getsubtitle` with no arguments (or `getsubtitle --help`) for a short overview and a list of topic pages.

## Topic help

Instead of a single overwhelming help page, the CLI splits into focused topics:

```sh
getsubtitle --help            # Short overview + topic list
getsubtitle --help download   # URL-based download flow
getsubtitle --help combine    # Combine subcommand
getsubtitle --help translate  # Machine translation (also: getsubtitle translate PATH)
getsubtitle --help modify     # Post-process existing SRTs on disk
getsubtitle --help config     # user_settings.toml defaults
getsubtitle --help keys       # API key setup
getsubtitle --help furigana   # Japanese readings
getsubtitle --help advanced   # Troubleshooting, experimental flags
```

`getsubtitle combine --help`, `getsubtitle translate --help`, and `getsubtitle modify --help` (or each with no args) all route to the matching topic page.

## API keys

Set keys once, before using providers that need them:

```sh
getsubtitle --set-key            # interactive picker
getsubtitle --set-key jimaku
getsubtitle --set-key wyzie
getsubtitle --set-key deepl
```

| Provider | Get a key | Cost | Purpose | Needed when |
|---|---|---|---|---|
| Jimaku | [jimaku.cc account](https://jimaku.cc/) | Free | Japanese anime SRTs | `-l ja` for anime |
| Wyzie | [Free key / dashboard](https://store.wyzie.io/redeem) and [API key docs](https://docs.wyzie.io/subs/usage/api-keys) | Free tier: 1,000 requests/day. Pro: $5 one-time for paid request balance; top-ups available. Check Wyzie docs/store for current limits. | Movie/TV subtitles by IMDb/TMDB ID | non-`ja` languages, or `IMDb`/`TMDB`/`Netflix` URLs |
| DeepL | [DeepL API plans](https://support.deepl.com/hc/en-us/articles/360021200939-DeepL-API-plans) | DeepL docs currently mention a 1,000,000-character total Developer plan and legacy API Free at 500,000 chars/month. Paid plans are usage-based. | Machine translation (optional) | `--mt-engine deepl` |

On macOS keys live in Keychain. On Linux and Windows, set them as environment variables:

```sh
export JIMAKU_API_KEY="..."
export WYZIE_API_KEY="..."
export DEEPL_API_KEY="..."
```

Reset a saved key with `getsubtitle --reset-key <provider>`. See `getsubtitle --help keys` for details.

## Supported URLs

The CLI recognises and extracts what it can from each:

| Host | What it gives us |
|---|---|
| `crunchyroll.com/watch/...` | Title from page (when Cloudflare allows); pair with `--anilist` for reliability |
| `crunchyroll.com/series/...` | Title from slug (acronym-aware) → AniList |
| `netflix.com/.../?jbv=<id>` | Netflix work ID → IMDb/TMDB via Wikidata |
| `imdb.com/title/tt...` | IMDb ID directly |
| `themoviedb.org/movie/N` / `/tv/N` | TMDB ID directly |
| `anilist.co/anime/<id>/...` | AniList ID extracted from URL — no search prompt |
| `myanimelist.net/anime/<id>/...` | MAL ID → AniList via Anime-IDs bridge |
| `thetvdb.com/series/...` | TheTVDB ID (numeric path or scraped from slug page) |
| `letterboxd.com/film/...`, `rottentomatoes.com/...`, `trakt.tv/...` | Title fallback |

If the URL is Cloudflare-blocked or otherwise opaque, pass `--title "Show Name"` or `--anilist <id>` to skip the title-inference prompt. At the prompt, you can paste a title, an AniList ID, or an AniList URL.

## Common workflows

### Download a season in multiple languages

```sh
getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ja,ko,en,es
```

`--dry-run` shows what would be found without writing files. `-y` skips the bulk-download confirmation.

### Combine downloaded languages into a study stack

```sh
getsubtitle combine ~/Movies/Subtitles/MF\ Ghost -l ja,ko
```

Output is `MF Ghost - S01E07.ja-ko.srt` (language order in `-l` is preserved top-to-bottom). The first language is the timing master by default; override with `--master`. By default each language's cue is flattened to a single line; use `--preserve-lines` to keep original breaks.

### Fill missing languages with machine translation

```sh
# Translate whichever languages weren't found, picking the closest source SRT
getsubtitle "https://www.imdb.com/title/..." -l ja,ko,en,es --mt-engine argos
```

| Engine | Offline? | Setup | Quality |
|---|---|---|---|
| `argos` | Yes | `pip install argostranslate` + per-pair model | Gist-level |
| `ollama` | Yes | Open the Ollama desktop app, or `brew services start ollama`; missing models are pulled automatically | Good |
| `deepl` | No | `getsubtitle --set-key deepl` (500K chars/mo free) | Best |

For Ollama, avoid running `ollama serve` in the same terminal you want to keep using; it is a foreground server. Use the desktop app or `brew services start ollama` for the normal background-daemon flow. `ollama serve` is only a temporary fallback for a separate terminal.

You can choose Ollama models per language pair in `user_settings.toml`:

```toml
[translate]
engine = "ollama"
model = "aya-expanse:8b"   # generic fallback

[translate.ollama_models]
"ja:ko" = "qwen3:4b"
"ko:ja" = "qwen3:4b"
"en:es" = "llama3.2:3b"
"es:en" = "llama3.2:3b"
```

These model keys are `source:target` and need quotes because TOML bare keys cannot contain `:`. Dash form like `ja-ko` also works without quotes. For one command, `--mt-model NAME` overrides both the pair-specific and generic config.

MT output is suffixed `.lang.mt.srt` so it never gets confused with human-quality files.

### Generate Japanese furigana

```sh
getsubtitle "URL" -l ja -furigana          # hiragana (default)
getsubtitle "URL" -l ja -furigana romaji
```

Produces several variants: SRT with inline `漢字（かんじ）`, ruby VTT with real `<ruby><rt>` markup, and stacked-line ASS.

SRT remains the safest fallback across players. VTT gives the cleanest true furigana in asbplayer once HTML rendering is enabled.

## asbplayer setup

For ruby VTT furigana in asbplayer:

1. Open asbplayer settings.
2. Go to `Settings > Misc > Subtitles`.
3. Set `Subtitle HTML` to `Render`.

`Detect and Display Ruby` is optional. It helps asbplayer treat ruby text correctly for mouseover/auto-pause behavior, but it is not required for rendering.

Recommended commands for asbplayer:

```sh
# True ruby furigana in WebVTT
getsubtitle "URL" -l ja --furigana --format vtt --single-line

# Multi-language study stack with Japanese ruby VTT
getsubtitle combine ~/Movies/Subtitles/... -l ja,ko,en --furigana --format vtt

# Broad compatibility fallback when VTT is not wanted
getsubtitle combine ~/Movies/Subtitles/... -l ja,ko,en --furigana --format srt
```

### Clean broadcast-caption noise

Some Japanese SRTs (especially ANIMAX/NHK rips) include continuation-arrow markers like `➡`. Strip them:

```sh
getsubtitle "URL" -l ja --strip-cc-noise --single-line
```

`--single-line` also flattens multi-line cues so each cue is one visual line — useful for asbplayer.

## When things don't work

| Symptom | What's happening | Try |
|---|---|---|
| "Could not infer show title" | URL is opaque or Cloudflare-blocked | `--title "Show Name"` or `--anilist <id>` |
| "AniList could not resolve title: X" | Slug-derived title doesn't match exactly | Pass `--anilist <id>` directly |
| `ko: missing` consistently | Wyzie Free covers OpenSubtitles only; KR is thin there | `--experimental-addic7ed` (KR scraper), Wyzie Pro (adds Subf2m), or `--mt-engine` from ja |
| `es: missing` consistently | Same coverage problem in Spanish | `--experimental-subdivx` (ES scraper) or `--mt-engine` |
| Provider returned 0 — but I know the file exists | Provider might use a non-ISO language tag we filter | Run with `--debug-providers` to see raw counts and tags |
| Tracebacks from the installed command | Shouldn't happen — file an issue with the command and output | |

`--debug-providers` is the single most useful diagnostic flag. It shows per-call item counts and the actual language tags providers returned, so you can tell "the show isn't there at all" from "the show is there but tagged in a way my filter missed".

## Status

Early alpha. Test suite covers URL parsing, provider response shapes, combine logic, MT helpers, the help system, and dispatch. Network paths should be tested with `--dry-run` first.

See [ROADMAP.md](ROADMAP.md) for what's shipped, what's experimental, what's planned, and what's intentionally out of scope.

## Responsible use

`getsubtitle` searches and downloads subtitle files from public community databases (Jimaku, Wyzie's backends, optionally Subdivx and Addic7ed). It does not bypass DRM, account login, region locks, or any other access control of streaming services. The Netflix-browser-capture work in the roadmap is explicitly for tracks the user can already view in their logged-in browser — not for circumventing access.

When using `--mt-engine deepl`, watch your free-tier quota. When using experimental scrapers (`--experimental-subdivx`, `--experimental-addic7ed`), don't hammer them — they're community sites that can rate-limit or block IPs.

Don't redistribute downloaded subtitles in violation of their original license.

## License

MIT.
