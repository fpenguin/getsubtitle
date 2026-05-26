#!/usr/bin/env python3
"""getsubtitle batch — merge.

Walk the current directory, match each show/movie folder against
reference.json, and produce combined subtitle outputs via the existing
`getsubtitle combine` command.

Per-profile merge rules:
  ja  Convert any .smi → .ko.srt first, then combine ja+ko (master=ja,
      furigana on). One stacked output per episode.
  ko  Convert any .smi → .ko.srt first (rare for Korean shows but
      possible), then combine ko+ja (master=ko, furigana on). Plus a
      ko+ja+en+es quad if those side files exist.
  en  Two outputs:
        1. en+es dual (the "watch with Spanish learner" stack)
        2. ja+ko+en+es quad (the full study stack)
      Master=en, furigana on for any ja line present.

Usage:
  cd /path/to/your/plex/library
  python3 /path/to/getsubtitle/batch/merge.py [--run]

Default is dry-run. Add --run to actually merge.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    entries_from,
    find_video_folders,
    heading,
    list_subtitle_files,
    load_reference,
    match_entry,
    run_getsubtitle,
)


def convert_smi(folder: Path, dry_run: bool) -> bool:
    """Run `getsubtitle modify --convert smi-to-srt` if any .smi files
    are present in the folder. Returns True if conversion ran. Uses
    `--force` so re-runs after the first pass produce consistent .ko.srt
    (overwriting any prior auto-conversion). Existing human .ko.srt are
    NOT auto-overwritten because they'd be touched only if a .smi
    happens to live alongside them — uncommon."""
    smis = list_subtitle_files(folder, suffix_lower=".smi")
    if not smis:
        return False
    cmd = [
        "getsubtitle", "modify", str(folder),
        "--convert", "smi-to-srt",
        "--force",
    ]
    print(f"  smi→srt: {len(smis)} .smi file(s)")
    run_getsubtitle(cmd, dry_run=dry_run)
    return True


def combine_run(folder: Path, langs: list[str], master: str, with_furigana: bool,
                fmt: str | None, dry_run: bool, label: str) -> None:
    """Issue one `getsubtitle combine` call with the given language stack."""
    cmd = [
        "getsubtitle", "combine", str(folder),
        "-l", ",".join(langs),
        "--master", master,
    ]
    if with_furigana:
        cmd.append("--furigana")
    if fmt:
        cmd += ["--format", fmt]
    print(f"  combine ({label}): -l {','.join(langs)}  master={master}"
          + ("  +furigana" if with_furigana else ""))
    run_getsubtitle(cmd, dry_run=dry_run)


def merge_for_target(
    folder: Path,
    key: str,
    entry: dict,
    dry_run: bool,
    fmt: str | None,
) -> None:
    profile = entry.get("profile", "en")
    heading(f"[{profile}]  {key}  →  {folder}")

    # Step 1: convert any .smi present (no-op if none).
    convert_smi(folder, dry_run=dry_run)

    # Step 2: combine per profile.
    if profile == "ja":
        combine_run(
            folder, langs=["ja", "ko"], master="ja",
            with_furigana=True, fmt=fmt, dry_run=dry_run,
            label="JP master dual",
        )
    elif profile == "ko":
        # Primary: ko+ja dual.
        combine_run(
            folder, langs=["ko", "ja"], master="ko",
            with_furigana=True, fmt=fmt, dry_run=dry_run,
            label="KR master dual",
        )
        # Bonus: ko+ja+en+es quad if any of en/es happen to be present.
        # combine itself will skip langs with no file, so this is safe
        # to issue unconditionally — output filename differs.
        combine_run(
            folder, langs=["ko", "ja", "en", "es"], master="ko",
            with_furigana=True, fmt=fmt, dry_run=dry_run,
            label="KR master quad",
        )
    else:  # en (and zh/fr/it/etc treated as en for our workflow)
        # Dual EN+ES for the common "watch in es, study en" use case.
        combine_run(
            folder, langs=["en", "es"], master="en",
            with_furigana=False, fmt=fmt, dry_run=dry_run,
            label="EN master dual",
        )
        # Full quad with ja+ko for the language-learner stack.
        combine_run(
            folder, langs=["ja", "ko", "en", "es"], master="en",
            with_furigana=True, fmt=fmt, dry_run=dry_run,
            label="EN master quad",
        )


def process_root(root: Path, dry_run: bool, fmt: str | None) -> None:
    ref = load_reference()
    entries = entries_from(ref)

    folders = find_video_folders(root)
    matched = 0
    unmatched: list[Path] = []

    for folder in folders:
        m = match_entry(folder, root, entries)
        if not m:
            unmatched.append(folder)
            continue
        key, entry = m
        merge_for_target(
            folder=folder, key=key, entry=entry,
            dry_run=dry_run, fmt=fmt,
        )
        matched += 1

    print()
    print(f"Processed {matched} folder(s).")
    if unmatched:
        print(f"Unmatched ({len(unmatched)}): no reference.json entry —")
        for u in unmatched:
            try:
                print(f"  {u.relative_to(root)}")
            except ValueError:
                print(f"  {u}")
        print("Add entries to reference.json to include these.")


def main() -> int:
    p = argparse.ArgumentParser(
        prog="batch/merge.py",
        description="Walk CWD, convert any .smi to .ko.srt, then combine "
                    "language stacks per the reference.json profile.",
    )
    p.add_argument(
        "--run", action="store_true",
        help="Actually run the commands. Without this flag, every "
             "getsubtitle call gets --dry-run appended.",
    )
    p.add_argument(
        "--format", default=None, choices=["srt", "vtt"],
        help="Combined output format. Default: getsubtitle's default (srt). "
             "Pass vtt for asbplayer-friendly ruby furigana.",
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
    mode = "DRY RUN (no writes)" if dry_run else "LIVE"
    print(f"batch merge — root: {root}")
    print(f"mode: {mode}  |  format: {args.format or 'default (srt)'}")

    process_root(root, dry_run=dry_run, fmt=args.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
