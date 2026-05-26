#!/usr/bin/env python3
"""Download and prepare subtitles for language-learning workflows."""

from __future__ import annotations

import argparse
import json
import os
import getpass
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
from dataclasses import dataclass, field, fields
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
DEFAULT_OUTPUT_TEXT = "~/Movies/Subtitles"
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
        "use": "machine translation for --mt-engine deepl (free tier: 500K chars/mo)",
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


def enrich_media_from_tmdb(media: "MediaInfo", langs: list[str] | None = None) -> bool:
    """If a TMDB API key is configured and we have a title but no
    IMDb/TMDB/AniList ID yet, search TMDB and populate the IDs.

    Returns True if anything was added. Best-effort — silently no-ops
    without a key, on network failure, or when no result matches.

    Skips Japanese-origin results when the user asked for `ja` subs, so
    the existing AniList → Jimaku path stays intact for anime. (Wyzie's
    Japanese coverage for live-action is decent; Jimaku is anime-only.)"""
    if not media.title:
        return False
    if media.imdb_id or media.tmdb_id or media.anilist_id:
        return False
    api_key = get_provider_api_key("tmdb")
    if not api_key:
        return False
    # Try TV first — shows are the primary use case for the batch flow.
    hit = tmdb_search_tv(media.title, api_key=api_key)
    if not hit:
        hit = tmdb_search_movie(media.title, api_key=api_key)
    if not hit:
        return False
    # Preserve the AniList-driven path for "user wants Japanese subs of a
    # Japanese-origin title" — Jimaku needs AniList IDs, and TMDB filling
    # in imdb/tmdb here would shortcut the needs_anilist branch.
    wants_japanese = bool(langs) and "ja" in langs
    is_japanese = (hit.get("original_language") or "").lower() == "ja"
    if wants_japanese and is_japanese:
        return False
    if hit.get("tmdb_id"):
        media.tmdb_id = hit["tmdb_id"]
    if hit.get("imdb_id"):
        media.imdb_id = hit["imdb_id"]
    return bool(media.tmdb_id or media.imdb_id)


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


def infer_from_catalog_url(url: str, provider: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    html = request_text(url)
    raw_title = title_from_html_metadata(html) if html else None
    title = clean_catalog_title(raw_title, provider) if raw_title else None
    imdb_match = re.search(r"/title/(tt\d+)", parsed.path)
    imdb_id = imdb_match.group(1) if provider == "imdb" and imdb_match else None
    tmdb_match = re.search(r"/(?:movie|tv)/(\d+)", parsed.path)
    tmdb_id = tmdb_match.group(1) if provider == "tmdb" and tmdb_match else None
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
        self._entry_id_by_anilist: dict[int, int] = {}

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

    def search_entry_id(self, media: MediaInfo) -> int:
        if not media.anilist_id:
            raise CliError(
                "Jimaku search needs an AniList ID. Pass --anilist <id>, or use a "
                "URL the CLI can map to one (anilist.co/anime/<id>, MyAnimeList, "
                "Crunchyroll series page)."
            )
        if media.anilist_id in self._entry_id_by_anilist:
            return self._entry_id_by_anilist[media.anilist_id]
        q = urllib.parse.urlencode({"anilist_id": media.anilist_id})
        entries = request_json(f"{JIMAKU_API}/entries/search?{q}", headers=self._headers())
        if not isinstance(entries, list) or not entries:
            raise CliError(
                f"Jimaku has no entry for AniList ID {media.anilist_id}. "
                "Not every anime is on Jimaku — try the same URL with -l en,ko,es "
                "to use other providers, or check the show on jimaku.cc directly."
            )
        entry_id = int(entries[0]["id"])
        self._entry_id_by_anilist[media.anilist_id] = entry_id
        return entry_id

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
DEEPL_FREE_API = "https://api-free.deepl.com/v2/translate"


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

    def setup_help(self, source_lang: str | None = None, target_lang: str | None = None) -> str:
        return (
            "Set up the DeepL API key:\n"
            "  getsubtitle --set-key deepl     # macOS Keychain / guided\n"
            "  export DEEPL_API_KEY=...        # Linux/Windows env var\n"
            "Get a free Developer key at https://www.deepl.com/your-account/keys"
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
                DEEPL_FREE_API,
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


def parse_mt_source_lang(value: str | None, requested_langs: list[str]) -> dict[str, str] | None:
    """Parse the --mt-source-lang value into a {target: source} mapping.

    Accepts:
      None / empty string       -> None (no override; auto-pick applies)
      "ja"                      -> applies "ja" as source for every target
      "ko:ja"                   -> {"ko": "ja"}
      "ko:ja,es:en"             -> {"ko": "ja", "es": "en"}

    Raises CliError for ambiguous comma-lists-without-colons, unknown targets
    (not in --langs), empty halves, or duplicated targets.

    Public for testing."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    if ":" not in raw:
        # Single token (or multiple non-colon tokens, which we reject for
        # being ambiguous between "all targets from this" and "positional").
        if len(parts) == 1:
            src = parts[0].lower()
            src = LANGUAGE_ALIASES.get(src, src)
            return {target.lower(): src for target in requested_langs}
        raise CliError(
            f"--mt-source-lang: ambiguous value {value!r}. "
            "Use a single language code to apply to all targets, "
            "or 'target:source' pairs (e.g. ko:ja,es:en)."
        )
    mapping: dict[str, str] = {}
    # Normalise both -l targets and pair targets/sources through
    # LANGUAGE_ALIASES so users can type jp/cn/chinese/etc. interchangeably.
    requested_lower = {LANGUAGE_ALIASES.get(l.lower(), l.lower()) for l in requested_langs}
    for part in parts:
        if ":" not in part:
            raise CliError(
                f"--mt-source-lang: every entry needs a target:source pair "
                f"(got {part!r}). Example: ko:ja,es:en"
            )
        target, _, source = part.partition(":")
        target = target.strip().lower()
        source = source.strip().lower()
        if not target or not source:
            raise CliError(f"--mt-source-lang: empty target or source in {part!r}")
        target = LANGUAGE_ALIASES.get(target, target)
        source = LANGUAGE_ALIASES.get(source, source)
        if target not in requested_lower:
            raise CliError(
                f"--mt-source-lang: target {target!r} is not in -l "
                f"({','.join(requested_langs)}). Add it to -l or remove the pair."
            )
        if target in mapping:
            raise CliError(f"--mt-source-lang: target {target!r} mapped twice")
        mapping[target] = source
    return mapping


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
    raise CliError(f"Unknown --mt-engine: {engine}. Use argos, ollama, or deepl.")


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
    season_label = "All Seasons" if season == "all" else f"Season {int(season):02d}" if season.isdigit() else "Season Unknown"
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


def save_subtitle(sub: SubtitleFile, dest_dir: Path, media: MediaInfo, season: str, episode: str) -> list[Path]:
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
    ep = "all" if episode == "all" else "00" if episode == "auto" else f"{int(episode):02d}"
    ss = "all" if season == "all" else "00" if season == "auto" else f"{int(season):02d}"
    filename = f"{show} - S{ss}E{ep}.{sub.language}{ext}"
    out = dest_dir / filename
    out.write_bytes(raw)
    saved.append(out)
    return saved


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def has_kanji(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


EXISTING_READING_RE = re.compile(r"([\u4e00-\u9fff々〆ヶ]+)[(（]([ぁ-ゖァ-ヺーa-zA-Z0-9 -]+)[)）]")


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


def text_with_readings(text: str, mode: str) -> str:
    try:
        import pykakasi  # type: ignore
    except Exception as e:
        raise CliError(
            "Furigana needs the pykakasi package.\n"
            "  Quick install: python3 -m pip install pykakasi\n"
            "  Or reinstall with the extra: pip install -e \".[furigana]\"\n"
            "  See: getsubtitle --help furigana"
        ) from e

    protected_text, protected = protect_existing_readings(strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(protected_text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get("hira" if mode == "hiragana" else "hepburn", "")
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
            "  See: getsubtitle --help furigana"
        ) from e

    protected_text, protected = protect_existing_readings_as_ruby(strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(protected_text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get("hira" if mode == "hiragana" else "hepburn", "")
        if surface and reading and surface != reading and has_kanji(surface):
            chunks.append(ruby_tag(surface, reading))
        else:
            chunks.append(html_escape(surface))
    return restore_existing_readings("".join(chunks), protected)


def flatten_subtitle_lines(lines: list[str]) -> list[str]:
    flattened = "　".join(strip_subtitle_markup(line).strip() for line in lines if line.strip())
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


def strip_cc_noise_text(text: str) -> str:
    """Umbrella cleanup for closed-caption / broadcast-caption artifacts.

    Currently delegates to strip_cc_arrows_text. As we identify more shapes
    of CC noise to remove (music markers, voiceover brackets, etc.) we can
    layer them in here without changing the CLI flag or the call sites."""
    return strip_cc_arrows_text(text)


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


def parse_vtt(text: str) -> list[SrtCue]:
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
            stripped = _strip_vtt_markup(ln).strip()
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


def read_cues_from_file(path: Path, *, lang_hint: str | None = None) -> list[SrtCue]:
    """Read any supported subtitle file into the unified SrtCue
    representation used by the merge pipeline.

    Dispatch by extension:
      .srt        → parse_srt
      .vtt        → parse_vtt (ruby collapsed to 漢字（かんじ）)
      .ass/.ssa    → parse_ass (Events Dialogue timing/text; styling ignored)
      .smi/.sami  → parse_smi_for_lang (requires lang_hint)
    """
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(path.read_text(encoding="utf-8-sig", errors="replace"))
    if suffix == ".vtt":
        return parse_vtt(path.read_text(encoding="utf-8-sig", errors="replace"))
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
        subtitle_lines = [ln for ln in lines[time_idx + 1 :] if ln.strip()]
        if not subtitle_lines:
            out_blocks.append(block)
            continue
        flat = separator.join(strip_subtitle_markup(ln).strip() for ln in subtitle_lines)
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


def convert_smi_file(smi_path: Path, *, force: bool = False) -> tuple[list[Path], list[Path]]:
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
        out_path = stem.with_name(stem.name + f".{lang}.srt")
        if out_path.exists() and not force:
            skipped.append(out_path)
            continue
        out_path.write_text(sami_cues_to_srt(cues), encoding="utf-8")
        written.append(out_path)
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
            "  See: getsubtitle --help furigana"
        ) from e

    # Remove existing parenthetical readings so the reading line does not repeat them.
    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    chunks = []
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get("hira" if mode == "hiragana" else "hepburn", "")
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
            "  See: getsubtitle --help furigana"
        ) from e

    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    chunks = []
    has_reading = False
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get("hira" if mode == "hiragana" else "hepburn", "")
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
            "  See: getsubtitle --help furigana"
        ) from e

    text = EXISTING_READING_RE.sub(lambda m: m.group(1), strip_subtitle_markup(text))
    kakasi = pykakasi.kakasi()
    converted = kakasi.convert(text)
    reading_chunks: list[str] = []
    text_chunks: list[str] = []
    has_reading = False
    for c in converted:
        surface = c.get("orig", "")
        reading = c.get("hira" if mode == "hiragana" else "hepburn", "")
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
            "See: getsubtitle --help furigana"
        )
    return set(parts)


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

# Thresholds for time-overlap matching. Constants kept here so they're easy
# to tune without grepping. Each preset has cue-level and episode-level bars
# plus a max-drift hint used for tie-breaking close cue starts.
SYNC_PRESETS: dict[str, dict[str, float]] = {
    "auto":   {"cue_overlap": 0.35, "episode_success": 0.75, "max_drift_ms": 1500, "max_offset_ms": 45000, "offset_bucket_ms": 250, "offset_min_improvement": 0.05},
    "strict": {"cue_overlap": 0.60, "episode_success": 0.90, "max_drift_ms": 750, "max_offset_ms": 30000, "offset_bucket_ms": 250, "offset_min_improvement": 0.08},
    "loose":  {"cue_overlap": 0.20, "episode_success": 0.60, "max_drift_ms": 2500, "max_offset_ms": 60000, "offset_bucket_ms": 250, "offset_min_improvement": 0.03},
}


def parse_episode_marker(name: str) -> tuple[int, int] | None:
    """Return (season, episode) parsed from a filename, or None."""
    for pattern in _EPISODE_PATTERNS:
        m = pattern.search(name)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


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
        if root.is_file():
            discovered.append(root)
        elif root.is_dir():
            discovered.extend(sorted(root.rglob("*.srt")))
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
) -> list[tuple[Path, int, int, str, bool, str]]:
    """Walk paths and find subtitle files in SRT, VTT, ASS/SSA, and optionally SAMI.

    SRT and VTT use the standard `<base>.<lang>.<ext>` filename convention.
    SAMI files are multi-language internally, so they're only scanned when
    at least one entry in `format_hints` requests SMI for some language;
    each SMI file then emits one candidate per requested language that it
    actually contains.

    Returns: list[(path, season, episode, lang, is_mt, source_format)]
    where source_format is one of "srt" | "vtt" | "ass" | "ssa" | "smi".
    """
    format_hints = format_hints or {}
    out: list[tuple[Path, int, int, str, bool, str]] = []

    # SRT (delegate to existing scanner).
    for tup in scan_srt_files(paths, include_furigana=include_furigana):
        out.append(tup + ("srt",))

    # VTT.
    discovered_vtt: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".vtt":
            discovered_vtt.append(root)
        elif root.is_dir():
            discovered_vtt.extend(sorted(root.rglob("*.vtt")))
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
        if root.is_file() and root.suffix.lower() in (".ass", ".ssa"):
            discovered_ass.append(root)
        elif root.is_dir():
            discovered_ass.extend(sorted(root.rglob("*.ass")))
            discovered_ass.extend(sorted(root.rglob("*.ssa")))
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
) -> tuple[list[SrtCue], dict[str, float]]:
    """Combine `master_cues` with overlapping cues from each target language.

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
                    body.extend(_format_japanese_furigana_for_combine(
                        master_cue.text_lines, japanese_furigana_mode, preserve_lines
                    ))
                else:
                    body.extend(_format_cue_text_for_lang(master_cue.text_lines, preserve_lines))
            else:
                body.extend(per_lang_text.get(lang, []))

        combined.append(
            SrtCue(
                index=str(i + 1),
                time_line=master_cue.time_line,
                text_lines=body if body else [""],
            )
        )

    total = len(master_cues) or 1
    return combined, {lang: count / total for lang, count in match_counts.items()}


def combined_output_name(master_path: Path, lang_order: list[str], *, furigana: bool = False) -> str:
    """Compute the combined-output filename, e.g.
    'MF Ghost - S01E07.ja.srt' + ['ja','ko'] -> 'MF Ghost - S01E07.ja-ko.srt'.

    When `furigana` is set and 'ja' is present, the 'ja' token is rewritten
    to 'ja-furigana' so the output filename signals that readings were
    inlined into the Japanese lines."""
    name = master_path.name
    stem = re.sub(r"\.[a-z]{2,3}(\.mt)?\.srt$", "", name, flags=re.I)
    if stem == name:
        # No language token to strip; fall back to the bare stem.
        stem = master_path.with_suffix("").name
    tokens = list(lang_order)
    if furigana and "ja" in tokens:
        # Replace only the first ja so other ja entries (rare) aren't doubled.
        ja_idx = tokens.index("ja")
        tokens[ja_idx] = "ja-furigana"
    return f"{stem}.{'-'.join(tokens)}.srt"


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
              getsubtitle combine ~/Movies/Subtitles/MF\\ Ghost -l ja,ko
              getsubtitle combine FOLDER -l ja,ko --dry-run
              getsubtitle combine FOLDER -l ja,ko -o ~/Movies/Subtitles/Combined
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
    p.add_argument("--format", choices=["srt", "vtt"], default="srt", help="Combined output format. srt = broad compatibility; vtt = WebVTT with ruby markup when --furigana is used. Default: srt.")
    p.add_argument("--subdirectory", action="store_true", help="Bulk mode: treat each immediate subdirectory of PATH as its own show and run combine once per subdir. Useful for whole-library passes.")
    p.add_argument("--dry-run", action="store_true", help="Show the plan without writing files.")
    p.add_argument("--force", action="store_true", help="Overwrite existing combined outputs and bypass the episode-level match-rate threshold.")
    p.add_argument("--open-folder", action="store_true", help="Open the output folder after writing.")
    p.add_argument("--no-open-folder-prompt", action="store_true", help="Do not ask whether to open the output folder after writing.")
    p.add_argument("--sync", choices=list(SYNC_PRESETS), default="auto", help="Time-overlap strictness preset. Default: auto.")
    p.add_argument("--master", metavar="LANG", help="Override the timing master language (default: first language in -l).")
    p.add_argument("--single-line", "--single", dest="preserve_lines", action="store_false", default=argparse.SUPPRESS, help="Flatten each language to one line per cue. This is the default; kept as an explicit readability flag.")
    p.add_argument("--preserve-lines", action="store_true", default=argparse.SUPPRESS, help="Keep each source language's original line breaks. Default: flatten each language to a single line.")
    # Hidden compat aliases for the pre-v1.1 --furigana flag; kept so old
    # scripts and the [merge].furigana TOML key still work. New code should
    # use --romanization (added below), which generalises to non-Japanese
    # languages and routes Japanese entries through the same code path.
    p.add_argument("-f", "--furigana", "-furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help=argparse.SUPPRESS)
    p.add_argument("--no-furigana", dest="furigana", action="store_const", const=None, help=argparse.SUPPRESS)
    p.add_argument("--romanization", "--romanize", metavar="SPEC", help="Inline reading aids onto the matching language line in the merged cue stack. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana' or 'ja:romaji'. Japanese ships now; other languages land per the roadmap.")
    p.add_argument("--no-romanization", dest="romanization", action="store_const", const="", help="Disable inline reading aids for this run, overriding [merge].romanization / [merge].furigana from user_settings.toml.")
    p.set_defaults(preserve_lines=False)
    _apply_combine_config_defaults(p)
    return p


def _format_rate(rate: float) -> str:
    return f"{rate * 100:.0f}%"


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
    # --romanization (the v1.1 generalised flag) routes through the legacy
    # --furigana attribute for Japanese; non-Japanese languages raise a
    # clear "not yet implemented" CliError until per-language backends ship.
    _apply_romanization_to_args(args)
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
    # Master language precedence: --master flag > [combine].priority config >
    # first language in -l.
    if args.master:
        master_lang = args.master.lower()
    else:
        master_lang = _combine_master_from_config(langs) or langs[0]
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

    # If per-language :format hints are present (from --config TOML
    # and/or bare `-l ja:vtt,...` syntax), use the extended scanner that
    # also finds .vtt and (where requested) .smi sources. Otherwise stay
    # on the SRT-only fast path for behavior parity.
    if _effective_format_hints:
        scanned_ext = scan_subtitle_files_extended(
            paths, format_hints=_effective_format_hints,
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
            master_cues = read_cues_from_file(files[master_lang], lang_hint=master_lang)
        except Exception as e:
            skipped.append((key, f"could not parse master subtitle: {e}"))
            continue
        if not master_cues:
            skipped.append((key, "master subtitle has no cues"))
            continue
        if args.format == "vtt" and args.furigana and master_lang == "ja":
            try:
                apply_japanese_ruby(master_cues, args.furigana)
            except CliError as e:
                skipped.append((key, f"furigana failed: {e}"))
                continue

        target_cues: dict[str, list[SrtCue]] = {}
        for lang in langs:
            if lang == master_lang or lang not in files:
                continue
            try:
                cues = read_cues_from_file(files[lang], lang_hint=lang)
            except Exception:
                # Treat as missing for this lang rather than skipping the
                # whole episode.
                cues = []
            if args.format == "vtt" and args.furigana and lang == "ja":
                try:
                    apply_japanese_ruby(cues, args.furigana)
                except CliError as e:
                    skipped.append((key, f"furigana failed: {e}"))
                    cues = []
            target_cues[lang] = cues

        try:
            combined, rates = combine_cues(
                master_cues, target_cues, langs, master_lang, sync_preset,
                preserve_lines=args.preserve_lines,
                japanese_furigana_mode=args.furigana if args.format == "srt" else None,
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
        out_name = combined_output_path(files[master_lang], langs, furigana=bool(args.furigana), fmt=args.format)
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = serialize_vtt(combined) if args.format == "vtt" else serialize_srt(combined)
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
# Same MT engines and source-language priority as the in-download `--mt-engine`
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
              getsubtitle translate ~/Movies/Subtitles/MF\\ Ghost -l ja,ko --mt-engine argos
              getsubtitle translate FOLDER -s 1 -e 11 -l ko --mt-source-lang ja --mt-engine ollama
              getsubtitle translate FOLDER -l ja,ko,en,es --mt-engine deepl --dry-run
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
            "translate needs an engine. Pass --mt-engine {argos|ollama|deepl} "
            "or set [translate].engine in user_settings.toml."
        )
    langs = split_csv(args.langs, "ja")
    if not langs:
        raise CliError("No target languages specified. Use -l ja,ko or similar.")
    # [translate].strip_furigana_before_mt: when true (default), strip inline
    # 漢字（かんじ） readings from ja source cues before MT so the translator
    # doesn't treat them as extra content. Read once here so per-cue
    # translation stays fast.
    try:
        _cfg_tr = load_user_config().get("translate", {})
    except CliError:
        _cfg_tr = {}
    strip_furigana_before_mt = bool(_cfg_tr.get("strip_furigana_before_mt", True))

    # Parse --mt-source-lang once (so a bad value errors before the scan).
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
        print(f"Source overrides: {', '.join(f'{t}<-{s}' for t, s in source_overrides.items())}")

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
                src_lang = forced_source
                src_path = available.get(src_lang)
                if not src_path:
                    skipped.append((key, f"{target}: forced source {src_lang!r} not available for this episode"))
                    continue
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
        raise CliError(
            f"{translator.name}: not ready.\n{translator.setup_help(sample_src, sample_tgt)}"
        )

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
                strip_furigana=strip_furigana_before_mt,
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

    print(f"\nWrote {len(written)} machine-translated file(s).")
    if written:
        print("Reminder: .mt.srt files are machine-quality — verify before relying on them.")
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
    fur_mode = mod.get("furigana", False)
    if isinstance(fur_mode, str) and fur_mode.lower() not in ("off", "false", "none", "no", ""):
        overrides["furigana"] = fur_mode if fur_mode in ("hiragana", "romaji") else "hiragana"
    elif fur_mode is True:
        overrides["furigana"] = "hiragana"
    if mod.get("furigana_output_format"):
        overrides["furigana_format"] = mod["furigana_output_format"]
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
              getsubtitle modify FOLDER --romanization ja:hiragana
              getsubtitle modify FOLDER --romanization ja:romaji
              getsubtitle modify FOLDER --romanization "ja:hiragana|romaji"
              getsubtitle modify FOLDER --convert smi-to-srt
              getsubtitle modify FOLDER --convert smi-to-srt --force
              getsubtitle modify FOLDER --strip-cc-noise --single-line --romanization ja:hiragana --dry-run
            """
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="One or more subtitle files or directories to scan (recursive).")
    p.add_argument("--strip-cc-noise", action="store_true", help="Remove broadcast closed-caption noise (currently: Japanese ➡ continuation arrows) in place.")
    p.add_argument("--single-line", "--single", action="store_true", help="Flatten each SRT cue to one text line in place. Useful for asbplayer.")
    # Hidden compat alias for the pre-v1.1 --furigana flag. Internally
    # equivalent to `--romanization ja:MODE`.
    p.add_argument("-f", "--furigana", "-furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help=argparse.SUPPRESS)
    p.add_argument("--romanization", "--romanize", metavar="SPEC", help="Generate per-language reading aids. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana' or 'ja:hiragana|romaji' (pipe = both side files). MODE 'true' picks the language's sensible default. Japanese (furigana / romaji) ships now; Korean / Chinese / Cantonese / Thai / etc. land per the roadmap.")
    p.add_argument("--no-romanization", dest="romanization", action="store_const", const="", help="Disable romanization for this run, overriding [modify].romanization from user_settings.toml.")
    p.add_argument("--reading-format", "--format", "--furigana-format", "--romanization-format", dest="furigana_format", metavar="CODES", help="Reading-aid output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt. Overrides [modify].reading_format from user_settings.toml.")
    p.add_argument("--convert", choices=["smi-to-srt"], metavar="PAIR", help="Convert subtitle file format. Currently supports: smi-to-srt (Microsoft SAMI → one sibling .<lang>.srt per language found inside).")
    p.add_argument("--force", action="store_true", help="With --convert: overwrite existing sibling .srt files. Without --force, conversion skips targets that already exist.")
    p.add_argument("--subdirectory", action="store_true", help="Bulk mode: treat each immediate subdirectory of PATH as its own show and run modify once per subdir.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing anything.")
    _apply_modify_config_defaults(p)
    return p


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
    # --romanization is the v1.1 multi-language umbrella; for the Japanese
    # entry it routes to the existing --furigana code path so this round
    # ships the schema without rewriting the generator. Non-Japanese
    # entries raise a clear "not yet implemented" error pointing at the
    # roadmap until per-language backends ship.
    if getattr(args, "romanization", None):
        pairs = _parse_romanization_spec(args.romanization)
        ja_pair = next(((l, m) for l, m in pairs if l == "ja"), None)
        non_ja = [(l, m) for l, m in pairs if l != "ja"]
        if non_ja:
            langs = ", ".join(f"{l}:{m}" for l, m in non_ja)
            raise CliError(
                f"--romanization for non-Japanese languages ({langs}) is not yet "
                "implemented. Korean (Revised Romanization with G2P) and Chinese "
                "pinyin are on the roadmap; see ROADMAP.md > Romanization expansion. "
                "Japanese (--furigana / ja:hiragana / ja:romaji) ships now."
            )
        if ja_pair is not None:
            _lang, ja_mode = ja_pair
            # Map ja-specific modes onto --furigana's argparse value.
            if ja_mode in ("hiragana", "katakana", "furigana"):
                args.furigana = "hiragana"
            elif ja_mode == "romaji":
                args.furigana = "romaji"
    ops_selected = [
        bool(args.strip_cc_noise),
        bool(args.single_line),
        bool(args.furigana),
        bool(args.convert),
    ]
    if not any(ops_selected):
        raise CliError(
            "modify needs at least one operation flag: "
            "--strip-cc-noise, --single-line, --romanization SPEC, "
            "and/or --convert smi-to-srt."
        )
    # Validate --furigana-format upfront so a bad value errors before the
    # plan is printed and any work happens. Cached so the inner loop reuses it.
    furigana_formats = (
        parse_furigana_formats(getattr(args, "furigana_format", None))
        if args.furigana else None
    )

    paths = [Path(p).expanduser() for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise CliError("Path not found: " + ", ".join(str(p) for p in missing))

    # The in-place ops (strip-cc-noise, single-line, furigana) walk .srt files.
    # The convert op walks .smi files. Both share PATH discovery but scan
    # different extensions, so we run two separate scans here.
    inplace_ops = bool(args.strip_cc_noise or args.single_line or args.furigana)
    scanned: list[tuple[Path, int, int, str, bool]] = (
        scan_srt_files(paths) if inplace_ops else []
    )
    convert_files: list[Path] = (
        scan_smi_files(paths) if args.convert == "smi-to-srt" else []
    )

    if inplace_ops:
        print(f"Scanned: {len(scanned)} SRT file(s) across {len(paths)} path(s)")
    if args.convert == "smi-to-srt":
        print(f"Scanned: {len(convert_files)} SMI file(s) across {len(paths)} path(s)")

    if not scanned and not convert_files:
        if args.convert and not inplace_ops:
            print("No .smi files found. Nothing to convert.")
        elif inplace_ops and not args.convert:
            print("No single-language SRT files found. Nothing to process.")
        else:
            print("No SRT or SMI files found. Nothing to process.")
        return 1

    # Describe the plan up front so --dry-run is meaningful.
    ops_desc: list[str] = []
    if args.convert == "smi-to-srt":
        ops_desc.append("convert smi → srt")
    if args.strip_cc_noise:
        ops_desc.append("strip CC noise")
    if args.single_line:
        ops_desc.append("flatten single-line")
    if args.furigana:
        ops_desc.append(f"furigana ({args.furigana})")
    print("Operations: " + ", ".join(ops_desc))

    if inplace_ops:
        # Furigana applies only to .ja.srt files. Pre-compute the subset so the
        # summary doesn't double-count or mislead.
        ja_paths = [t[0] for t in scanned if t[3] == "ja"]
        if args.furigana and not ja_paths:
            print("(--furigana requested but no .ja.srt files found; that step will be a no-op.)")

        print(f"\nPlanned in-place: {len(scanned)} file(s)")
        for path, _season, _episode, lang, _is_mt in scanned[:20]:
            suffix = "  [ja → furigana variants]" if (args.furigana and lang == "ja") else ""
            print(f"  {path.name}{suffix}")
        if len(scanned) > 20:
            print(f"  ... and {len(scanned) - 20} more")

    if convert_files:
        print(f"\nPlanned convert: {len(convert_files)} .smi file(s)")
        for path in convert_files[:20]:
            print(f"  {path.name}")
        if len(convert_files) > 20:
            print(f"  ... and {len(convert_files) - 20} more")

    if args.dry_run:
        return 0

    touched_in_place = 0
    furigana_generated: list[Path] = []
    grouped_errors: dict[str, list[str]] = {}

    if inplace_ops:
        print("\nProcessing SRT:")
        # Order matches the download flow: strip-cc-noise -> single-line -> furigana.
        # First two are idempotent in-place rewrites; furigana writes side files.
        for idx, (path, _season, _episode, lang, _is_mt) in enumerate(scanned, start=1):
            progress_bar(idx, len(scanned), "processing", path.name, transient=True)
            before = path.read_bytes() if path.exists() else b""
            try:
                if args.strip_cc_noise:
                    strip_cc_noise_in_place(path)
                if args.single_line:
                    flatten_srt_in_place(path, separator=flatten_separator_for(path))
                if args.furigana and lang == "ja":
                    furigana_generated.extend(
                        generate_furigana(
                            [path], args.furigana, bool(args.single_line),
                            formats=furigana_formats,
                        )
                    )
            except CliError as e:
                grouped_errors.setdefault(str(e), []).append(path.name)
                continue
            after = path.read_bytes() if path.exists() else b""
            if before != after:
                touched_in_place += 1

    convert_written: list[Path] = []
    convert_skipped: list[Path] = []
    if convert_files:
        print("\nConverting SMI:")
        for idx, smi in enumerate(convert_files, start=1):
            progress_bar(idx, len(convert_files), "converting", smi.name, transient=True)
            try:
                written, skipped = convert_smi_file(smi, force=args.force)
            except CliError as e:
                # CliError carries "<name>: <reason>"; strip the name to group.
                msg = str(e)
                prefix = f"{smi.name}: "
                key = msg[len(prefix):] if msg.startswith(prefix) else msg
                grouped_errors.setdefault(key, []).append(smi.name)
                continue
            convert_written.extend(written)
            convert_skipped.extend(skipped)

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
    if args.furigana:
        print(f"Furigana variants generated: {len(furigana_generated)}")
    if args.convert == "smi-to-srt":
        skipped_note = (
            f" ({len(convert_skipped)} skipped — output exists, pass --force to overwrite)"
            if convert_skipped else ""
        )
        print(f"SRT files written from SMI: {len(convert_written)}{skipped_note}")
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
              getsubtitle fetch ~/Movies/Subtitles/MF\\ Ghost

              # PATH library, every immediate subdir = a show
              getsubtitle fetch ~/Movies/Subtitles --subdirectory --run

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
    if args.profile:
        print(f"profile override: {args.profile}")
    elif not get_provider_api_key("tmdb"):
        print("note: no TMDB key — profile detection falls back to char-set heuristics.")
        print("      Set one with: getsubtitle --set-key tmdb")

    total_targets = 0
    for show in roots:
        # Each `show` is one show folder (or one bare file). Walk inside
        # to find video-bearing folders / loose files; reuse the batch
        # walker since it already handles Plex Season subdirs.
        if show.is_dir():
            targets = _batch_walk_targets(show)
            if not targets:
                # No video files found anywhere inside — treat the show
                # folder itself as the target (user may want to download
                # before videos exist).
                targets = [(show, show, None)]
        else:
            targets = [(show, show, None)]
        for target, show_folder, season in targets:
            profile = args.profile or detect_profile_from_title(show_folder.name)
            _batch_fetch_one(
                target=target, show_folder=show_folder, season=season,
                profile=profile, dry_run=dry_run,
            )
            total_targets += 1

    print()
    print(f"Processed {total_targets} target(s).")
    return 0


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
                     profile: str, dry_run: bool) -> None:
    """Run fetch for one disk target (folder or bare file).

    Fetch-only — does NOT auto-translate. Users wanting MT to fill missing
    languages chain it via the pipeline form:
      getsubtitle --fetch PATH --subdirectory --translate ollama
    """
    _batch_heading(_batch_describe_target(target, show_folder, season, profile))

    title = show_folder.name
    is_folder = target.is_dir()
    output_dir = target if is_folder else target.parent

    fetch_langs = _BATCH_FETCH_LANGS.get(profile, _BATCH_FETCH_LANGS["en"])

    fetch_cmd = [
        sys.executable, "-m", "getsubtitle",
    ] if not shutil.which("getsubtitle") else ["getsubtitle"]
    fetch_cmd += ["--title", title]
    if season is not None:
        fetch_cmd += ["-s", str(season)]
    fetch_cmd += ["-e", "all", "-l", ",".join(fetch_langs),
                  "--layout", "flat", "-o", str(output_dir), "-y"]
    print(f"  fetch: -l {','.join(fetch_langs)}")
    _batch_run(fetch_cmd, dry_run=dry_run)


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
    return s.startswith(("http://", "https://", "HTTP://", "HTTPS://"))


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
_PIPELINE_GLOBAL_VALUED_FLAGS = {"--output"}     # take next token as value
_PIPELINE_GLOBAL_BOOL_FLAGS = {"--dry-run", "--force"}


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
    target = fetch_block[0]
    return (target, fetch_block[1:])


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
    shared_output: str | None = None
    shared_dry_run = False
    i = 0
    leftover_shared: list[str] = []
    while i < len(shared):
        tok = shared[i]
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

    # The "downstream target" — where translate/modify/merge operate — is:
    #   1. --output PATH if given
    #   2. fetch's TARGET (when fetch is a PATH, not a URL)
    #   3. error otherwise (URL fetch with no --output means we don't know
    #      where the SRTs landed; user must specify)
    downstream_target: str | None = shared_output
    if downstream_target is None and fetch_target is not None and not _looks_like_url(fetch_target):
        downstream_target = fetch_target
    if downstream_target is None and any(v in blocks for v in ("translate", "modify", "merge")):
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
        # Propagate shared --dry-run by adding to fetch's args if not already
        # there. URL form respects --dry-run via the URL parser. PATH form
        # is already dry-run by default unless --run; --dry-run is harmless.
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        rc = fetch_main(sub_argv)
        rc_total = rc or rc_total

    if "translate" in blocks:
        if downstream_target is None:
            raise CliError("--translate needs --output PATH or a PATH --fetch target.")
        _heading(f"translate {downstream_target}")
        tr_args = _rewrite_translate_block(blocks["translate"])
        sub_argv = [downstream_target] + tr_args
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        rc = translate_main(sub_argv)
        rc_total = rc or rc_total

    if "modify" in blocks:
        if downstream_target is None:
            raise CliError("--modify needs --output PATH or a PATH --fetch target.")
        _heading(f"modify {downstream_target}")
        sub_argv = [downstream_target] + blocks["modify"]
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
        rc = modify_main(sub_argv)
        rc_total = rc or rc_total

    if "merge" in blocks:
        if downstream_target is None:
            raise CliError("--merge needs --output PATH or a PATH --fetch target.")
        _heading(f"merge {downstream_target}")
        sub_argv = [downstream_target] + blocks["merge"]
        if shared_dry_run and "--dry-run" not in sub_argv:
            sub_argv.append("--dry-run")
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


def _resolve_modify_furigana(value) -> list[str]:
    """Pipeline `[modify].furigana = "off"|"hiragana"|"romaji"|true|false`
    → CLI flag emission. Japanese-specific shorthand kept for back-compat
    with users who set this before the v1.1 romanization umbrella shipped.

    - "off" or false → no --furigana emitted
    - "hiragana" / "romaji" → --furigana hiragana / --furigana romaji
    - true (boolean) → bare --furigana (uses default mode)
    """
    if isinstance(value, bool):
        return ["--furigana"] if value else []
    s = str(value).strip().lower()
    if s in ("off", "false", "none", "no", ""):
        return []
    if s in ("on", "true", "yes"):
        return ["--furigana"]
    if s in ("hiragana", "romaji"):
        return ["--furigana", s]
    raise CliError(
        f"[modify].furigana must be off | hiragana | romaji (got {value!r})."
    )


# Default romanization mode per language. When the user writes "ko:true" we
# resolve to this dictionary to pick the sensible default. Each language
# uses its own native term — Japanese is "furigana" not "romanization-ja",
# Chinese is "pinyin", Cantonese is "jyutping", etc.
_ROMANIZATION_DEFAULTS: dict[str, str] = {
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
_ROMANIZATION_ACCEPTED_MODES: dict[str, set[str]] = {
    "ja": {"hiragana", "katakana", "romaji", "furigana"},
    "ko": {"revised", "yale", "mr", "true"},
    "zh": {"marks", "numbers", "letters", "true"},
    "yue": {"numbers", "marks", "true"},
    "th": {"royal-thai", "iso-11940", "true"},
    "ar": {"ala-lc", "dmg", "true"},
    "hi": {"iast", "iso-15919", "itrans", "true"},
    "ru": {"iso-9", "bgn-pcgn", "true"},
}


def _parse_romanization_spec(value) -> list[tuple[str, str]]:
    """Pipeline `[modify].romanization = "ko:true, ja:hiragana"` (string OR list)
    → list of (lang_iso, mode) pairs.

    Accepted forms:
      "ko:true, ja:hiragana, zh:true"               (comma string)
      ["ko:true", "ja:hiragana"]                    (list)
      "ja:hiragana|romaji"                           (pipe expands to two entries)
      true / "true"                                  (every supported lang's default)

    Each entry's mode "true" resolves to the default for that language
    (see _ROMANIZATION_DEFAULTS). Language codes accept ISO codes (ja, ko,
    zh, yue, …) or common typos (jp, kr, cn) via LANGUAGE_ALIASES.
    """
    # Convert input to a flat list of "lang:mode" entries.
    if isinstance(value, bool):
        if not value:
            return []
        # `true` alone → every supported lang at its default. Usually not
        # what the user wants (most folks have one or two target langs),
        # but it makes "turn everything on" trivial.
        return [(lang, mode) for lang, mode in _ROMANIZATION_DEFAULTS.items()]
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
                m = _ROMANIZATION_DEFAULTS.get(lang)
                if m is None:
                    raise CliError(
                        f"[modify].romanization: language {lang!r} has no built-in "
                        f"default. Specify a mode explicitly (e.g. {lang}:romanized)."
                    )
            accepted = _ROMANIZATION_ACCEPTED_MODES.get(lang)
            if accepted and m not in accepted:
                raise CliError(
                    f"[modify].romanization: {lang!r} doesn't support mode {m!r}. "
                    f"Try one of: {', '.join(sorted(accepted - {'true'}))}."
                )
            out.append((lang, m))
    return out


def _apply_romanization_to_args(args) -> None:
    """Translate `args.romanization` (the v1.1 SPEC string) onto the
    legacy `args.furigana` attribute the downstream code reads. Routes
    Japanese entries through the existing furigana code path; raises a
    clear CliError for non-Japanese languages still to ship.

    A no-op when `args.romanization` is unset or empty. Used by
    combine_main and the URL-form download flow so the SPEC layer above
    feeds the same generator below.
    """
    spec = getattr(args, "romanization", None)
    if not spec:
        return
    if spec == "":
        # --no-romanization → explicit disable.
        args.furigana = None
        return
    pairs = _parse_romanization_spec(spec)
    ja_modes = [m for l, m in pairs if l == "ja"]
    non_ja = [(l, m) for l, m in pairs if l != "ja"]
    if non_ja:
        langs = ", ".join(f"{l}:{m}" for l, m in non_ja)
        raise CliError(
            f"--romanization for non-Japanese languages ({langs}) is not yet "
            "implemented. Korean (Revised Romanization with G2P) and Chinese "
            "pinyin are on the roadmap; see ROADMAP.md > Romanization expansion."
        )
    if ja_modes:
        # Map the first ja-mode onto --furigana's value (the downstream
        # generator handles only one mode at a time; multi-mode |-pipe
        # support comes with the per-language backend rollout).
        mode = ja_modes[0]
        args.furigana = "romaji" if mode == "romaji" else "hiragana"


def _resolve_modify_romanization(value) -> list[str]:
    """Pipeline `[modify].romanization = "ko:true, ja:hiragana"` → CLI flag
    emission. The CLI flag is `--romanization SPEC` (a comma string), so
    this just normalises and re-serializes the spec for the downstream
    parser, with backward-compat to the older `[modify].furigana` key
    handled separately in _toml_to_pipeline_argv."""
    pairs = _parse_romanization_spec(value)
    if not pairs:
        return []
    spec = ",".join(f"{lang}:{mode}" for lang, mode in pairs)
    return ["--romanization", spec]


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
    accepted by --mt-source-lang.

    Accepts:
      - string: "ja" (global) or "ko:ja,es:en" (per-target)
      - dict: { ko = "ja", es = "en" } (per-target, cleaner)
              { en = ["ko", "ja"] } (fallback list — first item used today;
              future round will pick first AVAILABLE on disk)
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for target, source in value.items():
            if isinstance(source, (list, tuple)):
                # First-listed source is the canonical pick for today's CLI.
                if not source:
                    continue
                source = source[0]
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
      mt_source = { ko = "ja", es = "en" }   # per-target source (dict form)
      # or: mt_source = "ko:ja,es:en"        # comma-string form (mt_source_lang accepted as alias)
      "ja:ko" = "qwen3:4b"            # per-pair Ollama overrides (session-only)
      "en:es" = "llama3.2:3b"

      [modify]
      strip_cc_noise = true
      single_line = true
      furigana = "hiragana"           # off | hiragana | romaji
      reading_format = "all"          # srt | ass | vtt | all (alias: furigana_output_format)
      convert = "smi-to-srt"          # "none" or omitted = no conversion

      [merge]
      languages = "ja:vtt, en, ko:smi"   # per-lang :format input hints
      master = "ja"
      sync = "strict"
      furigana = true                 # inline 漢字（かんじ） into merged ja
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
        fetch_src = fb.pop("source", None) or fb.pop("target", None) or fb.pop("url", None)
        if fetch_src is None:
            raise CliError("Pipeline TOML [fetch] section needs a `source` key.")
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
            argv += ["--mt-source", _normalize_mt_source(_mt_src_val)]
        # Global --force propagates to translate.
        if out_force:
            argv.append("--force")
        for key, value in remaining.items():
            argv += _emit_pipeline_flag(key, value)

    if "modify" in toml_data:
        mb = dict(toml_data["modify"])
        argv.append("--modify")
        # `romanization` is the v1.1 multi-language umbrella; takes precedence
        # over the older `furigana` key when both are present.
        if "romanization" in mb:
            argv += _resolve_modify_romanization(mb.pop("romanization"))
            mb.pop("furigana", None)  # romanization wins; drop the legacy key
        elif "furigana" in mb:
            argv += _resolve_modify_furigana(mb.pop("furigana"))
        # Canonical: reading_format.
        # Aliases: furigana_output_format, romanization_output_format,
        #          furigana_format, format.
        out_fmt = (
            mb.pop("reading_format", None)
            or mb.pop("romanization_output_format", None)
            or mb.pop("furigana_output_format", None)
            or mb.pop("furigana_format", None)
            or mb.pop("format", None)
        )
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
            "--languages": ("languages", None),
            "--langs": ("languages", None),
            "-l": ("languages", None),
            "--release-source": ("release_source", None),
            "--layout": ("layout", None),
            "--run": ("run", True),
        },
        "translate": {
            "--mt-source": ("mt_source", None),
            "--mt-source-lang": ("mt_source", None),
            "--engine": ("engine", None),
            "--mt-engine": ("engine", None),
            "--model": ("model", None),
            "--mt-model": ("model", None),
            "--force": ("force", True),
        },
        "modify": {
            "--strip-cc-noise": ("strip_cc_noise", True),
            "--single-line": ("single_line", True),
            "--furigana": ("furigana", "hiragana"),  # bare → mode default
            "--reading-format": ("reading_format", None),
            "--furigana-format": ("reading_format", None),
            "--convert": ("convert", None),
            "--force": ("force", True),
        },
        "merge": {
            "-l": ("languages", None),
            "--langs": ("languages", None),
            "--languages": ("languages", None),
            "--master": ("master", None),
            "--sync": ("sync", None),
            "--furigana": ("furigana", True),
            "--format": ("format", None),
            "--force": ("force", True),
            "--preserve-lines": ("preserve_lines", True),
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
              getsubtitle URL -s 1 -e all -l ja --romanization ja:hiragana --single
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
                -l ja,ko,en,es --mt-engine argos

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
    search.add_argument("-l", "--languages", "--langs", "--lang", dest="langs", default="ja", metavar="CODES", help="Comma-separated language codes. Default: ja. Accepts ISO codes (ja,en) or full names (japanese,english). Example: ja,en,es")
    search.add_argument("--title", metavar="TEXT", help="Title override when URL metadata is missing or blocked.")
    search.add_argument("--anilist", type=int, metavar="ID", help="AniList ID override for anime.")
    search.add_argument("--browser", action="store_true", help="Open the URL in your browser first, useful for login/Cloudflare pages.")
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
    # Hidden compat aliases for the pre-v1.1 --furigana flag. New code uses
    # --romanization (which generalises to non-Japanese reading aids).
    learning.add_argument("-f", "--furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help=argparse.SUPPRESS)
    learning.add_argument("--no-furigana", dest="furigana", action="store_const", const=None, help=argparse.SUPPRESS)
    learning.add_argument("--reading-format", "--format", "--furigana-format", "--romanization-format", dest="furigana_format", metavar="CODES", help="Reading-aid output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt. Overrides [modify].reading_format from user_settings.toml.")
    learning.add_argument("-furigana", dest="furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help=argparse.SUPPRESS)
    learning.add_argument("--romanization", "--romanize", metavar="SPEC", help="Generate per-language reading aids from downloaded SRTs. SPEC is a comma list of LANG:MODE pairs, e.g. 'ja:hiragana' or 'ja:hiragana|romaji'. Japanese ships now; other languages land per the roadmap.")
    learning.add_argument("--no-romanization", dest="romanization", action="store_const", const="", help="Disable romanization side-file generation for this run.")
    learning.add_argument("--single-line", "--single", action="store_true", default=False, help="Flatten SRT cues to one text line for cleaner asbplayer display. On by default; this flag is kept as an explicit readability marker.")
    learning.add_argument("--no-single-line", "--preserve-lines", dest="single_line", action="store_false", help="Keep each downloaded SRT's original line breaks (disables the default single-line flattening).")
    learning.add_argument("-single-line", "-single", dest="single_line", action="store_true", help=argparse.SUPPRESS)
    learning.add_argument("--strip-cc-noise", action="store_true", default=False, help="Remove broadcast closed-caption noise from downloaded SRTs (currently: Japanese continuation arrows ➡). On by default; this flag is kept as an explicit readability marker.")
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
        "strip_furigana_before_mt": True,
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
        # Tristate: "off" | "hiragana" | "romaji". Replaces the old
        # [furigana].enabled+mode pair.
        "furigana": "hiragana",
        "furigana_output_format": "srt",
    },
    "merge": {
        # Target language (ja) on top, English (likely native) below.
        # Western learners are the largest audience; override for other targets.
        "languages": "ja,en",
        "sync": "auto",
        "preserve_lines": False,
        "priority": [],
        # Inline 漢字（かんじ） readings into the merged ja line.
        # Was [furigana].combine under the old schema.
        "furigana": True,
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
    """Reject any top-level section that isn't part of the v1.1 schema.
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
    # mt_source accepts string ("ja" / "ko:ja,es:en") or dict ({ko = "ja"}).
    # mt_source_lang remains a silent alias for back-compat.
    _mt_source_key = "mt_source" if "mt_source" in tr else ("mt_source_lang" if "mt_source_lang" in tr else None)
    if _mt_source_key is not None:
        val = tr[_mt_source_key]
        if isinstance(val, str):
            tr_out["mt_source_lang"] = val
        elif isinstance(val, dict):
            tr_out["mt_source_lang"] = val   # left as dict; _normalize_mt_source converts at use
        else:
            raise CliError(f"translate.{_mt_source_key}: expected string or dict")
    if "strip_furigana_before_mt" in tr:
        tr_out["strip_furigana_before_mt"] = _validate_bool(
            tr["strip_furigana_before_mt"], "translate.strip_furigana_before_mt"
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
    if "furigana" in m:
        val = m["furigana"]
        if isinstance(val, bool):
            m_out["furigana"] = val
        elif isinstance(val, str) and val.lower() in {"off", "hiragana", "romaji", "true", "false", "on", "yes", "no", "none"}:
            m_out["furigana"] = val.lower()
        else:
            raise CliError("modify.furigana: expected off | hiragana | romaji (or bool)")
    # `reading_format` (canonical) — aliases: `furigana_output_format`, `format`.
    _reading_fmt_key = next(
        (k for k in ("reading_format", "furigana_output_format", "format") if k in m),
        None,
    )
    if _reading_fmt_key is not None:
        if not isinstance(m[_reading_fmt_key], str):
            raise CliError(f"modify.{_reading_fmt_key}: expected string (srt, ass, vtt, or 'all')")
        parse_furigana_formats(m[_reading_fmt_key])
        m_out["furigana_output_format"] = m[_reading_fmt_key]
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
    for bk in ("preserve_lines", "furigana"):
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

[translate]
engine = "argos"                  # "" | argos | ollama[:model] | deepl
model = "qwen3:4b"                # default Ollama model
mt_source = "auto"                # "auto" | "ja" | "ko:ja,es:en" | { ko = "ja" }
strip_furigana_before_mt = true   # strip 漢字（かんじ） readings before MT

[translate.ollama_models]
auto_load = true                  # pull missing models on demand
auto_unload = true                # free model from RAM/VRAM after MT
# Per-pair Ollama model overrides (uncomment to use):
# "ja:ko" = "qwen3:4b"
# "ja:en" = "qwen3:8b"
# "en:es" = "llama3.2:3b"

[modify]
single_line = true                # asbplayer-friendly one-line cues
strip_cc_noise = true             # remove broadcast ➡ continuation arrows
furigana = "hiragana"             # off | hiragana | romaji
reading_format = "srt"            # srt | ass | vtt | all (alias: furigana_output_format)

[merge]
languages = "ja,en"
sync = "auto"                     # auto | strict | loose
preserve_lines = false
priority = []                     # e.g. ["ja", "en", "ko"]
furigana = true                   # inline ja readings into merged output

[output]
target = "~/Movies/Subtitles"
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
    # furigana tristate → only "off"/false skips the side files.
    fur_mode = mod_cfg.get("furigana", False)
    if isinstance(fur_mode, str) and fur_mode.lower() not in ("off", "false", "none", "no", ""):
        overrides["furigana"] = fur_mode if fur_mode in ("hiragana", "romaji") else "hiragana"
    elif fur_mode is True:
        overrides["furigana"] = "hiragana"
    if mod_cfg.get("furigana_output_format"):
        overrides["furigana_format"] = mod_cfg["furigana_output_format"]
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
    out_cfg = cfg.get("output", {})
    if out_cfg.get("force"):
        overrides["force"] = True

    # Inline ja furigana into merged output when [merge].furigana is true.
    if mg.get("furigana", False):
        mod_cfg = cfg.get("modify", {})
        fur_mode = mod_cfg.get("furigana", "hiragana")
        if isinstance(fur_mode, str) and fur_mode in ("hiragana", "romaji"):
            overrides["furigana"] = fur_mode
        elif fur_mode is True:
            overrides["furigana"] = "hiragana"
        else:
            overrides["furigana"] = "hiragana"
    mod = cfg.get("modify", {})
    if mod.get("furigana_output_format"):
        overrides["furigana_format"] = mod["furigana_output_format"]

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


HELP_MAIN = """\
getsubtitle — Find and prepare subtitles for language learning.

Quick start:
  getsubtitle -i                                  # interactive wizard (recommended for first run)
  getsubtitle URL                                 # download from a URL
  getsubtitle merge PATH -l ja,en                 # stack downloaded SRTs
  getsubtitle --config FILE.toml                  # run a saved workflow

Subcommands (each has its own --help):
  interactive   Guided wizard — asks 11 questions, then prints / saves / runs.
  fetch         Download from URL, or scan a folder. (Bare URL works too.)
  translate     Fill missing-language SRTs via MT (argos / ollama / deepl).
  modify        Cleanup, romanization (furigana / pinyin / jyutping / hangul / …), SAMI→SRT conversion.
  merge         Stack 2+ language SRTs into one study file.
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
  getsubtitle --help interactive | config | keys | furigana | sources | advanced

New here? Try `getsubtitle -i` for a guided setup wizard.
"""


HELP_TOPICS: dict[str, str] = {
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
    "furigana": """\
Generate Japanese reading helpers.

Furigana is the Japanese-specific case of getsubtitle's reading-aid
system. For other languages (Korean romanization, Chinese pinyin,
Cantonese jyutping, Thai/Arabic/Hindi/etc. transliterations), use the
generalized --romanization flag instead — see `getsubtitle --help modify`
and the ROADMAP. Japanese is what ships today; other backends land in
v1.1+ per the roadmap.

Usage (Japanese — works today):
  getsubtitle URL -l ja --romanization ja:hiragana
  getsubtitle merge PATH -l ja,en --romanization ja:hiragana
  getsubtitle modify FOLDER --romanization ja:hiragana

Multi-mode side files (pipe shorthand):
  getsubtitle modify FOLDER --romanization "ja:hiragana|romaji"   # both side files

Examples:
  getsubtitle URL -l ja -furigana
  getsubtitle URL -l ja -furigana romaji
  getsubtitle URL -l ja -furigana --single
  getsubtitle merge PATH -l ja,en --romanization ja:hiragana

Modes:
  hiragana                 Default for `ja:true`. 漢字（かんじ）
  romaji                   漢字（kanji）

Output formats (--format / --romanization-format):
  srt                      Default. Broadly compatible; inline parenthetical
                           readings. One file per episode. Safest fallback.
  ass                      Stacked-line ASS. Experimental; player support varies.
  vtt                      Ruby VTT (<ruby><rt>). Works in asbplayer when
                           Settings > Misc > Subtitles > Subtitle HTML is Render.
                           Detect and Display Ruby is optional for mouseover/
                           auto-pause behavior.
  all                      Generate all three. Same as srt,ass,vtt.

Examples:
  getsubtitle URL -l ja --romanization ja:hiragana                       # just srt
  getsubtitle URL -l ja --romanization ja:hiragana --format srt,ass      # srt + ass
  getsubtitle URL -l ja --romanization ja:hiragana --format all          # all three
  getsubtitle modify FOLDER --romanization ja:hiragana --format srt      # existing files

Set defaults in user_settings.toml:
  [modify]
  romanization = "ja:hiragana"         # also: "ja:hiragana, ko:true" (Korean — v1.1)
  romanization_output_format = "srt"   # srt | ass | vtt | all (or comma list)

  [merge]
  romanization = true                  # inline reading aids on the merged ja line

  [translate]
  strip_furigana_before_mt = true      # strip 漢字（かんじ） readings before MT
                                       # (default true; only meaningful for ja sources)

Use --no-romanization to disable a configured default for one command.
Use --format to override side-file formats per run.

MT-source notes:
  When a .ja.srt has inline 漢字（かんじ） readings and is used as an MT
  source (translate or fetch --mt-engine), strip_furigana_before_mt=true
  (the default) removes the parentheticals before sending to the engine.
  Prevents output like "Specifically (especially) the legs (legs) ..."
  caused by the engine translating the readings as extra content. The
  normal pipeline keeps furigana in side files only, so this is a
  defence for third-party or hand-edited Japanese sources.

Output notes:
  SRT is the safest fallback across players.
  VTT gives true furigana in asbplayer with Subtitle HTML set to Render.
  ASS support depends on the player.
  Furigana is added only for Japanese text. For non-Japanese reading
  aids, use --romanization (see `getsubtitle --help modify`).
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
  getsubtitle translate ~/Movies/Subtitles/MF\\ Ghost -l ja,en --engine argos
  getsubtitle translate FOLDER -s 1 -e 11 -l en --engine deepl
  getsubtitle translate FOLDER -l ja,en,es --engine deepl --dry-run
  getsubtitle translate FOLDER -s 1 -e 1-3 -l en --mt-source ja --engine ollama --force

Explicit source mapping (per-target):
  # Force en<-ja and es<-en regardless of what auto-pick would do.
  getsubtitle translate FOLDER -l ja,en,es --engine argos --mt-source en:ja,es:en
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
  --mt-source CODE         Force translation source language (default: auto)
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
  getsubtitle modify FOLDER --romanization ja:hiragana          # Japanese furigana
  getsubtitle modify FOLDER --romanization ja:romaji            # Japanese romaji
  getsubtitle modify FOLDER --romanization "ja:hiragana|romaji" # both side files
  getsubtitle modify FOLDER --convert smi-to-srt
  getsubtitle modify FOLDER --convert smi-to-srt --force
  getsubtitle modify FOLDER --strip-cc-noise --single-line --romanization ja:hiragana --dry-run

Operations (run in this order; pick at least one):
  --convert PAIR           Convert subtitle file format. Currently supports:
                             smi-to-srt — Microsoft SAMI .smi → one sibling
                             .<lang>.srt per language found inside the file.
                             SAMI Class attributes (KRCC, ENCC, JPCC, ...) map
                             to ko/en/ja/etc.; unknown classes default to ko.
                             Encoding is auto-detected (UTF-8/UTF-16/CP949).
  --strip-cc-noise         Remove broadcast CC noise (➡ continuation arrows)
                           in place. Idempotent.
  --single-line, --single  Flatten each cue to one text line in place.
                           Idempotent. Useful for asbplayer.
  --romanization SPEC      Generate per-language reading aids. SPEC is a
                           comma list of LANG:MODE pairs.
                             ja:hiragana, ja:katakana, ja:romaji   (Japanese)
                             ja:hiragana|romaji                    (both side files)
                             ko:true | ko:revised                  (Korean — soon)
                             zh:true | zh:marks | zh:numbers       (pinyin — soon)
                             yue:true | yue:numbers                (jyutping — soon)
                           "true" picks the language's sensible default.
                           Japanese (furigana / romaji) ships now; other
                           languages land per-language as backends arrive
                           (see ROADMAP).
  --no-romanization        Disable reading-aid generation for this run.
  --format CODES           Which reading-aid side files to generate. Comma
                           list of srt, ass, vtt, or 'all'. Default: srt.
                           (Also accepts --romanization-format.)

Other:
  --force                  With --convert: overwrite existing sibling .srt files.
                           Without --force, conversion skips targets that
                           already exist (protects human-quality .ko.srt etc.).
  --dry-run                Show what would change; write nothing.

Composes with the other subcommands:
  getsubtitle modify    FOLDER --convert smi-to-srt
  getsubtitle translate FOLDER -l ja,en --mt-engine argos
  getsubtitle modify    FOLDER --strip-cc-noise --single-line --romanization ja:hiragana
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

  [fetch]         languages, release_source
  [translate]     engine, model, mt_source, strip_furigana_before_mt
                  [translate.ollama_models] — per-pair model overrides +
                                              auto_load / auto_unload flags
  [modify]        single_line, strip_cc_noise, furigana, reading_format
  [merge]         languages, sync, preserve_lines, priority, furigana
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
  getsubtitle fetch ~/Movies/Subtitles/MF\\ Ghost --run
  getsubtitle fetch "~/Movies/유포니움/1기" --profile ja --run

Examples (PATH library-walk form):
  getsubtitle fetch ~/Movies/Subtitles --subdirectory          # dry-run
  getsubtitle fetch ~/Movies/Subtitles --subdirectory --run    # do it

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
  -o, --output DIR         Output folder. Default: ~/Movies/Subtitles
  --layout MODE            archive, flat, or plex. Default: archive
  --title TEXT             Title override when URL metadata is missing
  --anilist ID             AniList ID override for anime
  --browser                Open URL first for login/Cloudflare pages
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
  getsubtitle merge ~/Movies/Subtitles/MF\\ Ghost -l ja,en
  getsubtitle merge ~/Movies/Subtitles/MF\\ Ghost -l ja,en --master ja --romanization ja:hiragana
  getsubtitle merge ~/Movies/Subtitles --subdirectory -l ja,en --format vtt

Merge options:
  -l, --langs CODES        Required. Language order for output
  -o, --output DIR         Output folder. Default: beside master subtitle
  --dry-run                Show merge plan without writing files
  --force                  Overwrite existing outputs and allow low-confidence matches
  --open-folder            Open output folder after writing
  --no-open-folder-prompt  Do not ask whether to open output folder
  --format FORMAT          srt or vtt. vtt can render ruby reading aids in asbplayer
  --sync MODE              auto, strict, or loose. Default: auto
  --master LANG            Timing master. Default: first language in -l
  --single-line, --single  Flatten each language to one line. Default behavior
  --preserve-lines         Keep original line breaks within each language
  --romanization SPEC      Inline reading aids on the matching language line
                           (e.g. `ja:hiragana` inlines 漢字（かんじ） onto ja cues).
                           See `getsubtitle --help modify` for the full SPEC syntax.
  --subdirectory           Walk immediate subdirs and run merge per show

Notes:
  - First language in -l is the timing master unless --master is set.
  - Input formats: srt, vtt, ass/ssa, smi. Use -l ja:vtt,en,ko:smi when
    multiple formats exist for the same language.
  - --romanization ja:hiragana inlines Japanese readings before merging.
  - --sync auto|strict|loose controls how strictly cues match.
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
              --output ~/Movies/StudyDeck

  # Just fetch + merge (no MT), single show.
  getsubtitle --fetch ~/Movies/Subtitles/MF\\ Ghost \\
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
  languages = "japanese,english,korean"
                                   # full names normalize to ja,en,ko;
                                   # alias keys: `langs`, `language`

  [translate]
  engine = "ollama"                # required: argos | ollama[:model] | deepl
  mt_source = { ko = "ja", es = "en", ja = "ko" }
                                   # per-target source map (dict form);
                                   # comma-string `mt_source = "ko:ja,es:en"` also works
                                   # (`mt_source_lang` kept as alias)
  "ja:ko" = "qwen3:4b"             # per-pair Ollama models (session-only;
  "en:es" = "llama3.2:3b"          # don't touch user_settings.toml)

  [modify]
  strip_cc_noise = true
  single_line = true
  furigana = "hiragana"            # off | hiragana | romaji
  reading_format = "all"           # srt | ass | vtt | all
                                   # aliases: furigana_output_format, format
  convert = "smi-to-srt"           # or "none"

  [merge]
  languages = "ja:vtt, en, ko:smi" # `:format` is an INPUT hint when multiple
                                   # source formats exist on disk for one lang
                                   # (supports :srt, :vtt, :ass, :ssa, :smi)
  master = "ja"
  sync = "strict"                  # auto | strict | loose
  furigana = true                  # inline 漢字（かんじ） into the merged ja line
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
  - Canonical TOML keys (v1.1):
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

Walks through a guided Q&A and produces one of three things:
  1. The equivalent CLI command (copy-paste ready, shell-quoted)
  2. A reusable TOML workflow (same schema as --config FILE.toml)
  3. A live run (with a dry-run preview first)

What it asks:
  Q1.  URL or folder
  Q2.  Languages to collect (comma list: ja,en,ko,es,…)
  Q3.  Display order (top → bottom on screen)
  Q4.  Which language controls timing (default: first displayed)
  Q5.  Episode scope (URL only): movie / season+episode / all / auto
  Q6.  MT fallback for missing languages: argos / ollama / deepl / skip
  Q7.  Reading aids — phonetic guides above the original script:
         ja:hiragana / ja:romaji            (★ ships now)
         ko:revised / ko:yale               (☆ wired through; backend coming)
         zh:marks / zh:numbers              (☆ wired through; backend coming)
         yue:numbers (jyutping)             (☆ wired through; backend coming)
         th:royal-thai / ar:ala-lc / etc.   (☆ wired through; backend coming)
  Q8.  asbplayer preset (single-line + cleanup + ruby VTT)
  Q9.  Final format: SRT / VTT / ASS
  Q10. Output folder
  Q11. Print CLI / Save TOML / Run now / Edit answers

After Q10 the wizard probes your environment for missing pieces — the
pykakasi package for Japanese furigana, the Ollama daemon if you picked
ollama MT, the DeepL key if you picked DeepL, missing Jimaku/Wyzie/TMDB
keys — and walks you through fixing each gap before the final action.

Limitations:
  - Requires an attached terminal (fails cleanly otherwise).
  - One language alone skips Q3/Q4 and the merge step.
  - Korean / Chinese / Cantonese / Thai / Arabic / Hindi / Russian
    reading-aid backends are not yet shipped; the wizard still accepts
    and saves them so you can re-run once the backend lands.

Tips:
  - Press 'q' at any prompt to quit; answers are auto-saved to
    ~/.cache/getsubtitle/wizard-draft.toml so you can resume later.
  - The wizard generates the v1.1 canonical names everywhere
    (--languages, --engine, --mt-source, --romanization, --reading-format
    on the CLI; mt_source / reading_format in TOML).
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
  --strip-cc-noise         Remove broadcast closed-caption noise (currently: ➡)
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
    if argv[0] in ("merge", "fetch", "sources"):
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
# Interactive wizard
# ═══════════════════════════════════════════════════════════════════════
# `getsubtitle --interactive` (or `getsubtitle interactive`, or `-i`) walks
# a new user through a workflow and produces a CLI command, a saved TOML,
# or a live run. Generated artifacts use the v1.1 canonical names
# (--languages, --engine, --mt-source, --romanization, --reading-format
# on the CLI; mt_source / reading_format in TOML).
#
# Romanization options exposed by the wizard cover every language in
# _ROMANIZATION_DEFAULTS — Japanese ships now, Korean / Chinese /
# Cantonese / Thai / Arabic / Hindi / Russian land per ROADMAP. The
# wizard accepts those choices and emits the same `--romanization`
# spec the CLI/TOML already validate; the parser raises a clear
# "not yet implemented" error at run time for the deferred languages.

_WIZARD_DRAFT_FILENAME = "wizard-draft.toml"


# Per-language reading-aid menu. Each row: (lang_iso, spec_value, label,
# is_shipping). `spec_value` is what we splice into the --romanization
# spec (e.g. "ja:hiragana"). `is_shipping` controls whether we warn.
_WIZARD_READING_AID_MENU: list[tuple[str, str, str, bool]] = [
    ("ja", "ja:hiragana",       "Japanese — hiragana furigana above kanji", True),
    ("ja", "ja:romaji",         "Japanese — romaji above kanji",            True),
    ("ko", "ko:revised",        "Korean — Revised Romanization (G2P)",      False),
    ("ko", "ko:yale",           "Korean — Yale Romanization",               False),
    ("zh", "zh:marks",          "Mandarin — pinyin with tone marks",        False),
    ("zh", "zh:numbers",        "Mandarin — pinyin with numbered tones",    False),
    ("yue", "yue:numbers",      "Cantonese — jyutping with numbered tones", False),
    ("th", "th:royal-thai",     "Thai — Royal Thai transliteration",        False),
    ("ar", "ar:ala-lc",         "Arabic — ALA-LC romanization",             False),
    ("hi", "hi:iast",           "Hindi — IAST transliteration",             False),
    ("ru", "ru:iso-9",          "Russian — ISO-9 transliteration",          False),
]


class _WizardAbort(Exception):
    """Raised when the user explicitly bails out (Ctrl-C / `q`)."""


def _wizard_is_interactive() -> bool:
    """True iff both stdin and stdout are a terminal. The wizard cannot
    run in a pipeline because every question is a blocking prompt."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _wizard_prompt(question: str, default: str | None = None, *, choices: list[str] | None = None) -> str:
    """Read one answer. Empty input → default (if any). Trims whitespace.

    `choices` is informational — printed alongside the question; we do
    NOT enforce it here (callers validate, since some questions accept
    free-form input on top of suggestions)."""
    suffix = ""
    if default is not None:
        suffix = f" [{default}]"
    while True:
        try:
            raw = input(f"  {question}{suffix} > ").strip()
        except EOFError as e:
            raise _WizardAbort("stdin closed") from e
        if not raw and default is not None:
            return default
        if raw.lower() in ("q", "quit", "exit"):
            raise _WizardAbort("user quit")
        if raw:
            return raw
        print("    (empty answer; please enter something, or 'q' to quit)")


def _wizard_yesno(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        ans = _wizard_prompt(question, suffix).strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        if ans == suffix:
            return default
        # Treat the first character as a guess if the user typed Y/N alone.
        if ans and ans[0] in "yn":
            return ans[0] == "y"
        print("    (please answer y or n)")


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
    source_kind: str = ""                  # "url" | "path"
    languages: list[str] = field(default_factory=list)        # Q2
    order: list[str] = field(default_factory=list)            # Q3
    master: str = ""                       # Q4: "" | lang code | "auto"
    season: str = ""                       # Q5
    episode: str = ""                      # Q5
    mt_engine: str = ""                    # Q6: "" | argos | ollama | deepl
    reading_aids: list[str] = field(default_factory=list)     # Q7: spec entries
    asbplayer: bool = False                # Q8
    format: str = ""                       # Q9: srt | vtt | ass
    output: str = ""                       # Q10
    final_action: str = "print"            # Q11: print | run | save | edit
    save_path: str = ""                    # Q11 sub-prompt

    def to_toml(self) -> str:
        """Serialize as a TOML draft for resume support. Quick-and-dirty
        — only strings and bools; lists become comma-joined strings."""
        lines = ["# getsubtitle wizard draft — auto-saved; safe to delete.\n"]
        lines.append("[wizard]\n")
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool):
                lines.append(f'{f.name} = {"true" if v else "false"}\n')
            elif isinstance(v, list):
                lines.append(f'{f.name} = "{",".join(v)}"\n')
            else:
                lines.append(f'{f.name} = "{v}"\n')
        return "".join(lines)


# ─── Wizard questions Q1-Q11 ────────────────────────────────────────────

def _wizard_q1_source(state: _WizardState) -> None:
    """Q1: URL or PATH. We auto-detect by sniffing for `://`."""
    print()
    print("Q1. What should getsubtitle work on?")
    print("    a) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)")
    print("    b) A folder or file on disk (your Plex/Movies, ~/Downloads, …)")
    src = _wizard_prompt("Paste a URL or filesystem path")
    state.source = src
    state.source_kind = "url" if _looks_like_url(src) else "path"


def _wizard_q2_languages(state: _WizardState) -> None:
    print()
    print("Q2. Which subtitle languages do you want to collect?")
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


def _wizard_q3_order(state: _WizardState) -> None:
    """Confirm display order; only branch into custom-order on 'no'."""
    if len(state.languages) <= 1:
        state.order = list(state.languages)
        return
    default_order = ",".join(state.languages)
    print()
    print("Q3. Subtitle display order (top → bottom on screen).")
    print(f"    Default: {default_order}")
    print("    'ja,en' = Japanese on top, English below.")
    keep = _wizard_yesno(f"Keep order {default_order}?", default=True)
    if keep:
        state.order = list(state.languages)
        return
    raw = _wizard_prompt("Custom order (comma-separated, top → bottom)", default_order)
    order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    order = [LANGUAGE_ALIASES.get(p, p) for p in order]
    # Must be a permutation of Q2's languages.
    if set(order) != set(state.languages):
        raise CliError(
            "interactive: display order must contain the same languages as Q2 "
            f"({','.join(state.languages)})."
        )
    state.order = order


def _wizard_q4_master(state: _WizardState) -> None:
    if len(state.order) <= 1:
        state.master = ""
        return
    print()
    print("Q4. Which language controls cue timing (the 'master' track)?")
    print(f"    a) First displayed — {state.order[0]} (recommended)")
    print("    b) Japanese (if collected)")
    print("    c) Custom")
    pick = _wizard_prompt("Choose a/b/c", "a").lower()
    if pick.startswith("a"):
        state.master = ""  # default — first language wins
    elif pick.startswith("b"):
        if "ja" not in state.order:
            print("    (Japanese isn't in your list; falling back to first.)")
            state.master = ""
        else:
            state.master = "ja"
    elif pick.startswith("c"):
        raw = _wizard_prompt("Master language code", state.order[0])
        cand = LANGUAGE_ALIASES.get(raw.lower(), raw.lower())
        if cand not in state.order:
            raise CliError(f"interactive: master {cand!r} must be one of {state.order}.")
        state.master = cand
    else:
        state.master = ""


def _wizard_q5_scope(state: _WizardState) -> None:
    """Episode scope — only when source is a URL."""
    if state.source_kind != "url":
        state.season = ""
        state.episode = ""
        return
    print()
    print("Q5. What episode scope?")
    print("    a) Movie / single item (no season/episode)")
    print("    b) A specific season + episode (or range)")
    print("    c) Whole season, every episode (-e all)")
    print("    d) Auto (let getsubtitle infer)")
    pick = _wizard_prompt("Choose a/b/c/d", "d").lower()
    if pick.startswith("a"):
        state.season = ""
        state.episode = ""
    elif pick.startswith("b"):
        state.season = _wizard_prompt("Season (e.g. 1 or 1-3)", "1")
        state.episode = _wizard_prompt("Episode (e.g. 1 or 3-5)", "1")
    elif pick.startswith("c"):
        state.season = _wizard_prompt("Season (e.g. 1)", "1")
        state.episode = "all"
        # Non-anime TV needs TMDB to expand -e all. Heads-up only.
        if "anilist" not in state.source.lower() and "myanimelist" not in state.source.lower():
            print("    (Note: -e all on non-anime TV requires a TMDB key. "
                  "Run `getsubtitle --set-key tmdb` later if needed.)")
    else:
        state.season = ""
        state.episode = ""


def _wizard_q6_translate(state: _WizardState) -> None:
    print()
    print("Q6. If a language isn't downloadable, what should we do?")
    print("    a) Skip — accept gaps (no MT)")
    print("    b) Argos — offline, free, gist-level quality (default)")
    print("    c) Ollama — offline LLM, good quality (needs daemon + model)")
    print("    d) DeepL — online, best quality (free tier; needs API key)")
    pick = _wizard_prompt("Choose a/b/c/d", "a").lower()
    state.mt_engine = {"a": "", "b": "argos", "c": "ollama", "d": "deepl"}.get(pick[:1], "")


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
    print("Q7. Reading aids (phonetic guides above/beside the original script).")
    print("    Pick any combination by number. Empty = no reading aids.")
    print("    (★ = ships now · ☆ = wired through to CLI/TOML; backend lands per ROADMAP)")
    for i, (lang, spec, label, shipping) in enumerate(relevant, start=1):
        mark = "★" if shipping else "☆"
        print(f"    {i}) {mark} {label}   [{spec}]")
    raw = _wizard_prompt(
        "Numbers (comma-separated), or 'none'",
        "1" if relevant and relevant[0][3] else "none",
    ).lower()
    if raw in ("", "none", "0", "no", "skip"):
        state.reading_aids = []
        return
    picks: list[str] = []
    deferred_seen: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        idx = int(tok) - 1
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
    print("Q8. Optimize output for asbplayer (the common asbplayer setup is")
    print("    single-line cues + cleaned broadcast noise + ruby VTT for")
    print("    furigana)?")
    state.asbplayer = _wizard_yesno("Apply asbplayer preset?", default=True)


def _wizard_q9_format(state: _WizardState) -> None:
    needs_ruby = any(spec.startswith("ja:hiragana") or spec.startswith("ja:furigana")
                     for spec in state.reading_aids)
    default = "vtt" if (state.asbplayer and needs_ruby) else "srt"
    print()
    print("Q9. Final output format.")
    print("    a) SRT  — most compatible (default if no ruby/furigana)")
    print("    b) VTT  — required for asbplayer ruby furigana")
    print("    c) ASS  — experimental")
    pick = _wizard_prompt("Choose a/b/c", {"vtt": "b", "srt": "a"}.get(default, "a")).lower()
    state.format = {"a": "srt", "b": "vtt", "c": "ass"}.get(pick[:1], default)
    if needs_ruby and state.format != "vtt":
        print("    Note: hiragana furigana looks best as VTT ruby. "
              "SRT will fall back to parenthetical 漢字（かんじ） form.")
    if state.format == "vtt" and state.asbplayer and needs_ruby:
        print("    Reminder: asbplayer needs Settings > Misc > Subtitles > "
              "Subtitle HTML = Render.")


def _wizard_q10_output(state: _WizardState) -> None:
    print()
    print("Q10. Where should the final files go?")
    print("    a) Default — ~/Movies/Subtitles")
    print("    b) Same folder as the source files (in-place)")
    print("    c) Custom folder")
    pick = _wizard_prompt("Choose a/b/c", "a").lower()
    if pick.startswith("a"):
        state.output = "~/Movies/Subtitles"
    elif pick.startswith("b"):
        state.output = ""  # default downstream = beside source
    else:
        state.output = _wizard_prompt("Output folder", "~/Movies/Subtitles")


def _wizard_q11_action(state: _WizardState) -> str:
    """Final action. Returns one of 'print', 'run', 'save', 'edit'."""
    print()
    print("Q11. What now?")
    print("    a) Print the equivalent CLI command")
    print("    b) Save as a reusable TOML workflow")
    print("    c) Run it now (dry-run first, then ask to confirm)")
    print("    d) Edit a previous answer")
    pick = _wizard_prompt("Choose a/b/c/d", "a").lower()
    mapping = {"a": "print", "b": "save", "c": "run", "d": "edit"}
    return mapping.get(pick[:1], "print")


# ─── Orchestrator ──────────────────────────────────────────────────────

# Question dispatch table keeps the orchestrator readable and the test
# harness focused — tests can call individual questions via this table.
_WIZARD_STEPS: list[tuple[str, "callable"]] = [
    ("source",        _wizard_q1_source),
    ("languages",     _wizard_q2_languages),
    ("order",         _wizard_q3_order),
    ("master",        _wizard_q4_master),
    ("scope",         _wizard_q5_scope),
    ("translate",     _wizard_q6_translate),
    ("reading_aids",  _wizard_q7_reading_aids),
    ("asbplayer",     _wizard_q8_asbplayer),
    ("format",        _wizard_q9_format),
    ("output",        _wizard_q10_output),
]


def _run_wizard(state: _WizardState | None = None) -> tuple[_WizardState, str]:
    """Run Q1-Q10, then loop on Q11 until a final action is chosen.
    Returns (state, final_action). Caller owns dispatching the action."""
    state = state or _WizardState()
    for label, fn in _WIZARD_STEPS:
        fn(state)
        _wizard_save_draft(state)
    while True:
        action = _wizard_q11_action(state)
        if action != "edit":
            state.final_action = action
            return state, action
        # Edit flow: list answers, jump to specific question.
        print()
        print("Your answers so far:")
        for i, (label, _) in enumerate(_WIZARD_STEPS, start=1):
            v = getattr(state, _WIZARD_STEPS[i - 1][0], "")
            print(f"  Q{i}. {label}: {v!r}")
        pick = _wizard_prompt("Question number to redo (1-10), or 'done'", "done").lower()
        if pick.isdigit():
            idx = int(pick) - 1
            if 0 <= idx < len(_WIZARD_STEPS):
                _WIZARD_STEPS[idx][1](state)
                _wizard_save_draft(state)


# ─── Emitters: CLI command + TOML workflow ────────────────────────────

def _wizard_emit_cli(state: _WizardState) -> list[str]:
    """Build a canonical-form argv list for the wizard's answers.

    Uses the v1.1 long names: --languages, --engine, --mt-source,
    --romanization (NOT --furigana). Output is suitable for shell-quoting
    via shlex.join."""
    argv: list[str] = ["getsubtitle"]
    # Pipeline form. We always emit --fetch X so URL vs path is captured
    # uniformly and downstream verbs are explicit.
    argv += ["--fetch", state.source]
    if state.source_kind == "url" and state.season:
        argv += ["--season", state.season]
    if state.source_kind == "url" and state.episode:
        argv += ["--episode", state.episode]
    if state.languages:
        argv += ["--languages", ",".join(state.languages)]
    if state.mt_engine:
        argv += ["--translate", state.mt_engine]
    # Modify block — only emit when something inside it is on. Saves
    # noise in the printed command.
    if state.reading_aids or state.asbplayer:
        argv.append("--modify")
        if state.asbplayer:
            argv += ["--strip-cc-noise", "--single-line"]
        if state.reading_aids:
            argv += ["--romanization", ",".join(state.reading_aids)]
            # Reading-format mirrors the merge format when ruby is in play.
            if state.format == "vtt":
                argv += ["--reading-format", "vtt"]
    # Merge block — only when 2+ languages.
    if len(state.order) >= 2:
        argv += ["--merge", "--languages", ",".join(state.order)]
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


def _wizard_emit_toml(state: _WizardState) -> str:
    """Build a workflow TOML matching --config FILE.toml schema, using
    the v1.1 canonical key names (mt_source, reading_format)."""
    lines: list[str] = []
    lines.append("# Generated by `getsubtitle --interactive`")
    lines.append("# Re-run with: getsubtitle --config THIS_FILE.toml\n")
    # [fetch]
    lines.append("[fetch]")
    lines.append(f'source = "{state.source}"')
    if state.source_kind == "url":
        if state.season:
            lines.append(f'season = "{state.season}"')
        if state.episode:
            lines.append(f'episode = "{state.episode}"')
    if state.languages:
        lines.append(f'languages = "{",".join(state.languages)}"')
    lines.append("")
    # [translate]
    if state.mt_engine:
        lines.append("[translate]")
        lines.append(f'engine = "{state.mt_engine}"')
        lines.append('mt_source = "auto"')
        lines.append("")
    # [modify]
    has_modify = bool(state.reading_aids or state.asbplayer)
    if has_modify:
        lines.append("[modify]")
        if state.asbplayer:
            lines.append("single_line = true")
            lines.append("strip_cc_noise = true")
        if state.reading_aids:
            lines.append(f'romanization = "{",".join(state.reading_aids)}"')
            if state.format == "vtt":
                lines.append('reading_format = "vtt"')
        lines.append("")
    # [merge]
    if len(state.order) >= 2:
        lines.append("[merge]")
        lines.append(f'languages = "{",".join(state.order)}"')
        if state.master:
            lines.append(f'priority = ["{state.master}"]')
        lines.append('sync = "auto"')
        if state.format:
            lines.append(f'format = "{state.format}"')
        lines.append("")
    # [output]
    if state.output:
        lines.append("[output]")
        lines.append(f'target = "{state.output}"')
        lines.append('layout = "archive"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    # Non-Japanese reading aids — backends not shipped yet.
    deferred = [s for s in state.reading_aids if not s.startswith("ja:")]
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
    if state.source_kind == "url":
        wants_ja = "ja" in state.languages
        if wants_ja and not get_provider_api_key("jimaku"):
            out.append(("warn", "Jimaku API key (Japanese anime)",
                        "getsubtitle --set-key jimaku"))
        wants_non_ja = any(lang != "ja" for lang in state.languages)
        if wants_non_ja and not get_provider_api_key("wyzie"):
            out.append(("warn", "Wyzie API key (movies / non-anime TV)",
                        "getsubtitle --set-key wyzie"))
        if state.episode == "all" and not get_provider_api_key("tmdb") and \
           "anilist" not in state.source.lower() and \
           "myanimelist" not in state.source.lower():
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


# ─── Entry point ───────────────────────────────────────────────────────

_WIZARD_INTRO = """
getsubtitle — interactive workflow builder

I'll ask a few questions, then either print the CLI command, save a
reusable TOML workflow, or run it now. You can press 'q' at any prompt
to quit, or Ctrl-C to bail.
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
    state = _WizardState()
    try:
        state, action = _run_wizard(state)
    except _WizardAbort:
        print()
        print("Cancelled. (Your answers are saved at " + str(_wizard_draft_path()) + ".)")
        return 130

    # Probe dependencies after the answers are in. Show a status banner
    # whether anything is missing or not.
    gaps = _wizard_probe_dependencies(state)
    if gaps:
        print()
        print("Dependency check — issues found:")
        for sev, label, fix in gaps:
            marker = "✗ block" if sev == "block" else "• warn "
            print(f"  {marker}  {label}")
        blockers = [g for g in gaps if g[0] == "block"]
        if blockers and _wizard_yesno("Run setup now to fix these?", default=True):
            _wizard_run_setup(state, gaps)

    cli_string = _wizard_emit_cli_string(state)
    toml_str = _wizard_emit_toml(state)

    print()
    print("Generated CLI:")
    print("  " + cli_string)
    print()
    print("Equivalent TOML workflow:")
    for line in toml_str.splitlines():
        print("  " + line)

    if action == "print":
        _wizard_clear_draft()
        return 0
    if action == "save":
        default_name = "getsubtitle-workflow.toml"
        path_raw = _wizard_prompt("Save to (relative paths OK)", default_name)
        path = Path(path_raw).expanduser()
        if path.exists() and not _wizard_yesno(f"{path} exists. Overwrite?", default=False):
            print("Not saved.")
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(toml_str, encoding="utf-8")
        print(f"Saved: {path}")
        _wizard_clear_draft()
        return 0
    if action == "run":
        # Always dry-run first so the user sees what's about to happen.
        argv_dry = _wizard_emit_cli(state)[1:] + ["--dry-run"]
        print()
        print("Dry-run preview:")
        rc = main(argv_dry)
        if rc != 0:
            print("(Dry-run reported issues — review above before running for real.)")
        if not _wizard_yesno("Run for real?", default=False):
            print("Stopped before live run. Re-run with the printed CLI when ready.")
            return 0
        _wizard_clear_draft()
        return main(_wizard_emit_cli(state)[1:])
    return 0


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
    # --romanization (the v1.1 generalised flag) routes through the legacy
    # --furigana attribute for Japanese; non-Japanese languages raise a
    # clear "not yet implemented" error.
    _apply_romanization_to_args(args)
    if args.reset_key is not None:
        return reset_api_keys(args.reset_key or None)
    if args.set_key is not None:
        return set_api_keys(args.set_key or None)
    if args.reset_jimaku_key:
        return reset_api_keys("jimaku")
    if args.set_jimaku_key:
        return set_api_keys("jimaku")
    if not args.url:
        raise CliError("Missing URL. Run getsubtitle --help for usage.")
    if args.browser:
        open_in_browser(args.url)
        if sys.stdin.isatty():
            input("Browser opened. After the page loads or you identify the show, press Enter to continue...")
        else:
            print("Browser opened. Continuing without waiting because stdin is not interactive.")
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

    anilist_info = fetch_anilist_info(media.anilist_id) if media.anilist_id else None
    if anilist_info:
        if not media.title or (args.anilist and not args.title):
            media.title = anilist_info.title or media.title
        add_media_title_aliases(media, [anilist_info.title, *(anilist_info.title_aliases or [])])
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

    jimaku_provider = JimakuProvider(get_jimaku_api_key()) if media.anilist_id and "ja" in langs else None
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

    if not planned:
        print("\nNo downloads planned.")
        return 1

    print_planned_downloads(planned)

    confirm_bulk(len(planned), args)
    if args.dry_run:
        return 0

    base = Path(args.output).expanduser()
    saved: list[Path] = []
    print("\nDownloading subtitles:")
    for idx, (_lang, ep, sub) in enumerate(planned, start=1):
        progress_bar(idx, len(planned), "downloading", f"episode {ep} {sub.language}", transient=True)
        dest = output_dir(base, media, media.season, args.layout)
        saved.extend(save_subtitle(sub, dest, media, media.season, ep))

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
        translator_cache: dict[tuple[str, str | None], _BaseTranslator] = {}
        # [translate].strip_furigana_before_mt: same defense as translate_main.
        # Default true; only meaningful when an MT source is ja.
        try:
            _cfg_tr = load_user_config().get("translate", {})
        except CliError:
            _cfg_tr = {}
        strip_furigana_before_mt = bool(_cfg_tr.get("strip_furigana_before_mt", True))

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
                    src_lang = forced_source
                    src_path = available.get(src_lang)
                    if not src_path:
                        warnings.append(
                            f"{target} ep{ep}: forced source {src_lang!r} wasn't downloaded "
                            f"this run. Add {src_lang!r} to -l (e.g. -l {src_lang},{target}…) "
                            f"or run `getsubtitle translate FOLDER` on an existing folder."
                        )
                        continue
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
                        strip_furigana=strip_furigana_before_mt,
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

    generated: list[Path] = []
    if args.furigana:
        furigana_sources = [path for path in saved if ".ja" in path.name and path.suffix.lower() == ".srt"]
        if furigana_sources:
            print("\nGenerating furigana:")
            for idx, path in enumerate(furigana_sources, start=1):
                progress_bar(idx, len(furigana_sources), "furigana", path.name, transient=True)
                generated.extend(
                    generate_furigana(
                        [path], args.furigana, args.single_line,
                        formats=parse_furigana_formats(getattr(args, "furigana_format", None)),
                    )
                )
        else:
            generated = []

    print("\nSaved:")
    for path in saved:
        print(f"  {path}")
    if mt_files:
        print("\nMachine-translated (not human-quality — verify before use):")
        for path in mt_files:
            print(f"  {path}")
    if args.furigana:
        if generated:
            print("\nGenerated furigana:")
            for path in generated:
                print(f"  {path}")
        else:
            print("\nFurigana: no .ja.srt files were generated; furigana is currently created from Japanese SRT.")
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
