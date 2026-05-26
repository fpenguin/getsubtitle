#!/usr/bin/env python3
"""Run all getsubtitle source smoke diagnostics."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ("korean", ROOT / "scripts" / "test_korean_sources.py"),
    ("chinese", ROOT / "scripts" / "test_chinese_sources.py"),
    ("european", ROOT / "scripts" / "test_european_sources.py"),
]


def run_one(script: Path, *, live: bool) -> dict:
    cmd = [sys.executable, str(script), "--json"]
    if live:
        cmd.append("--live")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if proc.returncode != 0:
        return {
            "name": script.stem,
            "mode": "live" if live else "offline",
            "error": (proc.stderr or proc.stdout).strip(),
            "results": [],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "name": script.stem,
            "mode": "live" if live else "offline",
            "error": "script did not return JSON",
            "results": [],
        }


def print_summary(results: list[dict]) -> None:
    print("All subtitle source smoke tests")
    print()
    for result in results:
        print(f"{result.get('name', 'unknown').title()} ({result.get('mode', 'offline')}):")
        if result.get("error"):
            print(f"  error: {result['error']}")
            continue
        for row in result.get("results", []):
            source = row.get("source", "")
            status = row.get("status", "")
            notes = row.get("notes", "")
            print(f"  {source:<20} {status:<15} {notes}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Korean, Chinese, and European source smoke diagnostics.")
    parser.add_argument("--live", action="store_true", help="Run live provider/site probes.")
    parser.add_argument("--json", action="store_true", help="Print combined machine-readable JSON.")
    args = parser.parse_args(argv)

    results = [run_one(script, live=args.live) for _name, script in SCRIPTS]
    if args.json:
        print(json.dumps({"mode": "live" if args.live else "offline", "groups": results}, ensure_ascii=False, indent=2))
        return 0
    print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
