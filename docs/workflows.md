# Saved Workflows And Pipeline Form

GetSubtitle can save wizard answers as TOML and rerun them later with one flag.

## Save Workflows As TOML

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
- [`../plex-movies-fill-merge.toml`](../plex-movies-fill-merge.toml) - scan `/Plex/Movies`, fetch JP/KO/EN/ES, fill MT gaps, merge in place.

## Named Workflows

Save a workflow under a short name and run it without typing the path:

```sh
getsubtitle run --save anime plex-movies-fill-merge.toml
getsubtitle run anime
getsubtitle run anime --source /Plex/NewShow
getsubtitle run --list
```

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

## Pipeline Form

Chain verbs in one call:

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

`--subdirectory` on any PATH-based verb walks each immediate subfolder and runs
the verb per show.

See:

```sh
getsubtitle --help pipeline
```
