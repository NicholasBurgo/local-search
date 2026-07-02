#!/usr/bin/env python3
"""Fail if any tracked source/doc file contains non-ASCII characters.

Keeps the tree ASCII-only (no emojis, em-dashes, or box-drawing characters).
Run locally or in CI: `uv run python scripts/check_ascii.py`.
"""

from __future__ import annotations

import pathlib
import sys

CHECK_EXTS = {".py", ".md", ".toml", ".cfg", ".yml", ".yaml", ".txt"}
CHECK_NAMES = {".env.example", ".gitignore"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "leads_output",
    "logs",
    ".pytest_cache",
    "assets",
}
ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    problems: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in CHECK_EXTS and path.name not in CHECK_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for col, ch in enumerate(line, 1):
                if ord(ch) > 127:
                    rel = path.relative_to(ROOT)
                    problems.append(f"{rel}:{lineno}:{col}: U+{ord(ch):04X} {ch!r}")

    if problems:
        print("Non-ASCII characters found:")
        for problem in problems:
            print("  " + problem)
        return 1
    print("ASCII check passed: no non-ASCII characters in source or docs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
