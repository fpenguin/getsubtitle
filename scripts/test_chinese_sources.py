#!/usr/bin/env python3
"""Smoke-test Chinese subtitle source coverage for getsubtitle.

Default mode is offline-safe: it reports which source integrations are present
and verifies local Chinese subtitle parsing. Use --live for light provider and
candidate-community probes.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import getsubtitle_core as core  # noqa: E402


DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "chinese_sample.srt"


@dataclass
class SourceResult:
    source: str
    status: str
    notes: str


def _safe_key(provider: str) -> str | None:
    env_name = f"{provider.upper()}_API_KEY"
    if os.environ.get(env_name):
        return os.environ[env_name]
    try:
        return core.get_provider_api_key(provider, prompt_if_missing=False)
    except Exception:
        return None


def format_table(rows: list[SourceResult]) -> str:
    headers = ("Source", "Status", "Notes")
    widths = [
        max(len(headers[0]), *(len(r.source) for r in rows)),
        max(len(headers[1]), *(len(r.status) for r in rows)),
        max(len(headers[2]), *(len(r.notes) for r in rows)),
    ]
    lines = [
        f"{headers[0]:<{widths[0]}}  {headers[1]:<{widths[1]}}  {headers[2]}",
        f"{'-' * widths[0]}  {'-' * widths[1]}  {'-' * widths[2]}",
    ]
    for row in rows:
        lines.append(f"{row.source:<{widths[0]}}  {row.status:<{widths[1]}}  {row.notes}")
    return "\n".join(lines)


def _fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "getsubtitle-chinese-smoke/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def _sample_titles() -> list[core.MediaInfo]:
    return [
        core.MediaInfo(
            source_url="https://www.imdb.com/title/tt0245429/",
            provider="imdb",
            title="Spirited Away",
            title_aliases=["千と千尋の神隠し", "千与千寻", "神隱少女"],
            imdb_id="tt0245429",
            season="auto",
            episode="auto",
        ),
        core.MediaInfo(
            source_url="https://www.imdb.com/title/tt2560140/",
            provider="imdb",
            title="Attack on Titan",
            title_aliases=["進撃の巨人", "Shingeki no Kyojin", "进击的巨人", "進擊的巨人"],
            imdb_id="tt2560140",
            season="1",
        ),
    ]


def wyzie_check(*, live: bool, episodes: list[str]) -> SourceResult:
    if not hasattr(core, "WyzieProvider"):
        return SourceResult("Wyzie", "not implemented", "Provider class missing")
    key = _safe_key("wyzie")
    if not key:
        return SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie")
    if not live:
        return SourceResult("Wyzie", "ready", "Key configured; run with --live to query zh results")

    provider = core.WyzieProvider(key)
    langs = ["zh", "zh-cn", "zh-tw", "chi", "zho"]
    hits: list[str] = []
    errors: list[str] = []
    for media in _sample_titles():
        probe_episodes = ["auto"] if media.season == "auto" else episodes
        for episode in probe_episodes:
            for lang in langs:
                try:
                    files = provider.files(media, episode, lang)
                except Exception as e:
                    errors.append(f"{media.title} {lang}: {e}")
                    continue
                if files:
                    names = ", ".join(f.name for f in files[:2])
                    hits.append(f"{media.title} {lang}: {len(files)} ({names})")
                    break
                time.sleep(0.25)
            time.sleep(0.25)

    if hits:
        return SourceResult("Wyzie", "ok", f"Found Chinese candidates: {hits[0][:140]}")
    if errors:
        return SourceResult("Wyzie", "error", errors[0][:140])
    return SourceResult("Wyzie", "no results", "No zh/zh-cn/zh-tw candidates in sample probes")


def subhd_check(*, live: bool, fetcher: Callable[[str], str] = _fetch_text) -> SourceResult:
    if not live:
        return SourceResult("SubHD", "candidate", "Chinese-focused community; no provider yet")

    # Search and detail URL shapes have changed over time, so this only checks
    # reachability and subtitle-like page markers, not extraction.
    urls = [
        "https://subhd.tv/",
        "https://subhd.cc/",
        "https://subhd.me/",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            html = fetcher(url)
        except urllib.error.HTTPError as e:
            errors.append(f"{url}: HTTP {e.code}")
            continue
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        if re.search(r"字幕|SubHD|srt|ass|ssa|download", html, re.I):
            return SourceResult("SubHD", "reachable", f"{url} exposes subtitle-site markers")
        time.sleep(0.4)
    return SourceResult("SubHD", "blocked/error", errors[0][:140] if errors else "No subtitle markers found")


def zimuku_check(*, live: bool, fetcher: Callable[[str], str] = _fetch_text) -> SourceResult:
    if not live:
        return SourceResult("Zimuku/SrtKu", "candidate", "Chinese subtitle community; provider not implemented")

    # Known domains rotate. These are availability probes only; downloader work
    # should inspect current Kodi/ZiMuKuX add-on logic before implementation.
    urls = [
        "https://www.zimuku.org/",
        "https://zimuku.org/",
        "https://zmk.pw/",
        "https://www.srtku.com/",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            html = fetcher(url)
        except urllib.error.HTTPError as e:
            errors.append(f"{url}: HTTP {e.code}")
            continue
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        if re.search(r"字幕库|字幕|Zimuku|SrtKu|srt|ass|ssa", html, re.I):
            return SourceResult("Zimuku/SrtKu", "reachable", f"{url} exposes subtitle-site markers")
        time.sleep(0.4)
    return SourceResult("Zimuku/SrtKu", "blocked/error", errors[0][:140] if errors else "No subtitle markers found")


def local_chinese_check(fixture: Path = DEFAULT_FIXTURE) -> SourceResult:
    if not fixture.exists():
        return SourceResult("Local SRT", "error", f"Fixture missing: {fixture}")
    try:
        cues = core.read_cues_from_file(fixture)
    except Exception as e:
        return SourceResult("Local SRT", "error", str(e)[:140])
    joined = "\n".join(line for cue in cues for line in cue.text_lines)
    if cues and any("\u4e00" <= ch <= "\u9fff" for ch in joined):
        return SourceResult("Local SRT", "ok", f"Parsed Chinese SRT ({len(cues)} cue(s))")
    return SourceResult("Local SRT", "error", "Parsed no Chinese cue text")


def local_ass_status() -> SourceResult:
    fixture = ROOT / "tests" / "fixtures" / "chinese_sample.ass"
    if not fixture.exists():
        return SourceResult("Local ASS/SSA", "error", f"Fixture missing: {fixture}")
    try:
        cues = core.read_cues_from_file(fixture)
    except Exception as e:
        return SourceResult("Local ASS/SSA", "error", str(e)[:140])
    if cues:
        return SourceResult("Local ASS/SSA", "ok", f"Parsed Chinese ASS/SSA-style input ({len(cues)} cue(s))")
    return SourceResult("Local ASS/SSA", "error", "Parsed no ASS/SSA cues")


def manual_source_rows() -> list[SourceResult]:
    return [
        SourceResult("SubDL direct", "not implemented", "API exists; likely good direct fallback beyond Wyzie"),
        SourceResult("OpenSubtitles direct", "not implemented", "Likely broad zh/zh-CN/zh-TW fallback"),
        SourceResult("Official streaming", "manual", "Netflix/Disney+/Prime often have region-specific Chinese tracks"),
    ]


def run_checks(*, live: bool, episodes: list[str]) -> list[SourceResult]:
    return [
        wyzie_check(live=live, episodes=episodes),
        subhd_check(live=live),
        zimuku_check(live=live),
        *manual_source_rows(),
        local_chinese_check(),
        local_ass_status(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Chinese subtitle source coverage for getsubtitle.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Probe public/provider endpoints. Default is offline-safe.",
    )
    parser.add_argument(
        "-e",
        "--episodes",
        default="1",
        help="Comma-separated episode numbers to probe in live mode. Default: 1.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    episodes = [p.strip() for p in args.episodes.split(",") if p.strip()] or ["1"]

    rows = run_checks(live=args.live, episodes=episodes)
    if args.json:
        print(json.dumps({
            "name": "chinese",
            "mode": "live" if args.live else "offline",
            "results": [asdict(row) for row in rows],
        }, ensure_ascii=False, indent=2))
        return 0

    print("Chinese subtitle source smoke test")
    print(f"Mode: {'live network probes' if args.live else 'offline diagnostics'}")
    print()
    print(format_table(rows))
    print()
    if not args.live:
        print("Tip: run with --live to query configured providers and candidate community homepages.")
    print("Note: Public website availability is not permission to scrape heavily; keep probes light.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
