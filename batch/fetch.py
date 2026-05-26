#!/usr/bin/env python3
"""getsubtitle batch — fetch.

Walk the current directory, match each show/movie folder against
reference.json, and shell out to `getsubtitle` to fetch missing
subtitles according to the entry's profile.

Profiles:
  ja  Japanese-origin. Master=ja. Fetch ko first (Wyzie/Addic7ed);
      if Korean is unavailable, MT ja→ko via Ollama.
  ko  Korean-origin. Master=ko. Fetch ja first (Wyzie);
      if Japanese is unavailable, MT ko→ja via Ollama.
  en  English / Western / other-origin. Master=en. Fetch es + ko;
      MT from en (or whatever source exists) for whichever
      target is missing.

Usage:
  cd /path/to/your/plex/library
  python3 /path/to/getsubtitle/batch/fetch.py [--run] [--mt-engine ollama]

Default is dry-run. Add --run to actually fetch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this file directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    entries_from,
    find_bare_video_files,
    find_video_folders,
    heading,
    load_reference,
    match_entry,
    run_getsubtitle,
)


# Per-profile fetch order. The translate fallback only triggers if
# Wyzie/Addic7ed couldn't return the language.
PROFILE_FETCH_LANGS = {
    "ja": ["ko"],          # JP master → fetch Korean first
    "ko": ["ja"],          # KR master → fetch Japanese first
    "en": ["es", "ko"],    # EN master → fetch Spanish + Korean
}

PROFILE_MT_SOURCE = {
    "ja": "ja",            # MT from ja when ko fetch failed
    "ko": "ko",            # MT from ko when ja fetch failed
    "en": "en",            # MT from en when es/ko fetch failed
}


def build_base_args(entry: dict) -> tuple[list[str], str | None]:
    """Return (positional-or-flags-for-search, label) used by every
    getsubtitle call for this entry.

    Order of preference for identifying the show:
      1. URL synthesized from imdb_id (most reliable for live-action)
      2. AniList ID via --anilist (most reliable for anime)
      3. --title fallback
    """
    title = entry.get("title")
    anilist = entry.get("anilist_id")
    imdb = entry.get("imdb_id")

    args: list[str] = []
    label_bits: list[str] = []

    if imdb:
        # IMDb URL is the most stable identifier for live-action.
        args.append(f"https://www.imdb.com/title/{imdb}/")
        label_bits.append(f"imdb={imdb}")
    elif anilist:
        # No URL — title + anilist flag.
        if title:
            args += ["--title", title]
        args += ["--anilist", str(anilist)]
        label_bits.append(f"anilist={anilist}")
    elif title:
        args += ["--title", title]
        label_bits.append(f'title="{title}"')
    else:
        return [], None

    return args, ", ".join(label_bits)


def episode_args(entry: dict) -> list[str]:
    """Return -s / -e flags appropriate for the entry. Movies get nothing;
    shows get a season filter and an episode range if known."""
    if entry.get("type") != "show":
        return []
    args: list[str] = []
    season = entry.get("season")
    if season is not None:
        args += ["-s", str(season)]
    ep_range = entry.get("episode_range")
    if ep_range:
        args += ["-e", str(ep_range)]
    else:
        args += ["-e", "all"]
    return args


def fetch_for_target(
    target_path: Path,
    is_folder: bool,
    key: str,
    entry: dict,
    dry_run: bool,
    mt_engine: str | None,
) -> None:
    """Run fetch for one disk target (a folder or a bare file)."""
    profile = entry.get("profile", "en")
    fetch_langs = PROFILE_FETCH_LANGS.get(profile, PROFILE_FETCH_LANGS["en"])
    mt_source = PROFILE_MT_SOURCE.get(profile, PROFILE_MT_SOURCE["en"])

    label_path = str(target_path)
    heading(f"[{profile}]  {key}  →  {label_path}")
    base_args, ident = build_base_args(entry)
    if not base_args:
        print("  (skip) no title / anilist / imdb in reference entry")
        return
    print(f"  identifier: {ident}")

    # For bare files (no surrounding folder), use the parent dir as
    # output. The .srt(s) will land next to the .mkv/.mp4.
    output_dir = target_path if is_folder else target_path.parent

    # Step 1: fetch the profile's preferred human-quality langs.
    fetch_cmd = (
        ["getsubtitle"]
        + base_args
        + episode_args(entry)
        + ["-l", ",".join(fetch_langs)]
        + ["--layout", "flat", "-o", str(output_dir), "-y"]
    )
    print(f"\n  fetch: -l {','.join(fetch_langs)}")
    run_getsubtitle(fetch_cmd, dry_run=dry_run)

    # Step 2: MT fallback for any of those langs that came up empty.
    # We can't easily detect which ones missed without parsing
    # getsubtitle output, so we ask `translate` to fill anything
    # missing in the folder — it's idempotent (skips existing .srt).
    if mt_engine:
        translate_cmd = (
            ["getsubtitle", "translate", str(output_dir)]
            + ["-l", ",".join(fetch_langs)]
            + ["--mt-engine", mt_engine]
            + ["--mt-source-lang", mt_source]
        )
        print(f"\n  mt fallback: -l {','.join(fetch_langs)} via {mt_engine} ({mt_source}→targets)")
        run_getsubtitle(translate_cmd, dry_run=dry_run)


def process_root(root: Path, dry_run: bool, mt_engine: str | None) -> None:
    ref = load_reference()
    entries = entries_from(ref)

    folders = find_video_folders(root)
    bare_files = find_bare_video_files(root)

    matched = 0
    unmatched: list[Path] = []

    # Process folders. For Plex-style Season XX subdirs, the parent will
    # match the reference key and the same entry is run once per season
    # subdir — which is the right behavior (each season needs its own
    # fetch). For movies with one folder, this runs once. We dedupe by
    # the season-subdir path itself so we don't re-walk the parent.
    for folder in folders:
        m = match_entry(folder, root, entries)
        if not m:
            unmatched.append(folder)
            continue
        key, entry = m
        fetch_for_target(
            target_path=folder,
            is_folder=True,
            key=key,
            entry=entry,
            dry_run=dry_run,
            mt_engine=mt_engine,
        )
        matched += 1

    # Process bare files (loose .mkv movies at the top level).
    for f in bare_files:
        m = match_entry(f, root, entries)
        if not m:
            unmatched.append(f)
            continue
        key, entry = m
        fetch_for_target(
            target_path=f,
            is_folder=False,
            key=key,
            entry=entry,
            dry_run=dry_run,
            mt_engine=mt_engine,
        )
        matched += 1

    print()
    print(f"Processed {matched} target(s).")
    if unmatched:
        print(f"Unmatched ({len(unmatched)}): no reference.json entry —")
        for u in unmatched:
            try:
                print(f"  {u.relative_to(root)}")
            except ValueError:
                print(f"  {u}")
        print("Add entries to reference.json (or run lookup.py later) to include these.")


def main() -> int:
    p = argparse.ArgumentParser(
        prog="batch/fetch.py",
        description="Walk CWD, match folders/files against reference.json, "
                    "and fetch missing subtitles via the existing `getsubtitle` CLI.",
    )
    p.add_argument(
        "--run", action="store_true",
        help="Actually run the commands. Without this flag, every getsubtitle "
             "call gets --dry-run appended.",
    )
    p.add_argument(
        "--mt-engine", default="ollama", choices=["", "argos", "ollama", "deepl"],
        help="Engine for the MT fallback pass. Use '' to skip MT entirely "
             "and only run the provider fetch. Default: ollama.",
    )
    p.add_argument(
        "--root", default=".",
        help="Root directory to walk. Default: current directory.",
    )
    args = p.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"--root must be a directory: {root}")

    dry_run = not args.run
    mt_engine = args.mt_engine or None
    mode = "DRY RUN (no writes)" if dry_run else "LIVE"
    mt_note = f"MT engine: {mt_engine}" if mt_engine else "MT disabled"
    print(f"batch fetch — root: {root}")
    print(f"mode: {mode}  |  {mt_note}")

    process_root(root, dry_run=dry_run, mt_engine=mt_engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
