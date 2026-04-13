#!/usr/bin/env python3
"""Fetches sources, calls research LLM to extract items, writes /tmp/research.json."""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from sources import ALL_SOURCES

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
SEEN_FILE = Path(__file__).parent / "seen.json"
WATCHLIST_FILE = Path(__file__).parent.parent / "watchlist.txt"
OUTPUT_FILE = Path("/tmp/research.json")
BUSINESS_KEYWORDS = {"funding", "valuation", "ipo", "acquisition", "acquires", "merger", "raises", "series a", "series b", "series c"}

SYSTEM_PROMPT = """You are a technical research assistant for AI/ML engineers.

Extract technically relevant items from the provided content. Focus on:
- New open-source releases and framework updates
- Practical research papers with engineering implications
- Developer techniques, tools, and libraries
- Performance benchmarks and optimization findings

Exclude strictly:
- Business news: funding, acquisitions, valuations, IPOs, layoffs
- Marketing announcements without technical substance
- Hype without concrete details

For each item, if multiple URLs point to the same story, pick the most useful/canonical one.

Return ONLY a JSON array. Each element must have exactly these fields:
{
  "title": "concise title",
  "url": "canonical URL",
  "summary": "2-3 sentence technical summary",
  "category": "release|paper|discussion|tutorial",
  "relevance_score": <integer 1-10>
}

Drop items with relevance_score below 7. Return [] if nothing qualifies.

Items marked [CURATED - author hand-picked] were personally selected by the author — treat them as high-priority and include at least one per post if they meet the minimum quality bar."""


def load_seen_urls() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    data = json.loads(SEEN_FILE.read_text())
    return {entry["url"] for entry in data.get("urls", [])}


def load_watchlist(seen_urls: set[str], path: Path = WATCHLIST_FILE) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    kept_lines = []
    urls = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept_lines.append(line)
            continue
        if stripped not in seen_urls:
            kept_lines.append(line)
            urls.append(stripped)
    path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""))
    return urls


def save_watchlist(consumed_urls: set[str], path: Path = WATCHLIST_FILE) -> None:
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    kept_lines = [
        line for line in lines
        if not line.strip() or line.strip().startswith("#") or line.strip() not in consumed_urls
    ]
    path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""))


def fetch_url(url: str) -> str:
    try:
        r = httpx.get(
            url,
            headers={"User-Agent": "tenkai-bot/1.0 (github.com/mattdlong/tenkai)"},
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.text[:2000]
    except Exception as e:
        print(f"  fetch failed {url}: {e}", file=sys.stderr)
        return ""


def call_llm(content: str, model: str, retries: int = 3) -> list[dict] | None:
    """Call the LLM to extract and filter items.

    Returns a list on success (possibly empty if model found nothing worth keeping),
    or None if all attempts failed (caller should fall back to rule-based filtering).
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "HTTP-Referer": "https://github.com/mcfredrick/tenkai",
        "X-Title": "Tenkai Research Agent",
    }

    for attempt in range(retries):
        try:
            r = httpx.post(OPENROUTER_API, json=payload, headers=headers, timeout=120)
            if r.status_code == 429:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            # Extract JSON array from response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            return json.loads(text[start:end])
        except Exception as e:
            print(f"  LLM call failed (attempt {attempt + 1}): {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)

    return None


def passthrough_filter(items: list[dict]) -> list[dict]:
    """Rule-based fallback when LLM is unavailable.

    Applies seen-URL and business-news filters, assigns a default category
    and relevance score so downstream code works without LLM scoring.
    """
    results = []
    for raw in items[:20]:  # cap to avoid bloating the post
        item = {
            "title": raw.get("title", ""),
            "url": raw.get("url", ""),
            "summary": raw.get("text", "")[:300],
            "category": "release",
            "relevance_score": 7,
        }
        if is_business_news(item):
            continue
        try:
            item = recategorize(item)
        except Exception:
            pass
        results.append(item)
    return results


import re as _re

# Word-boundary pattern prevents "cli" from matching "client", etc.
# fine-tun prefix catches fine-tuning/fine-tune without a trailing boundary.
_DEV_TOOL_PATTERN = _re.compile(
    r"\b(?:framework|platform|agents?|sdk|cli|toolkit)\b|fine-tun\w*",
    _re.IGNORECASE,
)


def recategorize(item: dict) -> dict:
    """Override LLM-assigned category using URL patterns and keywords."""
    url = item.get("url", "").lower()
    text = item.get("title", "") + " " + item.get("summary", "")

    if "huggingface.co/" in url:
        return {**item, "category": "model"}
    if "arxiv.org/" in url or "openreview.net/" in url:
        return {**item, "category": "paper"}
    if "smithery.ai/servers/" in url:
        return {**item, "category": "mcp"}
    if "github.com/" in url and _DEV_TOOL_PATTERN.search(text):
        return {**item, "category": "dev-tool"}

    return item


def is_business_news(item: dict) -> bool:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(kw in text for kw in BUSINESS_KEYWORDS)


def fetch_all_sources() -> dict[str, list[dict]]:
    raw: dict[str, list[dict]] = {}
    for name, fetcher in ALL_SOURCES.items():
        print(f"Fetching {name}...", file=sys.stderr)
        try:
            raw[name] = fetcher()
            print(f"  {len(raw[name])} items", file=sys.stderr)
        except Exception as e:
            print(f"  Error fetching {name}: {e}", file=sys.stderr)
            raw[name] = []
    return raw


def build_prompt_for_source(name: str, items: list[dict]) -> str:
    lines = [f"Source: {name}", ""]
    for item in items[:30]:  # cap per source to manage token usage
        lines.append(f"Title: {item.get('title', '')}")
        lines.append(f"URL: {item.get('url', '')}")
        lines.append(f"Text: {item.get('text', '')[:400]}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    model = os.environ.get("RESEARCH_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    print(f"Research model: {model}", file=sys.stderr)

    seen_urls = load_seen_urls()
    print(f"Loaded {len(seen_urls)} seen URLs", file=sys.stderr)

    watchlist_urls = load_watchlist(seen_urls)
    if watchlist_urls:
        print(f"Loaded {len(watchlist_urls)} watchlist URLs", file=sys.stderr)

    raw_sources = fetch_all_sources()

    # Process each source through LLM
    results: dict[str, list[dict]] = {"date": str(date.today())}

    # Process curated watchlist items first
    if watchlist_urls:
        curated_items = []
        for url in watchlist_urls:
            print(f"Fetching curated URL: {url}", file=sys.stderr)
            text = fetch_url(url)
            curated_items.append({"title": url, "url": url, "text": text})

        print("Processing curated watchlist with LLM...", file=sys.stderr)
        prompt = build_prompt_for_source("[CURATED - author hand-picked]", curated_items)
        extracted = call_llm(prompt, model)
        if extracted is None:
            print("  LLM unavailable, using passthrough for curated items", file=sys.stderr)
            extracted = passthrough_filter(curated_items)
        filtered = [item for item in extracted if item.get("url") not in seen_urls and not is_business_news(item)]
        results["curated"] = filtered
        print(f"  {len(filtered)} curated items after filtering", file=sys.stderr)

    for source_name, items in raw_sources.items():
        if not items:
            results[source_name] = []
            continue

        print(f"Processing {source_name} with LLM...", file=sys.stderr)
        prompt = build_prompt_for_source(source_name, items)
        extracted = call_llm(prompt, model)
        if extracted is None:
            print(f"  LLM unavailable, using passthrough for {source_name}", file=sys.stderr)
            extracted = passthrough_filter(items)

        filtered = []
        for item in extracted:
            if item.get("url") in seen_urls or is_business_news(item):
                continue
            try:
                item = recategorize(item)
            except Exception as e:
                print(f"  recategorize failed for {item.get('url', '?')}: {e}", file=sys.stderr)
            filtered.append(item)
        results[source_name] = filtered
        print(f"  {len(filtered)} items after filtering", file=sys.stderr)

    total = sum(len(v) for v in results.values() if isinstance(v, list))
    print(f"Total research items: {total}", file=sys.stderr)

    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"Wrote {OUTPUT_FILE}", file=sys.stderr)

    # Remove consumed watchlist URLs from watchlist.txt
    if watchlist_urls:
        consumed = {item["url"] for items in results.values() if isinstance(items, list) for item in items}
        save_watchlist(consumed)


if __name__ == "__main__":
    main()
