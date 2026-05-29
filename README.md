# GetSubtitle

Turn movies, anime, dramas, and sitcoms into subtitle stacks for language
learning.

GetSubtitle helps you watch with the subtitle setup streaming apps rarely
offer: the language you are learning, a pronunciation guide, your native
language, and an optional bridge language, all synced into one study-friendly
file for players like VLC, mpv, IINA, asbplayer, Plex, and Jellyfin.

![asbplayer rendering Japanese ruby furigana from WebVTT](examples/asbplayer-ruby-vtt-preview.png)

## Why Learners Use It

- **Watch with two, three, or four subtitles at once** instead of switching
  tracks back and forth.
- **Add reading aids**: Japanese furigana, Korean Revised Romanization, and
  Mandarin pinyin.
- **Fill missing subtitles** with DeepL, Ollama, or Argos when the language
  you need is unavailable.
- **Clean messy captions** by removing broadcast noise and flattening cues for
  easier reading and sentence mining.
- **Prepare a media library** by scanning Plex/Jellyfin folders, converting
  legacy `.smi`, and merging per episode.

## What You Can Make

```text
Japanese audio
日本語字幕 + ふりがな
Korean / English / Spanish support line
One synced SRT or WebVTT file
```

Good fits:

| You want to... | GetSubtitle can... |
|---|---|
| Learn Japanese from anime or dramas | download `ja`, add furigana, merge with your native language |
| Use Korean as your support language | fetch or translate `ko`, then stack `ja,ko` |
| Learn English or Spanish from sitcoms | collect `en,es`, or translate missing tracks from another language |
| Use asbplayer for sentence mining | output single-line WebVTT with ruby reading aids |
| Clean up a Plex/Jellyfin library | scan folders, convert `.smi`, fill gaps, and merge per episode |

## Try These Workflows

### Easiest: `getsubtitle --interactive`

Let the wizard ask what you watch, which languages you want, whether to add
reading aids, and whether to run now or save a reusable workflow:

```sh
getsubtitle --interactive
```

### CLI Examples

```sh
# Easy: movie, TMDB link — Totoro, Japanese + English
getsubtitle "https://www.themoviedb.org/movie/8392" -l ja,en

# Medium: series, IMDb link — Midnight Diner, Japanese + Korean
# with Japanese pronunciation guides for asbplayer
getsubtitle "https://www.imdb.com/title/tt6150576/" \
    -s 1 -e all -l ja,ko --reading ja:hiragana --format vtt

# Hard: Friends S4E3-5, fill missing Spanish from French, then merge
getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 4 -e 3-5 -l fr,en,es
getsubtitle translate ~/Movies/Subtitles/Friends -s 4 -e 3-5 -l es \
    --engine deepl --mt-source es:fr
getsubtitle merge ~/Movies/Subtitles/Friends -s 4 -e 3-5 -l fr,en,es
```

`-e all` on **non-anime TV** needs a TMDB key — set one once with
`getsubtitle --set-key tmdb`, or pass an explicit range like `-e 1-22`.

## Reading Aids

Reading aids are phonetic guides inlined into the original-script line, in
either ruby (VTT) or parenthetical (SRT/SMI/ASS) form.

| Language       | Modes                                | Status                                                       |
|----------------|--------------------------------------|--------------------------------------------------------------|
| Japanese (`ja`)  | `hiragana`, `katakana`, `romaji`   | Ships today (`pip install -e ".[furigana]"`)                |
| Korean (`ko`)    | `revised`, `yale`                  | Ships today (`pip install -e ".[romanization-ko]"`)         |
| Mandarin (`zh`)  | `marks`, `numbers`, `letters`      | Ships today (`pip install -e ".[romanization-zh]"`)         |
| Cantonese (`yue`)| `numbers` (jyutping)               | Wired through; backend lands per ROADMAP                    |
| Thai / Arabic / Hindi / Russian | Royal Thai / ALA-LC / IAST / ISO-9 | Wired through; backends land per ROADMAP        |

`reading = "ja:hiragana,ko:revised,zh:marks"` in TOML; `--reading
ja:hiragana,ko:revised,zh:marks` on the CLI.

## Start Here

After installing, run:

```sh
getsubtitle setup
getsubtitle -i
```

`getsubtitle setup` asks what languages you know, what you are learning, what
you watch, and where you watch it. Then it recommends providers, API keys,
player settings, and optional dependencies with rough setup time.

`getsubtitle -i` is the guided workflow builder. It asks a handful of
questions, shows the command and reusable TOML workflow, then lets you Run,
Save, Edit, Restart, or Quit.

## Install

### macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/fpenguin/getsubtitle/main/setup.sh -o setup.sh
sh setup.sh
getsubtitle -i
```

The installer creates an isolated Python environment, asks which reading-aid
backends to install, adds a `getsubtitle` command shim in `~/.local/bin`, and
offers to run `getsubtitle setup`.

### Windows PowerShell

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/fpenguin/getsubtitle/main/setup.ps1 -OutFile setup.ps1
.\setup.ps1
getsubtitle -i
```

If PowerShell blocks local scripts, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

The installer creates an isolated environment under `%LOCALAPPDATA%\getsubtitle`,
asks which reading-aid backends to install, writes `getsubtitle.cmd` to
`%USERPROFILE%\bin`, and offers to run `getsubtitle setup`.

### pipx

Good if you already use `pipx`:

```sh
pipx install "getsubtitle[furigana,romanization-ko,romanization-zh] @ git+https://github.com/fpenguin/getsubtitle.git"
getsubtitle setup
getsubtitle -i
```

On Windows, install pipx first if needed:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

### Developer Checkout

```sh
git clone https://github.com/fpenguin/getsubtitle.git
cd getsubtitle
./setup.sh        # macOS/Linux; must run from the repo root
```

On Windows:

```powershell
git clone https://github.com/fpenguin/getsubtitle.git
cd getsubtitle
.\setup.ps1       # must run from the repo root
```

The installer detects the source checkout and creates an editable venv at
`./.venv`. Activate it each session with `source .venv/bin/activate`
on macOS/Linux or `.\.venv\Scripts\Activate.ps1` on Windows.

PyPI note: the `getsubtitle` package name is already occupied by an older
unrelated project, so `pip install getsubtitle` does **not** install this tool
yet. Use the GitHub installer or `pipx` command above for now.

## Setup Notes

**Optional dependencies** — install only what you need:

```sh
pip install -e ".[furigana]"          # Japanese (pykakasi)
pip install -e ".[romanization-ko]"   # Korean (g2pk + korean-romanizer)
pip install -e ".[romanization-zh]"   # Mandarin (pypinyin)
pip install -e .                       # bare install (no reading aids)
```

On Windows, prefix each command with `py -m `.

**API keys** — set once, stored in macOS Keychain or env vars:

```sh
getsubtitle --set-key                # interactive: pick a provider
getsubtitle --set-key jimaku         # Japanese anime (Jimaku)
getsubtitle --set-key wyzie          # movies / TV (Wyzie)
getsubtitle --set-key subdl          # SubDL fallback when Wyzie misses
getsubtitle --set-key deepl          # DeepL AI translation (free 500K chars/month)
getsubtitle --set-key tmdb           # title matching + `-e all` for live-action TV
```

If Keychain isn't available, set `JIMAKU_API_KEY`, `WYZIE_API_KEY`,
`SUBDL_API_KEY`, `DEEPL_API_KEY`, `TMDB_API_KEY` in your shell instead.

**asbplayer ruby furigana** — open asbplayer settings, then `Misc >
Subtitles > Subtitle HTML = Render`, and use `--format vtt`. Most
other players render VTT ruby out of the box.

## Common commands

Each verb has its own focused `--help`:

```sh
getsubtitle --help               # quick overview
getsubtitle --help fetch         # URL or PATH download
getsubtitle --help translate     # AI translation
getsubtitle --help modify        # cleanup, SAMI→SRT, reading aids
getsubtitle --help merge         # stack languages into one file
getsubtitle --help reading       # reading-aid spec (ja/ko/zh/…)
getsubtitle --help interactive   # the -i wizard
getsubtitle --help config        # user_settings.toml defaults
getsubtitle --help keys          # API key setup
getsubtitle --help advanced      # troubleshooting, experimental flags
```

## Config files

Save a set of options once, re-run with one flag:

```sh
getsubtitle --config simpsons-s1-en-fr.toml
getsubtitle --config plex-movies-fill-merge.toml

# CLI flags override the file:
getsubtitle --source /Plex/Anime --config plex-movies-fill-merge.toml
```

Two example configs ship in this repo:

- [`simpsons-s1-en-fr.toml`](simpsons-s1-en-fr.toml) — URL: download
  Simpsons S1 in English + French.
- [`plex-movies-fill-merge.toml`](plex-movies-fill-merge.toml) — PATH:
  scan `/Plex/Movies`, fetch JP/KO/EN/ES, fill MT gaps, merge in-place.

Per-user defaults live in `user_settings.toml`:

```sh
getsubtitle config --init        # write a commented template
getsubtitle config --path        # print where it lives
getsubtitle config --show        # show the effective merged config
```

Layered config (lowest → highest priority):
**built-in defaults** < **user_settings.toml** < **--config FILE.toml** < **CLI flags**

API keys never live in any TOML — they're in Keychain or env vars.

## Machine translation engines

| Engine            | Offline? | Setup                                            | Quality   |
|-------------------|----------|--------------------------------------------------|-----------|
| `argos` (default) | Yes      | `pip install argostranslate`                     | Gist      |
| `ollama`          | Yes      | Ollama daemon + a model (auto-pulled by default) | Good      |
| `deepl`           | No       | `--set-key deepl` (free 500K chars/month)        | Best      |

Per-pair model selection lives in `[translate.ollama_models]` in
`user_settings.toml`. Engine spec accepts `ollama:qwen3:8b` colon-form
to pin a model.

## Advanced

### Pipeline form (chain verbs in one call)

Verbs always run in canonical order (fetch → translate → modify → merge):

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

Add `--subdirectory` to any PATH-based verb to walk a whole library
and run it per show. See `getsubtitle --help pipeline` for the full
schema.

### Multi-variant merge

Stack the original alongside its reading-aid variants in one file —
useful for kanji-heavy material:

```sh
getsubtitle merge FOLDER -l ja,ja-hiragana,en          # kanji + hiragana + English
getsubtitle merge FOLDER -l ja,ja-hiragana,ja-romaji,en  # + romaji
getsubtitle merge FOLDER -l ko,ko-revised,en           # 한글 + Revised + English
getsubtitle merge FOLDER -l zh,zh-marks,en             # 漢字 + nǐ hǎo + English
```

Recognised pseudo-lang codes: `ja-hiragana`, `ja-katakana`,
`ja-romaji`, `ko-revised`, `ko-yale`, `zh-marks`, `zh-numbers`,
`zh-letters`. Each resolves to the matching
`.{base}.{infix}-{mode}.{srt|vtt|ass}` reading-aid side file produced
by `modify --reading {lang}:{mode}`. Output filenames collapse
adjacent same-base tokens
(`Show.S01E01.ja-hiragana-romaji-en.srt`, not
`Show.S01E01.ja-ja-hiragana-ja-romaji-en.srt`).

To generate the variants and stack them in one call:

```sh
getsubtitle "URL" --modify --reading ja:hiragana,ja:romaji \
    --merge -l ja,ja-hiragana,ja-romaji,en
```

### Supported URLs

- **Streaming**: Crunchyroll · Netflix · Hulu · Max (HBO) · Disney+ · Apple TV+ · Paramount+ · Peacock · Prime Video
- **Catalog**: IMDb · TMDB · AniList · MyAnimeList · TheTVDB · Letterboxd · Rotten Tomatoes · Trakt
- **Bridges**: AniList ↔ IMDb/TMDB/TVDB (Anime-IDs + Wikidata) · Netflix work ID → IMDb/TMDB (Wikidata P1874)

For non-anime TV, `-e all` expansion needs a TMDB key.

### Source diagnostics

```sh
getsubtitle sources --check      # which internal sources your Wyzie key reaches
```

If SubDL doesn't appear, a direct SubDL key fills coverage gaps for
Korean, Spanish, Chinese, and European-language subtitles:
`getsubtitle --set-key subdl`.

### Bare SRT (no learning helpers)

```sh
getsubtitle "URL" -l ja --no-reading --no-single-line --no-strip-cc-noise --no-mt-engine
```

### Developer source smoke tests

Diagnostic scripts under `scripts/` probe Korean, Chinese, and
European-language subtitle coverage before new providers are wired in.
See ROADMAP.md for the diagnostic workflow.

## Responsible use

GetSubtitle searches and downloads subtitle files from public
community databases (Jimaku, Wyzie, optionally Subdivx and Addic7ed).
It does **not** bypass DRM, account login, or region locks. Don't
redistribute downloaded subtitles in violation of their original
license.

## License

MIT. See [LICENSE](LICENSE).
