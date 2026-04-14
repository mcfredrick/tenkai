#!/usr/bin/env python3
"""Writes a roundup post from roundup_research.json."""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from model_selector import build_candidate_list

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
RESEARCH_FILE = Path("/tmp/roundup_research.json")
SEEN_FILE = Path(__file__).parent / "seen.json"
POSTS_DIR = Path(__file__).parent.parent / "content" / "posts"

SYSTEM_PROMPT = """You are the voice behind Tenkai, writing a weekly deep-dive for senior engineers.

This is NOT the daily news digest. This is an editorial roundup: a focused look at 4-6 tools or
approaches that address a specific topic engineers care about right now.

Voice: casual, opinionated, no hype. Write like a senior engineer sharing what they'd actually use.

Structure (output ONLY the markdown body, no frontmatter):

Start with a short opening paragraph (2-4 sentences): what the topic is, why it matters this week,
and a quick characterization of what you found. No heading — just prose.

Then for each item, use this EXACT format — the heading MUST be a markdown link:
## [Name](url)
2-4 sentences. What it actually does. A concrete example of how you'd use it or why it matters.
An honest take — if there's a catch or a tradeoff, say so.

CRITICAL: The ## heading must be a clickable markdown link: ## [Name](url). Never write a plain ## heading like ## SomeTool. Always ## [SomeTool](https://github.com/...).

End with:
## The Takeaway
2-4 sentences tying the items together. What does this collection say about where the ecosystem
is heading? What would you actually reach for first?

Rules:
- No section headers other than per-item ## headers and ## The Takeaway
- No bullets — prose only in the opening and takeaway, per-item sections are also prose
- No "check out", "dive into", "leverage", "unleash"
- Emojis sparingly if they add personality — skip them if forced
- Do NOT include a synthesis section or sign-off"""


def _try_model(content: str, model: str, headers: dict) -> str | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.7,
        "max_tokens": 3000,
    }
    r = httpx.post(OPENROUTER_API, json=payload, headers=headers, timeout=180)
    if r.status_code == 429:
        return None
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return text.strip() if text else None


def call_llm(content: str, preferred_model: str) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/mcfredrick/tenkai",
        "X-Title": "Tenkai Roundup Writer",
    }
    import time

    candidates = build_candidate_list(preferred_model, api_key)

    for candidate in candidates:
        max_attempts = 3 if candidate == preferred_model else 1
        for attempt in range(max_attempts):
            print(f"  Trying: {candidate}" + (f" (attempt {attempt + 1})" if max_attempts > 1 else ""), file=sys.stderr)
            try:
                result = _try_model(content, candidate, headers)
                if result is None:
                    wait = 30 * (2 ** attempt)
                    print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                print(f"  Success: {candidate}", file=sys.stderr)
                return result
            except httpx.HTTPStatusError as e:
                print(f"  {candidate} HTTP {e.response.status_code}, skipping", file=sys.stderr)
                break
            except Exception as e:
                print(f"  {candidate} error: {e}, skipping", file=sys.stderr)
                break

    raise RuntimeError("All writing models exhausted")


def build_prompt(research: dict) -> str:
    topic = research["topic"]
    items = research["items"]
    lines = [
        f"TOPIC: {topic['topic']}",
        f"DESCRIPTION: {topic['description']}",
        f"RATIONALE: {topic['rationale']}",
        "",
        "ITEMS TO COVER (write each as ## [name](url) — use the URL provided):",
    ]
    for item in items:
        lines.append(f"\nName: {item['name']}")
        lines.append(f"URL: {item['url']}  ← use this as the link in the ## heading")
        lines.append(f"Summary: {item['summary']}")
    return "\n".join(lines)


def build_description(items: list[dict]) -> str:
    names = [item.get("name", "") for item in items[:3] if item.get("name")]
    if not names:
        return "Weekly AI tools roundup"
    return "This week: " + ", ".join(names) + " and more."


def update_seen(new_urls: list[str], post_date: str) -> None:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=60)
    data = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {"urls": []}
    data["urls"] = [
        entry for entry in data["urls"]
        if datetime.fromisoformat(entry["date"]).replace(tzinfo=timezone.utc) > cutoff
    ]
    existing = {e["url"] for e in data["urls"]}
    for url in new_urls:
        if url and url not in existing:
            data["urls"].append({"url": url, "date": post_date})
    SEEN_FILE.write_text(json.dumps(data, indent=2))


def main() -> None:
    if not RESEARCH_FILE.exists():
        raise RuntimeError(f"Research file not found: {RESEARCH_FILE}")

    research = json.loads(RESEARCH_FILE.read_text())
    topic = research["topic"]
    items = research["items"]

    model = os.environ.get("WRITING_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    print(f"Writing model: {model}", file=sys.stderr)

    prompt = build_prompt(research)
    body = call_llm(prompt, model)

    post_date = date.today()
    post_date_str = str(post_date)
    post_date_fmt = post_date.strftime("%B %-d, %Y")

    description = build_description(items)
    title = topic['topic']

    front_matter = f"""---
title: "{title}"
date: {post_date_str}
draft: false
tags: [roundup]
description: "{description}"
---

"""

    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]
    post_path = POSTS_DIR / f"{post_date_str}-{slug}.md"
    post_path.write_text(front_matter + body)
    print(f"Wrote post: {post_path}", file=sys.stderr)

    new_urls = [item.get("url", "") for item in items]
    update_seen(new_urls, post_date_str)
    print(f"Updated seen.json with {len(new_urls)} URLs", file=sys.stderr)


if __name__ == "__main__":
    main()
