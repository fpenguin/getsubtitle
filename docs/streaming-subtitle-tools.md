# Streaming Subtitle Tools

GetSubtitle does not bypass DRM, login, region locks, or streaming-service
access controls. For Netflix, Crunchyroll, and similar browser-streaming
workflows, use GetSubtitle for metadata, cleanup, reading aids, translation,
and merging after you have subtitle files you are allowed to access.

If automatic fetch cannot find subtitles, these external projects may help you
download subtitles from services you can already watch:

| Tool | Status | Notes |
|---|---|---|
| [plateaukao/NetflixSubtitleDownloader](https://github.com/plateaukao/NetflixSubtitleDownloader) | Confirmed working | Good first option for Netflix subtitle downloads. |
| [wayneclub/Subtitle-Downloader](https://github.com/wayneclub/Subtitle-Downloader) | Untested | Older project; last known update was about two years ago. |
| [anidl/multi-downloader-nx](https://github.com/anidl/multi-downloader-nx) | Untested | Active, 500+ stars, supports anime-oriented downloader workflows. |

## How to use them with GetSubtitle

1. Download the subtitle files with one of the external tools.
2. Put the files beside the matching movie or episode, or into the folder
   GetSubtitle told you to use.
3. Run merge, modify, or translate from those local files:

```sh
getsubtitle merge /path/to/folder -l ja,en
getsubtitle modify /path/to/folder --reading ja:hiragana --format ass
```

If the downloaded subtitles are `.smi`, convert them first:

```sh
getsubtitle modify /path/to/folder --convert ko:smi-to-srt
```

