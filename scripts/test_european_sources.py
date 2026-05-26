#!/usr/bin/env python3
"""Smoke-test European-language subtitle source coverage for getsubtitle.

Default mode is offline-safe: it reports integration coverage and verifies
local subtitle parsing with European text. Use --live for light provider and
candidate-community probes.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import getsubtitle_core as core  # noqa: E402


DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "european_sample.srt"
DEFAULT_LANGS = ["fr", "de", "es", "it", "pt", "pl", "nl", "tr", "ru"]


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
            "User-Agent": "getsubtitle-european-smoke/0.1",
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
            title_aliases=["Le Voyage de Chihiro", "El viaje de Chihiro", "A Viagem de Chihiro"],
            imdb_id="tt0245429",
            season="auto",
            episode="auto",
        ),
        core.MediaInfo(
            source_url="https://www.imdb.com/title/tt14452776/",
            provider="imdb",
            title="The Bear",
            title_aliases=["El oso", "L'ours"],
            imdb_id="tt14452776",
            season="1",
        ),
    ]


def wyzie_check(*, live: bool, episodes: list[str], langs: list[str]) -> SourceResult:
    if not hasattr(core, "WyzieProvider"):
        return SourceResult("Wyzie", "not implemented", "Provider class missing")
    key = _safe_key("wyzie")
    if not key:
        return SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie")
    if not live:
        return SourceResult("Wyzie", "ready", f"Key configured; --live will query {','.join(langs)}")

    provider = core.WyzieProvider(key)
    found: dict[str, str] = {}
    sources: Counter[str] = Counter()
    errors: list[str] = []
    for media in _sample_titles():
        probe_episodes = ["auto"] if media.season == "auto" else episodes
        for episode in probe_episodes:
            for lang in langs:
                if lang in found:
                    continue
                try:
                    files = provider.files(media, episode, lang)
                except Exception as e:
                    errors.append(f"{media.title} {lang}: {e}")
                    continue
                if files:
                    first = files[0]
                    found[lang] = f"{media.title} ({len(files)})"
                    sources[first.source_provider or first.provider or "unknown"] += 1
                time.sleep(0.2)
            if len(found) == len(langs):
                break

    missing = [lang for lang in langs if lang not in found]
    if found:
        found_langs = [lang for lang in langs if lang in found]
        examples = ", ".join(f"{lang}:{found[lang]}" for lang in found_langs[:4])
        source_text = ", ".join(f"{src}:{count}" for src, count in sources.most_common(3))
        status = "ok" if not missing else "partial"
        note = f"Found {len(found)}/{len(langs)} langs ({','.join(found_langs)})"
        if examples:
            note += f"; examples {examples}"
        if source_text:
            note += f"; sources {source_text}"
        if missing:
            note += f"; missing {','.join(missing)}"
        return SourceResult("Wyzie", status, note[:220])
    if errors:
        return SourceResult("Wyzie", "error", errors[0][:160])
    return SourceResult("Wyzie", "no results", f"No candidates for {','.join(langs)} in sample probes")


def homepage_check(
    source: str,
    urls: list[str],
    marker_re: str,
    *,
    live: bool,
    offline_note: str,
    fetcher: Callable[[str], str] = _fetch_text,
) -> SourceResult:
    if not live:
        return SourceResult(source, "candidate", offline_note)
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
        if re.search(marker_re, html, re.I):
            return SourceResult(source, "reachable", f"{url} exposes subtitle-site markers")
        time.sleep(0.4)
    return SourceResult(source, "blocked/error", errors[0][:160] if errors else "No subtitle markers found")


def subdivx_status(*, live: bool) -> SourceResult:
    if hasattr(core, "SubdivxProvider"):
        return SourceResult("Subdivx", "available", "Experimental Spanish provider already exists")
    return homepage_check(
        "Subdivx",
        ["https://www.subdivx.com/"],
        r"subtit|srt|descargar",
        live=live,
        offline_note="Spanish / Latin American Spanish community",
    )


def local_european_check(fixture: Path = DEFAULT_FIXTURE) -> SourceResult:
    if not fixture.exists():
        return SourceResult("Local SRT", "error", f"Fixture missing: {fixture}")
    try:
        cues = core.read_cues_from_file(fixture)
    except Exception as e:
        return SourceResult("Local SRT", "error", str(e)[:160])
    joined = "\n".join(line for cue in cues for line in cue.text_lines)
    expected = ["é", "ñ", "ş", "ł", "Пр"]
    if cues and all(token in joined for token in expected):
        return SourceResult("Local SRT", "ok", f"Parsed multilingual European SRT ({len(cues)} cue(s))")
    return SourceResult("Local SRT", "error", "Parsed text but lost expected accents/scripts")


def manual_source_rows(*, live: bool) -> list[SourceResult]:
    return [
        homepage_check(
            "Podnapisi",
            ["https://www.podnapisi.net/"],
            r"subtitle|podnapisi|subtitles",
            live=live,
            offline_note="Central/Eastern Europe; likely strong via aggregators too",
        ),
        homepage_check(
            "TVsubtitles",
            ["https://www.tvsubtitles.net/"],
            r"subtitles|TVsubtitles",
            live=live,
            offline_note="Older TV episode subtitles",
        ),
        homepage_check(
            "Subf2m",
            ["https://subf2m.co/"],
            r"subtitles|sous-titres|download",
            live=live,
            offline_note="French-focused candidate",
        ),
        homepage_check(
            "Legendas.TV",
            ["https://legendas.tv/"],
            r"legendas|subtitle|baixar",
            live=live,
            offline_note="Portuguese/Brazilian Portuguese; likely login friction",
        ),
        homepage_check(
            "TurkceAltyazi",
            ["https://turkcealtyazi.org/"],
            r"altyaz|subtitle|film",
            live=live,
            offline_note="Turkish community; likely browser/manual flow",
        ),
        SourceResult("SubDL direct", "not implemented", "Probably the first direct API to add if Wyzie misses European languages"),
        SourceResult("OpenSubtitles direct", "not implemented", "Useful fallback, but auth/quota friction is higher than Wyzie"),
    ]


def run_checks(*, live: bool, episodes: list[str], langs: list[str]) -> list[SourceResult]:
    return [
        wyzie_check(live=live, episodes=episodes, langs=langs),
        subdivx_status(live=live),
        *manual_source_rows(live=live),
        local_european_check(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test European-language subtitle source coverage for getsubtitle.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Probe public/provider endpoints. Default is offline-safe.",
    )
    parser.add_argument(
        "-l",
        "--langs",
        default=",".join(DEFAULT_LANGS),
        help="Comma-separated language codes to probe. Default: fr,de,es,it,pt,pl,nl,tr,ru.",
    )
    parser.add_argument(
        "-e",
        "--episodes",
        default="1",
        help="Comma-separated episode numbers to probe in live mode. Default: 1.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    langs = core.split_csv(args.langs, ",".join(DEFAULT_LANGS))
    episodes = [p.strip() for p in args.episodes.split(",") if p.strip()] or ["1"]

    rows = run_checks(live=args.live, episodes=episodes, langs=langs)
    if args.json:
        print(json.dumps({
            "name": "european",
            "mode": "live" if args.live else "offline",
            "languages": langs,
            "results": [asdict(row) for row in rows],
        }, ensure_ascii=False, indent=2))
        return 0

    print("European subtitle source smoke test")
    print(f"Mode: {'live network probes' if args.live else 'offline diagnostics'}")
    print(f"Languages: {', '.join(langs)}")
    print()
    print(format_table(rows))
    print()
    if not args.live:
        print("Tip: run with --live to compare Wyzie coverage against candidate source reachability.")
    print("Note: Public website availability is not permission to scrape heavily; keep probes light.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
