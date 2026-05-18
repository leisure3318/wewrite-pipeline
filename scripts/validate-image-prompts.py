#!/usr/bin/env python3
"""Validate wewrite-pipeline Baoyu image prompt structure."""

from __future__ import annotations

import sys
from pathlib import Path


COVER_REQUIRED = [
    "---",
    "type: cover",
    "palette:",
    "rendering:",
    "# Content Context",
    "# Visual Design",
    "# Text Elements",
    "# Mood Application",
    "# Font Application",
    "# Composition",
]

BODY_REQUIRED = [
    "---",
    "illustration_id:",
    "type:",
    "style:",
    "palette:",
    "ZONES:",
    "LABELS:",
    "COLORS:",
    "STYLE:",
    "ASPECT:",
]


def missing_markers(path: Path, markers: list[str]) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return [marker for marker in markers if marker not in content]


def validate_group(directory: Path, markers: list[str], label: str) -> list[str]:
    errors: list[str] = []
    files = sorted(directory.glob("*.md"))
    if not files:
        return [f"{label}: no prompt files found in {directory}"]
    for path in files:
        missing = missing_markers(path, markers)
        if missing:
            errors.append(f"{path}: missing {', '.join(missing)}")
    return errors


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("Usage: validate-image-prompts.py <article_dir> [--cover-only|--body-only]", file=sys.stderr)
        return 2
    mode = sys.argv[2] if len(sys.argv) == 3 else ""
    if mode not in {"", "--cover-only", "--body-only"}:
        print("Usage: validate-image-prompts.py <article_dir> [--cover-only|--body-only]", file=sys.stderr)
        return 2
    article_dir = Path(sys.argv[1]).expanduser().resolve()
    errors = []
    if mode != "--body-only":
        errors.extend(validate_group(article_dir / "02-cover" / "prompts", COVER_REQUIRED, "cover"))
    if mode != "--cover-only":
        errors.extend(validate_group(article_dir / "03-images" / "prompts", BODY_REQUIRED, "body"))
    if errors:
        print("Image prompt validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"✓ Image prompt QA passed: {article_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
