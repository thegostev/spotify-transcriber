"""Commit-msg guard: conventional type in the subject and a Linear id."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TYPES = ("feat", "fix", "test", "refactor", "chore", "docs", "perf", "build", "ci", "style", "revert")
SUBJECT_RE = re.compile(rf"^({'|'.join(TYPES)})(\([\w./ -]+\))?!?: \S.*")
ISSUE_RE = re.compile(r"\bLAG-\d+\b")
PASSTHROUGH_PREFIXES = ("Merge ", "fixup! ", "squash! ", "amend! ")


def check_message(message: str) -> tuple[int, str]:
    """Return (exit code, reason) for a commit message.

    Args:
        message: Full commit message, comment lines included.
    """
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        return 1, "empty message"
    subject = text.splitlines()[0]
    if subject.startswith(PASSTHROUGH_PREFIXES):
        return 0, "passthrough"
    if not SUBJECT_RE.match(subject):
        return 1, f"subject must start with one of {', '.join(TYPES)}: '<type>(<scope>): <summary>'"
    if not ISSUE_RE.search(text):
        return 1, "message must reference a Linear issue, e.g. LAG-1046"
    return 0, "ok"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: takes the path git passes to commit-msg."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message_file", type=Path)
    args = parser.parse_args(argv)
    code, reason = check_message(args.message_file.read_text(encoding="utf-8"))
    if code:
        print(f"[commit-msg] REJECTED: {reason}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
