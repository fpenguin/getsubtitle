# Saved Workflows And One-Command Workflows

GetSubtitle can save wizard answers as a workflow file and rerun them later with one flag.

## Save Workflow Files

```sh
getsubtitle --config simpsons-s1-en-fr.toml
getsubtitle --config plex-movies-fill-merge.toml
```

CLI flags override saved settings:

```sh
getsubtitle --source /Plex/Anime --config plex-movies-fill-merge.toml
```

Two example configs ship in this repo:

- [`../simpsons-s1-en-fr.toml`](../simpsons-s1-en-fr.toml) - download Simpsons S1 in English + French.
- [`../plex-movies-fill-merge.toml`](../plex-movies-fill-merge.toml) - scan `/Plex/Movies`, fetch JP/KO/EN/ES, fill AI translation gaps, and merge beside the source files.

## Named Workflows

Save a workflow under a short name and run it without typing the path:

```sh
getsubtitle run --save anime plex-movies-fill-merge.toml
getsubtitle run anime
getsubtitle run anime --source /Plex/NewShow
getsubtitle run --list
```

## External subtitle downloads

If you use an external streaming subtitle downloader, bring the downloaded
files back into GetSubtitle as local inputs. GetSubtitle can then convert,
clean, add reading aids, translate missing tracks, and merge them.

Example workflow for downloaded Netflix or Crunchyroll subtitles:

```toml
[fetch]
source = "~/Downloads/StreamingSubtitles/Show/Season 01"
languages = "ja,en,ko"

[modify]
single_line = true
strip_cc_noise = true
reading = "ja:hiragana"

[merge]
format = "vtt"

[output]
target = "~/Downloads/GetSubtitle"
```

Run it later:

```sh
getsubtitle --config streaming-study.toml
```

Suggested external tools are listed in
[Streaming subtitle tools](streaming-subtitle-tools.md).

## User Defaults

Per-user defaults live in `user_settings.toml`:

```sh
getsubtitle config --init
getsubtitle config --show
```

Layered priority, low to high:

```text
built-in defaults < user_settings.toml < --config FILE.toml < CLI flags
```

## One-Command Workflow

Run several steps in one command:

```sh
# Whole-library pass: fetch + translate + clean + merge
getsubtitle --fetch /Plex/Anime --subdirectory \
    --translate ollama \
    --modify --strip-cc-noise --single-line \
    --merge -l ja,en --format vtt

# URL -> study deck into a specific output folder
getsubtitle --fetch "https://www.imdb.com/title/tt28299608/" -s 1 -e all \
    --translate deepl \
    --merge -l ja,en --format vtt \
    --output ~/Downloads/GetSubtitle/StudyDeck
```

`--subdirectory` on any path-based step scans each immediate subfolder and runs
that step once per show.

See:

```sh
getsubtitle --help workflow
```
