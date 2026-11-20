"""Pre-commit guard: each commit carries 20-80 lines of production code.

Counts added + deleted lines of staged files. Tests, docs, lockfiles and
config templates are not production code and are not counted.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_PROD_LOC = 80
MIN_PROD_LOC = 20
EXEMPT_PATTERNS = (
    "*.md",
    "*.lock",
    "pyproject.toml",
    "config.example.yaml",
    ".gitignore",
    "LICENSE",
    "docs/*",
    "tests/fixtures/*",
    ".githooks/*",
)
TEST_PATTERNS = ("tests/*",)
TEST_BASENAME_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")


@dataclass
class Counts:
    """Line counts per file class."""

    production: int = 0
    test: int = 0
    exempt: int = 0


def resolve_rename(path: str) -> str:
    """Return the new path from a git numstat rename entry.

    Args:
        path: Path as printed by ``git diff --numstat -M``, e.g.
            ``src/{a.py => b.py}`` or ``a.py => b.py``.

    Returns:
        The destination path.
    """
    if " => " not in path:
        return path
    if "{" in path and "}" in path:
        head, rest = path.split("{", 1)
        inner, tail = rest.split("}", 1)
        new = inner.split(" => ", 1)[1]
        return (head + new + tail).replace("//", "/")
    return path.split(" => ", 1)[1]


def classify(path: str) -> str:
    """Classify a repo path as ``exempt``, ``test`` or ``production``."""
    name = PurePosixPath(path).name
    if any(fnmatch.fnmatch(path, p) for p in EXEMPT_PATTERNS):
        return "exempt"
    if any(fnmatch.fnmatch(path, p) for p in TEST_PATTERNS) or any(
        fnmatch.fnmatch(name, p) for p in TEST_BASENAME_PATTERNS
    ):
        return "test"
    return "production"


def count_numstat(numstat: str) -> Counts:
    """Sum added + deleted lines per class from ``git diff --numstat`` output."""
    counts = Counts()
    for line in numstat.splitlines():
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        lines = (0 if added == "-" else int(added)) + (0 if deleted == "-" else int(deleted))
        kind = classify(resolve_rename(path))
        setattr(counts, kind, getattr(counts, kind) + lines)
    return counts


def evaluate(counts: Counts, max_loc: int = MAX_PROD_LOC, min_loc: int = MIN_PROD_LOC) -> tuple[int, str]:
    """Return (exit code, message) for the given counts."""
    summary = f"production={counts.production} test={counts.test} exempt={counts.exempt}"
    if counts.production > max_loc:
        return 1, f"REJECTED: {summary}. Over {max_loc} production lines - split the slice."
    if 0 < counts.production < min_loc:
        return 0, f"WARNING: {summary}. Under {min_loc} production lines - is this a whole unit of function?"
    return 0, f"OK: {summary}"


def staged_numstat() -> str:
    """Read numstat of the staged changes."""
    return subprocess.run(
        ["git", "diff", "--cached", "--numstat", "-M"], check=True, capture_output=True, text=True
    ).stdout


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=MAX_PROD_LOC)
    parser.add_argument("--min", type=int, default=MIN_PROD_LOC)
    args = parser.parse_args(argv)
    code, message = evaluate(count_numstat(staged_numstat()), args.max, args.min)
    print(f"[commit-size] {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
