#!/usr/bin/env python3
"""Rewrites existing posts using the current SYSTEM_PROMPT style."""

import os
import re
import sys
from pathlib import Path

from writing_agent import SYSTEM_PROMPT, call_llm

POSTS_DIR = Path(__file__).parent.parent / "content" / "posts"

REWRITE_USER_PROMPT = """\
Rewrite the following blog post body in the new style described in your instructions.
Preserve all links, facts, and section structure — only change the writing style.
Output ONLY the rewritten markdown body (no front matter).

---
{body}
"""


def split_front_matter(text: str) -> tuple[str, str]:
    """Return (front_matter_block, body). front_matter_block includes the --- delimiters."""
    if not text.startswith("---"):
        return ("", text)
    end = text.index("---", 3)
    front = text[: end + 3]
    body = text[end + 3 :].lstrip("\n")
    return front, body


def rewrite_post(path: Path, model: str) -> None:
    text = path.read_text()
    front_matter, body = split_front_matter(text)

    if not body.strip():
        print(f"  Skipping {path.name}: no body", file=sys.stderr)
        return

    print(f"  Rewriting {path.name}...", file=sys.stderr)
    prompt = REWRITE_USER_PROMPT.format(body=body)
    new_body = call_llm(prompt, model)
    path.write_text(front_matter + "\n\n" + new_body + "\n")
    print(f"  Done: {path.name}", file=sys.stderr)


def main() -> None:
    model = os.environ.get("WRITING_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    # Accept explicit post filenames/dates as args; default to all posts
    if sys.argv[1:]:
        paths = []
        for arg in sys.argv[1:]:
            # Accept bare date (2026-03-14) or full filename
            name = arg if arg.endswith(".md") else f"{arg}.md"
            p = POSTS_DIR / name
            if not p.exists():
                print(f"Not found: {p}", file=sys.stderr)
                sys.exit(1)
            paths.append(p)
    else:
        paths = sorted(POSTS_DIR.glob("*.md"))

    if not paths:
        print("No posts found.", file=sys.stderr)
        sys.exit(0)

    print(f"Rewriting {len(paths)} post(s) with model {model}", file=sys.stderr)
    for path in paths:
        rewrite_post(path, model)


if __name__ == "__main__":
    main()
