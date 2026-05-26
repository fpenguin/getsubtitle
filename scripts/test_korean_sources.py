#!/usr/bin/env python3
"""Smoke-test Korean subtitle source coverage for getsubtitle.

Default mode is offline-safe: it reports which source integrations are present
and verifies the local Korean SAMI (.smi) conversion path. Use --live to probe
public/provider endpoints with light, read-only requests.
"""

import argparse
import json
import os
import re
import shutil
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


DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "korean_sample.smi"


@dataclass
class SourceResult:
    source: str
    status: str
    notes: str


def _has_class(name: str) -> bool:
    return hasattr(core, name)


def _safe_key(provider: str) -> str | None:
    """Return a configured key without prompting or failing the smoke test."""
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
            "User-Agent": "getsubtitle-korean-smoke/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def _sample_titles() -> list[core.MediaInfo]:
    return [
        core.MediaInfo(
            source_url="https://www.imdb.com/title/tt28299608/",
            provider="imdb",
            title="MF Ghost",
            title_aliases=["MFゴースト", "MF 고스트"],
            imdb_id="tt28299608",
            tmdb_id="154526",
            tvdb_id="414207",
            season="1",
        ),
        core.MediaInfo(
            source_url="https://www.imdb.com/title/tt2560140/",
            provider="imdb",
            title="Attack on Titan",
            title_aliases=["進撃の巨人", "Shingeki no Kyojin", "진격의 거인"],
            imdb_id="tt2560140",
            season="1",
        ),
    ]


def wyzie_check(*, live: bool, episodes: list[str]) -> SourceResult:
    if not _has_class("WyzieProvider"):
        return SourceResult("Wyzie", "not implemented", "Provider class missing")
    key = _safe_key("wyzie")
    if not key:
        return SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie")
    if not live:
        return SourceResult("Wyzie", "ready", "Key configured; run with --live to query ko results")

    provider = core.WyzieProvider(key)
    hits: list[str] = []
    misses: list[str] = []
    errors: list[str] = []
    for media in _sample_titles():
        for episode in episodes:
            try:
                files = provider.files(media, episode, "ko")
            except Exception as e:
                errors.append(f"{media.title} E{episode}: {e}")
                continue
            if files:
                hits.append(f"{media.title} E{episode}: {len(files)}")
            else:
                misses.append(f"{media.title} E{episode}")
            time.sleep(0.4)

    if hits:
        return SourceResult("Wyzie", "ok", f"Found ko candidates: {', '.join(hits[:3])}")
    if errors:
        return SourceResult("Wyzie", "error", errors[0][:120])
    return SourceResult("Wyzie", "no results", f"No ko candidates for {len(misses)} title/episode probes")


def addic7ed_check(*, live: bool, episodes: list[str]) -> SourceResult:
    if not _has_class("Addic7edProvider"):
        return SourceResult("Addic7ed", "not implemented", "Provider class missing")
    if not live:
        return SourceResult("Addic7ed", "available", "Experimental provider present; run with --live sparingly")

    provider = core.Addic7edProvider(enabled=True)
    media = core.MediaInfo(
        source_url="",
        provider="manual",
        title="Attack on Titan",
        title_aliases=["Shingeki no Kyojin", "진격의 거인"],
        season="1",
    )
    try:
        files, diagnostic = provider.files(media, episodes[0])
    except Exception as e:
        return SourceResult("Addic7ed", "error", str(e)[:120])
    if files:
        return SourceResult("Addic7ed", "ok", f"Found {len(files)} Korean candidate(s)")
    return SourceResult("Addic7ed", "no results", diagnostic or "No Korean download links")


def gomlab_check(*, live: bool, fetcher: Callable[[str], str] = _fetch_text) -> SourceResult:
    if not live:
        return SourceResult("GOM Lab", "candidate", "No provider yet; --live probes public search pages")

    queries = ["진격의 거인", "Attack on Titan", "MF Ghost", "MF 고스트"]
    hits: list[str] = []
    errors: list[str] = []
    for query in queries:
        params = urllib.parse.urlencode({"keyword": query})
        urls = [
            f"https://www.gomlab.com/subtitle/?{params}",
            f"https://www.gomlab.com/en/subtitle/?{params}",
        ]
        for url in urls:
            try:
                html = fetcher(url)
            except urllib.error.HTTPError as e:
                errors.append(f"HTTP {e.code}")
                continue
            except Exception as e:
                errors.append(str(e))
                continue
            # GOM pages may expose file names, detail URLs, or just result cards.
            smi_like = len(re.findall(r"\.smi\b|SAMI|subtitle-view|/subtitle/", html, re.I))
            if smi_like:
                hits.append(f"{query}: page has {smi_like} subtitle markers")
                break
        time.sleep(0.4)

        if hits:
            return SourceResult("GOM Lab", "promising", hits[0])

    # Search result HTML can be sparse or JS-shaped, while detail pages are
    # indexable and expose the .smi filename. These known public examples are
    # only used as a light availability probe, not as downloader targets.
    known_detail_urls = [
        "https://www.gomlab.com/subtitle-info?intseq=195517&keyword=&page=1879&preface=All",
        "https://www.gomlab.com/en/subtitle-info?intseq=193815&keyword=&page=1987&preface=All",
    ]
    for url in known_detail_urls:
        try:
            html = fetcher(url)
        except Exception as e:
            errors.append(str(e))
            continue
        if re.search(r"\.smi\b|Subtitle files|자막 파일", html, re.I):
            return SourceResult("GOM Lab", "promising", "Known detail page exposes .smi metadata")
        time.sleep(0.4)

    if errors:
        return SourceResult("GOM Lab", "blocked/error", errors[0][:120])
    return SourceResult("GOM Lab", "no results", "Search pages loaded but no subtitle markers found")


def local_smi_check(fixture: Path = DEFAULT_FIXTURE) -> SourceResult:
    if not fixture.exists():
        return SourceResult("Local SMI", "error", f"Fixture missing: {fixture}")
    with tempfile.TemporaryDirectory(prefix="getsubtitle-ko-smi-") as td:
        work = Path(td) / fixture.name
        shutil.copy2(fixture, work)
        try:
            written, skipped = core.convert_smi_file(work, force=False)
        except Exception as e:
            return SourceResult("Local SMI", "error", str(e)[:120])
        ko_written = [p for p in written if p.name.endswith(".ko.srt")]
        if ko_written:
            sample = ko_written[0].read_text(encoding="utf-8", errors="replace")
            cue_count = sample.count("-->")
            return SourceResult("Local SMI", "ok", f"Converted fixture to ko SRT ({cue_count} cue(s))")
        if skipped:
            return SourceResult("Local SMI", "skipped", "Output already existed in temp dir unexpectedly")
        return SourceResult("Local SMI", "error", "Conversion produced no Korean SRT")


def manual_source_rows() -> list[SourceResult]:
    return [
        SourceResult("Cineaste", "manual", "Community/login flow; do not scrape aggressively"),
        SourceResult("Bunyuc", "manual", "Community source candidate; needs browser-assisted review"),
        SourceResult("OpenSubtitles/SubDL", "not implemented", "Useful API-style fallback if added later"),
    ]


def run_checks(*, live: bool, episodes: list[str]) -> list[SourceResult]:
    rows = [
        wyzie_check(live=live, episodes=episodes),
        addic7ed_check(live=live, episodes=episodes),
        gomlab_check(live=live),
        *manual_source_rows(),
        local_smi_check(),
    ]
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Korean subtitle source coverage for getsubtitle.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Probe public/provider endpoints. Default is offline-safe.",
    )
    parser.add_argument(
        "-e",
        "--episodes",
        default="1,5",
        help="Comma-separated episode numbers to probe in live mode. Default: 1,5.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    episodes = [p.strip() for p in args.episodes.split(",") if p.strip()] or ["1"]

    rows = run_checks(live=args.live, episodes=episodes)
    if args.json:
        print(json.dumps({
            "name": "korean",
            "mode": "live" if args.live else "offline",
            "results": [asdict(row) for row in rows],
        }, ensure_ascii=False, indent=2))
        return 0

    print("Korean subtitle source smoke test")
    print(f"Mode: {'live network probes' if args.live else 'offline diagnostics'}")
    print()
    print(format_table(rows))
    print()
    if not args.live:
        print("Tip: run with --live to query configured providers and public candidate pages.")
    print("Note: Public website availability is not permission to scrape heavily; keep probes light.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
