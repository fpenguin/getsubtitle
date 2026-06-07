#!/usr/bin/env python3
"""Download and prepare subtitles for language-learning workflows."""

from __future__ import annotations

import argparse
import json
import os
import getpass
import platform
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field, fields, replace
from html import unescape
from pathlib import Path
from typing import Iterable


JIMAKU_API = "https://jimaku.cc/api"
ANILIST_API = "https://graphql.anilist.co"
TMDB_API = "https://api.themoviedb.org/3"
WIKIDATA_SPARQL_API = "https://query.wikidata.org/sparql"
WYZIE_API = "https://sub.wyzie.io/search"
WYZIE_SOURCES_API = "https://sub.wyzie.io/sources"
SUBDL_API = "https://api.subdl.com/api/v1/subtitles"
SUBDL_DOWNLOAD_BASE = "https://dl.subdl.com"
ANIME_IDS_URL = "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/master/anime_ids.json"
SUBDIVX_BASE = "https://www.subdivx.com"
SUBDIVX_SEARCH_URL = SUBDIVX_BASE + "/inc/ajax.php"
ADDIC7ED_BASE = "https://www.addic7ed.com"
ADDIC7ED_KOREAN_LANG_ID = 22  # Addic7ed's internal numeric ID for Korean.
ADDIC7ED_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_OUTPUT_TEXT = "~/Downloads/GetSubtitle"
DEFAULT_OUTPUT = Path(DEFAULT_OUTPUT_TEXT).expanduser()
SUB_EXTENSIONS = {".ass", ".srt", ".vtt", ".ssa"}
ARCHIVE_EXTENSIONS = {".zip"}
KEYCHAIN_SERVICE = "getsubtitle"
KEYCHAIN_JIMAKU_ACCOUNT = "jimaku"
KEYCHAIN_WYZIE_ACCOUNT = "wyzie"
KEYCHAIN_TMDB_ACCOUNT = "tmdb"
KEYCHAIN_SUBDL_ACCOUNT = "subdl"
ASS_BASE_FONT_SIZE = 54
ASS_FURIGANA_FONT_SIZE = round(ASS_BASE_FONT_SIZE * 0.75)
ASS_FURIGANA_SCALE_X = round(100 * ASS_BASE_FONT_SIZE / ASS_FURIGANA_FONT_SIZE)
ASS_FONT_NAME = "monospace"
ANSI_RED = "\033[31m"
ANSI_RESET = "\033[0m"


class CliError(Exception):
    pass


KEY_PROVIDERS = {
    "jimaku": {
        "label": "Jimaku",
        "env": "JIMAKU_API_KEY",
        "account": KEYCHAIN_JIMAKU_ACCOUNT,
        "url": "https://jimaku.cc/",
        "use": "Japanese anime subtitles",
    },
    "wyzie": {
        "label": "Wyzie",
        "env": "WYZIE_API_KEY",
        "account": KEYCHAIN_WYZIE_ACCOUNT,
        "url": "https://store.wyzie.io/redeem",
        "use": "movie and TV subtitles by IMDb/TMDB ID",
    },
    "subdl": {
        "label": "SubDL",
        "env": "SUBDL_API_KEY",
        "account": KEYCHAIN_SUBDL_ACCOUNT,
        "url": "https://subdl.com/panel",
        "use": "direct SubDL subtitle fallback by IMDb/TMDB ID",
    },
    "deepl": {
        "label": "DeepL",
        "env": "DEEPL_API_KEY",
        "account": "deepl",
        "url": "https://www.deepl.com/your-account/keys",
        "use": "machine translation for --engine deepl (free tier: 500K chars/mo)",
    },
    "tmdb": {
        "label": "TMDB",
        "env": "TMDB_API_KEY",
        "account": KEYCHAIN_TMDB_ACCOUNT,
        "url": "https://www.themoviedb.org/settings/api",
        "use": "movie/TV title → ID resolution (improves Wyzie match rate when only a title is known)",
    },
}

LANGUAGE_ALIASES = {
    # Japanese
    "jp": "ja",
    "jpn": "ja",
    "japanese": "ja",
    # Korean
    "kr": "ko",
    "kor": "ko",
    "korean": "ko",
    # English
    "eng": "en",
    "english": "en",
    # Spanish
    "sp": "es",
    "spa": "es",
    "spanish": "es",
    # Chinese — `cn` is the country code many users reach for instinctively,
    # so accept it as a synonym for the language code `zh`.
    "cn": "zh",
    "chi": "zh",
    "zho": "zh",
    "cmn": "zh",
    "chinese": "zh",
    "mandarin": "zh",
    # French
    "fre": "fr",
    "fra": "fr",
    "french": "fr",
    # German
    "ger": "de",
    "deu": "de",
    "german": "de",
    # Portuguese
    "por": "pt",
    "portuguese": "pt",
    # Italian
    "ita": "it",
    "italian": "it",
    # Russian
    "rus": "ru",
    "russian": "ru",
}


# Tag forms a provider might use for the same logical language. Used for
# client-side filtering when a provider returns mixed-language results or uses a
# non-ISO-639-1 tag. Tags are matched case-insensitively as exact words *or* as
# longer-than-3-character substrings (so "Latin Spanish" matches "spanish" but
# "es" does not bleed into "estonian").
LANGUAGE_TAG_VARIANTS: dict[str, tuple[str, ...]] = {
    "ja": ("ja", "jpn", "jp", "japanese"),
    "ko": ("ko", "kor", "kr", "korean"),
    "en": ("en", "eng", "english"),
    "es": (
        "es", "spa", "spanish", "castilian",
        "es-es", "es-la", "es-419", "es-mx", "es-ar",
        "latin spanish", "spanish (latin america)", "spanish (spain)",
    ),
    "zh": (
        "zh", "chi", "zho", "cmn", "cn",
        "chinese", "mandarin", "cantonese",
        "zh-cn", "zh-tw", "zh-hk", "zh-hans", "zh-hant",
        "chs", "cht",
    ),
    "fr": ("fr", "fre", "fra", "french"),
    "de": ("de", "ger", "deu", "german"),
    "pt": ("pt", "por", "portuguese", "pt-br", "pt-pt", "brazilian portuguese"),
}


def lang_matches(target: str, *fields: str | None) -> bool:
    """Return True if any of `fields` plausibly refers to `target` language.

    `target` is the canonical ISO 639-1 code we care about (e.g. "ko").
    `fields` are free-form strings from a provider's response: tag, filename,
    release name, origin string, etc."""
    canonical = (target or "").strip().lower()
    if not canonical:
        return False
    canonical = LANGUAGE_ALIASES.get(canonical, canonical)
    variants = LANGUAGE_TAG_VARIANTS.get(canonical, (canonical,))
    short = {v for v in variants if len(v) <= 3}
    long = [v for v in variants if len(v) > 3]
    for field in fields:
        if not field:
            continue
        text = str(field).strip().lower()
        if not text:
            continue
        # Exact match (including short codes like "ko")
        if text in short or text in variants:
            return True
        # Tokenised match for compound fields like "Korean.srt" or "es-LA.WEB"
        tokens = re.split(r"[^a-z0-9]+", text)
        for token in tokens:
            if not token:
                continue
            if token in short or token in variants:
                return True
        # Substring match only for variants long enough to be unambiguous
        for variant in long:
            if variant in text:
                return True
    return False


@dataclass
class MediaInfo:
    source_url: str
    provider: str
    title: str | None = None
    title_aliases: list[str] | None = None
    season: str = "auto"
    episode: str = "auto"
    anilist_id: int | None = None
    imdb_id: str | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    mal_id: str | None = None
    netflix_id: str | None = None
    # True when the source is identifiably a movie. Used by output_dir +
    # download filename to skip the Season/Episode placeholders that make
    # sense for TV series but produce ugly 'Season Unknown' / 'S00E00'
    # paths for single-item movies.
    is_movie: bool = False


def title_source_url(title: str) -> str:
    return "title://" + urllib.parse.quote(title.strip())


def title_from_source_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "title":
        return None
    raw = (parsed.netloc + parsed.path).strip("/")
    return urllib.parse.unquote(raw).strip() or None


@dataclass
class SubtitleFile:
    provider: str
    language: str
    name: str
    url: str
    size: int | None = None
    release_source: str | None = None
    release: str | None = None
    origin: str | None = None
    source_provider: str | None = None
    media_title: str | None = None
    ai: bool = False
    # Raw language tag from the provider's response (e.g. "ko", "kor", "Korean").
    # Useful for diagnostics and for fuzzy matching when the requested code does
    # not strictly equal what the provider returns.
    provider_language: str | None = None
    # Extra HTTP headers some providers require to download the file body
    # (e.g. Addic7ed insists on a Referer and a browser-like User-Agent).
    # Merged into the request headers by save_subtitle/download_bytes.
    download_headers: dict[str, str] | None = None


@dataclass
class SearchResult:
    language: str
    episode: str
    provider: str
    status: str
    file: SubtitleFile | None = None
    error: str | None = None


@dataclass
class ManualSearchSuggestion:
    language: str
    label: str
    url: str
    note: str


@dataclass
class ProviderDebugRecord:
    provider: str
    episode: str
    language: str
    count: int
    language_tags: dict[str, int] = field(default_factory=dict)
    source_tags: dict[str, int] = field(default_factory=dict)
    extensions: dict[str, int] = field(default_factory=dict)
    ai_count: int = 0
    hi_count: int = 0
    dubbed_count: int = 0
    example: str = ""
    error: str | None = None


@dataclass
class AniListCandidate:
    id: int
    romaji: str | None
    english: str | None
    native: str | None
    season_year: int | None
    episodes: int | None
    # AniList enum: TV / TV_SHORT / MOVIE / SPECIAL / OVA / ONA / MUSIC.
    # The wizard treats MOVIE (and single-episode SPECIAL/OVA/ONA) as
    # movie-shape sources so the user does not see Q6 and downstream
    # filenames skip the Season Unknown / S00E00 placeholders.
    format: str | None = None

    def is_movie(self) -> bool:
        if (self.format or "").upper() == "MOVIE":
            return True
        # AniList sometimes mislabels MOVIE as SPECIAL/OVA. Falling back
        # on episodes==1 catches those — and is also a meaningful signal
        # for single-OVA releases that the user likely wants treated as
        # a single item rather than as S01E01 of a series.
        if self.episodes == 1 and (self.format or "").upper() in {"SPECIAL", "OVA", "ONA", ""}:
            return True
        return False

    def label(self) -> str:
        names = [n for n in [self.romaji, self.english, self.native] if n]
        deduped = []
        for name in names:
            if name not in deduped:
                deduped.append(name)
        meta = []
        if self.season_year:
            meta.append(str(self.season_year))
        if self.episodes:
            meta.append(f"{self.episodes} eps")
        suffix = f" ({', '.join(meta)})" if meta else ""
        return f"{self.id}: {' / '.join(deduped)}{suffix}"


@dataclass
class AniListInfo:
    id: int
    title: str | None
    episodes: int | None
    title_aliases: list[str] | None = None
    # AniList format enum (TV / TV_SHORT / MOVIE / SPECIAL / OVA / ONA /
    # MUSIC). MOVIE — or a single-episode SPECIAL/OVA/ONA — flips the
    # output to movie layout (no Season subfolder, no S00E00 placeholder).
    format: str | None = None

    def is_movie(self) -> bool:
        if (self.format or "").upper() == "MOVIE":
            return True
        if self.episodes == 1 and (self.format or "").upper() in {"SPECIAL", "OVA", "ONA", ""}:
            return True
        return False


def _norm_title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def unique_titles(titles: Iterable[str | None]) -> list[str]:
    """Return non-empty title variants preserving order and removing
    case-insensitive duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for title in titles:
        if not isinstance(title, str):
            continue
        cleaned = re.sub(r"\s+", " ", title).strip()
        if not cleaned:
            continue
        key = _norm_title_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def media_title_queries(media: MediaInfo) -> list[str]:
    """Search titles to try with providers that only accept free-text titles."""
    return unique_titles([media.title, *(media.title_aliases or [])])


def add_media_title_aliases(media: MediaInfo, aliases: Iterable[str | None]) -> None:
    merged = unique_titles([*(media.title_aliases or []), *aliases])
    media.title_aliases = [
        title for title in merged
        if _norm_title_key(title) != _norm_title_key(media.title or "")
    ]


def request_json(url: str, *, headers: dict[str, str] | None = None, data: dict | None = None) -> object:
    payload = None
    req_headers = {
        "User-Agent": "getsubtitle/0.1",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if url == ANILIST_API and '"data":{"Media":null}' in body:
            raise CliError("AniList could not resolve the inferred title.") from e
        if e.code == 429 and "jimaku.cc" in url:
            raise CliError("Jimaku rate limit exceeded. Wait a bit, then retry; bulk episode downloads now cache the entry lookup.") from e
        raise CliError(f"HTTP {e.code} from {redact_url(url)}: {body[:500]}") from e
    except urllib.error.URLError as e:
        raise CliError(f"Network error for {redact_url(url)}: {e.reason}") from e


# ---------------------------------------------------------------------------
# TMDB — movie / TV title resolution
# ---------------------------------------------------------------------------
# Used to convert "--title TEXT" into a TMDB ID (and the IMDb ID alongside it),
# which then unlocks Wyzie's primary search path. All TMDB calls are
# best-effort: any HTTP or network failure returns None instead of raising,
# because TMDB is a metadata bridge, not a hard dependency. The CLI works
# without it (just with fewer auto-resolved IDs).

# Module-level cache so repeated lookups in the same run don't re-hit TMDB.
_TMDB_CACHE: dict[str, object] = {}


def _tmdb_get(path: str, params: dict[str, str], api_key: str) -> dict | None:
    """GET https://api.themoviedb.org/3/<path>?<params>&api_key=...
    Returns parsed JSON dict or None on any failure. Cached per call."""
    full_params = {**params, "api_key": api_key}
    url = f"{TMDB_API}/{path.lstrip('/')}?" + urllib.parse.urlencode(full_params)
    # Cache key omits api_key so we don't leak it into the dict.
    cache_key = f"{path}?" + urllib.parse.urlencode(params)
    if cache_key in _TMDB_CACHE:
        return _TMDB_CACHE[cache_key]  # type: ignore[return-value]
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "getsubtitle/0.1", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            body = res.read().decode("utf-8")
        data = json.loads(body)
    except urllib.error.HTTPError as e:
        # 401 = bad/missing key. Don't crash the run; downstream code falls back.
        if e.code in (401, 404):
            _TMDB_CACHE[cache_key] = None
            return None
        # Other HTTP errors: cache the None so we don't retry on the same URL.
        _TMDB_CACHE[cache_key] = None
        return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        _TMDB_CACHE[cache_key] = None
        return None
    if not isinstance(data, dict):
        _TMDB_CACHE[cache_key] = None
        return None
    _TMDB_CACHE[cache_key] = data
    return data


def tmdb_search_movie(title: str, year: int | None = None, *, api_key: str | None = None) -> dict | None:
    """Search TMDB for a movie. Returns the top result with imdb_id resolved,
    or None if no key is configured / no match / network error.

    Shape: {tmdb_id, imdb_id, title, year, original_language}."""
    if api_key is None:
        api_key = get_provider_api_key("tmdb")
    if not api_key or not title.strip():
        return None
    params: dict[str, str] = {"query": title.strip()}
    if year:
        params["year"] = str(year)
    data = _tmdb_get("search/movie", params, api_key)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    tmdb_id = top.get("id")
    if not tmdb_id:
        return None
    # Pull imdb_id from the movie detail endpoint.
    detail = _tmdb_get(f"movie/{tmdb_id}", {}, api_key) or {}
    release = top.get("release_date") or ""
    return {
        "tmdb_id": str(tmdb_id),
        "imdb_id": detail.get("imdb_id"),
        "title": top.get("title") or top.get("original_title"),
        "year": int(release[:4]) if release[:4].isdigit() else None,
        "original_language": top.get("original_language"),
    }


def tmdb_search_tv(title: str, *, api_key: str | None = None) -> dict | None:
    """Search TMDB for a TV show. Returns top match with imdb_id resolved.
    Shape: {tmdb_id, imdb_id, title, year, original_language}."""
    if api_key is None:
        api_key = get_provider_api_key("tmdb")
    if not api_key or not title.strip():
        return None
    data = _tmdb_get("search/tv", {"query": title.strip()}, api_key)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    tmdb_id = top.get("id")
    if not tmdb_id:
        return None
    ext = _tmdb_get(f"tv/{tmdb_id}/external_ids", {}, api_key) or {}
    first_air = top.get("first_air_date") or ""
    return {
        "tmdb_id": str(tmdb_id),
        "imdb_id": ext.get("imdb_id"),
        "title": top.get("name") or top.get("original_name"),
        "year": int(first_air[:4]) if first_air[:4].isdigit() else None,
        "original_language": top.get("original_language"),
    }


def tmdb_external_ids(media_type: str, tmdb_id: str | int, *, api_key: str | None = None) -> dict | None:
    """Resolve a TMDB ID to its IMDb (and other) IDs via the external_ids
    endpoint. media_type is 'movie' or 'tv'."""
    if api_key is None:
        api_key = get_provider_api_key("tmdb")
    if not api_key:
        return None
    if media_type == "movie":
        # Movies expose imdb_id on the detail endpoint; external_ids is for tv.
        data = _tmdb_get(f"movie/{tmdb_id}", {}, api_key) or {}
        return {"imdb_id": data.get("imdb_id")}
    if media_type == "tv":
        return _tmdb_get(f"tv/{tmdb_id}/external_ids", {}, api_key)
    return None


def tmdb_tv_season_episode_count(tmdb_id: str | int, season: int, *, api_key: str | None = None) -> int | None:
    """Return the number of episodes in a TV season per TMDB, or None on miss.
    Useful for `-e all` expansion on non-anime shows."""
    if api_key is None:
        api_key = get_provider_api_key("tmdb")
    if not api_key:
        return None
    data = _tmdb_get(f"tv/{tmdb_id}/season/{season}", {}, api_key)
    if not data:
        return None
    episodes = data.get("episodes")
    if isinstance(episodes, list):
        return len(episodes)
    return None


def enrich_media_from_tmdb(
    media: "MediaInfo",
    langs: list[str] | None = None,
    *,
    allow_existing_anilist: bool = False,
    prefer_movie: bool = False,
) -> bool:
    """If a TMDB API key is configured and we have a title but no
    IMDb/TMDB/AniList ID yet, search TMDB and populate the IDs.

    Returns True if anything was added. Best-effort — silently no-ops
    without a key, on network failure, or when no result matches.

    Skips Japanese-origin results when the user asked for `ja` subs, so
    the existing AniList → Jimaku path stays intact for anime. (Wyzie's
    Japanese coverage for live-action is decent; Jimaku is anime-only.)"""
    if not media.title:
        return False
    if media.imdb_id or media.tmdb_id or (media.anilist_id and not allow_existing_anilist):
        return False
    api_key = get_provider_api_key("tmdb")
    if not api_key:
        return False
    searchers = [tmdb_search_movie, tmdb_search_tv] if prefer_movie else [tmdb_search_tv, tmdb_search_movie]
    # Preserve the AniList-driven path for "user wants Japanese subs of a
    # Japanese-origin title" — Jimaku needs AniList IDs, and TMDB filling
    # in imdb/tmdb here would shortcut the needs_anilist branch.
    wants_japanese = bool(langs) and "ja" in langs
    for title in media_title_queries(media):
        for searcher in searchers:
            hit = searcher(title, api_key=api_key)  # type: ignore[misc]
            if not hit:
                continue
            is_japanese = (hit.get("original_language") or "").lower() == "ja"
            if wants_japanese and is_japanese:
                continue
            if hit.get("tmdb_id"):
                media.tmdb_id = hit["tmdb_id"]
            if hit.get("imdb_id"):
                media.imdb_id = hit["imdb_id"]
            if media.tmdb_id or media.imdb_id:
                return True
    return False


def request_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 getsubtitle/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def download_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": "getsubtitle/0.1"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {e.code} downloading {redact_url(url)}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise CliError(f"Network error downloading {redact_url(url)}: {e.reason}") from e


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.query:
        return url
    sensitive = {"key", "api_key", "apikey", "token", "access_token"}
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(
        [(name, "REDACTED" if name.lower() in sensitive else value) for name, value in params]
    )
    return urllib.parse.urlunparse(parsed._replace(query=query))


def macos_keychain_available() -> bool:
    return sys.platform == "darwin" and shutil.which("security") is not None


def keychain_get(service: str, account: str) -> str | None:
    if not macos_keychain_available():
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = getattr(result, "stdout", "").strip()
    return value or None


def keychain_set(service: str, account: str, password: str) -> None:
    if not macos_keychain_available():
        raise CliError("Secure key storage is only implemented for macOS Keychain right now; set the provider API key in your shell instead.")
    result = subprocess.run(
        ["security", "add-generic-password", "-U", "-s", service, "-a", account, "-w", password],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CliError(f"Could not save API key to Keychain: {result.stderr.strip()}")


def keychain_delete(service: str, account: str) -> bool:
    if not macos_keychain_available():
        return False
    result = subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def masked_input(prompt: str) -> str:
    if not sys.stdin.isatty():
        return ""

    if not sys.platform.startswith(("darwin", "linux", "freebsd")):
        return getpass.getpass(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars: list[str] = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in {"\x7f", "\b"}:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch == "\x15":
                while chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                sys.stdout.flush()
                continue
            if ch and ch.isprintable():
                chars.append(ch)
                sys.stdout.write("*")
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return "".join(chars)


def open_in_browser(url: str) -> None:
    if sys.platform == "darwin":
        cmd = ["open", url]
    elif shutil.which("xdg-open"):
        cmd = ["xdg-open", url]
    elif shutil.which("open"):
        cmd = ["open", url]
    else:
        raise CliError("No browser opener found. Open the URL manually in your browser.")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise CliError(f"Could not open browser: {result.stderr.strip()}")


def open_folder(path: Path) -> None:
    folder = path if path.is_dir() else path.parent
    if sys.platform == "darwin":
        cmd = ["open", str(folder)]
    elif sys.platform.startswith("win"):
        cmd = ["explorer", str(folder)]
    elif shutil.which("xdg-open"):
        cmd = ["xdg-open", str(folder)]
    else:
        raise CliError(f"No folder opener found. Folder: {folder}")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise CliError(f"Could not open folder: {result.stderr.strip()}")


def get_jimaku_api_key() -> str | None:
    return get_provider_api_key("jimaku", prompt_if_missing=True)


def get_wyzie_api_key() -> str | None:
    return get_provider_api_key("wyzie", prompt_if_missing=True)


def get_subdl_api_key(*, prompt_if_missing: bool = False) -> str | None:
    return get_provider_api_key("subdl", prompt_if_missing=prompt_if_missing)


def provider_has_api_key(provider: str) -> bool:
    info = KEY_PROVIDERS[provider]
    return bool(os.environ.get(str(info["env"])) or keychain_get(KEYCHAIN_SERVICE, str(info["account"])))


def get_provider_api_key(provider: str, *, prompt_if_missing: bool = False) -> str | None:
    info = KEY_PROVIDERS[provider]
    env_key = os.environ.get(str(info["env"]))
    if env_key:
        return env_key

    stored_key = keychain_get(KEYCHAIN_SERVICE, str(info["account"]))
    if stored_key:
        return stored_key

    if not prompt_if_missing or not sys.stdin.isatty():
        return None

    print(f"{info['label']} API key not found.")
    print(f"Use: {info['use']}")
    print(f"Create one at {info['url']}")
    if macos_keychain_available():
        print("Paste it here. It will be saved in macOS Keychain.")
    else:
        print(f"Paste it here for this run, or set {info['env']} to avoid this prompt next time.")
    key = masked_input(f"{info['label']} API key: ").strip()
    if not key:
        return None
    if macos_keychain_available():
        keychain_set(KEYCHAIN_SERVICE, str(info["account"]), key)
        print(f"Saved {info['label']} API key to macOS Keychain.")
    else:
        print(f"Using {info['label']} API key for this run only.")
    return key


def provider_choices(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip().lower()
    if value == "-all":
        value = "all"
    if value == "all":
        return list(KEY_PROVIDERS)
    providers = [part.strip().lower().lstrip("-") for part in value.split(",") if part.strip()]
    invalid = [provider for provider in providers if provider not in KEY_PROVIDERS]
    if invalid:
        raise CliError(f"Unknown key provider: {', '.join(invalid)}. Use one of: {', '.join(KEY_PROVIDERS)}, all.")
    return providers


def prompt_for_key_provider(action: str) -> list[str]:
    if not sys.stdin.isatty():
        raise CliError(f"--{action}-key needs a provider in non-interactive mode. Example: --{action}-key jimaku")
    print("Available API key providers:")
    for idx, (provider, info) in enumerate(KEY_PROVIDERS.items(), start=1):
        print(f"  {idx}. {provider} - {info['use']}")
    print(f"  {len(KEY_PROVIDERS) + 1}. all")
    choice = input(f"Choose provider to {action} [1]: ").strip() or "1"
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(KEY_PROVIDERS):
            return [list(KEY_PROVIDERS)[idx - 1]]
        if idx == len(KEY_PROVIDERS) + 1:
            return list(KEY_PROVIDERS)
    return provider_choices(choice)


def set_api_keys(provider_value: str | None) -> int:
    providers = provider_choices(provider_value) if provider_value else prompt_for_key_provider("set")
    for provider in providers:
        info = KEY_PROVIDERS[provider]
        print(f"\n{info['label']} ({provider})")
        print(f"Use: {info['use']}")
        print(f"Create key: {info['url']}")
        if not macos_keychain_available():
            print(f"Secure key storage is only implemented for macOS Keychain right now.")
            print(f"Set this environment variable instead: {info['env']}")
            continue
        key = masked_input(f"{info['label']} API key: ").strip()
        if not key:
            print("Skipped: no key entered.")
            continue
        keychain_set(KEYCHAIN_SERVICE, str(info["account"]), key)
        print(f"Saved {info['label']} API key to macOS Keychain.")
    return 0


def reset_api_keys(provider_value: str | None) -> int:
    providers = provider_choices(provider_value) if provider_value else prompt_for_key_provider("reset")
    for provider in providers:
        info = KEY_PROVIDERS[provider]
        if macos_keychain_available():
            deleted = keychain_delete(KEYCHAIN_SERVICE, str(info["account"]))
            print(f"Deleted saved {info['label']} API key." if deleted else f"No saved {info['label']} API key was found.")
        else:
            print(f"No macOS Keychain is available. Remove {info['env']} from your environment instead.")
    return 0


def parse_wyzie_sources_response(data: object) -> list[dict[str, str]]:
    """Normalize Wyzie /sources responses into [{source, status, note}]."""
    raw_items: object
    if isinstance(data, dict):
        raw_items = data.get("sources") or data.get("data") or data.get("results") or data
        if isinstance(raw_items, dict):
            out = []
            for source, value in raw_items.items():
                if isinstance(value, dict):
                    status = str(value.get("status") or value.get("tier") or value.get("access") or value.get("enabled") or "unknown")
                    note = str(value.get("note") or value.get("message") or "")
                else:
                    status = str(value)
                    note = ""
                out.append({"source": str(source), "status": status, "note": note})
            return sorted(out, key=lambda item: item["source"].lower())
    else:
        raw_items = data
    if isinstance(raw_items, list):
        out = []
        for item in raw_items:
            if isinstance(item, str):
                out.append({"source": item, "status": "available", "note": ""})
            elif isinstance(item, dict):
                source = item.get("source") or item.get("name") or item.get("id") or item.get("slug")
                if not source:
                    continue
                status = str(item.get("status") or item.get("tier") or item.get("access") or item.get("enabled") or "unknown")
                note = str(item.get("note") or item.get("message") or "")
                out.append({"source": str(source), "status": status, "note": note})
        return sorted(out, key=lambda item: item["source"].lower())
    return []


def fetch_wyzie_sources(api_key: str) -> list[dict[str, str]]:
    url = WYZIE_SOURCES_API + "?" + urllib.parse.urlencode({"key": api_key})
    return parse_wyzie_sources_response(request_json(url))


def build_sources_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Check subtitle provider/source availability for configured API keys.",
        epilog=textwrap.dedent(
            """
            Examples:
              getsubtitle sources --check
              getsubtitle sources --check --provider wyzie

            Notes:
              Wyzie source access can vary by key/tier. This command asks
              Wyzie which internal sources your current key can use, so you
              can see whether SubDL/OpenSubtitles/etc. are available before
              adding direct provider integrations.
            """
        ),
    )
    p.add_argument("--check", action="store_true", help="Check configured provider/source access.")
    p.add_argument("--provider", choices=["wyzie", "all"], default="all", help="Provider to check. Default: all.")
    return p


def sources_main(argv: list[str]) -> int:
    args = build_sources_parser().parse_args(argv)
    if not args.check:
        args.check = True
    if args.provider in {"wyzie", "all"}:
        api_key = get_provider_api_key("wyzie", prompt_if_missing=False)
        print("Wyzie sources:")
        if not api_key:
            print("  auth required - run: getsubtitle --set-key wyzie")
            return 1
        try:
            sources = fetch_wyzie_sources(api_key)
        except CliError as e:
            print(f"  error - {e}")
            return 1
        if not sources:
            print("  no source data returned")
            return 1
        width = max(6, *(len(item["source"]) for item in sources))
        for item in sources:
            note = f"  {item['note']}" if item.get("note") else ""
            print(f"  {item['source']:<{width}}  {item['status']}{note}")
    return 0


_VOWELS = set("aeiouy")


def _cased_word(word: str) -> str:
    # Preserve likely acronyms/abbreviations such as "mf" -> "MF", "tv" -> "TV".
    # Heuristic: all letters, length 2-3, no vowels. "of"/"in" still have vowels
    # so they stay title-cased.
    if word.isalpha() and 2 <= len(word) <= 3 and not (set(word.lower()) & _VOWELS):
        return word.upper()
    return word.title()


def slug_to_title(slug: str) -> str:
    slug = urllib.parse.unquote(slug)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug)
    words = slug.strip().split()
    return " ".join(_cased_word(w) for w in words)


def clean_page_title(title: str) -> str:
    title = unescape(title)
    title = re.sub(r"\s*-\s*Watch on Crunchyroll\s*$", "", title, flags=re.I)
    title = re.sub(r"\s*\|\s*Crunchyroll\s*$", "", title, flags=re.I)
    title = re.sub(r"^Watch\s+", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title)
    title = title.strip()
    lower = title.lower()
    if "crunchyroll" in lower and "watch popular anime" in lower:
        return ""
    if lower in {"crunchyroll", "crunchyroll: watch popular anime, play games & shop online"}:
        return ""
    return title


def clean_catalog_title(title: str, provider: str) -> str:
    title = clean_page_title(title)
    provider_patterns = {
        "imdb": [
            r"\s*\(\d{4}\)\s*-\s*IMDb\s*$",
            r"\s*-\s*IMDb\s*$",
        ],
        "tmdb": [
            r"\s*\(\d{4}\)\s*[—-]\s*The Movie Database\s*\(TMDB\)\s*$",
            r"\s*[—-]\s*The Movie Database\s*\(TMDB\)\s*$",
        ],
        "letterboxd": [
            r"\s*\(\d{4}\)\s+directed by .*$",
            r"\s*\u2022\s*Letterboxd\s*$",
        ],
        "rottentomatoes": [
            r"\s*\|\s*Rotten Tomatoes\s*$",
        ],
        "myanimelist": [
            r"\s*-\s*MyAnimeList\.net\s*$",
            r"\s*-\s*MyAnimeList\s*$",
        ],
        "thetvdb": [
            r"\s*-\s*TheTVDB\.com\s*$",
            r"\s*-\s*TheTVDB\s*$",
        ],
        "trakt": [
            r"\s*-\s*Trakt\s*$",
        ],
    }
    for pattern in provider_patterns.get(provider, []):
        title = re.sub(pattern, "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def provider_from_host(host: str) -> str:
    host = host.lower().removeprefix("www.")
    if host.endswith("imdb.com"):
        return "imdb"
    if host.endswith("themoviedb.org"):
        return "tmdb"
    if host.endswith("letterboxd.com"):
        return "letterboxd"
    if host.endswith("rottentomatoes.com"):
        return "rottentomatoes"
    if host.endswith("myanimelist.net"):
        return "myanimelist"
    if host.endswith("thetvdb.com"):
        return "thetvdb"
    if host.endswith("trakt.tv"):
        return "trakt"
    return host


def title_from_json_ld(html: str) -> str | None:
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        raw = unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            candidates = graph if isinstance(graph, list) else [item]
            for candidate in candidates:
                if isinstance(candidate, dict):
                    name = candidate.get("name") or candidate.get("headline")
                    if isinstance(name, str) and name.strip():
                        return name.strip()
    return None


def title_from_html_metadata(html: str) -> str | None:
    for meta_match in re.finditer(r"<meta\b[^>]*>", html, re.I):
        tag = meta_match.group(0)
        prop_match = re.search(r'\b(?:property|name)=["\']([^"\']+)["\']', tag, re.I)
        content_match = re.search(r'\bcontent=["\']([^"\']+)["\']', tag, re.I)
        if prop_match and content_match and prop_match.group(1).lower() in {"og:title", "twitter:title"}:
            return content_match.group(1)
    json_ld = title_from_json_ld(html)
    if json_ld:
        return json_ld
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if match:
        return match.group(1)
    return None


def title_from_imdb_id(imdb_id: str) -> str | None:
    query = """
    SELECT ?item ?itemLabel WHERE {
      ?item wdt:P345 "%s".
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    LIMIT 1
    """ % imdb_id
    url = WIKIDATA_SPARQL_API + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    try:
        with _StatusLine(f"Looking up title for IMDb {imdb_id}"):
            data = request_json(url, headers={"Accept": "application/sparql-results+json"})
    except CliError:
        return None
    bindings = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    if bindings:
        value = bindings[0].get("itemLabel", {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def wikidata_claim_value(claims: dict, prop: str) -> str | None:
    values = claims.get(prop) or []
    if not values:
        return None
    value = values[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    return value if isinstance(value, str) and value.strip() else None


def wikidata_entity_from_statement(prop: str, value: str) -> dict | None:
    for search in [f"haswbstatement:{prop}={value}", value]:
        api_query = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": search,
                "origin": "*",
            }
        )
        try:
            search_data = request_json(f"https://www.wikidata.org/w/api.php?{api_query}")
            results = search_data.get("query", {}).get("search", []) if isinstance(search_data, dict) else []
            for result in results:
                qid = result.get("title")
                entity_data = request_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
                entity = entity_data.get("entities", {}).get(qid, {}) if isinstance(entity_data, dict) else {}
                claims = entity.get("claims", {}) if isinstance(entity, dict) else {}
                if wikidata_claim_value(claims, prop) == value:
                    return entity if isinstance(entity, dict) else None
        except CliError:
            continue
    return None


def update_media_from_wikidata_entity(media: MediaInfo, entity: dict) -> None:
    labels = entity.get("labels", {}) if isinstance(entity, dict) else {}
    aliases = entity.get("aliases", {}) if isinstance(entity, dict) else {}
    claims = entity.get("claims", {}) if isinstance(entity, dict) else {}
    label = labels.get("en", {}).get("value") or labels.get("ja", {}).get("value")
    if isinstance(label, str) and label.strip():
        media.title = media.title or label
    discovered: list[str] = []
    for lang in ("en", "ja", "ko", "es"):
        value = labels.get(lang, {}).get("value")
        if isinstance(value, str) and value.strip():
            discovered.append(value)
        for alias in aliases.get(lang, []) if isinstance(aliases.get(lang), list) else []:
            value = alias.get("value") if isinstance(alias, dict) else None
            if isinstance(value, str) and value.strip():
                discovered.append(value)
    add_media_title_aliases(media, discovered)
    media.imdb_id = media.imdb_id or wikidata_claim_value(claims, "P345")
    media.tmdb_id = media.tmdb_id or wikidata_claim_value(claims, "P4983")
    media.tvdb_id = media.tvdb_id or wikidata_claim_value(claims, "P4835")


def enrich_external_ids_from_wikidata(media: MediaInfo) -> None:
    if media.imdb_id:
        entity = wikidata_entity_from_statement("P345", media.imdb_id)
        if entity:
            update_media_from_wikidata_entity(media, entity)
            return
    if media.tmdb_id:
        entity = wikidata_entity_from_statement("P4983", media.tmdb_id)
        if entity:
            update_media_from_wikidata_entity(media, entity)
            return
    if media.tvdb_id:
        entity = wikidata_entity_from_statement("P4835", media.tvdb_id)
        if entity:
            update_media_from_wikidata_entity(media, entity)


def external_ids_from_tvdb_id(tvdb_id: str) -> tuple[str | None, str | None, str | None]:
    api_query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"haswbstatement:P4835={tvdb_id}",
            "origin": "*",
        }
    )
    try:
        search_data = request_json(f"https://www.wikidata.org/w/api.php?{api_query}")
        results = search_data.get("query", {}).get("search", []) if isinstance(search_data, dict) else []
        if results:
            qid = results[0].get("title")
            entity_data = request_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
            entity = entity_data.get("entities", {}).get(qid, {}) if isinstance(entity_data, dict) else {}
            labels = entity.get("labels", {}) if isinstance(entity, dict) else {}
            claims = entity.get("claims", {}) if isinstance(entity, dict) else {}

            label = labels.get("en", {}).get("value") or labels.get("ja", {}).get("value")
            return (
                label if isinstance(label, str) and label.strip() else None,
                wikidata_claim_value(claims, "P345"),
                wikidata_claim_value(claims, "P4983"),
            )
    except CliError:
        pass

    query = """
    SELECT ?item ?itemLabel ?imdb ?tmdbTv WHERE {
      ?item wdt:P4835 "%s".
      OPTIONAL { ?item wdt:P345 ?imdb. }
      OPTIONAL { ?item wdt:P4983 ?tmdbTv. }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    LIMIT 1
    """ % tvdb_id
    url = WIKIDATA_SPARQL_API + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    try:
        with _StatusLine(f"Looking up external IDs for TVDB {tvdb_id}"):
            data = request_json(url, headers={"Accept": "application/sparql-results+json"})
    except CliError:
        return None, None, None
    bindings = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    if not bindings:
        return None, None, None
    first = bindings[0]
    title = first.get("itemLabel", {}).get("value")
    imdb_id = first.get("imdb", {}).get("value")
    tmdb_id = first.get("tmdbTv", {}).get("value")
    return (
        title if isinstance(title, str) and title.strip() else None,
        imdb_id if isinstance(imdb_id, str) and imdb_id.strip() else None,
        tmdb_id if isinstance(tmdb_id, str) and tmdb_id.strip() else None,
    )


def bridge_anilist_to_external_ids(media: MediaInfo) -> None:
    if not media.anilist_id or media.imdb_id or media.tmdb_id:
        return
    try:
        with _StatusLine("Loading anime ID database"):
            data = request_json(ANIME_IDS_URL)
    except CliError:
        return
    if not isinstance(data, dict):
        return
    target = str(media.anilist_id)
    match = None
    for item in data.values():
        if isinstance(item, dict) and str(item.get("anilist_id")) == target:
            match = item
            break
    if not match:
        return
    tvdb_id = match.get("tvdb_id")
    if tvdb_id:
        media.tvdb_id = str(tvdb_id)
        title, imdb_id, tmdb_id = external_ids_from_tvdb_id(str(tvdb_id))
        media.title = media.title or title
        media.imdb_id = media.imdb_id or imdb_id
        media.tmdb_id = media.tmdb_id or tmdb_id


def bridge_external_ids_to_anilist(media: MediaInfo) -> None:
    if media.anilist_id:
        return
    # MAL is indexed directly in Anime-IDs, so we don't need a Wikidata round
    # trip when only mal_id is set. Other external IDs may still benefit from
    # Wikidata enrichment to pick up missing imdb/tmdb/tvdb cross-references.
    if not media.mal_id:
        enrich_external_ids_from_wikidata(media)
    if not (media.mal_id or media.imdb_id or media.tmdb_id or media.tvdb_id):
        return
    try:
        with _StatusLine("Loading anime ID database"):
            data = request_json(ANIME_IDS_URL)
    except CliError:
        return
    if not isinstance(data, dict):
        return

    candidates = []
    for item in data.values():
        if not isinstance(item, dict):
            continue
        if media.mal_id and str(item.get("mal_id")) == str(media.mal_id):
            candidates.append(item)
        elif media.imdb_id and item.get("imdb_id") == media.imdb_id:
            candidates.append(item)
        elif media.tmdb_id and str(media.tmdb_id) in {
            str(item.get("tmdb_id")),
            str(item.get("tmdb_show_id")),
            str(item.get("tmdb_movie_id")),
        }:
            candidates.append(item)
        elif media.tvdb_id and str(item.get("tvdb_id")) == str(media.tvdb_id):
            candidates.append(item)

    if not candidates:
        return
    if media.season.isdigit():
        season = int(media.season)
        season_matches = [item for item in candidates if item.get("tvdb_season") == season]
        if season_matches:
            candidates = season_matches
    anilist_id = candidates[0].get("anilist_id")
    if anilist_id:
        media.anilist_id = int(anilist_id)


def bridge_external_ids_to_anilist_by_title(media: MediaInfo) -> None:
    """Last-resort fallback when the anime-IDs database doesn't cover this
    title (common for anime movies and obscure OVAs that have IMDb/TMDB
    pages but no entry in the cross-reference DB). Searches AniList by
    title and picks the top hit — only used when the user explicitly
    requested ja so Jimaku can be queried.

    Safe to call with no IDs set; bails when there's no usable title."""
    if media.anilist_id:
        return
    title = (media.title or "").strip()
    if not title:
        return
    try:
        candidates = search_anilist(title, limit=3)
    except CliError:
        return
    if not candidates:
        return
    # Bias toward movies when the source URL is a TMDB /movie/ or
    # Letterboxd /film/ — protects against picking a TV-series candidate
    # by the same name (e.g. "Frieren" the movie vs the TV series).
    if media.is_movie:
        movie_hits = [c for c in candidates if c.is_movie()]
        if movie_hits:
            candidates = movie_hits
    media.anilist_id = candidates[0].id


def infer_from_catalog_url(url: str, provider: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    html = request_text(url)
    raw_title = title_from_html_metadata(html) if html else None
    title = clean_catalog_title(raw_title, provider) if raw_title else None
    imdb_match = re.search(r"/title/(tt\d+)", parsed.path)
    imdb_id = imdb_match.group(1) if provider == "imdb" and imdb_match else None
    tmdb_match = re.search(r"/(?:movie|tv)/(\d+)", parsed.path)
    tmdb_id = tmdb_match.group(1) if provider == "tmdb" and tmdb_match else None
    # Identify movie sources straight from the URL where possible. TMDB
    # uses /movie/, Letterboxd uses /film/. Skips season/episode subdirs
    # and the S00E00 filename placeholder downstream.
    path_low = parsed.path.lower()
    is_movie = (
        (provider == "tmdb" and "/movie/" in path_low)
        or (provider == "letterboxd" and "/film/" in path_low)
    )
    mal_match = re.search(r"/anime/(\d+)", parsed.path)
    mal_id = mal_match.group(1) if provider == "myanimelist" and mal_match else None
    tvdb_id: str | None = None
    if provider == "thetvdb":
        # /series/<numeric-id> URLs carry the ID in the path directly.
        path_id = re.search(r"/series/(\d+)", parsed.path)
        if path_id:
            tvdb_id = path_id.group(1)
        elif html:
            # /series/<slug> URLs need the ID scraped from the page body.
            tvdb_id = tvdb_id_from_html(html)
    if not title and imdb_id:
        title = title_from_imdb_id(imdb_id)
    return MediaInfo(
        source_url=url,
        provider=provider,
        title=title,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        mal_id=mal_id,
        tvdb_id=tvdb_id,
        is_movie=is_movie,
    )


_TVDB_ID_PATTERNS = (
    # Image CDN URLs encode the series ID:
    # https://artworks.thetvdb.com/banners/series/<id>/...
    re.compile(r"artworks\.thetvdb\.com/[^\"'<>\s]*series/(\d+)/", re.I),
    # Internal links to season/episode subpages
    re.compile(r"/series/(\d{3,})/(?:seasons|episodes|allartwork|cast|crew)\b", re.I),
    # JSON-LD or data attribute fallbacks
    re.compile(r'"identifier"\s*:\s*"?(\d{3,})"?', re.I),
    re.compile(r'\bdata-series-id\s*=\s*["\'](\d+)["\']', re.I),
)


def tvdb_id_from_html(html: str) -> str | None:
    """Best-effort extraction of a TheTVDB numeric series ID from a slug page.

    Public for testing. TheTVDB does not surface the ID in og: tags; instead
    we look at the artworks CDN URLs embedded in the page, internal links to
    season/episode/cast subpages, and a couple of fallback attributes.
    Returns None when nothing plausible matches."""
    if not html:
        return None
    for pattern in _TVDB_ID_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def infer_from_anilist_url(url: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    anilist_id: int | None = None
    title: str | None = None
    # Forms: /anime/<id>/<slug>/ or /manga/<id>/<slug>/
    if len(parts) >= 2 and parts[0] in {"anime", "manga"} and parts[1].isdigit():
        anilist_id = int(parts[1])
    if len(parts) >= 3:
        title = slug_to_title(parts[2])
    return MediaInfo(
        source_url=url,
        provider="anilist",
        title=title,
        anilist_id=anilist_id,
    )


# Common multi-season markers at the end of a slug-derived title. Used to
# split "Mashle Magic And Muscles Season 2" → ("Mashle Magic And Muscles", 2)
# so AniList search hits the right season entry and `-s` reflects the URL.
_TRAILING_SEASON_RE = re.compile(
    r"\s*(?:[-:]\s*)?"
    r"(?:season\s*0*(\d+)"
    r"|0*(\d+)(?:st|nd|rd|th)\s+season"
    r"|s(?:eason)?\s*0*(\d+)"
    r"|part\s*0*(\d+)"
    r"|cours?\s*0*(\d+))"
    r"\s*$",
    re.IGNORECASE,
)


def parse_season_from_title(title: str) -> tuple[str, int | None]:
    """Strip a trailing 'Season N' / 'Part N' / 'Cour N' marker from a title.
    Returns (cleaned_title, season_number). When no marker is present
    returns (title, None) so callers can fall back to their default."""
    if not title:
        return title, None
    m = _TRAILING_SEASON_RE.search(title)
    if not m:
        return title, None
    season = next((int(g) for g in m.groups() if g), None)
    cleaned = title[: m.start()].rstrip(" -:·–—")
    return cleaned or title, season


def infer_from_crunchyroll_url(url: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    title = None
    episode = "auto"
    season: str = "auto"
    # Crunchyroll URLs include a stable alphanumeric series/episode ID like
    # `/series/GEXH3W2W7/...` — captured here so future Crunchyroll-specific
    # lookups (e.g. private API or a Wikidata bridge) can use it. Currently
    # informational; the slug + AniList search still does the real work.
    crunchyroll_id: str | None = None
    if len(parts) >= 2 and parts[0] in ("series", "watch"):
        if re.fullmatch(r"[A-Z0-9]{6,}", parts[1]):
            crunchyroll_id = parts[1]

    html = request_text(url)
    if html:
        if "Just a moment..." in html and "challenges.cloudflare.com" in html:
            html = ""
    if html:
        og = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if og:
            title = clean_page_title(og.group(1))
        if not title:
            mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if mt:
                title = clean_page_title(mt.group(1))
        ep_match = re.search(r"\b(?:E|Episode)\s*0*(\d+)\b", title or "", re.I)
        if ep_match:
            episode = str(int(ep_match.group(1)))

    if not title and parts:
        # Common forms: /watch/<id>/<episode-slug> or /series/<id>/<show-slug>
        if parts[0] == "series" and len(parts) >= 3:
            title = slug_to_title(parts[-1])
        elif parts[0] != "watch":
            title = slug_to_title(parts[-1])

    # Strip trailing "Season N" / "Part N" / "Cour N" markers from whichever
    # title we ended up with — these confuse AniList's exact-match search.
    # The number we strip becomes the inferred season (overridable by -s).
    if title:
        cleaned, parsed_season = parse_season_from_title(title)
        if parsed_season is not None:
            title = cleaned
            season = str(parsed_season)

    media = MediaInfo(source_url=url, provider="crunchyroll", title=title, episode=episode, season=season)
    # Attach the Crunchyroll ID via attribute so downstream code can use it
    # without forcing a MediaInfo schema migration for every URL handler.
    if crunchyroll_id:
        setattr(media, "crunchyroll_id", crunchyroll_id)
    return media


def netflix_id_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    # /watch/<id>, /title/<id>
    path_match = re.search(r"/(?:watch|title)/(\d+)", parsed.path)
    if path_match:
        return path_match.group(1)
    # /browse?jbv=<id> (and the older /browse/genre/<id>?jbv=<id> form)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("jbv", "jbp", "jbvideoId", "movieid"):
        values = query.get(key) or []
        for value in values:
            if value.isdigit():
                return value
    return None


def external_ids_from_netflix_id(netflix_id: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Look up IMDb/TMDB/TVDB IDs and the English label for a Netflix work ID.

    Uses Wikidata property P1874 (Netflix work ID). Returns (title, imdb_id,
    tmdb_id, tvdb_id) with any field None when unknown."""
    query = """
    SELECT ?item ?itemLabel ?imdb ?tmdbTv ?tmdbMovie ?tvdb WHERE {
      ?item wdt:P1874 "%s".
      OPTIONAL { ?item wdt:P345 ?imdb. }
      OPTIONAL { ?item wdt:P4983 ?tmdbTv. }
      OPTIONAL { ?item wdt:P4947 ?tmdbMovie. }
      OPTIONAL { ?item wdt:P4835 ?tvdb. }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    LIMIT 1
    """ % netflix_id
    url = WIKIDATA_SPARQL_API + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    try:
        with _StatusLine(f"Looking up external IDs for Netflix {netflix_id}"):
            data = request_json(url, headers={"Accept": "application/sparql-results+json"})
    except CliError:
        return None, None, None, None
    bindings = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    if not bindings:
        return None, None, None, None
    first = bindings[0]

    def _str(field: str) -> str | None:
        value = first.get(field, {}).get("value")
        return value if isinstance(value, str) and value.strip() else None

    return _str("itemLabel"), _str("imdb"), _str("tmdbTv") or _str("tmdbMovie"), _str("tvdb")


def infer_from_netflix_url(url: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    netflix_id = netflix_id_from_url(url)
    is_watch_page = bool(parts) and parts[0] == "watch"

    # Always try to scrape a title. On title/browse pages this is the
    # canonical series title. On /watch/ pages it's usually the EPISODE
    # title (e.g. "Pilot") — useful only as a last-resort fallback when
    # Wikidata returns nothing for the Netflix ID.
    scraped_title: str | None = None
    html = request_text(url)
    if html:
        og = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.I,
        )
        if og:
            candidate = clean_page_title(og.group(1))
            if candidate and not _looks_like_generic_streaming_title(candidate):
                scraped_title = candidate
        if not scraped_title:
            mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if mt:
                candidate = clean_page_title(mt.group(1))
                if candidate and not _looks_like_generic_streaming_title(candidate):
                    scraped_title = candidate

    # Use the scraped title immediately for non-/watch/ pages — it's the
    # series title there. For /watch/ pages, keep it on the side and only
    # use it as a fallback if Wikidata returns nothing.
    media = MediaInfo(
        source_url=url, provider="netflix",
        title=None if is_watch_page else scraped_title,
        netflix_id=netflix_id,
    )

    # Bridge Netflix ID -> IMDb/TMDB/TVDB via Wikidata so downstream providers
    # (Wyzie) and the AniList bridge can take it from there.
    if netflix_id:
        nf_title, imdb_id, tmdb_id, tvdb_id = external_ids_from_netflix_id(netflix_id)
        media.title = media.title or nf_title
        media.imdb_id = media.imdb_id or imdb_id
        media.tmdb_id = media.tmdb_id or tmdb_id
        media.tvdb_id = media.tvdb_id or tvdb_id

    # Fallback: Wikidata had nothing for this Netflix ID and the URL was
    # a /watch/ page we skipped earlier. Use the (likely episode) title
    # as a search seed — TMDB enrichment downstream may still resolve it,
    # and at minimum the user sees what we got instead of "unknown".
    if not media.title and scraped_title:
        media.title = scraped_title

    return media


# Streaming hosts handled by the generic streaming inferrer. Maps host →
# (provider_label, list_of_path_keywords_that_mark_a_useful_slug).
STREAMING_URL_HOSTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "hulu.com": ("hulu", ("series", "movie", "movies")),
    "max.com": ("hbo", ("show", "shows", "movie", "movies")),
    "play.max.com": ("hbo", ("show", "shows", "movie", "movies")),
    "hbomax.com": ("hbo", ("show", "shows", "movie", "movies")),
    "disneyplus.com": ("disney", ("video", "movies", "series", "browse")),
    "tv.apple.com": ("apple", ("show", "movie")),
    "paramountplus.com": ("paramount", ("shows", "movies")),
    "peacocktv.com": ("peacock", ("watch", "stream-tv", "shows", "movies")),
    "primevideo.com": ("amazon", ("detail",)),
}

# Strings that show up as og:title on auth-walled pages and aren't the show
# title. Each is a substring match (case-insensitive).
_GENERIC_STREAMING_TITLE_PATTERNS = (
    "sign in", "log in", "stream tv", "watch ", "stream on ",
    "tv shows", "movies", "free trial", "subscribe",
)


def _looks_like_generic_streaming_title(title: str) -> bool:
    """True for og:title strings that are clearly marketing boilerplate
    rather than the actual show name (auth wall / homepage redirect)."""
    if not title:
        return True
    lower = title.lower().strip()
    if len(lower) < 2 or len(lower) > 200:
        return True
    for pat in _GENERIC_STREAMING_TITLE_PATTERNS:
        if pat in lower:
            return True
    return False


def _slug_from_streaming_path(parts: list[str], known_keywords: tuple[str, ...]) -> str | None:
    """Pull the most likely 'show slug' out of a streaming URL path. Looks
    for a path segment that follows one of the known keywords (e.g. after
    `/series/` for Hulu, `/show/` for Max). Strips trailing UUID-ish
    suffixes that some services append (`some-show-name-deadbeef12ab...`)."""
    if not parts:
        return None
    for i, segment in enumerate(parts):
        if segment.lower() in known_keywords and i + 1 < len(parts):
            slug = parts[i + 1]
            # Strip trailing hex/UUID-ish chunk after the last hyphen.
            tail = slug.rsplit("-", 1)
            if len(tail) == 2 and re.fullmatch(r"[a-f0-9]{8,}", tail[1], re.I):
                slug = tail[0]
            return slug or None
    return None


def infer_from_streaming_url(url: str, host: str) -> MediaInfo:
    """Generic handler for hulu / max / disneyplus / apple tv+ / paramount+ /
    peacock / prime video. Extracts a title from the URL slug, falls back to
    scraping `og:title` (most services expose it even when content is
    auth-walled). Returns a MediaInfo with provider set to the service tag
    so the downstream release-source preference picks the right releases.

    No IDs are returned directly — the TMDB enrichment hook in main() takes
    the title and resolves IMDb/TMDB IDs."""
    host_key = host.lower()
    if host_key.startswith("www."):
        host_key = host_key[4:]

    provider_label = "unknown"
    known_keywords: tuple[str, ...] = ()
    for known_host, (label, kws) in STREAMING_URL_HOSTS.items():
        if host_key == known_host or host_key.endswith("." + known_host):
            provider_label = label
            known_keywords = kws
            break

    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]

    # 1) Try the URL slug as a title hint.
    title: str | None = None
    slug = _slug_from_streaming_path(parts, known_keywords)
    if slug:
        title = slug_to_title(slug)

    # 2) Try scraping og:title / <title>. Falls back gracefully on 403 /
    # network error (request_text returns "").
    html = request_text(url)
    if html:
        og = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.I,
        )
        if og:
            scraped = clean_page_title(og.group(1))
            if scraped and not _looks_like_generic_streaming_title(scraped):
                # Prefer scraped title over slug — usually has correct casing
                # / spacing / punctuation.
                title = scraped
        if not title:
            mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if mt:
                scraped = clean_page_title(mt.group(1))
                if scraped and not _looks_like_generic_streaming_title(scraped):
                    title = scraped

    return MediaInfo(source_url=url, provider=provider_label, title=title)


def infer_media(url: str) -> MediaInfo:
    title_source = title_from_source_url(url)
    if title_source:
        return MediaInfo(source_url=url, provider="title", title=title_source)
    if "..." in url:
        raise CliError(
            "That URL still contains '...'. Paste the full episode or series URL, "
            "or use --title/--anilist with a real URL."
        )
    host = urllib.parse.urlparse(url).netloc.lower()
    if "crunchyroll.com" in host:
        return infer_from_crunchyroll_url(url)
    if "netflix.com" in host:
        return infer_from_netflix_url(url)
    # Generic streaming-service handler covers hulu/max/disney+/apple/
    # paramount+/peacock/prime video. Falls through to the catalog
    # branch below for non-streaming hosts.
    host_stripped = host[4:] if host.startswith("www.") else host
    if any(host_stripped == h or host_stripped.endswith("." + h)
           for h in STREAMING_URL_HOSTS):
        return infer_from_streaming_url(url, host)
    if "anilist.co" in host:
        return infer_from_anilist_url(url)
    catalog_provider = provider_from_host(host)
    if catalog_provider in {"imdb", "tmdb", "letterboxd", "rottentomatoes", "myanimelist", "thetvdb", "trakt"}:
        return infer_from_catalog_url(url, catalog_provider)
    return MediaInfo(source_url=url, provider=host or "unknown", title=None)


def search_anilist(title: str, limit: int = 8) -> list[AniListCandidate]:
    if not title or title.lower() in {"...", "Unknown", "unknown"}:
        raise CliError("Could not infer a real title. Re-run with --title or --anilist.")
    query = """
    query ($title: String, $perPage: Int) {
      Page(page: 1, perPage: $perPage) {
        media(search: $title, type: ANIME) {
        id
        title { romaji english native }
          seasonYear
          episodes
          format
        }
      }
    }
    """
    data = request_json(
        ANILIST_API,
        data={"query": query, "variables": {"title": title, "perPage": limit}},
    )
    raw = data.get("data", {}).get("Page", {}).get("media", []) if isinstance(data, dict) else []
    candidates = []
    for item in raw:
        title_data = item.get("title") or {}
        candidates.append(
            AniListCandidate(
                id=int(item["id"]),
                romaji=title_data.get("romaji"),
                english=title_data.get("english"),
                native=title_data.get("native"),
                season_year=item.get("seasonYear"),
                episodes=item.get("episodes"),
                format=item.get("format"),
            )
        )
    return candidates


def fetch_anilist_info(anilist_id: int) -> AniListInfo:
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji english native }
        synonyms
        episodes
        format
      }
    }
    """
    data = request_json(ANILIST_API, data={"query": query, "variables": {"id": anilist_id}})
    media = data.get("data", {}).get("Media") if isinstance(data, dict) else None
    if not media:
        raise CliError(
            f"AniList has no entry for ID {anilist_id}. Double-check the ID at "
            f"https://anilist.co/anime/{anilist_id}/."
        )
    title_data = media.get("title") or {}
    title = title_data.get("romaji") or title_data.get("english") or title_data.get("native")
    aliases = unique_titles([
        title_data.get("romaji"),
        title_data.get("english"),
        title_data.get("native"),
        *(media.get("synonyms") or []),
    ])
    episodes = media.get("episodes")
    return AniListInfo(
        id=int(media["id"]),
        title=title,
        episodes=int(episodes) if episodes else None,
        title_aliases=[alias for alias in aliases if _norm_title_key(alias) != _norm_title_key(title or "")],
        format=media.get("format"),
    )


def _anilist_title_fallbacks(title: str) -> list[str]:
    """Generate progressively-shorter prefixes of a title to try when AniList
    returns no matches for the full string.

    Slug-derived titles like 'Frieren Beyond Journeys End' often lose
    punctuation (the real title is 'Frieren: Beyond Journey's End'). The
    first one or two words usually identify the show on their own. Public
    for testing."""
    words = title.split()
    fallbacks: list[str] = []
    # 2-word, then 1-word prefix. Don't bother with 3+ words: if the full
    # title didn't match, those probably won't either.
    for cutoff in (2, 1):
        if cutoff < len(words):
            shorter = " ".join(words[:cutoff])
            if shorter and shorter != title and shorter not in fallbacks:
                fallbacks.append(shorter)
    return fallbacks


def resolve_anilist_id(title: str) -> int:
    try:
        candidates = search_anilist(title, limit=1)
    except CliError as e:
        raise CliError(
            f"AniList could not resolve title: {title!r}. "
            "Crunchyroll may be blocking metadata access. Pass --title \"Show Name\" or --anilist ID."
        ) from e

    if not candidates:
        # Retry with shortened prefixes — handles slug titles where
        # punctuation/subtitles were lost (e.g. "Frieren Beyond Journeys End"
        # -> "Frieren" succeeds).
        for fallback in _anilist_title_fallbacks(title):
            try:
                candidates = search_anilist(fallback, limit=1)
            except CliError:
                break
            if candidates:
                break

    if not candidates:
        raise CliError(
            f"AniList could not resolve title: {title!r}. "
            "Pass --title \"Show Name\" or --anilist ID."
        )
    return candidates[0].id


ANILIST_INPUT_PROMPT = (
    "Show title, AniList ID, or AniList URL "
    "(e.g. 'MF Ghost', '143327', 'https://anilist.co/anime/143327/'): "
)


def parse_anilist_input(raw: str) -> tuple[int | None, str | None]:
    """Classify free-form user input as either an AniList ID or a search title.

    Returns (anilist_id, title). Exactly one is non-None when input is
    recognised; both are None when input is blank."""
    text = (raw or "").strip()
    if not text:
        return None, None
    if text.isdigit():
        return int(text), None
    if "anilist.co" in text.lower():
        media = infer_from_anilist_url(text)
        if media.anilist_id:
            return media.anilist_id, None
    # Treat anything else as a free-text title to search.
    return None, text


def prompt_for_anilist_id(initial_title: str | None = None) -> tuple[int, str | None]:
    title = initial_title
    direct_id: int | None = None

    while title is None and direct_id is None:
        if not sys.stdin.isatty():
            raise CliError(
                "Could not infer the show title from this URL. "
                "Re-run with --title \"Show Name\" or --anilist <id>. "
                "See: getsubtitle --help fetch"
            )
        raw = input(ANILIST_INPUT_PROMPT).strip()
        direct_id, parsed_title = parse_anilist_input(raw)
        title = parsed_title

    if direct_id is not None:
        info = fetch_anilist_info(direct_id)
        return direct_id, info.title

    assert title is not None
    candidates = search_anilist(title)
    if not candidates:
        raise CliError(f"AniList returned no matches for {title!r}. Try --title with another title or use --anilist.")

    if len(candidates) == 1 or not sys.stdin.isatty():
        candidate = candidates[0]
        return candidate.id, candidate.romaji or candidate.english or candidate.native

    print("\nAniList matches:")
    for idx, candidate in enumerate(candidates, start=1):
        print(f"  {idx}. {candidate.label()}")
    while True:
        choice = input("Choose AniList match [1]: ").strip() or "1"
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            candidate = candidates[int(choice) - 1]
            return candidate.id, candidate.romaji or candidate.english or candidate.native
        print("Enter a number from the list.")


class JimakuProvider:
    language = "ja"
    name = "jimaku"

    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self._entry_id_by_key: dict[str, int] = {}

    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CliError(
                "Jimaku needs an API key for Japanese anime subtitles.\n"
                "  Quick setup: getsubtitle --set-key jimaku  (macOS Keychain or env var)\n"
                "  See: getsubtitle --help keys"
            )
        return {"Authorization": self.api_key}

    def _search_entries(self, params: dict[str, object]) -> list[dict]:
        q = urllib.parse.urlencode(params)
        entries = request_json(f"{JIMAKU_API}/entries/search?{q}", headers=self._headers())
        if not isinstance(entries, list):
            raise CliError("Unexpected Jimaku response.")
        return [entry for entry in entries if isinstance(entry, dict)]

    def _cached_entry_lookup(self, cache_key: str, params: dict[str, object]) -> int | None:
        if cache_key in self._entry_id_by_key:
            return self._entry_id_by_key[cache_key]
        entries = self._search_entries(params)
        if not isinstance(entries, list) or not entries:
            return None
        entry_id = int(entries[0]["id"])
        self._entry_id_by_key[cache_key] = entry_id
        return entry_id

    @staticmethod
    def _tmdb_entry_param(media: MediaInfo) -> str | None:
        if not media.tmdb_id:
            return None
        media_type = "movie" if media.is_movie else "tv"
        if media.source_url:
            path = urllib.parse.urlparse(media.source_url).path.lower()
            if "/movie/" in path:
                media_type = "movie"
            elif "/tv/" in path:
                media_type = "tv"
        return f"{media_type}:{media.tmdb_id}"

    @staticmethod
    def _entry_titles(entry: dict) -> list[str]:
        return unique_titles([
            str(entry.get("name") or ""),
            str(entry.get("english_name") or ""),
            str(entry.get("japanese_name") or ""),
        ])

    @staticmethod
    def _query_entry_score(query: str, entry: dict) -> int:
        query_key = _norm_title_key(query)
        if not query_key:
            return 0
        best = 0
        for title in JimakuProvider._entry_titles(entry):
            title_key = _norm_title_key(title)
            if not title_key:
                continue
            if title_key == query_key:
                best = max(best, 100)
            elif len(query_key) >= 6 and query_key in title_key:
                best = max(best, 85)
            elif len(title_key) >= 6 and title_key in query_key:
                best = max(best, 80)
        return best

    def _query_entry_id(self, media: MediaInfo) -> int | None:
        for query in media_title_queries(media):
            cache_key = f"query:{_norm_title_key(query)}"
            if cache_key in self._entry_id_by_key:
                return self._entry_id_by_key[cache_key]
            try:
                entries = self._search_entries({"query": query, "anime": "true"})
            except CliError:
                continue
            scored = [
                (self._query_entry_score(query, entry), entry)
                for entry in entries
            ]
            scored = [(score, entry) for score, entry in scored if score > 0]
            if not scored:
                continue
            scored.sort(key=lambda item: item[0], reverse=True)
            entry_id = int(scored[0][1]["id"])
            self._entry_id_by_key[cache_key] = entry_id
            return entry_id
        return None

    def search_entry_id(self, media: MediaInfo) -> int:
        tried: list[str] = []
        if media.anilist_id:
            tried.append(f"AniList ID {media.anilist_id}")
            entry_id = self._cached_entry_lookup(
                f"anilist:{media.anilist_id}",
                {"anilist_id": media.anilist_id},
            )
            if entry_id is not None:
                return entry_id

        tmdb_param = self._tmdb_entry_param(media)
        if tmdb_param:
            tried.append(f"TMDB {tmdb_param}")
            entry_id = self._cached_entry_lookup(
                f"tmdb:{tmdb_param}",
                {"tmdb_id": tmdb_param},
            )
            if entry_id is not None:
                return entry_id

        if media_title_queries(media):
            tried.append("title aliases")
            entry_id = self._query_entry_id(media)
            if entry_id is not None:
                return entry_id

        where = ", ".join(tried) if tried else "no usable ID/title"
        raise CliError(
            f"Jimaku has no matching entry via {where}. "
            "Jimaku works best with AniList/TMDB IDs; alternate title search is "
            "best-effort. Try --anilist, a TMDB URL, or check jimaku.cc directly."
        )

    def files(self, media: MediaInfo, episode: str) -> list[SubtitleFile]:
        entry_id = self.search_entry_id(media)
        url = f"{JIMAKU_API}/entries/{entry_id}/files"
        if episode not in {"all", "auto"}:
            url += "?" + urllib.parse.urlencode({"episode": episode})
        files = request_json(url, headers=self._headers())
        if not isinstance(files, list):
            raise CliError("Unexpected Jimaku response.")
        subs = []
        for f in files:
            name = str(f.get("name", "subtitle"))
            if Path(name).suffix.lower() in SUB_EXTENSIONS | ARCHIVE_EXTENSIONS:
                subs.append(
                    SubtitleFile(
                        provider=self.name,
                        language=self.language,
                        name=name,
                        url=str(f["url"]),
                        size=f.get("size"),
                    )
                )
        return subs


class WyzieProvider:
    name = "wyzie"

    def __init__(self, api_key: str | None):
        self.api_key = api_key
        # Cache: (media_id, season, episode) -> raw items list.
        # Lets us call Wyzie once per episode and split results across the
        # requested languages locally, instead of once per (lang, episode).
        self._all_lang_cache: dict[tuple[str, str, str], list[dict]] = {}
        # Episodes where the no-language call returned 0 items (likely the API
        # requires a language filter). We avoid retrying that path.
        self._all_lang_unsupported: set[tuple[str, str, str]] = set()

    def configured(self) -> bool:
        return bool(self.api_key)

    def _candidate_ids(self, media: MediaInfo) -> list[str]:
        """Return the IDs to query Wyzie with, in order of preference. IMDb is
        tried first; TMDB is a secondary because some titles index differently
        between the two databases inside Wyzie's backend."""
        ids: list[str] = []
        if media.imdb_id and media.imdb_id not in ids:
            ids.append(media.imdb_id)
        if media.tmdb_id and media.tmdb_id not in ids:
            ids.append(media.tmdb_id)
        return ids

    def _build_params_for_id(self, media_id: str, media: MediaInfo, episode: str, language: str | None) -> dict[str, str]:
        params: dict[str, str] = {
            "id": media_id,
            "format": "srt,ass,vtt",
            "source": "all",
            "key": self.api_key or "",
        }
        if language:
            params["language"] = language
        if media.season not in {"auto", "all"} and episode not in {"auto", "all"}:
            params["season"] = media.season
            params["episode"] = episode
        return params

    def _fetch(self, params: dict[str, str]) -> list[dict]:
        url = WYZIE_API + "?" + urllib.parse.urlencode(params)
        try:
            data = request_json(url)
        except CliError as e:
            if "No subtitles found" in str(e):
                return []
            raise
        if isinstance(data, dict):
            items = data.get("subtitles") or data.get("results") or data.get("data") or []
        else:
            items = data
        if not isinstance(items, list):
            raise CliError("Unexpected Wyzie response.")
        return [item for item in items if isinstance(item, dict)]

    def _make_subtitle(self, item: dict, media: MediaInfo, media_id: str, language: str) -> SubtitleFile | None:
        sub_url = item.get("url")
        if not isinstance(sub_url, str) or not sub_url:
            return None
        fmt = str(item.get("format") or Path(str(item.get("fileName") or "")).suffix.lstrip(".") or "srt").lower()
        ext = "." + fmt.lstrip(".")
        if ext not in SUB_EXTENSIONS:
            return None
        name = str(item.get("fileName") or item.get("release") or f"{media.title or media_id}.{language}{ext}")
        if not Path(name).suffix:
            name += ext
        return SubtitleFile(
            provider=self.name,
            language=language,
            name=name,
            url=sub_url,
            release_source=normalized_release_source(
                " ".join(str(v) for v in [item.get("origin"), item.get("release"), item.get("fileName"), item.get("source")] if v)
            ),
            release=str(item.get("release") or item.get("matchedRelease") or ""),
            origin=str(item.get("origin") or ""),
            source_provider=str(item.get("source") or ""),
            media_title=str(item.get("media") or "") or None,
            ai=bool(item.get("ai")),
            provider_language=(str(item.get("language")) if item.get("language") else None),
        )

    def files(self, media: MediaInfo, episode: str, language: str) -> list[SubtitleFile]:
        ids = self._candidate_ids(media)
        if not ids:
            raise CliError(
                "Wyzie needs an IMDb or TMDB ID. Try an imdb.com/title/tt... or "
                "themoviedb.org/movie/... URL, or pass --anilist <id> for anime "
                "(the CLI bridges that to IMDb/TMDB automatically)."
            )

        # Strategy 1 (cheap, preferred): broad call (no language filter) per
        # candidate ID. First ID that returns items wins; results are cached
        # per (id, season, episode) so subsequent language requests reuse them.
        items_for_filter: list[dict] | None = None
        used_id: str | None = None
        for media_id in ids:
            cache_key = (media_id, str(media.season), str(episode))
            if cache_key in self._all_lang_unsupported:
                continue
            if cache_key in self._all_lang_cache:
                items_for_filter = self._all_lang_cache[cache_key]
                used_id = media_id
                break
            fetched = self._fetch(self._build_params_for_id(media_id, media, episode, None))
            if fetched:
                self._all_lang_cache[cache_key] = fetched
                items_for_filter = fetched
                used_id = media_id
                break
            # 0 items from the broad call: mark this ID's broad-mode unsupported
            # and continue to the next ID (or to the per-language fallback).
            self._all_lang_unsupported.add(cache_key)

        if items_for_filter is not None and used_id is not None:
            matches: list[SubtitleFile] = []
            for item in items_for_filter:
                provider_lang = item.get("language")
                file_name = item.get("fileName") or item.get("release")
                if not lang_matches(language, provider_lang, file_name, item.get("origin")):
                    continue
                sub = self._make_subtitle(item, media, used_id, language)
                if sub is not None:
                    matches.append(sub)
            return matches

        # Strategy 2 (fallback): broad call returned 0 for every candidate ID,
        # so try the original per-language call across the same candidate set.
        for media_id in ids:
            items = self._fetch(self._build_params_for_id(media_id, media, episode, language))
            if not items:
                continue
            subs: list[SubtitleFile] = []
            for item in items:
                sub = self._make_subtitle(item, media, media_id, language)
                if sub is not None:
                    subs.append(sub)
            if subs:
                return subs
        return []


class SubDLProvider:
    """Direct SubDL API provider.

    Wyzie can proxy SubDL for some keys, but free/source access varies. This
    direct provider is used only when a SubDL key is configured and fills gaps
    after the normal Wyzie/Jimaku pass.
    """

    name = "subdl"

    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self._cache: dict[tuple[str, str, str, str], list[dict]] = {}

    def configured(self) -> bool:
        return bool(self.api_key)

    def _candidate_ids(self, media: MediaInfo) -> list[tuple[str, str]]:
        ids: list[tuple[str, str]] = []
        if media.imdb_id:
            ids.append(("imdb_id", media.imdb_id))
        if media.tmdb_id:
            ids.append(("tmdb_id", media.tmdb_id))
        return ids

    def _language_param(self, language: str) -> str:
        # SubDL's docs show upper-case ISO-ish tags (EN, FR). Keep the user's
        # canonical code but uppercase it; provider_language is still recorded
        # from the response for diagnostics.
        return LANGUAGE_ALIASES.get(language.lower(), language.lower()).upper()

    def _build_params_for_id(self, id_name: str, media_id: str, media: MediaInfo, episode: str, language: str) -> dict[str, str]:
        params: dict[str, str] = {
            "api_key": self.api_key or "",
            id_name: media_id,
            "languages": self._language_param(language),
            "subs_per_page": "30",
            "releases": "1",
            "hi": "1",
            "unpack": "1",
        }
        if media.season not in {"auto", "all"} and episode not in {"auto", "all"}:
            params["type"] = "tv"
            params["season_number"] = media.season
            params["episode_number"] = episode
        else:
            params["type"] = "movie"
        return params

    def _fetch(self, params: dict[str, str]) -> list[dict]:
        cache_key = (
            params.get("imdb_id") or params.get("tmdb_id") or "",
            params.get("season_number") or "",
            params.get("episode_number") or "",
            params.get("languages") or "",
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        url = SUBDL_API + "?" + urllib.parse.urlencode(params)
        data = request_json(url)
        if not isinstance(data, dict):
            raise CliError("Unexpected SubDL response.")
        if data.get("status") is False:
            error = data.get("error") or data.get("message") or "unknown error"
            raise CliError(f"SubDL: {error}")
        items = data.get("subtitles") or data.get("results") or []
        if not isinstance(items, list):
            raise CliError("Unexpected SubDL subtitles response.")
        out = [item for item in items if isinstance(item, dict)]
        self._cache[cache_key] = out
        return out

    def _download_url(self, raw_url: object) -> str | None:
        if not isinstance(raw_url, str) or not raw_url:
            return None
        if raw_url.startswith("http://") or raw_url.startswith("https://"):
            return raw_url
        if raw_url.startswith("/"):
            return SUBDL_DOWNLOAD_BASE + raw_url
        return SUBDL_DOWNLOAD_BASE + "/" + raw_url.lstrip("/")

    def _make_subtitle(self, item: dict, media: MediaInfo, episode: str, language: str) -> SubtitleFile | None:
        sub_url = self._download_url(item.get("url"))
        if not sub_url:
            return None
        fmt = str(item.get("format") or Path(str(item.get("name") or "")).suffix.lstrip(".") or "srt").lower()
        ext = "." + fmt.lstrip(".")
        if ext not in SUB_EXTENSIONS and ext not in ARCHIVE_EXTENSIONS:
            return None
        name = str(item.get("name") or item.get("release_name") or f"{media.title or 'subdl'}.S{media.season}E{episode}.{language}{ext}")
        if not Path(name).suffix:
            name += ext
        return SubtitleFile(
            provider=self.name,
            language=language,
            name=name,
            url=sub_url,
            size=int(item["size"]) if str(item.get("size") or "").isdigit() else None,
            release_source=normalized_release_source(" ".join(str(v) for v in [item.get("release_name"), item.get("name")] if v)),
            release=str(item.get("release_name") or ""),
            origin="subdl",
            source_provider="subdl",
            media_title=media.title,
            provider_language=(str(item.get("language")) if item.get("language") else None),
        )

    def _flatten_unpacked(self, items: list[dict], media: MediaInfo, episode: str, language: str) -> list[dict]:
        flattened: list[dict] = []
        for item in items:
            unpack_files = item.get("unpack_files")
            if not isinstance(unpack_files, list):
                flattened.append(item)
                continue
            for unpacked in unpack_files:
                if not isinstance(unpacked, dict):
                    continue
                item_ep = str(unpacked.get("episode") or item.get("episode") or "")
                if episode not in {"auto", "all"} and item_ep and item_ep != str(episode):
                    continue
                item_season = str(unpacked.get("season") or item.get("season") or "")
                if media.season not in {"auto", "all"} and item_season and item_season != str(media.season):
                    continue
                merged = dict(item)
                merged.update(unpacked)
                flattened.append(merged)
        return flattened

    def files(self, media: MediaInfo, episode: str, language: str) -> list[SubtitleFile]:
        ids = self._candidate_ids(media)
        if not ids:
            raise CliError("SubDL needs an IMDb or TMDB ID.")
        for id_name, media_id in ids:
            items = self._fetch(self._build_params_for_id(id_name, media_id, media, episode, language))
            if not items:
                continue
            subs: list[SubtitleFile] = []
            for item in self._flatten_unpacked(items, media, episode, language):
                if not lang_matches(language, item.get("language"), item.get("name"), item.get("release_name")):
                    continue
                sub = self._make_subtitle(item, media, episode, language)
                if sub is not None:
                    subs.append(sub)
            if subs:
                return subs
        return []


class SubdivxProvider:
    """EXPERIMENTAL: Spanish subtitle scraper for subdivx.com.

    Subdivx publishes no API, so this uses an AJAX endpoint shape that other
    open-source subtitle tools (e.g. Bazarr, Subliminal-derivatives) have used
    historically. The site re-skins occasionally — if matches stop appearing,
    inspect a real response with --debug-providers and update the parser.

    Returns .zip URLs; the existing zip-extraction path in save_subtitle()
    handles unpacking the .srt/.ass files inside.
    """

    name = "subdivx"
    language = "es"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def configured(self) -> bool:
        return self.enabled

    def files(self, media: MediaInfo, episode: str) -> list[SubtitleFile]:
        titles = media_title_queries(media)
        if not titles:
            return []

        all_subs: list[SubtitleFile] = []
        seen_urls: set[str] = set()
        for title in titles:
            query = title
            if media.season not in {"auto", "all"} and episode not in {"auto", "all"}:
                try:
                    query = f"{title} S{int(media.season):02d}E{int(episode):02d}"
                except (TypeError, ValueError):
                    pass
            try:
                data = self._search(query)
            except CliError:
                continue
            for sub in parse_subdivx_response(data, media, episode):
                if sub.url in seen_urls:
                    continue
                seen_urls.add(sub.url)
                all_subs.append(sub)
            if all_subs:
                break
        return all_subs

    def _search(self, query: str):
        post_body = urllib.parse.urlencode({"tabla": "resultados", "buscar2": query}).encode("utf-8")
        req = urllib.request.Request(
            SUBDIVX_SEARCH_URL,
            data=post_body,
            headers={
                "User-Agent": "Mozilla/5.0 getsubtitle/0.1",
                "Accept": "application/json, text/html",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": SUBDIVX_BASE + "/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                body = res.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise CliError(f"Subdivx HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise CliError(f"Subdivx network error: {e.reason}") from e
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body  # HTML response — let the parser pull what it can.


def parse_subdivx_response(data, media: MediaInfo, episode: str) -> list[SubtitleFile]:
    """Best-effort extraction of subtitle entries from a Subdivx response.

    Defensive against multiple known shapes:
      - JSON {"aaData": [...]} (DataTables-style)
      - JSON {"results": [...]} / {"subtitles": [...]}
      - JSON [...]
      - HTML page with <a class="titulo_menu_izq" href="descargar.php?id=N">

    Public for unit testing without network."""
    items: list[dict] = []
    if isinstance(data, dict):
        raw = data.get("aaData") or data.get("results") or data.get("subtitles") or []
        if isinstance(raw, list):
            items = [item for item in raw if isinstance(item, dict)]
    elif isinstance(data, list):
        items = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, str):
        items = _subdivx_items_from_html(data)

    subs: list[SubtitleFile] = []
    for item in items:
        # Try several common field names; Subdivx has used Spanish, English,
        # and short keys at different times.
        sub_id = item.get("id") or item.get("Id") or item.get("id_subtitulo")
        explicit_url = item.get("download_url") or item.get("url") or item.get("link")
        if explicit_url:
            sub_url = str(explicit_url)
        elif sub_id is not None:
            sub_url = f"{SUBDIVX_BASE}/descargar.php?id={sub_id}"
        else:
            continue

        title_text = (
            item.get("titulo")
            or item.get("title")
            or item.get("name")
            or item.get("Titulo")
            or f"subdivx-{sub_id or 'unknown'}"
        )
        description = (
            item.get("descripcion")
            or item.get("description")
            or item.get("Descripcion")
            or ""
        )

        name = str(title_text)
        if not Path(name).suffix:
            name += ".zip"
        subs.append(
            SubtitleFile(
                provider="subdivx",
                language="es",
                name=safe_filename(name),
                url=sub_url,
                release=str(description),
                source_provider="subdivx",
                provider_language="es",
                release_source=normalized_release_source(f"{title_text} {description}"),
            )
        )
    return subs


class Addic7edProvider:
    """EXPERIMENTAL: Korean subtitle scraper for addic7ed.com.

    Addic7ed publishes no API; this scrapes their public pages. The site is
    aggressively anti-bot — it can rate-limit, captcha-gate, or briefly ban an
    IP. Use sparingly and stop hammering it if it returns 503/403.

    Flow:
      1. /srch.php?search=<title>  -> parse search-results HTML for show_id
      2. /serie/<show_id>/<season>/<episode>/22  -> page lists Korean subs
      3. Each download link is /original/<file_id>/<seq>; downloads REQUIRE a
         browser User-Agent and a Referer header set to the episode page URL.
    """

    name = "addic7ed"
    language = "ko"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._show_id_cache: dict[str, int | None] = {}

    def configured(self) -> bool:
        return self.enabled

    def files(self, media: MediaInfo, episode: str) -> tuple[list[SubtitleFile], str | None]:
        """Return (subtitles, diagnostic). `diagnostic` is a short human-readable
        reason when no subtitles were returned, or None on success. Surfacing
        this lets --debug-providers tell apart 'no match' from 'HTTP 403'."""
        titles = media_title_queries(media)
        if not titles or not episode.isdigit() or not str(media.season).isdigit():
            return [], "title or season/episode not numeric"
        diagnostics: list[str] = []
        show_id = None
        try:
            for title in titles:
                show_id, show_diag = self._find_show_id(title)
                if show_id:
                    break
                if show_diag:
                    diagnostics.append(f"{title}: {show_diag}")
        except CliError as e:
            return [], str(e)
        if not show_id:
            return [], "; ".join(diagnostics[:3]) or "no matching show on Addic7ed"
        episode_url = (
            f"{ADDIC7ED_BASE}/serie/{show_id}/{int(media.season)}/{int(episode)}/{ADDIC7ED_KOREAN_LANG_ID}"
        )
        try:
            html = self._fetch(episode_url)
        except CliError as e:
            return [], str(e)
        subs = parse_addic7ed_episode_page(html, media, episode_url)
        if not subs:
            return [], "episode page returned no Korean download links"
        return subs, None

    def _find_show_id(self, title: str) -> tuple[int | None, str | None]:
        key = title.lower().strip()
        if key in self._show_id_cache:
            cached = self._show_id_cache[key]
            return cached, None if cached else "no matching show (cached)"
        url = ADDIC7ED_BASE + "/srch.php?search=" + urllib.parse.quote(title)
        try:
            html = self._fetch(url)
        except CliError as e:
            self._show_id_cache[key] = None
            return None, str(e)
        show_id = extract_addic7ed_show_id(html, title)
        self._show_id_cache[key] = show_id
        return show_id, None if show_id else "search results matched no show row"

    def _fetch(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ADDIC7ED_BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Referer": ADDIC7ED_BASE + "/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                return res.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise CliError(f"Addic7ed HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise CliError(f"Addic7ed network error: {e.reason}") from e


def extract_addic7ed_show_id(html: str, target_title: str) -> int | None:
    """Find a show ID in an Addic7ed search-results page.

    Public for testing. Returns the closest title match, falling back to the
    first result if no clear winner exists, or None if no plausible match."""
    pattern = re.compile(r'<a\s+href=["\']show/(\d+)["\'][^>]*>([^<]+)</a>', re.I)
    matches: list[tuple[int, str]] = []
    for m in pattern.finditer(html):
        show_id = int(m.group(1))
        name = unescape(m.group(2)).strip()
        matches.append((show_id, name))
    if not matches:
        return None
    target = target_title.lower().strip()
    for show_id, name in matches:
        if name.lower() == target:
            return show_id
    for show_id, name in matches:
        if target in name.lower() or name.lower() in target:
            return show_id
    return matches[0][0]


def parse_addic7ed_episode_page(html: str, media: MediaInfo, episode_url: str) -> list[SubtitleFile]:
    """Extract Korean subtitle download links from an Addic7ed episode page.

    Public for testing. We requested lang_id=22, so every download link on
    this page should be Korean."""
    if not html:
        return []
    subs: list[SubtitleFile] = []
    # Addic7ed download buttons: <a class="buttonDownload" href="/original/<id>/<seq>">Download</a>
    # We accept either "buttonDownload" or the older "download" class for robustness.
    pattern = re.compile(
        r'<a[^>]+class=["\'][^"\']*(?:buttonDownload|download)[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
        re.I,
    )
    seen: set[str] = set()
    for m in pattern.finditer(html):
        href = m.group(1)
        if "/original/" not in href and "/updated/" not in href:
            # Skip "more info" / unrelated links that share the class.
            continue
        download_url = urllib.parse.urljoin(ADDIC7ED_BASE + "/", href)
        if download_url in seen:
            continue
        seen.add(download_url)
        name = f"{(media.title or 'addic7ed').strip()}.ko.srt"
        subs.append(
            SubtitleFile(
                provider="addic7ed",
                language="ko",
                name=safe_filename(name),
                url=download_url,
                source_provider="addic7ed",
                provider_language="ko",
                download_headers={
                    "User-Agent": ADDIC7ED_BROWSER_UA,
                    "Referer": episode_url,
                },
            )
        )
    return subs


def _subdivx_items_from_html(html: str) -> list[dict]:
    items: list[dict] = []
    pattern = re.compile(
        r'<a[^>]+class=["\']titulo_menu_izq["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        href = match.group(1)
        title = unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        id_match = re.search(r"id=(\d+)", href)
        sub_id = id_match.group(1) if id_match else None
        items.append(
            {
                "id": sub_id,
                "title": title,
                "url": urllib.parse.urljoin(SUBDIVX_BASE + "/", href),
            }
        )
    return items


# ---------------------------------------------------------------------------
# Machine translation backends
# ---------------------------------------------------------------------------
# Each translator implements: name (class attr), is_available(), and
# translate_batch(texts, source, target) -> list[str]. translate() is a
# convenience wrapper. Translators must never raise on partial failure;
# return the original text for cues they can't translate.

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEEPL_FREE_API_BASE = "https://api-free.deepl.com"
DEEPL_PRO_API_BASE = "https://api.deepl.com"


class TranslatorError(CliError):
    pass


class _BaseTranslator:
    name: str = "base"

    def is_available(self) -> bool:
        raise NotImplementedError

    def setup_help(self, source_lang: str | None = None, target_lang: str | None = None) -> str:
        """One-line instruction for getting this engine ready. Subclasses
        override; the base impl is a generic fallback."""
        return f"{self.name}: not ready. See `getsubtitle --help translate` for engine setup."

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        result = self.translate_batch([text], source_lang, target_lang)
        return result[0] if result else text

    def translate_batch(self, texts: list[str], source_lang: str, target_lang: str, on_progress=None) -> list[str]:
        """Translate a list of strings. If `on_progress` is provided it is
        called as `on_progress(done, total)` after each item or chunk so
        callers can render a cue-level progress bar."""
        raise NotImplementedError

    def release_resources(self) -> bool:
        """Release any heavy resources held by this translator (loaded
        models, GPU memory, etc.). Default is a no-op — Argos and DeepL
        have nothing to release. Subclasses override when they do.
        Returns True if anything was released."""
        return False


@dataclass
class DeepLUsage:
    character_count: int
    character_limit: int | None = None
    api_key_character_count: int | None = None
    api_key_character_limit: int | None = None


def _deepl_api_base(api_key: str | None) -> str:
    """DeepL Free keys conventionally end with ':fx'; Pro keys use api.deepl.com."""
    key = (api_key or "").strip()
    return DEEPL_FREE_API_BASE if key.endswith(":fx") else DEEPL_PRO_API_BASE


def _deepl_int(data: dict, key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def format_deepl_usage(usage: DeepLUsage) -> list[str]:
    """Human-readable DeepL usage lines."""
    lines: list[str] = []
    if usage.character_limit and usage.character_limit > 0:
        remaining = max(usage.character_limit - usage.character_count, 0)
        pct = (usage.character_count / usage.character_limit) * 100
        lines.append(
            "Account characters this period: "
            f"{usage.character_count:,} / {usage.character_limit:,} "
            f"({remaining:,} remaining, {pct:.1f}% used)"
        )
    else:
        lines.append(f"Account characters this period: {usage.character_count:,} used")
    if usage.api_key_character_count is not None:
        key_limit = usage.api_key_character_limit
        # DeepL returns a very large sentinel when no key-level limit is set.
        if key_limit and 0 < key_limit < 1_000_000_000_000:
            remaining = max(key_limit - usage.api_key_character_count, 0)
            pct = (usage.api_key_character_count / key_limit) * 100
            lines.append(
                "API key characters this period: "
                f"{usage.api_key_character_count:,} / {key_limit:,} "
                f"({remaining:,} remaining, {pct:.1f}% used)"
            )
        else:
            lines.append(
                "API key characters this period: "
                f"{usage.api_key_character_count:,} used (no key-level limit)"
            )
    return lines


def print_deepl_usage_summary(translators: Iterable[_BaseTranslator]) -> None:
    deepl_translators = [
        tr for tr in translators
        if isinstance(tr, DeepLTranslator)
    ]
    if not deepl_translators:
        return
    translator = deepl_translators[0]
    print("\nDeepL usage:")
    try:
        usage = translator.usage()
    except TranslatorError as e:
        print(f"  unavailable: {e}")
        return
    for line in format_deepl_usage(usage):
        print(f"  {line}")


class ArgosTranslator(_BaseTranslator):
    """Offline translator using argostranslate. Per-pair models must be
    installed separately. Many Argos pairs route through English, e.g.
    Japanese -> Korean needs translate-ja_en and translate-en_ko."""

    name = "argos"

    def is_available(self) -> bool:
        try:
            import argostranslate.translate  # noqa: F401
            return True
        except Exception:
            return False

    def setup_help(self, source_lang: str | None = None, target_lang: str | None = None) -> str:
        pair = ""
        if source_lang and target_lang:
            if source_lang != "en" and target_lang != "en":
                pair = (
                    f"\n  argospm install translate-{source_lang}_en"
                    f"\n  argospm install translate-en_{target_lang}"
                    "\n\nIf a direct package exists, this may also work:"
                    f"\n  argospm install translate-{source_lang}_{target_lang}"
                )
            else:
                pair = f"\n  argospm install translate-{source_lang}_{target_lang}"
        return (
            "Install Argos Translate (offline):\n"
            "  python -m pip install argostranslate"
            f"{pair}"
            "\n(See https://www.argosopentech.com for the language-pair list.)"
        )

    def translate_batch(self, texts: list[str], source_lang: str, target_lang: str, on_progress=None) -> list[str]:
        try:
            import argostranslate.translate as at
        except Exception as e:
            raise TranslatorError(
                "Argos Translate is not installed. Run: "
                "pip install argostranslate, then "
                f"`argospm install translate-{source_lang}_{target_lang}`."
            ) from e

        # Discover whether a direct or English-pivot path exists.
        installed = at.get_installed_languages()
        src = next((lng for lng in installed if lng.code == source_lang), None)
        tgt = next((lng for lng in installed if lng.code == target_lang), None)
        translator = src.get_translation(tgt) if src and tgt else None
        pivot_translators = None
        if not translator and source_lang != "en" and target_lang != "en":
            english = next((lng for lng in installed if lng.code == "en"), None)
            first = src.get_translation(english) if src and english else None
            second = english.get_translation(tgt) if english and tgt else None
            if first and second:
                pivot_translators = (first, second)
        if not translator and not pivot_translators:
            if source_lang != "en" and target_lang != "en":
                install_hint = (
                    f"argospm install translate-{source_lang}_en && "
                    f"argospm install translate-en_{target_lang}"
                )
            else:
                install_hint = f"argospm install translate-{source_lang}_{target_lang}"
            raise TranslatorError(
                f"Argos has no installed translation path for {source_lang} -> {target_lang}. "
                f"Run: {install_hint}"
            )

        total = len(texts)
        out: list[str] = []
        for i, t in enumerate(texts, start=1):
            if not t:
                out.append("")
            elif pivot_translators:
                first, second = pivot_translators
                out.append(second.translate(first.translate(t)))
            else:
                out.append(translator.translate(t))
            if on_progress is not None:
                on_progress(i, total)
        return out


LANGUAGE_DISPLAY_NAMES = {
    "ja": "Japanese",
    "ko": "Korean",
    "en": "English",
    "es": "Spanish",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
}


def _display_lang(code: str) -> str:
    return LANGUAGE_DISPLAY_NAMES.get(code.lower(), code)


class OllamaTranslator(_BaseTranslator):
    """Local LLM translator hitting Ollama's HTTP API.

    Batches multiple cues per request using a numbered-list prompt that the
    LLM is asked to mirror in its response. This is dramatically faster than
    one-prompt-per-cue and gives the model surrounding context. We tolerate
    formatting drift (extra prose, missing numbers) by falling back to the
    original text when an output cue cannot be matched."""

    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        batch_size: int = 10,
        auto_load: bool = True,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.batch_size = max(1, batch_size)
        # auto_load=True (the default) calls `/api/pull` for missing models
        # before the first translation. auto_load=False makes us fail fast
        # with an actionable error instead — useful in restricted environments
        # or when the user wants strict control over model installs.
        self.auto_load = auto_load

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(self.host + "/api/tags")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def setup_help(self, source_lang: str | None = None, target_lang: str | None = None) -> str:
        return (
            "Set up Ollama (offline LLM):\n"
            "  # Recommended: install/open the Ollama desktop app so it runs in the background.\n"
            "  # Homebrew alternative:\n"
            "  brew install ollama\n"
            "  brew services start ollama   # background service; does not occupy this terminal\n"
            "  # Temporary fallback only:\n"
            "  ollama serve                 # foreground server; run in a separate terminal\n"
            "  ollama list                  # confirm which models are installed\n"
            f"  ollama pull {self.model}\n"
            f"Use a different installed model with: --model NAME\n"
            f"(Daemon URL: {self.host})"
        )

    def installed_models(self) -> set[str]:
        req = urllib.request.Request(self.host + "/api/tags")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise TranslatorError(f"Ollama network error while checking installed models: {e.reason}") from e
        except Exception as e:
            raise TranslatorError(f"Ollama could not list installed models: {e}") from e
        models = data.get("models", []) if isinstance(data, dict) else []
        names = set()
        for item in models:
            if isinstance(item, dict) and item.get("name"):
                names.add(str(item["name"]))
        return names

    def ensure_model_available(self) -> None:
        installed = self.installed_models()
        if self.model in installed:
            return
        if not self.auto_load:
            raise TranslatorError(
                f"Ollama model {self.model!r} is not installed and "
                f"[translate.ollama_models].auto_load is false.\n"
                "Install it manually, then retry:\n"
                f"  ollama pull {self.model}\n"
                "Or re-enable auto-pull by setting:\n"
                "  [translate.ollama_models]\n"
                "  auto_load = true"
            )
        print(f"Ollama model {self.model!r} is not installed. Pulling it now; this can take a while.")
        body = json.dumps({"name": self.model, "stream": True}).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        last_status = ""
        saw_progress = False
        try:
            with urllib.request.urlopen(req, timeout=1800) as res:
                while True:
                    raw = res.readline()
                    if not raw:
                        break
                    try:
                        data = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if "error" in data:
                        raise TranslatorError(f"Could not pull Ollama model {self.model!r}: {data.get('error')}")
                    status = str(data.get("status", "")).strip()
                    if status:
                        last_status = status
                    completed = data.get("completed")
                    total = data.get("total")
                    if isinstance(completed, int) and isinstance(total, int) and total > 0:
                        saw_progress = True
                        progress_bar(completed, total, "pulling", status or self.model, transient=True)
                if not saw_progress:
                    progress_bar(1, 1, "pulling", last_status or self.model, transient=True)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace").strip()
            detail = f"\nOllama said: {msg[:300]}" if msg else ""
            raise TranslatorError(
                f"Could not pull Ollama model {self.model!r}.\n"
                "Try manually:\n"
                f"  ollama pull {self.model}\n"
                "Or choose an installed model:\n"
                "  ollama list\n"
                "  getsubtitle translate PATH -l ko --engine ollama --model NAME"
                f"{detail}"
            ) from e
        except urllib.error.URLError as e:
            raise TranslatorError(f"Ollama network error while pulling {self.model!r}: {e.reason}") from e
        if last_status:
            print(f"Ollama pull status: {last_status}")

    def translate_batch(self, texts: list[str], source_lang: str, target_lang: str, on_progress=None) -> list[str]:
        if not texts:
            return []
        if not self.is_available():
            raise TranslatorError(
                f"Ollama is not reachable at {self.host}.\n"
                "Recommended setup:\n"
                "  1. Open the Ollama desktop app so it runs in the background, or\n"
                "  2. If installed with Homebrew: brew services start ollama\n"
                "Temporary fallback:\n"
                "  ollama serve   # run in a separate terminal; it keeps that terminal busy\n"
                f"Then retry. getsubtitle will pull {self.model!r} automatically if missing."
            )
        self.ensure_model_available()
        total = len(texts)
        results: list[str] = []
        for chunk_start in range(0, total, self.batch_size):
            chunk = texts[chunk_start : chunk_start + self.batch_size]
            translated = self._translate_chunk(chunk, source_lang, target_lang)
            # Fall back to original cue when a line was lost in the model's reply.
            results.extend(translated[i] if i < len(translated) and translated[i] else chunk[i] for i in range(len(chunk)))
            if on_progress is not None:
                on_progress(min(chunk_start + len(chunk), total), total)
        return results

    def _translate_chunk(self, texts: list[str], source: str, target: str) -> list[str]:
        prompt = self._build_prompt(texts, source, target)
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace").strip()
            if e.code == 404:
                detail = f"\nOllama said: {msg[:300]}" if msg else ""
                raise TranslatorError(
                    f"Ollama HTTP 404 while using model {self.model!r}.\n"
                    "This usually means Ollama is running, but that model is not installed.\n"
                    "Try:\n"
                    "  ollama list\n"
                    f"  ollama pull {self.model}\n"
                    "Or choose an installed model:\n"
                    "  getsubtitle translate PATH -l ko --engine ollama --model NAME"
                    f"{detail}"
                ) from e
            detail = f": {msg[:300]}" if msg else ""
            raise TranslatorError(f"Ollama HTTP {e.code}{detail}") from e
        except urllib.error.URLError as e:
            raise TranslatorError(f"Ollama network error: {e.reason}") from e
        return parse_ollama_numbered_response(str(data.get("response", "")), len(texts))

    def _build_prompt(self, texts: list[str], source: str, target: str) -> str:
        src_name = _display_lang(source)
        tgt_name = _display_lang(target)
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
        return (
            f"Translate the following {src_name} subtitle lines into {tgt_name}. "
            f"Output exactly {len(texts)} numbered lines in the same order. "
            "Do not add commentary, romanisation, or quotation marks. "
            "Preserve speaker tags in parentheses verbatim. "
            "If a line is only punctuation or symbols, repeat it unchanged.\n\n"
            f"{numbered}\n"
        )

    def release_resources(self) -> bool:
        """Ask Ollama to evict the model from memory (RAM/VRAM) immediately.

        Sends `keep_alive: 0` on a no-op generate call — Ollama treats that
        as 'drop this model now'. Best-effort: any error is swallowed,
        because the user's MT run already succeeded by the time we get here.
        Returns True on success, False otherwise."""
        body = json.dumps({
            "model": self.model,
            "prompt": "",
            "keep_alive": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                res.read()
            return True
        except (urllib.error.URLError, OSError):
            return False


class DeepLTranslator(_BaseTranslator):
    """DeepL Free API client. Free tier: 500,000 characters per month.

    DeepL uses uppercase 2-letter codes; some pairs need regional suffixes
    (e.g. PT-BR vs PT-PT). For our supported set (ja/ko/en/es) the simple
    codes work. Source can be None to let DeepL auto-detect."""

    name = "deepl"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def api_base(self) -> str:
        return _deepl_api_base(self.api_key)

    def setup_help(self, source_lang: str | None = None, target_lang: str | None = None) -> str:
        return (
            "Set up the DeepL API key:\n"
            "  getsubtitle --set-key deepl     # macOS Keychain / guided\n"
            "  export DEEPL_API_KEY=...        # Linux/Windows env var\n"
            "Get a free Developer key at https://www.deepl.com/your-account/keys"
        )

    def usage(self) -> DeepLUsage:
        if not self.api_key:
            raise TranslatorError(
                "DeepL API key not set. Run: getsubtitle --set-key deepl, or "
                "export DEEPL_API_KEY=..."
            )
        req = urllib.request.Request(
            f"{self.api_base}/v2/usage",
            headers={
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "User-Agent": "getsubtitle/0.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace").strip()[:200]
            detail = f": {msg}" if msg else ""
            raise TranslatorError(f"DeepL HTTP {e.code}{detail}") from e
        except urllib.error.URLError as e:
            raise TranslatorError(f"DeepL network error: {e.reason}") from e
        if not isinstance(data, dict):
            raise TranslatorError("DeepL returned an unexpected usage response.")
        count = _deepl_int(data, "character_count")
        if count is None:
            raise TranslatorError("DeepL usage response did not include character_count.")
        return DeepLUsage(
            character_count=count,
            character_limit=_deepl_int(data, "character_limit"),
            api_key_character_count=_deepl_int(data, "api_key_character_count"),
            api_key_character_limit=_deepl_int(data, "api_key_character_limit"),
        )

    def translate_batch(self, texts: list[str], source_lang: str, target_lang: str, on_progress=None) -> list[str]:
        if not texts:
            return []
        if not self.api_key:
            raise TranslatorError(
                "DeepL API key not set. Run: getsubtitle --set-key deepl, or "
                "export DEEPL_API_KEY=... (free tier at https://www.deepl.com/your-account/keys)."
            )

        total = len(texts)
        # DeepL accepts up to 50 `text` params per request; chunk just in case.
        results: list[str] = []
        for chunk_start in range(0, total, 50):
            chunk = texts[chunk_start : chunk_start + 50]
            params: list[tuple[str, str]] = [
                ("target_lang", target_lang.upper()),
            ]
            if source_lang:
                params.append(("source_lang", source_lang.upper()))
            for t in chunk:
                params.append(("text", t))
            body = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_base}/v2/translate",
                data=body,
                headers={
                    "Authorization": f"DeepL-Auth-Key {self.api_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "getsubtitle/0.1",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    data = json.loads(res.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", errors="replace")[:200]
                raise TranslatorError(f"DeepL HTTP {e.code}: {msg}") from e
            except urllib.error.URLError as e:
                raise TranslatorError(f"DeepL network error: {e.reason}") from e
            translations = data.get("translations", []) if isinstance(data, dict) else []
            for i, original in enumerate(chunk):
                if i < len(translations) and isinstance(translations[i], dict):
                    results.append(str(translations[i].get("text") or original))
                else:
                    results.append(original)
            if on_progress is not None:
                on_progress(min(chunk_start + len(chunk), total), total)
        return results


# Per-target source-language preference for MT. The first available source
# wins. Designed around the observation that closer grammar/lexicon gives
# better MT quality (ko<-ja over ko<-en) and that EN is the lingua franca
# anywhere else.
MT_SOURCE_PRIORITY: dict[str, tuple[str, ...]] = {
    "ko": ("ja", "zh", "en"),
    "ja": ("zh", "ko", "en"),
    "zh": ("ja", "ko", "en"),
    "es": ("en", "pt", "fr", "ja"),
    "fr": ("en", "es", "pt"),
    "pt": ("es", "en", "fr"),
    "de": ("en", "nl"),
    "en": ("ja", "ko", "es", "fr", "de", "pt"),
}


def pick_mt_source(target: str, available: dict[str, Path]) -> tuple[str, Path] | None:
    """Pick the best source SRT to translate `target` from.

    `available` maps language code -> path to an .srt file we already have.
    Returns (source_lang, path) or None if nothing usable is available."""
    target = target.lower()
    preferred = MT_SOURCE_PRIORITY.get(target, ())
    for src in preferred:
        if src in available and src != target:
            return src, available[src]
    # Fallback: any non-target language we have.
    for src, path in available.items():
        if src != target:
            return src, path
    return None


def mt_output_path(source_srt: Path, target_lang: str) -> Path:
    """`Show - S01E10.ja.srt` -> `Show - S01E10.ko.mt.srt`."""
    name = source_srt.name
    # Strip the source language token ".<2-3 letter>" before .srt
    stem = re.sub(r"\.[A-Za-z]{2,3}(?=\.srt$)", "", name)
    stem = stem[: -len(".srt")] if stem.lower().endswith(".srt") else stem
    return source_srt.with_name(f"{stem}.{target_lang}.mt.srt")


def translate_srt_file(
    source_path: Path,
    target_path: Path,
    translator: _BaseTranslator,
    source_lang: str,
    target_lang: str,
    on_progress=None,
    strip_furigana: bool = True,
) -> int:
    """Translate every cue's text from source_path, writing to target_path.

    Returns the number of cues translated. Preserves indices and timings.
    `on_progress(done, total)` is forwarded to the underlying translator so
    callers can render a cue-level progress bar instead of one tick per
    episode.

    When `strip_furigana` is True (the default) and the source language is
    Japanese, inline 漢字（かんじ） readings are stripped from each cue
    before the translator sees it. Otherwise every reading would be
    translated as if it were extra content, producing duplicated output.
    The default may be overridden per-run via the [furigana].strip_before_mt
    config setting (translate_main and the download flow read it once)."""
    text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    cues = parse_srt(text)
    if not cues:
        return 0
    # Translate each cue as a single string with internal newlines preserved
    # by joining with a sentinel that translators rarely emit.
    sentinel = " ⏎ "
    apply_strip = strip_furigana and source_lang.lower() == "ja"
    payload = [
        (strip_inline_furigana(sentinel.join(cue.text_lines)) if apply_strip
         else sentinel.join(cue.text_lines)) if cue.text_lines else ""
        for cue in cues
    ]
    try:
        translated = translator.translate_batch(payload, source_lang, target_lang, on_progress=on_progress)
    except TypeError as e:
        if "on_progress" not in str(e):
            raise
        translated = translator.translate_batch(payload, source_lang, target_lang)
    for cue, out in zip(cues, translated):
        out = out.replace("\r", "")
        # Split back into lines using the sentinel; tolerate the LLM dropping it.
        if sentinel in out:
            cue.text_lines = [ln for ln in out.split(sentinel) if ln]
        else:
            cue.text_lines = [out] if out else cue.text_lines
    target_path.write_text(serialize_srt(cues), encoding="utf-8")
    return len(cues)


def find_existing_srts_for_episode(saved: list[Path], episode: str) -> dict[str, Path]:
    """Group `saved` paths by language code, restricted to a given episode.

    Filenames are expected to look like `Show - S01E10.ja.srt`. Episodes are
    matched via the `E\\d+` token in the basename."""
    out: dict[str, Path] = {}
    ep_token = f"E{int(episode):02d}" if episode.isdigit() else episode
    for path in saved:
        if path.suffix.lower() != ".srt":
            continue
        name = path.name
        if ".mt." in name:  # never use machine-translated files as MT source
            continue
        if ep_token not in name:
            continue
        m = re.search(r"\.([A-Za-z]{2,3})\.srt$", name)
        if not m:
            continue
        lang = m.group(1).lower()
        # Honour first-wins so primary providers take priority over later additions.
        out.setdefault(lang, path)
    return out


def _normalize_lang_code(value: str) -> str:
    value = value.strip().lower()
    return LANGUAGE_ALIASES.get(value, value)


def parse_mt_source_lang(value: str | None, requested_langs: list[str]) -> dict[str, tuple[str, ...]] | None:
    """Parse the --mt-source value into a {target: (sources...)} mapping.

    Accepts:
      None / empty string       -> None (no override; auto-pick applies)
      "ja"                      -> applies "ja" as source for every target
      "ko:ja"                   -> {"ko": "ja"}
      "ko:ja,es:en"             -> {"ko": "ja", "es": "en"}
      "es:fr|en"                -> {"es": ("fr", "en")} first available wins

    Raises CliError for ambiguous comma-lists-without-colons, unknown targets
    (not in --langs), empty halves, or duplicated targets.

    Public for testing."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() == "auto":
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    if ":" not in raw:
        # Single token (or multiple non-colon tokens, which we reject for
        # being ambiguous between "all targets from this" and "positional").
        if len(parts) == 1:
            src = _normalize_lang_code(parts[0])
            return {_normalize_lang_code(target): (src,) for target in requested_langs}
        raise CliError(
            f"--mt-source: ambiguous value {value!r}. "
            "Use a single language code to apply to all targets, "
            "or 'target:source' pairs (e.g. ko:ja,es:en)."
        )
    mapping: dict[str, tuple[str, ...]] = {}
    # Normalise both -l targets and pair targets/sources through
    # LANGUAGE_ALIASES so users can type jp/cn/chinese/etc. interchangeably.
    requested_lower = {_normalize_lang_code(l) for l in requested_langs}
    for part in parts:
        if ":" not in part:
            raise CliError(
                f"--mt-source: every entry needs a target:source pair "
                f"(got {part!r}). Example: ko:ja,es:en"
            )
        target, _, source = part.partition(":")
        target = _normalize_lang_code(target)
        sources = tuple(
            _normalize_lang_code(src)
            for src in source.split("|")
            if src.strip()
        )
        if not target or not source:
            raise CliError(f"--mt-source: empty target or source in {part!r}")
        if not sources:
            raise CliError(f"--mt-source: empty source list in {part!r}")
        if target not in requested_lower:
            raise CliError(
                f"--mt-source: target {target!r} is not in -l "
                f"({','.join(requested_langs)}). Add it to -l or remove the pair."
            )
        if target in mapping:
            raise CliError(f"--mt-source: target {target!r} mapped twice")
        mapping[target] = sources
    return mapping


def _format_mt_source_overrides(mapping: dict[str, tuple[str, ...]]) -> str:
    return ", ".join(f"{target}<-{'|'.join(sources)}" for target, sources in mapping.items())


def pick_forced_mt_source(
    target: str,
    source_candidates: tuple[str, ...],
    available: dict[str, Path],
) -> tuple[str, Path] | None:
    """Pick the first requested MT source language present for an episode."""
    target = _normalize_lang_code(target)
    for src in source_candidates:
        src = _normalize_lang_code(src)
        if src != target and src in available:
            return src, available[src]
    return None


def parse_mt_model_pair(value: str | None) -> dict[str, str]:
    """Parse --mt-model-pair src:tgt=model[,src:tgt=model] into session map."""
    if not value:
        return {}
    out: dict[str, str] = {}
    for part in [p.strip() for p in value.split(",") if p.strip()]:
        pair, sep, model = part.partition("=")
        if not sep:
            raise CliError(
                f"--mt-model-pair: expected src:tgt=model, got {part!r}. "
                "Example: ja:ko=qwen3:4b,en:es=llama3.2:3b"
            )
        if not model.strip():
            raise CliError(f"--mt-model-pair: empty model name in {part!r}")
        pair_norm = pair.strip().lower().replace("_", "-").replace(":", "-")
        if "-" not in pair_norm:
            raise CliError(f"--mt-model-pair: expected source-target pair in {part!r}")
        src, tgt = pair_norm.split("-", 1)
        src = _normalize_lang_code(src)
        tgt = _normalize_lang_code(tgt)
        if not src or not tgt:
            raise CliError(f"--mt-model-pair: empty source or target in {part!r}")
        out[f"{src}-{tgt}"] = model.strip()
    return out


def apply_mt_model_pair_overrides(value: str | None) -> dict[str, str | None]:
    """Install CLI pair-model overrides for this process; return old values."""
    parsed = parse_mt_model_pair(value)
    previous: dict[str, str | None] = {}
    for key, model in parsed.items():
        previous[key] = _PIPELINE_TRANSLATE_PAIR_MODELS.get(key)
        _PIPELINE_TRANSLATE_PAIR_MODELS[key] = model
    return previous


def restore_mt_model_pair_overrides(previous: dict[str, str | None]) -> None:
    for key, old in previous.items():
        if old is None:
            _PIPELINE_TRANSLATE_PAIR_MODELS.pop(key, None)
        else:
            _PIPELINE_TRANSLATE_PAIR_MODELS[key] = old


def _ollama_models_flag(name: str, default: bool = True) -> bool:
    """Read a boolean flag from [translate.ollama_models] (auto_load,
    auto_unload). Falls back to `default` if unset or if the config can't
    be loaded."""
    try:
        cfg = load_user_config()
    except CliError:
        return default
    val = cfg.get("translate", {}).get("ollama_models", {}).get(name, default)
    return bool(val)


def select_translator(engine: str, model: str | None) -> _BaseTranslator:
    engine = engine.lower()
    if engine == "argos":
        return ArgosTranslator()
    if engine == "ollama":
        return OllamaTranslator(
            model=model or DEFAULT_OLLAMA_MODEL,
            auto_load=_ollama_models_flag("auto_load", True),
        )
    if engine == "deepl":
        return DeepLTranslator(api_key=get_provider_api_key("deepl", prompt_if_missing=True))
    raise CliError(f"Unknown --engine: {engine}. Use argos, ollama, or deepl.")


def ollama_model_for_pair(source_lang: str, target_lang: str, cli_model: str | None = None) -> str:
    """Resolve the Ollama model for a translation pair.

    Precedence: --mt-model > pipeline TOML [translate]."src:tgt" (session)
    > [translate.ollama_models].src-tgt (user_settings.toml) >
    [translate].model > built-in default.
    """
    if cli_model:
        return cli_model
    source = LANGUAGE_ALIASES.get(source_lang.lower(), source_lang.lower())
    target = LANGUAGE_ALIASES.get(target_lang.lower(), target_lang.lower())
    pair_dash = f"{source}-{target}"
    pair_colon = f"{source}:{target}"
    # Session-only pipeline overrides take precedence over user_settings.toml.
    for key in (pair_colon, pair_dash):
        if key in _PIPELINE_TRANSLATE_PAIR_MODELS:
            return _PIPELINE_TRANSLATE_PAIR_MODELS[key]
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}
    translate_cfg = cfg.get("translate", {})
    pair_models = translate_cfg.get("ollama_models", {}) or {}
    if pair_dash in pair_models:
        return str(pair_models[pair_dash])
    return str(translate_cfg.get("model") or DEFAULT_OLLAMA_MODEL)


def select_translator_for_pair(
    engine: str, model: str | None, source_lang: str, target_lang: str
) -> _BaseTranslator:
    selected_model = ollama_model_for_pair(source_lang, target_lang, model) if engine == "ollama" else model
    return select_translator(engine, selected_model)


def option_was_passed(argv: list[str], *names: str) -> bool:
    prefixes = tuple(name + "=" for name in names)
    return any(arg in names or arg.startswith(prefixes) for arg in argv)


def format_elapsed(seconds: float) -> str:
    seconds_i = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds_i, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def parse_ollama_numbered_response(response: str, expected: int) -> list[str]:
    """Extract translated lines from an LLM reply.

    Public for testing. Looks for `1. ...`, `1) ...`, or `1: ...` line starts.
    Returns up to `expected` strings; missing slots stay empty so the caller
    can fall back to the source text."""
    out: list[str | None] = [None] * expected
    pattern = re.compile(r"^\s*(\d+)\s*[\.\):]\s*(.*\S)\s*$")
    for line in response.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if 0 <= idx < expected:
            out[idx] = m.group(2)
    return [s if s is not None else "" for s in out]


def split_csv(value: str | None, default: str) -> list[str]:
    value = value or default
    langs = []
    for part in value.split(","):
        lang = part.strip().lower()
        if not lang:
            continue
        langs.append(LANGUAGE_ALIASES.get(lang, lang))
    return langs


def parse_episode_selector(value: str) -> list[str]:
    value = str(value).strip().lower()
    if value in {"auto", "all"}:
        return [value]
    episodes: list[str] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            episodes.extend(str(i) for i in range(int(start), int(end) + 1))
        else:
            episodes.append(str(int(part)))
    return episodes


def expand_episodes(value: str, total_episodes: int | None) -> list[str]:
    episodes = parse_episode_selector(value)
    if episodes == ["all"] and total_episodes:
        return [str(i) for i in range(1, total_episodes + 1)]
    return episodes


def normalized_release_source(text: str) -> str | None:
    value = text.lower()
    if any(token in value for token in ["netflix", ".nf.", " nf ", "webrip.nf", "web-dl.nf"]):
        return "netflix"
    if any(token in value for token in ["crunchyroll", ".cr.", " cr ", "webrip.cr", "web-dl.cr"]):
        return "crunchyroll"
    if any(token in value for token in ["amazon", ".amzn.", " amzn ", "prime video"]):
        return "amazon"
    if any(token in value for token in ["hulu", ".hulu.", "webrip.hulu", "web-dl.hulu"]):
        return "hulu"
    # Both HBO Max and the rebranded Max share these tags; .max. catches the
    # newer brand and .hmax./.hbomax. cover the older era's release groups.
    if any(token in value for token in [
        "hbo", "hmax", "hbomax", "max.web", ".max.", "webrip.max", "web-dl.max",
    ]):
        return "hbo"
    if any(token in value for token in [
        "disney+", "disneyplus", "dsnp", ".dsnp.", "webrip.dsnp", "web-dl.dsnp",
    ]):
        return "disney"
    if any(token in value for token in [
        "apple tv", "appletv", "atvp", ".atvp.", "webrip.atvp", "web-dl.atvp",
    ]):
        return "apple"
    if any(token in value for token in [
        "paramount+", "paramountplus", "pmtp", ".pmtp.", "webrip.pmtp", "web-dl.pmtp",
    ]):
        return "paramount"
    if any(token in value for token in [
        "peacock", "pcok", ".pcok.", "webrip.pcok", "web-dl.pcok",
    ]):
        return "peacock"
    if any(token in value for token in ["bluray", "blu-ray", "bdrip", "brrip"]):
        return "bluray"
    if any(token in value for token in ["web-dl", "webrip", "web "]):
        return "web"
    if "hdtv" in value:
        return "hdtv"
    if "dvd" in value:
        return "dvd"
    return None


# Streaming host → release-source preference. Used by --release-source auto
# so pasting a hulu.com URL preselects HULU rips when multiple are available.
STREAMING_HOST_RELEASE_SOURCE: dict[str, str] = {
    "netflix.com": "netflix",
    "crunchyroll.com": "crunchyroll",
    "amazon.com": "amazon",
    "primevideo.com": "amazon",
    "hulu.com": "hulu",
    "max.com": "hbo",
    "play.max.com": "hbo",
    "hbomax.com": "hbo",
    "disneyplus.com": "disney",
    "tv.apple.com": "apple",
    "paramountplus.com": "paramount",
    "peacocktv.com": "peacock",
}


def release_source_from_host(host: str) -> str | None:
    """Return a release-source preference inferred from a URL host, or None.
    Used by --release-source auto to bias subtitle picking toward releases
    that match the source the user is actually watching from."""
    host = (host or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    for known_host, source in STREAMING_HOST_RELEASE_SOURCE.items():
        if host == known_host or host.endswith("." + known_host):
            return source
    return None


def safe_filename(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "Unknown"


def output_dir(base: Path, media: MediaInfo, season: str, layout: str) -> Path:
    if layout == "flat":
        return base
    show = safe_filename(media.title or "Unknown Show")
    if layout == "plex":
        return base
    # Movies have no season — drop the per-season subfolder so the layout
    # is `Downloads/GetSubtitle/<Title>/<Title>.<lang>.srt` instead of
    # `Downloads/GetSubtitle/<Title>/Season Unknown/<Title> - S00E00.<lang>.srt`.
    if media.is_movie:
        return base / show
    if season == "all":
        season_label = "All Seasons"
    elif season.isdigit():
        season_label = f"Season {int(season):02d}"
    else:
        season_label = "Season Unknown"
    return base / show / season_label


def subtitle_quality_flags(file: SubtitleFile) -> tuple[bool, bool]:
    searchable = " ".join(
        str(part)
        for part in [
            file.name,
            file.release or "",
            file.origin or "",
            file.source_provider or "",
        ]
        if part
    ).lower()
    hi = bool(re.search(r"\b(?:hi|sdh|cc|hearing[- ]?impaired|closed captions?)\b", searchable))
    dubbed = bool(re.search(r"\b(?:dubbed|dub)\b", searchable))
    return hi, dubbed


def choose_best(files: list[SubtitleFile], preferred_source: str | None = None) -> SubtitleFile | None:
    if not files:
        return None
    preferred = [".srt", ".ass", ".vtt", ".ssa", ".zip"]
    source = preferred_source.lower() if preferred_source else None

    def score(file: SubtitleFile) -> tuple[int, int, int, int, int, int, str]:
        ext = Path(file.name).suffix.lower()
        searchable = " ".join(
            part
            for part in [
                file.name,
                file.release or "",
                file.origin or "",
                file.release_source or "",
                file.source_provider or "",
            ]
            if part
        ).lower()
        source_score = 0 if source and (source == file.release_source or source in searchable) else 1 if source else 0
        ai_score = 1 if file.ai else 0
        hi, dubbed = subtitle_quality_flags(file)
        hi_score = 1 if hi else 0
        dubbed_score = 1 if dubbed else 0
        ext_score = preferred.index(ext) if ext in preferred else 99
        provider_score = 0 if file.source_provider in {"opensubtitles", "subdl", "podnapisi"} else 1
        return source_score, ai_score, hi_score, dubbed_score, ext_score, provider_score, file.name.lower()

    return sorted(files, key=score)[0]


def provider_debug_record(
    provider: str,
    episode: str,
    language: str,
    files: list[SubtitleFile],
    *,
    error: str | None = None,
) -> ProviderDebugRecord:
    lang_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    ext_counts: dict[str, int] = {}
    ai_count = 0
    hi_count = 0
    dubbed_count = 0
    for file in files:
        lang_tag = file.provider_language or "(no tag)"
        source_tag = file.source_provider or file.provider or "(no source)"
        ext = Path(file.name).suffix.lower() or "(none)"
        lang_counts[lang_tag] = lang_counts.get(lang_tag, 0) + 1
        source_counts[source_tag] = source_counts.get(source_tag, 0) + 1
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        if file.ai:
            ai_count += 1
        hi, dubbed = subtitle_quality_flags(file)
        if hi:
            hi_count += 1
        if dubbed:
            dubbed_count += 1
    return ProviderDebugRecord(
        provider=provider,
        episode=episode,
        language=language,
        count=len(files),
        language_tags=lang_counts,
        source_tags=source_counts,
        extensions=ext_counts,
        ai_count=ai_count,
        hi_count=hi_count,
        dubbed_count=dubbed_count,
        example=files[0].name if files else "",
        error=error,
    )


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "-"


def print_provider_debug(records: list[ProviderDebugRecord]) -> None:
    if not records:
        return
    print("\nProvider debug:")
    header = ("Provider", "Ep", "Lang", "Found", "Sources", "Tags", "Fmt", "Flags", "Example/Error")
    rows = []
    for r in records:
        flags = []
        if r.ai_count:
            flags.append(f"AI:{r.ai_count}")
        if r.hi_count:
            flags.append(f"HI:{r.hi_count}")
        if r.dubbed_count:
            flags.append(f"dub:{r.dubbed_count}")
        rows.append((
            r.provider,
            episode_label(r.episode),
            r.language,
            str(r.count),
            _format_counts(r.source_tags),
            _format_counts(r.language_tags),
            _format_counts(r.extensions),
            ",".join(flags) or "-",
            (r.error or r.example or "-")[:80],
        ))
    widths = [len(h) for h in header]
    for row in rows:
        widths = [max(widths[i], len(row[i])) for i in range(len(header))]
    print("  " + "  ".join(header[i].ljust(widths[i]) for i in range(len(header))))
    print("  " + "  ".join("-" * widths[i] for i in range(len(header))))
    for row in rows:
        print("  " + "  ".join(row[i].ljust(widths[i]) for i in range(len(header))))


def _episode_for_output_filename(episode: str, episode_filename_start: int | None = None) -> str:
    if episode_filename_start is None or episode_filename_start <= 1:
        return episode
    ep = str(episode).strip().lower()
    if not ep.isdigit():
        return episode
    return str(int(ep) + episode_filename_start - 1)


def save_subtitle(
    sub: SubtitleFile,
    dest_dir: Path,
    media: MediaInfo,
    season: str,
    episode: str,
    *,
    episode_filename_start: int | None = None,
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = download_bytes(sub.url, headers=sub.download_headers)
    ext = Path(sub.name).suffix.lower() or ".srt"
    saved: list[Path] = []

    if ext == ".zip":
        archive_path = dest_dir / safe_filename(sub.name)
        archive_path.write_bytes(raw)
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                if Path(member).suffix.lower() not in SUB_EXTENSIONS:
                    continue
                out = dest_dir / safe_filename(Path(member).name)
                out.write_bytes(zf.read(member))
                saved.append(out)
        if not saved:
            saved.append(archive_path)
        return saved

    show = safe_filename(media.title or "Unknown Show")
    if media.is_movie:
        # Movies get a flat `Title.<lang>.srt` filename. Skipping
        # SxxExx prevents the cosmetic "S00E00" placeholder that the TV
        # convention would otherwise emit.
        filename = f"{show}.{sub.language}{ext}"
    else:
        filename_episode = _episode_for_output_filename(episode, episode_filename_start)
        ep = "00" if filename_episode in {"all", "auto"} else f"{int(filename_episode):02d}"
        ss = "01" if season == "all" else "00" if season == "auto" else f"{int(season):02d}"
        filename = f"{show} - S{ss}E{ep}.{sub.language}{ext}"
    out = dest_dir / filename
    out.write_bytes(raw)
    saved.append(out)
    return saved


def download_planned_subtitles(
    planned: list[tuple[str, str, SubtitleFile]],
    *,
    base: Path,
    media: MediaInfo,
    season: str,
    layout: str,
    episode_filename_start: int | None = None,
) -> tuple[list[Path], list[str]]:
    saved: list[Path] = []
    failures: list[str] = []
    print("\nDownloading subtitles:")
    for idx, (_lang, ep, sub) in enumerate(planned, start=1):
        progress_bar(idx, len(planned), "downloading", f"episode {ep} {sub.language}", transient=True)
        dest = output_dir(base, media, season, layout)
        try:
            if episode_filename_start and episode_filename_start > 1:
                saved.extend(
                    save_subtitle(
                        sub, dest, media, season, ep,
                        episode_filename_start=episode_filename_start,
                    )
                )
            else:
                saved.extend(save_subtitle(sub, dest, media, season, ep))
        except CliError as e:
            provider = sub.provider or sub.source_provider or "provider"
            failures.append(f"{sub.language} ep{ep}: download failed from {provider} — {e}")
    return saved, failures


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def has_kanji(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


EXISTING_READING_RE = re.compile(r"([\u4e00-\u9fff々〆ヶ]+)[(（]([ぁ-ゖァ-ヺーa-zA-Z0-9 -]+)[)）]")


# Map our public Japanese reading-mode names onto pykakasi's per-token
# field keys. pykakasi.convert() returns entries with at least:
#   orig    — the original token
#   hira    — hiragana reading
#   kana    — katakana reading
#   hepburn — Hepburn romaji reading
# Keeping the mapping in one place lets every ja helper stay consistent.
_PYKAKASI_KEY_FOR_MODE: dict[str, str] = {
    "hiragana": "hira",
    "katakana": "kana",
    "romaji": "hepburn",
}


def _pykakasi_reading_key(mode: str) -> str:
    """Pick the right pykakasi field for a Japanese reading mode.
    Unknown modes default to hiragana — the historical fallback."""
    return _PYKAKASI_KEY_FOR_MODE.get(mode, "hira")


def strip_inline_furigana(text: str) -> str:
    """Remove inline reading annotations like 漢字（かんじ） from `text`,
    keeping just the surface kanji. Safe to call on any text — non-matching
    text is returned unchanged. Used to clean MT input when furigana may
    have been inlined upstream (which would cause every reading to be
    re-translated as if it were extra content)."""
    return EXISTING_READING_RE.sub(lambda m: m.group(1), text)


ASS_INLINE_TAG_RE = re.compile(r"\{\\[^}]*\}")


def strip_subtitle_markup(text: str) -> str:
    return ASS_INLINE_TAG_RE.sub("", text)


def protect_existing_readings(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = f"__GETSUBTITLE_READING_{len(protected)}__"
        surface = match.group(1)
        reading = match.group(2)
        protected[token] = f"{surface}（{reading}）"
        return token

    return EXISTING_READING_RE.sub(repl, text), protected


def protect_existing_readings_as_ruby(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = f"__GETSUBTITLE_READING_{len(protected)}__"
        protected[token] = ruby_tag(match.group(1), match.group(2))
        return token

    return EXISTING_READING_RE.sub(repl, text), protected


def restore_existing_readings(text: str, protected: dict[str, str]) -> str:
    for token, original in protected.items():
        text = text.replace(token, original)
    return text


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def ruby_tag(surface: str, reading: str) -> str:
    return f"<ruby>{html_escape(surface)}<rt>{html_escape(reading)}</rt></ruby>"


ROMAJI_LEADING_PARTICLES = {
    "が": "ga",
    "を": "wo",
    "は": "ha",
    "に": "ni",
    "へ": "he",
    "と": "to",
    "で": "de",
    "も": "mo",
    "の": "no",
    "や": "ya",
}
ROMAJI_NO_SPACE_BEFORE = set(".,!?;:)]}）】」』。、！？；：")
ROMAJI_NO_SPACE_AFTER = set("([{（【「『")


def _join_romaji_tokens(tokens: list[str]) -> str:
    out = ""
    for token in [t for t in tokens if t]:
        if not out:
            out = token
            continue
        if token[0] in ROMAJI_NO_SPACE_BEFORE or out[-1] in ROMAJI_NO_SPACE_AFTER:
            out += token
        else:
            out += " " + token
    return out.strip()


def japanese_full_sentence_reading(text: str, mode: str) -> str:
    """Return a full Japanese reading line for romaji-style learner rows."""
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    chunks: list[str] = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if reading and reading != surface and (has_kanji(surface) or mode == "romaji"):
            if mode == "romaji" and surface and not has_kanji(surface):
                particle = ROMAJI_LEADING_PARTICLES.get(surface[0])
                if particle and reading.startswith(particle) and len(reading) > len(particle):
                    chunks.append(particle)
                    chunks.append(reading[len(particle):])
                    continue
            chunks.append(reading)
        else:
            chunks.append(surface)
    if mode == "romaji":
        return _join_romaji_tokens(chunks)
    return "".join(chunks).strip()


def text_with_readings(text: str, mode: str) -> str:
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    protected_text, protected = protect_existing_readings(strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(protected_text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if surface and reading and surface != reading and has_kanji(surface):
            chunks.append(f"{surface}（{reading}）")
        else:
            chunks.append(surface)
    return restore_existing_readings("".join(chunks), protected)


def text_with_ruby(text: str, mode: str) -> str:
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    clean_text = strip_subtitle_markup(text)
    if mode == "romaji":
        return html_escape(japanese_full_sentence_reading(clean_text, mode))

    protected_text, protected = protect_existing_readings_as_ruby(clean_text)
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(protected_text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if surface and reading and surface != reading and has_kanji(surface):
            chunks.append(ruby_tag(surface, reading))
        else:
            chunks.append(html_escape(surface))
    return restore_existing_readings("".join(chunks), protected)


SINGLE_LINE_DECORATIVE_WRAPPERS = str.maketrans("", "", "《》〈〉")


def clean_single_line_text(text: str) -> str:
    """Remove subtitle wrapper glyphs that become distracting in one-line cues."""
    return text.translate(SINGLE_LINE_DECORATIVE_WRAPPERS).strip()


def flatten_subtitle_lines(lines: list[str]) -> list[str]:
    cleaned = [
        clean_single_line_text(strip_subtitle_markup(line).strip())
        for line in lines
        if line.strip()
    ]
    flattened = "　".join(line for line in cleaned if line)
    return [flattened] if flattened else []


# Japanese broadcast-caption continuation arrow. Common in ANIMAX / NHK CC
# tracks. Indicates the sentence continues into the next cue; pure formatting
# noise for language-learning use.
JA_CC_CONTINUATION_ARROW = "➡"  # ➡


def strip_cc_arrows_text(text: str) -> str:
    """Remove Japanese CC continuation arrows from a string and tidy the
    trailing whitespace they leave behind. Operates on raw SRT text — safe
    against timing lines because they don't contain U+27A1."""
    if JA_CC_CONTINUATION_ARROW not in text:
        return text
    cleaned = text.replace(JA_CC_CONTINUATION_ARROW, "")
    # Collapse whitespace the arrow was hugging (typically end-of-line).
    cleaned = re.sub(r"[ \t　]+(\n)", r"\1", cleaned)
    cleaned = re.sub(r"[ \t　]+$", "", cleaned)
    return cleaned


def strip_cc_decorative_wrappers_text(text: str) -> str:
    """Remove broadcast subtitle wrapper marks such as 《...》 and 〈...〉."""
    return text.translate(SINGLE_LINE_DECORATIVE_WRAPPERS)


def strip_cc_noise_text(text: str) -> str:
    """Umbrella cleanup for closed-caption / broadcast-caption artifacts.

    As we identify more shapes of CC noise to remove (music markers,
    voiceover brackets, etc.) we can layer them in here without changing the
    CLI flag or the call sites."""
    cleaned = strip_cc_arrows_text(text)
    cleaned = strip_cc_decorative_wrappers_text(cleaned)
    return cleaned


@dataclass
class SrtCue:
    index: str        # original index string ("1", "2", ...) preserved verbatim
    time_line: str    # "00:00:01,000 --> 00:00:02,000" (and any positioning extensions)
    text_lines: list[str]  # text lines, each without trailing newline


def parse_srt(text: str) -> list[SrtCue]:
    """Parse an SRT body into cues. Tolerates BOM, CRLF, missing indices, and
    cues with positional extensions on the time line."""
    text = text.lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues: list[SrtCue] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if not lines:
            continue
        # Optional numeric index on the first line.
        if lines[0].strip().isdigit():
            index = lines[0].strip()
            lines = lines[1:]
        else:
            index = str(len(cues) + 1)
        if not lines or "-->" not in lines[0]:
            # Malformed block — skip rather than crash.
            continue
        time_line = lines[0].strip()
        text_lines = [ln for ln in lines[1:] if ln.strip()]
        cues.append(SrtCue(index=index, time_line=time_line, text_lines=text_lines))
    return cues


def serialize_srt(cues: list[SrtCue]) -> str:
    """Inverse of parse_srt. Always ends with a single trailing newline."""
    blocks: list[str] = []
    for cue in cues:
        body = "\n".join(cue.text_lines) if cue.text_lines else ""
        blocks.append(f"{cue.index}\n{cue.time_line}\n{body}".rstrip())
    return "\n\n".join(blocks) + "\n"


def renumber_cues(cues: list[SrtCue]) -> list[SrtCue]:
    """Return a copy with simple 1..N cue indexes."""
    return [
        SrtCue(index=str(idx), time_line=cue.time_line, text_lines=list(cue.text_lines))
        for idx, cue in enumerate(cues, start=1)
    ]


_VTT_CUE_HEADER_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})",
)


def _vtt_time_to_srt(t: str) -> str:
    """Normalize a WebVTT timestamp to SRT format (HH:MM:SS,mmm).

    VTT allows MM:SS.mmm (no hour). SRT requires HH:MM:SS,mmm with comma.
    """
    t = t.strip().replace(".", ",")
    parts = t.split(":")
    if len(parts) == 2:
        # MM:SS,mmm → 00:MM:SS,mmm
        parts = ["00"] + parts
    h, m, rest = parts[0], parts[1], parts[2]
    return f"{int(h):02d}:{int(m):02d}:{rest}"


_VTT_RUBY_RE = re.compile(r"<ruby>(.*?)<rt>(.*?)</rt>(?:\s*</ruby>)?", re.DOTALL)
_VTT_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_vtt_markup(text: str) -> str:
    """Remove WebVTT/HTML markup from cue text. Ruby `<ruby>漢字<rt>かんじ</rt></ruby>`
    collapses to `漢字（かんじ）` (parenthetical reading) so merged output
    preserves furigana information. Other HTML tags are stripped wholesale."""
    def _ruby_to_parens(m: re.Match) -> str:
        base = m.group(1).strip()
        reading = m.group(2).strip()
        return f"{base}（{reading}）" if reading else base
    text = _VTT_RUBY_RE.sub(_ruby_to_parens, text)
    text = _VTT_HTML_TAG_RE.sub("", text)
    return text


def parse_vtt(text: str, *, preserve_ruby: bool = False) -> list[SrtCue]:
    """Parse a WebVTT body into the same SrtCue structure used by the
    merge pipeline. Ruby markup is collapsed to `漢字（かんじ）` so that
    furigana information survives the read. Other VTT-specific markup
    (positioning, classes, etc.) is dropped.

    Tolerates the WEBVTT header, NOTE blocks, and cue identifiers.
    """
    text = text.lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues: list[SrtCue] = []
    # Strip the WEBVTT header line (and any signature/header keywords).
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = block.splitlines()
        # Skip the file header and NOTE blocks.
        if lines and lines[0].strip().upper().startswith("WEBVTT"):
            continue
        if lines and lines[0].strip().upper().startswith("NOTE"):
            continue
        if not lines:
            continue
        # Optional cue identifier (any line before the time line).
        time_line_idx = None
        for i, ln in enumerate(lines):
            if "-->" in ln:
                time_line_idx = i
                break
        if time_line_idx is None:
            continue
        time_line_raw = lines[time_line_idx].strip()
        m = _VTT_CUE_HEADER_RE.match(time_line_raw)
        if not m:
            continue
        start = _vtt_time_to_srt(m.group("start"))
        end = _vtt_time_to_srt(m.group("end"))
        srt_time_line = f"{start} --> {end}"
        text_lines = []
        for ln in lines[time_line_idx + 1:]:
            stripped = ln.strip() if preserve_ruby else _strip_vtt_markup(ln).strip()
            if stripped:
                text_lines.append(stripped)
        cues.append(SrtCue(
            index=str(len(cues) + 1),
            time_line=srt_time_line,
            text_lines=text_lines,
        ))
    return cues


def _sami_cues_to_srt_cues(cues: list[tuple[int, int, str]]) -> list[SrtCue]:
    """Adapter from parse_sami's `(start_ms, end_ms, text)` triples to the
    SrtCue list used by the merge pipeline."""
    out: list[SrtCue] = []
    for idx, (start_ms, end_ms, body) in enumerate(sorted(cues, key=lambda c: (c[0], c[1])), start=1):
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        time_line = f"{_format_srt_timestamp(start_ms)} --> {_format_srt_timestamp(end_ms)}"
        text_lines = [ln for ln in body.split("\n") if ln.strip()]
        out.append(SrtCue(index=str(idx), time_line=time_line, text_lines=text_lines))
    return out


_ASS_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_ASS_EVENT_RE = re.compile(r"^(Dialogue|Comment)\s*:\s*(.*)$", re.IGNORECASE)


def _ass_time_to_srt(value: str) -> str:
    value = value.strip()
    m = re.match(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.](\d{1,3}))?$", value)
    if not m:
        raise CliError(f"Invalid ASS timestamp: {value!r}")
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    frac = (m.group(4) or "0").ljust(3, "0")[:3]
    # ASS commonly stores centiseconds; h:mm:ss.cc should become cc0 ms.
    if len((m.group(4) or "")) == 2:
        frac = (m.group(4) + "0")[:3]
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{frac}"


def _ass_clean_text(text: str) -> list[str]:
    text = re.sub(r"\{[^}]*\}", "", text)
    text = text.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    text = text.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    return [line.strip() for line in text.split("\n") if line.strip()]


def parse_ass(text: str) -> list[SrtCue]:
    """Parse basic ASS/SSA Events into SrtCue objects.

    This intentionally ignores styling and comments; it extracts Dialogue
    Start/End/Text fields so downloaded community .ass/.ssa files can be used
    as merge inputs.
    """
    section = ""
    fields_order: list[str] = []
    cues: list[SrtCue] = []
    for raw_line in text.splitlines():
        line = raw_line.strip("\ufeff")
        sec = _ASS_SECTION_RE.match(line)
        if sec:
            section = sec.group(1).strip().lower()
            fields_order = []
            continue
        if section != "events":
            continue
        if line.lower().startswith("format:"):
            fields_order = [part.strip().lower() for part in line.split(":", 1)[1].split(",")]
            continue
        m = _ASS_EVENT_RE.match(line)
        if not m or m.group(1).lower() == "comment":
            continue
        body = m.group(2)
        if not fields_order:
            fields_order = [
                "layer", "start", "end", "style", "name",
                "marginl", "marginr", "marginv", "effect", "text",
            ]
        parts = body.split(",", max(0, len(fields_order) - 1))
        if len(parts) < len(fields_order):
            continue
        data = {field: parts[idx].strip() for idx, field in enumerate(fields_order)}
        start = data.get("start")
        end = data.get("end")
        cue_text = data.get("text", "")
        if not start or not end or not cue_text:
            continue
        try:
            time_line = f"{_ass_time_to_srt(start)} --> {_ass_time_to_srt(end)}"
        except CliError:
            continue
        text_lines = _ass_clean_text(cue_text)
        if not text_lines:
            continue
        cues.append(SrtCue(index=str(len(cues) + 1), time_line=time_line, text_lines=text_lines))
    return cues


def parse_smi_for_lang(path: Path, lang: str) -> list[SrtCue]:
    """Read a .smi file and return SrtCues for the requested language only.
    Returns an empty list if the language isn't present in the SAMI body.
    Uses the same encoding-detection path as convert_smi_file."""
    data = path.read_bytes()
    text = _sami_decode_bytes(data)
    by_lang = parse_sami(text)
    if lang not in by_lang:
        return []
    return _sami_cues_to_srt_cues(by_lang[lang])


def read_cues_from_file(
    path: Path,
    *,
    lang_hint: str | None = None,
    preserve_vtt_ruby: bool = False,
) -> list[SrtCue]:
    """Read any supported subtitle file into the unified SrtCue
    representation used by the merge pipeline.

    Dispatch by extension:
      .srt        → parse_srt
      .vtt        → parse_vtt (ruby collapsed to 漢字（かんじ） unless
                    preserve_vtt_ruby is true)
      .ass/.ssa    → parse_ass (Events Dialogue timing/text; styling ignored)
      .smi/.sami  → parse_smi_for_lang (requires lang_hint)
    """
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(path.read_text(encoding="utf-8-sig", errors="replace"))
    if suffix == ".vtt":
        return parse_vtt(
            path.read_text(encoding="utf-8-sig", errors="replace"),
            preserve_ruby=preserve_vtt_ruby,
        )
    if suffix in (".ass", ".ssa"):
        return parse_ass(path.read_text(encoding="utf-8-sig", errors="replace"))
    if suffix in (".smi", ".sami"):
        if not lang_hint:
            raise CliError(
                f"Reading {path.name}: SAMI is multi-language; pass a lang_hint."
            )
        return parse_smi_for_lang(path, lang_hint)
    raise CliError(
        f"Cannot read subtitles from {path.name}: extension {suffix!r} "
        "not supported. Convert to SRT first with `getsubtitle modify "
        "--convert smi-to-srt` when applicable."
    )


def serialize_vtt(cues: list[SrtCue]) -> str:
    """Serialize cue stack as WebVTT. Cue text is assumed already escaped or
    intentionally marked up (e.g. ruby HTML)."""
    blocks = ["WEBVTT"]
    for cue in cues:
        time_line = cue.time_line.replace(",", ".")
        body = "\n".join(cue.text_lines) if cue.text_lines else ""
        blocks.append(f"{time_line}\n{body}".rstrip())
    return "\n\n".join(blocks) + "\n"


def _parse_time_line_to_ms(line: str) -> tuple[int, int]:
    start, end = parse_srt_time_line(line)
    return start, end


def _ms_to_ass_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    cs = (ms % 1000) // 10
    total_seconds = ms // 1000
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")


def ass_font_size_for_stack(cues: list[SrtCue]) -> int:
    max_lines = max((len([line for line in cue.text_lines if line.strip()]) for cue in cues), default=1)
    if max_lines >= 5:
        return 26
    if max_lines == 4:
        return 30
    if max_lines == 3:
        return 36
    return 42


def serialize_ass(cues: list[SrtCue]) -> str:
    font_size = ass_font_size_for_stack(cues)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,30,30,30,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events: list[str] = []
    for cue in cues:
        start_ms, end_ms = _parse_time_line_to_ms(cue.time_line)
        body = r"\N".join(_escape_ass_text(line) for line in cue.text_lines if line.strip())
        if not body:
            continue
        events.append(
            f"Dialogue: 0,{_ms_to_ass_time(start_ms)},{_ms_to_ass_time(end_ms)},Default,,0,0,0,,{body}"
        )
    return header + "\n".join(events) + ("\n" if events else "")


def _ms_to_smi_time(ms: int) -> str:
    return str(max(0, int(ms)))


def serialize_smi(cues: list[SrtCue]) -> str:
    out: list[str] = [
        "<SAMI>",
        "<HEAD>",
        "<STYLE TYPE=\"text/css\">",
        "<!--",
        "P { margin-left:2pt; margin-right:2pt; margin-bottom:1pt; margin-top:1pt;",
        " font-size:20pt; text-align:center; font-family:Arial, sans-serif; font-weight:normal; color:white; }",
        ".SUBTTL { Name:English; lang:en-US; SAMIType:CC; }",
        "-->",
        "</STYLE>",
        "</HEAD>",
        "<BODY>",
    ]
    for cue in cues:
        start_ms, end_ms = _parse_time_line_to_ms(cue.time_line)
        text = "<br>".join(html_escape(line) for line in cue.text_lines if line.strip())
        out.append(f"<SYNC Start={_ms_to_smi_time(start_ms)}><P Class=SUBTTL>{text}</P></SYNC>")
        out.append(f"<SYNC Start={_ms_to_smi_time(end_ms)}><P Class=SUBTTL>&nbsp;</P></SYNC>")
    out.extend(["</BODY>", "</SAMI>"])
    return "\n".join(out) + "\n"


def serialize_txt(cues: list[SrtCue]) -> str:
    # Plain transcript: no timestamps, no indices, no style/HTML tags.
    lines: list[str] = []
    for cue in cues:
        for line in cue.text_lines:
            cleaned = _strip_vtt_markup(strip_subtitle_markup(line)).strip()
            if cleaned:
                lines.append(cleaned)
    return "\n".join(lines) + ("\n" if lines else "")


def apply_japanese_ruby(cues: list[SrtCue], mode: str) -> None:
    """Inline WebVTT/browser ruby markup into Japanese cue text in place."""
    for cue in cues:
        cue.text_lines = [text_with_ruby(line, mode) for line in cue.text_lines]


def strip_cc_arrows_in_place(path: Path) -> None:
    """Deprecated narrow alias kept for callers that touch this directly.
    Prefer strip_cc_noise_in_place which subsumes this and any future
    CC-cleanup categories."""
    strip_cc_noise_in_place(path)


def strip_cc_noise_in_place(path: Path) -> None:
    """Rewrite an SRT file with CC noise removed in place. Idempotent —
    a second call is a no-op when nothing further to strip."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = strip_cc_noise_text(text)
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")


def flatten_srt_in_place(path: Path, separator: str = " ") -> None:
    """Rewrite an SRT file so each cue's text occupies a single line.

    Joins multi-line subtitle text with `separator`. Preserves cue indices and
    timings. Leaves cues whose bodies are already single-line untouched.
    Idempotent: running twice produces the same file."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    out_blocks: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        time_idx: int | None = None
        for idx, ln in enumerate(lines):
            if "-->" in ln:
                time_idx = idx
                break
        if time_idx is None:
            out_blocks.append(block)
            continue
        header = lines[: time_idx + 1]
        subtitle_lines = [
            clean_single_line_text(strip_subtitle_markup(ln).strip())
            for ln in lines[time_idx + 1 :]
            if ln.strip()
        ]
        if not subtitle_lines:
            out_blocks.append(block)
            continue
        flat = separator.join(ln for ln in subtitle_lines if ln)
        if not flat:
            out_blocks.append("\n".join(header))
            continue
        out_blocks.append("\n".join(header + [flat]))
    path.write_text("\n\n".join(out_blocks) + "\n", encoding="utf-8")


def flatten_separator_for(path: Path) -> str:
    """Pick a join separator suited to the SRT's language.

    Full-width space '　' for Japanese (matches CJK rendering width); regular
    space for everything else."""
    return "　" if ".ja" in path.name else " "


# ---------------------------------------------------------------------------
# SAMI (.smi) → SRT conversion
# ---------------------------------------------------------------------------
# Microsoft SAMI is the dominant Korean subtitle container on consumer disks.
# Files we care about look roughly like:
#
#   <SAMI>
#     <HEAD><STYLE>.KRCC { ... } .ENCC { ... }</STYLE></HEAD>
#     <BODY>
#       <SYNC Start=1234><P Class=KRCC>안녕하세요<br>반갑습니다</P></SYNC>
#       <SYNC Start=4321><P Class=KRCC>&nbsp;</P></SYNC>
#       ...
#
# The "empty" SYNC marks the end of the previous cue. We pair adjacent SYNCs
# to derive duration and emit one .srt per language tag found.

# Class-attribute → ISO 639-1 language code mapping. The list below covers
# the names actually seen in the wild on Korean SMI sources. Unknown classes
# default to "ko" because the overwhelming majority of .smi files in this
# corpus are Korean.
_SAMI_CLASS_TO_LANG: dict[str, str] = {
    "KRCC": "ko", "KOREAN": "ko", "KO": "ko", "KOR": "ko", "KORCC": "ko",
    "KOKRCC": "ko", "KOKR": "ko",  # seen in the wild (e.g. Mashle CC).
    "ENCC": "en", "ENUSCC": "en", "ENGCC": "en", "ENGLISH": "en", "EN": "en",
    "ENG": "en", "ENUS": "en",
    "JPCC": "ja", "JPNCC": "ja", "JACC": "ja", "JAPANESE": "ja",
    "JA": "ja", "JAP": "ja", "JPN": "ja",
    "CHCC": "zh", "CHICC": "zh", "ZH": "zh", "CHINESE": "zh",
    "SPCC": "es", "SPANISH": "es", "ES": "es", "ESP": "es",
}


def _sami_decode_bytes(data: bytes) -> str:
    """Try a sequence of plausible encodings for SAMI files. Falls back to
    Latin-1 with replacement so we always return something.

    Order matters: UTF-16 will happily decode any even-length byte string,
    so we only try it when a real BOM is present. Korean SAMI files are
    overwhelmingly CP949 (superset of EUC-KR), so it goes before any
    last-resort decode."""
    # BOM-gated UTF-16 first — covers the rarer Korean editor exports.
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    # UTF-8 (with optional BOM) — the modern default.
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    # CP949 covers the bulk of older Korean SAMI files.
    try:
        return data.decode("cp949")
    except UnicodeDecodeError:
        pass
    return data.decode("latin-1", errors="replace")


_SAMI_ENTITY_RE = re.compile(r"&(?:#(\d+)|#x([0-9a-fA-F]+)|([a-zA-Z]+));")
_SAMI_NAMED_ENTITIES: dict[str, str] = {
    "nbsp": " ", "amp": "&", "lt": "<", "gt": ">",
    "quot": '"', "apos": "'",
}


def _sami_decode_entities(text: str) -> str:
    def replace(m: "re.Match[str]") -> str:
        dec, hex_, name = m.group(1), m.group(2), m.group(3)
        try:
            if dec is not None:
                return chr(int(dec))
            if hex_ is not None:
                return chr(int(hex_, 16))
            if name and name.lower() in _SAMI_NAMED_ENTITIES:
                return _SAMI_NAMED_ENTITIES[name.lower()]
        except (ValueError, OverflowError):
            pass
        return m.group(0)
    return _SAMI_ENTITY_RE.sub(replace, text)


_SAMI_TAG_RE = re.compile(r"<[^>]+>")
_SAMI_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def _sami_normalize_text(raw: str) -> str:
    """Convert SAMI cue HTML into plain SRT text. <br> → newline, then strip
    all other tags, then decode entities, then collapse whitespace per line.
    Returns empty string for cues that contain only whitespace/nbsp."""
    text = _SAMI_BR_RE.sub("\n", raw)
    text = _SAMI_TAG_RE.sub("", text)
    text = _sami_decode_entities(text)
    # Drop ALL empty lines (including internal ones) — multi-<br> in SAMI is
    # a vertical-spacing convention that, if preserved, would corrupt the SRT
    # output (blank lines inside a cue body are parsed as cue separators by
    # most SRT readers).
    lines: list[str] = []
    for line in text.split("\n"):
        line = line.replace(" ", " ")
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


_SAMI_SYNC_RE = re.compile(r"<\s*SYNC\b([^>]*)>", re.IGNORECASE)
_SAMI_START_RE = re.compile(r"\bSTART\s*=\s*\"?(-?\d+)\"?", re.IGNORECASE)
# Within a SYNC, P tags either run to the next P, the next SYNC, or EOF.
_SAMI_P_RE = re.compile(
    r"<\s*P\b([^>]*)>(.*?)(?=<\s*P\b|<\s*SYNC\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_SAMI_CLASS_RE = re.compile(r"\bCLASS\s*=\s*\"?([A-Za-z0-9_-]+)\"?", re.IGNORECASE)
_SAMI_BODY_RE = re.compile(
    r"<\s*BODY\b[^>]*>(.*?)(?:<\s*/\s*BODY\b|$)",
    re.IGNORECASE | re.DOTALL,
)


def parse_sami(text: str) -> dict[str, list[tuple[int, int, str]]]:
    """Parse SAMI body. Returns {lang_code: [(start_ms, end_ms, text), ...]}.

    Cues are emitted in source order. Adjacent SYNCs determine duration; a
    SYNC whose text is empty (or only &nbsp;) marks the end of the previous
    cue and is not emitted itself. The final cue, if not closed by an empty
    SYNC, gets a 3-second fallback duration."""
    body_match = _SAMI_BODY_RE.search(text)
    body = body_match.group(1) if body_match else text

    syncs: list[tuple[int, str]] = []
    matches = list(_SAMI_SYNC_RE.finditer(body))
    for idx, m in enumerate(matches):
        start_attr = _SAMI_START_RE.search(m.group(1))
        if not start_attr:
            continue
        try:
            start_ms = int(start_attr.group(1))
        except ValueError:
            continue
        if start_ms < 0:
            continue
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        content = body[m.end():end_pos]
        syncs.append((start_ms, content))

    raw_cues: list[tuple[int, dict[str, str]]] = []
    for start_ms, content in syncs:
        lang_text: dict[str, str] = {}
        p_matches = list(_SAMI_P_RE.finditer(content))
        if p_matches:
            for pm in p_matches:
                cls_match = _SAMI_CLASS_RE.search(pm.group(1))
                cls = cls_match.group(1).upper() if cls_match else ""
                lang = _SAMI_CLASS_TO_LANG.get(cls, "ko")
                normalized = _sami_normalize_text(pm.group(2))
                # Multiple <P> tags for same lang in one SYNC: join with \n.
                if lang in lang_text:
                    combined = (lang_text[lang] + "\n" + normalized).strip("\n")
                    lang_text[lang] = combined
                else:
                    lang_text[lang] = normalized
        else:
            # SAMI files without <P> tags do exist; treat whole content as ko.
            lang_text["ko"] = _sami_normalize_text(content)
        raw_cues.append((start_ms, lang_text))

    by_lang: dict[str, list[tuple[int, int, str]]] = {}
    for i, (start_ms, lang_text) in enumerate(raw_cues):
        next_start = raw_cues[i + 1][0] if i + 1 < len(raw_cues) else start_ms + 3000
        for lang, body_text in lang_text.items():
            if not body_text:
                # Empty-text SYNCs are end-markers; skip emission.
                continue
            by_lang.setdefault(lang, []).append((start_ms, next_start, body_text))

    return by_lang


def _format_srt_timestamp(ms: int) -> str:
    if ms < 0:
        ms = 0
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_part = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"


def sami_cues_to_srt(cues: list[tuple[int, int, str]]) -> str:
    """Serialize (start_ms, end_ms, text) tuples to SRT text. Sorts by start
    time and ensures end > start with a 1-second fallback."""
    sorted_cues = sorted(cues, key=lambda c: (c[0], c[1]))
    blocks: list[str] = []
    for idx, (start_ms, end_ms, body) in enumerate(sorted_cues, start=1):
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        blocks.append(
            f"{idx}\n"
            f"{_format_srt_timestamp(start_ms)} --> {_format_srt_timestamp(end_ms)}\n"
            f"{body}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def scan_smi_files(paths: list[Path]) -> list[Path]:
    """Walk paths (files or directories) and return discovered .smi files,
    sorted and deduplicated. Case-insensitive on the extension."""
    discovered: list[Path] = []
    for root in paths:
        if root.is_file():
            if root.suffix.lower() == ".smi":
                discovered.append(root)
        elif root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() == ".smi":
                    discovered.append(p)
    return sorted(set(discovered))


_SMI_KNOWN_LANG_INFIX_RE = re.compile(
    r"\.(" + "|".join(sorted(set(_SAMI_CLASS_TO_LANG.values()))) + r")$",
    re.IGNORECASE,
)


def _smi_output_stem(smi_path: Path) -> Path:
    """Compute the SRT output stem for a .smi file. Strips any existing
    .<lang> token from the filename so Show.ko.smi → Show (not Show.ko)."""
    stem = smi_path.with_suffix("")
    m = _SMI_KNOWN_LANG_INFIX_RE.search(stem.name)
    if m:
        return stem.with_name(stem.name[: m.start()])
    return stem


def parse_convert_spec(value: str | None) -> tuple[str | None, set[str] | None]:
    """Parse modify --convert.

    Accepted:
      smi-to-srt        -> convert every SAMI language stream
      ko:smi-to-srt     -> convert only Korean streams (kr alias accepted)
      ko,en:smi-to-srt  -> convert only Korean and English streams
    """
    if not value:
        return None, None
    raw = str(value).strip().lower()
    if raw == "none":
        return None, None
    if ":" not in raw:
        op = raw
        langs = None
    else:
        lang_part, _, op = raw.rpartition(":")
        langs = {
            _normalize_lang_code(part)
            for part in re.split(r"[,|]", lang_part)
            if part.strip()
        }
        if not langs:
            raise CliError(f"--convert: empty language scope in {value!r}")
    if op != "smi-to-srt":
        raise CliError("--convert: supported values are smi-to-srt or LANG:smi-to-srt")
    return op, langs


def convert_smi_file(
    smi_path: Path,
    *,
    force: bool = False,
    only_langs: set[str] | None = None,
) -> tuple[list[Path], list[Path]]:
    """Convert one SMI file to one or more sibling .srt files.

    Returns (written, skipped). `skipped` contains target paths that already
    existed and would have been overwritten without --force. Raises CliError
    if the file has no parseable cues at all."""
    data = smi_path.read_bytes()
    text = _sami_decode_bytes(data)
    by_lang = parse_sami(text)
    if not by_lang:
        raise CliError(f"{smi_path.name}: no parseable SAMI cues")
    stem = _smi_output_stem(smi_path)
    written: list[Path] = []
    skipped: list[Path] = []
    for lang, cues in sorted(by_lang.items()):
        if only_langs is not None and lang not in only_langs:
            continue
        out_path = stem.with_name(stem.name + f".{lang}.srt")
        if out_path.exists() and not force:
            skipped.append(out_path)
            continue
        out_path.write_text(sami_cues_to_srt(cues), encoding="utf-8")
        written.append(out_path)
    if only_langs is not None and not written and not skipped:
        wanted = ",".join(sorted(only_langs))
        raise CliError(f"{smi_path.name}: no SAMI cues found for requested language scope ({wanted})")
    return written, skipped


def furigana_suffix(mode: str, kind: str, single_line: bool) -> str:
    single = ".single-line" if single_line else ""
    return f".furigana-{mode}{single}.{kind}"


def srt_to_asbplayer_readings(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            output_blocks.append(block)
            continue
        time_line = next((ln for ln in lines if "-->" in ln), "")
        if not time_line:
            output_blocks.append(block)
            continue
        idx = lines.index(time_line)
        prefix = lines[: idx + 1]
        subtitle_lines = lines[idx + 1 :]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_readings(line, mode) for line in subtitle_lines]
        output_blocks.append("\n".join(prefix + converted))

    out = src.with_suffix("").with_name(src.with_suffix("").name + furigana_suffix(mode, "asb.srt", single_line))
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_ruby_vtt(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = ["WEBVTT"]
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        time_line = lines[0].replace(",", ".")
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_ruby(line, mode) for line in subtitle_lines if line.strip()]
        if not converted:
            continue
        output_blocks.append("\n".join([time_line] + converted))

    out = src.with_suffix("").with_name(src.with_suffix("").name + furigana_suffix(mode, "ruby.vtt", single_line))
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def reading_only(text: str, mode: str) -> str:
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    # Remove existing parenthetical readings so the reading line does not repeat them.
    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if surface and reading and surface != reading and has_kanji(surface):
            chunks.append(reading)
        elif surface.strip():
            chunks.append("　" if has_kanji(surface) else surface)
        else:
            chunks.append(surface)
    return "".join(chunks).strip()


KANA_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30faー]+")


def kana_to_hiragana(text: str) -> str:
    converted = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            converted.append(chr(code - 0x60))
        else:
            converted.append(ch)
    return "".join(converted)


def display_cells(text: str) -> int:
    """Approximate subtitle display width in mono-cell units.

    Japanese glyphs and full-width punctuation usually render twice as wide as
    Latin text. Counting cells instead of Python characters keeps stacked SRT
    furigana rows much closer to the kanji they annotate.
    """
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def visual_blank_cells(cells: int) -> str:
    if cells <= 0:
        return ""
    return "　" * (cells // 2) + (" " if cells % 2 else "")


def center_in_cells(text: str, cells: int) -> str:
    text_width = display_cells(text)
    if text_width >= cells:
        return text
    left = (cells - text_width) // 2
    right = cells - text_width - left
    return f"{visual_blank_cells(left)}{text}{visual_blank_cells(right)}"


def visible_blank(text: str) -> str:
    return visual_blank_cells(max(1, display_cells(text)))


def trim_kana_affixes_from_reading(surface: str, reading: str) -> tuple[str, str, str]:
    prefix = ""
    suffix = ""
    prefix_match = KANA_RE.match(surface)
    if prefix_match:
        prefix = prefix_match.group(0)
        prefix_hira = kana_to_hiragana(prefix)
        if reading.startswith(prefix_hira):
            reading = reading[len(prefix_hira) :]

    suffix_match = KANA_RE.search(surface)
    for match in KANA_RE.finditer(surface):
        suffix_match = match
    if suffix_match and suffix_match.end() == len(surface):
        suffix = suffix_match.group(0)
        suffix_hira = kana_to_hiragana(suffix)
        if reading.endswith(suffix_hira):
            reading = reading[: -len(suffix_hira)]

    return prefix, reading, suffix


def kanji_reading_line(text: str, mode: str) -> str:
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    if mode == "romaji":
        return japanese_full_sentence_reading(text, mode)

    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    chunks = []
    has_reading = False
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if surface and reading and surface != reading and has_kanji(surface):
            prefix, kanji_reading, suffix = trim_kana_affixes_from_reading(surface, reading)
            chunks.append(visible_blank(prefix) if prefix else "")
            chunks.append(kanji_reading or visible_blank(surface))
            chunks.append(visible_blank(suffix) if suffix else "")
            has_reading = True
        elif surface:
            chunks.append(visible_blank(surface))
    return "".join(chunks) if has_reading else ""


def kanji_reading_pair_lines(text: str, mode: str) -> tuple[str, str] | None:
    """Return (reading_row, text_row) for stacked SRT furigana.

    The two rows are built from the same visual-width fields. This costs a bit
    of natural spacing in the Japanese text when a reading is wider than its
    kanji surface, but it greatly reduces drift in centered SRT renderers.
    """
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help reading"
        ) from e

    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    reading_chunks: list[str] = []
    text_chunks: list[str] = []
    has_reading = False
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get(_pykakasi_reading_key(mode), "")
        if not surface:
            continue
        if reading and reading != surface and has_kanji(surface):
            prefix, kanji_reading, suffix = trim_kana_affixes_from_reading(surface, reading)
            fields: list[tuple[str, str]] = []
            if prefix:
                fields.append(("", prefix))
            fields.append((kanji_reading, surface[len(prefix): len(surface) - len(suffix) if suffix else len(surface)] or surface))
            if suffix:
                fields.append(("", suffix))
            for field_reading, field_text in fields:
                cells = max(display_cells(field_reading), display_cells(field_text))
                reading_chunks.append(center_in_cells(field_reading, cells) if field_reading else visual_blank_cells(cells))
                text_chunks.append(center_in_cells(field_text, cells))
            has_reading = True
        else:
            cells = display_cells(surface)
            reading_chunks.append(visual_blank_cells(cells))
            text_chunks.append(surface)
    if not has_reading:
        return None
    return "".join(reading_chunks), "".join(text_chunks)


def strip_existing_readings(text: str) -> str:
    return EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))


def ass_time_from_srt(groups: tuple[str, ...]) -> tuple[str, str]:
    def convert(h: str, m: str, s: str, ms: str) -> str:
        cs = round(int(ms) / 10)
        sec = int(s)
        if cs >= 100:
            sec += 1
            cs = 0
        return f"{int(h)}:{int(m):02d}:{sec:02d}.{cs:02d}"

    return convert(*groups[:4]), convert(*groups[4:])


def srt_to_furigana_lines_ass(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    time_re = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d{3})\s+-->\s+(\d\d):(\d\d):(\d\d),(\d{3})")

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{ASS_FONT_NAME},{ASS_BASE_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,2,80,80,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    for block in blocks:
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            continue
        m = time_re.match(lines[0].strip())
        if not m:
            continue
        subtitle_lines = [ln for ln in lines[1:] if ln.strip()]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        if not subtitle_lines:
            continue
        start, end = ass_time_from_srt(m.groups())
        body_lines = []
        for line in subtitle_lines:
            clean = strip_existing_readings(line)
            reading = kanji_reading_line(line, mode)
            if reading and has_kanji(clean):
                body_lines.append(r"{\fs" + str(ASS_FURIGANA_FONT_SIZE) + r"\fscx" + str(ASS_FURIGANA_SCALE_X) + "}" + ass_escape(reading))
            body_lines.append(r"{\fs" + str(ASS_BASE_FONT_SIZE) + r"\fscx100}" + ass_escape(clean))
        text_body = r"\N".join(body_lines)
        dialogues.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text_body}")

    out = src.with_suffix("").with_name(src.with_suffix("").name + furigana_suffix(mode, "lines.ass", single_line))
    out.write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    return out


ALLOWED_FURIGANA_FORMATS = ("srt", "ass", "vtt")


def parse_furigana_formats(value: str | None) -> set[str]:
    """Parse --reading-format (or [modify].reading_format) into a set of format codes.

    Accepts:
      None / empty      -> {"srt"}            (default — most reliable / asbplayer)
      "srt"             -> {"srt"}
      "srt,ass"         -> {"srt", "ass"}
      "srt,ass,vtt"     -> {"srt", "ass", "vtt"}
      "all"             -> all three

    Raises CliError for unknown format codes."""
    if not value:
        return {"srt"}
    text = value.strip().lower()
    if not text:
        return {"srt"}
    if text == "all":
        return set(ALLOWED_FURIGANA_FORMATS)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    unknown = [p for p in parts if p not in ALLOWED_FURIGANA_FORMATS]
    if unknown:
        raise CliError(
            f"--reading-format: unknown format(s): {', '.join(unknown)}. "
            "Allowed: srt, ass, vtt, all (comma-list ok). "
            "See: getsubtitle --help reading"
        )
    return set(parts)


# ═══════════════════════════════════════════════════════════════════════
# Korean romanization
# ═══════════════════════════════════════════════════════════════════════
# Mirror of the Japanese furigana code path, but with Korean linguistics:
#   • G2P (g2pk) preprocesses hangul into pronounced form before romanizing
#       같이 (gat-i)   → 가치 (gachi)     palatalization
#       읽는 (ilg-neun) → 잉는 (ingneun)  nasal assimilation
#       한국어 (han-guk-eo) → 한구거 (hangugeo)  linking sounds
#     Without G2P we still produce something, but edge cases drift.
#   • Revised Romanization (the South Korean standard) is the default mode;
#     Yale (academic) is offered as an alternative and doesn't need G2P
#     because Yale is orthographic, not phonological.
#   • Display surface = romaji-style chunks per eojeol (whitespace-delimited
#     word). Each chunk feeds the same per-format renderers used by ja
#     (parenthetical SRT, ruby VTT, stacked ASS).

# Hangul Syllables block (가–힣). Plus Jamo (ᄀ–ᇿ) for the rare decomposed cue.
_HANGUL_RE = re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏]")


def has_hangul(text: str) -> bool:
    """True iff text contains any Hangul character (syllable or jamo)."""
    return bool(_HANGUL_RE.search(text))


# Cached engine instances — both libraries do non-trivial init (g2pk
# loads a corpus, korean-romanizer compiles rule tables). Building each
# instance once per process keeps the per-cue cost low.
_KOREAN_G2P_CACHE: object | None = None
_KOREAN_G2P_TRIED: bool = False
_KOREAN_ROMANIZER_CLS: object | None = None


def _korean_g2p_or_none() -> object | None:
    """Return a cached `g2pk.G2p` instance, or None if g2pk isn't installed.
    Treated as a soft dep — output quality drops without it, but ko
    romanization still runs."""
    global _KOREAN_G2P_CACHE, _KOREAN_G2P_TRIED
    if _KOREAN_G2P_TRIED:
        return _KOREAN_G2P_CACHE
    _KOREAN_G2P_TRIED = True
    try:
        import g2pk  # type: ignore
        _KOREAN_G2P_CACHE = g2pk.G2p()
    except Exception:
        _KOREAN_G2P_CACHE = None
    return _KOREAN_G2P_CACHE


def _korean_revised_romanizer_class() -> object:
    """Return korean-romanizer's `Romanizer` class. Hard dep — raises
    CliError if missing because Revised Romanization is the default mode
    and we have no in-tree fallback for the full ruleset."""
    global _KOREAN_ROMANIZER_CLS
    if _KOREAN_ROMANIZER_CLS is not None:
        return _KOREAN_ROMANIZER_CLS
    try:
        from korean_romanizer.romanizer import Romanizer  # type: ignore
    except Exception as e:
        raise CliError(
            "Korean Revised Romanization needs the korean-romanizer package.\n"
            "  Quick install: python3 -m pip install korean-romanizer\n"
            "  Recommended (best accuracy): pip install -e \".[romanization-ko]\"\n"
            "    — also installs g2pk for grapheme-to-phoneme preprocessing,\n"
            "    which handles palatalization (같이→가치) and nasal assimilation.\n"
            "  See: getsubtitle --help reading"
        ) from e
    _KOREAN_ROMANIZER_CLS = Romanizer
    return _KOREAN_ROMANIZER_CLS


# ── Yale romanization (in-tree, no external deps) ──────────────────────
# Yale is orthographic — it maps jamo directly to roman letters with no
# pronunciation rules. Useful for linguists and historical Korean. The
# canonical Yale table per Martin (1992).
_YALE_INITIAL: dict[str, str] = {
    "ᄀ": "k", "ᄁ": "kk", "ᄂ": "n", "ᄃ": "t", "ᄄ": "tt", "ᄅ": "l",
    "ᄆ": "m", "ᄇ": "p", "ᄈ": "pp", "ᄉ": "s", "ᄊ": "ss", "ᄋ": "",
    "ᄌ": "c", "ᄍ": "cc", "ᄎ": "ch", "ᄏ": "kh", "ᄐ": "th", "ᄑ": "ph",
    "ᄒ": "h",
}
_YALE_VOWEL: dict[str, str] = {
    "ᅡ": "a", "ᅢ": "ay", "ᅣ": "ya", "ᅤ": "yay", "ᅥ": "e", "ᅦ": "ey",
    "ᅧ": "ye", "ᅨ": "yey", "ᅩ": "o", "ᅪ": "wa", "ᅫ": "way", "ᅬ": "oy",
    "ᅭ": "yo", "ᅮ": "wu", "ᅯ": "we", "ᅰ": "wey", "ᅱ": "wi", "ᅲ": "yu",
    "ᅳ": "u", "ᅴ": "uy", "ᅵ": "i",
}
_YALE_FINAL: dict[str, str] = {
    "": "", "ᆨ": "k", "ᆩ": "kk", "ᆪ": "ks", "ᆫ": "n", "ᆬ": "nc",
    "ᆭ": "nh", "ᆮ": "t", "ᆯ": "l", "ᆰ": "lk", "ᆱ": "lm", "ᆲ": "lp",
    "ᆳ": "ls", "ᆴ": "lth", "ᆵ": "lph", "ᆶ": "lh", "ᆷ": "m", "ᆸ": "p",
    "ᆹ": "ps", "ᆺ": "s", "ᆻ": "ss", "ᆼ": "ng", "ᆽ": "c", "ᆾ": "ch",
    "ᇀ": "th", "ᇁ": "ph", "ᇂ": "h",
}


def _romanize_yale(text: str) -> str:
    """Direct orthographic Yale romanization. Decomposes each Hangul
    syllable into jamo via Unicode NFD, looks each up in the table,
    re-joins as ASCII. Non-Hangul passes through unchanged."""
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3:
            # Hangul syllable — decompose into (initial, vowel, final).
            syl = cp - 0xAC00
            final_idx = syl % 28
            vowel_idx = (syl // 28) % 21
            initial_idx = syl // (28 * 21)
            initial = chr(0x1100 + initial_idx)
            vowel = chr(0x1161 + vowel_idx)
            final = chr(0x11A7 + final_idx) if final_idx > 0 else ""
            out.append(
                _YALE_INITIAL.get(initial, "")
                + _YALE_VOWEL.get(vowel, "")
                + _YALE_FINAL.get(final, "")
            )
        else:
            out.append(ch)
    return "".join(out)


def _romanize_revised(text: str) -> str:
    """Revised Romanization with optional G2P preprocessing.

    G2P (when available) converts hangul into pronounced form so the
    romanizer sees `가치` instead of `같이`; the romanizer then emits
    `gachi` correctly. Without G2P the romanizer still runs but treats
    `같이` orthographically and emits `gat-i`."""
    g2p = _korean_g2p_or_none()
    source = g2p(text) if g2p is not None else text
    Romanizer = _korean_revised_romanizer_class()
    return Romanizer(source).romanize()


def romanize_korean(text: str, mode: str) -> str:
    """Top-level Korean romanizer. `mode` is one of:
        revised  — South Korean official standard (Revised Romanization)
        yale     — academic / linguistic (Yale Romanization, no G2P)
    Returns the romanized form of `text`; non-Hangul passes through."""
    if mode == "revised":
        return _romanize_revised(text)
    if mode == "yale":
        return _romanize_yale(text)
    raise CliError(
        f"Unknown Korean romanization mode {mode!r}. "
        "Allowed: revised, yale."
    )


# ── Line / chunk helpers (mirror the ja text_with_* surface) ──────────

def _korean_pair_chunks(text: str, mode: str) -> list[tuple[str, str]]:
    """Split text on whitespace and return (hangul, romaji) pairs.

    Each whitespace run is preserved as its own chunk so the renderer
    can keep word boundaries intact. Non-Hangul tokens (punctuation,
    latin words, digits) emit (text, text) so the renderer can decide
    whether to annotate them."""
    chunks: list[tuple[str, str]] = []
    text = strip_subtitle_markup(text)
    parts = re.split(r"(\s+)", text)
    for part in parts:
        if not part:
            continue
        if part.isspace():
            chunks.append((part, part))
            continue
        if has_hangul(part):
            chunks.append((part, romanize_korean(part, mode)))
        else:
            chunks.append((part, part))
    return chunks


def text_with_korean_readings(text: str, mode: str) -> str:
    """SRT-flavoured inline parentheticals: 한국어를（hangugeoreul）.
    Mirror of `text_with_readings` for Japanese."""
    chunks = _korean_pair_chunks(text, mode)
    out: list[str] = []
    for hangul, roman in chunks:
        if has_hangul(hangul) and roman and roman != hangul:
            out.append(f"{hangul}（{roman}）")
        else:
            out.append(hangul)
    return "".join(out)


def text_with_korean_ruby(text: str, mode: str) -> str:
    """VTT ruby markup per eojeol: <ruby>한국어<rt>hangugeo</rt></ruby>.
    Mirror of `text_with_ruby` for Japanese."""
    chunks = _korean_pair_chunks(text, mode)
    out: list[str] = []
    for hangul, roman in chunks:
        if has_hangul(hangul) and roman and roman != hangul:
            out.append(ruby_tag(hangul, roman))
        elif hangul.isspace():
            out.append(hangul)
        else:
            out.append(html_escape(hangul))
    return "".join(out)


def hangul_reading_pair_lines(text: str, mode: str) -> tuple[str, str] | None:
    """Return (reading_row, text_row) for stacked SRT/ASS Korean rows.
    Mirror of `kanji_reading_pair_lines`. Returns None if there's no
    Hangul to annotate."""
    chunks = _korean_pair_chunks(text, mode)
    if not any(has_hangul(h) for h, _ in chunks):
        return None
    reading_chunks: list[str] = []
    text_chunks: list[str] = []
    has_reading = False
    for hangul, roman in chunks:
        if has_hangul(hangul) and roman and roman != hangul:
            cells = max(display_cells(hangul), display_cells(roman))
            reading_chunks.append(center_in_cells(roman, cells))
            text_chunks.append(center_in_cells(hangul, cells))
            has_reading = True
        else:
            cells = display_cells(hangul)
            reading_chunks.append(visual_blank_cells(cells))
            text_chunks.append(hangul)
    return ("".join(reading_chunks), "".join(text_chunks)) if has_reading else None


# ── Per-format side-file generators (mirror srt_to_* for ja) ───────────

def romanization_suffix(lang: str, mode: str, kind: str, single_line: bool) -> str:
    """Generalised filename infix for reading-aid side files.

    Japanese keeps the historical `.furigana-{mode}` infix for backward
    compatibility with scanners and downstream tools. Other languages
    use `.romanization-{mode}` so filenames advertise the script."""
    single = ".single-line" if single_line else ""
    if lang == "ja":
        return f".furigana-{mode}{single}.{kind}"
    return f".romanization-{mode}{single}.{kind}"


def srt_to_korean_readings(src: Path, mode: str, single_line: bool = False) -> Path:
    """SRT side file with inline parenthetical romanization per eojeol.
    Mirror of `srt_to_asbplayer_readings` — same block-by-block structure."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            output_blocks.append(block)
            continue
        time_line = next((ln for ln in lines if "-->" in ln), "")
        if not time_line:
            output_blocks.append(block)
            continue
        idx = lines.index(time_line)
        prefix = lines[: idx + 1]
        subtitle_lines = lines[idx + 1 :]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_korean_readings(line, mode) for line in subtitle_lines]
        output_blocks.append("\n".join(prefix + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("ko", mode, "asb.srt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_korean_ruby_vtt(src: Path, mode: str, single_line: bool = False) -> Path:
    """VTT side file with `<ruby>` markup per eojeol. Mirror of
    `srt_to_ruby_vtt`."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = ["WEBVTT"]
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        time_line = lines[0].replace(",", ".")
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_korean_ruby(line, mode) for line in subtitle_lines if line.strip()]
        if not converted:
            continue
        output_blocks.append("\n".join([time_line] + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("ko", mode, "ruby.vtt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_korean_pair_lines_ass(src: Path, mode: str, single_line: bool = False) -> Path:
    """ASS stacked side file (top: romaji row, bottom: hangul row).
    Mirror of `srt_to_furigana_lines_ass`."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    time_re = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d{3})\s+-->\s+(\d\d):(\d\d):(\d\d),(\d{3})")

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, Italic, Outline, Alignment, MarginV
Style: Reading, Arial, 36, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 60
Style: Text, Arial, 48, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 20

[Events]
Format: Layer, Start, End, Style, Text
"""
    events: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        m = time_re.match(lines[0])
        if not m:
            continue
        start, end = ass_time_from_srt(m.groups())
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        for line in subtitle_lines:
            if not line.strip():
                continue
            pair = hangul_reading_pair_lines(line, mode)
            if pair is None:
                events.append(f"Dialogue: 0,{start},{end},Text,{line}")
                continue
            reading_row, text_row = pair
            events.append(f"Dialogue: 0,{start},{end},Text,{text_row}")
            events.append(f"Dialogue: 0,{start},{end},Reading,{reading_row}")

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("ko", mode, "stacked.ass", single_line)
    )
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out


def generate_korean_romanization(
    paths: Iterable[Path],
    mode: str,
    single_line: bool = False,
    formats: set[str] | None = None,
) -> list[Path]:
    """Orchestrator — mirrors `generate_furigana` but scans `.ko.srt` files.
    Each path yields up to three side files depending on `formats`."""
    if formats is None:
        formats = {"srt"}
    generated: list[Path] = []
    for path in paths:
        if ".ko" not in path.name:
            continue
        if path.suffix.lower() != ".srt":
            continue
        if "srt" in formats:
            generated.append(srt_to_korean_readings(path, mode, single_line))
        if "vtt" in formats:
            generated.append(srt_to_korean_ruby_vtt(path, mode, single_line))
        if "ass" in formats:
            generated.append(srt_to_korean_pair_lines_ass(path, mode, single_line))
    return generated


def apply_korean_ruby(cues, mode: str) -> None:
    """Mirror of `apply_japanese_ruby`: inline VTT ruby markup into Korean
    cues in place, for the merge subcommand's VTT output."""
    for cue in cues:
        cue.text_lines = [text_with_korean_ruby(line, mode) for line in cue.text_lines]


# ═══════════════════════════════════════════════════════════════════════
# Chinese (Mandarin) romanization — pinyin
# ═══════════════════════════════════════════════════════════════════════
# Mirror of the Korean code path with Mandarin specifics:
#   • pypinyin handles per-character pinyin lookup, polyphones, and built-in
#     tone sandhi. No G2P split is needed (Mandarin pronunciation maps from
#     hanzi more directly than Korean hangul → pronounced form does).
#   • Two output styles live under one knob:
#       zh:marks   → nǐ hǎo shì jiè    (tone marks above vowels — default)
#       zh:numbers → ni3 hao3 shi4 jie4 (numbered tones — IME-friendly)
#       zh:letters → ni hao shi jie    (no tones — accessible / beginner)
#   • Word boundaries: pypinyin emits one pinyin syllable per character.
#     We group consecutive hanzi runs into one chunk so SRT inline
#     parentheticals stay readable (`你好（nǐ hǎo）` instead of
#     `你（nǐ）好（hǎo）`). VTT ruby is per-run too, with syllables
#     joined by spaces inside <rt>.

# CJK Unified Ideographs (4E00–9FFF) plus Extension-A (3400–4DBF). Excludes
# Hiragana and Hangul (those are handled by their own modules) but does
# overlap with Japanese kanji — that's expected because the same script is
# shared. The pipeline only invokes this branch when the file is tagged ko/
# /zh in its filename, so cross-language confusion isn't a risk.
_HANZI_RE = re.compile(r"[㐀-䶿一-鿿]")


def has_hanzi(text: str) -> bool:
    """True iff text contains any CJK Unified ideograph (hanzi/kanji)."""
    return bool(_HANZI_RE.search(text))


_PYPINYIN_MODULE: object | None = None


def _pypinyin_module() -> object:
    """Return the cached `pypinyin` module, or raise CliError if missing.
    pypinyin builds its dictionary at import time (~50ms), so we cache it."""
    global _PYPINYIN_MODULE
    if _PYPINYIN_MODULE is not None:
        return _PYPINYIN_MODULE
    try:
        import pypinyin  # type: ignore
    except Exception as e:
        raise CliError(
            "Chinese pinyin needs the pypinyin package.\n"
            "  Quick install: python3 -m pip install pypinyin\n"
            "  Or reinstall with the extra: pip install -e \".[romanization-zh]\"\n"
            "  See: getsubtitle --help reading"
        ) from e
    _PYPINYIN_MODULE = pypinyin
    return _PYPINYIN_MODULE


def _pypinyin_style_for(mode: str) -> object:
    """Map our public mode names onto pypinyin's Style enum.
    Encapsulated so tests can mock pypinyin without knowing the enum."""
    py = _pypinyin_module()
    if mode == "marks":
        return py.Style.TONE      # nǐ hǎo
    if mode == "numbers":
        return py.Style.TONE3     # ni3 hao3
    if mode == "letters":
        return py.Style.NORMAL    # ni hao
    raise CliError(
        f"Unknown Chinese romanization mode {mode!r}. "
        "Allowed: marks, numbers, letters."
    )


def romanize_chinese(text: str, mode: str) -> str:
    """Top-level Mandarin romanizer. Returns pinyin syllables separated
    by single spaces. Non-hanzi characters pass through verbatim, which
    keeps mixed content (e.g. punctuation, Latin words, numerals) intact."""
    if not has_hanzi(text):
        return text
    style = _pypinyin_style_for(mode)
    py = _pypinyin_module()
    # lazy_pinyin returns one string per character. errors='default' keeps
    # non-hanzi characters as-is (instead of replacing with '?').
    syllables = py.lazy_pinyin(text, style=style, errors="default")
    # Re-stitch: every original character maps to one element in `syllables`.
    # Hanzi → its pinyin syllable; non-hanzi → the original character.
    # We insert a single space between adjacent hanzi syllables so the
    # output reads as words, not concatenated phonemes.
    out: list[str] = []
    chars = list(text)
    for i, ch in enumerate(chars):
        is_hanzi = bool(_HANZI_RE.match(ch))
        prev_is_hanzi = i > 0 and bool(_HANZI_RE.match(chars[i - 1]))
        if is_hanzi and prev_is_hanzi:
            out.append(" ")
        out.append(syllables[i] if i < len(syllables) else ch)
    return "".join(out)


# ── Line / chunk helpers (mirror the ko text_with_* surface) ──────────

def _chinese_pair_chunks(text: str, mode: str) -> list[tuple[str, str]]:
    """Split text into (hanzi_run, pinyin) pairs.

    Each maximal run of consecutive hanzi characters becomes one chunk;
    each run of non-hanzi (whitespace, punctuation, Latin) becomes its
    own passthrough chunk. This gives one parenthetical / ruby block per
    word-like unit rather than per character."""
    chunks: list[tuple[str, str]] = []
    text = strip_subtitle_markup(text)
    # Build runs by walking characters and grouping by hanzi-ness.
    buf: list[str] = []
    is_hanzi_run: bool | None = None
    for ch in text:
        ch_is_hanzi = bool(_HANZI_RE.match(ch))
        if is_hanzi_run is None:
            is_hanzi_run = ch_is_hanzi
            buf.append(ch)
            continue
        if ch_is_hanzi == is_hanzi_run:
            buf.append(ch)
        else:
            run = "".join(buf)
            if is_hanzi_run:
                chunks.append((run, romanize_chinese(run, mode)))
            else:
                chunks.append((run, run))
            buf = [ch]
            is_hanzi_run = ch_is_hanzi
    if buf:
        run = "".join(buf)
        if is_hanzi_run:
            chunks.append((run, romanize_chinese(run, mode)))
        else:
            chunks.append((run, run))
    return chunks


def text_with_chinese_readings(text: str, mode: str) -> str:
    """SRT-flavoured inline parentheticals: 你好（nǐ hǎo）世界（shì jiè）.
    Mirror of `text_with_korean_readings`."""
    chunks = _chinese_pair_chunks(text, mode)
    out: list[str] = []
    for hanzi, pinyin in chunks:
        if has_hanzi(hanzi) and pinyin and pinyin != hanzi:
            out.append(f"{hanzi}（{pinyin}）")
        else:
            out.append(hanzi)
    return "".join(out)


def text_with_chinese_ruby(text: str, mode: str) -> str:
    """VTT ruby markup per hanzi run: <ruby>你好<rt>nǐ hǎo</rt></ruby>.
    Mirror of `text_with_korean_ruby`."""
    chunks = _chinese_pair_chunks(text, mode)
    out: list[str] = []
    for hanzi, pinyin in chunks:
        if has_hanzi(hanzi) and pinyin and pinyin != hanzi:
            out.append(ruby_tag(hanzi, pinyin))
        elif hanzi.isspace():
            out.append(hanzi)
        else:
            out.append(html_escape(hanzi))
    return "".join(out)


def hanzi_reading_pair_lines(text: str, mode: str) -> tuple[str, str] | None:
    """Return (reading_row, text_row) for stacked SRT/ASS Chinese rows.
    Mirror of `hangul_reading_pair_lines`. Returns None if no hanzi."""
    chunks = _chinese_pair_chunks(text, mode)
    if not any(has_hanzi(h) for h, _ in chunks):
        return None
    reading_chunks: list[str] = []
    text_chunks: list[str] = []
    has_reading = False
    for hanzi, pinyin in chunks:
        if has_hanzi(hanzi) and pinyin and pinyin != hanzi:
            cells = max(display_cells(hanzi), display_cells(pinyin))
            reading_chunks.append(center_in_cells(pinyin, cells))
            text_chunks.append(center_in_cells(hanzi, cells))
            has_reading = True
        else:
            cells = display_cells(hanzi)
            reading_chunks.append(visual_blank_cells(cells))
            text_chunks.append(hanzi)
    return ("".join(reading_chunks), "".join(text_chunks)) if has_reading else None


# ── Per-format side-file generators (mirror srt_to_korean_* for ko) ───

def srt_to_chinese_readings(src: Path, mode: str, single_line: bool = False) -> Path:
    """SRT side file with inline parenthetical pinyin per hanzi run.
    Mirror of `srt_to_korean_readings`."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            output_blocks.append(block)
            continue
        time_line = next((ln for ln in lines if "-->" in ln), "")
        if not time_line:
            output_blocks.append(block)
            continue
        idx = lines.index(time_line)
        prefix = lines[: idx + 1]
        subtitle_lines = lines[idx + 1 :]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_chinese_readings(line, mode) for line in subtitle_lines]
        output_blocks.append("\n".join(prefix + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("zh", mode, "asb.srt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_chinese_ruby_vtt(src: Path, mode: str, single_line: bool = False) -> Path:
    """VTT side file with `<ruby>` per hanzi run. Mirror of `srt_to_korean_ruby_vtt`."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = ["WEBVTT"]
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        time_line = lines[0].replace(",", ".")
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_chinese_ruby(line, mode) for line in subtitle_lines if line.strip()]
        if not converted:
            continue
        output_blocks.append("\n".join([time_line] + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("zh", mode, "ruby.vtt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_chinese_pair_lines_ass(src: Path, mode: str, single_line: bool = False) -> Path:
    """ASS stacked side file (top: pinyin row, bottom: hanzi row).
    Mirror of `srt_to_korean_pair_lines_ass`."""
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    time_re = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d{3})\s+-->\s+(\d\d):(\d\d):(\d\d),(\d{3})")

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, Italic, Outline, Alignment, MarginV
Style: Reading, Arial, 36, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 60
Style: Text, Arial, 48, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 20

[Events]
Format: Layer, Start, End, Style, Text
"""
    events: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        m = time_re.match(lines[0])
        if not m:
            continue
        start, end = ass_time_from_srt(m.groups())
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        for line in subtitle_lines:
            if not line.strip():
                continue
            pair = hanzi_reading_pair_lines(line, mode)
            if pair is None:
                events.append(f"Dialogue: 0,{start},{end},Text,{line}")
                continue
            reading_row, text_row = pair
            events.append(f"Dialogue: 0,{start},{end},Text,{text_row}")
            events.append(f"Dialogue: 0,{start},{end},Reading,{reading_row}")

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("zh", mode, "stacked.ass", single_line)
    )
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out


def generate_chinese_romanization(
    paths: Iterable[Path],
    mode: str,
    single_line: bool = False,
    formats: set[str] | None = None,
) -> list[Path]:
    """Orchestrator — mirrors `generate_korean_romanization` but scans
    `.zh.srt` files. Each path yields up to three side files depending
    on `formats`."""
    if formats is None:
        formats = {"srt"}
    generated: list[Path] = []
    for path in paths:
        if ".zh" not in path.name:
            continue
        if path.suffix.lower() != ".srt":
            continue
        if "srt" in formats:
            generated.append(srt_to_chinese_readings(path, mode, single_line))
        if "vtt" in formats:
            generated.append(srt_to_chinese_ruby_vtt(path, mode, single_line))
        if "ass" in formats:
            generated.append(srt_to_chinese_pair_lines_ass(path, mode, single_line))
    return generated


def apply_chinese_ruby(cues, mode: str) -> None:
    """Mirror of `apply_korean_ruby`: inline VTT ruby markup into Chinese
    cues in place, for the merge subcommand's VTT output."""
    for cue in cues:
        cue.text_lines = [text_with_chinese_ruby(line, mode) for line in cue.text_lines]


# ═══════════════════════════════════════════════════════════════════════
# Cantonese romanization — Jyutping
# ═══════════════════════════════════════════════════════════════════════

_PYCANTONESE_MODULE: object | None = None


def _pycantonese_module() -> object:
    """Return cached PyCantonese, or raise a user-facing install hint."""
    global _PYCANTONESE_MODULE
    if _PYCANTONESE_MODULE is not None:
        return _PYCANTONESE_MODULE
    try:
        import pycantonese  # type: ignore
    except Exception as e:
        raise CliError(
            "Cantonese Jyutping needs the pycantonese package.\n"
            "  Quick install: python3 -m pip install pycantonese\n"
            "  Or reinstall with the extra: pip install -e \".[romanization-yue]\"\n"
            "  See: getsubtitle --help reading"
        ) from e
    _PYCANTONESE_MODULE = pycantonese
    return _PYCANTONESE_MODULE


def _coerce_jyutping_items(raw) -> list[str]:
    """Normalise PyCantonese return shapes across versions.

    PyCantonese has returned simple strings in some examples and tuple-ish
    records in others. Prefer the last non-empty string in a record because
    that is where jyutping usually lives; keep this tolerant so tests can
    fake the backend without pinning one exact third-party shape.
    """
    out: list[str] = []
    for item in raw or []:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, (list, tuple)):
            strings = [str(part) for part in item if isinstance(part, str) and part]
            out.append(strings[-1] if strings else "")
            continue
        out.append(str(item) if item is not None else "")
    return out


def romanize_cantonese(text: str, mode: str) -> str:
    """Return Jyutping for a hanzi run. Modes:
        numbers — jyutping with tone numbers (default)
        marks   — accepted as an alias for numbers until a tone-mark
                  Cantonese backend is worth adding.
    """
    if mode not in ("numbers", "marks"):
        raise CliError(
            f"Unknown Cantonese romanization mode {mode!r}. "
            "Allowed: numbers, marks."
        )
    if not has_hanzi(text):
        return text
    yue = _pycantonese_module()
    try:
        raw = yue.characters_to_jyutping(text)
    except Exception as e:
        raise CliError(f"Cantonese Jyutping failed: {e}") from e
    pieces = _coerce_jyutping_items(raw)
    out: list[str] = []
    chars = list(text)
    for i, ch in enumerate(chars):
        is_hanzi = bool(_HANZI_RE.match(ch))
        prev_is_hanzi = i > 0 and bool(_HANZI_RE.match(chars[i - 1]))
        if is_hanzi and prev_is_hanzi:
            out.append(" ")
        piece = pieces[i] if i < len(pieces) else ""
        out.append(piece or ch)
    return "".join(out)


def _cantonese_pair_chunks(text: str, mode: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    text = strip_subtitle_markup(text)
    buf: list[str] = []
    is_hanzi_run: bool | None = None
    for ch in text:
        ch_is_hanzi = bool(_HANZI_RE.match(ch))
        if is_hanzi_run is None:
            is_hanzi_run = ch_is_hanzi
            buf.append(ch)
            continue
        if ch_is_hanzi == is_hanzi_run:
            buf.append(ch)
        else:
            run = "".join(buf)
            chunks.append((run, romanize_cantonese(run, mode) if is_hanzi_run else run))
            buf = [ch]
            is_hanzi_run = ch_is_hanzi
    if buf:
        run = "".join(buf)
        chunks.append((run, romanize_cantonese(run, mode) if is_hanzi_run else run))
    return chunks


def text_with_cantonese_readings(text: str, mode: str) -> str:
    chunks = _cantonese_pair_chunks(text, mode)
    out: list[str] = []
    for hanzi, jyutping in chunks:
        if has_hanzi(hanzi) and jyutping and jyutping != hanzi:
            out.append(f"{hanzi}（{jyutping}）")
        else:
            out.append(hanzi)
    return "".join(out)


def text_with_cantonese_ruby(text: str, mode: str) -> str:
    chunks = _cantonese_pair_chunks(text, mode)
    out: list[str] = []
    for hanzi, jyutping in chunks:
        if has_hanzi(hanzi) and jyutping and jyutping != hanzi:
            out.append(ruby_tag(hanzi, jyutping))
        elif hanzi.isspace():
            out.append(hanzi)
        else:
            out.append(html_escape(hanzi))
    return "".join(out)


def cantonese_reading_pair_lines(text: str, mode: str) -> tuple[str, str] | None:
    chunks = _cantonese_pair_chunks(text, mode)
    if not any(has_hanzi(h) for h, _ in chunks):
        return None
    reading_chunks: list[str] = []
    text_chunks: list[str] = []
    has_reading = False
    for hanzi, jyutping in chunks:
        if has_hanzi(hanzi) and jyutping and jyutping != hanzi:
            cells = max(display_cells(hanzi), display_cells(jyutping))
            reading_chunks.append(center_in_cells(jyutping, cells))
            text_chunks.append(center_in_cells(hanzi, cells))
            has_reading = True
        else:
            cells = display_cells(hanzi)
            reading_chunks.append(visual_blank_cells(cells))
            text_chunks.append(hanzi)
    return ("".join(reading_chunks), "".join(text_chunks)) if has_reading else None


def srt_to_cantonese_readings(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            output_blocks.append(block)
            continue
        time_line = next((ln for ln in lines if "-->" in ln), "")
        if not time_line:
            output_blocks.append(block)
            continue
        idx = lines.index(time_line)
        prefix = lines[: idx + 1]
        subtitle_lines = lines[idx + 1 :]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_cantonese_readings(line, mode) for line in subtitle_lines]
        output_blocks.append("\n".join(prefix + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("yue", mode, "asb.srt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_cantonese_ruby_vtt(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    output_blocks = ["WEBVTT"]
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        time_line = lines[0].replace(",", ".")
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        converted = [text_with_cantonese_ruby(line, mode) for line in subtitle_lines if line.strip()]
        if converted:
            output_blocks.append("\n".join([time_line] + converted))

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("yue", mode, "ruby.vtt", single_line)
    )
    out.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")
    return out


def srt_to_cantonese_pair_lines_ass(src: Path, mode: str, single_line: bool = False) -> Path:
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    time_re = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d{3})\s+-->\s+(\d\d):(\d\d):(\d\d),(\d{3})")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, Italic, Outline, Alignment, MarginV
Style: Reading, Arial, 36, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 60
Style: Text, Arial, 48, &H00FFFFFF, &H00000000, 0, 0, 1, 2, 20

[Events]
Format: Layer, Start, End, Style, Text
"""
    events: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        m = time_re.match(lines[0])
        if not m:
            continue
        start, end = ass_time_from_srt(m.groups())
        subtitle_lines = lines[1:]
        if single_line:
            subtitle_lines = flatten_subtitle_lines(subtitle_lines)
        for line in subtitle_lines:
            pair = cantonese_reading_pair_lines(line, mode)
            if pair is None:
                events.append(f"Dialogue: 0,{start},{end},Text,{line}")
                continue
            reading_row, text_row = pair
            events.append(f"Dialogue: 0,{start},{end},Text,{text_row}")
            events.append(f"Dialogue: 0,{start},{end},Reading,{reading_row}")

    out = src.with_suffix("").with_name(
        src.with_suffix("").name + romanization_suffix("yue", mode, "stacked.ass", single_line)
    )
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out


def generate_cantonese_romanization(
    paths: Iterable[Path],
    mode: str,
    single_line: bool = False,
    formats: set[str] | None = None,
) -> list[Path]:
    if formats is None:
        formats = {"srt"}
    generated: list[Path] = []
    for path in paths:
        if ".yue" not in path.name:
            continue
        if path.suffix.lower() != ".srt":
            continue
        if "srt" in formats:
            generated.append(srt_to_cantonese_readings(path, mode, single_line))
        if "vtt" in formats:
            generated.append(srt_to_cantonese_ruby_vtt(path, mode, single_line))
        if "ass" in formats:
            generated.append(srt_to_cantonese_pair_lines_ass(path, mode, single_line))
    return generated


def generate_furigana(
    paths: Iterable[Path],
    mode: str,
    single_line: bool = False,
    formats: set[str] | None = None,
) -> list[Path]:
    """Generate furigana side files for each .ja.srt in `paths`.

    `formats` controls which output variants get written. Default {'srt'} —
    the broadly compatible SRT. Pass {'srt','ass','vtt'} or call with
    formats=None then `formats={'srt','vtt'}` etc. to add ruby VTT or ASS.
    asbplayer can render ruby VTT when Subtitle HTML is set to Render."""
    if formats is None:
        formats = {"srt"}
    generated: list[Path] = []
    for path in paths:
        if ".ja" not in path.name:
            continue
        if path.suffix.lower() != ".srt":
            # Furigana conversion currently starts from SRT only.
            continue
        if "srt" in formats:
            generated.append(srt_to_asbplayer_readings(path, mode, single_line))
        if "vtt" in formats:
            generated.append(srt_to_ruby_vtt(path, mode, single_line))
        if "ass" in formats:
            generated.append(srt_to_furigana_lines_ass(path, mode, single_line))
    return generated


# ===========================================================================
# Combine subcommand
# ===========================================================================
# Combines downloaded single-language SRTs into one study-friendly stack per
# episode, e.g. ja-then-ko cues sharing a single timing track.
#
# Public functions (used by tests and from combine_main):
#   - parse_episode_marker(name)       -> (season, episode) | None
#   - parse_srt_filename(name)         -> (season, episode, lang, is_mt) | None
#   - is_combined_output_name(name)    -> bool
#   - is_furigana_output_name(name)    -> bool
#   - scan_srt_files(paths, include_furigana=False) -> list of tuples
#   - group_srts_by_episode(scanned)   -> dict[(season, episode)][lang] = Path
#   - parse_srt_time_line(line)        -> (start_ms, end_ms)
#   - overlap_ratio(...)               -> float in [0, 1]
#   - combine_cues(...)                -> (cues, per_lang_match_rate)
#   - combined_output_name(...)        -> filename string

_EPISODE_PATTERNS = (
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})\b", re.I),
    re.compile(r"\b(\d{1,2})x(\d{1,3})\b", re.I),
)
_BARE_EPISODE_PATTERN = re.compile(r"(?:^|[.\s_-])[Ee](\d{1,3})(?:\b|[.\s_-])", re.I)
# Single-language token before .srt, with optional ".mt" suffix for
# machine-translated files. Sonarr-style HI/CC/SDH/forced tags between the
# language code and `.srt` are stripped so .ja.hi.srt parses as lang=ja, not
# lang=hi. Examples:
#   "Show.S01E07.ja.srt"          -> ("ja", "")
#   "Show.S01E07.ko.mt.srt"       -> ("ko", ".mt")
#   "Show.S01E07.ja.hi.srt"       -> ("ja", "")
#   "Show.S01E07.en.cc.srt"       -> ("en", "")
#   "Show.S01E07.es.sdh.srt"      -> ("es", "")
#   "Show.S01E07.fr.forced.srt"   -> ("fr", "")
_LANG_FILENAME_PATTERN = re.compile(
    r"\.([a-z]{2,3})(\.mt)?(?:\.(?:hi|cc|sdh|forced))?\.(?:srt|vtt|ass|ssa)$",
    re.I,
)
# Combined output: hyphen-joined language token before .srt.
# Examples: ".ja-ko.srt", ".en-es-ko.srt", ".ja-furigana-ko.srt"
_COMBINED_OUTPUT_PATTERN = re.compile(
    r"\.([a-z]{2,3}(?:-[a-z]+)+)\.srt$", re.I
)
# Furigana variants live in their own .furigana-... segment.
_FURIGANA_OUTPUT_PATTERN = re.compile(r"\.furigana[-.]", re.I)

# Multi-variant merge support: pseudo-language codes that resolve to the
# reading-aid side files produced by `modify --reading {lang}:{mode}`.
# Format: pseudo-lang -> (base_lang, infix_word, mode_token). The infix
# matches romanization_suffix() — Japanese keeps the historical
# `.furigana-{mode}` filename infix; other languages use
# `.romanization-{mode}`.
_PSEUDO_LANG_VARIANTS: dict[str, tuple[str, str, str]] = {
    "ja-hiragana": ("ja", "furigana", "hiragana"),
    "ja-katakana": ("ja", "furigana", "katakana"),
    "ja-romaji":   ("ja", "furigana", "romaji"),
    "ko-revised":  ("ko", "romanization", "revised"),
    "ko-yale":     ("ko", "romanization", "yale"),
    "zh-marks":    ("zh", "romanization", "marks"),
    "zh-numbers":  ("zh", "romanization", "numbers"),
    "zh-letters":  ("zh", "romanization", "letters"),
    "yue-numbers": ("yue", "romanization", "numbers"),
}


def is_pseudo_lang(code: str) -> bool:
    """True if `code` is a recognised multi-variant pseudo-lang
    (e.g. `ja-hiragana`, `ko-revised`, `zh-marks`)."""
    return code.lower() in _PSEUDO_LANG_VARIANTS


def _variant_filename_pattern(pseudo_lang: str) -> re.Pattern[str] | None:
    """Build a regex matching `.{base}.{infix}-{mode}[.single-line].{ext}`
    for the given pseudo-lang. Returns None for unknown pseudo-langs."""
    decoded = _PSEUDO_LANG_VARIANTS.get(pseudo_lang.lower())
    if decoded is None:
        return None
    base, infix, mode = decoded
    return re.compile(
        rf"\.({re.escape(base)})(?:\.(?:hi|sdh|cc))*\.{re.escape(infix)}-{re.escape(mode)}"
        rf"(?:\.single-line)?(?:\.(?:asb|ruby|stacked|lines))?\.(?:srt|vtt|ass|ssa)$",
        re.I,
    )

# Thresholds for time-overlap matching. Constants kept here so they're easy
# to tune without grepping. Each preset has cue-level and episode-level bars
# plus a max-drift hint used for tie-breaking close cue starts.
SYNC_PRESETS: dict[str, dict[str, float]] = {
    "auto":   {"cue_overlap": 0.35, "episode_success": 0.75, "max_drift_ms": 1500, "max_offset_ms": 45000, "offset_bucket_ms": 250, "offset_min_improvement": 0.05},
    "strict": {"cue_overlap": 0.60, "episode_success": 0.90, "max_drift_ms": 750, "max_offset_ms": 30000, "offset_bucket_ms": 250, "offset_min_improvement": 0.08},
    "loose":  {"cue_overlap": 0.20, "episode_success": 0.60, "max_drift_ms": 2500, "max_offset_ms": 60000, "offset_bucket_ms": 250, "offset_min_improvement": 0.03},
}


def parse_episode_marker(name: str) -> tuple[int, int] | None:
    """Return (season, episode) parsed from a filename, or None.

    Movie filenames produced by save_subtitle look like `Title.<lang>.srt`
    with no S/E marker. Treat those as (season=0, episode=0) so the
    scanner can still group them by (season, episode, lang) and the
    downstream modify / merge stages see a single-item plan rather than
    an empty scan."""
    for pattern in _EPISODE_PATTERNS:
        m = pattern.search(name)
        if m:
            return int(m.group(1)), int(m.group(2))
    # Common Korean/Japanese release names often use bare E01/E02 inside a
    # Season 01 folder. Treat those as S01Exx so library folders like
    # "무빙.E01...ko.srt" do not collapse into the synthetic movie bucket.
    m = _BARE_EPISODE_PATTERN.search(name)
    if m:
        return 1, int(m.group(1))
    if _is_movie_style_filename(name):
        return 0, 0
    return None


def is_filesystem_metadata_name(name: str) -> bool:
    """Skip macOS AppleDouble resource-fork sidecars and similar metadata.

    On external drives Finder creates files named `._Episode.ko.srt`.
    They end in `.srt` but contain binary "Mac OS X" metadata, so scanning
    them makes merge pick an empty/corrupt master subtitle.
    """
    return name.startswith("._") or name in {".DS_Store", "Thumbs.db"}


def _is_movie_style_filename(name: str) -> bool:
    """True for `Title.<lang>.<ext>` (no SxxExx marker) — the shape
    save_subtitle emits for movies. Excludes our own combined outputs
    and furigana variants so re-scanning a folder doesn't pick them up
    as inputs."""
    if is_combined_output_name(name) or is_furigana_output_name(name):
        return False
    return bool(_LANG_FILENAME_PATTERN.search(name))


def is_combined_output_name(name: str) -> bool:
    """True if `name` looks like one of our combined outputs (hyphenated lang
    token, e.g. .ja-ko.srt). Used so re-scanning an output folder doesn't
    pick up its own previous outputs as inputs."""
    return bool(_COMBINED_OUTPUT_PATTERN.search(name))


def is_furigana_output_name(name: str) -> bool:
    """True if `name` is a generated furigana variant (.furigana-...)."""
    return bool(_FURIGANA_OUTPUT_PATTERN.search(name))


def parse_srt_filename(name: str) -> tuple[int, int, str, bool] | None:
    """Extract (season, episode, lang, is_mt) from a single-lang SRT filename.

    Returns None for non-SRT files, combined outputs, furigana variants, or
    anything that doesn't carry both a season/episode marker and a recognised
    language token."""
    if not name.lower().endswith(".srt"):
        return None
    if is_combined_output_name(name) or is_furigana_output_name(name):
        return None
    ep = parse_episode_marker(name)
    if not ep:
        return None
    m = _LANG_FILENAME_PATTERN.search(name)
    if not m:
        return None
    season, episode = ep
    return season, episode, m.group(1).lower(), bool(m.group(2))


def scan_srt_files(
    paths: list[Path], *, include_furigana: bool = False
) -> list[tuple[Path, int, int, str, bool]]:
    """Walk paths (files or directories) and return parseable SRTs.

    Returns a list of (path, season, episode, lang, is_mt). Skips combined
    outputs and (by default) furigana variants. Sorted by path for stable
    output."""
    discovered: list[Path] = []
    for root in paths:
        if root.is_file() and not is_filesystem_metadata_name(root.name):
            discovered.append(root)
        elif root.is_dir():
            discovered.extend(
                p for p in sorted(root.rglob("*.srt"))
                if not is_filesystem_metadata_name(p.name)
            )
    out: list[tuple[Path, int, int, str, bool]] = []
    for path in discovered:
        if not include_furigana and is_furigana_output_name(path.name):
            continue
        parsed = parse_srt_filename(path.name)
        if parsed is None:
            continue
        out.append((path, *parsed))
    return out


def group_srts_by_episode(
    scanned: list[tuple[Path, int, int, str, bool]],
) -> dict[tuple[int, int], dict[str, Path]]:
    """Bucket scanned files by (season, episode) and language.

    When the same language has both a human-quality and a machine-translated
    file for the same episode, prefer the human-quality one."""
    grouped: dict[tuple[int, int], dict[str, tuple[Path, bool]]] = {}
    for path, season, episode, lang, is_mt in scanned:
        key = (season, episode)
        episode_files = grouped.setdefault(key, {})
        existing = episode_files.get(lang)
        if existing is None or (existing[1] and not is_mt):
            # First occurrence wins, or prefer non-MT over MT.
            episode_files[lang] = (path, is_mt)
    return {key: {lang: pair[0] for lang, pair in files.items()} for key, files in grouped.items()}


def _parse_vtt_filename(name: str) -> tuple[int, int, str, bool] | None:
    """Like parse_srt_filename but for `<base>.<lang>.vtt`."""
    if not name.lower().endswith(".vtt"):
        return None
    if is_combined_output_name(name) or is_furigana_output_name(name):
        return None
    ep = parse_episode_marker(name)
    if not ep:
        return None
    m = _LANG_FILENAME_PATTERN.search(name)
    if not m:
        return None
    season, episode = ep
    return season, episode, m.group(1).lower(), bool(m.group(2))


def _parse_ass_filename(name: str) -> tuple[int, int, str, bool] | None:
    """Like parse_srt_filename but for `<base>.<lang>.ass/.ssa`."""
    if not name.lower().endswith((".ass", ".ssa")):
        return None
    if is_combined_output_name(name) or is_furigana_output_name(name):
        return None
    ep = parse_episode_marker(name)
    if not ep:
        return None
    m = _LANG_FILENAME_PATTERN.search(name)
    if not m:
        return None
    season, episode = ep
    return season, episode, m.group(1).lower(), bool(m.group(2))


def scan_subtitle_files_extended(
    paths: list[Path],
    *,
    format_hints: dict[str, str] | None = None,
    include_furigana: bool = False,
    pseudo_langs: list[str] | None = None,
) -> list[tuple[Path, int, int, str, bool, str]]:
    """Walk paths and find subtitle files in SRT, VTT, ASS/SSA, and optionally SAMI.

    SRT and VTT use the standard `<base>.<lang>.<ext>` filename convention.
    SAMI files are multi-language internally, so they're only scanned when
    at least one entry in `format_hints` requests SMI for some language;
    each SMI file then emits one candidate per requested language that it
    actually contains.

    `pseudo_langs` enables multi-variant merge: each entry is a code like
    `ja-hiragana`, `ko-revised`, `zh-marks` that resolves to the matching
    `*.{base}.{infix}-{mode}.{ext}` reading-aid side file. Each match emits
    a tuple with the pseudo-lang code as the "lang" field, so downstream
    grouping / stacking treats it as its own language column.

    Returns: list[(path, season, episode, lang, is_mt, source_format)]
    where source_format is one of "srt" | "vtt" | "ass" | "ssa" | "smi".
    """
    format_hints = format_hints or {}
    pseudo_langs = [p for p in (pseudo_langs or []) if is_pseudo_lang(p)]
    out: list[tuple[Path, int, int, str, bool, str]] = []

    # SRT (delegate to existing scanner).
    for tup in scan_srt_files(paths, include_furigana=include_furigana):
        out.append(tup + ("srt",))

    # VTT.
    discovered_vtt: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".vtt" and not is_filesystem_metadata_name(root.name):
            discovered_vtt.append(root)
        elif root.is_dir():
            discovered_vtt.extend(
                p for p in sorted(root.rglob("*.vtt"))
                if not is_filesystem_metadata_name(p.name)
            )
    for path in discovered_vtt:
        if not include_furigana and is_furigana_output_name(path.name):
            continue
        parsed = _parse_vtt_filename(path.name)
        if parsed is None:
            continue
        out.append((path, *parsed, "vtt"))

    # ASS/SSA.
    discovered_ass: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() in (".ass", ".ssa") and not is_filesystem_metadata_name(root.name):
            discovered_ass.append(root)
        elif root.is_dir():
            discovered_ass.extend(
                p for p in sorted(root.rglob("*.ass"))
                if not is_filesystem_metadata_name(p.name)
            )
            discovered_ass.extend(
                p for p in sorted(root.rglob("*.ssa"))
                if not is_filesystem_metadata_name(p.name)
            )
    for path in discovered_ass:
        if not include_furigana and is_furigana_output_name(path.name):
            continue
        parsed = _parse_ass_filename(path.name)
        if parsed is None:
            continue
        out.append((path, *parsed, path.suffix.lower().lstrip(".")))

    # SMI — only if a hint requests it (parsing every .smi file is
    # expensive, and the convention is multi-language-internal so we'd
    # need to peek inside each file).
    smi_langs = {l for l, fmt in format_hints.items() if fmt == "smi"}
    if smi_langs:
        for smi_path in scan_smi_files(paths):
            ep = parse_episode_marker(smi_path.name)
            if not ep:
                continue
            season, episode = ep
            try:
                data = smi_path.read_bytes()
                text = _sami_decode_bytes(data)
                by_lang = parse_sami(text)
            except Exception:
                continue
            for lang in smi_langs:
                if lang in by_lang:
                    out.append((smi_path, season, episode, lang, False, "smi"))

    # Multi-variant merge: walk the requested pseudo-langs and emit a row
    # per matching `.{base}.{infix}-{mode}.{ext}` side file. We deliberately
    # bypass the is_furigana_output_name skip here — the caller asked for
    # the variants by name.
    for pseudo in pseudo_langs:
        pattern = _variant_filename_pattern(pseudo)
        if pattern is None:
            continue
        discovered_var: list[Path] = []
        for root in paths:
            if root.is_file() and pattern.search(root.name) and not is_filesystem_metadata_name(root.name):
                discovered_var.append(root)
            elif root.is_dir():
                for ext in ("srt", "vtt", "ass", "ssa"):
                    discovered_var.extend(
                        p for p in sorted(root.rglob(f"*.{ext}"))
                        if not is_filesystem_metadata_name(p.name)
                    )
        for path in discovered_var:
            if not pattern.search(path.name):
                continue
            ep = parse_episode_marker(path.name)
            if not ep:
                continue
            season, episode = ep
            src_fmt = path.suffix.lower().lstrip(".")
            if src_fmt == "ssa":
                src_fmt = "ssa"
            out.append((path, season, episode, pseudo.lower(), False, src_fmt))

    return out


def group_subtitle_files_with_hints(
    scanned: list[tuple[Path, int, int, str, bool, str]],
    *,
    format_hints: dict[str, str] | None = None,
) -> dict[tuple[int, int], dict[str, Path]]:
    """Bucket scanned files by (season, episode) → {lang: path}, choosing the
    best candidate per language using:

      1. format_hints[lang] match wins over everything else
      2. Otherwise format priority: srt > vtt > ass/ssa > smi
      3. Within format, non-MT wins over MT

    Returns the same shape as group_srts_by_episode."""
    format_hints = format_hints or {}
    fmt_priority = {"srt": 0, "vtt": 1, "ass": 2, "ssa": 2, "smi": 3}

    def score(lang: str, source_format: str, is_mt: bool) -> tuple[int, int]:
        hint = format_hints.get(lang)
        if hint is None and lang in _PSEUDO_LANG_VARIANTS:
            base, _infix, mode = _PSEUDO_LANG_VARIANTS[lang]
            if base == "ja" and mode in {"hiragana", "katakana"}:
                hint = "vtt"
        fmt_rank = -1 if hint and source_format == hint else fmt_priority.get(source_format, 99)
        return (fmt_rank, 1 if is_mt else 0)

    grouped: dict[tuple[int, int], dict[str, tuple[Path, str, bool]]] = {}
    for path, season, episode, lang, is_mt, src_format in scanned:
        key = (season, episode)
        episode_files = grouped.setdefault(key, {})
        candidate_score = score(lang, src_format, is_mt)
        if lang not in episode_files:
            episode_files[lang] = (path, src_format, is_mt)
            continue
        existing_path, existing_format, existing_is_mt = episode_files[lang]
        if candidate_score < score(lang, existing_format, existing_is_mt):
            episode_files[lang] = (path, src_format, is_mt)
    return {
        key: {lang: triple[0] for lang, triple in files.items()}
        for key, files in grouped.items()
    }


def parse_srt_time_line(line: str) -> tuple[int, int]:
    """Return (start_ms, end_ms) for an SRT time line like
    '00:00:01,500 --> 00:00:02,750'. Ignores any positional extension."""
    m = re.match(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
        line.strip(),
    )
    if not m:
        raise ValueError(f"unrecognised SRT time line: {line!r}")
    g = m.groups()

    def to_ms(h: str, mi: str, s: str, ms: str) -> int:
        return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(ms.ljust(3, "0")[:3])

    return to_ms(*g[:4]), to_ms(*g[4:])


def overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    """Overlap fraction of two cue intervals relative to the SHORTER cue.

    Returns 0.0 for no overlap, 1.0 when one cue fully contains the other or
    they coincide. Symmetric. Public for testing."""
    overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
    if overlap <= 0:
        return 0.0
    shorter = min(a_end - a_start, b_end - b_start)
    if shorter <= 0:
        return 0.0
    return min(overlap / shorter, 1.0)


def is_dialogue_cue(cue: SrtCue) -> bool:
    text = " ".join(line.strip() for line in cue.text_lines if line.strip())
    if not text:
        return False
    plain = strip_subtitle_markup(text)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    lower = plain.casefold()
    if not plain:
        return False
    if re.fullmatch(r"[♬♪～\s]+", text):
        return False
    if re.fullmatch(r"[（）()\s・…ー\-！!？?]+", text):
        return False
    if re.search(r"https?://|www\.|\.com\b|discord\.gg|@[\w.-]+", lower):
        return False
    credit_patterns = (
        r"\b(?:subtitle|subtitles|subs|translation|translated|timing|sync|synced|edited|encoded)\s+by\b",
        r"\b(?:subbed|translated|timed|synced|encoded)\s+by\b",
        r"\b(?:raws?|rip|release)\s+by\b",
        r"\b(?:visit|follow|join)\s+(?:us\s+)?(?:at|on)\b",
        r"\bopensubtitles\b|\baddic7ed\b|\bsubdivx\b",
    )
    if any(re.search(pattern, lower) for pattern in credit_patterns):
        return False
    return True


def match_rate_for_shift(
    master_times: list[tuple[int, int]],
    target_times: list[tuple[int, int]],
    *,
    offset_ms: int,
    threshold: float,
) -> float:
    if not master_times:
        return 0.0
    shifted = [(start + offset_ms, end + offset_ms) for start, end in target_times]
    matched = 0
    for m_start, m_end in master_times:
        best = max((overlap_ratio(m_start, m_end, t_start, t_end) for t_start, t_end in shifted), default=0.0)
        if best >= threshold:
            matched += 1
    return matched / len(master_times)


def estimate_timing_offset_ms(
    master_cues: list[SrtCue],
    target_cues: list[SrtCue],
    sync_preset: dict[str, float],
) -> int:
    """Estimate a constant target->master timing offset.

    Downloaded subtitles from different releases often have the same cue order
    but a several-second offset. We test candidate offsets from nearby dialogue
    cue starts, then keep the offset only when it improves overlap enough."""
    threshold = float(sync_preset["cue_overlap"])
    window_ms = int(sync_preset.get("max_offset_ms", 45000))
    bucket_ms = int(sync_preset.get("offset_bucket_ms", 250))
    min_improvement = float(sync_preset.get("offset_min_improvement", 0.05))

    master_dialogue = [cue for cue in master_cues if is_dialogue_cue(cue)]
    target_dialogue = [cue for cue in target_cues if is_dialogue_cue(cue)]
    if len(master_dialogue) < 3 or len(target_dialogue) < 3:
        return 0

    master_times = [parse_srt_time_line(cue.time_line) for cue in master_dialogue]
    target_times = [parse_srt_time_line(cue.time_line) for cue in target_dialogue]
    baseline = match_rate_for_shift(master_times, target_times, offset_ms=0, threshold=threshold)

    buckets: dict[int, int] = {}
    for m_start, _m_end in master_times:
        for t_start, _t_end in target_times:
            diff = m_start - t_start
            if abs(diff) > window_ms:
                continue
            bucket = round(diff / bucket_ms) * bucket_ms
            buckets[bucket] = buckets.get(bucket, 0) + 1
    if not buckets:
        return 0

    best_offset = 0
    best_rate = baseline
    for offset, _count in sorted(buckets.items(), key=lambda item: -item[1])[:40]:
        rate = match_rate_for_shift(master_times, target_times, offset_ms=offset, threshold=threshold)
        if rate > best_rate or (rate == best_rate and abs(offset) < abs(best_offset)):
            best_rate = rate
            best_offset = offset

    if abs(best_offset) < bucket_ms:
        return 0
    if best_rate - baseline < min_improvement:
        return 0
    return int(best_offset)


def _format_cue_text_for_lang(lines: list[str], preserve_lines: bool) -> list[str]:
    """Format one language's contribution to a combined cue. Returns the
    physical text lines that should appear in the SRT for this language."""
    cleaned = [strip_subtitle_markup(ln).strip() for ln in lines if ln.strip()]
    if not cleaned:
        return []
    if preserve_lines:
        return cleaned
    joined = " ".join(cleaned)
    joined = re.sub(r"\s+", " ", joined)
    return [joined] if joined else []


def _format_japanese_furigana_for_combine(
    lines: list[str], mode: str, preserve_lines: bool
) -> list[str]:
    """Format Japanese for a combined SRT as reading row(s) above text row(s).

    SRT has no real ruby layout, and asbplayer currently treats uploaded SRT
    text as plain lines. This stacked layout is the most reliable compromise:
    keep each Japanese subtitle line clean, and insert a kana/romaji guide row
    immediately above it when the row contains kanji.
    """
    physical_lines: list[str] = []
    for line in _format_cue_text_for_lang(lines, preserve_lines):
        clean = strip_existing_readings(line).strip()
        if not clean:
            continue
        pair = kanji_reading_pair_lines(clean, mode)
        if pair and has_kanji(clean):
            reading, aligned_text = pair
            physical_lines.append(reading)
            physical_lines.append(aligned_text)
        else:
            physical_lines.append(clean)
    return physical_lines


def combine_cues(
    master_cues: list[SrtCue],
    target_cues: dict[str, list[SrtCue]],
    lang_order: list[str],
    master_lang: str,
    sync_preset: dict[str, float],
    *,
    preserve_lines: bool = False,
    japanese_furigana_mode: str | None = None,
    label_langs: bool = False,
) -> tuple[list[SrtCue], dict[str, float]]:
    """Combine `master_cues` with overlapping cues from each target language.

    When `label_langs` is true each language block is prefixed with an
    uppercase `[LANG] ` tag on its first line, so a stacked cue reads
    `[JA] …` / `[EN] …` — handy for telling tracks apart at a glance.

    Returns (combined_cues, per_target_lang_match_rate). Master is timing
    authority. Each target cue is matched to the master cue with the highest
    overlap above sync_preset['cue_overlap']; if no candidate clears the
    bar, that language is omitted from the cue's body.

    `target_cues` does NOT include the master language; the caller provides
    only the other requested languages."""
    if not master_cues:
        return [], {lang: 0.0 for lang in target_cues}

    master_times = [parse_srt_time_line(c.time_line) for c in master_cues]
    target_times: dict[str, list[tuple[int, int]]] = {
        lang: [parse_srt_time_line(c.time_line) for c in cues]
        for lang, cues in target_cues.items()
    }
    threshold = float(sync_preset["cue_overlap"])
    target_offsets = {
        lang: estimate_timing_offset_ms(master_cues, cues, sync_preset)
        for lang, cues in target_cues.items()
    }
    if any(target_offsets.values()):
        target_times = {
            lang: [(start + target_offsets.get(lang, 0), end + target_offsets.get(lang, 0)) for start, end in times]
            for lang, times in target_times.items()
        }

    match_counts: dict[str, int] = {lang: 0 for lang in target_cues}
    used_target_indices: dict[str, set[int]] = {lang: set() for lang in target_cues}
    combined: list[SrtCue] = []

    for i, master_cue in enumerate(master_cues):
        m_start, m_end = master_times[i]
        per_lang_text: dict[str, list[str]] = {}
        for lang, cues in target_cues.items():
            best_idx = None
            best_overlap = 0.0
            for j, (t_start, t_end) in enumerate(target_times[lang]):
                if j in used_target_indices[lang]:
                    continue
                ratio = overlap_ratio(m_start, m_end, t_start, t_end)
                if ratio > best_overlap:
                    best_overlap = ratio
                    best_idx = j
                    if ratio >= 0.999:
                        break  # Perfect or near-perfect match; no need to keep searching.
            if best_idx is not None and best_overlap >= threshold:
                if lang == "ja" and japanese_furigana_mode:
                    per_lang_text[lang] = _format_japanese_furigana_for_combine(
                        cues[best_idx].text_lines, japanese_furigana_mode, preserve_lines
                    )
                else:
                    per_lang_text[lang] = _format_cue_text_for_lang(
                        cues[best_idx].text_lines, preserve_lines
                    )
                if per_lang_text[lang]:
                    match_counts[lang] += 1
                    used_target_indices[lang].add(best_idx)
            # else: leave lang out of this cue.

        body: list[str] = []
        for lang in lang_order:
            if lang == master_lang:
                if lang == "ja" and japanese_furigana_mode:
                    lines = _format_japanese_furigana_for_combine(
                        master_cue.text_lines, japanese_furigana_mode, preserve_lines
                    )
                else:
                    lines = _format_cue_text_for_lang(master_cue.text_lines, preserve_lines)
            else:
                lines = list(per_lang_text.get(lang, []))
            if label_langs and lines:
                lines = [f"[{lang.upper()}] {lines[0]}", *lines[1:]]
            body.extend(lines)

        combined.append(
            SrtCue(
                index=str(i + 1),
                time_line=master_cue.time_line,
                text_lines=body if body else [""],
            )
        )

    total = len(master_cues) or 1
    return combined, {lang: count / total for lang, count in match_counts.items()}


def _pseudo_lang_reading_lines(pseudo_lang: str, lines: list[str], preserve_lines: bool) -> list[str]:
    decoded = _PSEUDO_LANG_VARIANTS.get(pseudo_lang.lower())
    if decoded is None:
        return []
    base, _infix, mode = decoded
    out: list[str] = []
    for line in _format_cue_text_for_lang(lines, preserve_lines):
        clean = strip_existing_readings(line).strip()
        if not clean:
            continue
        if base == "ja":
            reading = kanji_reading_line(clean, mode)
            if mode == "romaji":
                out.append(reading or clean)
            else:
                out.append(reading if reading and has_kanji(clean) else clean)
        elif base == "ko":
            pair = hangul_reading_pair_lines(clean, mode)
            out.append(pair[0] if pair else clean)
        elif base == "zh":
            pair = hanzi_reading_pair_lines(clean, mode)
            out.append(pair[0] if pair else clean)
        elif base == "yue":
            pair = cantonese_reading_pair_lines(clean, mode)
            out.append(pair[0] if pair else clean)
    return out


def derive_pseudo_lang_cues(
    source_cues: list[SrtCue],
    pseudo_lang: str,
    *,
    preserve_lines: bool = False,
) -> list[SrtCue]:
    """Create a reading-only pseudo-language track from the base language.

    Multi-variant merge should stack clean rows like `ko-revised`, not consume
    side files that may contain both original text and readings.
    """
    out: list[SrtCue] = []
    for cue in source_cues:
        lines = _pseudo_lang_reading_lines(pseudo_lang, cue.text_lines, preserve_lines)
        out.append(SrtCue(index=cue.index, time_line=cue.time_line, text_lines=lines or [""]))
    return out


def combined_output_name(master_path: Path, lang_order: list[str], *, furigana: bool = False) -> str:
    """Compute the combined-output filename, e.g.
    'MF Ghost - S01E07.ja.srt' + ['ja','ko'] -> 'MF Ghost - S01E07.ja-ko.srt'.

    When `furigana` is set and 'ja' is present, the 'ja' token is rewritten
    to 'ja-furigana' so the output filename signals that readings were
    inlined into the Japanese lines.

    For multi-variant merge, pseudo-lang codes (`ja-hiragana`, `ko-revised`,
    `zh-marks`, …) collapse adjacent same-base tokens — e.g. ['ja',
    'ja-hiragana', 'ja-romaji', 'en'] -> 'ja-hiragana-romaji-en' instead of
    the redundant 'ja-ja-hiragana-ja-romaji-en'."""
    name = master_path.name
    stem = _LANG_FILENAME_PATTERN.sub("", name)
    if stem == name:
        # No language token to strip; fall back to the bare stem.
        stem = master_path.with_suffix("").name
    tokens = list(lang_order)
    if furigana and "ja" in tokens:
        # Replace only the first ja so other ja entries (rare) aren't doubled.
        ja_idx = tokens.index("ja")
        tokens[ja_idx] = "ja-furigana"
    collapsed = _collapse_variant_tokens(tokens)
    return f"{stem}.{'-'.join(collapsed)}.srt"


def _collapse_variant_tokens(tokens: list[str]) -> list[str]:
    """Collapse adjacent same-base tokens for multi-variant merge filenames.

    Given ['ja', 'ja-hiragana', 'ja-romaji', 'en'], emit
    ['ja', 'hiragana', 'romaji', 'en'] so the joined form is
    `ja-hiragana-romaji-en` instead of `ja-ja-hiragana-ja-romaji-en`.

    Bases are tracked per group: a new bare base or a token with a
    different base starts a new emission group."""
    out: list[str] = []
    last_base: str | None = None
    for tok in tokens:
        # A pseudo-lang token like 'ja-hiragana' has a hyphen with a
        # known base prefix. A bare lang code like 'ja' has no hyphen.
        if "-" in tok and tok.lower() in _PSEUDO_LANG_VARIANTS:
            base, _, mode = tok.partition("-")
            if base == last_base:
                out.append(mode)
            else:
                out.append(tok)
                last_base = base
        else:
            out.append(tok)
            # Use the bare lang as the new base so a following
            # `lang-variant` collapses to just `-variant`.
            last_base = tok if "-" not in tok else None
    return out


def combined_output_path(master_path: Path, lang_order: list[str], *, furigana: bool = False, fmt: str = "srt") -> str:
    name = combined_output_name(master_path, lang_order, furigana=furigana)
    if fmt == "srt":
        return name
    return str(Path(name).with_suffix(f".{fmt}"))


def apply_furigana_inline(cues: list[SrtCue], mode: str) -> None:
    """Inline parenthetical readings into Japanese cue text in place.

    Reuses the existing text_with_readings helper so combine output stays
    consistent with the standalone furigana SRT generator. Raises CliError
    via text_with_readings if pykakasi isn't installed."""
    for cue in cues:
        cue.text_lines = [text_with_readings(line, mode) for line in cue.text_lines]


def _sorted_episode_keys(keys: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted(keys)


def _episode_label_se(season: int, episode: int) -> str:
    # (0, 0) is the synthetic key parse_episode_marker assigns to movie-
    # style filenames (Title.<lang>.srt with no SxxExx). Label that as
    # 'movie' instead of the misleading S00E00 placeholder.
    if season == 0 and episode == 0:
        return "movie"
    return f"S{season:02d}E{episode:02d}"


def filter_episode_keys(
    keys: Iterable[tuple[int, int]],
    *,
    season: str = "all",
    episode: str = "all",
) -> list[tuple[int, int]]:
    seasons = None if str(season).lower() in {"all", "auto"} else set(parse_episode_selector(season))
    episodes = None if str(episode).lower() in {"all", "auto"} else set(parse_episode_selector(episode))
    out = []
    for key in keys:
        season_num, episode_num = key
        if seasons is not None and str(season_num) not in seasons:
            continue
        if episodes is not None and str(episode_num) not in episodes:
            continue
        out.append(key)
    return _sorted_episode_keys(out)


def build_combine_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle combine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Combine multiple language SRT files into one study-friendly cue stack "
            "per episode. Group files by season/episode, match cues by time overlap, "
            "and write <name>.<lang1>-<lang2>.srt files alongside (or to -o)."
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              getsubtitle combine ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,ko
              getsubtitle combine FOLDER -l ja,ko --dry-run
              getsubtitle combine FOLDER -l ja,ko -o ~/Downloads/GetSubtitle/Combined
              getsubtitle combine FOLDER -l ja,ko --sync strict
              getsubtitle combine FOLDER -l ja,ko --force
              getsubtitle combine FOLDER -l ja,ko -furigana
              getsubtitle combine FOLDER -l ja,ko -furigana romaji
              getsubtitle combine FOLDER -l en,es,ko
            """
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="One or more SRT files or directories to scan (recursive).")
    p.add_argument("-l", "--languages", "--langs", "--lang", dest="langs", default="ja,en", metavar="CODES", help="Language order for the output cue stack. First language is the timing master unless --master is set. Accepts ISO codes (ja,en) or full names (japanese,english). Default: ja,en.")
    p.add_argument("-s", "--season", default="all", metavar="N|all", help="Season filter. Default: all detected seasons.")
    p.add_argument("-e", "--episode", default="all", metavar="N|N-M|all", help="Episode filter. Accepts one episode, a range, a comma list, or all. Default: all detected episodes.")
    p.add_argument("-o", "--output", metavar="DIR", help="Output directory. Default: beside each episode's master SRT.")
    p.add_argument("--format", choices=["srt", "vtt", "smi", "ass", "txt"], default="srt", help="Combined output format. srt = broad compatibility; vtt = WebVTT with ruby markup when --reading is used; smi = SAMI; ass = styled script; txt = plain text without timestamps. Default: srt.")
    p.add_argument("--no-watermark", action="store_true", help="Do not add the short GetSubtitle credit/disclaimer cues to merged outputs.")
    p.add_argument("--subdirectory", action="store_true", help="Bulk mode: treat each immediate subdirectory of PATH as its own show and run combine once per subdir. Useful for whole-library passes.")
    p.add_argument("--dry-run", action="store_true", help="Show the plan without writing files.")
    p.add_argument("--force", action="store_true", help="Overwrite existing combined outputs and bypass the episode-level match-rate threshold.")
    p.add_argument("--open-folder", action="store_true", help="Open the output folder after writing.")
    p.add_argument("--no-open-folder-prompt", action="store_true", help="Do not ask whether to open the output folder after writing.")
    p.add_argument("--sync", choices=list(SYNC_PRESETS), default="auto", help="Time-overlap strictness preset. Default: auto.")
    p.add_argument("--master", metavar="LANG", help="Override the timing master language (default: first language in -l).")
    p.add_argument("--label-langs", dest="label_langs", action="store_true", default=None, help="Prefix each language's line in a stacked cue with [JA]/[KO]/… so tracks are easy to tell apart.")
    p.add_argument("--no-label-langs", dest="label_langs", action="store_false", help="Never label languages, even when [merge] label_langs = true is set in user_settings.toml.")
    p.add_argument("--single-line", "--single", dest="preserve_lines", action="store_false", default=argparse.SUPPRESS, help="Flatten each language to one line per cue. This is the default; kept as an explicit readability flag.")
    p.add_argument("--preserve-lines", action="store_true", default=argparse.SUPPRESS, help="Keep each source language's original line breaks. Default: flatten each language to a single line.")
    # Hidden compat aliases for the pre-reading --furigana flag; kept so old
    # scripts and the [merge].furigana TOML key still work. New code should
    # use --reading (added below), which generalises to non-Japanese
    # languages and routes Japanese entries through the same code path.
    p.add_argument("--reading", dest="reading", metavar="SPEC", help="Inline reading aids onto the matching language line in the merged cue stack. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana', 'ja:katakana', 'ja:romaji', 'ko:revised', 'zh:marks'.")
    p.add_argument("--no-reading", dest="reading", action="store_const", const="", help="Disable inline reading aids for this run, overriding [merge].reading from user_settings.toml.")
    p.set_defaults(preserve_lines=False)
    _apply_combine_config_defaults(p)
    return p


def _format_rate(rate: float) -> str:
    return f"{rate * 100:.0f}%"


MERGED_WATERMARK_LINES = [
    "Prepared with GetSubtitle on GitHub.",
    "Media and subtitle rights remain with their respective copyright holders.",
]
MERGED_WATERMARK_DURATION_MS = 4000
MERGED_WATERMARK_GAP_MS = 500


def _srt_time_line_from_ms(start_ms: int, end_ms: int) -> str:
    return f"{_format_srt_timestamp(start_ms)} --> {_format_srt_timestamp(end_ms)}"


def add_merged_watermarks(cues: list[SrtCue]) -> list[SrtCue]:
    """Add a short credit/disclaimer cue at the beginning and end.

    Kept as normal subtitle cues so every merged output format can serialize
    it without special cases.
    """
    if not cues:
        return cues

    try:
        first_start_ms, _first_end_ms = parse_srt_time_line(cues[0].time_line)
        _last_start_ms, last_end_ms = parse_srt_time_line(cues[-1].time_line)
    except Exception:
        first_start_ms = 0
        last_end_ms = 0

    if first_start_ms > MERGED_WATERMARK_GAP_MS + 1000:
        intro_end_ms = min(
            MERGED_WATERMARK_DURATION_MS,
            max(1000, first_start_ms - MERGED_WATERMARK_GAP_MS),
        )
    else:
        intro_end_ms = MERGED_WATERMARK_DURATION_MS

    outro_start_ms = max(0, last_end_ms + MERGED_WATERMARK_GAP_MS)
    outro_end_ms = outro_start_ms + MERGED_WATERMARK_DURATION_MS
    watermarked = [
        SrtCue("1", _srt_time_line_from_ms(0, intro_end_ms), list(MERGED_WATERMARK_LINES)),
        *cues,
        SrtCue("1", _srt_time_line_from_ms(outro_start_ms, outro_end_ms), list(MERGED_WATERMARK_LINES)),
    ]
    return [
        SrtCue(str(index), cue.time_line, list(cue.text_lines))
        for index, cue in enumerate(watermarked, start=1)
    ]


def combine_main(argv: list[str]) -> int:
    # --subdirectory: bulk mode. Walk each PATH's immediate subdirs and
    # invoke combine_main per subdir without the flag. The subdir's
    # recursive scan handles Plex Season XX/ layouts inside each show.
    if "--subdirectory" in argv:
        sub_argv = _strip_flag(argv, "--subdirectory")
        # Reparse so we can find the original positional paths.
        parsed = build_combine_parser().parse_args(sub_argv + ["--subdirectory"])
        rc_total = 0
        printed_any = False
        for root_str in parsed.paths:
            root = Path(root_str).expanduser()
            if not root.is_dir():
                print(f"  (skip) {root_str}: not a directory")
                continue
            subdirs = _immediate_subdirs(root)
            if not subdirs:
                print(f"  (skip) {root_str}: no subdirectories found")
                continue
            for sub in subdirs:
                if printed_any:
                    print()
                printed_any = True
                print(f"━━ combine {root.name}/{sub.name} ━━")
                rc = combine_main(_replace_paths_in_argv(sub_argv, parsed.paths, str(sub)))
                rc_total = rc or rc_total
        return rc_total
    args = build_combine_parser().parse_args(argv)
    # --reading (the generalised reading flag) routes through the legacy
    # --furigana attribute for Japanese; non-Japanese languages raise a
    # clear "not yet implemented" CliError until per-language backends ship.
    _apply_reading_to_args(args)
    # CLI/TOML symmetry: bare `merge -l ja:vtt,en,ko:smi` accepts the same
    # per-language :format input hints as the pipeline TOML form. Strip the
    # hints so split_csv sees just the language codes, then merge into the
    # pipeline-set globals (CLI wins on key collision).
    _cli_format_hints: dict[str, str] = {}
    if args.langs and ":" in args.langs:
        normalized_langs, _cli_format_hints = _normalize_merge_langs(args.langs)
        args.langs = normalized_langs
    _effective_format_hints = {**_PIPELINE_MERGE_FORMAT_HINTS, **_cli_format_hints}
    langs = split_csv(args.langs, "ja,en")
    if not langs:
        raise CliError("No languages specified. Use -l ja,en or similar.")
    # Three-state: --label-langs (True) / --no-label-langs (False) win; when
    # neither is given (None) fall back to user_settings.toml [merge].label_langs.
    if getattr(args, "label_langs", None) is None:
        args.label_langs = _combine_label_langs_from_config()
    # Multi-variant merge: identify pseudo-lang codes (ja-hiragana,
    # ko-revised, zh-marks, …) so the scanner knows to look for the
    # `.{base}.{infix}-{mode}.{ext}` reading-aid side files. Pseudo-langs
    # are kept in `langs` so they appear as columns in the stacked output.
    pseudo_langs = [lang for lang in langs if is_pseudo_lang(lang)]
    # Master language precedence: --master flag > [combine].priority config >
    # first language in -l. When master would default to a pseudo-lang and
    # the base lang is also requested, prefer the base — variants share cue
    # timing with their base by construction (modify generates them 1:1),
    # but the base file is usually the authoritative source.
    if args.master:
        master_lang = args.master.lower()
    else:
        master_lang = _combine_master_from_config(langs) or langs[0]
        if is_pseudo_lang(master_lang):
            base = _PSEUDO_LANG_VARIANTS[master_lang][0]
            if base in langs:
                master_lang = base
    master_lang = master_lang.lower()
    if master_lang not in langs:
        raise CliError(
            f"--master {master_lang} is not in -l {','.join(langs)}. "
            "Add it to -l or pick one of the requested languages."
        )

    paths = [Path(p).expanduser() for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise CliError(
            "Path not found: " + ", ".join(str(p) for p in missing)
        )

    # If per-language :format hints OR pseudo-lang variants are present,
    # use the extended scanner that also finds .vtt, .ass/.ssa, .smi, and
    # multi-variant reading-aid side files. Otherwise stay on the
    # SRT-only fast path for behavior parity.
    if _effective_format_hints or pseudo_langs:
        scanned_ext = scan_subtitle_files_extended(
            paths,
            format_hints=_effective_format_hints,
            pseudo_langs=pseudo_langs,
        )
        grouped = group_subtitle_files_with_hints(
            scanned_ext, format_hints=_effective_format_hints,
        )
        scanned_count = len(scanned_ext)
    else:
        scanned = scan_srt_files(paths)
        grouped = group_srts_by_episode(scanned)
        scanned_count = len(scanned)
    output_dir_arg = Path(args.output).expanduser() if args.output else None
    sync_preset = SYNC_PRESETS[args.sync]
    episode_threshold = float(sync_preset["episode_success"])

    print(f"Scanned: {scanned_count} subtitle file(s) across {len(paths)} path(s)")
    if not grouped:
        print("No (season, episode, language) groups detected. Nothing to combine.")
        return 1

    detected_episode_keys = _sorted_episode_keys(grouped.keys())
    episode_keys = filter_episode_keys(detected_episode_keys, season=args.season, episode=args.episode)
    print(f"Episodes detected: {len(detected_episode_keys)} ({_episode_label_se(*detected_episode_keys[0])}-{_episode_label_se(*detected_episode_keys[-1])})")
    if len(episode_keys) != len(detected_episode_keys):
        if episode_keys:
            print(f"Episodes selected: {len(episode_keys)} ({_episode_label_se(*episode_keys[0])}-{_episode_label_se(*episode_keys[-1])})")
        else:
            print("Episodes selected: 0")
    print(f"Languages requested: {', '.join(langs)}  (master: {master_lang})")

    plan: list[tuple[tuple[int, int], Path, Path, dict[str, float]]] = []
    skipped: list[tuple[tuple[int, int], str]] = []

    if not episode_keys:
        print("\nNo episodes matched the requested -s/-e filter.")
        return 1

    for key in episode_keys:
        season, episode = key
        files = grouped[key]
        if master_lang not in files:
            skipped.append((key, f"missing master language ({master_lang})"))
            continue
        missing_langs = [lang for lang in langs if lang not in files]
        if missing_langs and not args.force:
            # Allow partial combine when only the master is missing? No —
            # already handled above. For other missing langs, we still try
            # to combine the ones we have; we just note the missing.
            pass

        # Parse subtitle bodies. read_cues_from_file dispatches on file
        # extension (SRT/VTT/SMI) so the merger can consume any input
        # format selected by the per-language :format hint upstream.
        try:
            master_cues = read_cues_from_file(
                files[master_lang],
                lang_hint=master_lang,
                preserve_vtt_ruby=args.format == "vtt",
            )
        except Exception as e:
            skipped.append((key, f"could not parse master subtitle: {e}"))
            continue
        if not master_cues:
            skipped.append((key, "master subtitle has no cues"))
            continue
        if args.format == "vtt" and args.ja_reading and master_lang == "ja":
            try:
                apply_japanese_ruby(master_cues, args.ja_reading)
            except CliError as e:
                skipped.append((key, f"furigana failed: {e}"))
                continue

        target_cues: dict[str, list[SrtCue]] = {}
        base_cue_cache: dict[str, list[SrtCue]] = {master_lang: master_cues}
        for lang in langs:
            if lang == master_lang:
                continue
            if is_pseudo_lang(lang):
                base_lang, _infix, _mode = _PSEUDO_LANG_VARIANTS[lang]
                use_ruby_side_file = (
                    args.format == "vtt"
                    and lang in files
                    and base_lang == "ja"
                    and _mode in {"hiragana", "katakana"}
                )
                if use_ruby_side_file:
                    try:
                        target_cues[lang] = read_cues_from_file(
                            files[lang],
                            lang_hint=lang,
                            preserve_vtt_ruby=args.format == "vtt",
                        )
                        continue
                    except Exception:
                        pass
                if base_lang not in base_cue_cache:
                    if base_lang not in files:
                        continue
                    try:
                        base_cue_cache[base_lang] = read_cues_from_file(
                            files[base_lang],
                            lang_hint=base_lang,
                            preserve_vtt_ruby=args.format == "vtt",
                        )
                    except Exception:
                        continue
                target_cues[lang] = derive_pseudo_lang_cues(
                    base_cue_cache[base_lang],
                    lang,
                    preserve_lines=args.preserve_lines,
                )
                continue
            if lang not in files:
                continue
            try:
                cues = read_cues_from_file(
                    files[lang],
                    lang_hint=lang,
                    preserve_vtt_ruby=args.format == "vtt",
                )
            except Exception:
                # Treat as missing for this lang rather than skipping the
                # whole episode.
                cues = []
            if args.format == "vtt" and args.ja_reading and lang == "ja":
                try:
                    apply_japanese_ruby(cues, args.ja_reading)
                except CliError as e:
                    skipped.append((key, f"furigana failed: {e}"))
                    cues = []
            target_cues[lang] = cues

        try:
            combined, rates = combine_cues(
                master_cues, target_cues, langs, master_lang, sync_preset,
                preserve_lines=args.preserve_lines,
                japanese_furigana_mode=args.ja_reading if args.format in ("srt", "smi", "ass", "txt") else None,
                label_langs=getattr(args, "label_langs", False),
            )
        except CliError as e:
            skipped.append((key, f"furigana failed: {e}"))
            continue

        # Episode-level threshold check across requested non-master languages.
        # A language that's entirely missing for this episode counts as 0%
        # match — otherwise we'd silently emit "ja-ko" files that contain
        # only ja.
        non_master_langs = [lang for lang in langs if lang != master_lang]
        if non_master_langs:
            worst_rate = min(rates.get(lang, 0.0) for lang in non_master_langs)
        else:
            worst_rate = 1.0  # Only the master was requested; nothing to combine.
        if worst_rate < episode_threshold and not args.force:
            missing_str = ", ".join(missing_langs) if missing_langs else "low time-overlap"
            skipped.append((
                key,
                f"match rate {_format_rate(worst_rate)} below {args.sync} threshold {_format_rate(episode_threshold)} "
                f"(missing: {missing_str}; use --force to write anyway)",
            ))
            continue

        dest_dir = output_dir_arg or files[master_lang].parent
        out_name = combined_output_path(files[master_lang], langs, furigana=bool(args.ja_reading), fmt=args.format)
        dest_path = dest_dir / out_name
        if dest_path.exists() and not args.force:
            skipped.append((key, f"output exists: {dest_path.name} (use --force to overwrite)"))
            continue

        plan.append((key, files[master_lang], dest_path, rates))

        # Stash combined cues alongside the plan entry so we don't re-do
        # work on the actual write pass. Use a side dict keyed by dest_path.
        _COMBINE_PENDING[dest_path] = (combined, missing_langs)

    print(f"\nPlanned outputs: {len(plan)}")
    for key, _src, dest, rates in plan:
        rate_str = ", ".join(f"{lang}={_format_rate(r)}" for lang, r in rates.items()) or "(master only)"
        print(f"  {_episode_label_se(*key)} -> {dest.name}  [{rate_str}]")

    if skipped:
        print(f"\nSkipped: {len(skipped)}")
        for key, reason in skipped:
            print(f"  {_episode_label_se(*key)}: {reason}")

    if args.dry_run:
        return 0 if plan else 1
    if not plan:
        print("\nNothing to write.")
        return 1

    print("\nWriting:")
    written: list[Path] = []
    for key, _src, dest, _rates in plan:
        combined, _missing = _COMBINE_PENDING.pop(dest, ([], []))
        if not args.no_watermark:
            combined = add_merged_watermarks(combined)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "vtt":
            body = serialize_vtt(combined)
        elif args.format == "smi":
            body = serialize_smi(combined)
        elif args.format == "ass":
            body = serialize_ass(combined)
        elif args.format == "txt":
            body = serialize_txt(combined)
        else:
            body = serialize_srt(combined)
        dest.write_text(body, encoding="utf-8")
        written.append(dest)
        print(f"  {dest}")

    print(f"\nWrote {len(written)} combined file(s).")
    should_open = args.open_folder
    if not should_open and not args.no_open_folder_prompt and sys.stdin.isatty():
        answer = input("\nOpen folder? [Y/n] ").strip().lower()
        should_open = answer in {"", "y", "yes"}
    if should_open and written:
        open_folder(written[0].parent)
    return 0


# Side channel: combine_main() does the work in two passes (plan, write) so
# the summary can be emitted up front. We stash the computed cues here keyed
# by destination path between the passes.
_COMBINE_PENDING: dict[Path, tuple[list[SrtCue], list[str]]] = {}


# ===========================================================================
# translate subcommand — offline MT against an existing folder of SRTs
# ===========================================================================
# Same MT engines and source-language priority as the in-download `--engine`
# path; the difference is that this works without a URL and never re-downloads.
# It scans PATH(s) for existing single-language SRTs, decides which requested
# languages are missing per episode, and writes <name>.<lang>.mt.srt next to
# the source (or to -o).

def _apply_translate_config_defaults(parser: argparse.ArgumentParser) -> None:
    """Push [translate] values into the translate parser as argparse
    defaults. Merges BUILTIN_CONFIG_DEFAULTS under user overrides so the
    default engine takes effect even without a user_settings.toml."""
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}
    tr = {**BUILTIN_CONFIG_DEFAULTS["translate"], **cfg.get("translate", {})}
    overrides: dict[str, object] = {}
    if tr.get("engine"):
        # Accept "ollama:qwen3:8b" colon-spec by splitting engine head.
        engine_spec = str(tr["engine"])
        engine_head, _sep, model_part = engine_spec.partition(":")
        overrides["mt_engine"] = engine_head if engine_head else engine_spec
        if model_part:
            overrides["mt_model"] = model_part
    if tr.get("model") and "mt_model" not in overrides:
        overrides["mt_model"] = tr["model"]
    src = tr.get("mt_source_lang", "auto")
    if isinstance(src, dict):
        src = _normalize_mt_source(src)
    if src and src != "auto":
        overrides["mt_source_lang"] = src
    if overrides:
        parser.set_defaults(**overrides)


def build_translate_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle translate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Machine-translate missing subtitle languages from existing files on "
            "disk. Scans PATH(s) for *.srt files, groups by season/episode, and "
            "for each requested language that's missing, translates from the best "
            "available source SRT. No URL needed and nothing is re-downloaded."
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              getsubtitle translate ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,ko --engine argos
              getsubtitle translate FOLDER -s 1 -e 11 -l ko --mt-source ja --engine ollama
              getsubtitle translate FOLDER -l ja,ko,en,es --engine deepl --dry-run
            """
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="One or more SRT files or directories to scan (recursive).")
    p.add_argument("-l", "--languages", "--langs", "--lang", dest="langs", required=True, metavar="CODES", help="Target languages to ensure exist (e.g. ja,en). Missing ones get MT'd from the best available source SRT.")
    p.add_argument("-s", "--season", default="all", metavar="N|all", help="Season filter. Default: all detected seasons.")
    p.add_argument("-e", "--episode", default="all", metavar="N|N-M|all", help="Episode filter. Accepts one episode, a range, a comma list, or all. Default: all detected episodes.")
    p.add_argument("--engine", "--mt-engine", dest="mt_engine", choices=["argos", "ollama", "deepl"], help="Translation engine. Default: argos (via [translate].engine in user_settings.toml). --mt-engine still accepted as alias.")
    p.add_argument("--no-mt-engine", dest="mt_engine", action="store_const", const="", help="Disable machine translation for this run even when [translate].engine is set in user_settings.toml.")
    p.add_argument("--model", "--mt-model", dest="mt_model", metavar="NAME", help=f"Ollama model when --engine ollama. Default: {DEFAULT_OLLAMA_MODEL}. --mt-model still accepted as alias.")
    p.add_argument("--mt-model-pair", metavar="PAIRS", help="Per-pair Ollama model overrides for this run, e.g. ja:ko=qwen3:4b,en:es=llama3.2:3b. Ignored unless --engine ollama.")
    p.add_argument("--mt-source", "--mt-source-lang", dest="mt_source_lang", metavar="CODES", help="Force the source language(s). Single code (ja) applies to all targets; target:source pairs (ko:ja,es:en) map per target. Default: auto-pick. --mt-source-lang still accepted as alias.")
    p.add_argument("-o", "--output", metavar="DIR", help="Output directory. Default: beside each episode's source SRT.")
    p.add_argument("--subdirectory", action="store_true", help="Bulk mode: treat each immediate subdirectory of PATH as its own show and run translate once per subdir.")
    p.add_argument("--dry-run", action="store_true", help="Show the translation plan without writing files.")
    p.add_argument("--force", action="store_true", help="Overwrite existing .mt.srt outputs.")
    _apply_translate_config_defaults(p)
    return p


def translate_main(argv: list[str]) -> int:
    # --subdirectory: walk each PATH's immediate subdirs, run translate
    # per subdir. Cosmetic for per-show progress; output files identical
    # to the no-flag case since translate already walks recursively.
    if "--subdirectory" in argv:
        sub_argv = _strip_flag(argv, "--subdirectory")
        parsed = build_translate_parser().parse_args(sub_argv + ["--subdirectory"])
        rc_total = 0
        printed_any = False
        for root_str in parsed.paths:
            root = Path(root_str).expanduser()
            if not root.is_dir():
                print(f"  (skip) {root_str}: not a directory")
                continue
            subdirs = _immediate_subdirs(root)
            if not subdirs:
                print(f"  (skip) {root_str}: no subdirectories found")
                continue
            for sub in subdirs:
                if printed_any:
                    print()
                printed_any = True
                print(f"━━ translate {root.name}/{sub.name} ━━")
                rc = translate_main(_replace_paths_in_argv(sub_argv, parsed.paths, str(sub)))
                rc_total = rc or rc_total
        return rc_total
    args = build_translate_parser().parse_args(argv)
    explicit_mt_model = args.mt_model if (
        option_was_passed(argv, "--model") or option_was_passed(argv, "--mt-model")
    ) else None
    if not args.mt_engine:
        raise CliError(
            "translate needs an engine. Pass --engine {argos|ollama|deepl} "
            "or set [translate].engine in user_settings.toml."
        )
    langs = split_csv(args.langs, "ja")
    if not langs:
        raise CliError("No target languages specified. Use -l ja,ko or similar.")
    # [translate].strip_reading_before_mt: when true (default), strip inline
    # 漢字（かんじ） readings from ja source cues before MT so the translator
    # doesn't treat them as extra content. Read once here so per-cue
    # translation stays fast.
    try:
        _cfg_tr = load_user_config().get("translate", {})
    except CliError:
        _cfg_tr = {}
    strip_reading_before_mt = bool(_cfg_tr.get("strip_reading_before_mt", True))

    # Parse --mt-source once (so a bad value errors before the scan).
    source_overrides = parse_mt_source_lang(args.mt_source_lang, langs)

    paths = [Path(p).expanduser() for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise CliError("Path not found: " + ", ".join(str(p) for p in missing))

    scanned = scan_srt_files(paths)
    grouped = group_srts_by_episode(scanned)
    output_dir_arg = Path(args.output).expanduser() if args.output else None

    print(f"Scanned: {len(scanned)} SRT file(s) across {len(paths)} path(s)")
    if not grouped:
        print("No (season, episode, language) groups detected. Nothing to translate.")
        return 1

    detected_episode_keys = _sorted_episode_keys(grouped.keys())
    episode_keys = filter_episode_keys(detected_episode_keys, season=args.season, episode=args.episode)
    print(f"Episodes detected: {len(detected_episode_keys)} ({_episode_label_se(*detected_episode_keys[0])}-{_episode_label_se(*detected_episode_keys[-1])})")
    if len(episode_keys) != len(detected_episode_keys):
        if episode_keys:
            print(f"Episodes selected: {len(episode_keys)} ({_episode_label_se(*episode_keys[0])}-{_episode_label_se(*episode_keys[-1])})")
        else:
            print("Episodes selected: 0")
    print(f"Target languages: {', '.join(langs)}  (engine: {args.mt_engine})")
    if source_overrides:
        print(f"Source overrides: {_format_mt_source_overrides(source_overrides)}")

    # Plan: list of (episode_key, source_path, source_lang, target_lang, dest_path)
    plan: list[tuple[tuple[int, int], Path, str, str, Path]] = []
    skipped: list[tuple[tuple[int, int], str]] = []

    for key in episode_keys:
        season, episode = key
        raw_available = grouped[key]
        # Exclude .mt.srt files from both the "do we already have this
        # language?" check and the source pool — an existing MT shouldn't
        # block re-translating it, and MTing from an MT file would compound
        # errors. Overwrite protection happens later via the dest_path check
        # (which respects --force).
        available = {lang: p for lang, p in raw_available.items() if ".mt." not in p.name}
        for target in langs:
            if target in available:
                # Already have a human-quality version; nothing to do.
                continue
            forced_source = source_overrides.get(target) if source_overrides else None
            if forced_source:
                picked_forced = pick_forced_mt_source(target, forced_source, available)
                if not picked_forced:
                    skipped.append((key, f"{target}: none of the forced sources ({'|'.join(forced_source)}) available for this episode"))
                    continue
                src_lang, src_path = picked_forced
            else:
                picked = pick_mt_source(target, available)
                if not picked:
                    skipped.append((key, f"{target}: no source SRT available for this episode"))
                    continue
                src_lang, src_path = picked

            dest_dir = output_dir_arg or src_path.parent
            dest_path = dest_dir / mt_output_path(src_path, target).name
            if dest_path.exists() and not args.force:
                skipped.append((key, f"{target}: output exists ({dest_path.name}; use --force to overwrite)"))
                continue
            plan.append((key, src_path, src_lang, target, dest_path))

    print(f"\nPlanned translations: {len(plan)}")
    for key, src_path, src_lang, target, dest_path in plan:
        print(f"  {_episode_label_se(*key)} {src_lang}->{target}: {src_path.name} -> {dest_path.name}")

    if skipped:
        # Dedupe identical reasons (common when one source lang is missing
        # across the whole season). One line per unique reason, with the
        # affected episodes listed.
        grouped_skips: dict[str, list[str]] = {}
        for key, reason in skipped:
            grouped_skips.setdefault(reason, []).append(_episode_label_se(*key))
        print(f"\nSkipped: {len(skipped)}")
        for reason, eps in grouped_skips.items():
            if len(eps) == 1:
                print(f"  {eps[0]}: {reason}")
            else:
                preview = eps[:6]
                more = f" (+{len(eps) - len(preview)} more)" if len(eps) > len(preview) else ""
                print(f"  {len(eps)} episodes [{', '.join(preview)}{more}]: {reason}")

    if args.dry_run:
        return 0 if plan else 1
    if not plan:
        print("\nNothing to translate.")
        return 1

    first_src = plan[0][2] if plan else None
    first_tgt = plan[0][3] if plan else None
    pair_model_previous = apply_mt_model_pair_overrides(
        args.mt_model_pair if args.mt_engine == "ollama" else None
    )
    translator_cache: dict[tuple[str, str | None], _BaseTranslator] = {}

    def translator_for(src_lang: str, target_lang: str) -> _BaseTranslator:
        model = ollama_model_for_pair(src_lang, target_lang, explicit_mt_model) if args.mt_engine == "ollama" else args.mt_model
        key = (args.mt_engine, model)
        if key not in translator_cache:
            translator_cache[key] = select_translator(args.mt_engine, model)
        return translator_cache[key]

    translator = translator_for(first_src, first_tgt) if first_src and first_tgt else select_translator(args.mt_engine, args.mt_model)

    # Pre-flight: fail fast if the engine isn't ready. Avoids running through
    # N episodes only to print N identical setup messages.
    if not translator.is_available():
        # Use the first plan entry's source/target to make the install hint
        # specific where it matters (e.g. argospm install translate-ja_ko).
        sample_src = plan[0][2] if plan else None
        sample_tgt = plan[0][3] if plan else None
        restore_mt_model_pair_overrides(pair_model_previous)
        raise CliError(f"{translator.name}: not ready.\n{translator.setup_help(sample_src, sample_tgt)}")

    print(f"\nTranslating with {translator.name}:")
    written: list[tuple[Path, float]] = []
    grouped_failures: dict[str, list[str]] = {}
    for idx, (key, src_path, src_lang, target, dest_path) in enumerate(plan, start=1):
        translator = translator_for(src_lang, target)
        ep_label = _episode_label_se(*key)
        started_at = time.monotonic()
        # Cue-level progress, throttled to ~5% steps so Argos's per-cue
        # neural call shows movement instead of one tick per episode.
        prefix = f"ep {ep_label} ({idx}/{len(plan)}) {src_lang}->{target}"
        last_pct = [-1]

        def cue_progress(done: int, total: int, _last=last_pct, _label=prefix) -> None:
            if total <= 0:
                return
            pct = (done * 100) // total
            if done >= total or pct >= _last[0] + 5:
                _last[0] = pct
                progress_bar(
                    done, total, "translating",
                    f"{_label} cue {done}/{total} ({format_elapsed(time.monotonic() - started_at)})",
                    transient=True,
                )

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            translate_srt_file(
                src_path, dest_path, translator, src_lang, target,
                on_progress=cue_progress,
                strip_furigana=strip_reading_before_mt,
            )
        except TranslatorError as e:
            grouped_failures.setdefault(str(e), []).append(f"{ep_label} {src_lang}->{target}")
            continue
        elapsed = time.monotonic() - started_at
        written.append((dest_path, elapsed))
        print(f"  {ep_label} {src_lang}->{target}: wrote {dest_path.name} in {format_elapsed(elapsed)}")

    if grouped_failures:
        print(f"\nFailures ({sum(len(v) for v in grouped_failures.values())}):")
        for msg, tasks in grouped_failures.items():
            if len(tasks) == 1:
                print(f"  {tasks[0]}: {msg}")
            else:
                print(f"  {len(tasks)} task(s) failed with the same error:")
                print(f"    {msg}")
                preview = tasks[:5]
                for t in preview:
                    print(f"      - {t}")
                if len(tasks) > len(preview):
                    print(f"      - ... and {len(tasks) - len(preview)} more")

    # Auto-unload Ollama models from memory after the batch, if enabled.
    # Default is true (set in BUILTIN_CONFIG_DEFAULTS) so the user's GPU/RAM
    # is freed promptly. Best-effort: failures are silent because the actual
    # MT work has already succeeded.
    if args.mt_engine == "ollama" and _ollama_models_flag("auto_unload", True):
        released: list[str] = []
        for tr in translator_cache.values():
            if tr.release_resources():
                released.append(getattr(tr, "model", tr.name))
        if released:
            uniq = sorted(set(released))
            print(f"Unloaded Ollama model(s) from memory: {', '.join(uniq)}")
    if args.mt_engine == "deepl" and translator_cache:
        print_deepl_usage_summary(translator_cache.values())

    print(f"\nWrote {len(written)} machine-translated file(s).")
    if written:
        print("Reminder: .mt.srt files are machine-quality — verify before relying on them.")
    restore_mt_model_pair_overrides(pair_model_previous)
    return 0 if written else 1


# ===========================================================================
# modify subcommand — post-process existing SRTs (strip / flatten / furigana)
# ===========================================================================
# The same cleanup operations that run after a download, but applied to files
# already on disk. Composable flags so you can run any subset.

def _apply_modify_config_defaults(parser: argparse.ArgumentParser) -> None:
    """Honour [modify] values from user_settings.toml for the modify
    subcommand defaults."""
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}
    overrides: dict[str, object] = {}
    mod = cfg.get("modify", {})
    if mod.get("single_line"):
        overrides["single_line"] = True
    if mod.get("strip_cc_noise"):
        overrides["strip_cc_noise"] = True
    # [modify].reading SPEC drives args.reading; downstream
    # _apply_reading_to_args() splits it into ja/ko/zh per-language attrs.
    if mod.get("reading"):
        overrides["reading"] = mod["reading"]
    if mod.get("reading_format"):
        overrides["reading_format"] = mod["reading_format"]
    if overrides:
        parser.set_defaults(**overrides)


def build_modify_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle modify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Post-process existing subtitle files on disk: strip broadcast-caption "
            "noise, flatten multi-line cues, generate Japanese furigana variants, "
            "and convert formats (currently Microsoft SAMI .smi → .srt). Same "
            "operations the download flow runs, but applied to files you already "
            "have."
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              getsubtitle modify FOLDER --strip-cc-noise
              getsubtitle modify FOLDER --single-line
              getsubtitle modify FOLDER --strip-cc-noise --single-line
              getsubtitle modify FOLDER --reading ja:hiragana
              getsubtitle modify FOLDER --reading ja:romaji
              getsubtitle modify FOLDER --reading "ja:hiragana|romaji"
              getsubtitle modify FOLDER -s 1 -e 3 --reading ko:revised
              getsubtitle modify FOLDER --convert smi-to-srt
              getsubtitle modify FOLDER --extract-mkv-subs
              getsubtitle modify FOLDER --convert smi-to-srt --force
              getsubtitle modify FOLDER --strip-cc-noise --single-line --reading ja:hiragana --dry-run
            """
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="One or more subtitle files or directories to scan (recursive).")
    p.add_argument("--strip-cc-noise", action="store_true", help="Remove broadcast closed-caption noise (Japanese ➡ continuation arrows and decorative wrappers like 《...》) in place.")
    p.add_argument("--single-line", "--single", action="store_true", help="Flatten each SRT cue to one text line in place. Useful for asbplayer.")
    # Hidden compat alias for the pre-reading --furigana flag. Internally
    # equivalent to `--reading ja:MODE`.
    p.add_argument("--reading", dest="reading", metavar="SPEC", help="Generate per-language reading aids. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana', 'ko:revised', 'zh:marks', 'yue:numbers'. Pipe shorthand 'ja:hiragana|romaji' generates both side files. MODE 'true' picks the language's sensible default. Japanese / Korean / Mandarin / Cantonese ship now; Thai / Arabic / Hindi / Russian land per the roadmap.")
    p.add_argument("--no-reading", dest="reading", action="store_const", const="", help="Disable reading-aid generation for this run, overriding [modify].reading from user_settings.toml.")
    p.add_argument("--reading-format", "--format", dest="reading_format", metavar="CODES", help="Reading-aid output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt. Overrides [modify].reading_format from user_settings.toml.")
    p.add_argument("--convert", metavar="SPEC", help="Convert subtitle file format. Supports smi-to-srt (all SAMI language streams) or LANG:smi-to-srt, e.g. ko:smi-to-srt, for one language.")
    p.add_argument("--extract-mkv-subs", action="store_true", help="Extract embedded text subtitles from MKV/video files using ffprobe + ffmpeg when available. Image subtitles such as PGS are reported and skipped.")
    p.add_argument("-s", "--season", default="all", help="Only process files matching this season/range when scanning a folder (default: all).")
    p.add_argument("-e", "--episode", default="all", help="Only process files matching this episode/range when scanning a folder (default: all).")
    p.add_argument("--force", action="store_true", help="With --convert: overwrite existing sibling .srt files. Without --force, conversion skips targets that already exist.")
    p.add_argument("--subdirectory", action="store_true", help="Bulk mode: treat each immediate subdirectory of PATH as its own show and run modify once per subdir.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing anything.")
    _apply_modify_config_defaults(p)
    return p


TEXT_SUBTITLE_CODECS_TO_EXT: dict[str, str] = {
    "subrip": "srt",
    "srt": "srt",
    "ass": "ass",
    "ssa": "ass",
    "webvtt": "vtt",
    "mov_text": "srt",
    "text": "srt",
}

IMAGE_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}


def scan_video_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in _BATCH_VIDEO_EXTS:
            out.append(p)
        elif p.is_dir():
            out.extend(
                f for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in _BATCH_VIDEO_EXTS
            )
    return sorted(out)


def _ffprobe_subtitle_streams(path: Path) -> list[dict]:
    if not shutil.which("ffprobe"):
        raise CliError("MKV subtitle extraction needs ffprobe on PATH. Install ffmpeg first.")
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        str(path),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "ffprobe failed").strip()
        raise CliError(msg)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        raise CliError(f"ffprobe returned invalid JSON: {e}") from e
    return list(data.get("streams") or [])


def _stream_lang(stream: dict, fallback_index: int) -> str:
    tags = stream.get("tags") or {}
    raw = str(tags.get("language") or "").strip().lower()
    if raw and raw not in {"und", "unknown"}:
        return LANGUAGE_ALIASES.get(raw, raw)
    return f"und{fallback_index}"


def plan_mkv_subtitle_extraction(video_files: list[Path]) -> tuple[list[tuple[Path, int, str, str, Path]], list[str]]:
    plan: list[tuple[Path, int, str, str, Path]] = []
    notes: list[str] = []
    for video in video_files:
        try:
            streams = _ffprobe_subtitle_streams(video)
        except CliError as e:
            notes.append(f"{video.name}: {e}")
            continue
        if not streams:
            notes.append(f"{video.name}: no embedded subtitle streams")
            continue
        seen_langs: dict[str, int] = {}
        for ordinal, stream in enumerate(streams, start=1):
            codec = str(stream.get("codec_name") or "").lower()
            if codec in IMAGE_SUBTITLE_CODECS:
                notes.append(f"{video.name}: skipped image subtitle stream {stream.get('index')} ({codec})")
                continue
            ext = TEXT_SUBTITLE_CODECS_TO_EXT.get(codec)
            if not ext:
                notes.append(f"{video.name}: skipped unsupported subtitle codec {codec or 'unknown'}")
                continue
            lang = _stream_lang(stream, ordinal)
            seen_langs[lang] = seen_langs.get(lang, 0) + 1
            lang_token = lang if seen_langs[lang] == 1 else f"{lang}.{seen_langs[lang]}"
            dest = video.with_suffix("").with_name(video.with_suffix("").name + f".{lang_token}.{ext}")
            plan.append((video, int(stream.get("index")), lang_token, codec, dest))
    return plan, notes


def extract_mkv_subtitle_plan(
    plan: list[tuple[Path, int, str, str, Path]],
    *,
    force: bool = False,
) -> tuple[list[Path], list[Path], list[str]]:
    if not shutil.which("ffmpeg"):
        raise CliError("MKV subtitle extraction needs ffmpeg on PATH. Install ffmpeg first.")
    written: list[Path] = []
    skipped: list[Path] = []
    errors: list[str] = []
    for video, stream_index, _lang, _codec, dest in plan:
        if dest.exists() and not force:
            skipped.append(dest)
            continue
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        cmd.append("-y" if force else "-n")
        cmd.extend(["-i", str(video), "-map", f"0:{stream_index}", str(dest)])
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode == 0 and dest.exists():
            written.append(dest)
        else:
            msg = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
            errors.append(f"{video.name} stream {stream_index}: {msg}")
    return written, skipped, errors


def convert_text_subtitle_to_srt_file(path: Path, *, force: bool = False) -> tuple[Path | None, bool]:
    """Convert a text subtitle sidecar (.ass/.ssa/.vtt) to sibling .srt.

    Returns (path, written). Existing .srt files are returned as available
    sources with written=False. Unsupported or empty files return (None, False).
    """
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return path, False
    if suffix not in {".ass", ".ssa", ".vtt"}:
        return None, False
    out_path = path.with_suffix(".srt")
    if out_path.exists() and not force:
        return out_path, False
    try:
        cues = read_cues_from_file(path)
    except CliError:
        return None, False
    if not cues:
        return None, False
    out_path.write_text(serialize_srt(renumber_cues(cues)), encoding="utf-8")
    return out_path, True


def _embedded_subtitle_lang_summary(plan: list[tuple[Path, int, str, str, Path]]) -> str:
    langs: list[str] = []
    for _video, _stream_index, lang, _codec, _dest in plan:
        base_lang = lang.split(".", 1)[0]
        if base_lang not in langs:
            langs.append(base_lang)
    return ", ".join(langs) if langs else "unknown"


def maybe_extract_embedded_subtitles_after_fetch_miss(
    target: Path,
    *,
    force: bool = False,
) -> bool:
    """Offer MKV embedded subtitles as a fallback source after online fetch misses.

    Returns True when at least one SRT source is available after extraction or
    conversion, so downstream translate/modify/merge stages may continue.
    """
    video_files = scan_video_files([target])
    if not video_files:
        return False
    try:
        plan, notes = plan_mkv_subtitle_extraction(video_files)
    except CliError as e:
        print("\nOnline fetch did not succeed, and embedded subtitle extraction is unavailable.")
        print(f"  {e}")
        return False
    if not plan:
        print("\nOnline fetch did not succeed, and no extractable embedded text subtitles were found.")
        for note in notes[:10]:
            print(f"  - {note}")
        return False

    print("\nOnline fetch did not succeed for this local video/folder.")
    print(
        "Embedded text subtitles were found in the MKV/video file(s): "
        f"{_embedded_subtitle_lang_summary(plan)}."
    )
    print("These can be extracted and used as translation/merge source subtitles.")
    for video, stream_index, lang, codec, dest in plan[:12]:
        print(f"  - {video.name} stream {stream_index} ({lang}, {codec}) -> {dest.name}")
    if len(plan) > 12:
        print(f"  ... and {len(plan) - 12} more")
    if notes:
        print("  Notes:")
        for note in notes[:8]:
            print(f"    - {note}")

    if sys.stdin.isatty():
        answer = input("\nExtract embedded subtitles now and continue? [Y/n] ").strip().lower()
        if answer in {"n", "no"}:
            print("Embedded subtitle extraction skipped.")
            return False
    else:
        print("\nRun this to extract embedded subtitles manually:")
        print(f"  getsubtitle modify {shlex.quote(str(target))} --extract-mkv-subs")
        return False

    written, skipped, errors = extract_mkv_subtitle_plan(plan, force=force)
    available = [dest for *_rest, dest in plan if dest.exists()]
    converted: list[Path] = []
    srt_sources: list[Path] = []
    for path in sorted(set([*written, *skipped, *available])):
        srt_path, was_written = convert_text_subtitle_to_srt_file(path, force=force)
        if srt_path is not None:
            srt_sources.append(srt_path)
            if was_written:
                converted.append(srt_path)

    if errors:
        print("\nEmbedded subtitle extraction errors:")
        for msg in errors[:10]:
            print(f"  - {msg}")
    print("\nEmbedded subtitle fallback:")
    print(f"  extracted: {len(written)} file(s)")
    if skipped:
        print(f"  already existed: {len(skipped)} file(s)")
    if converted:
        print(f"  converted to SRT for translation: {len(converted)} file(s)")
    if srt_sources:
        print("  SRT source files now available:")
        for path in srt_sources[:8]:
            print(f"    - {path.name}")
        if len(srt_sources) > 8:
            print(f"    ... and {len(srt_sources) - 8} more")
        return True
    print("  No SRT source files became available; downstream translation may still have no source.")
    return False


def modify_main(argv: list[str]) -> int:
    # --subdirectory: walk each PATH's immediate subdirs, run modify per
    # subdir. Same op set per show; useful for per-show progress / isolation
    # since modify already walks recursively within each PATH.
    if "--subdirectory" in argv:
        sub_argv = _strip_flag(argv, "--subdirectory")
        parsed = build_modify_parser().parse_args(sub_argv + ["--subdirectory"])
        rc_total = 0
        printed_any = False
        for root_str in parsed.paths:
            root = Path(root_str).expanduser()
            if not root.is_dir():
                print(f"  (skip) {root_str}: not a directory")
                continue
            subdirs = _immediate_subdirs(root)
            if not subdirs:
                print(f"  (skip) {root_str}: no subdirectories found")
                continue
            for sub in subdirs:
                if printed_any:
                    print()
                printed_any = True
                print(f"━━ modify {root.name}/{sub.name} ━━")
                rc = modify_main(_replace_paths_in_argv(sub_argv, parsed.paths, str(sub)))
                rc_total = rc or rc_total
        return rc_total
    args = build_modify_parser().parse_args(argv)
    # --reading is the multi-language umbrella. Route ja entries
    # to the legacy --furigana attribute and ko entries to a fresh
    # args.ko_reading attribute. Languages we haven't shipped a
    # backend for raise "not yet implemented" inside _apply_reading_to_args.
    _apply_reading_to_args(args)
    args.ko_reading = getattr(args, "ko_reading", None)
    args.zh_reading = getattr(args, "zh_reading", None)
    args.yue_reading = getattr(args, "yue_reading", None)
    convert_op, convert_langs = parse_convert_spec(args.convert)
    ops_selected = [
        bool(args.strip_cc_noise),
        bool(args.single_line),
        bool(args.ja_reading),
        bool(args.ko_reading),
        bool(args.zh_reading),
        bool(args.yue_reading),
        bool(convert_op),
        bool(args.extract_mkv_subs),
    ]
    if not any(ops_selected):
        raise CliError(
            "modify needs at least one operation flag: "
            "--strip-cc-noise, --single-line, --reading SPEC, "
            "--convert smi-to-srt, and/or --extract-mkv-subs."
        )
    # Validate --reading-format upfront so a bad value errors before the
    # plan is printed and any work happens. Cached so the inner loop reuses it.
    # The same setting drives ja furigana variants and ko romanization variants.
    reading_formats = (
        parse_furigana_formats(getattr(args, "reading_format", None))
        if (args.ja_reading or args.ko_reading or args.zh_reading or args.yue_reading)
        else None
    )

    paths = [Path(p).expanduser() for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise CliError("Path not found: " + ", ".join(str(p) for p in missing))

    # The in-place ops (strip-cc-noise, single-line, furigana) walk .srt files.
    # The convert op walks .smi files. Both share PATH discovery but scan
    # different extensions, so we run two separate scans here.
    inplace_ops = bool(
        args.strip_cc_noise
        or args.single_line
        or args.ja_reading
        or args.ko_reading
        or args.zh_reading
        or args.yue_reading
    )
    scanned: list[tuple[Path, int, int, str, bool]] = (
        scan_srt_files(paths) if inplace_ops else []
    )
    convert_files: list[Path] = (
        scan_smi_files(paths) if convert_op == "smi-to-srt" else []
    )
    video_files: list[Path] = scan_video_files(paths) if args.extract_mkv_subs else []
    selected_keys: set[tuple[int, int]] | None = None
    if str(args.season).lower() not in {"all", "auto"} or str(args.episode).lower() not in {"all", "auto"}:
        detected_keys = {(season, episode) for _path, season, episode, _lang, _is_mt in scanned}
        detected_keys.update(
            ep for ep in (parse_episode_marker(path.name) for path in convert_files + video_files)
            if ep is not None
        )
        selected_keys = set(filter_episode_keys(detected_keys, season=args.season, episode=args.episode))
        scanned = [row for row in scanned if (row[1], row[2]) in selected_keys]
        convert_files = [
            path for path in convert_files
            if (parse_episode_marker(path.name) in selected_keys)
        ]
        video_files = [
            path for path in video_files
            if (parse_episode_marker(path.name) in selected_keys)
        ]
    extract_plan: list[tuple[Path, int, str, str, Path]] = []
    extract_notes: list[str] = []
    if args.extract_mkv_subs:
        extract_plan, extract_notes = plan_mkv_subtitle_extraction(video_files)

    if inplace_ops:
        print(f"Scanned: {len(scanned)} SRT file(s) across {len(paths)} path(s)")
    if convert_op == "smi-to-srt":
        print(f"Scanned: {len(convert_files)} SMI file(s) across {len(paths)} path(s)")
    if args.extract_mkv_subs:
        print(f"Scanned: {len(video_files)} video file(s) across {len(paths)} path(s)")

    if not scanned and not convert_files and not extract_plan:
        if args.extract_mkv_subs and extract_notes:
            print("No extractable text subtitle streams found.")
            for note in extract_notes[:20]:
                print(f"  {note}")
        elif args.convert and not inplace_ops:
            print("No .smi files found. Nothing to convert.")
        elif inplace_ops and not args.convert:
            print("No single-language SRT files found. Nothing to process.")
        else:
            print("No SRT, SMI, or extractable MKV subtitle streams found. Nothing to process.")
        return 1

    # Describe the plan up front so --dry-run is meaningful.
    ops_desc: list[str] = []
    if convert_op == "smi-to-srt":
        if convert_langs:
            ops_desc.append(f"convert smi → srt ({','.join(sorted(convert_langs))} only)")
        else:
            ops_desc.append("convert smi → srt")
    if args.extract_mkv_subs:
        ops_desc.append("extract embedded text subtitles from video")
    if args.strip_cc_noise:
        ops_desc.append("strip CC noise")
    if args.single_line:
        ops_desc.append("flatten single-line")
    if args.ja_reading:
        ops_desc.append(f"furigana ({args.ja_reading})")
    if args.ko_reading:
        ops_desc.append(f"korean romanization ({args.ko_reading})")
    if args.zh_reading:
        ops_desc.append(f"chinese pinyin ({args.zh_reading})")
    if args.yue_reading:
        ops_desc.append(f"cantonese jyutping ({args.yue_reading})")
    print("Operations: " + ", ".join(ops_desc))

    if inplace_ops:
        # Reading aids are scoped to their language's .srt files; pre-compute
        # each subset so the summary doesn't double-count or mislead.
        ja_paths = [t[0] for t in scanned if t[3] == "ja"]
        ko_paths = [t[0] for t in scanned if t[3] == "ko"]
        zh_paths = [t[0] for t in scanned if t[3] == "zh"]
        yue_paths = [t[0] for t in scanned if t[3] == "yue"]
        if args.ja_reading and not ja_paths:
            print("(--reading ja:* requested but no .ja.srt files found; that step will be a no-op.)")
        if args.ko_reading and not ko_paths:
            print("(--reading ko:* requested but no .ko.srt files found; that step will be a no-op.)")
        if args.zh_reading and not zh_paths:
            print("(--reading zh:* requested but no .zh.srt files found; that step will be a no-op.)")
        if args.yue_reading and not yue_paths:
            print("(--reading yue:* requested but no .yue.srt files found; that step will be a no-op.)")

        print(f"\nPlanned in-place: {len(scanned)} file(s)")
        for path, _season, _episode, lang, _is_mt in scanned[:20]:
            if args.ja_reading and lang == "ja":
                suffix = "  [ja → furigana variants]"
            elif args.ko_reading and lang == "ko":
                suffix = "  [ko → romanization variants]"
            elif args.zh_reading and lang == "zh":
                suffix = "  [zh → pinyin variants]"
            elif args.yue_reading and lang == "yue":
                suffix = "  [yue → jyutping variants]"
            else:
                suffix = ""
            print(f"  {path.name}{suffix}")
        if len(scanned) > 20:
            print(f"  ... and {len(scanned) - 20} more")

    if convert_files:
        print(f"\nPlanned convert: {len(convert_files)} .smi file(s)")
        scope = f"  [{','.join(sorted(convert_langs))} only]" if convert_langs else ""
        for path in convert_files[:20]:
            print(f"  {path.name}{scope}")
        if len(convert_files) > 20:
            print(f"  ... and {len(convert_files) - 20} more")

    if args.extract_mkv_subs:
        print(f"\nPlanned MKV/video subtitle extraction: {len(extract_plan)} stream(s)")
        for video, stream_index, lang, codec, dest in extract_plan[:20]:
            exists = "  [exists; use --force]" if dest.exists() and not args.force else ""
            print(f"  {video.name} stream {stream_index} ({lang}, {codec}) -> {dest.name}{exists}")
        if len(extract_plan) > 20:
            print(f"  ... and {len(extract_plan) - 20} more")
        if extract_notes:
            print("  Notes:")
            for note in extract_notes[:10]:
                print(f"    - {note}")

    if args.dry_run:
        return 0

    touched_in_place = 0
    furigana_generated: list[Path] = []
    korean_generated: list[Path] = []
    chinese_generated: list[Path] = []
    cantonese_generated: list[Path] = []
    grouped_errors: dict[str, list[str]] = {}
    convert_written: list[Path] = []
    convert_skipped: list[Path] = []

    if convert_files:
        print("\nConverting SMI:")
        for idx, smi in enumerate(convert_files, start=1):
            progress_bar(idx, len(convert_files), "converting", smi.name, transient=True)
            try:
                written, skipped = convert_smi_file(smi, force=args.force, only_langs=convert_langs)
            except CliError as e:
                # CliError carries "<name>: <reason>"; strip the name to group.
                msg = str(e)
                prefix = f"{smi.name}: "
                key = msg[len(prefix):] if msg.startswith(prefix) else msg
                grouped_errors.setdefault(key, []).append(smi.name)
                continue
            convert_written.extend(written)
            convert_skipped.extend(skipped)

    if inplace_ops and convert_written:
        seen_paths = {row[0] for row in scanned}
        for path in convert_written:
            parsed = parse_srt_filename(path.name)
            if parsed is None:
                continue
            season, episode, _lang, _is_mt = parsed
            if selected_keys is not None and (season, episode) not in selected_keys:
                continue
            if path not in seen_paths:
                scanned.append((path, *parsed))
                seen_paths.add(path)

    if inplace_ops:
        print("\nProcessing SRT:")
        # Order matches the download flow: strip-cc-noise -> single-line ->
        # reading-aid side files. First two are idempotent in-place rewrites;
        # reading aids (furigana for ja, romanization for ko, pinyin for zh)
        # write side files.
        for idx, (path, _season, _episode, lang, _is_mt) in enumerate(scanned, start=1):
            progress_bar(idx, len(scanned), "processing", path.name, transient=True)
            before = path.read_bytes() if path.exists() else b""
            try:
                if args.strip_cc_noise:
                    strip_cc_noise_in_place(path)
                if args.single_line:
                    flatten_srt_in_place(path, separator=flatten_separator_for(path))
                if args.ja_reading and lang == "ja":
                    for mode in (getattr(args, "ja_readings", None) or [args.ja_reading]):
                        furigana_generated.extend(
                            generate_furigana(
                                [path], mode, bool(args.single_line),
                                formats=reading_formats,
                            )
                        )
                if args.ko_reading and lang == "ko":
                    for mode in (getattr(args, "ko_readings", None) or [args.ko_reading]):
                        korean_generated.extend(
                            generate_korean_romanization(
                                [path], mode, bool(args.single_line),
                                formats=reading_formats,
                            )
                        )
                if args.zh_reading and lang == "zh":
                    chinese_generated.extend(
                        generate_chinese_romanization(
                            [path], args.zh_reading, bool(args.single_line),
                            formats=reading_formats,
                        )
                    )
                if args.yue_reading and lang == "yue":
                    cantonese_generated.extend(
                        generate_cantonese_romanization(
                            [path], args.yue_reading, bool(args.single_line),
                            formats=reading_formats,
                        )
                    )
            except CliError as e:
                grouped_errors.setdefault(str(e), []).append(path.name)
                continue
            after = path.read_bytes() if path.exists() else b""
            if before != after:
                touched_in_place += 1

    extract_written: list[Path] = []
    extract_skipped: list[Path] = []
    extract_errors: list[str] = []
    if extract_plan:
        print("\nExtracting embedded subtitles:")
        try:
            extract_written, extract_skipped, extract_errors = extract_mkv_subtitle_plan(
                extract_plan, force=args.force
            )
        except CliError as e:
            grouped_errors.setdefault(str(e), []).append("ffmpeg")
        for msg in extract_errors:
            grouped_errors.setdefault(msg, []).append("ffmpeg")

    if grouped_errors:
        print(f"\nErrors ({sum(len(v) for v in grouped_errors.values())}):")
        for msg, files in grouped_errors.items():
            if len(files) == 1:
                print(f"  {files[0]}: {msg}")
            else:
                preview = files[:5]
                more = f" (+{len(files) - len(preview)} more)" if len(files) > len(preview) else ""
                print(f"  {len(files)} file(s) [{', '.join(preview)}{more}]: {msg}")

    print()
    if args.strip_cc_noise or args.single_line:
        print(f"In-place rewrites: {touched_in_place} file(s) changed.")
    if args.ja_reading:
        print(f"Furigana variants generated: {len(furigana_generated)}")
    if args.ko_reading:
        print(f"Korean romanization variants generated: {len(korean_generated)}")
    if args.zh_reading:
        print(f"Chinese pinyin variants generated: {len(chinese_generated)}")
    if args.yue_reading:
        print(f"Cantonese Jyutping variants generated: {len(cantonese_generated)}")
    if convert_op == "smi-to-srt":
        skipped_note = (
            f" ({len(convert_skipped)} skipped — output exists, pass --force to overwrite)"
            if convert_skipped else ""
        )
        print(f"SRT files written from SMI: {len(convert_written)}{skipped_note}")
    if args.extract_mkv_subs:
        skipped_note = (
            f" ({len(extract_skipped)} skipped — output exists, pass --force to overwrite)"
            if extract_skipped else ""
        )
        print(f"Subtitle files extracted from video: {len(extract_written)}{skipped_note}")
    return 0


# ===========================================================================
# batch subcommand — walk a library, fetch / merge per auto-detected profile
# ===========================================================================
# Two sub-actions:
#   batch fetch  — walks CWD (or --root), per show folder: derive title,
#                  detect origin language via TMDB original_language,
#                  shell out to `getsubtitle URL=None --title <T> -l <L>` with
#                  the right language set, optionally MT fallback via Ollama.
#   batch merge  — walks CWD, per show folder: smi-to-srt convert, then
#                  combine per profile (ja/ko master + furigana; en master
#                  produces both en+es dual and ja+ko+en+es quad).
#
# Profile detection is fully runtime — no reference.json needed. TMDB key is
# strongly recommended; without it, batch falls back to a char-set heuristic
# (Japanese kana → ja; Hangul-only → ko; otherwise → en). The heuristic
# correctly handles the common "Japanese anime stored in a Korean folder"
# case via the TMDB lookup, which knows the show's true origin language.

_BATCH_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".webm", ".m2ts", ".ts", ".wmv", ".mov", ".m4v"}
_BATCH_SUBTITLE_EXTS = {".srt", ".smi", ".ass", ".vtt", ".ssa"}


def _has_kana(text: str) -> bool:
    """True if text contains Hiragana or Katakana — a strong signal that the
    show is Japanese-origin (Korean / English titles never use these)."""
    return any("぀" <= c <= "ゟ" or "゠" <= c <= "ヿ" for c in text)


def _has_hangul(text: str) -> bool:
    """True if text contains Hangul syllables."""
    return any("가" <= c <= "힯" for c in text)


_PROFILE_CACHE: dict[str, str] = {}


def detect_profile_from_title(title: str, year: int | None = None) -> str:
    """Return 'ja' | 'ko' | 'en' based on TMDB's original_language for the
    show, with a quick character-set shortcut and fallback when no TMDB
    key is configured.

    Cached per title for the lifetime of the process."""
    cache_key = f"{title}|{year or ''}"
    if cache_key in _PROFILE_CACHE:
        return _PROFILE_CACHE[cache_key]

    # Fast path: native Japanese characters → definitely ja-origin.
    if _has_kana(title):
        _PROFILE_CACHE[cache_key] = "ja"
        return "ja"

    # Try TMDB if available — it knows the true origin language even when
    # the folder name is in Korean / English for a Japanese show.
    api_key = get_provider_api_key("tmdb")
    if api_key:
        hit = (tmdb_search_tv(title, api_key=api_key)
               or tmdb_search_movie(title, year=year, api_key=api_key))
        if hit:
            lang = (hit.get("original_language") or "").lower()
            if lang == "ja":
                _PROFILE_CACHE[cache_key] = "ja"
                return "ja"
            if lang == "ko":
                _PROFILE_CACHE[cache_key] = "ko"
                return "ko"
            _PROFILE_CACHE[cache_key] = "en"
            return "en"

    # No TMDB / no hit → guess from character set. Korean folder names are
    # common in the project's primary use case, so Hangul-only → ko is a
    # reasonable last-resort default.
    if _has_hangul(title):
        _PROFILE_CACHE[cache_key] = "ko"
        return "ko"
    _PROFILE_CACHE[cache_key] = "en"
    return "en"


_SEASON_FOLDER_PATTERNS = (
    # English: "Season 01", "Season 1", "Season 5"
    re.compile(r"^season\s*0*(\d+)$", re.I),
    # Korean: "1기", "2기" (literally "N-th season")
    re.compile(r"^(\d+)\s*기$"),
    # Compact: "S01", "S1", "s02"
    re.compile(r"^s\s*0*(\d+)$", re.I),
)


def parse_season_from_folder_name(name: str) -> int | None:
    """Pull a season number out of a Plex-style season subfolder name.
    Returns None when the folder name doesn't match a known season pattern
    (i.e. when the folder IS the show, not a season subdir)."""
    stripped = name.strip()
    for pat in _SEASON_FOLDER_PATTERNS:
        m = pat.match(stripped)
        if m:
            return int(m.group(1))
    return None


def detect_show_and_season(folder: "Path", root: "Path") -> tuple["Path", int | None]:
    """Given a leaf folder containing video files, decide which folder is
    the SHOW and what season number this is. Handles three layouts:
      Show/Season 01/        → show=Show, season=1
      Show/1기/              → show=Show, season=1 (Korean form)
      Show/                  → show=Show, season=None (single-folder shows)
    """
    season = parse_season_from_folder_name(folder.name)
    if season is not None and folder.parent != root and folder.parent.exists():
        return folder.parent, season
    return folder, None


def detect_show_and_season_for_video_file(video: "Path") -> tuple["Path", int | None]:
    """Infer show/season for one explicit video file path.

    Handles Plex-style `Show/Season 01/Episode.mkv` by using the parent show
    folder as the title. Falls back to the containing folder for flat layouts.
    """
    folder = video.parent
    season = parse_season_from_folder_name(folder.name)
    if season is not None and folder.parent.exists():
        return folder.parent, season
    parsed = parse_episode_marker(video.name)
    if parsed is not None:
        parsed_season, _episode = parsed
        if parsed_season > 0:
            return folder, parsed_season
    return folder, None


def _batch_find_video_folders(root: "Path") -> list["Path"]:
    """Return SUB-folders under root that directly contain video files.

    Skips `root` itself — videos sitting at the top level are handled by
    `_batch_find_bare_video_files` so they don't get double-counted (and
    so the library root isn't treated as a show folder)."""
    folders: set["Path"] = set()
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in _BATCH_VIDEO_EXTS:
            if p.parent == root:
                continue
            folders.add(p.parent)
    return sorted(folders)


def _batch_find_bare_video_files(root: "Path") -> list["Path"]:
    """Top-level loose video files (e.g. one-off movies dumped at root)."""
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in _BATCH_VIDEO_EXTS
    )


def _directory_has_direct_video_files(root: "Path") -> bool:
    return root.is_dir() and any(
        p.is_file() and p.suffix.lower() in _BATCH_VIDEO_EXTS
        for p in root.iterdir()
    )


def _batch_list_smi_files(folder: "Path") -> list["Path"]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() == ".smi")


def _batch_run(cmd: list[str], dry_run: bool) -> int:
    """Run a getsubtitle subprocess, printing the shell-quoted command first.
    Used so the user can copy-paste any single line if something looks off."""
    args = list(cmd)
    if dry_run and "--dry-run" not in args:
        args.append("--dry-run")
    print("  $ " + " ".join(shlex.quote(a) for a in args))
    return subprocess.run(args, check=False).returncode


def _batch_heading(text: str) -> None:
    bar = "─" * max(40, len(text))
    print()
    print(bar)
    print(text)
    print(bar)


# Per-profile fetch language preference. Order matters — first to succeed
# is what providers return; MT fallback fills any that come back empty.
_BATCH_FETCH_LANGS = {
    "ja": ["ko"],          # JP master → fetch Korean
    "ko": ["ja"],          # KR master → fetch Japanese
    "en": ["es", "ko"],    # EN master → fetch Spanish + Korean
}
_BATCH_MT_SOURCE = {"ja": "ja", "ko": "ko", "en": "en"}


def _batch_fetch_langs_from_rest(rest: list[str]) -> list[str] | None:
    """Return explicit -l/--languages from fetch PATH residual args.

    PATH fetch has an older profile mode where languages are chosen from
    `_BATCH_FETCH_LANGS`. Pipeline/wizard calls pass `--languages` explicitly;
    that user choice must override profile defaults.
    """
    for i, tok in enumerate(rest):
        if tok in ("-l", "--langs", "--lang", "--languages") and i + 1 < len(rest):
            langs = split_csv(rest[i + 1], "")
            return langs or None
        for flag in ("--langs=", "--lang=", "--languages="):
            if tok.startswith(flag):
                langs = split_csv(tok.split("=", 1)[1], "")
                return langs or None
    return None


def build_fetch_parser() -> argparse.ArgumentParser:
    """Parser for the `fetch` subcommand.

    `fetch` accepts either a URL (resolves IDs from the URL and fetches
    matching subtitles — equivalent to typing `getsubtitle URL ...`) or
    a PATH. With a PATH, it treats the folder as one show and runs the
    per-show download per detected profile. Add --subdirectory to walk
    one level of subdirs and treat each as its own show."""
    p = argparse.ArgumentParser(
        prog="getsubtitle fetch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Download subtitles for a URL or for folder(s) on disk. "
            "Accepts URL (existing download flow), PATH (treat folder "
            "as one show), or PATH with --subdirectory (treat each "
            "immediate subdir as its own show)."
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              # URL — identical to typing `getsubtitle URL ...`
              getsubtitle fetch "https://www.imdb.com/title/tt28299608/" -l ja,ko

              # PATH single show
              getsubtitle fetch ~/Downloads/GetSubtitle/MF\\ Ghost

              # PATH library, every immediate subdir = a show
              getsubtitle fetch ~/Downloads/GetSubtitle --subdirectory --run

            Profiles (auto-detected from TMDB original_language; override with --profile):
              ja  Japanese-origin → fetch ko; MT ja→ko fallback
              ko  Korean-origin   → fetch ja; MT ko→ja fallback
              en  English / other → fetch es+ko; MT from en fallback
            """
        ),
        add_help=False,
    )
    p.add_argument("target", help="URL or PATH (file or directory).")
    p.add_argument("--subdirectory", action="store_true",
                   help="PATH only: walk each immediate subdir and treat it as a separate show.")
    p.add_argument("--profile", default=None, choices=["ja", "ko", "en"],
                   help="PATH only: override auto-detected profile for every show.")
    p.add_argument("--run", action="store_true",
                   help="PATH only: actually run. Default is dry-run.")
    p.add_argument("-h", "--help", action="store_true",
                   help="Show this help.")
    return p


def fetch_main(argv: list[str]) -> int:
    """`fetch` subcommand: URL → resolve IDs and download from providers;
    PATH → folder-based bulk fetch (single show without --subdirectory;
    many shows with it)."""
    # Empty / explicit-help → show the topic page.
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP_TOPICS["fetch"])
        return 0

    parser = build_fetch_parser()
    args, rest = parser.parse_known_args(argv)
    if args.help:
        sys.stdout.write(HELP_TOPICS["fetch"])
        return 0

    # URL form: delegate to the bare-URL download flow with all the
    # rest-args passed through (-l, -s, -e, --furigana, etc.).
    if _looks_like_url(args.target):
        if args.subdirectory:
            raise CliError("--subdirectory only applies to PATH targets, not URLs.")
        return main([args.target] + rest)

    # PATH form.
    target_path = Path(args.target).expanduser()
    if not target_path.exists():
        raise CliError(f"path not found: {target_path}")

    if args.subdirectory:
        if not target_path.is_dir():
            raise CliError(f"--subdirectory requires a directory: {target_path}")
        roots = _immediate_subdirs(target_path)
        if not roots:
            print(f"No subdirectories found under {target_path}")
            return 1
    else:
        roots = [target_path]

    dry_run = not args.run

    mode = "DRY RUN (no writes)" if dry_run else "LIVE"
    print(f"fetch — root: {target_path}")
    print(f"mode: {mode}")
    requested_langs = _batch_fetch_langs_from_rest(rest)

    if args.profile:
        print(f"profile override: {args.profile}")
    if requested_langs:
        print(f"requested languages: {','.join(requested_langs)}")
    elif not get_provider_api_key("tmdb"):
        print("note: no TMDB key — profile detection falls back to char-set heuristics.")
        print("      Set one with: getsubtitle --set-key tmdb")

    total_targets = 0
    rc_total = 0
    for show in roots:
        # Each `show` is one show folder (or one bare file). Walk inside
        # to find video-bearing folders / loose files; reuse the batch
        # walker since it already handles Plex Season subdirs.
        if show.is_dir():
            if _directory_has_direct_video_files(show):
                show_folder, season = detect_show_and_season_for_video_file(
                    next(p for p in show.iterdir() if p.is_file() and p.suffix.lower() in _BATCH_VIDEO_EXTS)
                )
                targets = [(show, show_folder, season)]
            else:
                targets = _batch_walk_targets(show)
            if not targets:
                # No video files found anywhere inside — treat the show
                # folder itself as the target (user may want to download
                # before videos exist).
                targets = [(show, show, None)]
        else:
            show_folder, season = detect_show_and_season_for_video_file(show)
            targets = [(show, show_folder, season)]
        for target, show_folder, season in targets:
            profile = args.profile or detect_profile_from_title(show_folder.name)
            rc = _batch_fetch_one(
                target=target, show_folder=show_folder, season=season,
                profile=profile, dry_run=dry_run,
                fetch_langs_override=requested_langs,
            )
            rc_total = rc or rc_total
            total_targets += 1

    print()
    print(f"Processed {total_targets} target(s).")
    return rc_total


def build_merge_parser() -> argparse.ArgumentParser:
    """Parser for the `merge` subcommand. Internally still implemented
    on top of build_combine_parser() since the flag surface is identical."""
    p = build_combine_parser()
    p.prog = "getsubtitle merge"
    return p


def merge_main(argv: list[str]) -> int:
    """`merge` subcommand. Internally dispatched through combine_main
    (which carries the --subdirectory wrapper and the core algorithm)."""
    return combine_main(argv)


def _batch_describe_target(target: "Path", show_folder: "Path", season: int | None,
                            profile: str) -> str:
    name = str(target)
    if show_folder != target:
        name = f"{show_folder.name}  ({target.name})"
    else:
        name = show_folder.name
    s = f" S{season:02d}" if season is not None else ""
    return f"[{profile}]{s}  {name}"


def _batch_fetch_one(target: "Path", show_folder: "Path", season: int | None,
                     profile: str, dry_run: bool,
                     fetch_langs_override: list[str] | None = None) -> int:
    """Run fetch for one disk target (folder or bare file).

    Fetch-only — does NOT auto-translate. Users wanting MT to fill missing
    languages chain it via the pipeline form:
      getsubtitle --fetch PATH --subdirectory --translate ollama
    """
    _batch_heading(_batch_describe_target(target, show_folder, season, profile))

    title = show_folder.stem if show_folder.is_file() else show_folder.name
    is_folder = target.is_dir()
    output_dir = target if is_folder else target.parent

    fetch_langs = fetch_langs_override or _BATCH_FETCH_LANGS.get(profile, _BATCH_FETCH_LANGS["en"])
    episode_arg = "all"
    parsed_episode = parse_episode_marker(target.name) if target.is_file() else None
    if parsed_episode is not None:
        parsed_season, parsed_ep = parsed_episode
        if season is None and parsed_season > 0:
            season = parsed_season
        if parsed_ep > 0:
            episode_arg = str(parsed_ep)

    fetch_cmd = [
        sys.executable, "-m", "getsubtitle",
    ] if not shutil.which("getsubtitle") else ["getsubtitle"]
    fetch_cmd += ["--title", title]
    if season is not None:
        fetch_cmd += ["-s", str(season)]
    fetch_cmd += ["-e", episode_arg, "-l", ",".join(fetch_langs),
                  "--layout", "flat", "-o", str(output_dir), "-y"]
    suffix = " (requested)" if fetch_langs_override else ""
    print(f"  fetch: -l {','.join(fetch_langs)}{suffix}")
    rc = _batch_run(fetch_cmd, dry_run=dry_run)
    if rc and not dry_run:
        if maybe_extract_embedded_subtitles_after_fetch_miss(target):
            return 0
    return rc


def _batch_merge_one(target: "Path", show_folder: "Path", season: int | None,
                     profile: str, fmt: str | None, dry_run: bool) -> None:
    """Run smi-to-srt + combine for one folder."""
    if not target.is_dir():
        return  # combine works on folders, not bare files
    _batch_heading(_batch_describe_target(target, show_folder, season, profile))

    # Step 1: convert any .smi present to .ko.srt (no-op if none).
    smis = _batch_list_smi_files(target)
    if smis:
        convert_cmd = (["getsubtitle"] if shutil.which("getsubtitle")
                       else [sys.executable, "-m", "getsubtitle"])
        convert_cmd += ["modify", str(target), "--convert", "smi-to-srt", "--force"]
        print(f"  smi→srt: {len(smis)} .smi file(s)")
        _batch_run(convert_cmd, dry_run=dry_run)

    base = (["getsubtitle"] if shutil.which("getsubtitle")
            else [sys.executable, "-m", "getsubtitle"])

    def merge(langs: list[str], master: str, with_furigana: bool, label: str) -> None:
        cmd = base + ["merge", str(target), "-l", ",".join(langs), "--master", master]
        if with_furigana:
            cmd.append("--furigana")
        if fmt:
            cmd += ["--format", fmt]
        print(f"  merge ({label}): -l {','.join(langs)}  master={master}"
              + ("  +furigana" if with_furigana else ""))
        _batch_run(cmd, dry_run=dry_run)

    if profile == "ja":
        merge(["ja", "ko"], master="ja", with_furigana=True, label="JP master dual")
    elif profile == "ko":
        merge(["ko", "ja"], master="ko", with_furigana=True, label="KR master dual")
        merge(["ko", "ja", "en", "es"], master="ko", with_furigana=True, label="KR master quad")
    else:  # en (and zh/fr/etc treated as en for our workflow)
        merge(["en", "es"], master="en", with_furigana=False, label="EN master dual")
        merge(["ja", "ko", "en", "es"], master="en", with_furigana=True, label="EN master quad")


def _looks_like_url(s: str) -> bool:
    """True if `s` looks like a URL (http/https). Used by fetch to route
    URL → URL-form download vs. PATH → folder-based bulk mode."""
    return s.startswith(("http://", "https://", "HTTP://", "HTTPS://", "title://"))


def _expand_url_form_season_range(argv: list[str]) -> list[list[str]] | None:
    """If argv contains `--season 1-2` (or `-s 1,2,3`) with a multi-season
    range/list, return a list of argv copies, each with one expanded season.
    Returns None for single-season, "all", or "auto" — caller continues
    with the original argv unchanged.

    Only used for the URL-form download flow. The PATH-based subcommands
    (translate, merge, modify, fetch PATH) already accept ranges via
    parse_episode_selector inside filter_episode_keys.
    """
    for i, tok in enumerate(argv):
        if tok in ("-s", "--season") and i + 1 < len(argv):
            value = argv[i + 1].strip()
            if value.lower() in ("all", "auto") or value.isdigit():
                return None
            try:
                seasons = parse_episode_selector(value)
            except (ValueError, TypeError):
                return None
            if len(seasons) <= 1 or seasons in (["all"], ["auto"]):
                return None
            expanded: list[list[str]] = []
            for s in seasons:
                sub = list(argv)
                sub[i + 1] = s
                expanded.append(sub)
            return expanded
    return None


def _immediate_subdirs(root: "Path") -> list["Path"]:
    """Sorted immediate subdirectories of root. Used by --subdirectory mode
    to iterate one level deep per show."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def _strip_flag(argv: list[str], flag: str) -> list[str]:
    """Return argv with all occurrences of `flag` removed (use for boolean
    --subdirectory style flags that take no value)."""
    return [a for a in argv if a != flag]


def _replace_paths_in_argv(argv: list[str], old_paths: list[str], new_path: str) -> list[str]:
    """Replace the first occurrence of any path in `old_paths` with new_path
    in argv, dropping the rest. Other arguments preserved in order."""
    out: list[str] = []
    seen_first = False
    for a in argv:
        if a in old_paths and not seen_first:
            out.append(new_path)
            seen_first = True
        elif a in old_paths:
            continue  # drop duplicate paths
        else:
            out.append(a)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Pipeline form: getsubtitle [--fetch X opts] [--translate ENGINE opts]
#                            [--modify opts] [--merge opts] [--output PATH]
# Verbs run in canonical order regardless of typing order:
#   fetch → translate → modify → merge
# ─────────────────────────────────────────────────────────────────────────

PIPELINE_VERB_FLAGS = ("--fetch", "--translate", "--modify", "--merge")
PIPELINE_SHARED_FLAGS = {"--output", "--dry-run", "--config"}


def _is_pipeline_argv(argv: list[str]) -> bool:
    """True if argv contains any pipeline verb flag — caller routes to
    pipeline_main instead of the single-verb subcommand dispatch."""
    return any(a in PIPELINE_VERB_FLAGS for a in argv)


# Pipeline-shared flags that are global regardless of position in argv.
# Users tend to write them at the end of long commands (after the last
# verb block), so we extract them out of whichever verb block they
# accidentally land in and put them in "shared".
_PIPELINE_GLOBAL_VALUED_FLAGS = {"--output", "--source"}     # take next token as value
_PIPELINE_GLOBAL_BOOL_FLAGS = {"--dry-run", "--force", "--no-open-folder-prompt"}


def split_pipeline_argv(argv: list[str]) -> dict[str, list[str]]:
    """Split argv into per-verb blocks by scanning for verb-flag boundaries.

    Returns a dict like:
      {"shared": [...], "fetch": [...], "translate": [...], ...}
    where each verb's list is its private flag/positional block (NOT
    including the verb flag itself). Args appearing before any verb flag
    go into "shared".

    `--output PATH`, `--dry-run`, and `--force` are always treated as
    shared pipeline flags regardless of where they appear in argv —
    users typically write them at the end (after the last verb block),
    which would otherwise misroute them.

    Example:
      argv = ["--fetch", "URL", "-l", "ja",
              "--merge", "-l", "ja,en", "--format", "vtt",
              "--output", "/tmp/out"]
      → {"shared": ["--output", "/tmp/out"],
         "fetch":  ["URL", "-l", "ja"],
         "merge":  ["-l", "ja,en", "--format", "vtt"]}
    """
    blocks: dict[str, list[str]] = {"shared": []}
    current = "shared"
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in PIPELINE_VERB_FLAGS:
            current = tok[2:]  # "--fetch" → "fetch"
            blocks.setdefault(current, [])
            i += 1
            continue
        # Globally-shared valued flag (e.g. --output PATH): consume the
        # following token as its value and place the pair in "shared".
        if tok in _PIPELINE_GLOBAL_VALUED_FLAGS and i + 1 < len(argv):
            blocks["shared"].extend([tok, argv[i + 1]])
            i += 2
            continue
        # Globally-shared bool flag (e.g. --dry-run, --force).
        if tok in _PIPELINE_GLOBAL_BOOL_FLAGS:
            blocks["shared"].append(tok)
            i += 1
            continue
        blocks[current].append(tok)
        i += 1
    return blocks


def _parse_engine_spec(spec: str) -> tuple[str, str | None]:
    """Split an engine spec like "ollama:qwen3:8b" into (engine, model).
    Bare "ollama" or "argos"/"deepl" → (engine, None). Empty string → ("", None).
    Anything else with a colon → first segment is engine, rest is model.
    Engine must be one of argos/ollama/deepl (or empty)."""
    if not spec:
        return ("", None)
    engine, sep, model = spec.partition(":")
    engine = engine.strip().lower()
    if engine not in ("argos", "ollama", "deepl"):
        raise CliError(
            f"Unknown engine: {engine!r}. Use argos, ollama[:model], or deepl. "
            "Pass an empty string to disable."
        )
    return (engine, model if sep else None)


def _rewrite_translate_block(block: list[str]) -> list[str]:
    """Pipeline `--translate ENGINE [opts]` → translate_main argv flags.

    ENGINE is the first non-flag token in the block. It's stripped and
    rewritten as `--engine ENGINE` (with `--model NAME` appended if
    the spec was `engine:model`). Empty string → `--no-mt-engine`.

    Other tokens pass through unchanged so existing flags like
    --mt-source, --force, --dry-run still work.
    """
    if not block:
        raise CliError(
            "--translate needs an engine. Use --translate argos, "
            "--translate ollama[:model], or --translate deepl."
        )
    # First non-flag token is the engine spec.
    engine_spec = block[0]
    if engine_spec.startswith("-"):
        raise CliError(
            "--translate needs an engine before its options. "
            "Example: --translate ollama --mt-source en"
        )
    engine, model = _parse_engine_spec(engine_spec)
    rest = block[1:]
    rewritten: list[str] = []
    if engine == "":
        rewritten += ["--no-mt-engine"]
    else:
        rewritten += ["--engine", engine]
        if model:
            rewritten += ["--model", model]
    rewritten += rest
    return rewritten


def _pipeline_resolve_target(fetch_block: list[str]) -> tuple[str | None, list[str]]:
    """Pull TARGET out of the --fetch block. TARGET is the first non-flag
    token. Returns (target, remaining_fetch_options). target=None means
    no fetch verb in this pipeline."""
    if not fetch_block:
        raise CliError(
            "--fetch needs a TARGET (URL or PATH). "
            "Example: --fetch https://... or --fetch /Plex/Anime --subdirectory"
        )
    if fetch_block[0].startswith("-"):
        for title_flag in ("--title", "-title"):
            if title_flag in fetch_block:
                idx = fetch_block.index(title_flag)
                if idx + 1 >= len(fetch_block):
                    raise CliError("--fetch --title needs a movie/show title.")
                title = fetch_block[idx + 1]
                remaining = fetch_block[:idx] + fetch_block[idx + 2:]
                return (title_source_url(title), remaining + ["--title", title])
        raise CliError(
            "--fetch needs a TARGET (URL or PATH), or use --fetch --title \"Show Name\"."
        )
    target = fetch_block[0]
    return (target, fetch_block[1:])


def _pipeline_option_value(args: list[str], *names: str) -> str | None:
    for i, tok in enumerate(args):
        if tok in names and i + 1 < len(args):
            return args[i + 1]
        for name in names:
            prefix = name + "="
            if tok.startswith(prefix):
                return tok[len(prefix):]
    return None


_PIPELINE_LANGUAGE_FLAGS = ("-l", "--languages", "--langs", "--lang")


def _pipeline_language_value(args: list[str]) -> str | None:
    return _pipeline_option_value(args, *_PIPELINE_LANGUAGE_FLAGS)


def _pipeline_has_language_option(args: list[str]) -> bool:
    return option_was_passed(args, *_PIPELINE_LANGUAGE_FLAGS)


def _pipeline_url_fetch_output_target(fetch_target: str, fetch_options: list[str], output_root: str) -> str:
    media = infer_media(fetch_target)
    title = _pipeline_option_value(fetch_options, "--title")
    if title:
        media.title = title
    elif media.anilist_id and not media.title:
        try:
            info = fetch_anilist_info(media.anilist_id)
            media.title = info.title or media.title
            if info.is_movie():
                media.is_movie = True
        except CliError:
            pass
    season = _pipeline_option_value(fetch_options, "--season", "-s")
    if season:
        media.season = season
    elif not media.season:
        media.season = "auto"
    layout = _pipeline_option_value(fetch_options, "--layout") or "archive"
    return str(output_dir(Path(output_root).expanduser(), media, media.season, layout))


def _pipeline_existing_fetch_output_target(
    guessed_target: str | None,
    *,
    output_root: str | None,
    fetch_options: list[str],
) -> str | None:
    """After fetch runs, prefer the actual folder it wrote.

    Title-search fetches can resolve a user query like "mashle - magic and
    muscles" to a canonical AniList/TMDB title. The pre-fetch downstream
    guess may therefore point at `/root/mashle - magic and muscles/Season 02`
    while fetch actually saved `/root/MASHLE Kami .../Season 02`.
    """
    if guessed_target:
        guessed_path = Path(guessed_target).expanduser()
        if guessed_path.exists():
            return str(guessed_path)
    if not output_root:
        return guessed_target
    root = Path(output_root).expanduser()
    if not root.exists() or not root.is_dir():
        return guessed_target
    layout = (_pipeline_option_value(fetch_options, "--layout") or "archive").lower()
    season = (_pipeline_option_value(fetch_options, "--season", "-s") or "").strip().lower()
    candidates: list[Path] = []
    if layout == "archive":
        if season and season not in {"auto", "all"} and season.isdigit():
            season_dir = f"Season {int(season):02d}"
            candidates = [
                p for p in root.rglob(season_dir)
                if p.is_dir() and any(child.is_file() and child.suffix.lower() in SUB_EXTENSIONS for child in p.iterdir())
            ]
        elif season == "all":
            candidates = [
                p for p in root.rglob("All Seasons")
                if p.is_dir() and any(child.is_file() and child.suffix.lower() in SUB_EXTENSIONS for child in p.iterdir())
            ]
    if not candidates:
        candidates = [
            p for p in root.rglob("*")
            if p.is_dir() and any(child.is_file() and child.suffix.lower() in SUB_EXTENSIONS for child in p.iterdir())
        ]
    if not candidates:
        return guessed_target
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0])


def pipeline_main(argv: list[str]) -> int:
    """Run a getsubtitle pipeline of verbs in canonical order.

    Layout:
      [shared options] [--fetch TARGET opts] [--translate ENGINE opts]
      [--modify opts] [--merge opts]

    Shared options:
      --output PATH   final output directory (applied to merge if present;
                      passed to translate/modify via -o where supported)
      --dry-run       propagated to every verb that supports it

    Verb execution order is always fetch → translate → modify → merge,
    regardless of the order they were typed on the command line. Each
    verb's block is parsed by that verb's existing *_main function, so
    flag surfaces remain identical to the single-verb form.
    """
    blocks = split_pipeline_argv(argv)
    shared = blocks.pop("shared", [])

    # Parse shared options out of `shared`.
    shared_source: str | None = None
    shared_output: str | None = None
    shared_dry_run = False
    shared_force = False
    shared_no_open_folder_prompt = False
    i = 0
    leftover_shared: list[str] = []
    while i < len(shared):
        tok = shared[i]
        if tok == "--source":
            if i + 1 >= len(shared):
                raise CliError("--source needs a PATH argument.")
            shared_source = shared[i + 1]
            i += 2
            continue
        if tok == "--output":
            if i + 1 >= len(shared):
                raise CliError("--output needs a PATH argument.")
            shared_output = shared[i + 1]
            i += 2
            continue
        if tok == "--dry-run":
            shared_dry_run = True
            i += 1
            continue
        if tok == "--force":
            shared_force = True
            i += 1
            continue
        if tok == "--no-open-folder-prompt":
            shared_no_open_folder_prompt = True
            i += 1
            continue
        leftover_shared.append(tok)
        i += 1
    if leftover_shared:
        raise CliError(
            f"Unrecognized pipeline argument(s) before any verb: "
            f"{' '.join(leftover_shared)}. "
            "Place per-verb flags after their verb (--fetch / --translate / "
            "--modify / --merge)."
        )

    # Determine the working target for verbs that don't have their own TARGET.
    # fetch's TARGET is the pipeline target. If no --fetch, translate/modify/merge
    # need a TARGET passed via --output (or fall back to . — current dir).
    fetch_target: str | None = None
    fetch_options: list[str] = []
    if "fetch" in blocks:
        fetch_target, fetch_options = _pipeline_resolve_target(blocks["fetch"])
    has_downstream = any(v in blocks for v in ("translate", "modify", "merge"))

    # The "downstream target" — where translate/modify/merge operate — is:
    #   1. --output PATH if given
    #   2. fetch's TARGET (when fetch is a PATH, not a URL)
    #   3. error otherwise (URL fetch with no --output means we don't know
    #      where the SRTs landed; user must specify)
    downstream_target: str | None = shared_source or shared_output
    if downstream_target is None and fetch_target is not None and not _looks_like_url(fetch_target):
        downstream_target = fetch_target
    if (
        downstream_target is not None
        and shared_source is None
        and shared_output is not None
        and fetch_target is not None
        and _looks_like_url(fetch_target)
        and has_downstream
    ):
        downstream_target = _pipeline_url_fetch_output_target(fetch_target, fetch_options, shared_output)
    if downstream_target is None and has_downstream:
        if fetch_target and _looks_like_url(fetch_target):
            raise CliError(
                "Pipeline has --fetch URL + downstream verb(s) but no --output PATH. "
                "Add --output /path/to/folder so translate/modify/merge know where "
                "the fetched SRTs landed."
            )
        raise CliError(
            "Pipeline needs at least --fetch TARGET or --output PATH so the "
            "downstream verb(s) know which folder to operate on."
        )

    # Build per-verb argvs (in canonical exec order) and run them.
    rc_total = 0
    printed_any = False

    def _heading(name: str) -> None:
        nonlocal printed_any
        if printed_any:
            print()
        printed_any = True
        print(f"━━ {name} ━━")

    if "fetch" in blocks:
        assert fetch_target is not None  # checked above
        _heading(f"fetch {fetch_target}")
        sub_argv = [fetch_target] + fetch_options
        if shared_output and "--output" not in sub_argv and "-o" not in sub_argv:
            sub_argv += ["--output", shared_output]
        if (
            "translate" in blocks
            and not option_was_passed(
                sub_argv,
                "--engine", "--mt-engine", "--no-engine", "--no-mt-engine",
            )
        ):
            # A separate pipeline translate step should own MT. Otherwise the
            # URL-form fetch parser falls back to [translate].engine defaults
            # (usually Argos) before the requested pipeline engine can run.
            sub_argv.append("--no-engine")
        # Propagate shared --dry-run by adding to fetch's args if not already
        # there. URL form respects --dry-run via the URL parser. PATH form
        # is already dry-run by default unless --run; --dry-run is harmless.
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        elif not _looks_like_url(fetch_target) and "--run" not in sub_argv:
            sub_argv.append("--run")
        if (
            (has_downstream or shared_no_open_folder_prompt)
            and "--open-folder" not in sub_argv
            and "--no-open-folder-prompt" not in sub_argv
        ):
            sub_argv.append("--no-open-folder-prompt")
        rc = fetch_main(sub_argv)
        rc_total = rc or rc_total
        if rc and has_downstream:
            return rc_total
        if has_downstream and fetch_target is not None and _looks_like_url(fetch_target):
            downstream_target = _pipeline_existing_fetch_output_target(
                downstream_target,
                output_root=shared_output,
                fetch_options=fetch_options,
            )

    if "translate" in blocks:
        if downstream_target is None:
            raise CliError("--translate needs --output PATH or a PATH --fetch target.")
        _heading(f"translate {downstream_target}")
        tr_args = _rewrite_translate_block(blocks["translate"])
        if not _pipeline_has_language_option(tr_args):
            inherited_langs = (
                _pipeline_language_value(fetch_options)
                or _pipeline_language_value(blocks.get("merge", []))
            )
            if inherited_langs:
                tr_args += ["--languages", inherited_langs]
        sub_argv = [downstream_target] + tr_args
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        if shared_force and "--force" not in sub_argv:
            sub_argv.append("--force")
        rc = translate_main(sub_argv)
        rc_total = rc or rc_total

    if "modify" in blocks:
        if downstream_target is None:
            raise CliError("--modify needs --output PATH or a PATH --fetch target.")
        _heading(f"modify {downstream_target}")
        sub_argv = [downstream_target] + blocks["modify"]
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        if shared_force and "--force" not in sub_argv:
            sub_argv.append("--force")
        rc = modify_main(sub_argv)
        rc_total = rc or rc_total

    if "merge" in blocks:
        if downstream_target is None:
            raise CliError("--merge needs --output PATH or a PATH --fetch target.")
        _heading(f"merge {downstream_target}")
        sub_argv = [downstream_target] + blocks["merge"]
        if shared_source is not None and shared_output is not None and "--output" not in sub_argv:
            sub_argv += ["--output", shared_output]
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        if shared_force and "--force" not in sub_argv:
            sub_argv.append("--force")
        if shared_no_open_folder_prompt and "--no-open-folder-prompt" not in sub_argv:
            sub_argv.append("--no-open-folder-prompt")
        # combine_main is the underlying impl for merge.
        rc = combine_main(sub_argv)
        rc_total = rc or rc_total

    return rc_total


# Per-pair Ollama model overrides picked up by ollama_model_for_pair when set.
# Pipeline TOML's [translate]."src:tgt" = "model" entries write here for the
# duration of the run and are cleared at the end (session-only override).
_PIPELINE_TRANSLATE_PAIR_MODELS: dict[str, str] = {}


def _flag_from_key(key: str) -> str:
    """TOML key (underscore form) → CLI flag (dash form)."""
    return "--" + key.replace("_", "-")


# Plural-form TOML aliases mapped to the canonical singular CLI flag.
_TOML_KEY_ALIASES: dict[str, str] = {
    "episodes": "episode",
    "seasons": "season",
    "langs": "langs",            # already canonical
    "language": "langs",         # singular convenience alias
    "languages": "langs",        # plural convenience alias
}


def _canonicalize_toml_key(key: str) -> str:
    """Apply common plural/singular aliases so `episodes` works the same
    as `episode`, etc."""
    return _TOML_KEY_ALIASES.get(key, key)


def _emit_pipeline_flag(key: str, value) -> list[str]:
    """Emit one CLI flag-and-maybe-value pair from a TOML key/value.

    Rules:
      - Booleans → emit the flag when true; omit when false.
      - Lists/tuples → emit `--flag a,b,c` (comma-joined).
      - Strings/numbers → emit `--flag value`.
    """
    canon = _canonicalize_toml_key(key)
    flag = _flag_from_key(canon)
    if isinstance(value, bool):
        return [flag] if value else []
    if isinstance(value, (list, tuple)):
        return [flag, ",".join(str(v) for v in value)]
    return [flag, str(value)]


def _split_translate_pair_models(block: dict) -> tuple[dict, dict[str, str]]:
    """Pull out per-pair Ollama model overrides like "ja:ko" = "qwen3:4b"
    from a [translate] block. Returns (remaining_block, pair_models).
    Pair keys are detected by the presence of `:` in the key name."""
    remaining: dict = {}
    pair_models: dict[str, str] = {}
    for key, value in block.items():
        if isinstance(key, str) and ":" in key:
            pair_models[key] = str(value)
        else:
            remaining[key] = value
    return remaining, pair_models


# Default romanization mode per language. When the user writes "ko:true" we
# resolve to this dictionary to pick the sensible default. Each language
# uses its own native term — Japanese is "furigana" not "romanization-ja",
# Chinese is "pinyin", Cantonese is "jyutping", etc.
_READING_DEFAULTS: dict[str, str] = {
    "ja": "hiragana",      # furigana with hiragana script
    "ko": "revised",       # Revised Romanization (with G2P)
    "zh": "marks",         # pinyin with tone marks
    "yue": "numbers",      # jyutping with numbered tones
    "th": "royal-thai",
    "ar": "ala-lc",
    "hi": "iast",
    "ru": "iso-9",
}

# Accepted modes per language. The parser rejects unknown modes with a
# helpful error. Extend this table as new romanization backends ship.
_READING_ACCEPTED_MODES: dict[str, set[str]] = {
    "ja": {"hiragana", "katakana", "romaji", "furigana"},
    "ko": {"revised", "yale", "mr", "true"},
    "zh": {"marks", "numbers", "letters", "true"},
    "yue": {"numbers", "marks", "true"},
    "th": {"royal-thai", "iso-11940", "true"},
    "ar": {"ala-lc", "dmg", "true"},
    "hi": {"iast", "iso-15919", "itrans", "true"},
    "ru": {"iso-9", "bgn-pcgn", "true"},
}


def _parse_reading_spec(value) -> list[tuple[str, str]]:
    """Pipeline `[modify].reading = "ko:true, ja:hiragana"` (string OR list)
    → list of (lang_iso, mode) pairs.

    Accepted forms:
      "ko:true, ja:hiragana, zh:true"               (comma string)
      ["ko:true", "ja:hiragana"]                    (list)
      "ja:hiragana|romaji"                           (pipe expands to two entries)
      true / "true"                                  (every supported lang's default)

    Each entry's mode "true" resolves to the default for that language
    (see _READING_DEFAULTS). Language codes accept ISO codes (ja, ko,
    zh, yue, …) or common typos (jp, kr, cn) via LANGUAGE_ALIASES.
    """
    # Convert input to a flat list of "lang:mode" entries.
    if isinstance(value, bool):
        if not value:
            return []
        # `true` alone → every supported lang at its default. Usually not
        # what the user wants (most folks have one or two target langs),
        # but it makes "turn everything on" trivial.
        return [(lang, mode) for lang, mode in _READING_DEFAULTS.items()]
    if isinstance(value, (list, tuple)):
        entries = [str(v).strip() for v in value]
    else:
        entries = [s.strip() for s in str(value).split(",")]
    out: list[tuple[str, str]] = []
    for entry in entries:
        if not entry:
            continue
        if ":" not in entry:
            # Bare lang code (e.g. "ko") → use its default.
            lang = entry
            mode = "true"
        else:
            lang, _, mode = entry.partition(":")
            lang = lang.strip().lower()
            mode = mode.strip().lower()
        # Normalise lang code: jp → ja, kr → ko, cn → zh, etc.
        lang = LANGUAGE_ALIASES.get(lang, lang)
        # Expand pipe-mode shorthand (e.g. "ja:hiragana|romaji" → two pairs).
        modes = mode.split("|") if "|" in mode else [mode]
        for m in modes:
            m = m.strip()
            if m in ("true", "on", "yes", ""):
                m = _READING_DEFAULTS.get(lang)
                if m is None:
                    raise CliError(
                        f"[modify].reading: language {lang!r} has no built-in "
                        f"default. Specify a mode explicitly (e.g. {lang}:romanized)."
                    )
            accepted = _READING_ACCEPTED_MODES.get(lang)
            if accepted and m not in accepted:
                raise CliError(
                    f"[modify].reading: {lang!r} doesn't support mode {m!r}. "
                    f"Try one of: {', '.join(sorted(accepted - {'true'}))}."
                )
            out.append((lang, m))
    return out


def _apply_reading_to_args(args) -> None:
    """Translate `args.reading` (the reading SPEC string from --reading) onto
    the per-language attributes the downstream code reads.

    Japanese mode lands on `args.ja_reading`. Korean mode lands on
    `args.ko_reading`. Mandarin mode lands on `args.zh_reading`.
    Cantonese mode lands on `args.yue_reading`. Other languages still
    raise a clear "not yet implemented" error.

    Always initialises the three per-language attrs to None so downstream
    callers can use `args.ja_reading` (etc.) without `getattr` guards. A
    no-op for the SPEC routing itself when `args.reading` is unset.

    Used by combine_main, modify_main, and the URL-form download flow so
    the SPEC layer above feeds the same generator below.
    """
    # Always seed the per-language attrs so downstream consumers can do
    # `bool(args.ja_reading)` without worrying about whether _apply_reading_*
    # ran or not.
    if not hasattr(args, "ja_reading"):
        args.ja_reading = None
    if not hasattr(args, "ja_readings"):
        args.ja_readings = []
    if not hasattr(args, "ko_reading"):
        args.ko_reading = None
    if not hasattr(args, "ko_readings"):
        args.ko_readings = []
    if not hasattr(args, "zh_reading"):
        args.zh_reading = None
    if not hasattr(args, "yue_reading"):
        args.yue_reading = None
    spec = getattr(args, "reading", None)
    if not spec:
        return
    if spec == "":
        # --no-reading → explicit disable for every language.
        args.ja_reading = None
        args.ja_readings = []
        args.ko_reading = None
        args.ko_readings = []
        args.zh_reading = None
        args.yue_reading = None
        return
    pairs = _parse_reading_spec(spec)
    ja_modes = [m for l, m in pairs if l == "ja"]
    ko_modes = [m for l, m in pairs if l == "ko"]
    zh_modes = [m for l, m in pairs if l == "zh"]
    yue_modes = [m for l, m in pairs if l == "yue"]
    unsupported = [(l, m) for l, m in pairs if l not in ("ja", "ko", "zh", "yue")]
    if unsupported:
        langs = ", ".join(f"{l}:{m}" for l, m in unsupported)
        raise CliError(
            f"--reading for ({langs}) is not yet implemented. "
            "Japanese, Korean, Mandarin, and Cantonese ship today; Thai / "
            "Arabic / Hindi / Russian are on the roadmap (see ROADMAP.md)."
        )
    if ja_modes:
        # Mode names: hiragana (default), katakana, romaji.
        args.ja_readings = [
            mode if mode in ("hiragana", "katakana", "romaji") else "hiragana"
            for mode in ja_modes
        ]
        args.ja_reading = args.ja_readings[0]
    if ko_modes:
        # Korean mode lives on a fresh attribute. Accept the bare-default
        # case (`ko:true` → revised) the same way the spec parser does.
        args.ko_readings = ["yale" if mode == "yale" else "revised" for mode in ko_modes]
        args.ko_reading = args.ko_readings[0]
    if zh_modes:
        # Chinese mode → its own attribute. Default mode is `marks` (tone
        # diacritics — the form most learners recognise).
        mode = zh_modes[0]
        if mode in ("marks", "numbers", "letters"):
            args.zh_reading = mode
        else:
            args.zh_reading = "marks"
    if yue_modes:
        mode = yue_modes[0]
        args.yue_reading = "numbers" if mode in ("true", "marks") else mode


def _single_japanese_reading_spec(value) -> str | None:
    """Return `ja:MODE` when a reading spec has exactly one Japanese mode.

    A single Japanese reading can be inlined directly into merged output
    (`merge --reading ja:hiragana`) so final VTT files contain ruby. Multiple
    Japanese readings stay on the pseudo-language path (`ja-hiragana`,
    `ja-katakana`, `ja-romaji`) so users can build multi-row comparison stacks.
    """
    if not value:
        return None
    pairs = _parse_reading_spec(value)
    ja_modes = [mode for lang, mode in pairs if lang == "ja"]
    if len(ja_modes) == 1:
        return f"ja:{ja_modes[0]}"
    return None


def _resolve_modify_reading(value) -> list[str]:
    """Pipeline `[modify].reading = "ko:true, ja:hiragana"` → CLI flag
    emission. The CLI flag is `--reading SPEC` (a comma string), so
    this just normalises and re-serializes the spec for the downstream
    parser, with backward-compat to the older `[modify].furigana` key
    handled separately in _toml_to_pipeline_argv."""
    pairs = _parse_reading_spec(value)
    if not pairs:
        return []
    spec = ",".join(f"{lang}:{mode}" for lang, mode in pairs)
    return ["--reading", spec]


def _normalize_merge_langs(value) -> tuple[str, dict[str, str]]:
    """Pipeline `[merge].langs = "ja:vtt, en, ko:smi"` (string OR list)
    → (langs_string_for_-l, {lang: format_hint, ...}).

    The :format hint is stripped from the langs argument (so `-l` only
    sees language codes) and returned separately so the merge scanner
    can pick the right file when multiple formats coexist on disk.

    Accepts both:
      langs = "ja:vtt, en, ko:smi"          (comma string)
      langs = ["ja:vtt", "en", "ko:smi"]    (list of entries)
    """
    if isinstance(value, (list, tuple)):
        entries = [str(v).strip() for v in value]
    else:
        entries = [s.strip() for s in str(value).split(",")]
    langs: list[str] = []
    hints: dict[str, str] = {}
    for entry in entries:
        if not entry:
            continue
        if ":" in entry:
            lang, _, fmt = entry.partition(":")
            lang = lang.strip().lower()
            fmt = fmt.strip().lower()
            if fmt not in ("srt", "vtt", "ass", "ssa", "smi"):
                raise CliError(
                    f"merge :format hint {entry!r}: unknown format {fmt!r}. "
                    "Use :srt, :vtt, :ass, :ssa, or :smi."
                )
            langs.append(lang)
            hints[lang] = fmt
        else:
            langs.append(entry.lower())
    return ",".join(langs), hints


def _normalize_mt_source(value) -> str:
    """Normalize the [translate].mt_source value into the comma-list string
    accepted by --mt-source.

    Accepts:
      - string: "ja" (global) or "ko:ja,es:en" (per-target)
      - dict: { ko = "ja", es = "en" } (per-target, cleaner)
              { en = ["ko", "ja"] } (fallback list — first available wins)
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for target, source in value.items():
            if isinstance(source, (list, tuple)):
                source = "|".join(str(item).strip() for item in source if str(item).strip())
                if not source:
                    continue
            parts.append(f"{target}:{source}")
        return ",".join(parts)
    raise CliError(f"[translate].mt_source must be a string or dict (got {type(value).__name__}).")


def _toml_to_pipeline_argv(toml_data: dict) -> tuple[list[str], dict]:
    """Convert a parsed pipeline TOML document into:
      (argv for pipeline_main, extras dict)
    where extras carries side-channel info that doesn't fit on argv:
      {
        "translate_pair_models": {"ja:ko": "qwen3:4b", ...},
        "merge_format_hints":   {"ja": "vtt", "ko": "smi", ...},
        "output_layout":        "plex" | "archive" | "flat" | None,
        "output_format":        "vtt" | None,    # overrides per-verb format
        "force_live_run":       bool,             # propagate to PATH-form fetch
      }
    pipeline_main consumes both.

    Schema (sections in pipeline execution order):

      [fetch]
      source = "/Plex/Anime"          # required (was: target, kept as alias)
      subdirectory = true             # bool flags: true → --flag, false → omit
      season = "1-2"                  # range OK; also `seasons = ...`
      episode = "all"                 # also `episodes = ...`
      languages = "japanese,english"  # full names normalize; alias: langs

      [translate]
      engine = "ollama"               # required: argos | ollama[:model] | deepl
      mt_source = { ko = "ja", es = ["fr", "en"] }
                                      # per-target source; lists try first available
      # or: mt_source = "ko:ja,es:fr|en"     # string form (mt_source_lang accepted as alias)
      "ja:ko" = "qwen3:4b"            # per-pair Ollama overrides (session-only)
      "en:es" = "llama3.2:3b"

      [modify]
      strip_cc_noise = true
      single_line = true
      reading = "ja:hiragana"         # reading aids, e.g. ja:hiragana, ko:revised
      reading_format = "all"          # srt | ass | vtt | all
      convert = "smi-to-srt"          # "none" or omitted = no conversion

      [merge]
      languages = "ja:vtt, en, ko:smi"   # per-lang :format input hints
      master = "ja"
      sync = "strict"
      reading = "ja:hiragana"         # inline readings into the matching line
      format = "vtt"                  # final stacked-output format

      [output]
      target = "/Plex/Output"         # final output folder (was: root, kept as alias)
      layout = "plex"                 # archive | flat | plex
      retain_folder_structure = true  # alias for layout = "plex"
      format = "srt"                  # global override; per-verb wins if NOT set here
      dry_run = false                 # false = live run (auto-adds --run to fetch)
      force = false                   # propagates to translate / modify / merge
      yes = false                     # propagates to fetch (skip bulk confirm)
      debug_providers = false         # propagates to fetch
    """
    argv: list[str] = []
    extras: dict = {
        "translate_pair_models": {},
        "merge_format_hints": {},
        "output_layout": None,
        "output_format": None,
        "force_live_run": False,
    }

    # Normalize hyphen→underscore in every section's top-level keys so users
    # can write `dry-run` or `dry_run` interchangeably in --config TOMLs.
    toml_data = {
        k: (_normalize_section_keys(v) if isinstance(v, dict) else v)
        for k, v in toml_data.items()
    }

    # [output] section — read first so its globals can propagate into the
    # individual verb blocks below. NOT emitted via the generic flag walker
    # because every key here is special-cased.
    out_block = toml_data.get("output") or {}
    out_target = out_block.get("target") or out_block.get("root")  # canonical + alias
    if out_target is not None:
        argv += ["--output", str(out_target)]
    out_dry_run = bool(out_block.get("dry_run", False))
    if out_dry_run:
        argv.append("--dry-run")
    else:
        # Absent / explicitly false → live run. Pipeline_main will auto-add
        # --run to PATH-form fetch so [output].dry_run is the single source
        # of truth (no more [fetch].run = true duplication).
        extras["force_live_run"] = True
    if "format" in out_block:
        extras["output_format"] = str(out_block["format"])
    layout = out_block.get("layout")
    # Accept both `retain_folder_structure` (canonical snake_case) and the
    # historical hyphen form `retain-folder-structure`.
    if not layout and (
        out_block.get("retain_folder_structure") is True
        or out_block.get("retain-folder-structure") is True
    ):
        layout = "plex"
    if layout:
        extras["output_layout"] = str(layout)
    # Propagated booleans from [output] → verbs that support them.
    out_force = bool(out_block.get("force", False))
    out_yes = bool(out_block.get("yes", False))
    out_debug = bool(out_block.get("debug_providers", False))

    if "fetch" in toml_data:
        fb = dict(toml_data["fetch"])
        # Canonical key: source. Aliases: target (legacy), url.
        fetch_title = fb.pop("title", None)
        fetch_src = fb.pop("source", None) or fb.pop("target", None) or fb.pop("url", None)
        if fetch_src is None and fetch_title is not None:
            fetch_src = title_source_url(str(fetch_title))
        if fetch_src is None:
            raise CliError("Pipeline TOML [fetch] section needs a `source` or `title` key.")
        argv.append("--fetch")
        argv.append(str(fetch_src))
        # Strip [fetch].run if present — superseded by [output].dry_run.
        fb.pop("run", None)
        # Auto-add --run for PATH-form fetch when [output].dry_run is false.
        if extras["force_live_run"] and not _looks_like_url(str(fetch_src)):
            argv.append("--run")
        # Layout from [output] flows into fetch when present and fetch
        # didn't set its own.
        if extras["output_layout"] and "layout" not in fb:
            argv += ["--layout", extras["output_layout"]]
        # Global --yes / --debug-providers propagate to fetch.
        if out_yes:
            argv.append("-y")
        if out_debug:
            argv.append("--debug-providers")
        for key, value in fb.items():
            argv += _emit_pipeline_flag(key, value)

    if "translate" in toml_data:
        tb = dict(toml_data["translate"])
        if "engine" not in tb:
            raise CliError("Pipeline TOML [translate] section needs an `engine` key.")
        remaining, pair_models = _split_translate_pair_models(tb)
        extras["translate_pair_models"] = pair_models
        argv.append("--translate")
        argv.append(str(remaining.pop("engine")))
        # Canonical: mt_source. Alias: mt_source_lang (kept for back-compat).
        # Both forms accept string ("ko:ja,es:en") or dict ({ko = "ja"}).
        _mt_src_val = (
            remaining.pop("mt_source", None)
            if "mt_source" in remaining
            else remaining.pop("mt_source_lang", None)
        )
        if _mt_src_val is not None:
            mt_source = _normalize_mt_source(_mt_src_val)
            if mt_source.lower() != "auto":
                argv += ["--mt-source", mt_source]
        # Global --force propagates to translate.
        if out_force:
            argv.append("--force")
        for key, value in remaining.items():
            argv += _emit_pipeline_flag(key, value)

    if "modify" in toml_data:
        mb = dict(toml_data["modify"])
        argv.append("--modify")
        # canonical: [modify].reading = "ja:hiragana,ko:revised,zh:marks"
        if "reading" in mb:
            argv += _resolve_modify_reading(mb.pop("reading"))
        out_fmt = mb.pop("reading_format", None)
        if out_fmt:
            argv += ["--reading-format", str(out_fmt)]
        # convert = "none" treated as omitted.
        convert_val = mb.pop("convert", None)
        if convert_val and str(convert_val).lower() != "none":
            argv += ["--convert", str(convert_val)]
        if out_force:
            argv.append("--force")
        for key, value in mb.items():
            argv += _emit_pipeline_flag(key, value)

    if "merge" in toml_data:
        mb = dict(toml_data["merge"])
        argv.append("--merge")
        # Canonical: languages. Aliases: langs, language. Strip :format hints.
        langs_val = mb.pop("languages", None) or mb.pop("langs", None) or mb.pop("language", None)
        if langs_val is not None:
            langs_str, hints = _normalize_merge_langs(langs_val)
            extras["merge_format_hints"] = hints
            argv += ["-l", langs_str]
        # [output].format overrides per-verb merge format unless merge has its own.
        merge_format = mb.pop("format", None)
        if merge_format is None and extras["output_format"]:
            merge_format = extras["output_format"]
        if merge_format:
            argv += ["--format", str(merge_format)]
        merge_reading = mb.pop("reading", None)
        if merge_reading is None and isinstance(toml_data.get("modify"), dict):
            merge_reading = _single_japanese_reading_spec(toml_data["modify"].get("reading"))
        if merge_reading:
            argv += _resolve_modify_reading(merge_reading)
        merge_watermark = mb.pop("watermark", None)
        if merge_watermark is False:
            argv.append("--no-watermark")
        if out_force:
            argv.append("--force")
        for key, value in mb.items():
            argv += _emit_pipeline_flag(key, value)

    return argv, extras


def _extract_config_flag(argv: list[str]) -> str | None:
    """Scan argv for `--config FILE.toml` (anywhere in argv). Returns the
    file path if present, else None. Recommended position is at the end:
        getsubtitle --source X --output Y --config ./anime.toml
    but the parser accepts it anywhere. Raises CliError if --config
    appears with no following path argument."""
    for i, tok in enumerate(argv):
        if tok == "--config":
            if i + 1 >= len(argv):
                raise CliError(
                    "--config needs a TOML file path. "
                    "Example: getsubtitle --config ~/.getsubtitle/anime.toml"
                )
            return argv[i + 1]
        if tok.startswith("--config="):
            return tok.split("=", 1)[1]
    return None


# Top-level CLI flags that override fields in --config TOML data. These
# are the "common knobs" users want per-run without editing the TOML.
# Each maps to a (section, key) pair in the pipeline TOML structure.
_PIPELINE_CLI_OVERRIDE_MAP: dict[str, tuple[str, str]] = {
    "--source": ("fetch", "source"),
    "--season": ("fetch", "season"),
    "--episode": ("fetch", "episode"),
    "--episode-filename-start": ("fetch", "episode_filename_start"),
    "--languages": ("fetch", "languages"),
    "--langs": ("fetch", "languages"),
    "-l": ("fetch", "languages"),
    "--subdirectory": ("fetch", "subdirectory"),  # boolean
    "--output": ("output", "target"),
    "--format": ("output", "format"),
    "--dry-run": ("output", "dry_run"),           # boolean
    "--force": ("output", "force"),               # boolean
}
_PIPELINE_CLI_BOOLEAN_OVERRIDES = {"--subdirectory", "--dry-run", "--force"}


def _extract_cli_overrides(argv: list[str]) -> tuple[dict, list[str], dict[str, list[str]]]:
    """Pull the top-level override flags out of argv. Returns:
      (top_level_overrides, residual_argv, verb_blocks)
    where:
      top_level_overrides — {(section, key): value} dict for direct merge into TOML
      residual_argv       — argv with consumed flags removed (and --config FILE pair)
      verb_blocks         — {"fetch": [block_args...], ...} for inline --fetch etc.
                            (passed to split_pipeline_argv-style merge)
    """
    overrides: dict = {}
    residual: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--config" and i + 1 < len(argv):
            # Drop --config and its arg entirely.
            i += 2
            continue
        if tok.startswith("--config="):
            i += 1
            continue
        # Boolean override (no value).
        if tok in _PIPELINE_CLI_BOOLEAN_OVERRIDES:
            section, key = _PIPELINE_CLI_OVERRIDE_MAP[tok]
            overrides[(section, key)] = True
            i += 1
            continue
        # Valued override (flag + arg, or flag=arg).
        if tok in _PIPELINE_CLI_OVERRIDE_MAP and i + 1 < len(argv):
            section, key = _PIPELINE_CLI_OVERRIDE_MAP[tok]
            overrides[(section, key)] = argv[i + 1]
            i += 2
            continue
        if "=" in tok:
            flag, _, val = tok.partition("=")
            if flag in _PIPELINE_CLI_OVERRIDE_MAP and flag not in _PIPELINE_CLI_BOOLEAN_OVERRIDES:
                section, key = _PIPELINE_CLI_OVERRIDE_MAP[flag]
                overrides[(section, key)] = val
                i += 1
                continue
        residual.append(tok)
        i += 1
    # Now extract per-verb blocks (--fetch / --translate / --modify / --merge)
    # from the residual. These merge into TOML per-section.
    verb_blocks = split_pipeline_argv(residual)
    verb_blocks.pop("shared", None)  # already consumed
    return overrides, residual, verb_blocks


def _merge_overrides_into_toml(data: dict, overrides: dict, verb_blocks: dict) -> dict:
    """Layer CLI overrides into the parsed TOML data dict.

    Order (lowest precedence first):
      1. TOML as parsed
      2. Inline --verb blocks (per-section, per-key; CLI wins on collision)
      3. Top-level --source / --output / etc. overrides (CLI wins)

    Returns a NEW dict (does not mutate the input)."""
    out: dict = {k: (dict(v) if isinstance(v, dict) else v) for k, v in data.items()}

    # Step 2: inline verb blocks. We don't re-parse argparse for each verb;
    # we just convert the block argv into a small dict of {key: value}
    # using heuristic flag-pair extraction. Recognised flags only; others
    # are ignored (they wouldn't survive a TOML round-trip anyway).
    # Map argparse flag → TOML key for each verb.
    flag_to_key = {
        "fetch": {
            "--subdirectory": ("subdirectory", True),
            "--profile": ("profile", None),
            "--season": ("season", None),
            "-s": ("season", None),
            "--episode": ("episode", None),
            "-e": ("episode", None),
            "--episode-filename-start": ("episode_filename_start", None),
            "--languages": ("languages", None),
            "--langs": ("languages", None),
            "-l": ("languages", None),
            "--release-source": ("release_source", None),
            "--manual-search": ("manual_search", None),
            "--no-manual-search": ("manual_search", "off"),
            "--manual-search-open": ("manual_search_open", None),
            "--no-manual-search-open": ("manual_search_open", "never"),
            "--layout": ("layout", None),
            "--run": ("run", True),
        },
        "translate": {
            "--mt-source-lang": ("mt_source", None),
            "--mt-source": ("mt_source", None),
            "--engine": ("engine", None),
            "--mt-engine": ("engine", None),
            "--model": ("model", None),
            "--mt-model": ("model", None),
            "--mt-model-pair": ("mt_model_pair", None),
            "--force": ("force", True),
        },
        "modify": {
            "--season": ("season", None),
            "-s": ("season", None),
            "--episode": ("episode", None),
            "-e": ("episode", None),
            "--strip-cc-noise": ("strip_cc_noise", True),
            "--single-line": ("single_line", True),
            "--reading": ("reading", None),
            "--reading-format": ("reading_format", None),
            "--convert": ("convert", None),
            "--force": ("force", True),
        },
        "merge": {
            "--season": ("season", None),
            "-s": ("season", None),
            "--episode": ("episode", None),
            "-e": ("episode", None),
            "-l": ("languages", None),
            "--langs": ("languages", None),
            "--languages": ("languages", None),
            "--master": ("master", None),
            "--sync": ("sync", None),
            "--reading": ("reading", None),
            "--format": ("format", None),
            "--force": ("force", True),
            "--preserve-lines": ("preserve_lines", True),
            "--label-langs": ("label_langs", True),
            "--no-label-langs": ("label_langs", False),
        },
    }
    for verb in ("fetch", "translate", "modify", "merge"):
        block = verb_blocks.get(verb)
        if not block:
            continue
        section_name = verb
        out_section = dict(out.get(section_name) or {})
        # For fetch and translate, the first non-flag token is the positional
        # (source or engine respectively).
        idx = 0
        if verb == "fetch" and block and not block[0].startswith("-"):
            out_section["source"] = block[0]
            idx = 1
        elif verb == "translate" and block and not block[0].startswith("-"):
            # Use the colon-spec parser so engine:model works.
            engine, model = _parse_engine_spec(block[0])
            out_section["engine"] = engine if not model else f"{engine}:{model}"
            idx = 1
        while idx < len(block):
            tok = block[idx]
            spec = flag_to_key.get(verb, {}).get(tok)
            if spec is None:
                idx += 1
                continue
            key, fixed_value = spec
            if isinstance(fixed_value, bool):
                out_section[key] = fixed_value
                idx += 1
            elif idx + 1 < len(block) and not block[idx + 1].startswith("-"):
                out_section[key] = block[idx + 1]
                idx += 2
            else:
                # Flag with no value — for --furigana that's a bare flag.
                if fixed_value is not None:
                    out_section[key] = fixed_value
                idx += 1
        out[section_name] = out_section

    # Step 3: top-level CLI overrides win over everything.
    for (section, key), value in overrides.items():
        out_section = dict(out.get(section) or {})
        out_section[key] = value
        out[section] = out_section
    return out


def _pipeline_registry_dir() -> Path:
    """Folder holding named pipeline TOMLs, beside user_settings.toml."""
    return config_path().parent / "pipelines"


def _pipeline_registry_path(name: str) -> Path:
    safe = name.strip()
    bad = (
        not safe
        or safe.startswith(".")
        or safe.startswith("-")          # would collide with run's own flags
        or any(c in safe for c in '/\\<>:"|?*')
    )
    if bad:
        raise CliError(
            f"Invalid pipeline name {name!r}. Use letters, numbers, dashes "
            "(no slashes, and not starting with '.' or '-')."
        )
    return _pipeline_registry_dir() / f"{safe}.toml"


def run_main(argv: list[str]) -> int:
    """Named pipeline registry: save / list / remove / run a workflow TOML
    by short name so you don't have to remember its path.

        getsubtitle run --save anime path/to/workflow.toml
        getsubtitle run anime                       # run it
        getsubtitle run anime --source URL --output DIR   # with overrides
        getsubtitle run --list
        getsubtitle run --remove anime
    """
    if argv and argv[0] in ("--help", "-h", "help"):
        sys.stdout.write(HELP_TOPICS["run"])
        return 0
    if not argv or argv[0] in ("--list", "list"):
        reg = _pipeline_registry_dir()
        names = sorted(p.stem for p in reg.glob("*.toml")) if reg.is_dir() else []
        if not names:
            print("No saved pipelines yet.")
            print("Save one with:  getsubtitle run --save NAME path/to/workflow.toml")
            return 0
        print("Saved pipelines:")
        for n in names:
            print(f"  {n}")
        print()
        print("Run one with:  getsubtitle run NAME [--source X --output Y ...]")
        return 0
    if argv[0] == "--save":
        if len(argv) < 3:
            raise CliError("Usage: getsubtitle run --save NAME path/to/workflow.toml")
        name, src = argv[1], argv[2]
        src_path = Path(src).expanduser()
        if not src_path.is_file():
            raise CliError(f"Workflow file not found: {src}")
        dest = _pipeline_registry_path(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest)
        print(f"Saved pipeline {name!r}.")
        print(f"Run it with:  getsubtitle run {name}")
        return 0
    if argv[0] == "--remove":
        if len(argv) < 2:
            raise CliError("Usage: getsubtitle run --remove NAME")
        dest = _pipeline_registry_path(argv[1])
        if not dest.exists():
            raise CliError(f"No saved pipeline named {argv[1]!r}.")
        dest.unlink()
        print(f"Removed pipeline {argv[1]!r}.")
        return 0
    name, *overrides = argv
    dest = _pipeline_registry_path(name)
    if not dest.exists():
        raise CliError(
            f"No saved pipeline named {name!r}. "
            "List them with:  getsubtitle run --list"
        )
    full_argv = ["--config", str(dest), *overrides]
    return pipeline_from_config_main(str(dest), full_argv)


def pipeline_from_config_main(config_path: str, full_argv: list[str] | None = None) -> int:
    """Load a pipeline TOML file, optionally layer CLI overrides from
    `full_argv`, then run pipeline_main on the merged result.

    Layering (lowest to highest precedence):
      1. Built-in defaults (in _toml_to_pipeline_argv)
      2. TOML data parsed from `config_path`
      3. Inline --fetch / --translate / --modify / --merge blocks in full_argv
      4. Top-level --source / --output / --format / --season / --episode /
         -l / --subdirectory / --dry-run / --force overrides in full_argv
    """
    path = Path(config_path).expanduser()
    if not path.exists():
        raise CliError(f"Config not found: {path}")
    tomllib = _import_tomllib()
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise CliError(f"Could not parse config TOML {path}: {e}") from e
    if full_argv:
        overrides, _residual, verb_blocks = _extract_cli_overrides(full_argv)
        data = _merge_overrides_into_toml(data, overrides, verb_blocks)
    argv, extras = _toml_to_pipeline_argv(data)
    if not argv or not _is_pipeline_argv(argv):
        raise CliError(
            f"Config {path} has no verb sections after merging CLI overrides. "
            "Add at least one of [fetch], [translate], [modify], [merge] to the "
            "TOML, or pass an inline --fetch / --translate / --modify / --merge "
            "flag."
        )
    # Install session-only per-pair Ollama model overrides (cleared in finally).
    pair_models = extras.get("translate_pair_models") or {}
    saved = dict(_PIPELINE_TRANSLATE_PAIR_MODELS)
    _PIPELINE_TRANSLATE_PAIR_MODELS.update(pair_models)
    # Stash merge :format hints where the merge scanner can read them.
    global _PIPELINE_MERGE_FORMAT_HINTS
    saved_hints = _PIPELINE_MERGE_FORMAT_HINTS
    _PIPELINE_MERGE_FORMAT_HINTS = dict(extras.get("merge_format_hints") or {})
    try:
        return pipeline_main(argv)
    finally:
        _PIPELINE_TRANSLATE_PAIR_MODELS.clear()
        _PIPELINE_TRANSLATE_PAIR_MODELS.update(saved)
        _PIPELINE_MERGE_FORMAT_HINTS = saved_hints


# Session-only merge per-language format hint. Set by --config TOML
# loader from `[merge].languages = "ja:vtt, en, ko:smi"` entries. The merge
# scanner (scan_srt_files / its successor) consults this when choosing
# which source file to read per language.
_PIPELINE_MERGE_FORMAT_HINTS: dict[str, str] = {}


def _batch_walk_targets(root: "Path") -> list[tuple["Path", "Path", int | None]]:
    """Walk root and return (target, show_folder, season) tuples. `target`
    is the folder containing the video files (the actual fetch/merge
    destination); `show_folder` is the show name root (parent for Plex
    Season subdirs). Bare top-level files appear as (file, file, None)."""
    out: list[tuple["Path", "Path", int | None]] = []
    for folder in _batch_find_video_folders(root):
        show, season = detect_show_and_season(folder, root)
        out.append((folder, show, season))
    for f in _batch_find_bare_video_files(root):
        out.append((f, f, None))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Find and prepare subtitles for language learning. Download multiple "
            "languages, add Japanese furigana, clean SRT files for asbplayer, and "
            "optionally machine-translate missing languages."
        ),
        epilog=textwrap.dedent(
            """
            Examples (basic):
              getsubtitle URL -l ja
              getsubtitle URL -s 1 -e 3 -l ja,ko,en,es
              getsubtitle URL -s 1 -e all -l ja --reading ja:hiragana --single
              getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ko,en,es --dry-run

            Examples (by source):
              # IMDb movie (Spirited Away) — Wyzie covers movies; AniList bridge
              # adds Jimaku for ja if the title is in the anime DB.
              getsubtitle "https://www.imdb.com/title/tt0245429/" -l ja,ko,en,es --dry-run

              # TheTVDB series — currently needs a manual --title or --anilist
              # hint because the TVDB slug -> ID resolver is not yet implemented.
              getsubtitle "https://thetvdb.com/series/terrace-house-tokyo-2019" \\
                -s 1 -e 1 -l ja,en --title "Terrace House Tokyo 2019-2020" --dry-run

              # AniList direct — ID is pulled straight from the URL; no prompt.
              getsubtitle "https://anilist.co/anime/527/Pokemon/" -s 1 -e 1 -l ja,ko --dry-run

              # Crunchyroll series — slug "Frieren Beyond Journeys End" may not
              # resolve cleanly on AniList; pass --anilist for a sure match.
              getsubtitle "https://www.crunchyroll.com/series/GG5H5XQX4/frieren-beyond-journeys-end" \\
                -s 1 -e 1 -l ja,ko,en --anilist 154587 --furigana --single

              # Netflix browse — extracts jbv=60023642, bridges via Wikidata to
              # IMDb/TMDB so Wyzie can search even from a Netflix URL.
              getsubtitle "https://www.netflix.com/browse/genre/34399?jbv=60023642" \\
                -l ja,ko,en,es --dry-run

            Examples (MT fallback for missing languages):
              # Translate missing ko/es from the best available downloaded SRT
              # (e.g. ja -> ko, en -> es). Output saved as Show.lang.mt.srt.
              getsubtitle "https://www.imdb.com/title/tt0245429/" \\
                -l ja,ko,en,es --engine argos

            Subcommands:
              combine PATH ...        Stack downloaded SRTs into one file per episode.
                                      See: getsubtitle combine --help
            """
        ),
    )
    p.add_argument(
        "url",
        nargs="?",
        help=(
            "Media or metadata URL. Supports Crunchyroll, Netflix, IMDb, TMDB, "
            "Letterboxd, Rotten Tomatoes, MyAnimeList, TheTVDB, and Trakt."
        ),
    )

    search = p.add_argument_group("Search")
    search.add_argument("-s", "--season", default="auto", metavar="N|all", help="Season to search. Default: infer from URL/metadata when possible.")
    search.add_argument("-e", "--episode", default="auto", metavar="N|N-M|all", help="Episode to search. Accepts one episode, a range, a comma list, or all. Default: infer from URL/metadata when possible.")
    search.add_argument("--episode-filename-start", type=int, metavar="N", help="Use N as the output filename episode number for the first searched episode. Example: search Season 3 episodes 1-12 but save as S03E25-S03E36 when a streaming page labels the season E25 onward.")
    search.add_argument("-l", "--languages", "--langs", "--lang", dest="langs", default="ja", metavar="CODES", help="Comma-separated language codes. Default: ja. Accepts ISO codes (ja,en) or full names (japanese,english). Example: ja,en,es")
    search.add_argument("--title", metavar="TEXT", help="Title override when URL metadata is missing or blocked.")
    search.add_argument("--anilist", type=int, metavar="ID", help="AniList ID override for anime.")
    search.add_argument("--browser", action="store_true", help="Open the URL in your browser first, useful for login/Cloudflare pages.")
    search.add_argument("--manual-search", nargs="?", const="on-missing", choices=["off", "on-missing", "always"], default="on-missing", metavar="{off,on-missing,always}", help="After automatic providers miss Japanese/Korean/Chinese subtitles, show community search links and offer to open them. Default: on-missing.")
    search.add_argument("--no-manual-search", "--no-manual-download", dest="manual_search", action="store_const", const="off", help="Disable community search suggestions after provider misses.")
    search.add_argument("--manual-search-open", choices=["ask", "always", "never"], default="ask", metavar="{ask,always,never}", help="Whether to open manual-search links in your browser. Default: ask.")
    search.add_argument("--no-manual-search-open", dest="manual_search_open", action="store_const", const="never", help="Print manual-search links but never open browser tabs.")
    search.add_argument(
        "--release-source",
        choices=[
            "auto", "any",
            "netflix", "crunchyroll", "amazon", "hulu",
            "hbo", "disney", "apple", "paramount", "peacock",
        ],
        default="auto",
        metavar="{auto,any,netflix,crunchyroll,amazon,hulu,hbo,disney,apple,paramount,peacock}",
        help="Prefer matching release sources. Default: auto = infer from URL host (works for all the listed services); use any to disable source preference.",
    )
    search.add_argument("-release-source", dest="release_source", choices=["auto", "any", "netflix", "crunchyroll"], help=argparse.SUPPRESS)

    output = p.add_argument_group("Output")
    output.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT), metavar="DIR", help=f"Base output folder. Default: {DEFAULT_OUTPUT_TEXT}")
    output.add_argument("--layout", choices=["archive", "flat", "plex"], default="archive", help="Folder layout. Default: archive (Title/Season 01/files).")
    output.add_argument("--dry-run", action="store_true", help="Search and show availability without downloading.")
    output.add_argument("-y", "--yes", action="store_true", help="Skip bulk download confirmation.")
    output.add_argument("--open-folder", action="store_true", help="Open the output folder after saving.")
    output.add_argument("--no-open-folder-prompt", action="store_true", help="Never ask to open the output folder after saving.")

    learning = p.add_argument_group("Learning Helpers")
    learning.add_argument("--reading-format", "--format", dest="reading_format", metavar="CODES", help="Reading-aid output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt. Overrides [modify].reading_format from user_settings.toml.")
    learning.add_argument("--reading", dest="reading", metavar="SPEC", help="Generate per-language reading aids from downloaded SRTs. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana', 'ko:revised', 'zh:marks', 'yue:numbers'. Pipe shorthand 'ja:hiragana|romaji' generates both side files. Japanese / Korean / Mandarin / Cantonese ship now; Thai / Arabic / Hindi / Russian land per the roadmap.")
    learning.add_argument("--no-reading", dest="reading", action="store_const", const="", help="Disable reading-aid side-file generation for this run.")
    learning.add_argument("--single-line", "--single", action="store_true", default=False, help="Flatten SRT cues to one text line for cleaner asbplayer display. On by default; this flag is kept as an explicit readability marker.")
    learning.add_argument("--no-single-line", "--preserve-lines", dest="single_line", action="store_false", help="Keep each downloaded SRT's original line breaks (disables the default single-line flattening).")
    learning.add_argument("-single-line", "-single", dest="single_line", action="store_true", help=argparse.SUPPRESS)
    learning.add_argument("--strip-cc-noise", action="store_true", default=False, help="Remove broadcast closed-caption noise from downloaded SRTs (Japanese ➡ continuation arrows and decorative wrappers like 《...》). On by default; this flag is kept as an explicit readability marker.")
    learning.add_argument("--no-strip-cc-noise", dest="strip_cc_noise", action="store_false", help="Keep broadcast closed-caption noise in downloaded SRTs (disables the default ➡ stripping).")
    # Deprecated aliases — kept silently so existing scripts keep working.
    learning.add_argument("--strip-cc-arrows", "--strip-arrows", "-strip-cc-noise", "-strip-cc-arrows", "-strip-arrows", dest="strip_cc_noise", action="store_true", help=argparse.SUPPRESS)

    keys = p.add_argument_group("API Keys", description="Stored in macOS Keychain when available; otherwise set JIMAKU_API_KEY / WYZIE_API_KEY / SUBDL_API_KEY / DEEPL_API_KEY / TMDB_API_KEY in your shell.")
    keys.add_argument("--set-key", nargs="?", const="", metavar="PROVIDER", help="Guided API key setup: jimaku, wyzie, subdl, deepl, tmdb, or all.")
    keys.add_argument("--reset-key", nargs="?", const="", metavar="PROVIDER", help="Delete saved API key: jimaku, wyzie, subdl, deepl, tmdb, or all.")
    p.add_argument("--reset-jimaku-key", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--set-jimaku-key", action="store_true", help=argparse.SUPPRESS)

    translation = p.add_argument_group("Machine Translation", description="Runs AFTER download. Requires at least one other requested language to download successfully so MT has a source SRT to translate from. Output saved as <name>.<lang>.mt.srt.")
    translation.add_argument("--engine", "--mt-engine", dest="mt_engine", choices=["argos", "ollama", "deepl"], help="Translate missing requested languages from the best available SRT. Engines: argos (offline; pip install argostranslate), ollama (offline LLM; needs Ollama daemon), deepl (online; free tier, needs DEEPL_API_KEY). Default: argos (via [translate].engine).")
    translation.add_argument("--no-engine", "--no-mt-engine", dest="mt_engine", action="store_const", const="", help="Disable machine translation for this run even when [translate].engine is set in user_settings.toml.")
    translation.add_argument("--model", "--mt-model", dest="mt_model", metavar="NAME", help=f"Ollama model for --engine ollama. Default: {DEFAULT_OLLAMA_MODEL}")
    translation.add_argument("--mt-model-pair", metavar="PAIRS", help="Per-pair Ollama model overrides for this run, e.g. ja:ko=qwen3:4b,en:es=llama3.2:3b. Ignored unless --engine ollama.")
    translation.add_argument("--mt-source", "--mt-source-lang", dest="mt_source_lang", metavar="CODES", help="Force the source language(s) for MT. Single code (ja) applies to all targets; target:source pairs (ko:ja,es:en) map per target.")

    advanced = p.add_argument_group("Advanced / Experimental")
    advanced.add_argument("--debug-providers", action="store_true", help="Show raw provider counts and language tags for missing-subtitle debugging.")
    advanced.add_argument("--experimental-subdivx", action="store_true", help="Enable experimental Spanish Subdivx fallback.")
    advanced.add_argument("--experimental-addic7ed", action="store_true", help="Enable experimental Korean Addic7ed fallback; may rate-limit.")
    advanced.add_argument("-i", "--interactive", action="store_true", help=argparse.SUPPRESS)
    _apply_download_config_defaults(p)
    return p


def confirm_bulk(count: int, args: argparse.Namespace) -> None:
    if args.yes or count <= 4:
        return
    try:
        answer = input(f"About to download up to {count} subtitle files. Continue? [Y/n] ").strip().lower()
    except EOFError:
        raise CliError("Cancelled because confirmation input was not available. Re-run with -y to skip confirmation.")
    if answer in {"n", "no"}:
        raise CliError("Cancelled.")


class _StatusLine:
    """Lightweight 'doing X... done.' status feedback for slow blocking
    operations that would otherwise look frozen (e.g. fetching the Anime-IDs
    JSON or a Wikidata SPARQL query).

    Use as a context manager:
        with _StatusLine("Loading anime ID database"):
            data = request_json(ANIME_IDS_URL)

    Prints to stderr so it doesn't muddle stdout in scripted contexts, and
    is silent when stderr isn't a TTY (so logs and CI stay clean)."""

    def __init__(self, message: str):
        self.message = message
        self.active = sys.stderr.isatty()

    def __enter__(self) -> "_StatusLine":
        if self.active:
            sys.stderr.write(f"{self.message}... ")
            sys.stderr.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.active:
            return
        if exc_type is None:
            sys.stderr.write("done.\n")
        else:
            sys.stderr.write("failed.\n")
        sys.stderr.flush()


def progress_bar(current: int, total: int, label: str, detail: str = "", *, transient: bool = False) -> None:
    total = max(total, 1)
    width = 24
    filled = round(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    suffix = f" {detail}" if detail else ""
    line = f"[{bar}] {current}/{total} {label}{suffix}"
    if transient and sys.stdout.isatty():
        print(f"\r{line}", end="\n" if current >= total else "", flush=True)
    elif not transient or current >= total:
        print(line, flush=True)


def color_text(text: str, color: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{ANSI_RESET}"


def print_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print()
    print(color_text("Warnings:", ANSI_RED))
    print(color_text("┌" + "─" * 76, ANSI_RED))
    for warning in warnings:
        print(color_text(f"│ - {warning}", ANSI_RED))
    print(color_text("└" + "─" * 76, ANSI_RED))


def episode_sort_key(episode: str) -> tuple[int, int | str]:
    return (0, int(episode)) if episode.isdigit() else (1, episode)


def summarize_episodes(episodes: list[str]) -> str:
    if not episodes:
        return "none"
    sorted_episodes = sorted(episodes, key=episode_sort_key)
    if not all(ep.isdigit() for ep in sorted_episodes):
        return ", ".join(sorted_episodes)

    ranges: list[str] = []
    start = prev = int(sorted_episodes[0])
    for raw in sorted_episodes[1:]:
        current = int(raw)
        if current == prev + 1:
            prev = current
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = current
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(ranges)


def episode_label(episode: str) -> str:
    return f"E{int(episode):02d}" if episode.isdigit() else episode


def summarize_episode_labels(episodes: list[str]) -> str:
    if not episodes:
        return "none"
    sorted_episodes = sorted(episodes, key=episode_sort_key)
    if not all(ep.isdigit() for ep in sorted_episodes):
        return ", ".join(sorted_episodes)

    ranges: list[str] = []
    start = prev = int(sorted_episodes[0])
    for raw in sorted_episodes[1:]:
        current = int(raw)
        if current == prev + 1:
            prev = current
            continue
        ranges.append(f"E{start:02d}" if start == prev else f"E{start:02d}-E{prev:02d}")
        start = prev = current
    ranges.append(f"E{start:02d}" if start == prev else f"E{start:02d}-E{prev:02d}")
    return ", ".join(ranges)


def print_search_results(results: list[SearchResult]) -> None:
    if not results:
        return

    print("\nSearch results:")
    languages = []
    for result in results:
        if result.language not in languages:
            languages.append(result.language)

    for language in languages:
        language_results = [result for result in results if result.language == language]
        found = [result for result in language_results if result.status == "found"]
        missing = [result for result in language_results if result.status == "missing"]
        errors = [result for result in language_results if result.status == "error"]
        total = len(language_results)
        parts = [f"Found {len(found)}/{total}"]
        if found:
            parts.append(summarize_episode_labels([result.episode for result in found]))
        if missing:
            parts.append(f"Missing {summarize_episode_labels([result.episode for result in missing])}")
        if errors:
            parts.append(f"Errors {summarize_episode_labels([result.episode for result in errors])}")
        print(f"  {language}: {', '.join(parts)}")

        if 0 < len(found) <= 4:
            for result in sorted(found, key=lambda item: episode_sort_key(item.episode)):
                assert result.file is not None
                print(f"    - {episode_label(result.episode)}: {result.file.name} [{result.provider}]")


def print_planned_downloads(planned: list[tuple[str, str, SubtitleFile]]) -> None:
    if not planned:
        return
    print("\nPlanned downloads:")
    groups: dict[tuple[str, str], list[tuple[str, SubtitleFile]]] = {}
    for lang, ep, sub in planned:
        groups.setdefault((lang, sub.provider), []).append((ep, sub))
    for (lang, provider), items in groups.items():
        episodes = [ep for ep, _sub in items]
        print(f"  {lang}: {len(items)} file{'s' if len(items) != 1 else ''}, {summarize_episode_labels(episodes)} [{provider}]")
        if len(items) <= 4:
            for ep, sub in sorted(items, key=lambda item: episode_sort_key(item[0])):
                print(f"    - {episode_label(ep)}: {sub.name}")


def _manual_search_query_terms(media: MediaInfo) -> list[str]:
    """Return title/query variants for community subtitle searches."""
    seen: set[str] = set()
    out: list[str] = []
    candidates = [
        media.title,
        *(getattr(media, "title_aliases", None) or []),
    ]
    for item in candidates:
        if not item:
            continue
        value = re.sub(r"\s+", " ", str(item)).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    if not out and media.source_url:
        out.append(media.source_url)
    return out[:4]


def _manual_search_google_url(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def build_manual_search_suggestions(
    media: MediaInfo,
    missing_langs: list[str],
) -> list[ManualSearchSuggestion]:
    """Build browser-openable community search targets for missing subtitles.

    These suggestions are deliberately manual. They do not bypass ads,
    login walls, CAPTCHAs, or any other access-control step; they only put
    the user on likely search pages and let the normal site flow happen.
    """
    terms = _manual_search_query_terms(media)
    title = terms[0] if terms else (media.title or "subtitle")
    suggestions: list[ManualSearchSuggestion] = []

    def add(lang: str, label: str, url: str, note: str) -> None:
        suggestions.append(ManualSearchSuggestion(lang, label, url, note))

    for lang in missing_langs:
        if lang == "ja":
            q = urllib.parse.quote_plus(title)
            add("ja", "Jimaku web search", f"https://jimaku.cc/search?q={q}",
                "Japanese anime subtitle community. API lookup is automatic when an AniList match exists; web search can reveal alternate titles/releases.")
            add("ja", "Kitsunekko", "https://kitsunekko.net/dirlist.php?dir=subtitles%2Fjapanese%2F",
                "Long-running anime subtitle archive. Browse manually by Japanese/romaji/English title.")
            add("ja", "Google Japanese subtitle search",
                _manual_search_google_url(f'{title} 日本語字幕 srt OR ass OR vtt'),
                "Broad web search using Japanese subtitle keywords and alternate release formats.")
            if len(terms) > 1:
                add("ja", "Google alternate-title JP search",
                    _manual_search_google_url(" OR ".join(f'"{term}"' for term in terms[:3]) + " 日本語字幕"),
                    "Tries localized/English/romaji titles together.")
        elif lang == "ko":
            q = title
            add("ko", "GOM Lab", "https://www.gomlab.com/en/subtitle-home",
                "Korean-focused archive; often SMI. Complete any ad/login step manually.")
            add("ko", "Cineaste", "https://cineaste.co.kr/bbs/board.php?bo_table=psd_caption",
                "Korean subtitle community; search manually if the page blocks direct query URLs.")
            add("ko", "Google Korean SMI search",
                _manual_search_google_url(f'{q} 한글자막 smi OR srt'),
                "Broad web search using Korean subtitle keywords.")
            if len(terms) > 1:
                add("ko", "Google alternate-title search",
                    _manual_search_google_url(" OR ".join(f'"{term}"' for term in terms[:3]) + " 한글자막"),
                    "Tries localized/English/original titles together.")
        elif lang == "zh":
            q = urllib.parse.quote_plus(title)
            add("zh", "ASSRT / Shooter", f"https://2.assrt.net/sub/?searchword={q}",
                "Chinese subtitle site with an API; manual web search works even before API setup.")
            add("zh", "SubHD", f"https://subhd.tv/search/{q}",
                "Chinese community subtitles; may require site login/manual download.")
            add("zh", "Zimuku / SrtKu", "https://srtku.com/",
                "Large Simplified/Traditional/bilingual archive; search/download manually.")
            add("zh", "Google Chinese subtitle search",
                _manual_search_google_url(f'{title} 中文字幕 中英双语 字幕 srt ass'),
                "Broad web search for Simplified/Traditional/bilingual subtitles.")
    return suggestions


def missing_languages_for_manual_search(
    requested_langs: list[str],
    episodes: list[str],
    results: list[SearchResult],
) -> list[str]:
    found = {(r.language, r.episode) for r in results if r.status == "found"}
    missing: list[str] = []
    for lang in requested_langs:
        if lang not in {"ja", "ko", "zh"}:
            continue
        if any((lang, ep) not in found for ep in episodes):
            missing.append(lang)
    return missing


def maybe_print_manual_search_suggestions(
    media: MediaInfo,
    requested_langs: list[str],
    episodes: list[str],
    results: list[SearchResult],
    *,
    mode: str = "on-missing",
    open_mode: str = "ask",
    expected_output_dir: Path | None = None,
) -> None:
    if mode == "off":
        return
    missing_langs = missing_languages_for_manual_search(requested_langs, episodes, results)
    if mode == "on-missing" and not missing_langs:
        return
    if mode == "always":
        missing_langs = [lang for lang in requested_langs if lang in {"ko", "zh"}]
    if not missing_langs:
        return
    suggestions = build_manual_search_suggestions(media, missing_langs)
    if not suggestions:
        return

    print("\nManual search suggestions:")
    print("  Some requested subtitles were not found automatically.")
    print("  These links do not bypass login, ads, or site restrictions; download manually,")
    print("  then point getsubtitle at the downloaded .smi/.srt/.ass files.")
    for idx, suggestion in enumerate(suggestions, start=1):
        print(f"  {idx}. [{suggestion.language}] {suggestion.label}")
        print(f"     {suggestion.url}")
        print(f"     {suggestion.note}")

    convert_spec = "smi-to-srt"
    if missing_langs:
        convert_spec = f"{','.join(missing_langs)}:smi-to-srt"
    print("\nAfter downloading manually:")
    print("  1. Convert/clean the downloaded subtitle files:")
    print(f"     getsubtitle modify ~/Downloads --convert {convert_spec}")
    if expected_output_dir is not None:
        expected = str(expected_output_dir)
        print("  2. Move the matching subtitle files into the show folder:")
        print(f"     {shlex.quote(expected)}")
        print("  3. Merge from that show folder:")
        print(f"     getsubtitle merge {shlex.quote(expected)} -l {','.join(requested_langs)}")
    else:
        print("  2. Merge from the downloaded files:")
        print(f"     getsubtitle merge ~/Downloads -l {','.join(requested_langs)}")

    should_open = False
    if open_mode == "always":
        should_open = True
    elif open_mode == "ask" and sys.stdin.isatty():
        try:
            answer = input("\nOpen these searches in your browser? [Y/n] ").strip().lower()
            should_open = answer not in {"n", "no"}
        except EOFError:
            should_open = False
    if should_open:
        for suggestion in suggestions:
            try:
                open_in_browser(suggestion.url)
            except CliError as e:
                print(f"  (could not open {suggestion.label}: {e})")


def print_missing_subtitle_next_steps(
    requested_langs: list[str],
    episodes: list[str],
    results: list[SearchResult],
    *,
    media: MediaInfo,
    expected_output_dir: Path | None = None,
) -> None:
    missing_by_lang: dict[str, list[str]] = {}
    for lang in requested_langs:
        found = {r.episode for r in results if r.language == lang and r.status == "found"}
        missing = [ep for ep in episodes if ep not in found]
        if missing:
            missing_by_lang[lang] = missing
    if not missing_by_lang:
        return

    print("\nMissing subtitle next steps:")
    for lang, eps in missing_by_lang.items():
        shown = ", ".join(eps[:8])
        more = f" (+{len(eps) - 8} more)" if len(eps) > 8 else ""
        print(f"  - {lang}: missing {len(eps)}/{len(episodes)} episode(s): {shown}{more}")
    print("  Try:")
    if any(lang in {"ja", "ko", "zh", "yue"} for lang in missing_by_lang):
        print("  1. Open community search suggestions with `--manual-search-open always`.")
    else:
        print("  1. Re-run with `--debug-providers` to inspect provider language/source tags.")
    if expected_output_dir is not None:
        print(f"  2. Put manually downloaded subtitles in: {expected_output_dir}")
    else:
        print("  2. Put manually downloaded subtitles beside the matching media/subtitle files.")
    source_candidates = [lang for lang in requested_langs if lang not in missing_by_lang]
    if source_candidates:
        source = source_candidates[0]
        targets = ",".join(missing_by_lang)
        print(f"  3. Or machine-translate missing tracks: `getsubtitle translate FOLDER -l {targets} --mt-source {source}`")
    elif media.title:
        print("  3. Try a metadata URL with stronger IDs (IMDb/TMDB/AniList) or add `--title`.")
    print("  4. Merge after filling gaps: `getsubtitle merge FOLDER -l " + ",".join(requested_langs) + "`")


# ===========================================================================
# User settings (non-secret config file)
# ===========================================================================
# Loads ~/.config/getsubtitle/user_settings.toml (or %APPDATA% on Windows)
# and applies its values as defaults for the matching CLI flags. Secrets
# (API keys) are deliberately NOT supported here — they live in macOS
# Keychain or environment variables.
#
# Precedence: command-line flag > environment variable > user_settings.toml
# > built-in default.
#
# A test/CI override is available via the GETSUBTITLE_CONFIG_PATH env var.

CONFIG_PATH_ENV = "GETSUBTITLE_CONFIG_PATH"
CONFIG_DIR_NAME = "getsubtitle"
CONFIG_FILE_NAME = "user_settings.toml"
CONFIG_EXAMPLE_FILE_NAME = "user_settings.example.toml"


def config_path() -> Path:
    """Resolve the active config file path.

    Honours GETSUBTITLE_CONFIG_PATH (used by tests), then XDG_CONFIG_HOME on
    Linux/macOS, then platform conventions:
      macOS/Linux: ~/.config/getsubtitle/user_settings.toml
      Windows:     %APPDATA%\\getsubtitle\\user_settings.toml
    """
    override = os.environ.get(CONFIG_PATH_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg) if xdg else Path.home() / ".config"
    return base_dir / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def _minimal_toml_parse(text: str) -> dict:
    """Last-resort TOML reader covering only the user_settings.toml schema.

    Used when neither stdlib tomllib nor the tomli backport is available.
    Handles: comments, blank lines, [section] headers, booleans (true/false),
    double-quoted strings, and arrays of double-quoted strings. Does NOT
    handle inline tables, multi-line strings, integers,
    floats, or datetimes — none of which user_settings.toml needs."""
    out: dict[str, dict] = {}
    current: dict = {}
    section_name: str | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # [section] or [section.subsection]
        m = re.match(r"^\[([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)\]\s*(?:#.*)?$", line)
        if m:
            section_name = m.group(1)
            current = out
            for part in section_name.split("."):
                existing = current.setdefault(part, {})
                if not isinstance(existing, dict):
                    raise CliError(f"user_settings.toml line {lineno}: section conflicts with non-table value: {raw!r}")
                current = existing
            continue
        if section_name is None:
            raise CliError(f"user_settings.toml line {lineno}: key outside any [section]: {raw!r}")
        if "=" not in line:
            raise CliError(f"user_settings.toml line {lineno}: missing '=': {raw!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding double quotes from quoted keys so things like
        # "ja:ko" = "qwen3:4b" (TOML-spec quoted bare keys) work without
        # leaving the quotes embedded in the dict key.
        if key.startswith('"') and key.endswith('"') and len(key) >= 2:
            key = key[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        if value == "true":
            current[key] = True
        elif value == "false":
            current[key] = False
        elif value.startswith('"') and value.endswith('"') and len(value) >= 2:
            current[key] = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                current[key] = []
            else:
                items: list[str] = []
                for m_str in re.finditer(r'"((?:[^"\\]|\\.)*)"', inner):
                    items.append(m_str.group(1).replace('\\"', '"').replace('\\\\', '\\'))
                current[key] = items
        else:
            raise CliError(
                f"user_settings.toml line {lineno}: unsupported value (minimal "
                f"reader handles booleans, double-quoted strings, and arrays of strings only): {raw!r}"
            )
    return out


class _FallbackTomllib:
    """Adapter so the minimal parser exposes the same surface as tomllib."""

    @staticmethod
    def load(f):  # type: ignore[no-untyped-def]
        return _minimal_toml_parse(f.read().decode("utf-8"))

    @staticmethod
    def loads(s):  # type: ignore[no-untyped-def]
        return _minimal_toml_parse(s)


def _import_tomllib():
    """Lazy-import a TOML reader. Preference order:
      1. stdlib `tomllib` (Python 3.11+)
      2. `tomli` backport (declared as a dep for Python <3.11)
      3. in-tree minimal parser (covers our schema's subset)

    Users on Python 3.10 should `pip install tomli` per the project's
    dependency declaration; the fallback exists so getsubtitle never fails
    to read its own config in unusual environments."""
    try:
        import tomllib  # type: ignore  # noqa: PLC0415
        return tomllib
    except ImportError:
        pass
    try:
        import tomli as tomllib  # type: ignore  # noqa: PLC0415
        return tomllib
    except ImportError:
        pass
    return _FallbackTomllib


# Schema-ish dict of built-in defaults. Used for `config --show` and as the
# source of truth for the example template.
BUILTIN_CONFIG_DEFAULTS: dict[str, dict[str, object]] = {
    # Pipeline-aligned schema. Section names and keys match the pipeline
    # TOML schema (--config FILE.toml) so users can copy-paste blocks
    # between user_settings.toml and pipeline configs.
    "fetch": {
        "languages": "ja",
        "release_source": "auto",
        # Community-search helper after automatic providers miss. The helper
        # prints likely Japanese/Korean/Chinese sites and can open browser searches.
        "manual_search": "on-missing",      # off | on-missing | always
        "manual_search_open": "ask",        # ask | always | never
    },
    "translate": {
        # Default engine: argos (offline, free, no daemon). Users without
        # argostranslate installed see a one-line setup hint, not a crash.
        "engine": "argos",
        "model": DEFAULT_OLLAMA_MODEL,
        # Per-target source spec. Either a single string ("auto" or "ja" or
        # "ko:ja,es:en") or a dict ({ ko = "ja", es = "en" }).
        "mt_source_lang": "auto",
        # Strip inline 漢字（かんじ） readings from ja before sending to MT.
        # Was [furigana].strip_before_mt under the old schema.
        "strip_reading_before_mt": True,
        "ollama_models": {
            # Flags live alongside pair → model mappings in this nested table.
            # auto_load: pull a missing Ollama model automatically before MT.
            # auto_unload: free the model from RAM/VRAM after the MT pass.
            "auto_load": True,
            "auto_unload": True,
        },
    },
    "modify": {
        # On by default: getsubtitle's primary downstream is asbplayer, which
        # prefers single-line cues. Override per-run with --preserve-lines.
        "single_line": True,
        # On by default: Japanese broadcast SRTs are full of ➡ continuation
        # arrows that have no value for language learning.
        "strip_cc_noise": True,
        # Reading-aid SPEC (the umbrella covering ja/ko/zh and beyond).
        # No default value — the user opts in via wizard / setup / their TOML.
        # Format for output side files when reading is set: srt by default.
        "reading_format": "srt",
    },
    "merge": {
        # Target language (ja) on top, English (likely native) below.
        # Western learners are the largest audience; override for other targets.
        "languages": "ja,en",
        "sync": "auto",
        "preserve_lines": False,
        "label_langs": False,
        "priority": [],
        # Inline per-language readings (e.g. 漢字（かんじ）) into the merged
        # cue stack on the matching language line. Defaults to true so the
        # most common ja+en case "just works"; disable per-run with --no-reading.
        "reading": True,
        # Add a short GetSubtitle credit/disclaimer cue at the beginning and
        # end of merged study files. Disable per-run with --no-watermark.
        "watermark": True,
    },
    "output": {
        "target": DEFAULT_OUTPUT_TEXT,
        "layout": "archive",
        "open_folder": False,
        "force": False,
        # Was [experimental].debug_providers under the old schema.
        "debug_providers": False,
    },
    "experimental": {
        "subdivx": False,
        "addic7ed": False,
    },
}


def _validate_bool(value, key: str) -> bool:
    if not isinstance(value, bool):
        raise CliError(f"{key}: expected boolean (true/false), got {type(value).__name__} ({value!r})")
    return value


def _validate_enum(value, key: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CliError(f"{key}: expected one of {sorted(allowed)}, got {value!r}")
    return value


def _validate_lang_list(value, key: str) -> str:
    """Accept either a string ('ja,ko,en') or an array (['ja', 'ko', 'en']);
    return as a canonical comma-separated string for argparse defaults."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return ",".join(value)
    raise CliError(f"{key}: expected string ('ja,ko') or string array (['ja', 'ko'])")


def _validate_str(value, key: str) -> str:
    if not isinstance(value, str):
        raise CliError(f"{key}: expected string, got {type(value).__name__}")
    return value


_OLLAMA_MODELS_FLAG_KEYS = {"auto_load", "auto_unload"}


def _validate_ollama_model_map(value, key: str = "translate.ollama_models") -> dict:
    """Validate the [translate.ollama_models] table. Returns a dict that
    mixes two schemas:
      - "auto_load" / "auto_unload" → bool (control flags)
      - "<src>-<tgt>" → model name string (pair → model map)
    Any other key shape is rejected. Callers split the two by value type
    (use isinstance(v, str) to pick out pair entries)."""
    if not isinstance(value, dict):
        raise CliError(f"{key}: expected a table of language pairs to model names")
    out: dict[str, object] = {}
    pair_re = re.compile(r"^[a-z]{2,3}[:-][a-z]{2,3}$")
    for raw_key, raw_val in value.items():
        # Flag keys first — they live alongside the pair mappings because the
        # user explicitly asked for these controls under [translate.ollama_models].
        if raw_key in _OLLAMA_MODELS_FLAG_KEYS:
            out[raw_key] = _validate_bool(raw_val, f"{key}.{raw_key}")
            continue
        pair = str(raw_key).strip().lower().replace("_", "-").replace(":", "-")
        if not pair_re.match(pair):
            raise CliError(
                f"{key}.{raw_key}: expected source-target pair like ja-ko or ja:ko, "
                f"or one of: {', '.join(sorted(_OLLAMA_MODELS_FLAG_KEYS))}"
            )
        if not isinstance(raw_val, str) or not raw_val.strip():
            raise CliError(f"{key}.{raw_key}: expected non-empty model name string")
        src, tgt = pair.split("-", 1)
        src = LANGUAGE_ALIASES.get(src, src)
        tgt = LANGUAGE_ALIASES.get(tgt, tgt)
        out[f"{src}-{tgt}"] = raw_val.strip()
    return out


def _normalize_section_keys(section: dict) -> dict:
    """Return a copy with hyphens in top-level keys normalized to underscores.

    Lets users write either `dry-run` or `dry_run` in any TOML section without
    knowing which spelling is canonical. Nested dicts (e.g. translate.ollama_models)
    are walked one level too so per-pair `"ja:ko"` keys aren't mangled.
    On collision (both `dry-run` and `dry_run` present), the underscore form
    wins silently — it's the canonical spelling."""
    if not isinstance(section, dict):
        return section
    out: dict = {}
    for k, v in section.items():
        if isinstance(k, str) and "-" in k and ":" not in k:
            canon = k.replace("-", "_")
            if canon in section and canon != k:
                # underscore form already present — let it win, skip hyphen form
                continue
            out[canon] = v
        else:
            out[k] = v
    # Walk nested tables one level so things like [translate.ollama_models]
    # also get the same treatment.
    for k, v in list(out.items()):
        if isinstance(v, dict):
            out[k] = _normalize_section_keys(v)
    return out


def _validate_section(raw: dict, name: str) -> dict:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise CliError(f"[{name}]: expected a table, got {type(section).__name__}")
    return _normalize_section_keys(section)


_VALID_CONFIG_SECTIONS = ("fetch", "translate", "modify", "merge", "output", "experimental")


def _reject_unknown_sections(raw: dict) -> None:
    """Reject any top-level section that isn't part of the config schema.
    Point the user at the example template and `config --show`."""
    unknown = [
        s for s in raw
        if isinstance(raw[s], dict) and s not in _VALID_CONFIG_SECTIONS
    ]
    if not unknown:
        return
    raise CliError(
        f"user_settings.toml has unknown section(s): {', '.join(f'[{s}]' for s in unknown)}. "
        f"Valid sections: {', '.join(f'[{s}]' for s in _VALID_CONFIG_SECTIONS)}. "
        "Run `getsubtitle --help config` for the schema, or "
        "`getsubtitle config --init --force` to regenerate the template."
    )


def validate_user_config(raw: dict) -> dict:
    """Validate a raw TOML dict and return only the recognised, validated
    settings. Unknown keys are silently ignored so the file can evolve.

    Schema (sections in pipeline-execution order):
      [fetch] / [translate] / [modify] / [merge] / [output] / [experimental]

    Pre-pipeline section names ([download] / [combine] / [furigana]) are
    rejected with a migration hint."""
    _reject_unknown_sections(raw)
    out: dict[str, dict] = {}

    # [fetch]
    f = _validate_section(raw, "fetch")
    f_out: dict[str, object] = {}
    if "languages" in f:
        f_out["languages"] = _validate_lang_list(f["languages"], "fetch.languages")
    elif "langs" in f:  # alias
        f_out["languages"] = _validate_lang_list(f["langs"], "fetch.langs")
    if "release_source" in f:
        f_out["release_source"] = _validate_enum(
            f["release_source"], "fetch.release_source",
            {"auto", "any", "netflix", "crunchyroll", "amazon",
             "hulu", "hbo", "disney", "apple", "paramount", "peacock"},
        )
    if "manual_search" in f:
        val = f["manual_search"]
        if isinstance(val, bool):
            f_out["manual_search"] = "on-missing" if val else "off"
        else:
            f_out["manual_search"] = _validate_enum(
                val, "fetch.manual_search", {"off", "on-missing", "always"}
            )
    if "manual_search_open" in f:
        val = f["manual_search_open"]
        if isinstance(val, bool):
            f_out["manual_search_open"] = "always" if val else "never"
        else:
            f_out["manual_search_open"] = _validate_enum(
                val, "fetch.manual_search_open", {"ask", "always", "never"}
            )
    out["fetch"] = f_out

    # [translate]
    tr = _validate_section(raw, "translate")
    tr_out: dict[str, object] = {}
    if "engine" in tr:
        if not isinstance(tr["engine"], str):
            raise CliError("translate.engine: expected string ('', 'argos', 'ollama'[':MODEL'], or 'deepl')")
        # Accept "ollama:qwen3:8b" colon-spec.
        engine_head = tr["engine"].split(":", 1)[0] if tr["engine"] else ""
        if tr["engine"] and engine_head not in {"argos", "ollama", "deepl"}:
            raise CliError(
                f"translate.engine: expected one of ['argos', 'ollama', 'deepl'] or empty, got {tr['engine']!r}"
            )
        tr_out["engine"] = tr["engine"]
    if "model" in tr:
        tr_out["model"] = _validate_str(tr["model"], "translate.model")
    # mt_source accepts string ("ja" / "ko:ja,es:en") or dict
    # ({ko = "ja"} / {es = ["fr", "en"]}).
    # mt_source_lang remains a silent alias for back-compat.
    _mt_source_key = "mt_source" if "mt_source" in tr else ("mt_source_lang" if "mt_source_lang" in tr else None)
    if _mt_source_key is not None:
        val = tr[_mt_source_key]
        if isinstance(val, str):
            tr_out["mt_source_lang"] = val
        elif isinstance(val, dict):
            for target, source in val.items():
                if isinstance(source, str):
                    continue
                if isinstance(source, list) and all(isinstance(item, str) for item in source):
                    continue
                raise CliError(
                    f"translate.{_mt_source_key}.{target}: expected string or list of strings"
                )
            tr_out["mt_source_lang"] = val   # left as dict; _normalize_mt_source converts at use
        else:
            raise CliError(f"translate.{_mt_source_key}: expected string or dict")
    if "strip_reading_before_mt" in tr:
        tr_out["strip_reading_before_mt"] = _validate_bool(
            tr["strip_reading_before_mt"], "translate.strip_reading_before_mt"
        )
    if "ollama_models" in tr:
        tr_out["ollama_models"] = _validate_ollama_model_map(tr["ollama_models"])
    out["translate"] = tr_out

    # [modify]
    m = _validate_section(raw, "modify")
    m_out: dict[str, object] = {}
    for bk in ("single_line", "strip_cc_noise"):
        if bk in m:
            m_out[bk] = _validate_bool(m[bk], f"modify.{bk}")
    # `reading` is the reading SPEC string (e.g. "ja:hiragana,ko:revised").
    # Accepts string or `true` (=> every supported language's default).
    if "reading" in m:
        val = m["reading"]
        if isinstance(val, bool) or isinstance(val, str):
            m_out["reading"] = val
        else:
            raise CliError(
                "modify.reading: expected string SPEC "
                '(e.g. "ja:hiragana", "ko:revised", "ja:hiragana,ko:revised") or bool'
            )
    # `reading_format` selects output format(s) for the side files.
    if "reading_format" in m:
        if not isinstance(m["reading_format"], str):
            raise CliError("modify.reading_format: expected string (srt, ass, vtt, or 'all')")
        parse_furigana_formats(m["reading_format"])
        m_out["reading_format"] = m["reading_format"]
    out["modify"] = m_out

    # [merge]
    mg = _validate_section(raw, "merge")
    mg_out: dict[str, object] = {}
    if "languages" in mg:
        mg_out["languages"] = _validate_lang_list(mg["languages"], "merge.languages")
    elif "langs" in mg:
        mg_out["languages"] = _validate_lang_list(mg["langs"], "merge.langs")
    if "sync" in mg:
        mg_out["sync"] = _validate_enum(mg["sync"], "merge.sync", {"auto", "strict", "loose"})
    for bk in ("preserve_lines", "reading", "watermark", "label_langs"):
        if bk in mg:
            mg_out[bk] = _validate_bool(mg[bk], f"merge.{bk}")
    if "priority" in mg:
        value = mg["priority"]
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            raise CliError("merge.priority: expected a list of language codes, e.g. ['ja', 'en']")
        mg_out["priority"] = [x.lower() for x in value]
    out["merge"] = mg_out

    # [output]
    o = _validate_section(raw, "output")
    o_out: dict[str, object] = {}
    # target (canonical) or root (alias)
    if "target" in o:
        o_out["target"] = _validate_str(o["target"], "output.target")
    elif "root" in o:
        o_out["target"] = _validate_str(o["root"], "output.root")
    if "layout" in o:
        o_out["layout"] = _validate_enum(o["layout"], "output.layout", {"archive", "flat", "plex"})
    for bk in ("open_folder", "force", "debug_providers"):
        if bk in o:
            o_out[bk] = _validate_bool(o[bk], f"output.{bk}")
    out["output"] = o_out

    # [experimental]
    exp = _validate_section(raw, "experimental")
    exp_out: dict[str, object] = {}
    for bk in ("subdivx", "addic7ed"):
        if bk in exp:
            exp_out[bk] = _validate_bool(exp[bk], f"experimental.{bk}")
    out["experimental"] = exp_out

    return out


def load_user_config() -> dict:
    """Load and validate the active user_settings.toml, or return {} if
    missing. Raises CliError on parse/validation failures."""
    path = config_path()
    if not path.exists():
        return {}
    tomllib = _import_tomllib()
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        raise CliError(f"Could not parse {path}: {e}") from e
    return validate_user_config(raw)


def _example_template_text() -> str:
    """Return the example user_settings.toml content.

    Tries the file alongside the script first (editable install); falls back
    to a minimal embedded template so `config --init` works after pip install
    even if package_data isn't present."""
    candidates: list[Path] = []
    try:
        here = Path(__file__).resolve().parent
        candidates.append(here / CONFIG_EXAMPLE_FILE_NAME)
    except NameError:  # __file__ not defined under runpy
        pass
    candidates.append(Path.cwd() / CONFIG_EXAMPLE_FILE_NAME)
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    return _EMBEDDED_EXAMPLE_TEMPLATE


# Embedded fallback. Kept intentionally minimal — the on-disk
# user_settings.example.toml at the repo root is the authoritative copy and
# preferred whenever it can be located.
_EMBEDDED_EXAMPLE_TEMPLATE = """\
# getsubtitle user settings — minimal embedded fallback.
# Schema mirrors the pipeline TOML: fetch → translate → modify → merge → output.
# Edit any value to change the corresponding default. CLI flags always win.
# DO NOT put API keys here (set with: getsubtitle --set-key {jimaku|wyzie|subdl|deepl|tmdb}).

[fetch]
languages = "ja"                  # full names also work: "japanese,english"
release_source = "auto"           # auto | any | netflix | crunchyroll | amazon | hulu | hbo | disney | apple | paramount | peacock
manual_search = "on-missing"      # off | on-missing | always
manual_search_open = "ask"        # ask | always | never

[translate]
engine = "argos"                  # "" | argos | ollama[:model] | deepl
model = "qwen3:4b"                # default Ollama model
mt_source = "auto"                # "auto" | "ja" | "ko:ja,es:en" | { ko = "ja" }
strip_reading_before_mt = true   # strip 漢字（かんじ） readings before MT

[translate.ollama_models]
auto_load = true                  # pull missing models on demand
auto_unload = true                # free model from RAM/VRAM after MT
# Per-pair Ollama model overrides (uncomment to use):
# "ja:ko" = "qwen3:4b"
# "ja:en" = "qwen3:8b"
# "en:es" = "llama3.2:3b"

[modify]
single_line = true                # asbplayer-friendly one-line cues
strip_cc_noise = true             # remove broadcast ➡ arrows and 《...》 wrappers
reading = "ja:hiragana"           # e.g. ja:hiragana, ko:revised, zh:marks
reading_format = "srt"            # srt | ass | vtt | all

[merge]
languages = "ja,en"
sync = "auto"                     # auto | strict | loose
preserve_lines = false
priority = []                     # e.g. ["ja", "en", "ko"]
reading = "ja:hiragana"           # inline readings into merged output

[output]
target = "~/Downloads/GetSubtitle"
layout = "archive"                # archive | flat | plex
open_folder = false
force = false
debug_providers = false

[experimental]
subdivx = false
addic7ed = false
"""


def _toml_format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Crude but sufficient: backslash-escape quotes.
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_format_value(v) for v in value) + "]"
    if isinstance(value, (int, float)):
        return str(value)
    return repr(value)


def render_effective_config(user_cfg: dict | None = None) -> str:
    """Return a TOML-ish dump of built-in defaults merged with user settings.
    Marks user-overridden keys with a trailing '# from user_settings.toml'."""
    if user_cfg is None:
        user_cfg = load_user_config()
    lines: list[str] = [
        "# Effective getsubtitle settings (built-in defaults overlaid with",
        "# user_settings.toml). API keys are never printed here.",
        f"# Config file: {config_path()}",
        "",
    ]
    for section_name, section_defaults in BUILTIN_CONFIG_DEFAULTS.items():
        overrides = user_cfg.get(section_name, {})
        merged: dict[str, object] = dict(section_defaults)
        merged.update(overrides)
        nested_tables: list[tuple[str, dict]] = []
        lines.append(f"[{section_name}]")
        for key, value in merged.items():
            if isinstance(value, dict):
                nested_tables.append((key, value))
                continue
            suffix = "  # from user_settings.toml" if key in overrides else ""
            lines.append(f"{key} = {_toml_format_value(value)}{suffix}")
        lines.append("")
        for key, table in nested_tables:
            lines.append(f"[{section_name}.{key}]")
            for nested_key, nested_value in table.items():
                lines.append(f"{nested_key} = {_toml_format_value(nested_value)}")
            lines.append("")
    return "\n".join(lines)


def _open_in_default_app(target: str | Path) -> None:
    """Open a file or URL with the platform's default handler."""
    target_str = str(target)
    if sys.platform == "darwin":
        cmd = ["open", target_str]
    elif sys.platform.startswith("win"):
        try:
            os.startfile(target_str)  # type: ignore[attr-defined]
            return
        except Exception:
            cmd = ["explorer", target_str]
    elif shutil.which("xdg-open"):
        cmd = ["xdg-open", target_str]
    elif shutil.which("open"):
        cmd = ["open", target_str]
    else:
        raise CliError(f"No app opener found. Open manually: {target_str}")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise CliError(f"Could not open: {result.stderr.strip() or 'unknown error'}")


def build_config_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getsubtitle config",
        description="Manage the user_settings.toml file (non-secret defaults).",
    )
    action = p.add_argument_group("action")
    action.add_argument("--path", action="store_true", help="Print the expected config file path.")
    action.add_argument("--init", action="store_true", help="Create user_settings.toml from the example template.")
    action.add_argument("--open", action="store_true", help="Open the config file in your default editor.")
    action.add_argument("--show", action="store_true", help="Print the effective non-secret config.")
    p.add_argument("--force", action="store_true", help="With --init: overwrite an existing config.")
    return p


def config_main(argv: list[str]) -> int:
    parser = build_config_parser()
    args = parser.parse_args(argv)
    actions = [args.path, args.init, getattr(args, "open"), args.show]
    if sum(bool(a) for a in actions) > 1:
        raise CliError("Pass exactly one of --path, --init, --open, --show.")
    if not any(actions):
        parser.print_help()
        return 0

    path = config_path()

    if args.path:
        print(path)
        return 0

    if args.init:
        if path.exists() and not args.force:
            raise CliError(f"{path} already exists. Re-run with --force to overwrite.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_example_template_text(), encoding="utf-8")
        print(f"Created {path}")
        print("Edit this file to set your defaults; CLI flags still override anything you set here.")
        return 0

    if getattr(args, "open"):
        if not path.exists():
            raise CliError(f"{path} does not exist. Run: getsubtitle config --init")
        _open_in_default_app(path)
        return 0

    if args.show:
        sys.stdout.write(render_effective_config())
        return 0

    return 0  # unreachable


# ═══════════════════════════════════════════════════════════════════════
# First-time setup onboarding
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class _SetupChoice:
    native: list[str]
    learning: list[str]
    content: str
    venue: str
    mt: str


@dataclass
class _SetupRecommendation:
    key: str
    title: str
    reason: str
    cost: str
    setup_time: str
    url: str | None = None
    provider: str | None = None
    selected_by_default: bool = True


# Known-good ISO 639-1 codes. Anything outside this set (after alias
# normalisation) is either a typo or a language we don't have provider
# coverage for, so we reject early and ask the user to retype.
_SETUP_KNOWN_LANG_CODES: frozenset[str] = frozenset(LANGUAGE_TAG_VARIANTS) | frozenset(
    LANGUAGE_ALIASES.values()
)


def _setup_parse_langs(raw: str) -> list[str]:
    """Normalise a comma-list of language tokens to ISO 639-1 codes.
    Rejects unknown codes with a `CliError` so typos surface immediately
    instead of getting written into the user's config file."""
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    out: list[str] = []
    bad: list[str] = []
    for part in parts:
        canon = LANGUAGE_ALIASES.get(part, part)
        if canon not in _SETUP_KNOWN_LANG_CODES:
            bad.append(part)
            continue
        if canon not in out:
            out.append(canon)
    if bad:
        known = ", ".join(sorted(c for c in _SETUP_KNOWN_LANG_CODES if len(c) <= 3))
        raise CliError(
            f"setup: didn't recognise language code(s): {', '.join(bad)}. "
            f"Try one of: {known}."
        )
    return out


def _setup_select(question: str, options: list[tuple[str, str]], default: str) -> str:
    """Numbered multiple-choice prompt. Options are (key, label) pairs;
    `key` is the internal token the caller maps to a value. We display
    1..N and translate the typed number back to the matching key, so the
    user answers in numbers (consistent with the interactive wizard) while
    callers keep their stable key->value mapping. Re-prompts on
    unrecognised input rather than silently falling back to the default —
    silent fallback led to people answering 'movies' and getting routed
    into the 'mixed' branch without knowing."""
    print()
    print(question)
    keys = [key for key, _label in options]
    for i, (_key, label) in enumerate(options, start=1):
        print(f"  {i}) {label}")
    # `default` arrives as a key; surface its number in the prompt.
    default_num = str(keys.index(default) + 1) if default in keys else "1"
    while True:
        answer = _wizard_prompt("Number", default_num).strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return keys[int(answer) - 1]
        print(f"    (didn't recognise {answer!r} — pick a number 1-{len(keys)})")


def _setup_system_summary() -> list[str]:
    rows = [
        f"OS: {platform.system() or sys.platform}",
        f"CPU: {platform.machine() or 'unknown'}",
    ]
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        rows.append("Apple Silicon detected: good fit for small/medium Ollama models.")
    elif platform.machine():
        rows.append("Hardware note: offline LLM speed depends heavily on RAM/GPU.")
    ollama_state = "installed" if shutil.which("ollama") else "not installed"
    # Daemon reachability is a more useful signal than just "binary on PATH":
    # a user can have Ollama installed but the daemon stopped.
    if shutil.which("ollama") and _wizard_ollama_reachable():
        ollama_state += " (daemon reachable)"
    elif shutil.which("ollama"):
        ollama_state += " (daemon not running — start with `ollama serve`)"
    rows.append("Ollama: " + ollama_state)
    rows.append("Japanese reading-aid dependency: " + ("installed" if _setup_module_exists("pykakasi") else "not installed"))
    return rows


def _setup_module_exists(module_name: str) -> bool:
    """Cheap availability check via importlib's spec finder. Avoids
    triggering the target module's side-effecting top-level code (pykakasi
    builds dictionaries on import; argostranslate scans for language packs)."""
    import importlib.util
    return importlib.util.find_spec(module_name) is not None


# Per-language reading-aid metadata for the setup recommender. Mirrors
# _WIZARD_READING_AID_MENU but condensed to one row per language since
# setup picks the language's default mode.
#
# (lang, default_spec, label, status_note)
_SETUP_READING_AID_BY_LANG: dict[str, tuple[str, str, str]] = {
    "ja": ("ja:hiragana", "Japanese hiragana furigana above kanji",
           "Ships now via pykakasi."),
    "ko": ("ko:revised", "Korean Revised Romanization above Hangul",
           "Ships now via g2pk + korean-romanizer."),
    "zh": ("zh:marks", "Mandarin pinyin (with tone marks) above hanzi",
           "Ships now via pypinyin."),
    "yue": ("yue:numbers", "Cantonese jyutping above characters",
            "Ships now via pycantonese."),
    "th": ("th:royal-thai", "Thai Royal-Thai transliteration",
           "Wired through; backend lands per ROADMAP."),
    "ar": ("ar:ala-lc", "Arabic ALA-LC romanization",
           "Wired through; backend lands per ROADMAP."),
    "hi": ("hi:iast", "Hindi IAST transliteration",
           "Wired through; backend lands per ROADMAP."),
    "ru": ("ru:iso-9", "Russian ISO-9 transliteration",
           "Wired through; backend lands per ROADMAP."),
}


# Per-language "why" line, install-size hint, and setup-time string for the
# reading-aid recommendation. Lets a Korean learner see "essential while
# you're decoding Hangul" instead of the generic "shows pronunciation".
# install_mb is approximate disk impact AFTER dependencies — pip's own
# output is the source of truth at install time, but a one-line preview
# avoids surprising the user when g2pk pulls nltk.
#
# (reason, cost_line, setup_time_line)
_SETUP_READING_AID_PROSE: dict[str, tuple[str, str, str]] = {
    "ja": (
        "Hiragana above each kanji block (furigana). Essential while you're "
        "still building your kanji recognition — drops gracefully once you don't "
        "need it.",
        "Free; pykakasi pulls a small dictionary (~3 MB).",
        "~10 seconds (pip install).",
    ),
    "ko": (
        "Revised Romanization above each Hangul syllable, with G2P phonological "
        "corrections (같이→gachi, 읽는→ingneun). Most useful in the first ~100 "
        "hours of Korean reading.",
        "Free; g2pk pulls nltk + a small corpus (~80 MB total).",
        "~30-60 seconds (pip install; first run pulls nltk data).",
    ),
    "zh": (
        "Pinyin with tone marks above each hanzi (nǐ hǎo). pypinyin handles "
        "polyphones and tone sandhi. Critical while you're still acquiring "
        "characters.",
        "Free; pypinyin is a small pure-Python package (~5 MB).",
        "~5-10 seconds (pip install).",
    ),
    "yue": (
        "Jyutping with numbered tones above each character. Cantonese-specific; "
        "pinyin tones don't transfer.",
        "Free; pycantonese includes a Cantonese lexicon (~20 MB).",
        "~30 seconds (pip install).",
    ),
    "th": (
        "Royal Thai transliteration above each cluster. Useful for learners "
        "still building tone-mark intuition.",
        "Free (when backend ships).",
        "0 minutes — saves into config; activates when backend ships.",
    ),
    "ar": (
        "ALA-LC romanization above each Arabic word. Standard academic form.",
        "Free (when backend ships).",
        "0 minutes — saves into config; activates when backend ships.",
    ),
    "hi": (
        "IAST transliteration above devanagari. Standard academic form for "
        "Indic scripts.",
        "Free (when backend ships).",
        "0 minutes — saves into config; activates when backend ships.",
    ),
    "ru": (
        "ISO-9 transliteration above Cyrillic. Most direct 1-to-1 mapping.",
        "Free (when backend ships).",
        "0 minutes — saves into config; activates when backend ships.",
    ),
}


def _setup_mt_source_bias(choice: "_SetupChoice") -> dict[str, str]:
    """Decide whether the user's learning ↔ native combination warrants
    a per-target source override for MT.

    The auto-picker already prefers grammatically-close pairs at runtime,
    so this helper only writes an explicit `[translate].mt_source` block
    when:
      - Both the learner's target and a native language are CJK
        (ja / ko / zh) — typology is close enough that MT quality jumps
        noticeably with the right source.
      - The user has multiple CJK natives or learning targets, where
        auto-picking might choose the wrong one.

    Returns a `{ target: source }` dict, or an empty dict to fall back
    to `mt_source = "auto"`."""
    cjk = {"ja", "ko", "zh"}
    pairs: dict[str, str] = {}
    for target in choice.learning:
        if target not in cjk:
            continue
        # Pick the closest CJK native (skipping the target itself).
        close = [n for n in choice.native if n in cjk and n != target]
        if close:
            pairs[target] = close[0]
    return pairs


def _setup_ollama_pair_defaults(choice: "_SetupChoice") -> list[tuple[str, str]]:
    """Generate `(src:tgt, model)` rows for `[translate.ollama_models]`
    based on the user's actual learning ← native combinations.

    Seeds the small CJK-capable default model (DEFAULT_OLLAMA_MODEL) for
    every realistic translate direction the user will hit. This way the
    first time they run `translate ollama` after setup, Ollama already
    has the right model assignment ready — no "huh, which model do I
    pick" friction.

    Direction is `src:tgt` because MT translates from source to target.
    For a Japanese-native learning Korean (`learning=ko`, `native=ja`),
    the MT direction is ja→ko, so we emit `"ja:ko" = "qwen3:4b"`."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    # learning_targets × native_sources, plus English fallback.
    sources = list(choice.native) or ["en"]
    if "en" not in sources:
        sources = sources + ["en"]
    for target in choice.learning:
        for source in sources:
            if source == target:
                continue
            key = f"{source}:{target}"
            if key in seen:
                continue
            seen.add(key)
            pairs.append((key, DEFAULT_OLLAMA_MODEL))
    return pairs


def _setup_recommendations(choice: _SetupChoice) -> list[_SetupRecommendation]:
    """Build the recommendation list in the order they're presented to
    the user. Ordering principle: provider sources first (they unlock
    the *content* the user wants), then reading aids for each learning
    language (the differentiating feature), then MT, then the config
    file at the end (it bundles the other answers).

    Reading aids cover every language in _SETUP_READING_AID_BY_LANG, not
    just Japanese — Korean, Chinese, Cantonese, Thai, etc. are accepted
    too (with a "backend coming" note only for deferred languages)."""
    learning = set(choice.learning)
    content = choice.content
    mt = choice.mt
    recs: list[_SetupRecommendation] = []

    # ── Subtitle source providers ─────────────────────────────────────
    if "ja" in learning or content == "anime":
        recs.append(_SetupRecommendation(
            key="jimaku",
            title="Jimaku",
            reason="Recommended for Japanese anime subtitles.",
            cost="Free.",
            setup_time="About 2 minutes.",
            url=KEY_PROVIDERS["jimaku"]["url"],
            provider="jimaku",
        ))
    if content in {"movie", "tv", "mixed"} or any(
        lang in learning for lang in ["en", "ko", "es", "fr", "zh"]
    ):
        recs.append(_SetupRecommendation(
            key="wyzie",
            title="Wyzie",
            reason="Broad movie/TV subtitle search by IMDb/TMDB ID.",
            cost="Free tier available; paid tier widens source coverage.",
            setup_time="About 2 minutes.",
            url=KEY_PROVIDERS["wyzie"]["url"],
            provider="wyzie",
        ))
        recs.append(_SetupRecommendation(
            key="subdl",
            title="SubDL",
            reason="Fallback source when Wyzie misses, often useful for Korean, Spanish, Chinese, and European subtitles.",
            cost="API key required; SubDL has free and paid tiers.",
            setup_time="About 2 minutes.",
            url=KEY_PROVIDERS["subdl"]["url"],
            provider="subdl",
            selected_by_default=False,
        ))
    if content in {"movie", "tv", "mixed"}:
        recs.append(_SetupRecommendation(
            key="tmdb",
            title="TMDB",
            reason="Improves title matching and enables full-season detection for non-anime TV.",
            cost="Free API key.",
            setup_time="About 3 minutes.",
            url=KEY_PROVIDERS["tmdb"]["url"],
            provider="tmdb",
        ))

    # ── Reading aids — one per learning language we recognise. Ordered
    # right after providers because they're the highest-leverage UX
    # win for the most common (Japanese-learner) case. Each rec carries
    # its romanization spec in `key` so _setup_config_text can splice
    # them together. The per-language prose (reason/cost/setup-time)
    # lives in _SETUP_READING_AID_PROSE so each language gets a
    # learner-targeted "why" plus an honest size estimate.
    for lang in choice.learning:
        meta = _SETUP_READING_AID_BY_LANG.get(lang)
        if not meta:
            continue
        spec, label, status = meta
        shipped = lang in ("ja", "ko", "zh", "yue")   # backends actually live today
        prose = _SETUP_READING_AID_PROSE.get(lang)
        if prose is not None:
            reason, cost, setup_time = prose
        else:
            # Fallback for any new language added to the menu before its
            # prose row lands; better to ship something than nothing.
            reason = f"Pronunciation guide above {lang.upper()} text."
            cost = "Free." if shipped else "Free (when backend ships)."
            setup_time = (
                "~30 seconds (pip install)." if shipped
                else "0 minutes — saves into config; activates when backend ships."
            )
        recs.append(_SetupRecommendation(
            key=f"reading:{spec}",
            title=f"Reading aid — {label}",
            reason=reason,
            cost=cost,
            setup_time=setup_time,
            selected_by_default=shipped,
        ))

    # ── Machine translation ──────────────────────────────────────────
    # Prefer Ollama over Argos when the daemon is reachable: same
    # offline guarantee, much better quality on CJK pairs.
    if mt == "offline":
        if shutil.which("ollama") and _wizard_ollama_reachable():
            recs.append(_SetupRecommendation(
                key="ollama",
                title="Ollama (offline LLM MT)",
                reason="Offline machine translation via the Ollama daemon. Much higher quality than Argos on CJK pairs.",
                cost="Free, but RAM/VRAM hungry — see the system summary above.",
                setup_time=f"Default model is {DEFAULT_OLLAMA_MODEL}; auto-pulled on first use.",
                selected_by_default=True,
            ))
        else:
            recs.append(_SetupRecommendation(
                key="argos",
                title="Argos Translate",
                reason="Free offline machine translation fallback.",
                cost="Free.",
                setup_time="0-5 minutes depending on language packages.",
                selected_by_default=True,
            ))
    if mt == "online":
        recs.append(_SetupRecommendation(
            key="deepl",
            title="DeepL",
            reason="Best-quality online machine translation fallback.",
            cost="Free API tier includes 500,000 characters/month; paid tiers available. Roughly 50-80 anime episodes depending on subtitle length.",
            setup_time="About 2 minutes.",
            url=KEY_PROVIDERS["deepl"]["url"],
            provider="deepl",
        ))

    # ── Config file — last so it can bundle everything answered above.
    recs.append(_SetupRecommendation(
        key="config",
        title="user_settings.toml",
        reason="Saves your defaults so future commands are shorter.",
        cost="Free.",
        setup_time="Instant.",
        selected_by_default=True,
    ))
    return recs


def _setup_print_viewing_guidance(choice: _SetupChoice) -> None:
    print()
    print("Viewing guidance:")
    if choice.venue == "tablet":
        print("  Tablet/TV streaming apps usually cannot import custom subtitle files.")
        print("  Recommended alternatives: web browser + asbplayer, Plex, or a local video player.")
    elif choice.venue == "browser":
        print("  Browser streaming works best with asbplayer.")
        print("  For Japanese pronunciation guides: asbplayer Settings > Misc > Subtitles > Subtitle HTML = Render.")
    elif choice.venue == "plex":
        print("  Plex works best with SRT for normal playback, or merged study files for separate study sessions.")
    elif choice.venue == "local":
        print("  VLC/IINA/mpv work well with SRT. Use VTT when your player supports HTML/ruby subtitles.")
    else:
        print("  Mixed viewing is fine. Use SRT for compatibility; VTT for asbplayer ruby reading aids.")


def _setup_print_recommendations(recs: list[_SetupRecommendation]) -> None:
    print()
    print("Recommended setup:")
    for idx, rec in enumerate(recs, start=1):
        mark = "recommended" if rec.selected_by_default else "optional"
        print(f"\n  {idx}. {rec.title} ({mark})")
        print(f"     {rec.reason}")
        print(f"     Cost: {rec.cost}")
        print(f"     Setup time: {rec.setup_time}")
        if rec.key == "argos":
            print("     Quality: lower, but private and free.")
        if rec.key == "ja-reading":
            print("     Output tip: VTT looks best in asbplayer.")
        if rec.url:
            print(f"     URL: {rec.url}")


def _setup_config_text(choice: _SetupChoice) -> str:
    """Emit a user_settings.toml using canonical key names.
    Reading aids land under `[modify].reading` (NOT the legacy
    `[modify].furigana = "hiragana"` form). Engine picks Ollama when
    the daemon is reachable and the user wanted offline MT."""
    fetch_langs = ",".join(
        [*choice.learning, *[lang for lang in choice.native if lang not in choice.learning]]
    ) or "ja,en"
    merge_langs = fetch_langs

    # Build the romanization spec from every recognised learning language.
    # Each entry uses the language's documented default (ja:hiragana,
    # ko:revised, zh:marks, …) so the user can re-run with the wizard
    # and get the same defaults.
    rom_specs = [
        _SETUP_READING_AID_BY_LANG[lang][0]
        for lang in choice.learning
        if lang in _SETUP_READING_AID_BY_LANG
    ]
    has_reading_aids = bool(rom_specs)
    wants_ja_ruby = any(s.startswith("ja:") for s in rom_specs)
    fmt = "vtt" if wants_ja_ruby and choice.venue == "browser" else "srt"

    # MT engine selection mirrors _setup_recommendations: prefer Ollama
    # when available, otherwise Argos for offline; DeepL for online.
    if choice.mt == "online":
        mt_engine = "deepl"
    elif choice.mt == "offline":
        mt_engine = "ollama" if (shutil.which("ollama") and _wizard_ollama_reachable()) else "argos"
    else:
        mt_engine = ""

    lines = [
        "# Generated by `getsubtitle setup`",
        "# API keys are not stored here. Use `getsubtitle --set-key PROVIDER`.",
        "",
        "[fetch]",
        f'languages = "{fetch_langs}"',
        'release_source = "auto"',
        'manual_search = "on-missing"',
        'manual_search_open = "ask"',
        "",
        "[modify]",
        "single_line = true",
        "strip_cc_noise = true",
    ]
    if has_reading_aids:
        # `reading` is the canonical key (covers ja/ko/zh/…).
        lines.append(f'reading = "{",".join(rom_specs)}"')
        lines.append(f'reading_format = "{fmt}"')
    lines += [
        "",
        "[merge]",
        f'languages = "{merge_langs}"',
        'sync = "auto"',
        "preserve_lines = false",
        f'format = "{fmt}"',
    ]
    if wants_ja_ruby:
        # Inline per-language readings (e.g. 漢字（かんじ）) into the merged
        # cue stack on the matching language line.
        lines.append("reading = true")
    lines += [
        "",
        "[output]",
        'target = "~/Downloads/GetSubtitle"',
        'layout = "archive"',
        "open_folder = false",
        "",
    ]
    if mt_engine:
        lines.append("[translate]")
        lines.append(f'engine = "{mt_engine}"')
        # CJK-aware MT-source bias: when both learning target and a
        # native language are in {ja,ko,zh}, write an explicit per-target
        # source map. Falls back to "auto" otherwise.
        mt_bias = _setup_mt_source_bias(choice)
        if mt_bias:
            inline = ", ".join(f'{k} = "{v}"' for k, v in mt_bias.items())
            lines.append("mt_source = { " + inline + " }")
        else:
            lines.append('mt_source = "auto"')
        if mt_engine == "ollama":
            lines.append("")
            lines.append("[translate.ollama_models]")
            lines.append("auto_load = true")
            lines.append("auto_unload = true")
            # Seed the user's actual learning ← native pairs so Ollama
            # has the right model assignment ready on first translate.
            pair_defaults = _setup_ollama_pair_defaults(choice)
            for pair, model in pair_defaults:
                lines.append(f'"{pair}" = "{model}"')
        lines.append("")
    return "\n".join(lines)


def _setup_write_config(choice: _SetupChoice) -> bool:
    """Write user_settings.toml with the wizard's choices. Shows a full
    preview before any write, and backs up an existing file to
    `user_settings.toml.bak` before overwriting so destructive writes
    are reversible."""
    path = config_path()
    new_text = _setup_config_text(choice)

    print()
    print("  Will write the following to user_settings.toml:")
    print("  " + "─" * 60)
    for line in new_text.splitlines():
        print("  │ " + line)
    print("  " + "─" * 60)

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing.strip() == new_text.strip():
            print(f"  No change — {path} already matches.")
            return True
        print(f"  Existing file: {path}")
        print("  A backup will be saved to user_settings.toml.bak before overwriting.")
        if not _wizard_yesno(f"  Overwrite (backing up to .bak)?", default=False):
            print(f"  Kept existing config: {path}")
            return False
        try:
            backup = path.with_suffix(path.suffix + ".bak")
            backup.write_text(existing, encoding="utf-8")
            print(f"  Backup: {backup}")
        except OSError as e:
            print(f"  Backup failed ({e}); aborting write.")
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    print(f"  Created {path}")
    return True


# Approximate install size and duration for each known extra. Lets us
# warn the user before pulling heavy dependency trees (g2pk pulls nltk +
# a corpus; everything else is small). Numbers are conservative — pip's
# own output is the source of truth at install time.
_SETUP_INSTALL_HINTS: dict[str, tuple[str, str]] = {
    "furigana":        ("~3 MB",  "~10 seconds"),
    "romanization-ko": ("~80 MB", "30-60 seconds (nltk corpus on first run)"),
    "romanization-zh": ("~5 MB",  "~10 seconds"),
    "romanization-yue": ("~20 MB", "~30 seconds"),
}
# Same shape but keyed by bare package name for when an extra isn't used.
_SETUP_INSTALL_HINTS_BY_PACKAGE: dict[str, tuple[str, str]] = {
    "pykakasi":          ("~3 MB",  "~10 seconds"),
    "korean-romanizer":  ("~5 MB",  "~10 seconds"),
    "g2pk":              ("~70 MB", "30-60 seconds (nltk corpus on first run)"),
    "pypinyin":          ("~5 MB",  "~10 seconds"),
    "pycantonese":       ("~20 MB", "~30 seconds"),
    "argostranslate":    ("~50 MB", "30-60 seconds"),
}


def _setup_offer_pip_install(package: str, *, extra: str | None = None) -> bool:
    """Print the pip command and offer to run it inside the user's
    current Python environment. Returns True iff the package is
    importable after the (attempted) install.

    Prints a one-line size/duration estimate before asking so the user
    isn't surprised when a heavy extra (e.g. romanization-ko) pulls
    nltk + a corpus."""
    if extra:
        cmd = [sys.executable, "-m", "pip", "install", "-e", f".[{extra}]"]
        shell_form = f'pip install -e ".[{extra}]"'
        size_hint = _SETUP_INSTALL_HINTS.get(extra)
    else:
        cmd = [sys.executable, "-m", "pip", "install", package]
        shell_form = f"pip install {package}"
        size_hint = _SETUP_INSTALL_HINTS_BY_PACKAGE.get(package)
    print(f"  Suggested: {shell_form}")
    if size_hint is not None:
        size, duration = size_hint
        print(f"  Approximate: {size} download, {duration} on a fast connection.")
    print(f"  Will run in: {sys.executable}")
    if not _wizard_yesno("  Install now?", default=True):
        print("  Skipped — install later with the suggested command above.")
        return False
    print("  Running pip — output streams below…")
    print()
    try:
        rc = subprocess.run(cmd, check=False).returncode
    except OSError as e:
        print(f"  pip launch failed: {e}")
        return False
    print()
    if rc != 0:
        print(f"  ✗ pip exited with code {rc}. Try the command manually:")
        print(f"      {shell_form}")
        return False
    # Re-probe — find_spec result is cached on the meta-path importers,
    # so we need to invalidate caches before checking again.
    import importlib
    importlib.invalidate_caches()
    importable = _setup_module_exists(package.replace("-", "_"))
    if importable:
        print(f"  ✓ {package} ready to use.")
    else:
        print(f"  pip reported success but {package} still isn't importable.")
        print(f"  Try the command manually in a fresh shell: {shell_form}")
    return importable


_SETUP_SMOKE_URL = "https://www.imdb.com/title/tt0096283/"   # Totoro — small, ja+en widely available


def _setup_smoke_test(choice: _SetupChoice) -> None:
    """Run one tiny dry-run against a known-good public URL to prove the
    stack works end-to-end. Best-effort; failures here aren't fatal."""
    print()
    print("Smoke test — dry-running one fetch to prove the stack works…")
    langs = ",".join(choice.learning + [lang for lang in choice.native if lang not in choice.learning]) or "ja,en"
    argv = [_SETUP_SMOKE_URL, "-l", langs, "--dry-run"]
    print(f"  $ getsubtitle {' '.join(argv)}")
    try:
        rc = main(argv)
    except CliError as e:
        print(f"  Smoke test surfaced an error: {e}")
        return
    except Exception as e:                                # pragma: no cover
        print(f"  Smoke test crashed unexpectedly: {e}")
        return
    if rc == 0:
        print("  ✓ Stack works. You're ready for a real run.")
    else:
        print(f"  Smoke test exited with code {rc}. Inspect the output above.")


_SETUP_PROFILE_FILENAME = "setup-profile.toml"


def _setup_profile_path() -> Path:
    """Setup answers live in the *config* dir (not the cache dir) because
    they're durable preferences the user can copy across machines."""
    return config_path().parent / _SETUP_PROFILE_FILENAME


def _setup_save_profile(choice: _SetupChoice) -> None:
    """Persist the setup answers so `getsubtitle -i` can pre-fill them
    on a subsequent run. Best-effort; never fail setup over a write error."""
    path = _setup_profile_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# getsubtitle setup profile — answers from the most recent",
            "# `getsubtitle setup` run. Used by `getsubtitle -i` to skip",
            "# questions you've already answered. Safe to edit or delete.",
            "",
            "[setup]",
            f'native = "{",".join(choice.native)}"',
            f'learning = "{",".join(choice.learning)}"',
            f'content = "{choice.content}"',
            f'venue = "{choice.venue}"',
            f'mt = "{choice.mt}"',
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def _setup_load_profile() -> _SetupChoice | None:
    """Read a previously-saved profile. Returns None if missing or unreadable.
    Used by the wizard to offer pre-filling."""
    path = _setup_profile_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields_in: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        fields_in[k.strip()] = v.strip().strip('"')
    try:
        return _SetupChoice(
            native=[x for x in fields_in.get("native", "").split(",") if x],
            learning=[x for x in fields_in.get("learning", "").split(",") if x],
            content=fields_in.get("content", "mixed"),
            venue=fields_in.get("venue", "browser"),
            mt=fields_in.get("mt", "none"),
        )
    except Exception:
        return None


def _setup_configure_provider(provider: str) -> bool:
    info = KEY_PROVIDERS[provider]
    if provider_has_api_key(provider):
        print(f"  {info['label']}: already configured.")
        return False
    print(f"\n{info['label']} setup")
    print(f"  Use: {info['use']}")
    print(f"  URL: {info['url']}")
    if _wizard_yesno("  Open this page in your default browser?", default=True):
        try:
            open_in_browser(str(info["url"]))
        except CliError as e:
            print(f"  Could not open browser automatically: {e}")
    if not _wizard_yesno(f"  Paste and save {info['label']} API key now?", default=True):
        return False
    key = masked_input(f"{info['label']} API key: ").strip()
    if not key:
        print("  Skipped: no key entered.")
        return False
    if macos_keychain_available():
        keychain_set(KEYCHAIN_SERVICE, str(info["account"]), key)
        print(f"  Saved {info['label']} API key to macOS Keychain.")
        return True
    print(f"  Set this environment variable in your shell: {info['env']}={key}")
    print("  (Not saved automatically because secure key storage is only implemented for macOS Keychain.)")
    return False


def _setup_try_examples() -> None:
    print()
    print("Try one:")
    print()
    print("Easy: Movie, TMDB link — Totoro, Japanese + English subtitles.")
    print('  getsubtitle "https://www.themoviedb.org/movie/8392" -l ja,en')
    print()
    print("Medium: Series, IMDb link — Midnight Diner: Tokyo Stories, Japanese + Korean, with Japanese pronunciation guide.")
    print('  getsubtitle "https://www.imdb.com/title/tt6150576/" -s 1 -e all -l ja,ko --reading ja:hiragana --format vtt')
    print()
    print("Hard: Series + machine translation + merge — Friends S4E3-5, fill missing Spanish from French, then stack French/English/Spanish.")
    print('  getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 4 -e 3-5 -l fr,en,es')
    print('  getsubtitle translate ~/Downloads/GetSubtitle/Friends -s 4 -e 3-5 -l es --engine deepl --mt-source es:fr')
    print('  getsubtitle merge ~/Downloads/GetSubtitle/Friends -s 4 -e 3-5 -l fr,en,es')
    print()
    print("Frequently used settings can be saved into a file:")
    print('  getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 5 -e all --config ./friends.toml')


def setup_main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP_TOPICS["setup"])
        return 0
    if not _wizard_is_interactive():
        raise CliError("setup needs an attached terminal. See: getsubtitle --help setup")

    print("getsubtitle setup")
    print("Let's tune this for what you watch and what you're learning.")

    # If a previous setup left a profile on disk, offer to reuse it so
    # the user only has to confirm rather than re-answer everything.
    existing = _setup_load_profile()
    if existing is not None and _wizard_yesno(
        "Found a saved profile from a previous setup. Re-use it?", default=True
    ):
        choice = existing
        print(
            f"  Loaded: native={','.join(choice.native) or '(none)'}, "
            f"learning={','.join(choice.learning) or '(none)'}, "
            f"content={choice.content}, venue={choice.venue}, mt={choice.mt}"
        )
        print()
        print("System check:")
        for row in _setup_system_summary():
            print("  - " + row)
        _setup_print_viewing_guidance(choice)
        recs = _setup_recommendations(choice)
        _setup_print_recommendations(recs)
        return _setup_run_recommendation_loop(recs, choice)

    native = _setup_parse_langs(_wizard_prompt("What languages do you already understand? (comma-separated)", "english"))
    learning = _setup_parse_langs(_wizard_prompt("What languages are you trying to learn? (comma-separated)", "japanese"))
    content = _setup_select(
        "What do you watch most?",
        [("a", "Movies"), ("b", "TV shows"), ("c", "Anime"), ("d", "Mixed")],
        "d",
    )
    content_value = {"a": "movie", "b": "tv", "c": "anime", "d": "mixed"}[content]
    venue = _setup_select(
        "Where do you watch it?",
        [
            ("a", "Streaming service via web browser"),
            ("b", "Streaming service on tablet/TV app"),
            ("c", "Plex"),
            ("d", "Third-party/local video player with subtitle support"),
            ("e", "Mixed"),
        ],
        "a",
    )
    venue_value = {"a": "browser", "b": "tablet", "c": "plex", "d": "local", "e": "mixed"}[venue]
    mt = _setup_select(
        "Do you want machine translation when subtitles are missing?",
        [("a", "No"), ("b", "Free offline"), ("c", "Best quality online")],
        "a",
    )
    mt_value = {"a": "none", "b": "offline", "c": "online"}[mt]
    choice = _SetupChoice(native=native, learning=learning, content=content_value, venue=venue_value, mt=mt_value)

    print()
    print("System check:")
    for row in _setup_system_summary():
        print("  - " + row)
    _setup_print_viewing_guidance(choice)
    recs = _setup_recommendations(choice)
    _setup_print_recommendations(recs)

    return _setup_run_recommendation_loop(recs, choice)


def _setup_run_recommendation_loop(
    recs: list[_SetupRecommendation], choice: _SetupChoice
) -> int:
    """First-pass through each recommendation, then a "revisit skipped"
    edit-answers loop, then profile save + summary + smoke test + cross-link.
    Extracted so both the fresh-answers and resume-from-profile paths use
    the same finishing flow."""
    completed: list[str] = []
    skipped: list[str] = []
    print()
    print("Choose what to set up now. You can skip anything and come back later.")
    for rec in recs:
        if _setup_run_recommendation(rec, choice):
            completed.append(rec.title)
        else:
            skipped.append(rec.title)

    # Edit-answers loop: let the user revisit skipped items without
    # restarting the wizard. Loops until the user says they're done.
    while skipped:
        print()
        print("Skipped so far:")
        for i, title in enumerate(skipped, start=1):
            print(f"  {i}. {title}")
        pick = _wizard_prompt(
            "Number to revisit (1-N), or 'done'", "done"
        ).lower()
        if not pick.isdigit():
            break
        idx = int(pick) - 1
        if not (0 <= idx < len(skipped)):
            print("  (out of range)")
            continue
        chosen = next((r for r in recs if r.title == skipped[idx]), None)
        if chosen is None:
            break
        if _setup_run_recommendation(chosen, choice):
            completed.append(chosen.title)
            del skipped[idx]

    # Persist the answers so the interactive wizard can pre-fill from them.
    _setup_save_profile(choice)

    print()
    print("Setup summary:")
    print("  Configured: " + (", ".join(completed) if completed else "none yet"))
    print("  Skipped: " + (", ".join(skipped) if skipped else "none"))

    # Optional final smoke test — proves the stack works end-to-end.
    if _wizard_yesno("\nRun a quick smoke test now?", default=True):
        _setup_smoke_test(choice)

    print()
    print("Next steps:")
    print("  • Run `getsubtitle -i` for a guided workflow builder")
    print("    (it will pre-fill from your setup answers).")
    _setup_try_examples()
    return 0


def _setup_run_recommendation(rec: _SetupRecommendation, choice: _SetupChoice) -> bool:
    """Apply a single recommendation. Returns True iff it was actually
    configured (False = skipped/declined/install-deferred). Encapsulates
    the per-key dispatch so both the first pass and the edit-answers
    loop go through the same path."""
    if not _wizard_yesno(f"Set up {rec.title} now?", default=rec.selected_by_default):
        return False
    if rec.provider:
        return _setup_configure_provider(rec.provider)
    if rec.key == "config":
        return _setup_write_config(choice)
    if rec.key.startswith("reading:"):
        spec = rec.key.split(":", 1)[1]   # e.g. "ja:hiragana"
        lang = spec.split(":", 1)[0]
        if lang == "ja":
            if _setup_module_exists("pykakasi"):
                print("  pykakasi already installed.")
                return True
            return _setup_offer_pip_install("pykakasi", extra="furigana")
        if lang == "ko":
            mode = spec.split(":", 1)[1] if ":" in spec else "revised"
            if mode == "yale":
                # Yale is in-tree (no external deps); always installable.
                print("  Yale romanization is in-tree — no install needed.")
                return True
            if _setup_module_exists("korean_romanizer") and _setup_module_exists("g2pk"):
                print("  korean-romanizer and g2pk already installed.")
                return True
            if _setup_module_exists("korean_romanizer"):
                print("  korean-romanizer installed; g2pk missing (output will be naive).")
                print("  For best accuracy on edge cases like 같이→가치:")
                return _setup_offer_pip_install("g2pk")
            return _setup_offer_pip_install("korean-romanizer", extra="romanization-ko")
        if lang == "zh":
            if _setup_module_exists("pypinyin"):
                print("  pypinyin already installed.")
                return True
            return _setup_offer_pip_install("pypinyin", extra="romanization-zh")
        if lang == "yue":
            if _setup_module_exists("pycantonese"):
                print("  pycantonese already installed.")
                return True
            return _setup_offer_pip_install("pycantonese", extra="romanization-yue")
        # Other languages: backend not shipped. The spec lands in the
        # config file (via _setup_config_text); this confirms the user
        # opted in even though the backend isn't live yet.
        print(f"  Saved {spec} into config; backend lands per ROADMAP.")
        return True
    if rec.key == "ollama":
        if shutil.which("ollama") and _wizard_ollama_reachable():
            print("  Ollama daemon reachable.")
            print(f"  The default model is {DEFAULT_OLLAMA_MODEL}; auto_load = true "
                  "in your config will pull it on first translate.")
            return True
        print("  Start the Ollama daemon (`ollama serve`) and re-run setup.")
        return False
    if rec.key == "argos":
        if _setup_module_exists("argostranslate"):
            print("  argostranslate already installed.")
            return True
        return _setup_offer_pip_install("argostranslate")
    return False


def _apply_download_config_defaults(parser: argparse.ArgumentParser) -> None:
    """Push user_settings.toml pipeline-aligned values into the URL-form
    download parser as argparse defaults.

    Reads from the new schema: [fetch] / [translate] / [modify] / [output] /
    [experimental]. Merges BUILTIN_CONFIG_DEFAULTS under any user overrides
    so flips like single_line=true take effect even without a user TOML."""
    try:
        cfg = load_user_config()
    except CliError:
        # Don't let a bad config file break --help. Defer surfacing the
        # error until the user actually tries to run a command — for that
        # path the error will fire again at parse time below.
        cfg = {}

    fetch_cfg = {**BUILTIN_CONFIG_DEFAULTS["fetch"], **cfg.get("fetch", {})}
    tr_cfg = {**BUILTIN_CONFIG_DEFAULTS["translate"], **cfg.get("translate", {})}
    mod_cfg = {**BUILTIN_CONFIG_DEFAULTS["modify"], **cfg.get("modify", {})}
    out_cfg = {**BUILTIN_CONFIG_DEFAULTS["output"], **cfg.get("output", {})}
    exp_cfg = {**BUILTIN_CONFIG_DEFAULTS["experimental"], **cfg.get("experimental", {})}

    overrides: dict[str, object] = {}
    # [fetch] → URL-form download defaults.
    if fetch_cfg.get("languages"):
        overrides["langs"] = fetch_cfg["languages"]
    if fetch_cfg.get("release_source"):
        overrides["release_source"] = fetch_cfg["release_source"]
    if fetch_cfg.get("manual_search"):
        overrides["manual_search"] = fetch_cfg["manual_search"]
    if fetch_cfg.get("manual_search_open"):
        overrides["manual_search_open"] = fetch_cfg["manual_search_open"]
    # [output] → output dir / layout / open_folder.
    if out_cfg.get("target"):
        overrides["output"] = str(Path(str(out_cfg["target"])).expanduser())
    if out_cfg.get("layout"):
        overrides["layout"] = out_cfg["layout"]
    if out_cfg.get("open_folder"):
        overrides["open_folder"] = True
    if out_cfg.get("debug_providers"):
        overrides["debug_providers"] = True
    # [modify] → URL-form post-download cleanup defaults. Booleans set
    # explicitly so the BUILTIN flip reaches argparse.
    overrides["single_line"] = bool(mod_cfg.get("single_line", False))
    overrides["strip_cc_noise"] = bool(mod_cfg.get("strip_cc_noise", False))
    # [modify].reading SPEC drives args.reading; the URL flow runs
    # _apply_reading_to_args() after parse to split it per-language.
    if mod_cfg.get("reading"):
        overrides["reading"] = mod_cfg["reading"]
    if mod_cfg.get("reading_format"):
        overrides["reading_format"] = mod_cfg["reading_format"]
    # [translate] → MT defaults.
    if tr_cfg.get("engine"):
        engine_spec = str(tr_cfg["engine"])
        engine_head, _sep, model_part = engine_spec.partition(":")
        overrides["mt_engine"] = engine_head if engine_head else engine_spec
        if model_part:
            overrides["mt_model"] = model_part
    if tr_cfg.get("model") and "mt_model" not in overrides:
        overrides["mt_model"] = tr_cfg["model"]
    src = tr_cfg.get("mt_source_lang", "auto")
    if isinstance(src, dict):
        src = _normalize_mt_source(src)
    if src and src != "auto":
        overrides["mt_source_lang"] = src
    # [experimental] → experimental provider toggles.
    if exp_cfg.get("subdivx"):
        overrides["experimental_subdivx"] = True
    if exp_cfg.get("addic7ed"):
        overrides["experimental_addic7ed"] = True

    if overrides:
        parser.set_defaults(**overrides)


def _apply_combine_config_defaults(parser: argparse.ArgumentParser) -> None:
    """Push [merge] / [modify] values into the merge parser as argparse
    defaults. (The internal function name stays as combine_* since the
    underlying implementation hasn't been renamed.)"""
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}

    overrides: dict[str, object] = {}
    mg = cfg.get("merge", {})
    if "languages" in mg:
        overrides["langs"] = mg["languages"]
    if "sync" in mg:
        overrides["sync"] = mg["sync"]
    if mg.get("preserve_lines"):
        overrides["preserve_lines"] = True
    if mg.get("watermark") is False:
        overrides["no_watermark"] = True
    out_cfg = cfg.get("output", {})
    if out_cfg.get("force"):
        overrides["force"] = True

    # Inline per-language readings into the merged cue stack when
    # [merge].reading is true. The SPEC comes from [modify].reading.
    if mg.get("reading", False):
        mod_cfg = cfg.get("modify", {})
        if mod_cfg.get("reading"):
            overrides["reading"] = mod_cfg["reading"]
    mod = cfg.get("modify", {})
    if mod.get("reading_format"):
        overrides["reading_format"] = mod["reading_format"]

    if overrides:
        parser.set_defaults(**overrides)


def _combine_master_from_config(langs: list[str]) -> str | None:
    """Apply [merge].priority: return the first priority lang that's also
    in `langs`, or None if no priority is set or no overlap."""
    try:
        cfg = load_user_config()
    except CliError:
        return None
    priority = cfg.get("merge", {}).get("priority", []) or []
    for p in priority:
        if p in langs:
            return p
    return None


def _combine_label_langs_from_config() -> bool:
    """user_settings.toml [merge].label_langs default for the merge
    subcommand (the CLI --label-langs flag still wins / ORs on top)."""
    try:
        cfg = load_user_config()
    except CliError:
        return False
    return bool(cfg.get("merge", {}).get("label_langs", False))


HELP_MAIN = """\
getsubtitle — Find and prepare subtitles for language learning.

Quick start:
  getsubtitle setup                              # first-time setup helper
  getsubtitle doctor                             # check install health
  getsubtitle -i                                  # interactive wizard (recommended for first run)
  getsubtitle URL                                 # download from a URL
  getsubtitle merge PATH -l ja,en                 # stack downloaded SRTs
  getsubtitle --config FILE.toml                  # run a saved workflow

Subcommands (each has its own --help):
  setup         First-time onboarding: keys, config, recommendations.
  doctor        Check install, keys, dependencies, ffmpeg, and Ollama.
  interactive   Guided wizard — builds workflows or safely renames subtitle files.
  fetch         Download from URL, or scan a folder. (Bare URL works too.)
  translate     Fill missing-language SRTs via MT (argos / ollama / deepl).
  modify        Cleanup, reading aids, SAMI→SRT, and MKV subtitle extraction.
  merge         Stack 2+ language SRTs into one study file.
  run           Save and run workflows by short name (run --save NAME FILE; run NAME).
  config        Manage user_settings.toml defaults.
  sources       Check provider/source access for your configured API keys.

Pipeline — chain verbs in one call:
  getsubtitle --fetch X --translate ollama --merge -l ja,en
  getsubtitle --source X --output Y --format vtt --config FILE.toml

Two example configs ship in this repo. Copy and tweak:
  simpsons-s1-en-fr.toml          URL → download an entire season
  plex-movies-fill-merge.toml     PATH → bulk fetch + MT + merge in-place

  getsubtitle --config simpsons-s1-en-fr.toml
  getsubtitle --config plex-movies-fill-merge.toml

Layered config (lowest → highest priority):
  built-in defaults  <  user_settings.toml  <  --config FILE.toml  <  CLI flags

Topic help:
  getsubtitle --help fetch | translate | modify | merge | pipeline
  getsubtitle --help setup | interactive | config | keys | reading | sources | advanced

New here? Try `getsubtitle setup` first, then `getsubtitle -i`.
"""


HELP_TOPICS: dict[str, str] = {
    "setup": """\
First-time setup and onboarding.

  getsubtitle setup

Setup asks a few plain-language questions:
  1. Languages you already understand
  2. Languages you are learning
  3. What you watch most: movie / TV shows / anime / mixed
  4. Where you watch: web browser / tablet-TV app / Plex / local player
  5. Machine translation preference: none / free offline / best online

Then it shows recommendations with rough cost and setup time, lets you
choose which ones to opt into, opens the provider pages in your browser,
saves API keys with the same secure key flow as `--set-key`, optionally
creates user_settings.toml, and finishes with Easy / Medium / Hard
commands to try.

Notes:
  - API keys are never written to TOML.
  - Streaming apps on tablets/TVs usually cannot import custom subtitle
    files. Setup will recommend browser + asbplayer, Plex, or a local
    player instead.
  - For asbplayer + Japanese pronunciation guides, use VTT and set:
    Settings > Misc > Subtitles > Subtitle HTML = Render.
""",
    "keys": """\
Manage API keys.

Usage:
  getsubtitle --set-key [PROVIDER]
  getsubtitle --reset-key [PROVIDER]

Providers:
  jimaku                   Japanese anime subtitles
  wyzie                    Movie and TV subtitles by IMDb/TMDB ID
  subdl                    Direct SubDL fallback by IMDb/TMDB ID
  deepl                    Machine translation with DeepL
  tmdb                     Movie/TV title → ID resolution (improves Wyzie
                           match rate when only a title is known)
  all                      Set or reset all supported providers

Examples:
  getsubtitle --set-key
  getsubtitle --set-key jimaku
  getsubtitle --set-key wyzie
  getsubtitle --set-key subdl
  getsubtitle --set-key tmdb
  getsubtitle --reset-key wyzie
  getsubtitle --reset-key -all     # remove all saved keys (uninstall-friendly)

Environment variables:
  JIMAKU_API_KEY
  WYZIE_API_KEY
  SUBDL_API_KEY
  DEEPL_API_KEY
  TMDB_API_KEY

Notes:
  macOS stores keys in Keychain.
  Linux and Windows use environment variables.
  TMDB key is optional — without it the rest of the pipeline still works,
  but title-only inputs won't auto-resolve to IMDb/TMDB IDs and Wyzie's
  match rate will be lower. Get a free key at:
  https://www.themoviedb.org/settings/api
""",
    "reading": """\
Reading aids — phonetic guides above/beside the original script.

Usage:
  --reading SPEC                     in any verb (URL, modify, merge)
  [modify].reading = "SPEC"               in user_settings.toml or --config TOML

SPEC is a comma list of LANG:MODE pairs:
  --reading ja:hiragana              Japanese furigana above kanji
  --reading ko:revised               Korean Revised Romanization
  --reading ja:hiragana,ko:revised   Both (multi-language learners)

Each language has a sensible default that `LANG:true` resolves to.
The pipe shorthand `|` expands to multiple modes:
  --reading "ja:hiragana|romaji"     hiragana AND romaji side files

`--no-reading` disables a configured default for one command.

──────────────────────────────────────────────────────────────────────
Japanese (ja) — ships today
──────────────────────────────────────────────────────────────────────
Install: `pip install -e ".[furigana]"` (or just `pip install pykakasi`)

Modes:
  ja:hiragana    Default. 漢字（かんじ） — hiragana above each kanji block.
  ja:katakana    漢字（カンジ） — katakana above each kanji block.
  ja:romaji      kyou wa nihongo wo renshuu shitai — full-sentence Hepburn romaji.

Examples:
  getsubtitle URL -l ja --reading ja:hiragana
  getsubtitle URL -l ja --reading ja:romaji
  getsubtitle merge PATH -l ja,en --reading ja:hiragana

MT-source notes:
  When a .ja.srt carries inline 漢字（かんじ） readings AND is used as an
  MT source, strip_reading_before_mt=true (default) strips the
  parentheticals before sending to the engine. Without this, an engine
  would translate the readings as extra content
  ("Specifically (especially) the legs (legs) ..."). The normal pipeline
  keeps furigana in side files only, so this is a defence for
  third-party or hand-edited Japanese sources.

──────────────────────────────────────────────────────────────────────
Korean (ko) — ships today
──────────────────────────────────────────────────────────────────────
Install: `pip install -e ".[romanization-ko]"`
  (pulls korean-romanizer + g2pk. Yale mode is in-tree; no install needed.)

Modes:
  ko:revised     Default. Revised Romanization with G2P preprocessing.
                 G2P handles pronunciation rules so the output reflects how
                 Hangul is actually spoken, not its surface spelling:
                   같이  → gachi    (palatalization, not gat-i)
                   읽는  → ingneun  (nasal assimilation)
                   한국어 → hangugeo (linking sounds)
  ko:yale        Yale Romanization. Orthographic — no G2P. Useful for
                 linguistic work and historical Korean. In-tree (no extras).

Without g2pk installed, ko:revised still runs but skips the G2P pass;
edge cases like 같이/읽는/한국어 will look orthographic rather than
phonetic. Yale mode is unaffected (orthographic by design).

Examples:
  getsubtitle URL -l ko --reading ko:revised
  getsubtitle modify PATH --reading ko:revised --reading-format vtt
  getsubtitle merge PATH -l ja,ko --reading ja:hiragana,ko:revised

──────────────────────────────────────────────────────────────────────
Mandarin Chinese (zh) — ships today
──────────────────────────────────────────────────────────────────────
Install: `pip install -e ".[romanization-zh]"` (or just `pip install pypinyin`)

Modes:
  zh:marks       Default. Pinyin with diacritical tone marks above vowels:
                   你好世界  →  nǐ hǎo shì jiè
                 The form most learners recognise from textbooks.
  zh:numbers     Pinyin with numbered tones (IME-friendly, plain ASCII):
                   你好世界  →  ni3 hao3 shi4 jie4
  zh:letters     Pinyin with no tones (most accessible):
                   你好世界  →  ni hao shi jie

pypinyin handles per-character lookup, polyphones (e.g. 长 in 长大
vs 长城), and built-in tone sandhi rules. Per-character output is
joined with spaces inside each hanzi run, so SRT inline parentheticals
read naturally:
  你好世界 → 你好世界（nǐ hǎo shì jiè）

Examples:
  getsubtitle URL -l zh --reading zh:marks
  getsubtitle modify PATH --reading zh:marks --reading-format vtt
  getsubtitle merge PATH -l zh,en --reading zh:numbers

──────────────────────────────────────────────────────────────────────
Cantonese — Jyutping
──────────────────────────────────────────────────────────────────────
  yue:numbers    Default. Cantonese jyutping with numbered tones:
                   廣東話  →  gwong2 dung1 waa2

Requires PyCantonese:
  python3 -m pip install pycantonese
  pip install -e ".[romanization-yue]"

──────────────────────────────────────────────────────────────────────
Thai / Arabic / Hindi / Russian — coming soon
──────────────────────────────────────────────────────────────────────
Wired through to CLI and TOML; backends land per the ROADMAP. The
wizard can save these choices in a workflow now so you can re-run when
the backend lands.

  th:royal-thai  Thai Royal-Thai transliteration
  ar:ala-lc      Arabic ALA-LC romanization
  hi:iast        Hindi IAST transliteration
  ru:iso-9       Russian ISO-9 transliteration

──────────────────────────────────────────────────────────────────────
Output formats (--reading-format)
──────────────────────────────────────────────────────────────────────
  srt    Default. Broadly compatible; inline parenthetical readings
         (漢字（かんじ） for ja, 한국어（hangugeo） for ko). One file per
         episode. Safest fallback.
  vtt    Ruby <ruby><rt> markup. Renders true furigana / inline reading
         aids in asbplayer when Settings > Misc > Subtitles >
         Subtitle HTML is set to Render.
  ass    Stacked-line layout (reading above original). Best local-player
         choice for Korean, Mandarin, and Cantonese reading aids.
  all    Generate all three. Same as srt,ass,vtt.

Examples:
  getsubtitle URL -l ja --reading ja:hiragana --reading-format vtt
  getsubtitle modify FOLDER --reading ja:hiragana --reading-format all
  getsubtitle modify FOLDER --reading ko:revised --reading-format srt,vtt

──────────────────────────────────────────────────────────────────────
Set defaults in user_settings.toml
──────────────────────────────────────────────────────────────────────
  [modify]
  reading = "ja:hiragana,ko:revised"
  reading_format = "srt"                # srt | ass | vtt | all

  [translate]
  strip_reading_before_mt = true       # strip ja readings before MT

Filenames:
  ja: <name>.ja.furigana-{hiragana|romaji}.{asb.srt|ruby.vtt|stacked.ass}
  ko: <name>.ko.romanization-{revised|yale}.{asb.srt|ruby.vtt|stacked.ass}

`--help romanization` and `--help furigana` are aliases for this page.
""",
    "translate": """\
Machine-translate missing subtitles.

Not sure which engine to pick? `getsubtitle -i` asks one question and
checks whether the engine you choose is actually available.

Two ways to use it:
  1. Inside a fetch, as a fallback:
       getsubtitle URL -l LANGS --engine ENGINE
     MTs any requested language that fetch couldn't find, sourcing from
     the just-downloaded files.

  2. Standalone on an existing folder (no URL, no re-fetch):
       getsubtitle translate PATH -l LANGS --engine ENGINE
     Scans PATH for *.srt files and MTs any requested language that's
     missing from each episode's set, sourcing from the best available
     local SRT.

Examples (inline with fetch):
  getsubtitle URL -l ja,en --engine ollama
  getsubtitle URL -l en,es --engine deepl
  getsubtitle URL -l ja --engine ollama --mt-source en

Examples (standalone translate subcommand):
  getsubtitle translate ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,en --engine argos
  getsubtitle translate FOLDER -s 1 -e 11 -l en --engine deepl
  getsubtitle translate FOLDER -l ja,en,es --engine deepl --dry-run
  getsubtitle translate FOLDER -s 1 -e 1-3 -l en --mt-source ja --engine ollama --force

Explicit source mapping (per-target):
  # Force en<-ja and es<-en regardless of what auto-pick would do.
  getsubtitle translate FOLDER -l ja,en,es --engine argos --mt-source en:ja,es:en
  # Try French first, then English if French is missing on disk.
  getsubtitle translate FOLDER -l fr,en,es --engine deepl --mt-source "es:fr|en"
  # Inside a fetch, same syntax:
  getsubtitle URL -l ja,en,es --engine deepl --mt-source en:ja,es:en

Engines:
  argos                    Offline translation. Requires argostranslate
  ollama                   Offline LLM translation. Requires Ollama running
                           in the background. Open the Ollama desktop app, or
                           use `brew services start ollama` on macOS/Homebrew.
                           `ollama serve` is a foreground fallback for a
                           separate terminal.
  deepl                    Online translation. Requires DEEPL_API_KEY
                           After a DeepL run, getsubtitle prints character
                           usage for the current billing period.

Translation options:
  -s, --season N|all       (translate subcommand) season filter
  -e, --episode N|N-M|all  (translate subcommand) episode filter
  --engine ENGINE          argos, ollama, or deepl. Default: argos
                           (via [translate].engine in user_settings.toml).
                           --mt-engine is still accepted as a compatibility alias.
  --no-mt-engine           Disable MT for this run even when the config
                           has an engine set. Equivalent to engine = "".
  --model NAME             Ollama model. Default: qwen3:4b
                           --mt-model is still accepted as an alias.
  --mt-model-pair PAIRS    Per-pair Ollama model override for one command:
                           ja:ko=qwen3:4b,en:es=llama3.2:3b
                           --model still wins over pair-specific values.
  --mt-source CODE         Force translation source language (default: auto)
                           Lists use |: es:fr|en means first available wins.
                           Quote values containing | in your shell.
                           --mt-source-lang is still accepted as an alias.
  -o DIR                   (translate subcommand) output directory
  --dry-run                (translate subcommand) show plan, write nothing
  --force                  (translate subcommand) overwrite existing .mt.srt

Notes:
  Output is saved as <name>.<lang>.mt.srt so it's easy to identify and
  exclude from sync. Auto source-picking prefers grammatically close pairs:
  ko<-ja, ja<-ko, es<-en, en<-anything.
  For Ollama, user_settings.toml can choose models per language pair:
    [translate.ollama_models]
    "ja:ko" = "qwen3:4b"
    "en:es" = "llama3.2:3b"
  These model keys are source:target and need quotes. Dash form like
  ja-ko also works without quotes.
  --model NAME overrides pair-specific config for one command.
""",
    "modify": """\
Post-process existing subtitle files on disk.

Hint: `getsubtitle -i` walks you through reading-aid choices (ja, ko,
zh, yue, th, ar, hi, ru) and the asbplayer preset in plain English.

Usage:
  getsubtitle modify PATH [PATH ...] [options]

The same cleanup operations that run after a download — but applied to
files you already have. Plus format conversion for legacy containers
like Microsoft SAMI (.smi). Pick any combination of flags; they run in
the same order the download flow uses.

Examples:
  getsubtitle modify FOLDER --strip-cc-noise
  getsubtitle modify FOLDER --single-line
  getsubtitle modify FOLDER --strip-cc-noise --single-line
  getsubtitle modify FOLDER --reading ja:hiragana          # Japanese furigana
  getsubtitle modify FOLDER --reading ja:romaji            # Japanese romaji
  getsubtitle modify FOLDER --reading "ja:hiragana|romaji" # both side files
  getsubtitle modify FOLDER -s 1 -e 3 --reading ko:revised # one episode only
  getsubtitle modify FOLDER --convert smi-to-srt
  getsubtitle modify FOLDER --convert ko:smi-to-srt        # Korean only
  getsubtitle modify FOLDER --convert ko,en:smi-to-srt     # Korean + English
  getsubtitle modify FOLDER --extract-mkv-subs             # embedded text subs
  getsubtitle modify FOLDER --convert smi-to-srt --force
  getsubtitle modify FOLDER --strip-cc-noise --single-line --reading ja:hiragana --dry-run

Operations (run in this order; pick at least one):
  --convert PAIR           Convert subtitle file format. Currently supports:
                             smi-to-srt — Microsoft SAMI .smi → one sibling
                             .<lang>.srt per language found inside the file.
                             SAMI Class attributes (KRCC, ENCC, JPCC, ...) map
                             to ko/en/ja/etc.; unknown classes default to ko.
                             Encoding is auto-detected (UTF-8/UTF-16/CP949).
  --strip-cc-noise         Remove broadcast CC noise (➡ arrows, 《...》 wrappers)
                           in place. Idempotent.
  --extract-mkv-subs       Extract embedded text subtitles from MKV/video
                           files with local ffprobe + ffmpeg. Image subtitle
                           streams such as PGS are reported and skipped.
  --single-line, --single  Flatten each cue to one text line in place.
                           Idempotent. Useful for asbplayer.
  --reading SPEC      Generate per-language reading aids. SPEC is a
                           comma list of LANG:MODE pairs.
                             ja:hiragana, ja:katakana, ja:romaji   (Japanese — ships)
                             ko:true | ko:revised | ko:yale        (Korean — ships)
                             zh:true | zh:marks | zh:numbers       (pinyin — ships)
                             yue:true | yue:numbers                (jyutping — ships)
                             ja:hiragana|romaji                    (both side files)
                           "true" picks the language's sensible default.
                           Japanese, Korean, Mandarin Chinese, and
                           Cantonese ship now; other languages land as backends
                           arrive (see ROADMAP).
  --no-reading             Disable reading-aid generation for this run.
  --format CODES           Which reading-aid side files to generate. Comma
                           list of srt, ass, vtt, or 'all'. Default: srt.
                           (Also accepts --reading-format.)

Other:
  -s, --season RANGE       When PATH is a folder, only process matching
                           season(s), e.g. -s 1 or -s 1-2.
  -e, --episode RANGE      When PATH is a folder, only process matching
                           episode(s), e.g. -e 3 or -e 3-5.
  --force                  With --convert: overwrite existing sibling .srt files.
                           Without --force, conversion skips targets that
                           already exist (protects human-quality .ko.srt etc.).
  --dry-run                Show what would change; write nothing.

Composes with the other subcommands:
  getsubtitle modify    FOLDER --convert smi-to-srt
  getsubtitle translate FOLDER -l ja,en --engine argos
  getsubtitle modify    FOLDER --strip-cc-noise --single-line --reading ja:hiragana
  getsubtitle merge     FOLDER -l ja,en
""",
    "config": """\
User settings (non-secret defaults).

Easier first run: `getsubtitle -i` builds a workflow and offers to save
it. The resulting TOML uses the same schema as user_settings.toml.

Usage:
  getsubtitle config --path        Print the config file path
  getsubtitle config --init        Create the file from the example template
  getsubtitle config --init --force   ...overwrite if it already exists
  getsubtitle config --open        Open the file in your default editor
  getsubtitle config --show        Print the effective non-secret config

File location:
  macOS/Linux: ~/.config/getsubtitle/user_settings.toml
  Windows:     %APPDATA%\\getsubtitle\\user_settings.toml

Precedence (lowest → highest):
  built-in defaults  <  user_settings.toml  <  --config FILE.toml  <  CLI flags

Sections — same names as the pipeline (--config) TOML so blocks
copy-paste between this file and any workflow config. In execution order:

  [fetch]         languages, release_source, manual_search, manual_search_open
  [translate]     engine, model, mt_source, strip_reading_before_mt
                  [translate.ollama_models] — per-pair model overrides +
                                              auto_load / auto_unload flags
  [modify]        single_line, strip_cc_noise, reading, reading_format
  [merge]         languages, sync, preserve_lines, priority, reading
  [output]        target, layout, open_folder, force, debug_providers
  [experimental]  subdivx, addic7ed

Notes:
  API keys are NEVER read from this file — keep them in macOS Keychain or
  environment variables (JIMAKU_API_KEY, WYZIE_API_KEY, SUBDL_API_KEY,
  DEEPL_API_KEY, TMDB_API_KEY).
  Run `getsubtitle config --show` to see what's currently active.
""",
    "sources": """\
Check subtitle provider/source access.

Usage:
  getsubtitle sources --check
  getsubtitle sources --check --provider wyzie

This is mainly for debugging provider coverage. Wyzie access can vary by
API key/tier, so this command asks Wyzie which internal sources your key
can currently use. If your Wyzie key does not expose SubDL, configure the
separate direct fallback with `getsubtitle --set-key subdl`.

Notes:
  - Requires a Wyzie key: getsubtitle --set-key wyzie
  - Direct SubDL fallback is separate: getsubtitle --set-key subdl
  - Does not download subtitles.
  - Source names and statuses are reported as Wyzie returns them.
""",
    "doctor": """\
Check install health.

Usage:
  getsubtitle doctor
  getsubtitle doctor --verbose

Checks:
  - Python version and executable
  - Config and default output locations
  - Optional reading-aid dependencies:
      pykakasi, korean-romanizer, g2pk, pypinyin, pycantonese
  - Optional local tools:
      ffmpeg / ffprobe for MKV embedded subtitle extraction
      Ollama daemon for offline LLM translation
  - Provider API keys:
      Jimaku, Wyzie, SubDL, DeepL, TMDB

It does not download subtitles or contact subtitle providers. Use
`getsubtitle sources --check` for provider-source diagnostics.
""",
    "run": """\
Save and run workflows by short name.

A named pipeline registry lives beside user_settings.toml. Save any
workflow TOML under a short name, then run it without typing the path.

Usage:
  getsubtitle run --save NAME path/to/workflow.toml   # register it
  getsubtitle run NAME                                 # run it
  getsubtitle run NAME --source URL --output DIR       # run with overrides
  getsubtitle run --list                               # list saved names
  getsubtitle run --remove NAME                         # delete one
  getsubtitle run --help                                # this page

Notes:
  - NAME must be letters / numbers / dashes — no slashes, no leading
    dot or dash (those collide with run's own flags).
  - Overrides after NAME are the same top-level flags --config accepts
    (--source, --output, --format, --season, --episode, -l, --dry-run,
    --force). CLI flags win over the saved file.
  - The TOML is copied into the registry, so editing the original later
    does not change the saved pipeline. Re-save to update it.
""",
    "fetch": """\
Fetch subtitles for a URL or for folder(s) on disk.

Not sure what flags you need? `getsubtitle -i` walks you through it.

Usage:
  getsubtitle URL [options]                              (URL form, no subcommand)
  getsubtitle fetch URL [options]                        (URL form, explicit verb)
  getsubtitle fetch PATH [--profile ja|ko|en] [--run]
  getsubtitle fetch PATH --subdirectory [--profile ...] [--run]

With a URL, fetch resolves IDs from the URL and downloads matching
subtitles from providers (Jimaku for anime; Wyzie for movies/TV).

With a PATH, fetch treats the folder as one show: derives the title
from the folder name, auto-detects the show's origin language via
TMDB (or character-set heuristic when no TMDB key), and runs the
right per-profile fetch chain. Add --subdirectory to walk one level
of subdirs and treat each as its own show — the whole-library mode.

`fetch` is download-only. To fill in missing languages via MT, modify
the cleanup pass, or stack a merge afterward, use the pipeline form
(see `getsubtitle --help pipeline`):
  getsubtitle --fetch /Plex/Anime --subdirectory \\
              --translate ollama \\
              --merge -l ja,en --format vtt

Supported URL types:
  Streaming:  Crunchyroll, Netflix, Hulu, Max (HBO), Disney+,
              Apple TV+, Paramount+, Peacock, Prime Video
  Catalog:    IMDb, TMDB, AniList, MyAnimeList, TheTVDB,
              Letterboxd, Rotten Tomatoes, Trakt

For Crunchyroll and Netflix we extract IDs directly. For the other
streaming services we pull the title from the URL slug and (where
available) `og:title` from the page, then resolve IDs via TMDB —
configure a key once with `getsubtitle --set-key tmdb`.

Profiles (auto-detected on PATH form; override with --profile):
  ja  Japanese-origin. fetch ko first; MT ja→ko fallback.
  ko  Korean-origin. fetch ja first; MT ko→ja fallback.
  en  English / Western / other. fetch es+ko first; MT from en
      for whichever target came back empty.

Profile detection chain:
  1. --profile flag (applies to every folder).
  2. Japanese kana in the folder name → ja (fast path; never wrong).
  3. TMDB search by folder name → original_language → ja/ko/en.
     Recommended setup: getsubtitle --set-key tmdb
  4. Character-set fallback: Hangul-only → ko; otherwise → en.

Examples (URL form):
  getsubtitle "https://www.crunchyroll.com/watch/..." -l ja
  getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ko,en,es
  getsubtitle "https://www.hulu.com/series/the-bear-12345" -s 1 -e all -l es,ko
  getsubtitle URL -s 1 -e 7 -l ja,ko --dry-run
  getsubtitle URL --title "MF Ghost" --anilist 143327 -l ja

Examples (PATH single-show form):
  getsubtitle fetch ~/Downloads/GetSubtitle/MF\\ Ghost --run
  getsubtitle fetch "~/Downloads/유포니움/1기" --profile ja --run

Examples (PATH library-walk form):
  getsubtitle fetch ~/Downloads/GetSubtitle --subdirectory          # dry-run
  getsubtitle fetch ~/Downloads/GetSubtitle --subdirectory --run    # do it

Episode-range expansion (`-e all`):
  - Anime: episode count comes from AniList (no extra setup).
  - Live-action TV: episode count comes from TMDB. Needs a TMDB API
    key; set one with `getsubtitle --set-key tmdb` or
    `TMDB_API_KEY=...`. Without it, pass an explicit range like
    `-e 1-12`.

URL-inferred fields (auto-defaults):
  - Crunchyroll URLs with trailing `...-season-2` (etc.) default to
    -s 2 unless you pass an explicit -s.
  - The same applies to inferred -e values from URLs that include
    `/episode-N/` or similar markers.
  - User-supplied -s/-e always wins.

Folder layout handling (PATH form):
  Show/Season 01/      → show=Show, season=1
  Show/1기/           → show=Show, season=1 (Korean form)
  Show/                → show=Show, season=None (single-folder shows)
  loose-movie.mkv      → treated as a movie, fetched into the same dir

Fetch options:
  -l, --langs CODES        Languages to download. Default: ja
  -s, --season N|all       Season number. If omitted, infer when possible
  -e, --episode N|N-M|all  Episode, range, list, or all
  --episode-filename-start N
                           Shift output filenames only. Example: search
                           Season 3 episodes 1-12 but save as S03E25-S03E36
                           when the streaming page labels the season E25 onward.
  -o, --output DIR         Output folder. Default: ~/Downloads/GetSubtitle
  --layout MODE            archive, flat, or plex. Default: archive
  --title TEXT             Title override when URL metadata is missing
  --anilist ID             AniList ID override for anime
  --browser                Open URL first for login/Cloudflare pages
  --manual-search MODE     off | on-missing | always. Default: on-missing.
                           When Japanese/Korean/Chinese subtitles are missing
                           after normal providers, print likely community searches.
  --manual-search-open MODE
                           ask | always | never. Default: ask. Opens multiple
                           browser tabs for the manual-search links.
  --release-source MODE    auto | any | netflix | crunchyroll | amazon |
                           hulu | hbo | disney | apple | paramount |
                           peacock. Default: auto = infer from the URL's
                           host (HBO/Hulu/etc. → prefer matching rips).
  --dry-run                Search and show availability without downloading
  -y, --yes                Skip bulk confirmation
  --open-folder            Open output folder after saving

Notes:
  - PATH form defaults to dry-run. Add --run to actually fetch.
  - URL form does NOT default to dry-run — it's opt-in via --dry-run.
""",
    "merge": """\
Merge multiple language subtitle files into one study-friendly cue stack.

Quick way to figure out display order + master language: `getsubtitle -i`.

Usage:
  getsubtitle merge PATH -l LANGS [merge options]
  getsubtitle merge PATH --subdirectory [-l LANGS] [merge options]

Without --subdirectory, PATH is one show: scan it recursively for
single-language SRT/VTT/ASS/SSA/SMI inputs, group by season/episode, write the combined
.<lang1>-<lang2>.srt files alongside.

With --subdirectory, treat each immediate subdir of PATH as its own
show and run merge once per subdir. Useful for whole-library passes
after `fetch --subdirectory` has populated the per-show SRTs.

Behavior:
  The language order in -l controls display order.
  Example: -l ja,en puts Japanese above English.
  Each language is flattened to one line by default:
    Japanese line 1 Japanese line 2
    English line 1 English line 2

Examples:
  getsubtitle merge ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,en
  getsubtitle merge ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,en --master ja --reading ja:hiragana
  getsubtitle merge ~/Downloads/GetSubtitle --subdirectory -l ja,en --format vtt
  # Multi-variant: stack original + reading-aid variant(s) in one file.
  getsubtitle merge ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,ja-hiragana,en
  getsubtitle merge ~/Downloads/GetSubtitle/MF\\ Ghost -l ja,ja-hiragana,ja-romaji,en
  getsubtitle merge ~/Downloads/GetSubtitle -l ko,ko-revised,en
  getsubtitle merge ~/Downloads/GetSubtitle -l zh,zh-marks,en
  getsubtitle merge ~/Downloads/GetSubtitle -l yue,yue-numbers,en

Merge options:
  -l, --langs CODES        Required. Language order for output
  -o, --output DIR         Output folder. Default: beside master subtitle
  --dry-run                Show merge plan without writing files
  --force                  Overwrite existing outputs and allow low-confidence matches
  --open-folder            Open output folder after writing
  --no-open-folder-prompt  Do not ask whether to open output folder
  --no-watermark           Skip GetSubtitle credit/disclaimer cues
  --format FORMAT          srt, vtt, smi, ass, or txt. VTT is best for
                           asbplayer/browser ruby; ASS is best for local
                           stacked reading aids.
  --sync MODE              auto, strict, or loose. Default: auto
  --master LANG            Timing master. Default: first language in -l
  --label-langs            Prefix each language's line with [JA]/[KO]/… so
                           stacked tracks are easy to tell apart. Also
                           [merge] label_langs = true in user_settings.toml.
  --single-line, --single  Flatten each language to one line. Default behavior
  --preserve-lines         Keep original line breaks within each language
  --reading SPEC      Inline reading aids on the matching language line
                           (e.g. `ja:hiragana` inlines 漢字（かんじ） onto ja cues).
                           See `getsubtitle --help modify` for the full SPEC syntax.
  --subdirectory           Walk immediate subdirs and run merge per show

Notes:
  - First language in -l is the timing master unless --master is set.
  - Input formats: srt, vtt, ass/ssa, smi. Use -l ja:vtt,en,ko:smi when
    multiple formats exist for the same language.
  - --reading ja:hiragana inlines Japanese readings before merging.
  - Merged outputs include a short GetSubtitle credit/disclaimer cue at the
    beginning and end. Use --no-watermark to omit it.
  - --sync auto|strict|loose controls how strictly cues match.

Multi-variant merge:
  Pseudo-lang codes resolve to reading-aid side files generated by
  `modify --reading {lang}:{mode}`. Recognised codes:
    ja-hiragana, ja-katakana, ja-romaji
    ko-revised, ko-yale
    zh-marks, zh-numbers, zh-letters
    yue-numbers (ships via romanization-yue / pycantonese)
  Output filename collapses adjacent same-base tokens:
    -l ja,ja-hiragana,ja-romaji,en  ->  Show.ja-hiragana-romaji-en.srt
  Default master prefers the base language when both base and variant
  are requested. Variants share cue timing with their base.
""",
    "pipeline": """\
Chain fetch / translate / modify / merge into one call.

`getsubtitle -i` builds a pipeline for you and offers to save it as a
TOML you can re-run with `--config FILE.toml`.

Usage (inline form):
  getsubtitle [shared options] \\
      [--fetch TARGET [fetch-only options]] \\
      [--translate ENGINE [translate-only options]] \\
      [--modify [modify-only options]] \\
      [--merge [merge-only options]] \\
      [--output PATH] [--dry-run]

Usage (config-file form, with optional inline CLI overrides):
  getsubtitle [--source X] [--output Y] [--format vtt] [other overrides] --config FILE.toml

The `--config` flag can appear anywhere in argv; we recommend at the end
for readability. CLI flags override matching TOML values. Layer order:
  built-in defaults  <  user_settings.toml  <  --config FILE.toml  <  CLI flags

Top-level CLI overrides (layered onto the --config TOML):
  --source X        overrides [fetch].source
  --output X        overrides [output].target
  --format X        overrides [output].format
  --season X        overrides [fetch].season
  --episode X       overrides [fetch].episode
  --episode-filename-start X
                    overrides [fetch].episode_filename_start
  -l X, --languages X  overrides [fetch].languages
  --subdirectory    overrides [fetch].subdirectory = true
  --dry-run         overrides [output].dry_run = true
  --force           overrides [output].force = true

Inline verb blocks (--fetch / --translate / --modify / --merge) layer on
top of the TOML per-section: keys you set inline win on collision; keys
not set inline come from the TOML.

Verbs always run in canonical order regardless of typing order:
  fetch → translate → modify → merge

Each verb's flag block is parsed by that verb's existing argument
surface, so per-verb options work exactly like the standalone subcommands.
The verb's block starts at the verb flag and ends at the next verb flag
or end-of-argv. Shared options (--output, --dry-run) appear once,
before any verb flag.

Shared options:
  --output PATH   Working folder for downstream verbs. Required when
                  --fetch is a URL and --translate / --modify / --merge
                  are present. Otherwise defaults to --fetch's PATH.
  --dry-run       Propagated to every verb that supports it.

Translate engine spec (positional after --translate):
  --translate argos               Offline. Requires argostranslate.
  --translate ollama              Offline LLM. Uses default model.
  --translate ollama:qwen3:8b     Pin a specific Ollama model.
  --translate deepl               Online. Requires DEEPL_API_KEY.
  --translate ""                  Disable MT for this run.

Examples (inline):
  # Whole-library bilingual pass: fetch each show, MT missing langs,
  # clean broadcast noise, then merge into ja+en study files.
  getsubtitle --fetch /Plex/Anime --subdirectory \\
              --translate ollama \\
              --modify --strip-cc-noise --single-line \\
              --merge -l ja,en --format vtt

  # URL → study deck via DeepL into an explicit output folder.
  getsubtitle --fetch "https://www.imdb.com/title/tt28299608/" -s 1 -e all \\
              --translate deepl \\
              --merge -l ja,en --format vtt \\
              --output ~/Downloads/GetSubtitle/StudyDeck

  # Just fetch + merge (no MT), single show.
  getsubtitle --fetch ~/Downloads/GetSubtitle/MF\\ Ghost \\
              --merge -l ja,en

Examples (config file with CLI overrides):
  getsubtitle --config simpsons-s1-en-fr.toml
  getsubtitle --config plex-movies-fill-merge.toml
  getsubtitle --source /Plex/Anime --format vtt --config plex-movies-fill-merge.toml
  getsubtitle --season 2 --config simpsons-s1-en-fr.toml

Pipeline TOML schema (sections in execution order):

  [fetch]
  source = "/Plex/Anime"           # required: URL or PATH
  subdirectory = true              # walk immediate subdirs (PATH only)
  season = "1-2"                   # range OK; also `seasons = ...`
  episode = "all"                  # also `episodes = ...`
  episode_filename_start = "25"    # optional: search E1 but save as E25
  languages = "japanese,english,korean"
                                   # full names normalize to ja,en,ko;
                                   # alias keys: `langs`, `language`
  manual_search = "on-missing"     # off | on-missing | always
  manual_search_open = "ask"       # ask | always | never

  [translate]
  engine = "ollama"                # required: argos | ollama[:model] | deepl
  mt_source = { ko = "ja", es = ["fr", "en"], ja = "ko" }
                                   # per-target source map; lists try first available
                                   # comma-string `mt_source = "ko:ja,es:fr|en"` also works
                                   # (`mt_source_lang` kept as alias)
  "ja:ko" = "qwen3:4b"             # per-pair Ollama models (session-only;
  "en:es" = "llama3.2:3b"          # don't touch user_settings.toml)

  [modify]
  strip_cc_noise = true
  single_line = true
  reading = "ja:hiragana"          # e.g. ja:hiragana, ko:revised, zh:marks
  reading_format = "all"           # srt | ass | vtt | all
                                   # aliases: furigana_output_format, format
  convert = "smi-to-srt"           # or "none"

  [merge]
  languages = "ja:vtt, en, ko:smi" # `:format` is an INPUT hint when multiple
                                   # source formats exist on disk for one lang
                                   # (supports :srt, :vtt, :ass, :ssa, :smi)
  master = "ja"
  sync = "strict"                  # auto | strict | loose
  reading = "ja:hiragana"          # inline readings into the matching line
  format = "vtt"                   # final stacked output format

  [output]
  target = "/Plex/Output"          # final output folder (alias: `root`)
  layout = "plex"                  # archive | flat | plex (Plex preserves Show/Season XX)
  retain_folder_structure = true   # alias for layout = "plex" (hyphen form also accepted)
  format = "vtt"                   # global default; per-verb format wins when set
  dry_run = false                  # false (default) → live run; auto-adds
                                   # --run to PATH-form fetch
  force = false                    # propagates to translate / modify / merge
  yes = false                      # propagates to fetch (skip bulk confirmation)
  debug_providers = false          # propagates to fetch

Naming conventions:
  - CLI uses kebab-case (--mt-source, --reading-format, --strip-cc-noise).
    TOML uses snake_case (mt_source, reading_format, strip_cc_noise).
    Either spelling works in TOML — hyphens normalize to underscores so
    `dry-run` and `dry_run` are interchangeable.
  - Canonical TOML keys (pre-1.0):
      [translate]  mt_source           (was: mt_source_lang)
      [modify]     reading_format      (was: furigana_output_format)
      [output]     target              (was: root)
      [fetch]      source              (was: target/url)
      (anywhere)   languages           (was: langs)
    The old names remain as silent aliases.
  - Other aliases: `language`/`langs` for `languages`,
    `seasons`/`episodes` for `season`/`episode`,
    `format`/`furigana_format`/`furigana_output_format` for `reading_format`.
  - Language values accept ISO codes (ja, en, ko, es, fr, zh, de, it, pt, ru)
    OR full names (japanese, english, korean, spanish, french, chinese, …)
  - Boolean true → flag emitted, false → flag omitted
""",
    "interactive": """\
Interactive workflow builder.

  getsubtitle -i
  getsubtitle --interactive
  getsubtitle interactive

Walks through a guided Q&A and shows the equivalent terminal command
plus a saveable workflow file before letting you pick a final action.

You answer each menu by NUMBER (1/2/3…); only free-text fields take typed
text (languages, paths, URL, title, season/episode). Headings are numbered
contiguously from what you picked, so a subset run has no gaps.
Type 'b' at any prompt to return to the previous visible step.

What it asks (only the questions relevant to your step choice appear):
  • Which steps to run — fetch / translate / modify / merge / rename.
      Default: 1-4 — fetch, translate, modify, then merge.
      The translation question still defaults to "Skip", so pressing Enter
      through setup does not silently start AI translation.
      Common picks:
        '1-4'   → full subtitle workflow
        '1,3,4' → download + modify + merge existing subtitles
        '5'     → rename titles, prefixes, or numbering
      Rename is a separate maintenance workflow; choosing it with other
      steps runs rename only so files are not fetched/modified by accident.
  • Source kind — title search / streaming URL / folder or file.
      (default flips to 'folder' when no TMDB key is configured, so
       first-time users land on the most reliable path. Skipped when
       fetch isn't selected — the source is the local path you drop in.)
  • The actual title / URL / path.
      (title search picks among TMDB + AniList candidates, with 'r' to
       re-enter a different title. Path input strips wrapping single/
       double quotes — Finder / GNOME Files / Konsole drag-drop works.)
  • Episode scope (URL/title, TV only): movie / season+episode / all /
      auto. Skipped for movies (TMDB /movie/, AniList format=MOVIE,
      single-episode SPECIAL/OVA/ONA) and when the source filename
      already encodes SxxExx.
  • Languages to collect (comma list: ja,en,ko,es,…).
  • AI translation engine: skip / argos / ollama / deepl. Only when
      translate is selected.
  • Reading aids — phonetic guides for the original script. Option 1 is
      'No reading aid (skip)' and the default; aids start at 2 and are
      filtered to the languages you're collecting:
        ja:hiragana / ja:katakana / ja:romaji           ships now
        ko:revised / ko:yale                            ships now
        zh:marks / zh:numbers / zh:letters              ships now
        yue:numbers (jyutping)                          ships now
        th:royal-thai / ar:ala-lc / etc.                backend coming
      The header example adapts to your primary script
      (漢字（かんじ） for ja, 한글 (hangeul) for ko, 漢字 (pīnyīn) for zh).
  • Rename mode — groups matching subtitle filenames by variation
      (for example `Title - S03E**.ja.srt`), lets you choose one group
      or all groups, previews every old → new filename, checks for
      collisions, then asks whether to rename originals or create
      renamed copies. Copy-and-apply is the default. You can keep the
      previewed change and change another filename field before applying;
      each field can be handled only once per rename batch.

Auto-filled for you (shown in a "Smart defaults filled in for you" banner,
revisable via Edit — these are NOT asked as questions):
  • Display order — the order you typed the languages (top → bottom).
  • Timing master — the first language.
  • Cleanup preset — single-line cues + strip broadcast noise (on).
      Works in any player (VLC, mpv, IINA, Infuse, asbplayer, Plex web).
  • Output format — VTT when a ja:hiragana/furigana ruby aid is picked,
      else SRT (most compatible).
  • Output folder — ~/Downloads/GetSubtitle for URL/title sources;
      beside the source for local paths.

Final action menu (answer by number):
  1) Run it now      — dispatches immediately. Default for local sources;
                       URL/title sources default to 2 since fetches can
                       be slow. Offers to open the output folder when
                       finished.
  2) Save as a workflow file
                     — writes a self-contained .toml. Re-prompts on
                       overwrite collisions. Run later via
                       `getsubtitle --config FILE.toml`.
  3) Edit an answer  — list current answers, jump to one question.
  4) Start over      — confirms 'discard all answers?' before clearing.
  5) Quit

Before the action menu the wizard prints both the terminal command AND
the equivalent workflow file (in TOML, saveable as .toml) so you can
sanity-check. If a reading aid wants VTT ruby but the format is set to
something else, a one-line warning surfaces here.
Rename mode finishes immediately after the confirmed rename preview;
it does not generate a TOML workflow because it is file maintenance,
not a reusable fetch/modify/merge recipe. By default it creates renamed
copies and keeps your original files; choose "Rename the original files"
only when you are ready to move/rename in place. The preview menu first
asks "What next?" so you can keep/discard a pending change or apply now;
the apply menu then asks copy vs original-file rename.

When you pick **Run**, the wizard probes your environment for missing
pieces — the pykakasi package for Japanese furigana, korean-romanizer +
g2pk for Korean, pypinyin for Mandarin, pycantonese for Cantonese,
the Ollama daemon if you picked
ollama, the DeepL key if you picked DeepL, missing Jimaku/Wyzie/TMDB
keys — and walks you through fixing each gap before dispatching. Deferred
reading aids (th/ar/hi/ru) are stripped before Run so the modify
step doesn't crash; Save keeps them so the workflow re-runs once the
backend ships. **Save** skips the probe entirely so you can build
workflow files on one machine for use on another.

Limitations:
  - Requires an attached terminal (fails cleanly otherwise).
  - One language alone skips display order / master and the merge step.
  - Thai / Arabic / Hindi / Russian reading-aid backends
    are not yet shipped; the wizard accepts and saves them so you can
    re-run once the backend lands.

Tips:
  - Type 'b' or 'back' at any prompt to revisit the
    previous visible step.
  - Press 'q' at any prompt to quit; answers are auto-saved to
    ~/.cache/getsubtitle/wizard-draft.toml so you can resume later.
  - Movie filenames are flattened to <Title>/<Title>.<lang>.srt
    (no Season Unknown / S00E00 placeholders).
  - The wizard generates the canonical names everywhere
    (--languages, --engine, --mt-source, --reading, --reading-format
    on the CLI; mt_source / reading / reading_format in TOML).
""",
    "advanced": """\
Advanced and experimental options.

Troubleshooting:
  --debug-providers        Show raw provider counts and language tags
  --browser                Open URL first for login/Cloudflare pages

Provider selection:
  --release-source MODE    auto | any | netflix | crunchyroll | amazon |
                           hulu | hbo | disney | apple | paramount | peacock
                            auto = infer from the URL host (works for all
                                   the listed services)
                            any  = disable source preference
                            Or pin an explicit source name to bias toward
                            releases tagged accordingly (HULU, DSNP, ATVP, ...)

Experimental providers:
  --experimental-subdivx   Enable Spanish Subdivx fallback
  --experimental-addic7ed  Enable Korean Addic7ed fallback; may rate-limit

Output / cleanup:
  --layout MODE            archive, flat, plex
  --strip-cc-noise         Remove broadcast closed-caption noise (➡, 《...》)
  --single-line            Flatten SRT cues to one line

Compatibility aliases (still accepted):
  -single, --single        Same as --single-line
  -release-source          Same as --release-source
  --strip-cc-arrows        Same as --strip-cc-noise
  --strip-arrows           Same as --strip-cc-noise
""",
}


def _is_topic_help_request(argv: list[str]) -> bool:
    """Return True when argv should bypass argparse and show a topic page."""
    if not argv:
        return False
    if argv[0] in ("-h", "--help"):
        return True
    if argv[0] == "translate":
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
        if len(argv) == 1:
            # Same friendly treatment for `getsubtitle translate` alone.
            return True
    if argv[0] == "modify":
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
        if len(argv) == 1:
            return True
    if argv[0] in ("merge", "fetch", "sources", "setup", "doctor"):
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
        if len(argv) == 1:
            return True
    if argv[0] == "config":
        # `getsubtitle config --help` / `-h` routes to the config topic page.
        # `getsubtitle config` alone is handled by config_main (prints
        # config-parser help) so it doesn't fire here.
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
    return False


def _show_topic_help(argv: list[str]) -> int:
    if argv and argv[0] == "translate":
        sys.stdout.write(HELP_TOPICS["translate"])
        return 0
    if argv and argv[0] == "modify":
        sys.stdout.write(HELP_TOPICS["modify"])
        return 0
    if argv and argv[0] == "merge":
        sys.stdout.write(HELP_TOPICS["merge"])
        return 0
    if argv and argv[0] == "fetch":
        sys.stdout.write(HELP_TOPICS["fetch"])
        return 0
    if argv and argv[0] in ("--config", "pipeline"):
        sys.stdout.write(HELP_TOPICS["pipeline"])
        return 0
    if argv and argv[0] == "config":
        sys.stdout.write(HELP_TOPICS["config"])
        return 0
    if argv and argv[0] == "sources":
        sys.stdout.write(HELP_TOPICS["sources"])
        return 0
    if argv and argv[0] == "setup":
        sys.stdout.write(HELP_TOPICS["setup"])
        return 0
    if argv and argv[0] == "doctor":
        sys.stdout.write(HELP_TOPICS["doctor"])
        return 0
    # `--help TOPIC` form: topic is the next non-flag arg.
    topic: str | None = None
    if len(argv) > 1 and not argv[1].startswith("-"):
        topic = argv[1].lower()
    if topic is None:
        sys.stdout.write(HELP_MAIN)
        return 0
    if topic in HELP_TOPICS:
        sys.stdout.write(HELP_TOPICS[topic])
        return 0
    sys.stderr.write(
        f"Unknown help topic: {topic!r}. "
        f"Available: {', '.join(HELP_TOPICS)}.\n"
    )
    return 2


# ═══════════════════════════════════════════════════════════════════════
# Doctor
# ═══════════════════════════════════════════════════════════════════════

def _doctor_row(label: str, ok: bool | None, detail: str) -> str:
    mark = "OK" if ok is True else "WARN" if ok is None else "MISS"
    return f"  {mark:4} {label}: {detail}"


def doctor_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="getsubtitle doctor",
        description="Check install health, optional dependencies, API keys, and local tools.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show extra paths and environment details.")
    args = parser.parse_args(argv)

    rows: list[str] = []
    py_ok = sys.version_info >= (3, 10)
    rows.append(_doctor_row("Python", py_ok, platform.python_version()))
    rows.append(_doctor_row("Executable", True, sys.executable))
    rows.append(_doctor_row("Config", True, str(config_path())))
    rows.append(_doctor_row("Output folder", True, str(DEFAULT_OUTPUT)))

    optional_modules = [
        ("pykakasi", "Japanese furigana", 'pip install -e ".[furigana]"'),
        ("korean_romanizer", "Korean Revised Romanization", 'pip install -e ".[romanization-ko]"'),
        ("g2pk", "Korean G2P quality boost", 'pip install -e ".[romanization-ko]"'),
        ("pypinyin", "Mandarin pinyin", 'pip install -e ".[romanization-zh]"'),
        ("pycantonese", "Cantonese Jyutping", 'pip install -e ".[romanization-yue]"'),
        ("argostranslate", "Argos offline translation", "pip install argostranslate"),
    ]
    for module_name, label, install_hint in optional_modules:
        ok = _setup_module_exists(module_name)
        detail = "installed" if ok else f"not installed; {install_hint}"
        rows.append(_doctor_row(label, ok, detail))

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    rows.append(_doctor_row("ffmpeg", bool(ffmpeg), ffmpeg or "not found; needed for MKV subtitle extraction"))
    rows.append(_doctor_row("ffprobe", bool(ffprobe), ffprobe or "not found; needed for MKV subtitle detection"))
    ollama_bin = shutil.which("ollama")
    ollama_ok = bool(ollama_bin and _wizard_ollama_reachable())
    if ollama_ok:
        ollama_detail = f"daemon reachable ({ollama_bin})"
    elif ollama_bin:
        ollama_detail = f"installed but daemon not reachable ({ollama_bin})"
    else:
        ollama_detail = "not found; only needed for --engine ollama"
    rows.append(_doctor_row("Ollama", True if ollama_ok else None, ollama_detail))

    for provider, meta in KEY_PROVIDERS.items():
        key = get_provider_api_key(provider, prompt_if_missing=False)
        env = meta["env"]
        if key:
            detail = f"configured ({env} or keychain)"
            ok = True
        else:
            detail = f"missing; run getsubtitle --set-key {provider}"
            ok = None
        rows.append(_doctor_row(meta["label"] + " key", ok, detail))

    print("getsubtitle doctor")
    print()
    for row in rows:
        print(row)
    print()
    print("Suggested next steps:")
    missing_keys = [p for p in KEY_PROVIDERS if not get_provider_api_key(p, prompt_if_missing=False)]
    if missing_keys:
        print("  - Add useful provider keys with `getsubtitle --set-key PROVIDER`.")
    if not ffmpeg or not ffprobe:
        print("  - Install ffmpeg to enable `getsubtitle modify PATH --extract-mkv-subs`.")
    if not _setup_module_exists("pycantonese"):
        print('  - Install Cantonese support with `pip install -e ".[romanization-yue]"`.')
    if args.verbose:
        print()
        print("Environment:")
        print(f"  Platform: {platform.platform()}")
        print(f"  PATH: {os.environ.get('PATH', '')}")
    return 0 if py_ok else 1


# ═══════════════════════════════════════════════════════════════════════
# Interactive wizard
# ═══════════════════════════════════════════════════════════════════════
# `getsubtitle --interactive` (or `getsubtitle interactive`, or `-i`) walks
# a new user through a workflow and produces a CLI command, a saved TOML,
# or a live run. Generated artifacts use the canonical names
# (--languages, --engine, --mt-source, --reading, --reading-format
# on the CLI; mt_source / reading_format in TOML).
#
# Romanization options exposed by the wizard cover every language in
# _READING_DEFAULTS — Japanese / Korean / Chinese / Cantonese ship now;
# Thai / Arabic / Hindi / Russian land per ROADMAP. The
# wizard accepts those choices and emits the same `--reading`
# spec the CLI/TOML already validate; the parser raises a clear
# "not yet implemented" error at run time for the deferred languages.

_WIZARD_DRAFT_FILENAME = "wizard-draft.toml"


# Per-language reading-aid menu. Each row: (lang_iso, spec_value, label,
# is_shipping). `spec_value` is what we splice into the --reading
# spec (e.g. "ja:hiragana"). `is_shipping` controls whether we warn.
_WIZARD_READING_AID_MENU: list[tuple[str, str, str, bool]] = [
    # Labels are format-agnostic — "ruby above" only applies to VTT; SRT/SMI/
    # ASS fall back to parenthetical 漢字（かんじ） form. The wording below
    # works for both.
    ("ja", "ja:hiragana",       "Japanese — hiragana readings for kanji",   True),
    ("ja", "ja:katakana",       "Japanese — katakana readings for kanji",   True),
    ("ja", "ja:romaji",         "Japanese — full-sentence romaji",          True),
    ("ko", "ko:revised",        "Korean — Revised Romanization (G2P)",      True),
    ("ko", "ko:yale",           "Korean — Yale Romanization",               True),
    ("zh", "zh:marks",          "Mandarin — pinyin with tone marks",        True),
    ("zh", "zh:numbers",        "Mandarin — pinyin with numbered tones",    True),
    ("yue", "yue:numbers",      "Cantonese — jyutping with numbered tones", True),
    ("th", "th:royal-thai",     "Thai — Royal Thai transliteration",        False),
    ("ar", "ar:ala-lc",         "Arabic — ALA-LC romanization",             False),
    ("hi", "hi:iast",           "Hindi — IAST transliteration",             False),
    ("ru", "ru:iso-9",          "Russian — ISO-9 transliteration",          False),
]


class _WizardAbort(Exception):
    """Raised when the user explicitly bails out (Ctrl-C / `q`)."""


class _WizardBack(Exception):
    """Raised when the user asks to return to the previous wizard step."""


_WIZARD_BACK_NAV_ACTIVE = False


def _wizard_back_nav_active() -> bool:
    return bool(globals().get("_WIZARD_BACK_NAV_ACTIVE", False))


def _wizard_has_recoverable_draft(state: "_WizardState") -> bool:
    """True when the wizard has enough information to resume usefully."""
    if not state.steps:
        return False
    if not state.source_kind:
        return False
    if state.source_kind in {"path", "url", "title"} and not state.source:
        return False
    return True


def _wizard_is_interactive() -> bool:
    """True iff both stdin and stdout are a terminal. The wizard cannot
    run in a pipeline because every question is a blocking prompt."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _wizard_prompt(
    question: str,
    default: str | None = None,
    *,
    choices: list[str] | None = None,
    allow_back: bool = True,
) -> str:
    """Read one answer. Empty input → default (if any). Trims whitespace.

    `choices` is informational — printed alongside the question; we do
    NOT enforce it here (callers validate, since some questions accept
    free-form input on top of suggestions)."""
    can_go_back = allow_back and _wizard_back_nav_active()
    suffix = ""
    if default is not None:
        back_hint = " | b=back | q=quit" if can_go_back else (" | q=quit" if _wizard_back_nav_active() else "")
        suffix = f" [{default}{back_hint}]"
    elif can_go_back:
        suffix = " [b=back | q=quit]"
    elif _wizard_back_nav_active():
        suffix = " [q=quit]"
    while True:
        try:
            raw = input(f"  {question}{suffix} > ").strip()
        except EOFError as e:
            raise _WizardAbort("stdin closed") from e
        if not raw and default is not None:
            return default
        low = raw.lower()
        if low in ("q", "quit", "exit"):
            raise _WizardAbort("user quit")
        if can_go_back and low in ("b", "back", "prev", "previous"):
            raise _WizardBack()
        if raw:
            return raw
        if can_go_back:
            print("    (empty answer; please enter something, 'b' to go back, or 'q' to quit)")
        else:
            print("    (empty answer; please enter something, or 'q' to quit)")


def _wizard_yesno(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    if _wizard_back_nav_active():
        suffix = suffix[:-1] + " | b=back | q=quit]"
    while True:
        try:
            ans = input(f"  {question} {suffix} > ").strip().lower()
        except EOFError as e:
            raise _WizardAbort("stdin closed") from e
        if ans in ("q", "quit", "exit"):
            raise _WizardAbort("user quit")
        if _wizard_back_nav_active() and ans in ("b", "back", "prev", "previous"):
            raise _WizardBack()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        # Treat the first character as a guess if the user typed Y/N alone.
        if ans and ans[0] in "yn":
            return ans[0] == "y"
        print(f"    (please answer y or n; Enter = {'yes' if default else 'no'})")


def _wizard_draft_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "getsubtitle" / _WIZARD_DRAFT_FILENAME


def _wizard_save_draft(state: "_WizardState") -> None:
    """Persist current answers so an interrupted wizard can resume.
    Best-effort — never fail the wizard over a cache-write hiccup."""
    try:
        path = _wizard_draft_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.to_toml(), encoding="utf-8")
    except OSError:
        pass


def _wizard_clear_draft() -> None:
    try:
        _wizard_draft_path().unlink()
    except (OSError, FileNotFoundError):
        pass


@dataclass
class _WizardState:
    """Bag of answers for the interactive wizard. Each field maps to a
    question and a single emitter rule, so the emitters stay declarative."""
    source: str = ""                       # Q1: URL or path
    source_title: str = ""                 # optional title resolved by Q1 picker
    source_kind: str = ""                  # "url" | "path" | "title"
    languages: list[str] = field(default_factory=list)        # Q2
    order: list[str] = field(default_factory=list)            # Q3
    master: str = ""                       # Q4: "" | lang code | "auto"
    season: str = ""                       # Q5
    episode: str = ""                      # Q5
    episode_filename_start: str = ""       # optional: first episode number to use in filenames
    mt_engine: str = ""                    # Q6: "" | argos | ollama | deepl
    reading_aids: list[str] = field(default_factory=list)     # Q7: spec entries
    asbplayer: bool = False                # Q8
    convert_smi: bool = False              # Local modify: convert .smi before cleanup/readings
    format: str = ""                       # Q9: srt | vtt | ass
    output: str = ""                       # Q10
    final_action: str = "run"              # Q12: run | save | restart | quit | edit
    save_path: str = ""                    # Q11 sub-prompt
    is_movie: bool = False                 # Q1 hint: skip Q6 (episode scope) when set
    # Q1 step picker — which pipeline verbs to include. The visible wizard
    # default is the full pipeline (fetch + translate + modify + merge), but
    # the translate question itself still defaults to "Skip" so Enter-spamming
    # does not silently start AI translation.
    # Modify-only / merge-only / translate-only variants drop the verbs
    # they don't need from the emitted CLI and skip the corresponding
    # questions downstream.
    steps: set[str] = field(default_factory=lambda: {"fetch", "modify", "merge"})

    def to_toml(self) -> str:
        """Serialize as a TOML draft for resume support. Quick-and-dirty
        — only strings and bools; lists/sets become comma-joined strings."""
        lines = ["# getsubtitle wizard draft — auto-saved; safe to delete.\n"]
        lines.append("[wizard]\n")
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool):
                lines.append(f'{f.name} = {"true" if v else "false"}\n')
            elif isinstance(v, (list, set)):
                # Sets aren't ordered — sort for determinism so the draft
                # round-trips identically and tests can match on substrings.
                items = sorted(v) if isinstance(v, set) else v
                lines.append(f'{f.name} = "{",".join(items)}"\n')
            else:
                lines.append(f'{f.name} = "{v}"\n')
        return "".join(lines)


# ─── Wizard questions Q1-Q12 ────────────────────────────────────────────

def _wizard_url_is_movie(url: str) -> bool:
    """Heuristic: True when a URL clearly identifies a movie (not a TV
    series). Recognises TMDB /movie/, Letterboxd /film/, and IMDb
    title-pages tagged via 'movie' in the URL fragment. Used to skip
    Q6 (episode scope) and to avoid Season/Episode placeholders in
    download filenames."""
    if not url:
        return False
    low = url.lower()
    if "/movie/" in low or "/film/" in low:
        return True
    return False


def _wizard_describe_url_source(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    provider = provider_from_host(host)
    if "crunchyroll.com" in host:
        kind = "series URL" if "/series/" in path else "watch URL" if "/watch/" in path else "URL"
        return f"Crunchyroll {kind}"
    if "netflix.com" in host:
        kind = "watch URL" if "/watch/" in path else "catalog URL"
        return f"Netflix {kind}"
    if provider == "imdb":
        return "IMDb title URL" if re.search(r"/title/tt\d+", path) else "IMDb URL"
    if provider == "tmdb":
        if re.search(r"/movie/\d+", path):
            return "TMDB movie URL"
        if re.search(r"/tv/\d+", path):
            return "TMDB TV URL"
        return "TMDB URL"
    if "anilist.co" in host:
        return "AniList anime URL" if "/anime/" in path else "AniList URL"
    return f"{provider} URL"


def _wizard_media_counts(path: Path, limit: int = 5000) -> tuple[int, int, int, bool]:
    video_count = 0
    subtitle_count = 0
    season_dir_count = 0
    truncated = False
    if path.is_file():
        suffix = path.suffix.lower()
        return (
            1 if suffix in _BATCH_VIDEO_EXTS else 0,
            1 if suffix in SUB_EXTENSIONS else 0,
            0,
            False,
        )
    scanned = 0
    for item in path.rglob("*"):
        scanned += 1
        if scanned > limit:
            truncated = True
            break
        if item.is_dir() and parse_season_from_folder_name(item.name) is not None:
            season_dir_count += 1
        elif item.is_file():
            suffix = item.suffix.lower()
            if suffix in _BATCH_VIDEO_EXTS:
                video_count += 1
            elif suffix in SUB_EXTENSIONS:
                subtitle_count += 1
    return video_count, subtitle_count, season_dir_count, truncated


def _wizard_describe_path_source(raw_path: str) -> tuple[Path, str]:
    # Strip wrapping quotes that some file managers (Finder, GNOME Files,
    # Konsole drag-drop) add around paths with spaces. Pair them carefully:
    # only strip matching delimiters, otherwise leave intact (a path may
    # legitimately end with an apostrophe).
    cleaned = raw_path.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1]
    path = Path(cleaned).expanduser()
    if not path.exists():
        raise CliError(f"path not found: {path}")
    videos, subtitles, season_dirs, truncated = _wizard_media_counts(path)
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in _BATCH_VIDEO_EXTS:
            kind = "local video file"
        elif suffix in SUB_EXTENSIONS:
            kind = "local subtitle file"
        else:
            kind = "local file"
    elif parse_season_from_folder_name(path.name) is not None:
        kind = "local TV season folder"
    elif season_dirs:
        kind = "local show folder with season subfolders"
    elif videos == 1:
        kind = "local movie folder"
    elif videos > 1:
        kind = "local folder with video files"
    elif subtitles:
        kind = "local subtitle folder"
    else:
        kind = "local folder"
    suffix = " (scan limited)" if truncated else ""
    return path, f"{kind}: {videos} video file(s), {subtitles} subtitle file(s){suffix}"


def _wizard_title_candidates(title: str) -> list[dict]:
    """Return a list of {provider, label, url, is_movie} dicts. `is_movie`
    is the candidate's own opinion (TMDB movie endpoint, AniList format=
    MOVIE / single-episode SPECIAL/OVA/ONA) and lets the wizard skip Q6
    when the user picks it."""
    rows: list[dict] = []
    tmdb_key = get_provider_api_key("tmdb")
    if tmdb_key:
        tv = tmdb_search_tv(title, api_key=tmdb_key)
        if tv:
            rows.append({
                "provider": "tmdb-tv",
                "label": f"TMDB TV: {tv.get('title') or title} ({tv.get('year') or '?'})",
                "url": f"https://www.themoviedb.org/tv/{tv['tmdb_id']}",
                "is_movie": False,
            })
        movie = tmdb_search_movie(title, api_key=tmdb_key)
        if movie:
            rows.append({
                "provider": "tmdb-movie",
                "label": f"TMDB Movie: {movie.get('title') or title} ({movie.get('year') or '?'})",
                "url": f"https://www.themoviedb.org/movie/{movie['tmdb_id']}",
                "is_movie": True,
            })
    try:
        for cand in search_anilist(title, limit=3):
            rows.append({
                "provider": "anilist",
                "label": f"AniList: {cand.label()}",
                "url": f"https://anilist.co/anime/{cand.id}/",
                "is_movie": cand.is_movie(),
            })
    except CliError:
        pass
    return rows


def _wizard_title_from_candidate_label(label: str) -> str:
    text = re.sub(r"^(?:AniList|TMDB TV|TMDB Movie):\s*", "", label).strip()
    text = re.sub(r"^\d+:\s*", "", text)
    text = text.split("/", 1)[0]
    text = re.sub(r"\s*\(\d{4}.*$", "", text)
    return text.strip()


def _wizard_pick_title_candidate(title: str) -> tuple[str, str, str, bool] | None | str:
    """Pick a title hit. Return shape:
      - (url, provider, label, is_movie) — user picked a candidate
      - None                             — user chose to keep raw title text
      - "retry"                          — user wants to re-enter the title

    The is_movie flag is the candidate's own opinion (TMDB /movie/,
    AniList format=MOVIE, single-episode SPECIAL/OVA/ONA, …) and lets
    the wizard skip Q6 + flatten the download filename layout.
    """
    rows = _wizard_title_candidates(title)
    if not rows:
        # No candidates available. Tell the user WHY — most of the time it's
        # because no TMDB/AniList resolver key is configured.
        if not get_provider_api_key("tmdb"):
            print()
            print("    No title-resolver hits. Add a TMDB key for richer matches:")
            print("      getsubtitle --set-key tmdb")
            print("    Continuing with raw title text — fetch may still work via")
            print("    AniList or other built-in fallbacks.")
        return None
    print()
    print("    Title match candidates:")
    for i, row in enumerate(rows, start=1):
        print(f"    {i}) {row['label']}")
    print("    0) Keep raw title text")
    print("    r) Re-enter a different title")
    pick = _wizard_prompt("Pick candidate number, 0, or r", "1").strip().lower()
    if pick in ("r", "retry", "redo"):
        return "retry"
    if pick in ("0", "raw", "title", "keep"):
        return None
    if not pick.isdigit():
        return None
    idx = int(pick) - 1
    if not (0 <= idx < len(rows)):
        return None
    row = rows[idx]
    return row["url"], row["provider"], row["label"], row.get("is_movie", False)


_PIPELINE_STEPS = ("fetch", "translate", "modify", "merge")
_VALID_STEPS = (*_PIPELINE_STEPS, "rename")


def _wizard_parse_step_selection(raw: str) -> set[str]:
    """Parse Q1 step selection.

    Accepted forms are deliberately forgiving: "1,3,4", "1-4", step names,
    and the older hidden "a/all" aliases. Rename stays a separate maintenance
    workflow, so "all" maps to the four pipeline verbs only.
    """
    mapping = {
        "1": "fetch",
        "2": "translate",
        "3": "modify",
        "4": "merge",
        "5": "rename",
        "fetch": "fetch",
        "translate": "translate",
        "modify": "modify",
        "merge": "merge",
        "rename": "rename",
    }
    value = raw.strip().lower()
    value = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1-\2", value)
    if value in ("a", "all"):
        return set(_PIPELINE_STEPS)

    picked: set[str] = set()
    for tok in re.split(r"[, ]+", value):
        tok = tok.strip()
        if not tok:
            continue
        if re.fullmatch(r"\d+\s*-\s*\d+", tok):
            start_s, end_s = re.split(r"\s*-\s*", tok)
            start, end = int(start_s), int(end_s)
            if start <= end:
                numbers = range(start, end + 1)
            else:
                numbers = range(start, end - 1, -1)
            for number in numbers:
                step = mapping.get(str(number))
                if step:
                    picked.add(step)
                else:
                    print(f"    (ignored unrecognised step {number!r})")
            continue
        step = mapping.get(tok)
        if step is None:
            print(f"    (ignored unrecognised step {tok!r})")
            continue
        picked.add(step)
    return picked


@dataclass
class _RenameParts:
    path: Path
    title: str
    season_prefix: str
    season: str
    episode_prefix: str
    episode: str
    language: str
    modifiers: list[str]
    extension: str

    def render(self) -> str:
        trailer = [self.language, *self.modifiers] if self.language else list(self.modifiers)
        trailer_text = "." + ".".join(t for t in trailer if t) if trailer else ""
        return (
            f"{self.title} - "
            f"{self.season_prefix}{self.season}"
            f"{self.episode_prefix}{self.episode}"
            f"{trailer_text}.{self.extension}"
        )

    def variation_label(self) -> str:
        trailer = [self.language, *self.modifiers] if self.language else list(self.modifiers)
        trailer_text = "." + ".".join(t for t in trailer if t) if trailer else ""
        return (
            f"{self.title} - "
            f"{self.season_prefix}{self.season}"
            f"{self.episode_prefix}**"
            f"{trailer_text}.{self.extension}"
        )


_RENAME_FILENAME_RE = re.compile(
    r"^(?P<title>.+?)\s*-\s*"
    r"(?P<season_prefix>[A-Za-z]+)(?P<season>\d+)"
    r"(?P<episode_prefix>[A-Za-z]+)(?P<episode>\d+)"
    r"(?P<trailer>(?:\.[^.]+)*)\.(?P<extension>[A-Za-z0-9]+)$"
)
_RENAME_SUBTITLE_EXTS = {".srt", ".vtt", ".ass", ".ssa", ".smi", ".sami", ".txt"}


def _rename_parse_parts(path: Path) -> _RenameParts | None:
    if path.suffix.lower() not in _RENAME_SUBTITLE_EXTS:
        return None
    m = _RENAME_FILENAME_RE.match(path.name)
    if not m:
        return None
    trailer = [tok for tok in m.group("trailer").split(".") if tok]
    language = trailer[0] if trailer else ""
    modifiers = trailer[1:] if trailer else []
    return _RenameParts(
        path=path,
        title=m.group("title"),
        season_prefix=m.group("season_prefix"),
        season=m.group("season"),
        episode_prefix=m.group("episode_prefix"),
        episode=m.group("episode"),
        language=language,
        modifiers=modifiers,
        extension=m.group("extension"),
    )


def _rename_discover_parts(source: Path) -> list[_RenameParts]:
    if source.is_file():
        parsed = _rename_parse_parts(source)
        return [parsed] if parsed else []
    if not source.is_dir():
        return []
    out: list[_RenameParts] = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        parsed = _rename_parse_parts(path)
        if parsed:
            out.append(parsed)
    return out


def _rename_group_variations(parts: list[_RenameParts]) -> list[tuple[str, list[_RenameParts]]]:
    grouped: dict[str, list[_RenameParts]] = {}
    for part in parts:
        grouped.setdefault(part.variation_label(), []).append(part)
    return sorted(grouped.items(), key=lambda item: item[0].casefold())


def _rename_parse_selection(raw: str, group_count: int) -> set[int]:
    value = raw.strip().lower()
    if value in {"all", "a", "*"}:
        return set(range(1, group_count + 1))
    selected: set[int] = set()
    for tok in re.split(r"[, ]+", value):
        if not tok:
            continue
        if tok.isdigit() and 1 <= int(tok) <= group_count:
            selected.add(int(tok))
    return selected


def _rename_selected_parts(
    groups: list[tuple[str, list[_RenameParts]]],
    selected: set[int],
) -> list[_RenameParts]:
    out: list[_RenameParts] = []
    for idx in sorted(selected):
        out.extend(groups[idx - 1][1])
    return sorted(out, key=lambda part: (int(part.season), int(part.episode), part.path.name))


def _rename_with_digits(value: str, digits: int) -> str:
    return str(int(value)).zfill(max(1, digits))


def _rename_transform_parts(
    parts: list[_RenameParts],
    *,
    component: str,
    value: str = "",
    number_action: str = "",
) -> list[_RenameParts]:
    updated: list[_RenameParts] = []
    if component in {"title", "language", "modifiers", "extension"}:
        for part in parts:
            clone = replace(part)
            if component == "title":
                clone.title = value.strip()
            elif component == "language":
                clone.language = value.strip().lstrip(".")
            elif component == "modifiers":
                cleaned = value.strip().strip(".")
                clone.modifiers = [tok for tok in cleaned.split(".") if tok] if cleaned else []
            elif component == "extension":
                clone.extension = value.strip().lstrip(".")
            updated.append(clone)
    elif component == "season":
        action, _, arg = number_action.partition(":")
        for part in parts:
            clone = replace(part)
            if action == "prefix":
                clone.season_prefix = arg
            elif action == "number":
                clone.season = _rename_with_digits(arg, len(part.season))
            elif action == "digits":
                clone.season = _rename_with_digits(part.season, int(arg))
            updated.append(clone)
    elif component == "episode":
        action, _, arg = number_action.partition(":")
        if action == "range":
            start = int(arg)
            # Renumber DISTINCT episodes per season, not per file. This keeps
            # language variants of the same episode paired (E01.ja and E01.en
            # both become the same new number) and renumbers each season
            # independently from `start` instead of letting one season's count
            # bleed into the next.
            season_maps: dict[str, dict[int, int]] = {}
            for part in parts:
                eps = season_maps.setdefault(part.season, {})
                eps.setdefault(int(part.episode), 0)
            for eps in season_maps.values():
                for offset, ep in enumerate(sorted(eps)):
                    eps[ep] = start + offset
            for part in parts:
                clone = replace(part)
                new_ep = season_maps[part.season][int(part.episode)]
                clone.episode = _rename_with_digits(str(new_ep), len(part.episode))
                updated.append(clone)
        else:
            for part in parts:
                clone = replace(part)
                if action == "prefix":
                    clone.episode_prefix = arg
                elif action == "digits":
                    clone.episode = _rename_with_digits(part.episode, int(arg))
                updated.append(clone)
    return updated


def _rename_plan_for_parts(parts: list[_RenameParts]) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    for part in parts:
        new_name = part.render()
        try:
            dst = part.path.with_name(new_name)
        except ValueError as exc:
            # Defense in depth: turn a raw ValueError ("Invalid name") into a
            # clean CliError. The wizard validates input before this, but a
            # programmatic caller shouldn't get a traceback either.
            raise CliError(f"Cannot rename to {new_name!r}: invalid filename.") from exc
        plan.append((part.path, dst))
    return [(src, dst) for src, dst in plan if src != dst]


def _rename_plan(
    parts: list[_RenameParts],
    *,
    component: str,
    value: str = "",
    number_action: str = "",
) -> list[tuple[Path, Path]]:
    return _rename_plan_for_parts(_rename_transform_parts(
        parts,
        component=component,
        value=value,
        number_action=number_action,
    ))


def _rename_collision_errors(plan: list[tuple[Path, Path]], *, copy_mode: bool = False) -> list[str]:
    errors: list[str] = []
    destinations: dict[Path, Path] = {}
    sources = {src for src, _dst in plan}
    for src, dst in plan:
        previous = destinations.get(dst)
        if previous is not None and previous != src:
            errors.append(f"multiple files would become {dst.name}")
        destinations[dst] = src
        if dst.exists() and (copy_mode or dst not in sources):
            errors.append(f"{dst.name} already exists")
    return sorted(set(errors))


def _rename_apply_plan(plan: list[tuple[Path, Path]]) -> None:
    """Apply a checked rename plan without clobbering source files.

    A direct A->B, B->C loop can lose B on POSIX because rename replaces
    the destination. Moving every source to a temporary sibling first makes
    range shifts and swaps safe.
    """
    temporary: list[tuple[Path, Path, Path]] = []
    token = f".getsubtitle-renaming-{os.getpid()}"
    for idx, (src, dst) in enumerate(plan, start=1):
        tmp = src.with_name(f"{src.name}{token}-{idx}.tmp")
        while tmp.exists():
            idx += 1
            tmp = src.with_name(f"{src.name}{token}-{idx}.tmp")
        temporary.append((src, tmp, dst))
    try:
        for src, tmp, _dst in temporary:
            src.rename(tmp)
        for _src, tmp, dst in temporary:
            tmp.rename(dst)
    finally:
        # If the second phase partially failed, do not leave obvious temp
        # names behind when their original source name is still available.
        for src, tmp, _dst in temporary:
            if tmp.exists() and not src.exists():
                try:
                    tmp.rename(src)
                except OSError:
                    pass


def _rename_copy_plan(plan: list[tuple[Path, Path]]) -> None:
    for src, dst in plan:
        shutil.copy2(src, dst)


# Cross-platform unsafe filename characters: POSIX separators/NUL plus the
# Windows-reserved set (< > : " | ? * \ /) and ASCII control chars. Keeping
# subtitle names Windows-safe matters because they travel between machines.
_RENAME_UNSAFE_CHARS = set('/\\<>:"|?*') | {chr(c) for c in range(0x20)}


def _rename_value_is_safe(value: str) -> bool:
    """True when `value` is safe to put inside a filename component on every
    platform — no path separators, no Windows-reserved characters, no control
    characters. Unsafe values would make Path.with_name raise a raw ValueError
    on POSIX and produce un-creatable files on Windows."""
    if not value:
        return True
    if value != value.strip() or value.endswith("."):
        # Windows trims trailing dots/spaces, which silently changes the name.
        return False
    return not (set(value) & _RENAME_UNSAFE_CHARS)


def _wizard_rename_change_details(component: str, sample: _RenameParts) -> tuple[str, str]:
    if component in {"title", "language", "modifiers", "extension"}:
        prompt = {
            "title": "New title",
            "language": "New language token (e.g. ja, ko, ja-furigana-ko)",
            "modifiers": "New modifiers (dot-separated; empty removes modifiers)",
            "extension": "New extension (without dot)",
        }[component]
        if component == "extension":
            print("    This only changes the filename — it does NOT convert the")
            print("    subtitle format. For real conversion use `getsubtitle modify")
            print("    --convert smi-to-srt` (and similar).")
        value = _wizard_prompt(prompt, "")
        if component != "modifiers" and not value.strip():
            print("Empty value; rename cancelled.")
            return "", ""
        if not _rename_value_is_safe(value):
            print("    That can't be used in a filename on all platforms (avoid / \\ : * ? \" < > | and trailing dots/spaces); rename cancelled.")
            return "", ""
        return value, ""

    while True:
        print()
        print("How should it be changed?")
        print("    1) Change prefix (e.g. S -> Season, E -> Ep)")
        if component == "season":
            print("    2) Change season number (e.g. 03 -> 04)")
            print("    3) Change digits (e.g. 03 -> 003)")
        else:
            print("    2) Change range (e.g. 01-12 -> 13-24)")
            print("    3) Change digits (e.g. 01 -> 001)")
        action_pick = _wizard_prompt("Number", "2").strip()
        try:
            if action_pick == "1":
                new_prefix = _wizard_prompt(
                    "New prefix",
                    sample.season_prefix if component == "season" else sample.episode_prefix,
                )
                if not _rename_value_is_safe(new_prefix):
                    print("    That can't be used in a filename on all platforms (avoid / \\ : * ? \" < > | and trailing dots/spaces); rename cancelled.")
                    return "", ""
                return "", f"prefix:{new_prefix}"
            if action_pick == "2" and component == "season":
                new_number = _wizard_prompt("New season number", str(int(sample.season)))
                if not new_number.isdigit():
                    print("Season number must be numeric; rename cancelled.")
                    return "", ""
                return "", f"number:{new_number}"
            if action_pick == "2":
                first = _wizard_prompt("First episode number in the new range", str(int(sample.episode)))
                if not first.isdigit():
                    print("Episode number must be numeric; rename cancelled.")
                    return "", ""
                return "", f"range:{first}"
            if action_pick == "3":
                digits = _wizard_prompt(
                    "Number of digits",
                    str(len(sample.season if component == "season" else sample.episode)),
                )
                if not digits.isdigit() or int(digits) < 1:
                    print("Digits must be a positive number; rename cancelled.")
                    return "", ""
                return "", f"digits:{digits}"
            print("Invalid change type; rename cancelled.")
            return "", ""
        except _WizardBack:
            print("    Going back to the previous rename choice.")
            continue


def _wizard_q_rename(state: _WizardState) -> None:
    source = Path(state.source).expanduser()
    parts = _rename_discover_parts(source)
    if not parts:
        print("No renameable subtitle filenames found.")
        print("Expected shape: Title - S03E01.ja.furigana-hiragana.vtt")
        # Show what we DID find so a folder of validly-named-but-different
        # files doesn't look like an empty/broken folder.
        if source.is_dir():
            found = [
                p.name for p in sorted(source.iterdir())
                if p.is_file() and p.suffix.lower() in _RENAME_SUBTITLE_EXTS
            ]
            if found:
                print()
                print(f"Found {len(found)} subtitle file(s), but none match that shape:")
                for name in found[:5]:
                    print(f"    {name}")
                if len(found) > 5:
                    print(f"    ... and {len(found) - 5} more")
                print("Tip: rename needs ' - ' before SxxExx, e.g. 'Show - S01E01.ja.srt'.")
        return
    # Surface subtitle files we could not parse so the user isn't surprised
    # that some files in the folder are left untouched.
    if source.is_dir():
        skipped = [
            p.name for p in sorted(source.iterdir())
            if p.is_file()
            and p.suffix.lower() in _RENAME_SUBTITLE_EXTS
            and _rename_parse_parts(p) is None
        ]
        if skipped:
            print()
            print(f"Skipping {len(skipped)} file(s) that don't match the")
            print("  'Title - S03E05.lang.ext' shape (left untouched):")
            for name in skipped[:5]:
                print(f"    {name}")
            if len(skipped) > 5:
                print(f"    ... and {len(skipped) - 5} more")
    groups = _rename_group_variations(parts)
    step = "variation"
    selected_parts: list[_RenameParts] = []
    draft_parts: list[_RenameParts] = []
    candidate_parts: list[_RenameParts] = []
    handled_components: set[str] = set()
    component_back_step = "variation"
    component = ""
    value = ""
    number_action = ""
    plan: list[tuple[Path, Path]] = []
    copy_mode = True
    component_map = {
        "1": ("title", "Title"),
        "2": ("season", "Season"),
        "3": ("episode", "Episode"),
        "4": ("language", "Language"),
        "5": ("modifiers", "Modifiers"),
        "6": ("extension", "Extension (rename only; does not convert format)"),
    }

    while True:
        try:
            if step == "variation":
                print()
                print(f"Found {len(groups)} variation{'s' if len(groups) != 1 else ''} of files in the folder.")
                for idx, (label, group) in enumerate(groups, start=1):
                    count = f"  ({len(group)} file{'s' if len(group) != 1 else ''})"
                    print(f"    {idx}) {label}{count}")
                raw = _wizard_prompt("Which one would you like to work on? (1/2/3 or all)", "all")
                selected = _rename_parse_selection(raw, len(groups))
                if not selected:
                    print("No valid selection; rename cancelled.")
                    return
                selected_parts = _rename_selected_parts(groups, selected)
                draft_parts = list(selected_parts)
                candidate_parts = list(draft_parts)
                plan = []
                handled_components = set()
                component_back_step = "variation"
                step = "component"
                continue

            if step == "component":
                sample = draft_parts[0]
                print()
                print("Example:")
                print(f"  {sample.path.name}")
                print("  " + "-" * min(72, max(12, len(sample.path.name))))
                print("  {Title} - {Season}{Episode}.{Language}.{Modifiers}.{Extension}")
                print()
                print("What needs to be changed?")
                for number, (key, label) in component_map.items():
                    suffix = " (already handled)" if key in handled_components else ""
                    print(f"    {number}) {label}{suffix}")
                available_numbers = [
                    number for number, (key, _label) in component_map.items()
                    if key not in handled_components
                ]
                if not available_numbers:
                    print("All filename fields have already been handled; choose apply/copy.")
                    step = "apply_mode"
                    continue
                default_component = "2" if "season" not in handled_components else available_numbers[0]
                pick = _wizard_prompt("Number", default_component).strip()
                selected_component = component_map.get(pick[:1])
                component = selected_component[0] if selected_component else ""
                if not component:
                    print("Invalid component; rename cancelled.")
                    return
                if component in handled_components:
                    print("That filename field was already handled in this rename batch. Choose another field.")
                    continue
                step = "details"
                continue

            if step == "details":
                sample = draft_parts[0]
                value, number_action = _wizard_rename_change_details(component, sample)
                if component != "modifiers" and not value and not number_action:
                    return
                candidate_parts = _rename_transform_parts(
                    draft_parts,
                    component=component,
                    value=value,
                    number_action=number_action,
                )
                plan = _rename_plan_for_parts(candidate_parts)
                if not plan:
                    print("Nothing would change.")
                    return
                step = "apply_mode"
                continue

            if step == "apply_mode":
                print()
                print(f"Planned rename: {len(plan)} file(s)")
                for src, dst in plan[:20]:
                    print(f"  {src.name}")
                    print(f"    -> {dst.name}")
                if len(plan) > 20:
                    print(f"  ... and {len(plan) - 20} more")
                print()
                print("What next?")
                print("    1) Looks good — apply now")
                print("    2) Keep this change and change another field")
                print("    3) Discard this change and choose another field")
                print("    4) Cancel")
                next_pick = _wizard_prompt("Number", "1").strip()
                if next_pick.startswith("2"):
                    draft_parts = list(candidate_parts)
                    handled_components.add(component)
                    plan = _rename_plan_for_parts(draft_parts)
                    component = ""
                    value = ""
                    number_action = ""
                    component_back_step = "apply_mode" if plan else "variation"
                    step = "component"
                    continue
                if next_pick.startswith("3"):
                    # Discarding a previewed change must NOT lock the field —
                    # the user may want to retry it with a different value.
                    candidate_parts = list(draft_parts)
                    plan = _rename_plan_for_parts(draft_parts)
                    component = ""
                    value = ""
                    number_action = ""
                    component_back_step = "apply_mode" if plan else "variation"
                    step = "component"
                    continue
                if next_pick.startswith("4"):
                    print("Operation cancelled.")
                    return
                step = "apply_kind"
                continue

            if step == "apply_kind":
                print()
                print("How should it be applied?")
                print("    1) Copy and apply (keep the original files)")
                print("    2) Rename the original files")
                apply_pick = _wizard_prompt("Number", "1").strip()
                copy_mode = not apply_pick.startswith("2")
                step = "confirm"
                continue

            if step == "confirm":
                operation = "copy" if copy_mode else "rename"
                errors = _rename_collision_errors(plan, copy_mode=copy_mode)
                if errors:
                    print()
                    print("Operation cancelled because of filename conflicts:")
                    for err in errors:
                        print(f"  - {err}")
                    return
                confirm_question = "Create these renamed copies?" if copy_mode else "Rename the original files?"
                if not _wizard_yesno(confirm_question, default=False):
                    print("Operation cancelled.")
                    return
                try:
                    if copy_mode:
                        _rename_copy_plan(plan)
                        print(f"Copied {len(plan)} renamed file(s).")
                    else:
                        _rename_apply_plan(plan)
                        print(f"Renamed {len(plan)} file(s).")
                except OSError as exc:
                    # No traceback for a filesystem failure mid-apply. Tell the
                    # user plainly and warn that state may be partial.
                    print(f"Could not finish the {operation}: {exc}")
                    print("    Some files may not have been changed. Re-run rename")
                    print("    to see the current state before trying again.")
                return
        except _WizardBack:
            previous = {
                "variation": None,
                "component": component_back_step,
                "details": "component",
                "apply_mode": "details",
                "apply_kind": "apply_mode",
                "confirm": "apply_mode",
            }[step]
            if previous is None:
                raise
            step = previous
            print("    Going back to the previous rename step.")


def _wizard_next_q(state: _WizardState) -> str:
    """Return the next contiguous question label ('Q1.', 'Q2.', …).

    The wizard's question functions kept fixed numbers from an older
    12-question flow, so a trimmed run showed visible gaps (Q1 → Q2 →
    Q4 → Q7). A running counter numbers each heading in the order it is
    actually printed, which stays gap-free even when `state.steps`
    mutates mid-flow (the local-language preflight can add 'fetch'
    after the source/languages questions have already been numbered)."""
    n = getattr(state, "_qcount", 0) + 1
    state._qcount = n
    return f"Q{n}."


def _wizard_step_headings(label: str, state: _WizardState) -> int:
    """How many numbered headings a step prints in the forward pass.

    Every step prints one, except the source step: with fetch enabled it
    shows a source-kind picker AND an entry prompt (two headings); local-
    only flows show a single folder/file prompt."""
    if label == "source":
        return 2 if "fetch" in state.steps else 1
    return 1


def _wizard_qcount_before(state: _WizardState, target_label: str) -> int:
    """Count numbered headings shown before `target_label` in a forward
    pass, honoring the same step-gating as `_run_wizard`. Used to prime
    the counter when the edit loop re-runs a single question so the
    re-asked heading keeps its forward-pass number."""
    skip = {
        "scope":        "fetch" not in state.steps,
        "rename":       "rename" not in state.steps,
        "filename_numbering": not _wizard_should_ask_filename_numbering(state),
        "translate":    "translate" not in state.steps,
        "reading_aids": "modify" not in state.steps,
    }
    count = 0
    for lbl, _fn in _WIZARD_STEPS:
        if lbl == target_label:
            break
        if skip.get(lbl, False):
            continue
        count += _wizard_step_headings(lbl, state)
    return count


def _wizard_q0_steps(state: _WizardState) -> None:
    """Q1: pick which pipeline steps to include. The user can run the
    full pipeline (default) or a focused subset — e.g. 'just merge' for
    a folder of existing .srt files, or 'just modify' to add furigana
    to a single .ja.srt the user already has. Skipping steps avoids
    asking irrelevant questions downstream and keeps the emitted CLI
    short."""
    print()
    print(f"{_wizard_next_q(state)} What do you want getsubtitle to do?")
    print("    1) Fetch     — download subtitles from a URL or title")
    print("    2) Translate — fill any missing language with AI translation")
    print("    3) Modify    — clean up cues, add reading aids (furigana/hangul/pinyin/…)")
    print("    4) Merge     — stack multiple languages into one study file")
    print("    5) Rename    — batch-rename existing subtitle filenames")
    print()
    print("    Default: 1-4 — fetch, translate, modify, then merge.")
    print("    Common picks:")
    print("      1-4     full subtitle workflow")
    print("      1,3,4   download + modify + merge existing subtitles")
    print("      5       rename titles, prefixes, change numbering")
    print()
    raw = _wizard_prompt(
        "Numbers or ranges, or Enter for default",
        "1-4",
        allow_back=False,
    ).strip().lower()
    picked = _wizard_parse_step_selection(raw)
    if not picked:
        raise CliError("interactive: pick at least one step.")
    if "rename" in picked and len(picked) > 1:
        print("    Rename is a separate maintenance workflow; using rename only.")
        picked = {"rename"}
    state.steps = picked
    # If only a single verb is selected, surface what the wizard will
    # ask next so the user feels oriented before answering Q2.
    label = " + ".join(s for s in _VALID_STEPS if s in picked)
    print(f"    Selected: {label}.")


def _wizard_q1_source(state: _WizardState) -> None:
    """Q2: choose source kind, then collect the actual URL/path. When
    fetch is NOT in state.steps, the URL/title branches are hidden —
    modify/merge/translate work on local files, not URLs."""
    print()
    if "fetch" not in state.steps:
        # No URL/title branch — the local-path branch is the only one
        # that makes sense for modify/merge/translate alone.
        state.source_kind = "path"
        if state.steps == {"rename"}:
            print(f"{_wizard_next_q(state)} Folder or file to rename.")
            print("    Drop a season folder or one subtitle file.")
        else:
            print(f"{_wizard_next_q(state)} Folder or file to process.")
            print("    Drop a folder of .srt files, a single .srt file, or any path")
            print("    your selected step(s) should operate on.")
        while True:
            src = _wizard_prompt("Folder or file path")
            try:
                path, description = _wizard_describe_path_source(src)
            except CliError as exc:
                print(f"    {exc}")
                continue
            file_episode = parse_episode_marker(path.name) if path.is_file() else None
            if file_episode:
                state.season = str(file_episode[0])
                state.episode = str(file_episode[1])
                print(f"    Selected episode: {_episode_label_se(file_episode[0], file_episode[1])}")
            if path.is_file() and state.steps == {"rename"}:
                pass
            elif path.is_file() and state.steps & {"merge"}:
                print("    File selected; using its folder so matching sidecar subtitles can be found.")
                path = path.parent
                _videos, subtitles, _season_dirs, truncated = _wizard_media_counts(path)
                suffix = " (scan limited)" if truncated else ""
                description = f"local folder beside selected file: {subtitles} subtitle file(s){suffix}"
            elif path.is_file() and path.suffix.lower() in _BATCH_VIDEO_EXTS and state.steps & {"modify"}:
                print("    Video file selected; using its folder so sidecar subtitle files can be found.")
                path = path.parent
                _videos, subtitles, _season_dirs, truncated = _wizard_media_counts(path)
                suffix = " (scan limited)" if truncated else ""
                description = f"local folder beside video: {subtitles} subtitle file(s){suffix}"
            if "modify" in state.steps:
                smi_files = scan_smi_files([path])
                if file_episode:
                    smi_files = [
                        smi for smi in smi_files
                        if parse_episode_marker(smi.name) == file_episode
                    ]
                state.convert_smi = bool(smi_files)
                if state.convert_smi:
                    print("    SMI subtitles found; will convert them to SRT before cleanup/readings.")
            state.source = str(path)
            print(f"    Identified as: {description}")
            return
    print(f"{_wizard_next_q(state)} What should getsubtitle work on?")
    print("    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)")
    print("    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)")
    print("    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)")
    # Default to title search only when a title-resolver key is available;
    # otherwise default to the path branch, which is the most reliable first-
    # time experience.
    default_q1 = "1" if get_provider_api_key("tmdb") else "3"
    while True:
        pick = _wizard_prompt("Number", default_q1).strip()
        if pick in ("1", "2", "3"):
            break
        print("    Invalid selection. Type 1, 2, or 3. To search for a title, choose 1 first.")
    if pick == "3":
        state.source_kind = "path"
    elif pick == "1":
        state.source_kind = "title"
    else:
        state.source_kind = "url"
    print()
    entry_q = _wizard_next_q(state)
    if state.source_kind == "url":
        print(f"{entry_q} Enter the URL.")
        while True:
            src = _wizard_prompt("URL")
            if _looks_like_url(src):
                state.source = src
                state.is_movie = _wizard_url_is_movie(src)
                print(f"    Identified as: {_wizard_describe_url_source(src)}")
                return
            print("    That does not look like an http/https URL. Try again, or enter 'q' to quit.")
    if state.source_kind == "title":
        print(f"{entry_q} Enter the movie or show title.")
        while True:
            title = _wizard_prompt("Title")
            if _looks_like_url(title):
                print("    That looks like a URL. Choose option 'a' if you want to use a URL.")
                continue
            print(f"    Identified as: title search for {title!r}")
            picked = _wizard_pick_title_candidate(title)
            if picked == "retry":
                # User wants to type a different title. Loop without
                # assigning anything to state.source yet.
                continue
            if picked is None:
                # No matches OR user explicitly chose to keep raw text.
                state.source = title
                # Title-text input is genuinely ambiguous; ask once so we
                # can skip Q6 (and avoid Season Unknown / S00E00 on disk).
                state.is_movie = _wizard_yesno(
                    "Is this a movie? (No = TV show / anime)", default=False
                )
            else:
                picked_url, provider, label, picked_is_movie = picked
                state.source = picked_url
                state.source_title = _wizard_title_from_candidate_label(label)
                state.source_kind = "url"
                # Trust the picker's own movie tag — TMDB /movie/ and
                # AniList format=MOVIE both flow through here. URL-shape
                # detection is the fallback for other providers.
                state.is_movie = picked_is_movie or _wizard_url_is_movie(picked_url)
                print(f"    Locked to ID source: {label} [{provider}]")
            return
    print(f"{entry_q} Enter the folder or file path.")
    while True:
        src = _wizard_prompt("Folder or file path")
        try:
            path, description = _wizard_describe_path_source(src)
        except CliError as exc:
            print(f"    {exc}")
            continue
        state.source = str(path)
        print(f"    Identified as: {description}")
        return


def _wizard_q2_languages(state: _WizardState) -> None:
    print()
    print(f"{_wizard_next_q(state)} Which subtitle languages do you want to collect?")
    print("    List them in the order you want them displayed (top → bottom).")
    print("    Examples: ja,en   ja,ko,en,es   japanese,korean,english")
    raw = _wizard_prompt("Languages (comma-separated)", "ja,en")
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if not parts:
        raise CliError("interactive: no languages provided.")
    # Normalise via existing language alias map. Reject unknown codes early
    # so the user fixes typos here rather than after a 60-second probe.
    norm: list[str] = []
    for p in parts:
        canon = LANGUAGE_ALIASES.get(p, p)
        if len(canon) > 3 and canon not in LANGUAGE_ALIASES.values():
            raise CliError(f"interactive: unrecognised language code {p!r}.")
        norm.append(canon)
    # de-dupe preserving order
    seen: set[str] = set()
    state.languages = [c for c in norm if not (c in seen or seen.add(c))]
    reading_capable = [lang for lang in state.languages if lang in {"ja", "ko", "zh", "yue"}]
    if reading_capable and "modify" not in state.steps:
        names = {
            "ja": "Japanese furigana",
            "ko": "Korean romanization",
            "zh": "Mandarin pinyin",
            "yue": "Cantonese Jyutping",
        }
        label = ", ".join(names[lang] for lang in reading_capable)
        print()
        print(f"    {label} reading aids are available, but Modify is not selected.")
        print("    Add the Modify step so I can ask which reading aids you want?")
        if _wizard_yesno("Add Modify step for reading aids?", default=True):
            state.steps.add("modify")
            print("    Selected: fetch + modify.")
        else:
            print("    Reading aids skipped for this workflow.")
    _wizard_offer_fetch_for_missing_local_languages(state)


def _wizard_local_available_languages(state: _WizardState) -> set[str]:
    """Best-effort language inventory for a local wizard source.

    Used only for UX preflight: local modify/merge workflows can otherwise
    build a syntactically valid command that has no chance of producing the
    requested stack because the folder only contains another language.
    """
    if not state.source:
        return set()
    root = Path(state.source).expanduser()
    if not root.exists():
        return set()
    paths = [root]
    detected: set[str] = set()
    rows = scan_subtitle_files_extended(paths, include_furigana=False)
    if state.season or state.episode:
        keys = {(season, episode) for _path, season, episode, _lang, _is_mt, _fmt in rows}
        keys.update(
            ep for ep in (parse_episode_marker(path.name) for path in scan_smi_files(paths))
            if ep is not None
        )
        selected = set(filter_episode_keys(
            keys,
            season=state.season or "all",
            episode=state.episode or "all",
        ))
        rows = [row for row in rows if (row[1], row[2]) in selected]
    detected.update(lang for _path, _season, _episode, lang, _is_mt, _fmt in rows if not is_pseudo_lang(lang))

    smi_files = scan_smi_files(paths)
    if state.season or state.episode:
        smi_files = [
            path for path in smi_files
            if parse_episode_marker(path.name) in selected
        ]
    for smi_path in smi_files:
        try:
            text = _sami_decode_bytes(smi_path.read_bytes())
            detected.update(parse_sami(text).keys())
        except Exception:
            continue
    return detected


def _wizard_offer_fetch_for_missing_local_languages(state: _WizardState) -> None:
    if "fetch" in state.steps or not (state.steps & {"modify", "merge"}):
        return
    if state.source_kind != "path" or not state.source or not state.languages:
        return
    available = _wizard_local_available_languages(state)
    if not available:
        return
    missing = [lang for lang in state.languages if lang not in available]
    if not missing:
        return
    print()
    print("    Local subtitle check:")
    print(f"      Found locally: {', '.join(sorted(available))}")
    print(f"      Missing for your requested stack: {', '.join(missing)}")
    print("    If you continue without Fetch, modify/merge can only use the")
    print("    subtitle languages already in this folder.")
    if _wizard_yesno("Search online for the missing languages now?", default=True):
        local_target = state.source
        print()
        print("    Enter an IMDb/TMDB/AniList/Crunchyroll URL, or type the title.")
        fetch_source = _wizard_prompt("URL or title to fetch")
        if _looks_like_url(fetch_source):
            state.source_kind = "url"
            state.source = fetch_source
            state.source_title = ""
            state.is_movie = _wizard_url_is_movie(fetch_source)
        else:
            state.source_kind = "title"
            state.source = fetch_source
            state.source_title = ""
        state.steps.add("fetch")
        state.output = local_target
        print(f"    Fetch will save into: {local_target}")
        print("    Then Modify/Merge will continue from that folder.")
    else:
        print("    Tip: restart with `getsubtitle -i`, choose Fetch, and use a")
        print("    catalog URL/title so getsubtitle can look online for missing tracks.")


def _wizard_q3_order(state: _WizardState) -> None:
    """Confirm display order; only branch into custom-order on 'no'."""
    if len(state.languages) <= 1:
        state.order = list(state.languages)
        return
    default_order = ",".join(state.languages)
    print()
    print("Q5. Subtitle display order (top → bottom on screen).")
    print(f"    Default: {default_order}")
    if len(state.languages) >= 2:
        language_names = {
            "ja": "Japanese",
            "ko": "Korean",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "zh": "Chinese",
            "yue": "Cantonese",
            "th": "Thai",
            "ar": "Arabic",
            "hi": "Hindi",
            "ru": "Russian",
        }
        top_code = state.languages[0]
        bottom_code = state.languages[1]
        top = language_names.get(top_code, top_code.upper())
        bottom = language_names.get(bottom_code, bottom_code.upper())
        print(f"    '{top_code},{bottom_code}' = {top} on top, {bottom} below.")
    keep = _wizard_yesno(f"Keep order {default_order}?", default=True)
    if keep:
        state.order = list(state.languages)
        return
    raw = _wizard_prompt("Custom order (comma-separated, top → bottom)", default_order)
    order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    order = [LANGUAGE_ALIASES.get(p, p) for p in order]
    # Must be a permutation of Q3's languages.
    if set(order) != set(state.languages):
        raise CliError(
            "interactive: display order must contain the same languages as Q3 "
            f"({','.join(state.languages)})."
        )
    state.order = order


def _wizard_q4_master(state: _WizardState) -> None:
    if len(state.order) <= 1:
        state.master = ""
        return
    # Q5 inherits its choices from Q4's order list. The smart "first
    # learner-priority match" heuristic confused users (Korean learner
    # collecting en,ja,ko sees option 2 = Japanese). Cleaner: offer
    # first-displayed (the common case) and a custom override over the
    # collected languages.
    print()
    print("Q6. Which language controls cue timing (the 'master' track)?")
    # List one option per collected language so the user doesn't have to
    # navigate a "Custom" branch. The first-displayed is the recommendation.
    for i, code in enumerate(state.order, start=1):
        tail = "  (recommended — first displayed)" if i == 1 else ""
        print(f"    {i}) {code}{tail}")
    n = len(state.order)
    pick = _wizard_prompt("Number", "1").strip()
    if pick.isdigit() and 1 <= int(pick) <= n:
        idx = int(pick) - 1
        # First-displayed is the default — leave master empty so the
        # downstream 'first lang wins' logic keeps working.
        state.master = "" if idx == 0 else state.order[idx]
    else:
        state.master = ""


def _wizard_q5_scope(state: _WizardState) -> None:
    """Episode scope — only when source is a URL or title for a TV series."""
    if state.source_kind not in ("url", "title"):
        state.season = ""
        state.episode = ""
        return
    # Movies have no season/episode. Skip Q6 entirely so the user doesn't
    # see an irrelevant prompt and the downstream filename builder doesn't
    # invent 'Season Unknown' / 'S00E00' placeholders.
    if state.is_movie:
        state.season = ""
        state.episode = ""
        return
    if state.season or state.episode:
        print()
        scope_q = _wizard_next_q(state)
        if state.season and state.episode:
            if state.season.isdigit() and state.episode.isdigit():
                label = _episode_label_se(int(state.season), int(state.episode))
            else:
                label = f"season {state.season}, episode {state.episode}"
            print(f"{scope_q} Episode scope already selected: {label}")
        elif state.season:
            print(f"{scope_q} Season scope already selected: season {state.season}")
        else:
            print(f"{scope_q} Episode scope already selected: episode {state.episode}")
        return
    parsed_source = urllib.parse.urlparse(state.source or "")
    is_crunchyroll = "crunchyroll.com" in parsed_source.netloc.lower()
    print()
    print(f"{_wizard_next_q(state)} What episode scope?")
    print("    1) Movie / single item (no season/episode)")
    print("    2) A specific season + episode (or range)")
    print("    3) Whole season, every episode (-e all)")
    print("    4) Auto — let getsubtitle infer from the URL/title metadata")
    print("       (anime URLs typically resolve to single episodes; movies to a")
    print("        single item; TV without -e usually picks S01E01)")
    if is_crunchyroll:
        print()
        print("    Crunchyroll may display Season 3 as E25-E37, but subtitle")
        print("    sources usually search that as Season 3 episodes 1-13.")
    pick = _wizard_prompt("Number", "2" if is_crunchyroll else "4").strip()
    if pick == "1":
        state.season = ""
        state.episode = ""
    elif pick == "2":
        state.season = _wizard_prompt("Season or range (e.g. 1, 2-3, all)", "1")
        state.episode = _wizard_prompt("Episode or range within each season (e.g. 5, 1-10, all)", "1")
    elif pick == "3":
        state.season = state.season or "1"
        state.episode = "all"
        # Non-anime TV needs TMDB to expand -e all. Heads-up only.
        if state.source_kind == "title" or (
            "anilist" not in state.source.lower()
            and "myanimelist" not in state.source.lower()
        ):
            print("    (Note: -e all on non-anime TV requires a TMDB key. "
                  "Run `getsubtitle --set-key tmdb` later if needed.)")
    elif pick == "4" and is_crunchyroll:
        print("    Crunchyroll auto cannot reliably infer the visible season.")
        print("    Enter the season and episode numbers used by subtitle sources.")
        state.season = _wizard_prompt("Season or range (e.g. 1, 2-3, all)", "1")
        state.episode = _wizard_prompt("Episode or range within each season (e.g. 5, 1-10, all)", "1")
    else:
        state.season = ""
        state.episode = ""


def _wizard_should_ask_filename_numbering(state: _WizardState) -> bool:
    if "fetch" not in state.steps:
        return False
    if state.source_kind not in ("url", "title"):
        return False
    if not state.season or not str(state.season).isdigit():
        return False
    if int(state.season) <= 1:
        return False
    if not state.episode or state.episode in {"auto"}:
        return False
    return True


def _wizard_q5_filename_numbering(state: _WizardState) -> None:
    if not _wizard_should_ask_filename_numbering(state):
        state.episode_filename_start = ""
        return
    print()
    print(f"{_wizard_next_q(state)} How should episode numbers appear in output filenames?")
    print(f"    You are searching Season {state.season} episode(s): {state.episode}.")
    print("    Some streaming pages continue numbering across seasons, while")
    print("    subtitle sources often restart from episode 1 inside each season.")
    print()
    print("    1) Start filenames at E1 for this season")
    print(f"       Example: S{int(state.season):02d}E01, S{int(state.season):02d}E02, ...")
    print("    2) Match the episode numbers shown on the streaming page")
    print(f"       Example: S{int(state.season):02d}E25, S{int(state.season):02d}E26, ...")
    pick = _wizard_prompt("Number", "1").strip()
    if pick != "2":
        state.episode_filename_start = ""
        return
    while True:
        raw = _wizard_prompt("First episode number shown on the page (e.g. 25)")
        if raw.isdigit() and int(raw) > 0:
            state.episode_filename_start = raw
            print(
                f"    Output filenames will start at "
                f"S{int(state.season):02d}E{int(raw):02d}."
            )
            return
        print("    Enter a positive number, like 25.")


def _wizard_q6_translate(state: _WizardState) -> None:
    print()
    print(f"{_wizard_next_q(state)} If a language is missing, what should we do?")
    print("    1) Skip — accept the gap (no AI translation)")
    print("    2) Argos — on your computer, low quality (free)")
    print("    3) Ollama — on your computer, good quality (free; slower)")
    print("    4) DeepL — online, better quality (free tier; needs API key)")
    pick = _wizard_prompt("Number", "1").strip()
    state.mt_engine = {"1": "", "2": "argos", "3": "ollama", "4": "deepl"}.get(pick[:1], "")


def _wizard_q7_reading_aids(state: _WizardState) -> None:
    """Multi-select reading aids. Defaults to the sensible mode for each
    collected language (Japanese → hiragana, Korean → Revised, Chinese →
    tone marks)."""
    # Filter the menu down to languages the user is actually collecting,
    # plus a couple of "but you might want it anyway" hints.
    relevant: list[tuple[str, str, str, bool]] = [
        row for row in _WIZARD_READING_AID_MENU if row[0] in state.languages
    ]
    if not relevant:
        state.reading_aids = []
        return
    print()
    print(f"{_wizard_next_q(state)} Reading aids (phonetic guides for the original script).")
    # Pick a script-appropriate example so Korean / Mandarin users don't
    # see a kanji-only sample. Falls back to a Japanese example only when
    # ja is the first relevant language.
    primary = relevant[0][0]  # base language code from the first menu row
    example = {
        "ja": "漢字（かんじ）",
        "ko": "한글 (hangeul)",
        "zh": "漢字 (pīnyīn)",
        "yue": "漢字 (jyutping)",
    }.get(primary, "original (reading)")
    print("    VTT renders them as ruby above the script; SRT / SMI / ASS")
    print(f"    show them as parenthetical {example} form.")
    print("    Pick any combination by number, or '1' to skip.")
    # 'No reading aid' is the explicit first choice + default. The aid
    # entries shift to indices 2..n+1 so users see the no-op at the top
    # and don't have to know that 'none' is a magic word.
    print("    1) No reading aid (skip)")
    for i, (lang, spec, label, shipping) in enumerate(relevant, start=2):
        print(f"    {i}) {label}   [{spec}]")
    raw = _wizard_prompt(
        "Numbers (comma-separated)",
        "1",
    ).lower()
    if raw in ("", "1", "none", "0", "no", "skip"):
        state.reading_aids = []
        return
    picks: list[str] = []
    deferred_seen: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        # Aid entries are 1-indexed in the menu, but '1' is reserved for
        # 'No reading aid'. Subtract 2 to land in the relevant[] list.
        idx = int(tok) - 2
        if not (0 <= idx < len(relevant)):
            continue
        lang, spec, label, shipping = relevant[idx]
        picks.append(spec)
        if not shipping:
            deferred_seen.append(spec)
    state.reading_aids = picks
    if deferred_seen:
        print()
        print("    Heads up: backend not implemented yet for: " + ", ".join(deferred_seen))
        print("    These are accepted in the generated TOML so you can re-run once")
        print("    the backend ships. Saving / printing the workflow is safe.")


def _wizard_q8_asbplayer(state: _WizardState) -> None:
    print()
    print("Q10. Apply learner-friendly cleanup? (single-line cues + strip")
    print("    broadcast noise like ➡). Works in any player.")
    state.asbplayer = _wizard_yesno("Apply cleanup preset?", default=True)


def _wizard_q9_format(state: _WizardState) -> None:
    needs_ruby = any(spec.startswith("ja:hiragana") or spec.startswith("ja:furigana")
                     for spec in state.reading_aids)
    default = "vtt" if (state.asbplayer and needs_ruby) else "srt"
    print()
    print("Q11. Final output format.")
    print("    1) SRT  — most compatible (default if no ruby reading aid)")
    print("    2) VTT  — best for Japanese ruby in asbplayer/browser study")
    print("             workflows; local-player ruby support is uneven.")
    print("    3) SMI")
    print("    4) ASS  — best local-player choice for stacked Korean/Chinese/Cantonese")
    print("             readings above the original script.")
    print("    5) TXT - without timestamp")
    pick = _wizard_prompt("Number", {"vtt": "2", "srt": "1"}.get(default, "1")).strip()
    state.format = {"1": "srt", "2": "vtt", "3": "smi", "4": "ass", "5": "txt"}.get(pick[:1], default)
    if needs_ruby and state.format != "vtt":
        print("    Note: hiragana readings render as ruby (above-the-kanji)")
        print("          only in VTT; SRT/SMI/ASS fall back to parenthetical")
        print("          漢字（かんじ） form.")
    if state.format == "vtt" and state.asbplayer and needs_ruby:
        print("    Reminder: in asbplayer, enable Settings > Misc > Subtitles >")
        print("              Subtitle HTML = Render to see ruby. Most other")
        print("              players render VTT ruby out of the box.")


def _wizard_q10_output(state: _WizardState) -> None:
    print()
    print("Q12. Where should the final files go?")
    print("    1) Default — ~/Downloads/GetSubtitle")
    print("    2) Same folder as the source files (in-place)")
    print("    3) Custom folder")
    pick = _wizard_prompt("Number", "1").strip()
    if pick == "1":
        state.output = "~/Downloads/GetSubtitle"
    elif pick == "2":
        state.output = ""  # default downstream = beside source
    else:
        state.output = _wizard_prompt("Output folder", "~/Downloads/GetSubtitle")


def _wizard_plain_plan(state: _WizardState) -> list[str]:
    """A few plain-language lines describing what the workflow will do, so
    the user sees the intent at a glance instead of decoding the full CLI
    flag string."""
    langs = ", ".join(state.languages)
    src = state.source_title or state.source or "your files"
    steps = state.steps
    if "rename" in steps:
        return [f"Rename subtitle files in {src}"]
    scope = ""
    if state.season and state.episode:
        scope = f"  (season {state.season}, episode {state.episode})"
    elif state.season:
        scope = f"  (season {state.season})"
    lines: list[str] = []
    if "fetch" in steps:
        lines.append(f"Fetch {langs} for {src}{scope}")
    else:
        lines.append(f"Use local {langs} files in {src}")
    if "translate" in steps and state.mt_engine:
        lines.append(f"Fill gaps with {state.mt_engine.title()} AI translation")
    if "modify" in steps:
        if state.reading_aids:
            lines.append(f"Add reading aids: {', '.join(state.reading_aids)}")
        else:
            lines.append("Clean up cues (single line, strip broadcast noise)")
    if "merge" in steps:
        fmt = (state.format or "srt").upper()
        lines.append(f"Stack {langs} into one {fmt} study file")
    lines.append(f"Save to {state.output or 'the source folder'}")
    return lines


def _wizard_q11_action(state: _WizardState) -> str:
    """Final action. Returns one of 'run', 'save', 'restart', 'quit', 'edit'."""
    # Fixed-width separator. Stretching to the CLI command produces
    # ~190-char rules that wrap on most terminals and look terrible;
    # 70 fits a standard 80-col terminal with two columns of breathing
    # room. The CLI form can soft-wrap; that's fine.
    cli_string = _wizard_emit_cli_string(state)
    toml_str = _wizard_emit_toml(state)
    rule = "=" * 70
    print()
    # Plain-language plan first — the human "what's going to happen" before
    # any flag soup, so beginners don't have to parse the CLI string.
    print(rule)
    print("Here's the plan:")
    print(rule)
    for ln in _wizard_plain_plan(state):
        print(f"  • {ln}")
    # Smart-defaults block: the five questions the wizard no longer
    # asks. Surfaced so users see (and can revise) what was auto-picked.
    notes = getattr(state, "_smart_defaults_notes", None) or {}
    if notes:
        print(rule)
        print("Smart defaults filled in for you (edit via 'Edit a single answer'):")
        print(rule)
        for k, v in notes.items():
            print(f"  {k:14} {v}")
    print(rule)
    print("Based on your choice, you can try:")
    print(rule)
    print("  " + cli_string)
    print(rule)
    print("Equivalent workflow file (save as .toml):")
    print(rule)
    for line in toml_str.splitlines():
        print("  " + line)
    print(rule)
    # Consistency check: reading aid wants VTT ruby but format is something else.
    needs_ruby = any(
        spec.startswith("ja:hiragana") or spec.startswith("ja:furigana")
        for spec in state.reading_aids
    )
    if needs_ruby and state.format and state.format != "vtt":
        print(f"  Note: ja:hiragana looks best as VTT ruby; format is {state.format!r}.")
        print("        SRT/SMI/ASS will fall back to parenthetical 漢字（かんじ） form.")
    print()
    # Default-action heuristic: save-first is safer when "run" would start a
    # long network job (URL/title sources). For local paths, run-first is fine.
    default_pick = "2" if state.source_kind in ("url", "title") else "1"
    print("    1) Run it now")
    print("    2) Save as a reusable workflow file")
    print("    3) Edit a single answer")
    print("    4) Start over from beginning")
    print("    5) Quit")
    pick = _wizard_prompt("Number", default_pick).strip()
    mapping = {"1": "run", "2": "save", "3": "edit", "4": "restart", "5": "quit"}
    return mapping.get(pick[:1], "run")


# ─── Orchestrator ──────────────────────────────────────────────────────

# Question dispatch table keeps the orchestrator readable and the test
# harness focused — tests can call individual questions via this table.
_WIZARD_STEPS: list[tuple[str, "callable"]] = [
    # Streamlined down to a maximum of 7 user-facing questions. Five
    # questions were removed in favor of smart defaults applied by
    # `_wizard_apply_smart_defaults` before the Q-banner: display order
    # (Q4 already implies it), master timing language (first lang
    # wins), cleanup preset (always on for learners), output format
    # (VTT when reading aids, else SRT), output folder
    # (~/Downloads/GetSubtitle for URL/title, source's parent for local paths).
    ("steps",         _wizard_q0_steps),
    ("source",        _wizard_q1_source),
    ("scope",         _wizard_q5_scope),
    ("filename_numbering", _wizard_q5_filename_numbering),
    ("languages",     _wizard_q2_languages),
    ("translate",     _wizard_q6_translate),
    ("reading_aids",  _wizard_q7_reading_aids),
    ("rename",        _wizard_q_rename),
]


def _wizard_apply_smart_defaults(state: _WizardState) -> dict[str, str]:
    """Fill in the five answers the wizard no longer asks. Returns a
    dict of {label: human-readable value} for the banner to surface so
    users see what was decided (and can revise via the Edit action by
    re-running the wizard or hand-tweaking the saved workflow file)."""
    notes: dict[str, str] = {}
    # Display order = the order languages were typed at Q4.
    if "merge" in state.steps and len(state.languages) >= 2 and not state.order:
        state.order = list(state.languages)
        notes["Display order"] = ", ".join(state.order) + "  (top → bottom on screen)"
    elif "merge" in state.steps and not state.order:
        state.order = list(state.languages)
    # Master timing language: blank means 'first lang in order wins'.
    # That's the right answer for nearly every merge.
    if "merge" in state.steps and len(state.order) >= 2 and not state.master:
        notes["Timing master"] = f"{state.order[0]}  (first language)"
    # Cleanup preset: single-line cues + strip broadcast noise. Universal
    # win for learners and works in every player.
    if state.steps & {"modify", "merge"} and not state.asbplayer:
        state.asbplayer = True
        notes["Cleanup preset"] = "on  (single-line cues + strip broadcast noise)"
    # Output format: VTT when reading aids are requested (so ruby
    # renders), else SRT (most compatible).
    if "merge" in state.steps and not state.format:
        needs_ruby = any(
            spec.startswith(("ja:hiragana", "ja:furigana"))
            for spec in state.reading_aids
        )
        state.format = "vtt" if needs_ruby else "srt"
        notes["Output format"] = (
            f"{state.format.upper()}  ("
            + ("VTT renders reading aids as ruby"
               if needs_ruby
               else "SRT — most compatible")
            + ")"
        )
    # Output folder: URL/title sources land in ~/Downloads/GetSubtitle by
    # default; local-path sources land beside the source file/folder.
    if not state.output:
        if state.source_kind in ("url", "title"):
            state.output = DEFAULT_OUTPUT_TEXT
            notes["Output folder"] = state.output
        elif state.source_kind == "path" and state.source:
            from pathlib import Path as _P
            src = _P(state.source).expanduser()
            target = src if src.is_dir() else src.parent
            state.output = str(target)
            notes["Output folder"] = state.output + "  (beside source)"
    return notes


def _wizard_step_skip(label: str, state: _WizardState) -> bool:
    if "rename" in state.steps:
        return label != "rename" and label not in {"steps", "source"}
    skip = {
        "scope":        "fetch" not in state.steps,
        "rename":       True,
        "filename_numbering": not _wizard_should_ask_filename_numbering(state),
        "translate":    "translate" not in state.steps,
        "reading_aids": "modify" not in state.steps,
    }
    return skip.get(label, False)


def _wizard_step_prefilled(label: str, state: _WizardState) -> bool:
    prefilled = {
        "languages": bool(state.languages),
        "filename_numbering": bool(state.episode_filename_start),
        "translate": state.mt_engine != "",
        "reading_aids": bool(state.reading_aids),
    }
    return prefilled.get(label, False)


def _wizard_clear_step_answer(state: _WizardState, label: str) -> None:
    """Clear the answer owned by one wizard step before re-asking it."""
    if label == "steps":
        state.steps = {"fetch", "modify", "merge"}
        state.convert_smi = False
    elif label == "source":
        state.source = ""
        state.source_title = ""
        state.source_kind = ""
        state.is_movie = False
        state.convert_smi = False
        state.season = ""
        state.episode = ""
        state.episode_filename_start = ""
        state.output = ""
    elif label == "languages":
        state.languages = []
        state.order = []
        state.master = ""
        state.reading_aids = []
        state.format = ""
    elif label == "scope":
        state.season = ""
        state.episode = ""
        state.episode_filename_start = ""
    elif label == "filename_numbering":
        state.episode_filename_start = ""
    elif label == "translate":
        state.mt_engine = ""
    elif label == "reading_aids":
        state.reading_aids = []
        state.format = ""
    if hasattr(state, "_smart_defaults_notes"):
        state._smart_defaults_notes = {}


def _run_wizard(state: _WizardState | None = None) -> tuple[_WizardState, str]:
    """Run Q1-Q11, then loop on Q12 until a final action is chosen.
    Returns (state, final_action). Caller owns dispatching the action.

    Pre-filled state (from a setup profile, say) short-circuits the
    matching question — we don't ask Q3 if `state.languages` is already
    populated. The user can still revisit any answer via Q12's edit loop."""
    state = state or _WizardState()
    previous_back_nav = _wizard_back_nav_active()
    globals()["_WIZARD_BACK_NAV_ACTIVE"] = True
    try:
        return _run_wizard_with_back_nav(state)
    finally:
        globals()["_WIZARD_BACK_NAV_ACTIVE"] = previous_back_nav


def _run_wizard_with_back_nav(state: _WizardState) -> tuple[_WizardState, str]:
    """Implementation for _run_wizard while prompt-level back navigation is active."""
    # Reset the contiguous question counter for this forward pass so the
    # printed headings number 1..N with no gaps (see _wizard_next_q).
    state._qcount = 0
    step_index = 0
    visible_history: list[str] = []
    while step_index < len(_WIZARD_STEPS):
        label, fn = _WIZARD_STEPS[step_index]
        # Step gating: skip Qs whose verb isn't in state.steps.
        if _wizard_step_skip(label, state):
            step_index += 1
            continue
        # Skip pre-answered questions so resume / setup-profile pre-fill
        # actually saves keystrokes.
        if _wizard_step_prefilled(label, state):
            step_index += 1
            continue
        try:
            fn(state)
        except _WizardBack:
            if not visible_history:
                print("    Already at the first step.")
                state._qcount = _wizard_qcount_before(state, label)
                continue
            previous_label = visible_history.pop()
            _wizard_clear_step_answer(state, previous_label)
            step_index = next(
                (i for i, (candidate, _fn) in enumerate(_WIZARD_STEPS)
                 if candidate == previous_label),
                0,
            )
            state._qcount = _wizard_qcount_before(state, previous_label)
            print("    Going back to the previous step.")
            continue
        _wizard_save_draft(state)
        visible_history.append(label)
        step_index += 1
    if state.steps == {"rename"}:
        state.final_action = "rename_done"
        return state, "rename_done"
    # Five questions the wizard no longer asks (display order, master
    # timing, cleanup preset, output format, output folder) are now
    # filled in here. The returned notes are surfaced in the Q-banner
    # so users see what was decided.
    state._smart_defaults_notes = _wizard_apply_smart_defaults(state)
    _wizard_save_draft(state)
    while True:
        try:
            action = _wizard_q11_action(state)
        except _WizardBack:
            if not visible_history:
                print("    Already at the first step.")
                continue
            previous_label = visible_history.pop()
            _wizard_clear_step_answer(state, previous_label)
            step_index = next(
                (i for i, (candidate, _fn) in enumerate(_WIZARD_STEPS)
                 if candidate == previous_label),
                0,
            )
            state._qcount = _wizard_qcount_before(state, previous_label)
            print("    Going back to the previous step.")
            while step_index < len(_WIZARD_STEPS):
                label, fn = _WIZARD_STEPS[step_index]
                if _wizard_step_skip(label, state) or _wizard_step_prefilled(label, state):
                    step_index += 1
                    continue
                try:
                    fn(state)
                except _WizardBack:
                    if not visible_history:
                        print("    Already at the first step.")
                        state._qcount = _wizard_qcount_before(state, label)
                        continue
                    previous_label = visible_history.pop()
                    _wizard_clear_step_answer(state, previous_label)
                    step_index = next(
                        (i for i, (candidate, _fn) in enumerate(_WIZARD_STEPS)
                         if candidate == previous_label),
                        0,
                    )
                    state._qcount = _wizard_qcount_before(state, previous_label)
                    print("    Going back to the previous step.")
                    continue
                _wizard_save_draft(state)
                visible_history.append(label)
                step_index += 1
            state._smart_defaults_notes = _wizard_apply_smart_defaults(state)
            _wizard_save_draft(state)
            continue
        if action == "restart":
            # Confirm — 10+ answers is a lot to throw away by mistyping 'd'.
            if not _wizard_yesno(
                "Discard all answers and start over?", default=False
            ):
                # Loop back to the action menu without leaving _run_wizard.
                continue
            state.final_action = action
            return state, action
        if action != "edit":
            state.final_action = action
            return state, action
        # Edit flow: list answers, jump to specific question.
        print()
        print("Your answers so far:")
        print(f"  Q1. source type: {state.source_kind!r}")
        print(f"  Q2. source: {state.source!r}")
        visible_labels = [
            ("languages", state.languages),
            ("order", state.order),
            ("master", state.master),
            ("scope", {"season": state.season, "episode": state.episode}),
            ("translate", state.mt_engine),
            ("reading_aids", state.reading_aids),
            ("asbplayer", state.asbplayer),
            ("format", state.format),
            ("output", state.output),
        ]
        for i, (label, value) in enumerate(visible_labels, start=3):
            print(f"  Q{i}. {label}: {value!r}")
        pick = _wizard_prompt("Question number to redo (1-11), or 'done'", "done").lower()
        if pick.isdigit():
            visible = int(pick)
            idx = 0 if visible in (1, 2) else visible - 2
            if 0 <= idx < len(_WIZARD_STEPS):
                edit_label = _WIZARD_STEPS[idx][0]
                if edit_label == "scope":
                    state.season = ""
                    state.episode = ""
                # Prime the counter so the re-asked heading keeps the
                # number it had during the forward pass.
                state._qcount = _wizard_qcount_before(state, edit_label)
                _WIZARD_STEPS[idx][1](state)
                _wizard_save_draft(state)


# ─── Emitters: CLI command + TOML workflow ────────────────────────────

def _wizard_emit_cli(state: _WizardState) -> list[str]:
    """Build a canonical-form argv list for the wizard's answers.

    Uses the canonical long names: --languages, --engine, --mt-source,
    --reading (NOT --furigana). Honors state.steps so modify-only /
    merge-only / translate-only paths emit a focused command without
    --fetch noise or unwanted verbs."""
    steps = state.steps or {"fetch", "modify", "merge"}
    local_steps = steps - {"fetch"}
    local_episode_filter = "fetch" not in steps and bool(state.season or state.episode)

    def add_local_episode_filter(argv: list[str]) -> None:
        if not local_episode_filter:
            return
        if state.season:
            argv += ["--season", state.season]
        if state.episode:
            argv += ["--episode", state.episode]

    def merge_order() -> list[str]:
        order = list(state.order)
        for lang in list(state.order):
            modes = [
                spec.split(":", 1)[1]
                for spec in state.reading_aids
                if spec.startswith(f"{lang}:")
            ]
            if len(modes) <= 1 or lang not in order:
                continue
            variants = [f"{lang}-{mode}" for mode in modes if is_pseudo_lang(f"{lang}-{mode}")]
            if variants:
                idx = order.index(lang)
                order[idx:idx] = variants
        return order

    # Local-only, single-verb workflows should use the ordinary subcommands
    # instead of the pipeline flags. `getsubtitle PATH --merge` is parsed as
    # a pipeline and rejects the positional PATH before any verb; the
    # subcommand form is what users expect and what argparse supports.
    if "fetch" not in steps and local_steps == {"modify"}:
        argv: list[str] = ["getsubtitle", "modify", state.source]
        add_local_episode_filter(argv)
        if state.convert_smi:
            argv += ["--convert", "smi-to-srt"]
        if state.asbplayer:
            argv += ["--strip-cc-noise", "--single-line"]
        if state.reading_aids:
            argv += ["--reading", ",".join(state.reading_aids)]
            if state.format == "vtt":
                argv += ["--reading-format", "vtt"]
        return argv

    if "fetch" not in steps and local_steps == {"merge"}:
        argv = ["getsubtitle", "merge", state.source]
        add_local_episode_filter(argv)
        order = merge_order()
        if len(order) >= 2:
            argv += ["--languages", ",".join(order)]
        if state.master:
            argv += ["--master", state.master]
        if state.format:
            argv += ["--format", state.format]
        if state.output:
            argv += ["--output", state.output]
        return argv

    if "fetch" not in steps and local_steps == {"translate"}:
        argv = ["getsubtitle", "translate", state.source]
        if state.languages:
            argv += ["--languages", ",".join(state.languages)]
        if state.mt_engine:
            argv += ["--engine", state.mt_engine]
        if state.output:
            argv += ["--output", state.output]
        return argv

    argv = ["getsubtitle"]
    # Source. With fetch in steps, emit --fetch and (for URL/title) the
    # season/episode slicing. Without fetch, the source path is the
    # input for modify/merge/translate and is carried by --source.
    if "fetch" in steps:
        if state.source_kind == "title":
            argv += ["--fetch", "--title", state.source]
        else:
            argv += ["--fetch", state.source]
            if state.source_title:
                argv += ["--title", state.source_title]
        if state.source_kind in ("url", "title") and state.season:
            argv += ["--season", state.season]
        if state.source_kind in ("url", "title") and state.episode:
            argv += ["--episode", state.episode]
        if state.source_kind in ("url", "title") and state.episode_filename_start:
            argv += ["--episode-filename-start", state.episode_filename_start]
    else:
        argv += ["--source", state.source]
    if state.languages and "fetch" in steps:
        argv += ["--languages", ",".join(state.languages)]
    # Translate verb. --translate ENGINE is the canonical form when MT
    # is requested; --no-engine is the explicit opt-out when fetch is
    # selected without translate.
    if "translate" in steps and state.mt_engine:
        argv += ["--translate", state.mt_engine]
        if "fetch" not in steps and state.languages:
            argv += ["--languages", ",".join(state.languages)]
    elif "fetch" in steps and state.source_kind in ("url", "title"):
        argv.append("--no-engine")
    # Modify block.
    if "modify" in steps and (state.reading_aids or state.asbplayer or state.convert_smi):
        argv.append("--modify")
        add_local_episode_filter(argv)
        if state.convert_smi:
            argv += ["--convert", "smi-to-srt"]
        if state.asbplayer:
            argv += ["--strip-cc-noise", "--single-line"]
        if state.reading_aids:
            argv += ["--reading", ",".join(state.reading_aids)]
            if state.format == "vtt":
                argv += ["--reading-format", "vtt"]
    # Merge block — only when 2+ languages.
    if "merge" in steps and len(state.order) >= 2:
        argv += ["--merge", "--languages", ",".join(merge_order())]
        add_local_episode_filter(argv)
        merge_reading = _wizard_merge_inline_reading_spec(state)
        if merge_reading:
            argv += ["--reading", merge_reading]
        if state.master:
            argv += ["--master", state.master]
        if state.format:
            argv += ["--format", state.format]
    if state.output:
        argv += ["--output", state.output]
    return argv


def _wizard_emit_cli_string(state: _WizardState) -> str:
    """Shell-safe one-liner. Uses shlex.quote for paths-with-spaces etc."""
    import shlex
    parts = _wizard_emit_cli(state)
    return " ".join(shlex.quote(p) if (" " in p or any(c in p for c in "$&|'\"")) else p for p in parts)


def _wizard_collect_variant_files(state: _WizardState, target: Path) -> list[Path]:
    """Find intermediate reading-aid variant files in `target` that the
    just-finished wizard run generated as merge inputs. Used by the
    post-run cleanup prompt so users aren't left with five files when
    they only wanted the merged one."""
    if not target.exists() or not target.is_dir():
        return []
    pseudo_langs = [lang for lang in state.order if is_pseudo_lang(lang)]
    if not pseudo_langs:
        return []
    out: list[Path] = []
    for pseudo in pseudo_langs:
        pattern = _variant_filename_pattern(pseudo)
        if pattern is None:
            continue
        for path in sorted(target.rglob("*.*")):
            if pattern.search(path.name):
                out.append(path)
    # Deduplicate (a path could match multiple patterns) while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _wizard_open_folder_target(state: _WizardState) -> Path | None:
    if not state.output:
        return None
    target = Path(state.output).expanduser()
    if "fetch" not in state.steps:
        return target
    try:
        blocks = split_pipeline_argv(_wizard_emit_cli(state)[1:])
        fetch_target, fetch_options = _pipeline_resolve_target(blocks.get("fetch", []))
        if fetch_target and _looks_like_url(fetch_target):
            guessed = _pipeline_url_fetch_output_target(fetch_target, fetch_options, state.output)
            resolved = _pipeline_existing_fetch_output_target(
                guessed,
                output_root=state.output,
                fetch_options=fetch_options,
            )
            if resolved:
                return Path(resolved).expanduser()
    except CliError:
        pass
    return target


def _wizard_merge_order(state: _WizardState) -> list[str]:
    order = list(state.order)
    for lang in list(state.order):
        modes = [
            spec.split(":", 1)[1]
            for spec in state.reading_aids
            if spec.startswith(f"{lang}:")
        ]
        if len(modes) <= 1 or lang not in order:
            continue
        variants = [f"{lang}-{mode}" for mode in modes if is_pseudo_lang(f"{lang}-{mode}")]
        if variants:
            idx = order.index(lang)
            order[idx:idx] = variants
    return order


def _wizard_merge_inline_reading_spec(state: _WizardState) -> str | None:
    return _single_japanese_reading_spec(state.reading_aids)


def _wizard_emit_toml(state: _WizardState) -> str:
    """Build a workflow TOML matching --config FILE.toml schema. Sections
    are only emitted for the verbs the user actually picked at Q1, so a
    merge-only workflow stays terse instead of carrying [fetch]/[translate]
    boilerplate."""
    lines: list[str] = []
    steps = state.steps or {"fetch", "modify", "merge"}
    local_episode_filter = "fetch" not in steps and bool(state.season or state.episode)
    if "fetch" in steps:
        lines.append("[fetch]")
        if state.source_kind == "title":
            lines.append(f'title = "{state.source}"')
        else:
            lines.append(f'source = "{state.source}"')
            if state.source_title:
                lines.append(f'title = "{state.source_title}"')
        if state.source_kind in ("url", "title"):
            if state.season:
                lines.append(f'season = "{state.season}"')
            if state.episode:
                lines.append(f'episode = "{state.episode}"')
            if state.episode_filename_start:
                lines.append(f'episode_filename_start = "{state.episode_filename_start}"')
        if state.languages:
            lines.append(f'languages = "{",".join(state.languages)}"')
        if not state.mt_engine and state.source_kind in ("url", "title"):
            lines.append("no_engine = true")
        lines.append("")
    # [translate]
    if "translate" in steps and state.mt_engine:
        lines.append("[translate]")
        lines.append(f'engine = "{state.mt_engine}"')
        if "fetch" not in steps and state.languages:
            lines.append(f'languages = "{",".join(state.languages)}"')
        lines.append('mt_source = "auto"')
        lines.append("")
    # [modify]
    has_modify = "modify" in steps and bool(state.reading_aids or state.asbplayer or state.convert_smi)
    if has_modify:
        lines.append("[modify]")
        if local_episode_filter:
            if state.season:
                lines.append(f'season = "{state.season}"')
            if state.episode:
                lines.append(f'episode = "{state.episode}"')
        if state.convert_smi:
            lines.append('convert = "smi-to-srt"')
        if state.asbplayer:
            lines.append("single_line = true")
            lines.append("strip_cc_noise = true")
        if state.reading_aids:
            lines.append(f'reading = "{",".join(state.reading_aids)}"')
            if state.format == "vtt":
                lines.append('reading_format = "vtt"')
        lines.append("")
    # [merge]
    if "merge" in steps and len(state.order) >= 2:
        lines.append("[merge]")
        lines.append(f'languages = "{",".join(_wizard_merge_order(state))}"')
        if local_episode_filter:
            if state.season:
                lines.append(f'season = "{state.season}"')
            if state.episode:
                lines.append(f'episode = "{state.episode}"')
        merge_reading = _wizard_merge_inline_reading_spec(state)
        if merge_reading:
            lines.append(f'reading = "{merge_reading}"')
        if state.master:
            lines.append(f'priority = ["{state.master}"]')
        lines.append('sync = "auto"')
        if state.format:
            lines.append(f'format = "{state.format}"')
        lines.append("")
    # [output]. For local-only workflows, target carries the input folder
    # used by modify/merge/translate. This mirrors `--source PATH` in the
    # CLI form and avoids adding a misleading [fetch] section.
    local_only = "fetch" not in steps
    output_target = state.output or (state.source if local_only else "")
    if output_target:
        lines.append("[output]")
        lines.append(f'target = "{output_target}"')
        lines.append('layout = "archive"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _wizard_print_saved_workflow_next_steps(path_raw: str, path: Path, cli_string: str) -> None:
    """Explain how to re-run and reuse a saved workflow TOML."""
    config_arg = shlex.quote(path_raw)
    print(f"Your {path.name} runs the same workflow as this command:")
    print("  # " + cli_string)
    print()
    print("Run it later with:")
    print(f"  getsubtitle --config {config_arg}")
    print()
    print("You can recycle this TOML and override saved settings with extra CLI flags.")
    print("For example, reuse the same language, reading-aid, translation, and merge")
    print("choices on another show or season:")
    print(
        f"  getsubtitle --config {config_arg} "
        "--source 'https://www.imdb.com/title/tt1234567/' "
        "--season 3 --episode all "
        '--output "$HOME/Downloads/GetSubtitle/TV Show/Season 03"'
    )
    print()
    print("CLI flags win over matching TOML settings, so the file can stay as a reusable template.")


def _wizard_offer_open_saved_workflow_folder(path: Path) -> None:
    """Offer to open the folder containing a saved workflow file."""
    folder = path.expanduser().parent
    try:
        folder = folder.resolve()
    except OSError:
        folder = folder.expanduser()
    if _wizard_yesno(f"Open folder containing {path.name}?", default=True):
        try:
            open_folder(folder)
        except Exception as e:
            print(f"  (could not open folder: {e})")


# ─── Dependency probe + auto-setup ─────────────────────────────────────

def _wizard_probe_dependencies(state: _WizardState) -> list[tuple[str, str, str]]:
    """Inspect the wizard answers and return a list of unmet requirements.

    Each row: (severity, label, fix_hint). severity is "block" (the
    chosen action will fail without it) or "warn" (might fail at run
    time but isn't fatal upfront)."""
    out: list[tuple[str, str, str]] = []

    # Reading aids → pykakasi for Japanese.
    needs_pykakasi = any(s.startswith("ja:") for s in state.reading_aids)
    if needs_pykakasi:
        try:
            import pykakasi  # noqa: F401
        except ImportError:
            out.append(("block", "pykakasi (Japanese reading aids)",
                        'pip install -e ".[furigana]"  # or: pip install pykakasi'))
    # Korean Revised Romanization needs korean-romanizer (hard) + g2pk (soft).
    # Yale is in-tree so we don't probe deps for ko:yale.
    needs_ko_revised = any(
        s.startswith("ko:") and not s.startswith("ko:yale") for s in state.reading_aids
    )
    if needs_ko_revised:
        try:
            import korean_romanizer  # noqa: F401
        except ImportError:
            out.append(("block", "korean-romanizer (Korean Revised Romanization)",
                        'pip install -e ".[romanization-ko]"  # also installs g2pk'))
        else:
            try:
                import g2pk  # noqa: F401
            except ImportError:
                out.append(("warn", "g2pk (Korean G2P preprocessing)",
                            "pip install g2pk — improves 같이→가치 / 읽는→잉는 accuracy"))
    # Mandarin pinyin needs pypinyin.
    needs_zh = any(s.startswith("zh:") for s in state.reading_aids)
    if needs_zh:
        try:
            import pypinyin  # noqa: F401
        except ImportError:
            out.append(("block", "pypinyin (Mandarin pinyin)",
                        'pip install -e ".[romanization-zh]"  # or: pip install pypinyin'))
    # Cantonese Jyutping needs PyCantonese.
    needs_yue = any(s.startswith("yue:") for s in state.reading_aids)
    if needs_yue:
        try:
            import pycantonese  # noqa: F401
        except ImportError:
            out.append(("block", "pycantonese (Cantonese Jyutping)",
                        'pip install -e ".[romanization-yue]"  # or: pip install pycantonese'))
    # Other reading-aid backends — still not shipped.
    deferred = [
        s for s in state.reading_aids
        if not s.startswith("ja:")
        and not s.startswith("ko:")
        and not s.startswith("zh:")
        and not s.startswith("yue:")
    ]
    if deferred:
        out.append(("warn",
                    f"reading-aid backend(s) for {', '.join(deferred)}",
                    "backend not yet implemented; will warn at run time. TOML still saves cleanly."))
    # MT engines.
    if state.mt_engine == "argos":
        try:
            import argostranslate  # noqa: F401
        except ImportError:
            out.append(("block", "argostranslate (offline MT)",
                        "pip install argostranslate"))
    if state.mt_engine == "ollama":
        if not _wizard_ollama_reachable():
            out.append(("block", "Ollama daemon at http://localhost:11434",
                        "Start Ollama: https://ollama.com  (then re-run)"))
    if state.mt_engine == "deepl":
        if not get_provider_api_key("deepl"):
            out.append(("block", "DeepL API key", "getsubtitle --set-key deepl"))
    # Subtitle providers (URL source only).
    if state.source_kind in ("url", "title"):
        wants_ja = "ja" in state.languages
        if wants_ja and not get_provider_api_key("jimaku"):
            out.append(("warn", "Jimaku API key (Japanese anime)",
                        "getsubtitle --set-key jimaku"))
        wants_non_ja = any(lang != "ja" for lang in state.languages)
        if wants_non_ja and not get_provider_api_key("wyzie"):
            out.append(("warn", "Wyzie API key (movies / non-anime TV)",
                        "getsubtitle --set-key wyzie"))
        if state.episode == "all" and not get_provider_api_key("tmdb") and (
           state.source_kind == "title"
           or (
               "anilist" not in state.source.lower()
               and "myanimelist" not in state.source.lower()
           )
        ):
            out.append(("block", "TMDB API key for `-e all` on non-anime TV",
                        "getsubtitle --set-key tmdb"))
    return out


def _wizard_ollama_reachable() -> bool:
    """Quick health-check against the local Ollama daemon. 1-second
    timeout — we don't want the wizard to hang waiting on a dead port."""
    try:
        import urllib.request as _ur
        req = _ur.Request("http://localhost:11434/api/tags", method="GET")
        with _ur.urlopen(req, timeout=1) as resp:  # noqa: S310 — localhost only
            return 200 <= resp.status < 300
    except Exception:
        return False


def _wizard_run_setup(state: _WizardState, gaps: list[tuple[str, str, str]]) -> None:
    """Walk the user through fixing each gap. Three options per gap:
    run the suggested fix, skip, or quit setup. We don't shell out to
    pip without consent — too easy to install the wrong thing into the
    wrong environment."""
    print()
    print("Setup — let's fill in the missing pieces.")
    print()
    for severity, label, fix in gaps:
        marker = "✗" if severity == "block" else "•"
        print(f"  {marker} {label}")
        print(f"      Suggested fix: {fix}")
        if fix.startswith("getsubtitle --set-key "):
            provider = fix.split()[-1]
            if _wizard_yesno(f"    Run `--set-key {provider}` now?", default=True):
                rc = set_api_keys(provider)
                if rc == 0:
                    print("    ✓ key saved")
        elif fix.startswith("pip install"):
            print("    (Run this in your shell, then re-launch the wizard.)")
        else:
            print("    (Manual step — re-launch the wizard once done.)")
        print()


def _wizard_dependency_check_before_run(state: _WizardState) -> str:
    """Return the action to take after dependency probing.

    `run` means all blockers are resolved or only warnings remain. `save`
    means the user tried or skipped setup but required pieces are still
    missing, so the safe path is to save the workflow instead of dispatching
    a doomed run. `quit` exits without running.
    """
    gaps = _wizard_probe_dependencies(state)
    if not gaps:
        return "run"

    print()
    print("Dependency check — issues found:")
    for sev, label, fix in gaps:
        marker = "✗ block" if sev == "block" else "• warn "
        print(f"  {marker}  {label}")
    blockers = [g for g in gaps if g[0] == "block"]
    if not blockers:
        return "run"

    if _wizard_yesno("Run setup now to fix these?", default=True):
        _wizard_run_setup(state, gaps)

    remaining = [g for g in _wizard_probe_dependencies(state) if g[0] == "block"]
    if not remaining:
        return "run"

    print()
    print("Still missing required setup:")
    for _sev, label, fix in remaining:
        print(f"  - {label}: {fix}")
    print("Not running yet, because this workflow would fail before it starts.")
    if _wizard_yesno("Save the workflow instead so you can run it after setup?", default=True):
        return "save"
    return "quit"


# ─── Entry point ───────────────────────────────────────────────────────

_WIZARD_INTRO = """
getsubtitle — interactive workflow builder

I'll ask a few short questions, then show you the equivalent terminal
command and a reusable workflow file. You can save the workflow for
later, run it now, or edit a single answer. Type 'b' to go back,
'q' to quit, or Ctrl-C to bail.
"""


def interactive_main(argv: list[str] | None = None) -> int:
    """Run the wizard. Returns a shell-style exit code.
    `argv` is accepted (and ignored) so it slots into the same dispatch
    shape as the other *_main functions."""
    if not _wizard_is_interactive():
        raise CliError(
            "interactive mode needs an attached terminal "
            "(stdin / stdout must be a tty). Use --config FILE.toml for unattended runs."
        )
    print(_WIZARD_INTRO)
    setup_profile = _setup_load_profile()
    use_setup_profile = False
    if setup_profile is not None:
        use_setup_profile = _wizard_yesno(
            "Found your setup profile. Pre-fill Q2 (languages) / Q6 (MT engine) / "
            "Q7 (reading aids) / Q9 (format) from it?",
            default=True,
        )

    while True:
        state = _WizardState()
        if setup_profile is not None and use_setup_profile:
            state.languages = list(setup_profile.learning + [
                lang for lang in setup_profile.native
                if lang not in setup_profile.learning
            ])
            state.order = list(state.languages)
            state.mt_engine = {"online": "deepl", "offline": "argos", "none": ""}.get(
                setup_profile.mt, ""
            )
            state.reading_aids = [
                _SETUP_READING_AID_BY_LANG[lang][0]
                for lang in setup_profile.learning
                if lang in _SETUP_READING_AID_BY_LANG
            ]
            if setup_profile.venue == "browser" and any(
                s.startswith("ja:") for s in state.reading_aids
            ):
                state.format = "vtt"
                state.asbplayer = True
            print(
                f"  Loaded: languages={','.join(state.languages)}, "
                f"mt={state.mt_engine or '(none)'}, "
                f"reading_aids={','.join(state.reading_aids) or '(none)'}."
            )

        try:
            state, action = _run_wizard(state)
        except _WizardAbort:
            print()
            if _wizard_has_recoverable_draft(state):
                _wizard_save_draft(state)
                print("Cancelled. (Your answers are saved at " + str(_wizard_draft_path()) + ".)")
            else:
                _wizard_clear_draft()
                print("Cancelled.")
            return 130

        if action == "restart":
            _wizard_clear_draft()
            print()
            print("════════════════════════════════════════")
            print(_WIZARD_INTRO.strip())
            print("════════════════════════════════════════")
            continue
        if action == "rename_done":
            _wizard_clear_draft()
            return 0
        if action == "quit":
            _wizard_clear_draft()
            print("Quit.")
            return 0

        # Probe dependencies only for the 'run' action. Save can be cross-
        # machine — don't nag a user generating a TOML for a different box.
        if action == "run":
            action = _wizard_dependency_check_before_run(state)
            if action == "quit":
                _wizard_clear_draft()
                print("Quit.")
                return 0

        cli_string = _wizard_emit_cli_string(state)
        toml_str = _wizard_emit_toml(state)

        if action == "save":
            print()
            default_name = "getsubtitle-workflow.toml"
            # Loop the filename prompt so "no, don't overwrite" lets the user
            # pick a different name instead of dropping out of the wizard.
            while True:
                path_raw = _wizard_prompt("Save to (relative paths OK)", default_name)
                path = Path(path_raw).expanduser()
                if path.exists():
                    if not _wizard_yesno(f"{path} exists. Overwrite?", default=False):
                        print("  Pick a different filename, or 'q' to cancel.")
                        continue
                break
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(toml_str, encoding="utf-8")
            print(f"Saved: {path}")
            print()
            _wizard_print_saved_workflow_next_steps(path_raw, path, cli_string)
            print()
            _wizard_offer_open_saved_workflow_folder(path)
            _wizard_clear_draft()
            return 0

        if action == "run":
            # User picked Run explicitly at Q11 — that IS the confirmation.
            # Drop the redundant 'Proceed?' prompt and just show what's
            # running so the log makes sense if it scrolls off the banner.
            #
            # Deferred reading-aid backends (yue, th, ar, hi, ru) crash
            # the modify step at runtime. Strip them BEFORE dispatching
            # so the rest of the pipeline (fetch + merge + ja/ko/zh
            # readings) still succeeds. Save flow keeps them so the
            # generated TOML works once the backend ships.
            shipped = {"ja", "ko", "zh", "yue"}
            deferred = [s for s in state.reading_aids
                        if s.split(":", 1)[0] not in shipped]
            run_state = state
            if deferred:
                from dataclasses import replace as _dc_replace
                run_state = _dc_replace(state, reading_aids=[
                    s for s in state.reading_aids
                    if s.split(":", 1)[0] in shipped
                ])
                print("Note: dropping reading-aid(s) without a shipped backend:")
                print(f"  {', '.join(deferred)}")
                print("  (Saved TOML keeps these so the workflow runs once the")
                print("   backend ships. See ROADMAP.md.)")
                cli_string = _wizard_emit_cli_string(run_state)
            print()
            print("Running:")
            print("  " + cli_string)
            print()
            _wizard_clear_draft()
            # Inject --no-open-folder-prompt so the merge/fetch subcommands
            # don't ask "Open folder?" mid-run; the wizard handles a single
            # post-run prompt below. Without this the user sees the prompt
            # twice (merge_main asks, then the wizard asks again).
            dispatch_argv = _wizard_emit_cli(run_state)[1:]
            if "--no-open-folder-prompt" not in dispatch_argv:
                dispatch_argv.append("--no-open-folder-prompt")
            rc = main(dispatch_argv)
            # Post-run cleanup + folder opener. Skipped silently on a
            # failed run so we don't act on a half-finished output.
            if rc == 0 and state.output:
                try:
                    target = _wizard_open_folder_target(run_state) or Path(state.output).expanduser()
                    # Multi-variant merge leaves intermediate
                    # `.furigana-*.vtt` / `.romanization-*.vtt` files
                    # alongside the merged output. Most wizard users want
                    # the merged file only; offer to delete the variants.
                    variants = _wizard_collect_variant_files(run_state, target)
                    if variants:
                        print()
                        print(
                            f"Merge consumed {len(variants)} intermediate variant file(s):"
                        )
                        # Truncate long lists so the prompt stays scannable.
                        for v in variants[:6]:
                            print(f"  {v.name}")
                        if len(variants) > 6:
                            print(f"  … and {len(variants) - 6} more")
                        print(
                            "The merged file already contains all of these."
                        )
                        if _wizard_yesno(
                            "Delete the intermediate variant files?", default=True
                        ):
                            removed = 0
                            for v in variants:
                                try:
                                    v.unlink()
                                    removed += 1
                                except OSError as e:
                                    print(f"  (could not delete {v.name}: {e})")
                            print(f"Deleted {removed} variant file(s).")
                    if target.exists() and _wizard_yesno("Open folder?", default=True):
                        try:
                            open_folder(target)
                        except CliError as e:
                            print(f"  (could not open folder: {e})")
                except _WizardAbort:
                    pass
            return rc


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    # No args -> short main help. Friendlier than the old "Missing URL" error.
    if not raw_argv:
        sys.stdout.write(HELP_MAIN)
        return 0
    # Interactive wizard — both flag form (-i / --interactive) and
    # subcommand form (`getsubtitle interactive`) route here.
    if raw_argv[0] in ("interactive",) or raw_argv[0] in ("-i", "--interactive"):
        # Strip the trigger so interactive_main sees clean argv.
        return interactive_main(raw_argv[1:])
    if raw_argv[0] == "setup":
        return setup_main(raw_argv[1:])
    if raw_argv[0] == "doctor":
        return doctor_main(raw_argv[1:])
    if raw_argv[0] == "run":
        return run_main(raw_argv[1:])
    # Topic-help dispatch — handled before argparse so we own the help UX.
    if _is_topic_help_request(raw_argv):
        return _show_topic_help(raw_argv)
    # --config FILE.toml form (anywhere in argv): load TOML, layer CLI
    # overrides on top, run pipeline. Takes precedence over inline pipeline
    # form because the user has chosen to source the workflow from a file.
    config_path = _extract_config_flag(raw_argv)
    if config_path is not None:
        return pipeline_from_config_main(config_path, raw_argv)
    # Inline pipeline form (--fetch / --translate / --modify / --merge).
    if _is_pipeline_argv(raw_argv):
        return pipeline_main(raw_argv)
    # Subcommand dispatch — sniff the first positional. The bare
    # `getsubtitle URL ...` shape (no subcommand) falls through to the
    # URL-form download flow below.
    if raw_argv[0] == "merge":
        return combine_main(raw_argv[1:])
    if raw_argv[0] == "translate":
        return translate_main(raw_argv[1:])
    if raw_argv[0] == "modify":
        return modify_main(raw_argv[1:])
    if raw_argv[0] == "fetch":
        return fetch_main(raw_argv[1:])
    if raw_argv[0] == "config":
        return config_main(raw_argv[1:])
    if raw_argv[0] == "sources":
        return sources_main(raw_argv[1:])
    # URL-form season-range expansion: `--season 1-2` / `-s 1,2,3` →
    # run the URL flow once per expanded season.
    expanded_seasons = _expand_url_form_season_range(raw_argv)
    if expanded_seasons is not None:
        rc_total = 0
        for idx, sub_argv in enumerate(expanded_seasons, start=1):
            if idx > 1:
                print()
            print(f"━━ season {sub_argv[sub_argv.index('--season' if '--season' in sub_argv else '-s') + 1]} ━━")
            rc = main(sub_argv)
            rc_total = rc or rc_total
        return rc_total
    args = build_parser().parse_args(raw_argv)
    # --reading (the generalised reading flag) routes through the legacy
    # --furigana attribute for Japanese; non-Japanese languages raise a
    # clear "not yet implemented" error.
    _apply_reading_to_args(args)
    if args.reset_key is not None:
        return reset_api_keys(args.reset_key or None)
    if args.set_key is not None:
        return set_api_keys(args.set_key or None)
    if args.reset_jimaku_key:
        return reset_api_keys("jimaku")
    if args.set_jimaku_key:
        return set_api_keys("jimaku")
    if not args.url and args.title:
        args.url = title_source_url(args.title)
    if not args.url:
        raise CliError("Missing URL or title. Run getsubtitle --help for usage.")
    if args.browser:
        open_in_browser(args.url)
        if sys.stdin.isatty():
            input("Browser opened. After the page loads or you identify the show, press Enter to continue...")
        else:
            print("Browser opened. Continuing without waiting because stdin is not interactive.")
    if args.episode_filename_start is not None and args.episode_filename_start < 1:
        raise CliError("--episode-filename-start must be a positive integer.")
    langs = split_csv(args.langs, "ja")
    media = infer_media(args.url)
    # User-supplied -s wins; otherwise keep any season the URL inferred
    # (e.g. Crunchyroll "...-season-2" slug → season=2). Same pattern for -e.
    if str(args.season).lower() != "auto":
        media.season = str(args.season).lower()
    elif not media.season or media.season == "auto":
        media.season = "auto"
    if str(args.episode).lower() != "auto":
        media.episode = str(args.episode).lower()
    elif not media.episode or media.episode == "auto":
        media.episode = "auto"
    if args.title:
        media.title = args.title
    # TMDB title → IDs enrichment. Only fires when the user has a TMDB
    # API key configured AND we have a title but no IDs yet. Skipped for
    # Japanese-origin titles when `ja` is requested (preserves AniList
    # path for Jimaku). Pure no-op otherwise.
    enrich_media_from_tmdb(media, langs=langs)
    # If the URL gave us a TVDB ID but no IMDb/TMDB yet (e.g. a /thetvdb.com/
    # series page), use Wikidata to bridge. This lets non-anime TVDB shows
    # reach Wyzie without first being routed through AniList.
    if media.tvdb_id and not (media.imdb_id or media.tmdb_id) and not media.anilist_id:
        enrich_external_ids_from_wikidata(media)
    broad_provider_requested = any(lang != "ja" for lang in langs)
    needs_anilist = not media.anilist_id and not (media.imdb_id or media.tmdb_id) and (
        "ja" in langs or broad_provider_requested or str(args.episode).lower() == "all"
    )
    if args.anilist:
        media.anilist_id = args.anilist
    elif media.anilist_id:
        # Already resolved via URL parsing (e.g. anilist.co/anime/<id>); nothing to do.
        pass
    elif needs_anilist:
        if not media.title:
            print(
                f"Could not infer the show title from this {media.provider} URL. "
                "Type a show title, AniList ID, or AniList URL below — or rerun "
                "with --title / --anilist to skip this prompt."
            )
            media.anilist_id, resolved_title = prompt_for_anilist_id()
            media.title = resolved_title or media.title
        elif args.title:
            media.anilist_id, resolved_title = prompt_for_anilist_id(media.title)
            media.title = resolved_title or media.title
        else:
            media.anilist_id = resolve_anilist_id(media.title)
    elif str(args.episode).lower() == "all" or "ja" in langs:
        bridge_external_ids_to_anilist(media)
        # Anime-IDs DB lookup is sparse for movies and obscure OVAs (no IMDb
        # entry, or no cross-ref to AniList). If ja was explicitly requested
        # and the ID-based bridge didn't land, fall back to AniList title
        # search so Jimaku still has a chance at finding native Japanese subs.
        if not media.anilist_id and "ja" in langs and media.title:
            bridge_external_ids_to_anilist_by_title(media)

    anilist_info = fetch_anilist_info(media.anilist_id) if media.anilist_id else None
    if anilist_info:
        if not media.title or (args.anilist and not args.title):
            media.title = anilist_info.title or media.title
        add_media_title_aliases(media, [anilist_info.title, *(anilist_info.title_aliases or [])])
        # AniList format=MOVIE / single-episode SPECIAL/OVA/ONA flips
        # MediaInfo.is_movie so output_dir + save_subtitle skip the
        # Season Unknown / S00E00 placeholders. Don't downgrade a flag
        # set earlier by URL parsing.
        if not media.is_movie and anilist_info.is_movie():
            media.is_movie = True
    if broad_provider_requested and not (media.imdb_id or media.tmdb_id):
        enrich_media_from_tmdb(
            media,
            langs=[lang for lang in langs if lang != "ja"],
            allow_existing_anilist=True,
            prefer_movie=bool(anilist_info and anilist_info.episodes == 1),
        )
    if any(lang != "ja" for lang in langs):
        bridge_anilist_to_external_ids(media)

    episodes = expand_episodes(media.episode, anilist_info.episodes if anilist_info else None)
    # If `-e all` couldn't be expanded by AniList (anime path) and we have
    # a TMDB ID + a numeric season, ask TMDB for the season's episode count.
    # Unlocks `-e all` for live-action shows without anyone counting by hand.
    if episodes == ["all"] and media.tmdb_id:
        season_str = str(media.season).strip().lower()
        if season_str.isdigit():
            tmdb_count = tmdb_tv_season_episode_count(media.tmdb_id, int(season_str))
            if tmdb_count and tmdb_count > 0:
                episodes = [str(i) for i in range(1, tmdb_count + 1)]
    if episodes == ["all"]:
        raise CliError(
            "Episode count is unknown. Use -e 1-12, -e 1,2,3, pass --anilist "
            "for anime, or set up a TMDB key (getsubtitle --set-key tmdb) "
            "for live-action `-e all` expansion."
        )
    if episodes == ["auto"] and media.episode == "auto":
        episodes = ["auto"]

    print(f"Source: {media.provider}")
    print(f"Title: {media.title or 'unknown'}")
    print(f"Season: {media.season}")
    print(f"Episodes: {', '.join(episodes)}")
    print(f"Languages: {', '.join(langs)}")
    if media.anilist_id:
        print(f"AniList: {media.anilist_id}")
    if media.imdb_id:
        print(f"IMDb: {media.imdb_id}")
    if media.tmdb_id:
        print(f"TMDB: {media.tmdb_id}")
    if media.tvdb_id:
        print(f"TVDB: {media.tvdb_id}")
    if media.mal_id:
        print(f"MAL: {media.mal_id}")
    if media.netflix_id:
        print(f"Netflix: {media.netflix_id}")

    jimaku_provider = (
        JimakuProvider(get_jimaku_api_key())
        if "ja" in langs and (media.anilist_id or media.tmdb_id or media_title_queries(media))
        else None
    )
    subdl_api_key = get_subdl_api_key(prompt_if_missing=False) if (media.imdb_id or media.tmdb_id) else None
    wyzie_api_key = (
        get_provider_api_key("wyzie", prompt_if_missing=not bool(subdl_api_key))
        if (media.imdb_id or media.tmdb_id or broad_provider_requested)
        else None
    )
    wyzie_provider = WyzieProvider(wyzie_api_key) if (media.imdb_id or media.tmdb_id or broad_provider_requested) else None
    subdl_provider = SubDLProvider(subdl_api_key) if subdl_api_key else None
    preferred_release_source = None
    if args.release_source == "any":
        preferred_release_source = None
    elif args.release_source == "auto":
        # Prefer the source URL's host first (covers Hulu/Disney/Apple/etc.
        # via release_source_from_host); fall back to the legacy provider-
        # equals-source check for catalog-site URLs that share a name.
        host = urllib.parse.urlparse(media.source_url or "").netloc
        preferred_release_source = (
            release_source_from_host(host)
            or (media.provider if media.provider in {"netflix", "crunchyroll"} else None)
        )
    else:
        preferred_release_source = args.release_source
    planned: list[tuple[str, str, SubtitleFile]] = []
    search_results: list[SearchResult] = []
    warnings: list[str] = []
    search_work: list[tuple[str, str, JimakuProvider | WyzieProvider]] = []

    for lang in langs:
        provider = None
        if lang == "ja" and jimaku_provider:
            provider = jimaku_provider
        elif wyzie_provider:
            provider = wyzie_provider
        if not provider:
            if subdl_provider:
                # Direct SubDL fallback below will handle this pair.
                continue
            if lang == "ja":
                warnings.append(f"{lang}: no provider available for this URL. Use AniList/Jimaku for Japanese anime, or an IMDb/TMDB URL with WYZIE_API_KEY for broad lookup.")
            else:
                warnings.append(f"{lang}: broad provider lookup needs an IMDb/TMDB URL plus WYZIE_API_KEY. Crunchyroll URLs currently only resolve Japanese anime subtitles through Jimaku.")
            continue
        if not provider.configured():
            if provider.name == "wyzie" and subdl_provider:
                # Direct SubDL fallback below will handle this pair.
                continue
            if provider.name == "jimaku":
                warnings.append(
                    f"{lang}: {provider.name} not configured. Set JIMAKU_API_KEY, "
                    "or run getsubtitle in an interactive terminal so it can prompt for the key."
                )
            else:
                warnings.append(f"{lang}: {provider.name} not configured. Run getsubtitle --set-key wyzie, or set WYZIE_API_KEY.")
            continue
        if isinstance(provider, WyzieProvider) and not (media.imdb_id or media.tmdb_id):
            if media.provider == "title" or media.anilist_id:
                warnings.append(
                    f"{lang}: broad lookup needs an IMDb/TMDB ID, but title/anime lookup did not find one. "
                    "Choose a TMDB/IMDb match in the title picker, or use an IMDb/TMDB URL."
                )
            else:
                warnings.append(f"{lang}: Wyzie key is configured, but this URL has no IMDb/TMDB ID. Use an IMDb/TMDB URL for broad subtitle lookup.")
            continue
        for ep in episodes:
            search_work.append((lang, ep, provider))

    if search_work:
        print("\nSearching subtitles:")
    debug_records: list[ProviderDebugRecord] = []
    for idx, (lang, ep, provider) in enumerate(search_work, start=1):
        progress_bar(idx, len(search_work), "searching", f"episode {ep} {lang} [{provider.name}]", transient=True)
        try:
            if isinstance(provider, WyzieProvider):
                files = provider.files(media, ep, lang)
            else:
                files = provider.files(media, ep)
        except CliError as e:
            search_results.append(SearchResult(lang, ep, provider.name, "error", error=str(e)))
            warnings.append(f"{lang} episode {ep}: {e}")
            if args.debug_providers:
                debug_records.append(provider_debug_record(provider.name, ep, lang, [], error=str(e)))
            continue
        if args.debug_providers:
            debug_records.append(provider_debug_record(provider.name, ep, lang, files))
        best = choose_best(files, preferred_release_source)
        if best:
            if not media.title and best.media_title:
                media.title = best.media_title
            planned.append((lang, ep, best))
            search_results.append(SearchResult(lang, ep, provider.name, "found", file=best))
        else:
            search_results.append(SearchResult(lang, ep, provider.name, "missing"))

    if subdl_provider and subdl_provider.configured():
        # Direct SubDL fallback for any requested language/episode not already
        # found. This helps when a Wyzie key cannot access its proxied SubDL
        # source, while preserving the normal provider order for users without
        # a direct SubDL key.
        found_pairs = {(r.language, r.episode) for r in search_results if r.status == "found"}
        missing_pairs = [(lang, ep) for lang in langs for ep in episodes if (lang, ep) not in found_pairs]
        if missing_pairs:
            print(
                "\nSubDL: retrying "
                f"{len(missing_pairs)} missing language/episode pair(s) with direct API."
            )
        for idx, (lang, ep) in enumerate(missing_pairs, start=1):
            progress_bar(idx, len(missing_pairs), "searching", f"episode {ep} {lang} [subdl]", transient=True)
            try:
                sd_files = subdl_provider.files(media, ep, lang)
            except CliError as e:
                if args.debug_providers:
                    debug_records.append(provider_debug_record("subdl", ep, lang, [], error=str(e)))
                if not any(r.language == lang and r.episode == ep for r in search_results):
                    search_results.append(SearchResult(lang, ep, "subdl", "error", error=str(e)))
                continue
            if args.debug_providers:
                debug_records.append(provider_debug_record("subdl", ep, lang, sd_files))
            best = choose_best(sd_files, preferred_release_source)
            if not best:
                if not any(r.language == lang and r.episode == ep for r in search_results):
                    search_results.append(SearchResult(lang, ep, "subdl", "missing"))
                continue
            replaced = False
            for idx_r, r in enumerate(search_results):
                if r.language == lang and r.episode == ep and r.status != "found":
                    search_results[idx_r] = SearchResult(lang, ep, "subdl", "found", file=best)
                    replaced = True
                    break
            if not replaced:
                search_results.append(SearchResult(lang, ep, "subdl", "found", file=best))
            planned.append((lang, ep, best))
    elif (media.imdb_id or media.tmdb_id) and any(
        r.status != "found" and r.language != "ja" for r in search_results
    ):
        warnings.append("Some broad-provider subtitles were missing. Direct SubDL fallback is available with: getsubtitle --set-key subdl")

    if args.experimental_subdivx and "es" in langs:
        # Spanish fallback: try Subdivx for every requested episode where we
        # don't yet have a "found" result for es. This covers both Wyzie misses
        # *and* the case where Wyzie wasn't configured / wasn't applicable.
        found_es = {r.episode for r in search_results if r.language == "es" and r.status == "found"}
        missing_es_episodes = [ep for ep in episodes if ep not in found_es]
        if missing_es_episodes and media.title:
            print(
                "\nSubdivx (experimental): retrying "
                f"{len(missing_es_episodes)} missing es episode(s). "
                "Verify with --debug-providers if results look off."
            )
            subdivx = SubdivxProvider(enabled=True)
            for ep in missing_es_episodes:
                try:
                    sd_files = subdivx.files(media, ep)
                except CliError as e:
                    if args.debug_providers:
                        debug_records.append(provider_debug_record("subdivx", ep, "es", [], error=str(e)))
                    continue
                if args.debug_providers:
                    debug_records.append(provider_debug_record("subdivx", ep, "es", sd_files))
                best = choose_best(sd_files, preferred_release_source)
                if not best:
                    continue
                # Replace existing missing/error result if any; otherwise append.
                replaced = False
                for idx_r, r in enumerate(search_results):
                    if r.language == "es" and r.episode == ep and r.status != "found":
                        search_results[idx_r] = SearchResult("es", ep, "subdivx", "found", file=best)
                        replaced = True
                        break
                if not replaced:
                    search_results.append(SearchResult("es", ep, "subdivx", "found", file=best))
                planned.append(("es", ep, best))
        elif missing_es_episodes and not media.title:
            warnings.append("es: Subdivx fallback skipped — title is unknown, cannot search.")

    if args.experimental_addic7ed and "ko" in langs:
        # Korean fallback: try Addic7ed for every requested episode where we
        # don't yet have a "found" result for ko.
        found_ko = {r.episode for r in search_results if r.language == "ko" and r.status == "found"}
        missing_ko_episodes = [ep for ep in episodes if ep not in found_ko]
        if missing_ko_episodes and media.title:
            print(
                "\nAddic7ed (experimental): retrying "
                f"{len(missing_ko_episodes)} missing ko episode(s). "
                "Site is anti-bot — stop using this flag if you start seeing HTTP 403/503."
            )
            addic7ed = Addic7edProvider(enabled=True)
            for ep in missing_ko_episodes:
                try:
                    a7_files, a7_diag = addic7ed.files(media, ep)
                except CliError as e:
                    if args.debug_providers:
                        debug_records.append(provider_debug_record("addic7ed", ep, "ko", [], error=str(e)))
                    continue
                if args.debug_providers:
                    debug_records.append(provider_debug_record("addic7ed", ep, "ko", a7_files, error=a7_diag if a7_diag and not a7_files else None))
                best = choose_best(a7_files, preferred_release_source)
                if not best:
                    continue
                replaced = False
                for idx_r, r in enumerate(search_results):
                    if r.language == "ko" and r.episode == ep and r.status != "found":
                        search_results[idx_r] = SearchResult("ko", ep, "addic7ed", "found", file=best)
                        replaced = True
                        break
                if not replaced:
                    search_results.append(SearchResult("ko", ep, "addic7ed", "found", file=best))
                planned.append(("ko", ep, best))
        elif missing_ko_episodes and not media.title:
            warnings.append("ko: Addic7ed fallback skipped — title is unknown, cannot search.")

    if args.debug_providers:
        print_provider_debug(debug_records)

    print_search_results(search_results)
    print_warnings(warnings)
    expected_dir = output_dir(Path(args.output).expanduser(), media, media.season, args.layout)
    print_missing_subtitle_next_steps(
        langs,
        episodes,
        search_results,
        media=media,
        expected_output_dir=expected_dir,
    )
    maybe_print_manual_search_suggestions(
        media,
        langs,
        episodes,
        search_results,
        mode=args.manual_search,
        open_mode=args.manual_search_open,
        expected_output_dir=expected_dir,
    )

    if not planned:
        print("\nNo downloads planned.")
        return 1

    print_planned_downloads(planned)

    confirm_bulk(len(planned), args)
    if args.dry_run:
        return 0

    base = Path(args.output).expanduser()
    saved, download_failures = download_planned_subtitles(
        planned,
        base=base,
        media=media,
        season=media.season,
        layout=args.layout,
        episode_filename_start=args.episode_filename_start,
    )

    if download_failures:
        warnings.extend(download_failures)
        print_warnings(download_failures)
    if not saved:
        print("\nNo subtitles were downloaded successfully.")
        return 1

    if args.strip_cc_noise:
        # Strip first so the flatten step below doesn't have to deal with
        # noise (arrows, etc.) in the middle of joined cues.
        for path in saved:
            if path.suffix.lower() == ".srt":
                strip_cc_noise_in_place(path)

    if args.single_line:
        # Flatten every downloaded .srt in place so each cue is one visual
        # line. Applied to all languages, not just .ja (the flag is opt-in).
        for path in saved:
            if path.suffix.lower() == ".srt":
                flatten_srt_in_place(path, separator=flatten_separator_for(path))

    # Machine translation pass: fill missing requested languages by
    # translating from the closest available downloaded SRT.
    mt_files: list[Path] = []
    if args.mt_engine:
        explicit_mt_model = args.mt_model if (
            option_was_passed(raw_argv, "--model") or option_was_passed(raw_argv, "--mt-model")
        ) else None
        pair_model_previous = apply_mt_model_pair_overrides(
            args.mt_model_pair if args.mt_engine == "ollama" else None
        )
        translator_cache: dict[tuple[str, str | None], _BaseTranslator] = {}
        # [translate].strip_reading_before_mt: same defense as translate_main.
        # Default true; only meaningful when an MT source is ja.
        try:
            _cfg_tr = load_user_config().get("translate", {})
        except CliError:
            _cfg_tr = {}
        strip_reading_before_mt = bool(_cfg_tr.get("strip_reading_before_mt", True))

        def translator_for(src_lang: str, target_lang: str) -> _BaseTranslator:
            model = ollama_model_for_pair(src_lang, target_lang, explicit_mt_model) if args.mt_engine == "ollama" else args.mt_model
            key = (args.mt_engine, model)
            if key not in translator_cache:
                translator_cache[key] = select_translator(args.mt_engine, model)
            return translator_cache[key]

        translator = select_translator(args.mt_engine, args.mt_model)
        # Pre-flight so users get one clear install message instead of N
        # identical errors when the engine isn't ready.
        if not translator.is_available():
            restore_mt_model_pair_overrides(pair_model_previous)
            raise CliError(
                f"{translator.name}: not ready.\n{translator.setup_help()}"
            )
        # Same explicit-pair syntax as `getsubtitle translate`.
        source_overrides = parse_mt_source_lang(args.mt_source_lang, langs)
        found_by_lang_ep: dict[tuple[str, str], bool] = {}
        for r in search_results:
            if r.status == "found":
                found_by_lang_ep[(r.language, r.episode)] = True

        mt_tasks: list[tuple[str, str, Path, str]] = []
        for ep in episodes:
            available = find_existing_srts_for_episode(saved, ep)
            for target in langs:
                if found_by_lang_ep.get((target, ep)):
                    continue
                if target in available:
                    continue  # We already have a downloaded SRT for this lang.
                forced_source = source_overrides.get(target) if source_overrides else None
                if forced_source:
                    picked_forced = pick_forced_mt_source(target, forced_source, available)
                    if not picked_forced:
                        warnings.append(
                            f"{target} ep{ep}: none of the forced sources ({'|'.join(forced_source)}) "
                            f"were downloaded this run. Add one source to -l "
                            f"or run `getsubtitle translate FOLDER` on an existing folder."
                        )
                        continue
                    src_lang, src_path = picked_forced
                else:
                    picked = pick_mt_source(target, available)
                    if not picked:
                        warnings.append(
                            f"{target} ep{ep}: MT skipped — no source SRT was downloaded this run. "
                            f"Add a source lang to -l (e.g. ja or en), or run "
                            f"`getsubtitle translate FOLDER` against an existing folder. "
                            f"See: getsubtitle --help translate"
                        )
                        continue
                    src_lang, src_path = picked
                target_path = mt_output_path(src_path, target)
                mt_tasks.append((target, ep, src_path, src_lang))

        if mt_tasks:
            print(f"\nMachine translation ({translator.name}):")
            grouped_mt_failures: dict[str, list[str]] = {}
            mt_written_times: list[tuple[Path, float]] = []
            for idx, (target, ep, src_path, src_lang) in enumerate(mt_tasks, start=1):
                translator = translator_for(src_lang, target)
                target_path = mt_output_path(src_path, target)
                prefix = f"ep{ep} ({idx}/{len(mt_tasks)}) {src_lang}->{target}"
                last_pct = [-1]
                started_at = time.monotonic()

                def cue_progress(done: int, total: int, _last=last_pct, _label=prefix) -> None:
                    if total <= 0:
                        return
                    pct = (done * 100) // total
                    if done >= total or pct >= _last[0] + 5:
                        _last[0] = pct
                        progress_bar(
                            done, total, "translating",
                            f"{_label} cue {done}/{total} ({format_elapsed(time.monotonic() - started_at)})",
                            transient=True,
                        )

                try:
                    translate_srt_file(
                        src_path, target_path, translator, src_lang, target,
                        on_progress=cue_progress,
                        strip_furigana=strip_reading_before_mt,
                    )
                except TranslatorError as e:
                    grouped_mt_failures.setdefault(str(e), []).append(
                        f"ep{ep} {src_lang}->{target}"
                    )
                    continue
                elapsed = time.monotonic() - started_at
                mt_files.append(target_path)
                mt_written_times.append((target_path, elapsed))
                print(f"  ep{ep} {src_lang}->{target}: wrote {target_path.name} in {format_elapsed(elapsed)}")
            # Compact one warning per unique error message so the user sees a
            # single actionable line instead of N near-identical ones.
            for msg, tasks in grouped_mt_failures.items():
                if len(tasks) == 1:
                    warnings.append(f"{tasks[0]}: MT failed — {msg}")
                else:
                    sample = ", ".join(tasks[:3])
                    more = f" (+{len(tasks) - 3} more)" if len(tasks) > 3 else ""
                    warnings.append(f"MT failed for {len(tasks)} task(s) [{sample}{more}]: {msg}")

        # Auto-unload Ollama models from memory after the MT pass, if enabled.
        # Default true; failures are silent because the user's MT already ran.
        if args.mt_engine == "ollama" and _ollama_models_flag("auto_unload", True):
            released: list[str] = []
            for tr in translator_cache.values():
                if tr.release_resources():
                    released.append(getattr(tr, "model", tr.name))
            if released:
                uniq = sorted(set(released))
                print(f"Unloaded Ollama model(s) from memory: {', '.join(uniq)}")
        if args.mt_engine == "deepl" and translator_cache:
            print_deepl_usage_summary(translator_cache.values())
        restore_mt_model_pair_overrides(pair_model_previous)

    generated: list[Path] = []
    ko_generated: list[Path] = []
    zh_generated: list[Path] = []
    yue_generated: list[Path] = []
    _reading_formats = parse_furigana_formats(getattr(args, "reading_format", None))
    if args.ja_reading:
        furigana_sources = [path for path in saved if ".ja" in path.name and path.suffix.lower() == ".srt"]
        if furigana_sources:
            print("\nGenerating furigana:")
            total = len(furigana_sources) * len(getattr(args, "ja_readings", None) or [args.ja_reading])
            done = 0
            for path in furigana_sources:
                for mode in (getattr(args, "ja_readings", None) or [args.ja_reading]):
                    done += 1
                    progress_bar(done, total, "furigana", f"{path.name} ({mode})", transient=True)
                    generated.extend(
                        generate_furigana(
                            [path], mode, args.single_line,
                            formats=_reading_formats,
                        )
                    )
        else:
            generated = []
    if getattr(args, "ko_reading", None):
        ko_sources = [path for path in saved if ".ko" in path.name and path.suffix.lower() == ".srt"]
        if ko_sources:
            print("\nGenerating Korean romanization:")
            total = len(ko_sources) * len(getattr(args, "ko_readings", None) or [args.ko_reading])
            done = 0
            for path in ko_sources:
                for mode in (getattr(args, "ko_readings", None) or [args.ko_reading]):
                    done += 1
                    progress_bar(done, total, "romanization", f"{path.name} ({mode})", transient=True)
                    ko_generated.extend(
                        generate_korean_romanization(
                            [path], mode, args.single_line,
                            formats=_reading_formats,
                        )
                    )
    if getattr(args, "zh_reading", None):
        zh_sources = [path for path in saved if ".zh" in path.name and path.suffix.lower() == ".srt"]
        if zh_sources:
            print("\nGenerating Chinese pinyin:")
            for idx, path in enumerate(zh_sources, start=1):
                progress_bar(idx, len(zh_sources), "pinyin", path.name, transient=True)
                zh_generated.extend(
                    generate_chinese_romanization(
                        [path], args.zh_reading, args.single_line,
                        formats=_reading_formats,
                    )
                )
    if getattr(args, "yue_reading", None):
        yue_sources = [path for path in saved if ".yue" in path.name and path.suffix.lower() == ".srt"]
        if yue_sources:
            print("\nGenerating Cantonese Jyutping:")
            for idx, path in enumerate(yue_sources, start=1):
                progress_bar(idx, len(yue_sources), "jyutping", path.name, transient=True)
                yue_generated.extend(
                    generate_cantonese_romanization(
                        [path], args.yue_reading, args.single_line,
                        formats=_reading_formats,
                    )
                )

    print("\nSaved:")
    for path in saved:
        print(f"  {path}")
    if mt_files:
        print("\nMachine-translated (not human-quality — verify before use):")
        for path in mt_files:
            print(f"  {path}")
    if args.ja_reading:
        if generated:
            print("\nGenerated furigana:")
            for path in generated:
                print(f"  {path}")
        else:
            print("\nFurigana: no .ja.srt files were generated; furigana is currently created from Japanese SRT.")
    if getattr(args, "ko_reading", None):
        if ko_generated:
            print("\nGenerated Korean romanization:")
            for path in ko_generated:
                print(f"  {path}")
        else:
            print("\nKorean romanization: no .ko.srt files were generated; romanization is created from Korean SRT.")
    if getattr(args, "zh_reading", None):
        if zh_generated:
            print("\nGenerated Chinese pinyin:")
            for path in zh_generated:
                print(f"  {path}")
        else:
            print("\nChinese pinyin: no .zh.srt files were generated; pinyin is created from Chinese SRT.")
    if getattr(args, "yue_reading", None):
        if yue_generated:
            print("\nGenerated Cantonese Jyutping:")
            for path in yue_generated:
                print(f"  {path}")
        else:
            print("\nCantonese Jyutping: no .yue.srt files were generated; Jyutping is created from Cantonese SRT.")
    # If MT contributed late-stage warnings (e.g., no source available, engine
    # not configured), surface them after the saved-files block so they aren't
    # lost beneath download output.
    mt_warnings = [w for w in warnings if "MT" in w or "mt-source" in w]
    if args.mt_engine and mt_warnings:
        print_warnings(mt_warnings)
    if saved:
        should_open = args.open_folder
        if not should_open and not args.no_open_folder_prompt and sys.stdin.isatty():
            answer = input("\nOpen folder? [Y/n] ").strip().lower()
            should_open = answer in {"", "y", "yes"}
        if should_open:
            open_folder(saved[0].parent)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CliError as e:
        print(f"getsubtitle: {e}", file=sys.stderr)
        raise SystemExit(2)
