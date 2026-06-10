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

## Local MKV Files

For local MKV files, GetSubtitle can extract embedded text subtitle tracks you
already have and use them as translation or merge sources.

## Responsible Use Reminder

GetSubtitle does not bypass DRM, account login, or region locks. If a source is
not available publicly or through your own local files, GetSubtitle will not
unlock it.
