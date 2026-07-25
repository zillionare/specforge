"""Tiny Wordcount CLI — FR-1701 seed project.

Computes word/line/byte counts for one or more text files. The
implementation is intentionally small and dependency-free so the
FR-1701 lifecycle harness can build, install and publish it on a
localhost wheel sink without contacting any public registry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def count_file(path: Path) -> dict[str, int]:
    """Return ``{lines, words, bytes}`` for *path*."""
    text = path.read_text(encoding="utf-8")
    return {
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1 if text else 0),
        "words": len(text.split()),
        "bytes": len(text.encode("utf-8")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wordcount")
    parser.add_argument(
        "paths", nargs="+", type=Path, help="One or more text files to count."
    )
    parser.add_argument(
        "--format",
        choices={"table", "json"},
        default="table",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    rows = [(p, count_file(p)) for p in args.paths]
    if args.format == "json":
        json.dump(
            {str(p): r for p, r in rows},
            sys.stdout,
            sort_keys=True,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
    else:
        for p, r in rows:
            print(f"{p}\tlines={r['lines']}\twords={r['words']}\tbytes={r['bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
