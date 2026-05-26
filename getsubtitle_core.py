#!/usr/bin/env python3
"""Download and prepare subtitles for language-learning workflows."""

from __future__ import annotations

import argparse
import json
import os
import getpass
import re
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
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable


JIMAKU_API = "https://jimaku.cc/api"
ANILIST_API = "https://graphql.anilist.co"
TMDB_API = "https://api.themoviedb.org/3"
WIKIDATA_SPARQL_API = "https://query.wikidata.org/sparql"
WYZIE_API = "https://sub.wyzie.io/search"
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
    value = result.stdout.strip()
    return value or None


def keychain_set(service: str, account: str, password: str) -> None:
    if not macos_keychain_available():
        raise CliError("Secure key storage is only implemented for macOS Keychain right now; set JIMAKU_API_KEY in your shell instead.")
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
    if value == "all":
        return list(KEY_PROVIDERS)
    providers = [part.strip().lower() for part in value.split(",") if part.strip()]
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


def infer_from_crunchyroll_url(url: str) -> MediaInfo:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    title = None
    episode = "auto"

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

    return MediaInfo(source_url=url, provider="crunchyroll", title=title, episode=episode)


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

    title = None
    if not (parts and parts[0] == "watch"):
        # Watch pages often surface the episode title, not the series title,
        # so we skip the HTML scrape there. Browse/title pages can be useful.
        html = request_text(url)
        if html:
            og = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if og:
                title = clean_page_title(og.group(1))
            if not title:
                mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                if mt:
                    title = clean_page_title(mt.group(1))

    media = MediaInfo(source_url=url, provider="netflix", title=title, netflix_id=netflix_id)

    # Bridge Netflix ID -> IMDb/TMDB/TVDB via Wikidata so downstream providers
    # (Wyzie) and the AniList bridge can take it from there.
    if netflix_id:
        nf_title, imdb_id, tmdb_id, tvdb_id = external_ids_from_netflix_id(netflix_id)
        media.title = media.title or nf_title
        media.imdb_id = media.imdb_id or imdb_id
        media.tmdb_id = media.tmdb_id or tmdb_id
        media.tvdb_id = media.tvdb_id or tvdb_id

    return media


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
                "See: getsubtitle --help download"
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
            f"Use a different installed model with: --mt-model NAME\n"
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
                "  getsubtitle translate PATH -l ko --mt-engine ollama --mt-model NAME"
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
                    "  getsubtitle translate PATH -l ko --mt-engine ollama --mt-model NAME"
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

    Precedence: --mt-model > [translate.ollama_models].src-tgt >
    [translate].model > built-in default.
    """
    if cli_model:
        return cli_model
    source = LANGUAGE_ALIASES.get(source_lang.lower(), source_lang.lower())
    target = LANGUAGE_ALIASES.get(target_lang.lower(), target_lang.lower())
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}
    translate_cfg = cfg.get("translate", {})
    pair_models = translate_cfg.get("ollama_models", {}) or {}
    pair_key = f"{source}-{target}"
    if pair_key in pair_models:
        return str(pair_models[pair_key])
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
    if any(token in value for token in ["bluray", "blu-ray", "bdrip", "brrip"]):
        return "bluray"
    if any(token in value for token in ["web-dl", "webrip", "web "]):
        return "web"
    if "hdtv" in value:
        return "hdtv"
    if "dvd" in value:
        return "dvd"
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


def choose_best(files: list[SubtitleFile], preferred_source: str | None = None) -> SubtitleFile | None:
    if not files:
        return None
    preferred = [".srt", ".ass", ".vtt", ".ssa", ".zip"]
    source = preferred_source.lower() if preferred_source else None

    def score(file: SubtitleFile) -> tuple[int, int, int, int, str]:
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
        ext_score = preferred.index(ext) if ext in preferred else 99
        provider_score = 0 if file.source_provider in {"opensubtitles", "subdl", "podnapisi"} else 1
        return source_score, ai_score, ext_score, provider_score, file.name.lower()

    return sorted(files, key=score)[0]


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
    """Parse --furigana-format (or [furigana].format) into a set of format codes.

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
            f"--furigana-format: unknown format(s): {', '.join(unknown)}. "
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
    r"\.([a-z]{2,3})(\.mt)?(?:\.(?:hi|cc|sdh|forced))?\.srt$",
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
    p.add_argument("-l", "--langs", "--lang", default="ja,ko", metavar="CODES", help="Language order for the output cue stack. First language is the timing master unless --master is set. Default: ja,ko.")
    p.add_argument("-s", "--season", default="all", metavar="N|all", help="Season filter. Default: all detected seasons.")
    p.add_argument("-e", "--episode", default="all", metavar="N|N-M|all", help="Episode filter. Accepts one episode, a range, a comma list, or all. Default: all detected episodes.")
    p.add_argument("-o", "--output", metavar="DIR", help="Output directory. Default: beside each episode's master SRT.")
    p.add_argument("--format", choices=["srt", "vtt"], default="srt", help="Combined output format. srt = broad compatibility; vtt = WebVTT with ruby markup when --furigana is used. Default: srt.")
    p.add_argument("--dry-run", action="store_true", help="Show the plan without writing files.")
    p.add_argument("--force", action="store_true", help="Overwrite existing combined outputs and bypass the episode-level match-rate threshold.")
    p.add_argument("--open-folder", action="store_true", help="Open the output folder after writing.")
    p.add_argument("--no-open-folder-prompt", action="store_true", help="Do not ask whether to open the output folder after writing.")
    p.add_argument("--sync", choices=list(SYNC_PRESETS), default="auto", help="Time-overlap strictness preset. Default: auto.")
    p.add_argument("--master", metavar="LANG", help="Override the timing master language (default: first language in -l).")
    p.add_argument("--single-line", "--single", dest="preserve_lines", action="store_false", default=argparse.SUPPRESS, help="Flatten each language to one line per cue. This is the default; kept as an explicit readability flag.")
    p.add_argument("--preserve-lines", action="store_true", default=argparse.SUPPRESS, help="Keep each source language's original line breaks. Default: flatten each language to a single line.")
    p.add_argument("-f", "--furigana", "-furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help="Inline Japanese readings into ja cues before combining. Default mode when used: hiragana.")
    p.add_argument("--no-furigana", dest="furigana", action="store_const", const=None, help="Disable combine furigana for this run even if enabled in user_settings.toml.")
    p.set_defaults(preserve_lines=False)
    _apply_combine_config_defaults(p)
    return p


def _format_rate(rate: float) -> str:
    return f"{rate * 100:.0f}%"


def combine_main(argv: list[str]) -> int:
    args = build_combine_parser().parse_args(argv)
    langs = split_csv(args.langs, "ja,ko")
    if not langs:
        raise CliError("No languages specified. Use -l ja,ko or similar.")
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

    scanned = scan_srt_files(paths)
    grouped = group_srts_by_episode(scanned)
    output_dir_arg = Path(args.output).expanduser() if args.output else None
    sync_preset = SYNC_PRESETS[args.sync]
    episode_threshold = float(sync_preset["episode_success"])

    print(f"Scanned: {len(scanned)} SRT file(s) across {len(paths)} path(s)")
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

        # Parse SRT bodies.
        try:
            master_cues = parse_srt(files[master_lang].read_text(encoding="utf-8-sig", errors="replace"))
        except Exception as e:
            skipped.append((key, f"could not parse master SRT: {e}"))
            continue
        if not master_cues:
            skipped.append((key, "master SRT has no cues"))
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
                cues = parse_srt(files[lang].read_text(encoding="utf-8-sig", errors="replace"))
            except Exception as e:
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
        overrides["mt_engine"] = tr["engine"]
    if tr.get("model"):
        overrides["mt_model"] = tr["model"]
    src = tr.get("source_lang", "")
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
    p.add_argument("-l", "--langs", "--lang", required=True, metavar="CODES", help="Target languages to ensure exist (e.g. ja,ko,en). Missing ones get MT'd from the best available source SRT.")
    p.add_argument("-s", "--season", default="all", metavar="N|all", help="Season filter. Default: all detected seasons.")
    p.add_argument("-e", "--episode", default="all", metavar="N|N-M|all", help="Episode filter. Accepts one episode, a range, a comma list, or all. Default: all detected episodes.")
    p.add_argument("--mt-engine", choices=["argos", "ollama", "deepl"], help="Translation engine. Default: argos (via [translate].engine in user_settings.toml).")
    p.add_argument("--no-mt-engine", dest="mt_engine", action="store_const", const="", help="Disable machine translation for this run even when [translate].engine is set in user_settings.toml.")
    p.add_argument("--mt-model", metavar="NAME", help=f"Ollama model when --mt-engine ollama. Default: {DEFAULT_OLLAMA_MODEL}.")
    p.add_argument("--mt-source-lang", metavar="CODES", help="Force the source language(s). Single code (ja) applies to all targets; target:source pairs (ko:ja,es:en) map per target. Default: auto-pick.")
    p.add_argument("-o", "--output", metavar="DIR", help="Output directory. Default: beside each episode's source SRT.")
    p.add_argument("--dry-run", action="store_true", help="Show the translation plan without writing files.")
    p.add_argument("--force", action="store_true", help="Overwrite existing .mt.srt outputs.")
    _apply_translate_config_defaults(p)
    return p


def translate_main(argv: list[str]) -> int:
    args = build_translate_parser().parse_args(argv)
    explicit_mt_model = args.mt_model if option_was_passed(argv, "--mt-model") else None
    if not args.mt_engine:
        raise CliError(
            "translate needs an engine. Pass --mt-engine {argos|ollama|deepl} "
            "or set [translate].engine in user_settings.toml."
        )
    langs = split_csv(args.langs, "ja")
    if not langs:
        raise CliError("No target languages specified. Use -l ja,ko or similar.")
    # [furigana].strip_before_mt: when true (default), strip inline 漢字（かんじ）
    # readings from ja source cues before MT so the translator doesn't treat
    # them as extra content. Read once here so per-cue translation stays fast.
    try:
        _cfg_furi = load_user_config().get("furigana", {})
    except CliError:
        _cfg_furi = {}
    strip_furigana_before_mt = bool(_cfg_furi.get("strip_before_mt", True))

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
    """Honour [download].strip_cc_noise / [download].single_line and
    [furigana].enabled / .mode for the modify subcommand defaults."""
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}
    overrides: dict[str, object] = {}
    dl = cfg.get("download", {})
    if dl.get("single_line"):
        overrides["single_line"] = True
    if dl.get("strip_cc_noise"):
        overrides["strip_cc_noise"] = True
    fur = cfg.get("furigana", {})
    if fur.get("enabled"):
        overrides["furigana"] = fur.get("mode", "hiragana")
    if fur.get("format"):
        overrides["furigana_format"] = fur["format"]
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
              getsubtitle modify FOLDER --furigana
              getsubtitle modify FOLDER --furigana romaji
              getsubtitle modify FOLDER --convert smi-to-srt
              getsubtitle modify FOLDER --convert smi-to-srt --force
              getsubtitle modify FOLDER --strip-cc-noise --single-line --furigana --dry-run
            """
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="One or more subtitle files or directories to scan (recursive).")
    p.add_argument("--strip-cc-noise", action="store_true", help="Remove broadcast closed-caption noise (currently: Japanese ➡ continuation arrows) in place.")
    p.add_argument("--single-line", "--single", action="store_true", help="Flatten each SRT cue to one text line in place. Useful for asbplayer.")
    p.add_argument("-f", "--furigana", "-furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help="Generate Japanese reading variants from each .ja.srt file (creates new .furigana-*.srt/.vtt/.ass files; does not modify the source).")
    p.add_argument("--format", "--furigana-format", dest="furigana_format", metavar="CODES", help="Furigana output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt. Overrides [furigana].format from user_settings.toml.")
    p.add_argument("--convert", choices=["smi-to-srt"], metavar="PAIR", help="Convert subtitle file format. Currently supports: smi-to-srt (Microsoft SAMI → one sibling .<lang>.srt per language found inside).")
    p.add_argument("--force", action="store_true", help="With --convert: overwrite existing sibling .srt files. Without --force, conversion skips targets that already exist.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing anything.")
    _apply_modify_config_defaults(p)
    return p


def modify_main(argv: list[str]) -> int:
    args = build_modify_parser().parse_args(argv)
    ops_selected = [
        bool(args.strip_cc_noise),
        bool(args.single_line),
        bool(args.furigana),
        bool(args.convert),
    ]
    if not any(ops_selected):
        raise CliError(
            "modify needs at least one operation flag: "
            "--strip-cc-noise, --single-line, --furigana [hiragana|romaji], "
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
              getsubtitle URL -s 1 -e all -l ja --furigana --single
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
    search.add_argument("-l", "--langs", "--lang", default="ja", metavar="CODES", help="Comma-separated language codes. Default: ja. Example: ja,ko,en,es")
    search.add_argument("--title", metavar="TEXT", help="Title override when URL metadata is missing or blocked.")
    search.add_argument("--anilist", type=int, metavar="ID", help="AniList ID override for anime.")
    search.add_argument("--browser", action="store_true", help="Open the URL in your browser first, useful for login/Cloudflare pages.")
    search.add_argument("--release-source", choices=["auto", "any", "netflix", "crunchyroll"], default="auto", metavar="{auto,any,netflix,crunchyroll}", help="Prefer matching release sources. Default: match the URL source when useful; use any to disable source preference.")
    search.add_argument("-release-source", dest="release_source", choices=["auto", "any", "netflix", "crunchyroll"], help=argparse.SUPPRESS)

    output = p.add_argument_group("Output")
    output.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT), metavar="DIR", help=f"Base output folder. Default: {DEFAULT_OUTPUT_TEXT}")
    output.add_argument("--layout", choices=["archive", "flat", "plex"], default="archive", help="Folder layout. Default: archive (Title/Season 01/files).")
    output.add_argument("--dry-run", action="store_true", help="Search and show availability without downloading.")
    output.add_argument("-y", "--yes", action="store_true", help="Skip bulk download confirmation.")
    output.add_argument("--open-folder", action="store_true", help="Open the output folder after saving.")
    output.add_argument("--no-open-folder-prompt", action="store_true", help="Never ask to open the output folder after saving.")

    learning = p.add_argument_group("Learning Helpers")
    learning.add_argument("-f", "--furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help="Generate extra Japanese reading files (from downloaded .ja.srt only). Optional value: hiragana or romaji. Default when used: hiragana.")
    learning.add_argument("--no-furigana", dest="furigana", action="store_const", const=None, help="Disable furigana for this run even if enabled in user_settings.toml.")
    learning.add_argument("--format", "--furigana-format", dest="furigana_format", metavar="CODES", help="Furigana output format(s) — comma list of srt, ass, vtt, or 'all'. Default: srt (asbplayer-friendly; the other variants are experimental). Use this to override [furigana].format from user_settings.toml for a single run.")
    learning.add_argument("-furigana", dest="furigana", nargs="?", const="hiragana", choices=["hiragana", "romaji"], help=argparse.SUPPRESS)
    learning.add_argument("--single-line", "--single", action="store_true", default=False, help="Flatten SRT cues to one text line for cleaner asbplayer display. On by default; this flag is kept as an explicit readability marker.")
    learning.add_argument("--no-single-line", "--preserve-lines", dest="single_line", action="store_false", help="Keep each downloaded SRT's original line breaks (disables the default single-line flattening).")
    learning.add_argument("-single-line", "-single", dest="single_line", action="store_true", help=argparse.SUPPRESS)
    learning.add_argument("--strip-cc-noise", action="store_true", default=False, help="Remove broadcast closed-caption noise from downloaded SRTs (currently: Japanese continuation arrows ➡). On by default; this flag is kept as an explicit readability marker.")
    learning.add_argument("--no-strip-cc-noise", dest="strip_cc_noise", action="store_false", help="Keep broadcast closed-caption noise in downloaded SRTs (disables the default ➡ stripping).")
    # Deprecated aliases — kept silently so existing scripts keep working.
    learning.add_argument("--strip-cc-arrows", "--strip-arrows", "-strip-cc-noise", "-strip-cc-arrows", "-strip-arrows", dest="strip_cc_noise", action="store_true", help=argparse.SUPPRESS)

    keys = p.add_argument_group("API Keys", description="Stored in macOS Keychain when available; otherwise set JIMAKU_API_KEY / WYZIE_API_KEY / DEEPL_API_KEY / TMDB_API_KEY in your shell.")
    keys.add_argument("--set-key", nargs="?", const="", metavar="PROVIDER", help="Guided API key setup: jimaku, wyzie, deepl, tmdb, or all.")
    keys.add_argument("--reset-key", nargs="?", const="", metavar="PROVIDER", help="Delete saved API key: jimaku, wyzie, deepl, tmdb, or all.")
    p.add_argument("--reset-jimaku-key", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--set-jimaku-key", action="store_true", help=argparse.SUPPRESS)

    translation = p.add_argument_group("Machine Translation", description="Runs AFTER download. Requires at least one other requested language to download successfully so MT has a source SRT to translate from. Output saved as <name>.<lang>.mt.srt.")
    translation.add_argument("--mt-engine", choices=["argos", "ollama", "deepl"], help="Translate missing requested languages from the best available SRT. Engines: argos (offline; pip install argostranslate), ollama (offline LLM; needs Ollama daemon), deepl (online; free tier, needs DEEPL_API_KEY). Default: argos (via [translate].engine).")
    translation.add_argument("--no-mt-engine", dest="mt_engine", action="store_const", const="", help="Disable machine translation for this run even when [translate].engine is set in user_settings.toml.")
    translation.add_argument("--mt-model", metavar="NAME", help=f"Ollama model for --mt-engine ollama. Default: {DEFAULT_OLLAMA_MODEL}")
    translation.add_argument("--mt-source-lang", metavar="CODES", help="Force the source language(s) for MT. Single code (ja) applies to all targets; target:source pairs (ko:ja,es:en) map per target.")

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
    "download": {
        "langs": "ja",
        "output": DEFAULT_OUTPUT_TEXT,
        "layout": "archive",
        "release_source": "auto",
        "open_folder": False,
        # On by default: getsubtitle's primary downstream is asbplayer, which
        # prefers single-line cues. Override per-run with --preserve-lines.
        "single_line": True,
        # On by default: Japanese broadcast SRTs are full of ➡ continuation
        # arrows that have no value for language learning.
        "strip_cc_noise": True,
    },
    "combine": {
        "langs": "ja,ko",
        "sync": "auto",
        "preserve_lines": False,
        "force": False,
        "priority": [],
    },
    "furigana": {
        # On by default: language-learning is getsubtitle's headline use case.
        "enabled": True,
        "combine": True,
        "mode": "hiragana",
        "format": "srt",
        "strip_before_mt": True,
    },
    "translate": {
        # Default engine: argos (offline, free, no daemon). Users without
        # argostranslate installed see a one-line setup hint, not a crash.
        "engine": "argos",
        "model": DEFAULT_OLLAMA_MODEL,
        "source_lang": "auto",
        "ollama_models": {
            # Flags live alongside pair → model mappings in this nested table.
            # auto_load: pull a missing Ollama model automatically before MT.
            # auto_unload: free the model from RAM/VRAM after the MT pass.
            "auto_load": True,
            "auto_unload": True,
        },
    },
    "experimental": {
        "debug_providers": False,
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


def _validate_section(raw: dict, name: str) -> dict:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise CliError(f"[{name}]: expected a table, got {type(section).__name__}")
    return section


def validate_user_config(raw: dict) -> dict:
    """Validate a raw TOML dict and return only the recognised, validated
    settings. Unknown keys are silently ignored so the file can evolve."""
    out: dict[str, dict] = {}

    dl = _validate_section(raw, "download")
    dl_out: dict[str, object] = {}
    if "langs" in dl:
        dl_out["langs"] = _validate_lang_list(dl["langs"], "download.langs")
    if "output" in dl:
        dl_out["output"] = _validate_str(dl["output"], "download.output")
    if "layout" in dl:
        dl_out["layout"] = _validate_enum(dl["layout"], "download.layout", {"archive", "flat", "plex"})
    if "release_source" in dl:
        dl_out["release_source"] = _validate_enum(
            dl["release_source"], "download.release_source",
            {"auto", "any", "netflix", "crunchyroll"},
        )
    for bk in ("open_folder", "single_line", "strip_cc_noise"):
        if bk in dl:
            dl_out[bk] = _validate_bool(dl[bk], f"download.{bk}")
    out["download"] = dl_out

    cb = _validate_section(raw, "combine")
    cb_out: dict[str, object] = {}
    if "langs" in cb:
        cb_out["langs"] = _validate_lang_list(cb["langs"], "combine.langs")
    if "sync" in cb:
        cb_out["sync"] = _validate_enum(cb["sync"], "combine.sync", {"auto", "strict", "loose"})
    for bk in ("preserve_lines", "force"):
        if bk in cb:
            cb_out[bk] = _validate_bool(cb[bk], f"combine.{bk}")
    if "priority" in cb:
        value = cb["priority"]
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            raise CliError("combine.priority: expected a list of language codes, e.g. ['ja', 'en']")
        cb_out["priority"] = [x.lower() for x in value]
    out["combine"] = cb_out

    fur = _validate_section(raw, "furigana")
    fur_out: dict[str, object] = {}
    if "enabled" in fur:
        fur_out["enabled"] = _validate_bool(fur["enabled"], "furigana.enabled")
    if "combine" in fur:
        fur_out["combine"] = _validate_bool(fur["combine"], "furigana.combine")
    if "mode" in fur:
        fur_out["mode"] = _validate_enum(fur["mode"], "furigana.mode", {"hiragana", "romaji"})
    if "strip_before_mt" in fur:
        fur_out["strip_before_mt"] = _validate_bool(
            fur["strip_before_mt"], "furigana.strip_before_mt"
        )
    if "format" in fur:
        if not isinstance(fur["format"], str):
            raise CliError("furigana.format: expected string (srt, ass, vtt, or comma-list, or 'all')")
        # Validate by running through the parser; raises CliError on bad values.
        parse_furigana_formats(fur["format"])
        fur_out["format"] = fur["format"]
    out["furigana"] = fur_out

    tr = _validate_section(raw, "translate")
    tr_out: dict[str, object] = {}
    if "engine" in tr:
        if not isinstance(tr["engine"], str):
            raise CliError("translate.engine: expected string ('', 'argos', 'ollama', or 'deepl')")
        if tr["engine"] and tr["engine"] not in {"argos", "ollama", "deepl"}:
            raise CliError(
                f"translate.engine: expected one of ['argos', 'ollama', 'deepl'] or empty, got {tr['engine']!r}"
            )
        tr_out["engine"] = tr["engine"]
    if "model" in tr:
        tr_out["model"] = _validate_str(tr["model"], "translate.model")
    if "source_lang" in tr:
        tr_out["source_lang"] = _validate_str(tr["source_lang"], "translate.source_lang")
    if "ollama_models" in tr:
        tr_out["ollama_models"] = _validate_ollama_model_map(tr["ollama_models"])
    out["translate"] = tr_out

    exp = _validate_section(raw, "experimental")
    exp_out: dict[str, object] = {}
    for bk in ("debug_providers", "subdivx", "addic7ed"):
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
# Every value below is set to the current built-in default; edit to change.
# Command-line flags always win. DO NOT put API keys here.

[download]
langs = "ja"
output = "~/Movies/Subtitles"
layout = "archive"                # archive | flat | plex
release_source = "auto"           # auto | any | netflix | crunchyroll
open_folder = false
single_line = true                # asbplayer-friendly one-line cues
strip_cc_noise = true             # remove broadcast ➡ continuation arrows

[combine]
langs = "ja,ko"
sync = "auto"                     # auto | strict | loose
preserve_lines = false
force = false
priority = []                     # e.g. ["ja", "en", "ko", "es"]

[furigana]
enabled = true                    # auto-generate furigana side files on download
combine = true                    # inline furigana into combine outputs
mode = "hiragana"                 # hiragana | romaji
strip_before_mt = true            # strip 漢字（かんじ） readings before MT
format = "srt"                    # srt | ass | vtt | all (or comma list)

[translate]
engine = "argos"                  # "" | argos | ollama | deepl
model = "qwen3:4b"                # default Ollama model
source_lang = "auto"

[translate.ollama_models]
auto_load = true                  # pull missing models on demand
auto_unload = true                # free model from RAM/VRAM after MT
# "ja:ko" = "qwen3:4b"
# "ko:ja" = "qwen3:4b"
# "en:es" = "llama3.2:3b"
# "es:en" = "llama3.2:3b"

[experimental]
debug_providers = false
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
    """Push user_settings.toml [download] / [furigana] / [translate] /
    [experimental] values into the download parser as argparse defaults.

    Merges BUILTIN_CONFIG_DEFAULTS under any user_settings.toml overrides,
    so flips like single_line=true take effect even without a user TOML."""
    try:
        cfg = load_user_config()
    except CliError:
        # Don't let a bad config file break --help. Defer surfacing the
        # error until the user actually tries to run a command — for that
        # path the error will fire again at parse time below.
        cfg = {}

    dl = {**BUILTIN_CONFIG_DEFAULTS["download"], **cfg.get("download", {})}
    fur = {**BUILTIN_CONFIG_DEFAULTS["furigana"], **cfg.get("furigana", {})}
    tr = {**BUILTIN_CONFIG_DEFAULTS["translate"], **cfg.get("translate", {})}
    exp = {**BUILTIN_CONFIG_DEFAULTS["experimental"], **cfg.get("experimental", {})}

    overrides: dict[str, object] = {}
    if dl.get("langs"):
        overrides["langs"] = dl["langs"]
    if dl.get("output"):
        overrides["output"] = str(Path(str(dl["output"])).expanduser())
    if dl.get("layout"):
        overrides["layout"] = dl["layout"]
    if dl.get("release_source"):
        overrides["release_source"] = dl["release_source"]
    if dl.get("open_folder"):
        overrides["open_folder"] = True
    # Booleans below: explicit set in either direction so the BUILTIN flip
    # actually reaches argparse (store_true defaults to False otherwise).
    overrides["single_line"] = bool(dl.get("single_line", False))
    overrides["strip_cc_noise"] = bool(dl.get("strip_cc_noise", False))

    if fur.get("enabled"):
        overrides["furigana"] = fur.get("mode", "hiragana")
    if fur.get("format"):
        overrides["furigana_format"] = fur["format"]

    if tr.get("engine"):
        overrides["mt_engine"] = tr["engine"]
    if tr.get("model"):
        overrides["mt_model"] = tr["model"]
    src = tr.get("source_lang", "")
    if src and src != "auto":
        overrides["mt_source_lang"] = src

    if exp.get("debug_providers"):
        overrides["debug_providers"] = True
    if exp.get("subdivx"):
        overrides["experimental_subdivx"] = True
    if exp.get("addic7ed"):
        overrides["experimental_addic7ed"] = True

    if overrides:
        parser.set_defaults(**overrides)


def _apply_combine_config_defaults(parser: argparse.ArgumentParser) -> None:
    try:
        cfg = load_user_config()
    except CliError:
        cfg = {}

    overrides: dict[str, object] = {}
    cb = cfg.get("combine", {})
    if "langs" in cb:
        overrides["langs"] = cb["langs"]
    if "sync" in cb:
        overrides["sync"] = cb["sync"]
    if cb.get("preserve_lines"):
        overrides["preserve_lines"] = True
    if cb.get("force"):
        overrides["force"] = True

    fur = cfg.get("furigana", {})
    if fur.get("enabled") or fur.get("combine"):
        overrides["furigana"] = fur.get("mode", "hiragana")
    if fur.get("format"):
        overrides["furigana_format"] = fur["format"]

    if overrides:
        parser.set_defaults(**overrides)


def _combine_master_from_config(langs: list[str]) -> str | None:
    """Apply [combine].priority: return the first priority lang that's also
    in `langs`, or None if no priority is set or no overlap."""
    try:
        cfg = load_user_config()
    except CliError:
        return None
    priority = cfg.get("combine", {}).get("priority", []) or []
    for p in priority:
        if p in langs:
            return p
    return None


HELP_MAIN = """\
getsubtitle — Find and prepare subtitles for language learning.

Usage:
  getsubtitle URL [options]
  getsubtitle combine PATH -l LANGS [options]
  getsubtitle translate PATH -l LANGS --mt-engine ENGINE [options]
  getsubtitle modify PATH [--strip-cc-noise] [--single-line] [--furigana [MODE]]

Common examples:
  getsubtitle URL -l ja
  getsubtitle URL -s 1 -e all -l ja,ko,en
  getsubtitle URL -l ja -furigana
  getsubtitle combine ~/Movies/Subtitles/MF\\ Ghost -l ja,ko
  getsubtitle translate ~/Movies/Subtitles/MF\\ Ghost -l ja,ko --mt-engine argos
  getsubtitle modify ~/Movies/Subtitles/MF\\ Ghost --strip-cc-noise --single-line

Core options:
  -l, --langs CODES        Languages, e.g. ja,ko,en,es. Default: ja
  -s, --season N|all       Season to search
  -e, --episode N|N-M|all  Episode, range, list, or all
  -o, --output DIR         Output folder
  --dry-run                Show what would happen without writing files
  -y, --yes                Skip confirmation

Preferences:
  getsubtitle config --path     Show where user_settings.toml lives
  getsubtitle config --init     Create user_settings.toml from the template
  edit user_settings.toml       Set your defaults; CLI flags still win

More help:
  getsubtitle --help download
  getsubtitle --help combine
  getsubtitle --help translate
  getsubtitle --help modify
  getsubtitle --help config
  getsubtitle --help keys
  getsubtitle --help furigana
  getsubtitle --help batch
  getsubtitle --help advanced
"""


HELP_TOPICS: dict[str, str] = {
    "download": """\
Download subtitles from a streaming or metadata URL.

Usage:
  getsubtitle URL [download options]

Supported URL types:
  Crunchyroll, Netflix, IMDb, TMDB, Letterboxd, Rotten Tomatoes,
  MyAnimeList, AniList, TheTVDB, Trakt

Examples:
  getsubtitle "https://www.crunchyroll.com/watch/..." -l ja
  getsubtitle "https://www.imdb.com/title/tt28299608/" -s 1 -e all -l ko,en,es
  getsubtitle URL -s 1 -e 7 -l ja,ko --dry-run
  getsubtitle URL --title "MF Ghost" --anilist 143327 -l ja

Download options:
  -l, --langs CODES        Languages to download. Default: ja
  -s, --season N|all       Season number. If omitted, infer when possible
  -e, --episode N|N-M|all  Episode, range, list, or all. If omitted, infer when possible
  -o, --output DIR         Output folder. Default: ~/Movies/Subtitles
  --layout MODE            archive, flat, or plex. Default: archive
  --title TEXT             Title override when URL metadata is missing
  --anilist ID             AniList ID override for anime
  --browser                Open URL first for login/Cloudflare pages
  --release-source MODE    auto, any, netflix, crunchyroll. Default: auto
  --dry-run                Search and show availability without downloading
  -y, --yes                Skip bulk confirmation
  --open-folder            Open output folder after saving
""",
    "combine": """\
Combine multiple subtitle languages into one study-friendly subtitle file.

Usage:
  getsubtitle combine PATH -l LANGS [combine options]

Examples:
  getsubtitle combine ~/Movies/Subtitles/MF\\ Ghost -l ja,ko
  getsubtitle combine ~/Movies/Subtitles/MF\\ Ghost -l en,es,ko
  getsubtitle combine PATH -l ja,ko -furigana
  getsubtitle combine PATH -l ja,ko --sync strict --dry-run

Behavior:
  The language order in -l controls display order.
  Example: -l ja,ko puts Japanese above Korean.
  Each language is flattened to one line by default:
    Japanese line 1 Japanese line 2
    Korean line 1 Korean line 2

Combine options:
  -l, --langs CODES        Required. Language order for output
  -o, --output DIR         Output folder. Default: beside master subtitle
  --dry-run                Show combine plan without writing files
  --force                  Overwrite existing outputs and allow low-confidence matches
  --open-folder            Open output folder after writing
  --no-open-folder-prompt  Do not ask whether to open output folder
  --format FORMAT          srt or vtt. vtt can render ruby furigana in asbplayer
  --sync MODE              auto, strict, or loose. Default: auto
  --master LANG            Timing master. Default: first language in -l
  --single-line, --single  Flatten each language to one line. Default behavior
  --preserve-lines         Keep original line breaks within each language
  -f, --furigana [MODE]    Add Japanese readings. MODE: hiragana or romaji
""",
    "keys": """\
Manage API keys.

Usage:
  getsubtitle --set-key [PROVIDER]
  getsubtitle --reset-key [PROVIDER]

Providers:
  jimaku                   Japanese anime subtitles
  wyzie                    Movie and TV subtitles by IMDb/TMDB ID
  deepl                    Machine translation with DeepL
  tmdb                     Movie/TV title → ID resolution (improves Wyzie
                           match rate when only a title is known)
  all                      Set or reset all supported providers

Examples:
  getsubtitle --set-key
  getsubtitle --set-key jimaku
  getsubtitle --set-key wyzie
  getsubtitle --set-key tmdb
  getsubtitle --reset-key wyzie

Environment variables:
  JIMAKU_API_KEY
  WYZIE_API_KEY
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

Usage:
  getsubtitle URL -l ja -furigana [hiragana|romaji]
  getsubtitle combine PATH -l ja,ko -furigana [hiragana|romaji]

Examples:
  getsubtitle URL -l ja -furigana
  getsubtitle URL -l ja -furigana romaji
  getsubtitle URL -l ja -furigana --single
  getsubtitle combine PATH -l ja,ko -furigana

Modes:
  hiragana                 Default. 漢字（かんじ）
  romaji                   漢字（kanji）

Output formats (--format):
  srt                      Default. Broadly compatible, with parenthetical readings.
                           One file per episode. Safest fallback.
  ass                      Stacked-line ASS. Experimental; player support varies.
  vtt                      Ruby VTT (<ruby><rt>). Works in asbplayer when
                           Settings > Misc > Subtitles > Subtitle HTML is Render.
                           Detect and Display Ruby is optional for mouseover/
                           auto-pause behavior.
  all                      Generate all three. Same as srt,ass,vtt.

Examples:
  getsubtitle URL -l ja -furigana                       # just srt
  getsubtitle URL -l ja -furigana --format srt,ass      # srt + ass for this run
  getsubtitle URL -l ja -furigana --format all          # all three
  getsubtitle modify FOLDER --furigana --format srt     # post-process existing files

(--furigana-format still works as an alias for --format.)

Set defaults in user_settings.toml:
  [furigana]
  combine = true         # inline readings into getsubtitle combine outputs
  mode = "hiragana"      # or "romaji"
  format = "srt"          # or "srt,ass" / "all"
  strip_before_mt = true # strip 漢字（かんじ） readings from ja before MT
                          # (on by default; turn off only if you want the
                          # translator to see the parentheticals)

Use --no-furigana to disable a configured default for one command.
Use --format to override side-file formats for download/modify runs.

MT-source notes:
  When a .ja.srt has inline 漢字（かんじ） readings and is used as an MT
  source (translate or download --mt-engine), strip_before_mt=true (the
  default) removes the parentheticals before sending to the engine. This
  prevents output like "Specifically (especially) the legs (legs) ..."
  caused by the engine translating the readings as extra content. The
  normal pipeline keeps furigana in side files only, so this is a defence
  for third-party or hand-edited Japanese sources.

Output notes:
  SRT is the safest fallback across players.
  VTT gives true furigana in asbplayer with Subtitle HTML set to Render.
  ASS support depends on the player.
  Furigana is added only for Japanese text.
""",
    "translate": """\
Machine-translate missing subtitles.

Two ways to use it:
  1. Inside a download, as a fallback:
       getsubtitle URL -l LANGS --mt-engine ENGINE
     MTs any requested language that the download couldn't find, sourcing
     from the just-downloaded files.

  2. Standalone on an existing folder (no URL, no re-download):
       getsubtitle translate PATH -l LANGS --mt-engine ENGINE
     Scans PATH for *.srt files and MTs any requested language that's
     missing from each episode's set, sourcing from the best available
     local SRT.

Examples (inline with download):
  getsubtitle URL -l ja,ko,en --mt-engine ollama
  getsubtitle URL -l en,es --mt-engine deepl
  getsubtitle URL -l ko --mt-engine ollama --mt-source-lang ja

Examples (standalone translate subcommand):
  getsubtitle translate ~/Movies/Subtitles/MF\\ Ghost -l ja,ko --mt-engine argos
  getsubtitle translate FOLDER -s 1 -e 11 -l ko --mt-engine deepl
  getsubtitle translate FOLDER -l ja,ko,en,es --mt-engine deepl --dry-run
  getsubtitle translate FOLDER -s 1 -e 1-3 -l ko --mt-source-lang ja --mt-engine ollama --force

Explicit source mapping (per-target):
  # Force ko<-ja and es<-en regardless of what auto-pick would do.
  getsubtitle translate FOLDER -l ja,ko,en,es --mt-engine argos --mt-source-lang ko:ja,es:en
  # Inside a download, same syntax:
  getsubtitle URL -l ja,ko,en,es --mt-engine deepl --mt-source-lang ko:ja,es:en

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
  --mt-engine ENGINE       argos, ollama, or deepl. Default: argos
                           (via [translate].engine in user_settings.toml).
  --no-mt-engine           Disable MT for this run even when the config
                           has an engine set. Equivalent to engine = "".
  --mt-model NAME          Ollama model. Default: qwen3:4b
  --mt-source-lang CODE    Force translation source language (default: auto)
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
  --mt-model NAME overrides pair-specific config for one command.
""",
    "modify": """\
Post-process existing subtitle files on disk.

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
  getsubtitle modify FOLDER --furigana
  getsubtitle modify FOLDER --furigana romaji
  getsubtitle modify FOLDER --convert smi-to-srt
  getsubtitle modify FOLDER --convert smi-to-srt --force
  getsubtitle modify FOLDER --strip-cc-noise --single-line --furigana --dry-run

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
  -f, --furigana [MODE]    Generate Japanese reading variants from each .ja.srt.
                           MODE = hiragana (default) or romaji.
                           Creates new side files; does not modify source.
  --format CODES           Which furigana files to generate. Comma list of
                           srt, ass, vtt, or 'all'. Default: srt only
                           (one file per episode instead of three).
                           (Also accepts --furigana-format.)

Other:
  --force                  With --convert: overwrite existing sibling .srt files.
                           Without --force, conversion skips targets that
                           already exist (protects human-quality .ko.srt etc.).
  --dry-run                Show what would change; write nothing.

Composes with the other subcommands:
  getsubtitle modify    FOLDER --convert smi-to-srt
  getsubtitle translate FOLDER -l ja,ko --mt-engine argos
  getsubtitle modify    FOLDER --strip-cc-noise --single-line --furigana
  getsubtitle combine   FOLDER -l ja,ko
""",
    "config": """\
User settings (non-secret defaults).

Usage:
  getsubtitle config --path        Print the config file path
  getsubtitle config --init        Create the file from the example template
  getsubtitle config --init --force   ...overwrite if it already exists
  getsubtitle config --open        Open the file in your default editor
  getsubtitle config --show        Print the effective non-secret config

File location:
  macOS/Linux: ~/.config/getsubtitle/user_settings.toml
  Windows:     %APPDATA%\\getsubtitle\\user_settings.toml

Precedence:
  command-line flags > environment variables > user_settings.toml > built-in defaults

Sections (see the example template):
  [download]      langs, output, layout, release_source, open_folder,
                  single_line, strip_cc_noise
  [combine]       langs, sync, preserve_lines, force, priority
  [furigana]      enabled, combine, mode, format, strip_before_mt
  [translate]     engine, model, source_lang
  [experimental]  debug_providers, subdivx, addic7ed

Notes:
  API keys are NEVER read from this file — keep them in macOS Keychain or
  environment variables (JIMAKU_API_KEY, WYZIE_API_KEY, DEEPL_API_KEY,
  TMDB_API_KEY).
  Run `getsubtitle config --show` to see what's currently active.
""",
    "batch": """\
Bulk subtitle workflows over a whole library (batch/ scripts).

The batch/ directory ships three companion Python scripts that walk a
Plex-style library, match each show/movie folder against a reference
map, and shell out to the regular `getsubtitle` CLI in bulk. They're
not subcommands of `getsubtitle` itself — run them with Python
directly. All of getsubtitle's own defaults (engine, model, auto-load,
furigana, etc.) apply to the shelled-out calls.

Files:
  batch/reference.json    Folder name -> {title, profile, IDs, season,
                          notes}. The single source of truth that drives
                          all three scripts. Edit by hand or have
                          lookup.py fill in IDs.
  batch/fetch.py          Walk CWD, fetch missing subtitles per the
                          entry's profile.
  batch/merge.py          Walk CWD, convert any .smi to .ko.srt, then
                          combine language stacks per the profile.
  batch/lookup.py         Backfill empty anilist_id / imdb_id / tmdb_id
                          in reference.json from AniList + TMDB.
  batch/README.md         User-facing docs (longer than this topic).

Profiles (set per entry in reference.json):
  ja                       Japanese-origin. fetch.py grabs ko first; if
                           missing, MTs ja->ko via Ollama. merge.py
                           combines ja+ko with --master ja --furigana.
  ko                       Korean-origin. fetch.py grabs ja first; if
                           missing, MTs ko->ja. merge.py combines
                           ko+ja (and a ko+ja+en+es quad if those
                           sidefiles exist), --master ko --furigana.
  en                       English / Western / other. fetch.py grabs
                           es and ko; MTs from en when missing.
                           merge.py produces both en+es dual and
                           ja+ko+en+es quad, --master en.

Quickstart:
  # 1. Backfill missing IDs in reference.json (free TMDB key needed for
  #    live-action). getsubtitle --set-key tmdb works too.
  python3 /path/to/getsubtitle/batch/lookup.py

  # 2. Walk your library, see what would be fetched (default: dry-run).
  cd /path/to/your/plex/library
  python3 /path/to/getsubtitle/batch/fetch.py

  # 3. If the plan looks right, run for real.
  python3 /path/to/getsubtitle/batch/fetch.py --run

  # 4. Build combined study files.
  python3 /path/to/getsubtitle/batch/merge.py --run --format vtt

Each script accepts --help for its own flags:
  python3 batch/fetch.py --help
  python3 batch/merge.py --help
  python3 batch/lookup.py --help

Matching rules (how a folder on disk lines up with a reference entry):
  1. Exact path relative to CWD              (e.g. "유포니움/1기")
  2. Walk up parents until one matches       (Plex Season XX -> Show key)
  3. Bare filename for loose top-level files (e.g. "Kill Boksoon ...mkv")

Unmatched targets are listed at the end of each run with a hint to add
them to reference.json.

Adding a new entry to reference.json:

  "New Show (2026)": {
    "title": "New Show",
    "year": 2026,
    "type": "show",          // or "movie"
    "profile": "en",          // ja | ko | en
    "needs_lookup": true      // lookup.py will fill IDs on next run
  }

Notes:
  - Both fetch.py and merge.py are dry-run by default. Add --run.
  - merge.py runs `getsubtitle modify --convert smi-to-srt --force` on
    each folder first, so legacy Korean .smi files become .ko.srt
    automatically before combine.
  - lookup.py is idempotent and never overwrites a manually-set ID.
""",
    "advanced": """\
Advanced and experimental options.

Troubleshooting:
  --debug-providers        Show raw provider counts and language tags
  --browser                Open URL first for login/Cloudflare pages

Provider selection:
  --release-source MODE    auto, any, netflix, crunchyroll
                            auto prefers the URL source when useful
                            any disables source preference

Experimental providers:
  --experimental-subdivx   Enable Spanish Subdivx fallback
  --experimental-addic7ed  Enable Korean Addic7ed fallback; may rate-limit

Output / cleanup:
  --layout MODE            archive, flat, plex
  --strip-cc-noise         Remove broadcast closed-caption noise (currently: ➡)
  --single-line            Flatten SRT cues to one line

Compatibility aliases (still accepted):
  -furigana                Same as --furigana
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
    if argv[0] == "combine":
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
        if len(argv) == 1:
            # `getsubtitle combine` with no args -> show combine help instead
            # of failing in argparse on missing PATH.
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
    if argv[0] == "config":
        # `getsubtitle config --help` / `-h` routes to the config topic page.
        # `getsubtitle config` alone is handled by config_main (prints
        # config-parser help) so it doesn't fire here.
        if any(a in ("-h", "--help") for a in argv[1:]):
            return True
    return False


def _show_topic_help(argv: list[str]) -> int:
    if argv and argv[0] == "combine":
        sys.stdout.write(HELP_TOPICS["combine"])
        return 0
    if argv and argv[0] == "translate":
        sys.stdout.write(HELP_TOPICS["translate"])
        return 0
    if argv and argv[0] == "modify":
        sys.stdout.write(HELP_TOPICS["modify"])
        return 0
    if argv and argv[0] == "config":
        sys.stdout.write(HELP_TOPICS["config"])
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


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    # No args -> short main help. Friendlier than the old "Missing URL" error.
    if not raw_argv:
        sys.stdout.write(HELP_MAIN)
        return 0
    # Topic-help dispatch — handled before argparse so we own the help UX.
    if _is_topic_help_request(raw_argv):
        return _show_topic_help(raw_argv)
    # Subcommand dispatch — preserve the existing 'getsubtitle URL ...' shape
    # by sniffing the first positional. Add more subcommands here as needed.
    if raw_argv[0] == "combine":
        return combine_main(raw_argv[1:])
    if raw_argv[0] == "translate":
        return translate_main(raw_argv[1:])
    if raw_argv[0] == "modify":
        return modify_main(raw_argv[1:])
    if raw_argv[0] == "config":
        return config_main(raw_argv[1:])
    args = build_parser().parse_args(raw_argv)
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
    media.season = str(args.season).lower()
    media.episode = str(args.episode).lower()
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
    if episodes == ["all"]:
        raise CliError("Episode count is unknown. Use -e 1-12, -e 1,2,3, or pass --anilist for automatic expansion.")
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
    wyzie_provider = WyzieProvider(get_wyzie_api_key()) if (media.imdb_id or media.tmdb_id or broad_provider_requested) else None
    preferred_release_source = None
    if args.release_source == "any":
        preferred_release_source = None
    elif args.release_source == "auto":
        preferred_release_source = media.provider if media.provider in {"netflix", "crunchyroll"} else None
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
            if lang == "ja":
                warnings.append(f"{lang}: no provider available for this URL. Use AniList/Jimaku for Japanese anime, or an IMDb/TMDB URL with WYZIE_API_KEY for broad lookup.")
            else:
                warnings.append(f"{lang}: broad provider lookup needs an IMDb/TMDB URL plus WYZIE_API_KEY. Crunchyroll URLs currently only resolve Japanese anime subtitles through Jimaku.")
            continue
        if not provider.configured():
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
    debug_lines: list[str] = []
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
                debug_lines.append(f"  {provider.name} ep{ep} {lang}: ERROR {e}")
            continue
        if args.debug_providers:
            tag_counts: dict[str, int] = {}
            for f in files:
                tag = f.provider_language or "(no tag)"
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            tags = ", ".join(f"{tag}={count}" for tag, count in sorted(tag_counts.items())) or "(empty)"
            debug_lines.append(f"  {provider.name} ep{ep} {lang}: {len(files)} items [{tags}]")
        best = choose_best(files, preferred_release_source)
        if best:
            if not media.title and best.media_title:
                media.title = best.media_title
            planned.append((lang, ep, best))
            search_results.append(SearchResult(lang, ep, provider.name, "found", file=best))
        else:
            search_results.append(SearchResult(lang, ep, provider.name, "missing"))

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
                        debug_lines.append(f"  subdivx ep{ep} es: ERROR {e}")
                    continue
                if args.debug_providers:
                    debug_lines.append(f"  subdivx ep{ep} es: {len(sd_files)} items")
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
                        debug_lines.append(f"  addic7ed ep{ep} ko: ERROR {e}")
                    continue
                if args.debug_providers:
                    suffix = f" ({a7_diag})" if a7_diag and not a7_files else ""
                    debug_lines.append(f"  addic7ed ep{ep} ko: {len(a7_files)} items{suffix}")
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

    if args.debug_providers and debug_lines:
        print("\nProvider debug:")
        for line in debug_lines:
            print(line)

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
        explicit_mt_model = args.mt_model if option_was_passed(raw_argv, "--mt-model") else None
        translator_cache: dict[tuple[str, str | None], _BaseTranslator] = {}
        # [furigana].strip_before_mt: same defense as translate_main. Default
        # true; only meaningful when an MT source is ja.
        try:
            _cfg_furi = load_user_config().get("furigana", {})
        except CliError:
            _cfg_furi = {}
        strip_furigana_before_mt = bool(_cfg_furi.get("strip_before_mt", True))

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
