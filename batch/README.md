# batch/ — bulk subtitle workflows over your library

Three scripts that walk a Plex-style directory, match each show/movie
against `reference.json`, and run the right `getsubtitle` commands per
the show's origin language.

```
batch/
├── reference.json   show/movie database (folder name → metadata + IDs)
├── _common.py       shared helpers (walk, match, run)
├── fetch.py         bulk download missing subtitles
├── merge.py         bulk combine + smi-to-srt conversion
└── lookup.py        backfill empty IDs in reference.json from AniList / TMDB
```

## Quick start

```sh
# 1. Walk your library, see what would be fetched (default: dry-run)
cd /path/to/your/plex/library
python3 /path/to/getsubtitle/batch/fetch.py

# 2. If the plan looks right, run for real
python3 /path/to/getsubtitle/batch/fetch.py --run

# 3. Once subtitles are on disk, build the combined study files
python3 /path/to/getsubtitle/batch/merge.py --run --format vtt
```

`fetch.py` and `merge.py` are both dry-run by default. Add `--run` to
actually do work. Both shell out to the installed `getsubtitle` CLI,
so all of getsubtitle's own settings (engine, model, auto_load, etc.)
apply.

## How matching works

Each script walks the **current working directory** for folders that
contain video files (`.mkv`, `.mp4`, `.avi`, etc.), plus loose video
files directly at the top level.

For each target, it tries to match against `reference.json` in this
order:

1. **Exact relative path** — e.g. `유포니움/1기` matches that key
2. **Walk up the parents** — e.g. `Show (2023)/Season 01/` falls back
   to matching `Show (2023)`
3. **Bare filename** for top-level files (e.g. `Kill Boksoon …mkv`)

Anything that doesn't match is listed under "Unmatched" at the end of
the run with a hint to add it to `reference.json`.

## Profiles

Each entry has a `profile` that drives both fetch and merge behavior:

| Profile | Origin           | fetch.py                    | merge.py                                  |
| ------- | ---------------- | --------------------------- | ----------------------------------------- |
| `ja`    | Japanese (anime + JP live-action) | Fetch `ko`; MT `ja→ko` if missing  | `combine -l ja,ko --master ja --furigana` |
| `ko`    | Korean (K-drama, K-variety)       | Fetch `ja`; MT `ko→ja` if missing  | `combine -l ko,ja` and `combine -l ko,ja,en,es` (both `--master ko --furigana`) |
| `en`    | English / Western / other         | Fetch `es,ko`; MT from `en` if missing | `combine -l en,es --master en` and `combine -l ja,ko,en,es --master en --furigana` |

The merge step also runs `getsubtitle modify --convert smi-to-srt --force`
on each folder first, so legacy Korean `.smi` files get turned into
`.ko.srt` before combine sees them.

## reference.json schema

See the `schema` block at the top of `reference.json` itself for the
full field list. Minimum useful entry:

```json
"Folder Name (2023)": {
  "title": "Folder Name",
  "type": "movie",
  "profile": "en",
  "imdb_id": "tt0123456"
}
```

Add `anilist_id` for anime, `season` / `episode_count` for shows, and
`needs_lookup: true` to flag entries `lookup.py` should try to enrich.

## Backfilling missing IDs (lookup.py)

Most fetch operations work better with explicit IDs. For entries flagged
`needs_lookup: true`, run:

```sh
# Anime-only (uses anonymous AniList GraphQL)
python3 /path/to/getsubtitle/batch/lookup.py

# Include live-action (requires a free TMDB API key)
export TMDB_API_KEY=your_key_here
python3 /path/to/getsubtitle/batch/lookup.py

# Try just one entry
python3 /path/to/getsubtitle/batch/lookup.py --only "Couples Therapy (2019)"

# Limit to N entries per run
python3 /path/to/getsubtitle/batch/lookup.py --limit 10
```

Lookups only fill empty fields; manually-set IDs are never overwritten.
Successful lookups clear `needs_lookup`.

Get a TMDB key at <https://www.themoviedb.org/settings/api> — it's free
and instant.

## Adding new shows to reference.json

```jsonc
"New Show (2026)": {
  "title": "New Show",
  "year": 2026,
  "type": "show",          // or "movie"
  "profile": "en",          // ja | ko | en
  "needs_lookup": true,     // lookup.py will fill IDs on next run
  "notes": ""
}
```

Then either set the IDs by hand (faster if you already know them) or
run `lookup.py` to populate them automatically.

## Troubleshooting

**"Unmatched: my-folder"**
Either the folder isn't in reference.json or its name on disk doesn't
match the key. Add it (above) or fix the key.

**Fetch finds nothing for a show that exists**
The reference entry may have wrong IDs, or the providers genuinely
don't have it. Re-run with `--debug-providers` via raw `getsubtitle` to
see what the providers actually returned.

**MT fallback is slow**
`--mt-engine ollama` uses your local Ollama daemon. Auto-load pulls the
default model (`qwen3:4b`) on first use, then auto-unload frees it
after each batch. To skip MT entirely for a fetch pass, pass
`--mt-engine ''`.

**.smi files aren't being converted**
The merge step runs `modify --convert smi-to-srt` automatically. If a
human `.ko.srt` already exists, conversion is forced (`--force`),
overwriting it — back up first if that matters.
