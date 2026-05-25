"""Import wrapper for the getsubtitle executable module."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Sequence


_module = runpy.run_path(str(Path(__file__).with_name("getsubtitle")), run_name="getsubtitle_script")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _module["main"](list(argv) if argv is not None else None)
    except _module["CliError"] as e:
        print(f"getsubtitle: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
