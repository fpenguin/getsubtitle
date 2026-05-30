#!/usr/bin/env python3
"""Smoke-test ASSRT/Shooter API viability for getsubtitle.

This script is intentionally separate from the main downloader. It probes the
official token-based API lightly so we can decide whether an ASSRT provider is
worth implementing.

Usage:
  ASSRT_API_KEY=... scripts/test_assrt_api.py "The Matrix"
  ASSRT_API_KEY=... scripts/test_assrt_api.py "千与千寻" --json

It does not scrape community pages, bypass login/ad gates, or download files
unless the API response exposes direct download metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_BASE = "https://api.assrt.net/v1"


@dataclass
class AssrtSmokeResult:
    step: str
    status: str
    notes: str


def _request_json(url: str, *, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "getsubtitle-assrt-smoke/0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response: {raw[:160]!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def _api_url(base: str, path: str, params: dict[str, str]) -> str:
    return base.rstrip("/") + path + "?" + urllib.parse.urlencode(params)


def _items_from_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # ASSRT responses have changed shape over time; accept common object paths
    # so the smoke test remains useful even when the docs drift slightly.
    candidates: list[Any] = [
        payload.get("sub", {}).get("subs") if isinstance(payload.get("sub"), dict) else None,
        payload.get("sub", {}).get("list") if isinstance(payload.get("sub"), dict) else None,
        payload.get("subs"),
        payload.get("list"),
        payload.get("data", {}).get("subs") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("list") if isinstance(payload.get("data"), dict) else None,
    ]
    for value in candidates:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _pick_id(item: dict[str, Any]) -> str | None:
    for key in ("id", "sub_id", "sid", "native_name"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _summarize_item(item: dict[str, Any]) -> str:
    name = (
        item.get("native_name")
        or item.get("videoname")
        or item.get("title")
        or item.get("filename")
        or item.get("release_site")
        or "unnamed"
    )
    lang = item.get("lang") or item.get("language") or item.get("langdesc") or "unknown-lang"
    fmt = item.get("subtype") or item.get("format") or item.get("ext") or "unknown-format"
    return f"{name} [{lang}, {fmt}]"


def run_smoke(title: str, *, token: str, base: str, detail: bool) -> list[AssrtSmokeResult]:
    rows: list[AssrtSmokeResult] = []
    search_url = _api_url(base, "/sub/search", {"token": token, "q": title})
    try:
        search_payload = _request_json(search_url)
    except urllib.error.HTTPError as exc:
        return [AssrtSmokeResult("search", "http-error", f"HTTP {exc.code}: {exc.reason}")]
    except Exception as exc:
        return [AssrtSmokeResult("search", "error", str(exc))]

    status = str(search_payload.get("status", search_payload.get("code", "")))
    if status and status not in {"0", "200", "success", "ok"}:
        rows.append(AssrtSmokeResult("search", "api-status", f"status={status}; response keys={sorted(search_payload)[:8]}"))

    items = _items_from_search(search_payload)
    if not items:
        rows.append(AssrtSmokeResult("search", "no-results", f"No subtitles returned for {title!r}; response keys={sorted(search_payload)[:8]}"))
        return rows

    rows.append(AssrtSmokeResult("search", "ok", f"{len(items)} result(s); first: {_summarize_item(items[0])}"))
    if not detail:
        return rows

    item_id = _pick_id(items[0])
    if not item_id:
        rows.append(AssrtSmokeResult("detail", "skip", "First result had no obvious id/sub_id/sid field"))
        return rows

    detail_url = _api_url(base, "/sub/detail", {"token": token, "id": item_id})
    try:
        detail_payload = _request_json(detail_url)
    except urllib.error.HTTPError as exc:
        rows.append(AssrtSmokeResult("detail", "http-error", f"HTTP {exc.code}: {exc.reason}"))
        return rows
    except Exception as exc:
        rows.append(AssrtSmokeResult("detail", "error", str(exc)))
        return rows

    detail_keys = sorted(detail_payload.keys())
    text = json.dumps(detail_payload, ensure_ascii=False)
    has_download = any(word in text.lower() for word in ("download", "url", "filelist", "subs"))
    rows.append(AssrtSmokeResult(
        "detail",
        "ok" if has_download else "unclear",
        f"id={item_id}; keys={detail_keys[:8]}; download-like metadata={'yes' if has_download else 'no'}",
    ))
    return rows


def print_table(rows: list[AssrtSmokeResult]) -> None:
    headers = ("Step", "Status", "Notes")
    widths = [
        max(len(headers[0]), *(len(r.step) for r in rows)),
        max(len(headers[1]), *(len(r.status) for r in rows)),
    ]
    print(f"{headers[0]:<{widths[0]}}  {headers[1]:<{widths[1]}}  {headers[2]}")
    print(f"{'-' * widths[0]}  {'-' * widths[1]}  {'-' * 40}")
    for row in rows:
        print(f"{row.step:<{widths[0]}}  {row.status:<{widths[1]}}  {row.notes}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test ASSRT/Shooter API coverage.")
    parser.add_argument("title", nargs="?", default="The Matrix", help="Title/query to search.")
    parser.add_argument("--token", default=os.environ.get("ASSRT_API_KEY"), help="ASSRT API token. Defaults to ASSRT_API_KEY.")
    parser.add_argument("--base", default=os.environ.get("ASSRT_API_BASE", DEFAULT_BASE), help=f"API base URL. Default: {DEFAULT_BASE}")
    parser.add_argument("--no-detail", action="store_true", help="Only search; skip detail probe.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    if not args.token:
        rows = [AssrtSmokeResult("auth", "missing", "Set ASSRT_API_KEY or pass --token.")]
        if args.json:
            print(json.dumps({"name": "assrt", "results": [asdict(row) for row in rows]}, ensure_ascii=False, indent=2))
        else:
            print("ASSRT API smoke test")
            print_table(rows)
        return 2

    rows = run_smoke(args.title, token=args.token, base=args.base, detail=not args.no_detail)
    if args.json:
        print(json.dumps({
            "name": "assrt",
            "query": args.title,
            "base": args.base,
            "results": [asdict(row) for row in rows],
        }, ensure_ascii=False, indent=2))
        return 0

    print("ASSRT API smoke test")
    print(f"Query: {args.title}")
    print(f"Base:  {args.base}")
    print()
    print_table(rows)
    print()
    print("Note: keep probes light. This script is for API viability checks, not scraping.")
    return 0 if all(row.status not in {"error", "http-error", "missing"} for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
