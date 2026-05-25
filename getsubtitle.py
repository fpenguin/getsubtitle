"""Console entry point for getsubtitle."""

from __future__ import annotations

import sys
from typing import Sequence

import getsubtitle_core


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return getsubtitle_core.main(list(argv) if argv is not None else None)
    except getsubtitle_core.CliError as e:
        print(f"getsubtitle: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
