# Supported Sources

GetSubtitle works with common movie, TV, anime, and streaming/catalog URLs.

## Streaming

- Crunchyroll
- Netflix
- Hulu
- Max / HBO
- Disney+
- Apple TV+
- Paramount+
- Peacock
- Prime Video

## Catalog

- IMDb
- TMDB
- AniList
- MyAnimeList
- TheTVDB
- Letterboxd
- Rotten Tomatoes
- Trakt

## Bridges

- AniList to IMDb / TMDB / TVDB
- Anime-IDs + Wikidata
- Netflix work ID to IMDb / TMDB through Wikidata P1874

## Streaming helpers

Streaming URLs are used for identification and safer search, not for bypassing
streaming-service access controls.

- Crunchyroll watch/series URLs can be resolved through Crunchyroll metadata
  so GetSubtitle can identify the show, episode, and better subtitle-search
  aliases.
- Netflix URLs can expose a Netflix work ID. GetSubtitle can bridge that ID to
  Wikidata / IMDb / TMDB metadata when available.
- [Netflix Helper](../NetflixHelper.md) is the planned companion workflow for
  browser/asbplayer learners: identify Netflix titles and episode ranges, then
  generate GetSubtitle commands or workflow files for external subtitle search,
  translation, reading aids, and merging.

For non-anime TV, `-e all` expansion needs a TMDB key:

```sh
getsubtitle --set-key tmdb
```

## Local Files

When you run `getsubtitle fetch PATH`, local subtitle sources are checked before
online providers:

1. Embedded text subtitle streams inside video files.
2. Matching sidecar subtitle files beside the video.
3. Online subtitle providers for any requested languages still missing.

Image subtitle streams such as PGS/VobSub are reported but skipped because they
need OCR before they can be merged, translated, or used for reading aids.
