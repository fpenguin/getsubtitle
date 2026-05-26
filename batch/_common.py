"""Shared helpers for the getsubtitle batch tooling.

Both fetch.py and merge.py walk the current working directory, match
folders against reference.json, and shell out to `getsubtitle`. This
module centralises the discovery and matching logic so the two scripts
stay thin and consistent.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REFERENCE = SCRIPT_DIR / "reference.json"

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".webm", ".m2ts", ".ts", ".wmv", ".mov", ".m4v"}
SUBTITLE_EXTS = {".srt", ".smi", ".ass", ".vtt", ".ssa"}


def load_reference() -> dict:
    """Load reference.json. Aborts cleanly if missing or malformed."""
    if not REFERENCE.exists():
        sys.exit(f"reference.json not found at {REFERENCE}")
    try:
        return json.loads(REFERENCE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"reference.json is not valid JSON: {e}")


def entries_from(ref: dict) -> dict:
    """Return the entries dict from a parsed reference.json."""
    entries = ref.get("entries", {})
    if not isinstance(entries, dict):
        sys.exit("reference.json: 'entries' must be an object")
    return entries


def find_video_folders(root: Path) -> list[Path]:
    """Return folders under root that contain at least one video file,
    plus the root itself if any video files live there. Deduplicated and
    sorted. Returns folders only — see find_bare_video_files for loose
    movie files at the top level."""
    folders: set[Path] = set()
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            folders.add(p.parent)
    return sorted(folders)


def find_bare_video_files(root: Path) -> list[Path]:
    """Return video files that live directly in `root` (no surrounding
    folder). Used for the bare-mkv movies (Kill Boksoon, #Alive, etc.)."""
    return sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def match_entry(target: Path, root: Path, entries: dict) -> tuple[str, dict] | None:
    """Try to map a folder (or bare file) to a reference entry.

    Matching order:
      1. Exact relative path from root (e.g. "유포니움/1기")
      2. Walk up the parent chain (so "Show/Season 01" matches "Show")
      3. Bare filename for loose files (e.g. "Kill Boksoon ... .mkv")

    Returns (matched_key, entry) or None."""
    try:
        rel = target.relative_to(root)
    except ValueError:
        rel = Path(target.name)

    candidates: list[str] = []
    parts = rel.parts
    for i in range(len(parts), 0, -1):
        candidates.append("/".join(parts[:i]))
    # Also try the bare basename in case the entry is keyed that way.
    if rel.name not in candidates:
        candidates.append(rel.name)

    for key in candidates:
        if key in entries:
            return key, entries[key]
    return None


def run_getsubtitle(cmd: list[str], dry_run: bool, verbose: bool = True) -> int:
    """Run a getsubtitle command. Returns its exit code.

    If dry_run is True, --dry-run is appended (unless already present).
    Prints the command before running so the user can copy-paste."""
    args = list(cmd)
    if dry_run and "--dry-run" not in args:
        args.append("--dry-run")
    if verbose:
        # Shell-quote so the printed line is paste-safe.
        print("  $ " + " ".join(shlex.quote(a) for a in args))
    result = subprocess.run(args, check=False)
    return result.returncode


def list_subtitle_files(folder: Path, suffix_lower: str | None = None) -> list[Path]:
    """List subtitle files in `folder` (non-recursive). If suffix_lower is
    given (e.g. '.smi', '.srt'), filter to that extension."""
    out: list[Path] = []
    if not folder.is_dir():
        return out
    for p in folder.iterdir():
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in SUBTITLE_EXTS:
            continue
        if suffix_lower and ext != suffix_lower:
            continue
        out.append(p)
    return sorted(out)


def heading(text: str) -> None:
    """Print a section header so per-show output is easy to scan."""
    bar = "─" * max(40, len(text))
    print()
    print(bar)
    print(text)
    print(bar)
