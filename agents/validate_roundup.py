#!/usr/bin/env python3
"""Validates a weekly roundup post. Exits 0 if valid, 1 if not."""

import re
import sys
from pathlib import Path

MIN_ITEMS = 4


def validate(path: Path) -> list[str]:
    if not path.exists():
        return [f"Post file not found: {path}"]

    text = path.read_text()

    if text.startswith("---"):
        end = text.index("---", 3)
        body = text[end + 3:].lstrip("\n")
    else:
        body = text

    errors = []

    # Must have an opening paragraph before the first ## heading
    first_heading = re.search(r'^## ', body, re.MULTILINE)
    if not first_heading or not body[:first_heading.start()].strip():
        errors.append("Missing opening paragraph before first ## section")

    # Must have at least MIN_ITEMS ## sections that contain a markdown link somewhere
    # (ideally in the heading as ## [Name](url), but the whole section is checked)
    item_sections = [
        s for s in re.split(r'(?=^## )', body, flags=re.MULTILINE)
        if s.startswith("## ") and "## The Takeaway" not in s and re.search(r'\]\(https?://', s)
    ]
    if len(item_sections) < MIN_ITEMS:
        errors.append(f"Only {len(item_sections)} item sections with links (minimum {MIN_ITEMS})")

    # Must have a Takeaway section
    if "## The Takeaway" not in body:
        errors.append("Missing '## The Takeaway' section")

    # No space URLs (hallucinated broken links)
    bad_urls = re.findall(r'\]\((https?://[^)]*\s[^)]*)\)', body)
    if bad_urls:
        errors.append(f"Links with spaces in URL (hallucinated): {bad_urls[:3]}")

    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: validate_roundup.py <post.md>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    errors = validate(path)

    if errors:
        print(f"Roundup validation failed: {path}", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Roundup valid: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
