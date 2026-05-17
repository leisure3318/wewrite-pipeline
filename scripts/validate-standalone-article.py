#!/usr/bin/env python3
"""Validate that a source-derived article reads as a standalone WeChat article.

The source URL/transcript may be stored in metadata, but the public body should not
frame the piece as a video recap or transcript commentary unless the user asked for
that format explicitly.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SOURCE_FRAME_PATTERNS = [
    r"看完这个视频",
    r"看完这[条个]内容",
    r"这个视频",
    r"这条视频",
    r"原视频",
    r"本视频",
    r"视频作者",
    r"视频里",
    r"视频中",
    r"字幕里",
    r"字幕中",
    r"原字幕",
    r"博主说",
    r"作者说",
    r"UP\s*主",
    r"up\s*主",
    r"观后感",
]


def body_without_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)


def validate(path: Path) -> list[tuple[int, str, str]]:
    body = body_without_frontmatter(path.read_text(encoding="utf-8"))
    findings: list[tuple[int, str, str]] = []
    regexes = [(pat, re.compile(pat, re.I)) for pat in SOURCE_FRAME_PATTERNS]
    for line_no, line in enumerate(body.splitlines(), 1):
        for pat, rx in regexes:
            if rx.search(line):
                findings.append((line_no, pat, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown_file", type=Path)
    args = parser.parse_args()

    findings = validate(args.markdown_file)
    if not findings:
        print(f"✓ Standalone article QA passed: {args.markdown_file}")
        return 0

    print(f"✗ Standalone article QA failed: {args.markdown_file}", file=sys.stderr)
    for line_no, pat, line in findings:
        print(f"  line {line_no}: /{pat}/ -> {line}", file=sys.stderr)
    print("Rewrite the body so the source becomes background material, not the article frame.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
