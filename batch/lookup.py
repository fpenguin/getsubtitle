#!/usr/bin/env python3
"""getsubtitle batch — lookup.

Backfill missing anilist_id / imdb_id / tmdb_id values in reference.json
by querying AniList (for anime) and TMDB (for live-action), updating
entries flagged with "needs_lookup": true.

The script is conservative: it only fills empty fields and only updates
entries whose current lookup confidence is explicitly flagged. It will
NOT overwrite IDs you've manually verified.

Requirements:
  - Internet access (anonymous AniList GraphQL + TMDB API).
  - Optional: TMDB_API_KEY in the environment for higher rate limit
    and live-action lookups. Without it, AniList lookups still work
    (anime-only mode).

Usage:
  python3 /path/to/getsubtitle/batch/lookup.py [--limit N] [--dry-run]
  python3 /path/to/getsubtitle/batch/lookup.py --only "Show Name"

Default behavior: process every entry with needs_lookup=true, persist
back to reference.json after each successful fill.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REFERENCE, entries_from, load_reference

# Prefer the main getsubtitle module's TMDB helpers when available — they
# handle keychain lookup, caching, and error swallowing consistently with
# the rest of the CLI. Falls back to a local urllib path if the package
# isn't importable (e.g. running this script from outside an install).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import getsubtitle_core as _gs  # type: ignore
    _MAIN_TMDB = True
except Exception:
    _gs = None  # type: ignore[assignment]
    _MAIN_TMDB = False


ANILIST_GRAPHQL = "https://graphql.anilist.co"
TMDB_BASE = "https://api.themoviedb.org/3"

USER_AGENT = "getsubtitle-batch-lookup/1.0 (+https://github.com/fpenguin/getsubtitle)"


def _post_json(url: str, body: dict, timeout: int = 15) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def query_anilist(title: str) -> int | None:
    """Return the AniList ID for the best title match, or None."""
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) { id title { romaji english native } }
    }
    """
    try:
        out = _post_json(ANILIST_GRAPHQL, {"query": query, "variables": {"search": title}})
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"    anilist error: {e}")
        return None
    except Exception as e:
        print(f"    anilist unexpected error: {e}")
        return None
    media = (out.get("data") or {}).get("Media")
    if not media:
        return None
    return media.get("id")


def query_tmdb_movie(title: str, year: int | None, api_key: str) -> tuple[int | None, str | None]:
    """Return (tmdb_id, imdb_id) for a movie title. Either may be None.
    Uses getsubtitle_core.tmdb_search_movie when importable so the shared
    cache + key-handling logic lives in one place."""
    if _MAIN_TMDB:
        hit = _gs.tmdb_search_movie(title, year=year, api_key=api_key)
        if not hit:
            return None, None
        tid = hit.get("tmdb_id")
        return (int(tid) if tid else None), hit.get("imdb_id")
    # Fallback path: direct urllib calls (when running outside an install).
    params = {"api_key": api_key, "query": title}
    if year:
        params["year"] = str(year)
    url = f"{TMDB_BASE}/search/movie?" + urllib.parse.urlencode(params)
    try:
        out = _get_json(url)
    except Exception as e:
        print(f"    tmdb search error: {e}")
        return None, None
    results = out.get("results") or []
    if not results:
        return None, None
    tmdb_id = results[0].get("id")
    if not tmdb_id:
        return None, None
    try:
        detail = _get_json(f"{TMDB_BASE}/movie/{tmdb_id}?api_key={api_key}")
    except Exception:
        return tmdb_id, None
    return tmdb_id, detail.get("imdb_id")


def query_tmdb_tv(title: str, api_key: str) -> tuple[int | None, str | None]:
    """Return (tmdb_id, imdb_id) for a TV show title.
    Uses getsubtitle_core.tmdb_search_tv when importable."""
    if _MAIN_TMDB:
        hit = _gs.tmdb_search_tv(title, api_key=api_key)
        if not hit:
            return None, None
        tid = hit.get("tmdb_id")
        return (int(tid) if tid else None), hit.get("imdb_id")
    params = {"api_key": api_key, "query": title}
    url = f"{TMDB_BASE}/search/tv?" + urllib.parse.urlencode(params)
    try:
        out = _get_json(url)
    except Exception as e:
        print(f"    tmdb tv search error: {e}")
        return None, None
    results = out.get("results") or []
    if not results:
        return None, None
    tmdb_id = results[0].get("id")
    if not tmdb_id:
        return None, None
    try:
        detail = _get_json(f"{TMDB_BASE}/tv/{tmdb_id}/external_ids?api_key={api_key}")
    except Exception:
        return tmdb_id, None
    return tmdb_id, detail.get("imdb_id")


def needs_anime_lookup(entry: dict) -> bool:
    return (
        entry.get("profile") == "ja"
        and not entry.get("anilist_id")
    )


def needs_imdb_lookup(entry: dict) -> bool:
    return not entry.get("imdb_id") and not entry.get("tmdb_id")


def fill_entry(key: str, entry: dict, tmdb_key: str | None) -> bool:
    """Try to fill the entry. Returns True if anything was added."""
    title = entry.get("title") or key
    changed = False

    if needs_anime_lookup(entry):
        print(f"  AniList: searching {title!r}")
        anilist_id = query_anilist(title)
        if anilist_id:
            entry["anilist_id"] = anilist_id
            print(f"    found anilist_id={anilist_id}")
            changed = True
            time.sleep(0.5)  # polite to AniList free API
        else:
            print(f"    no AniList match")

    if needs_imdb_lookup(entry) and tmdb_key:
        kind = entry.get("type", "movie")
        year = entry.get("year")
        print(f"  TMDB {kind}: searching {title!r}{f' year={year}' if year else ''}")
        if kind == "show":
            tmdb_id, imdb_id = query_tmdb_tv(title, tmdb_key)
        else:
            tmdb_id, imdb_id = query_tmdb_movie(title, year, tmdb_key)
        if tmdb_id:
            entry["tmdb_id"] = tmdb_id
            print(f"    found tmdb_id={tmdb_id}")
            changed = True
        if imdb_id:
            entry["imdb_id"] = imdb_id
            print(f"    found imdb_id={imdb_id}")
            changed = True
        if tmdb_id or imdb_id:
            time.sleep(0.25)  # polite to TMDB

    if changed:
        entry["needs_lookup"] = False
    return changed


def main() -> int:
    p = argparse.ArgumentParser(
        prog="batch/lookup.py",
        description="Backfill anilist_id / imdb_id / tmdb_id in reference.json.",
    )
    p.add_argument("--limit", type=int, default=None, help="Process at most N entries.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be looked up; do not write back to reference.json.")
    p.add_argument("--only", default=None,
                   help="Process only the entry whose key matches this string exactly.")
    p.add_argument("--all", action="store_true",
                   help="Process entries even if needs_lookup is false (re-check).")
    args = p.parse_args()

    # Prefer the shared key-resolution path so users who ran
    # `getsubtitle --set-key tmdb` don't need to also export the env var.
    tmdb_key = None
    if _MAIN_TMDB:
        try:
            tmdb_key = _gs.get_provider_api_key("tmdb")
        except Exception:
            tmdb_key = None
    if not tmdb_key:
        tmdb_key = os.environ.get("TMDB_API_KEY")
    if not tmdb_key:
        print("Note: no TMDB key found — only AniList anime lookups will run.")
        print("Set one with:  getsubtitle --set-key tmdb")
        print("Or:            export TMDB_API_KEY=...")
        print("Get a free key at https://www.themoviedb.org/settings/api")
        print()

    ref = load_reference()
    entries = entries_from(ref)

    if args.only:
        if args.only not in entries:
            sys.exit(f"--only key not found: {args.only}")
        targets = [(args.only, entries[args.only])]
    else:
        targets = [
            (k, e) for k, e in entries.items()
            if args.all or e.get("needs_lookup")
        ]

    if args.limit:
        targets = targets[: args.limit]

    if not targets:
        print("Nothing to do — no entries marked needs_lookup (or all already filled).")
        return 0

    print(f"Looking up {len(targets)} entry(ies)...")
    any_changed = False
    for key, entry in targets:
        print(f"\n[{entry.get('profile', '?')}] {key}")
        if fill_entry(key, entry, tmdb_key):
            any_changed = True

    if args.dry_run:
        print("\n(--dry-run) reference.json was NOT written.")
        return 0

    if any_changed:
        REFERENCE.write_text(
            json.dumps(ref, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {REFERENCE}")
    else:
        print("\nNo changes to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
