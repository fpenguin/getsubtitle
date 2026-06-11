# Troubleshooting

## Health Check

Run:

```sh
getsubtitle doctor
```

`doctor` reports missing Python dependencies, API keys, ffmpeg/ffprobe, and
Ollama readiness before you get stuck mid-workflow.

## Common Help Topics

Each verb has focused help:

```sh
getsubtitle --help
getsubtitle --help doctor
getsubtitle --help fetch
getsubtitle --help translate
getsubtitle --help modify
getsubtitle --help merge
getsubtitle --help inspect
getsubtitle --help reading
getsubtitle --help interactive
getsubtitle --help config
getsubtitle --help keys
getsubtitle --help advanced
```

## asbplayer Japanese Readings

For Japanese readings above kanji in asbplayer:

```text
Misc > Subtitles > Subtitle HTML = Render
```

Then use:

```sh
--format vtt
```

For local playback with reading aids, prefer ASS. VTT support for positioned
readings varies by player.

## Local Video Files

For local MKV/MP4/MOV/M4V/AVI files, GetSubtitle can inspect embedded text
subtitle tracks you already have and use them as translation or merge sources.

```sh
getsubtitle inspect /path/to/movie-or-season-folder
getsubtitle fetch /path/to/movie-or-season-folder -l ja,en --run
```

`fetch PATH` checks embedded text tracks and subtitle files next to your videos
before online search. Embedded extraction writes separate subtitle files beside
the video; it does not modify the video file.

## Slow Subtitle Searches

Local-folder fetches cap each online search attempt at about two minutes. If an
online subtitle source stalls, GetSubtitle skips that attempt cleanly and
suggests retrying, using a more specific title/ID, or searching manually.

## Responsible Use Reminder

GetSubtitle does not bypass DRM, account login, or region locks. If a source is
not available publicly or through your own local files, GetSubtitle will not
unlock it.
