#!/usr/bin/env python3
"""Researches 4-6 tools/projects/approaches for a given weekly roundup topic."""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

from model_selector import build_candidate_list

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
TOPIC_FILE = Path("/tmp/roundup_topic.json")
RESEARCH_FILE = Path("/tmp/roundup_research.json")
SEEN_FILE = Path(__file__).parent / "seen.json"

HEADERS = {"User-Agent": "tenkai-bot/1.0 (github.com/mcfredrick/tenkai)"}
TIMEOUT = 20

SYSTEM_PROMPT = """You are a research assistant for Tenkai, a weekly AI/dev tools digest for senior engineers.

Given a topic and a list of candidate items found across GitHub and HN, select 4-6 items that best address the topic.

Quality bar — only include items that pass ALL of these:
- Real adoption: GitHub repos must have meaningful stars (listed in the candidate data). Reject anything that looks experimental or toy-level.
- Actively maintained: recent commits or releases, not abandoned side projects.
- Concrete utility: engineers can install and use it today, not "coming soon" or research-only.
- Avoid: pure academic papers, vague blog posts with no tools, company marketing, anything with <50 stars unless it has exceptional HN engagement (>100 points).

For each selected item return:
{
  "name": "project or tool name",
  "url": "canonical URL (GitHub repo, docs, or project page)",
  "summary": "2-3 sentences: what it is, what problem it solves, why it's relevant to the topic",
  "category": one of: "tool", "library", "technique", "service"
}

Return ONLY a JSON array of 4-6 items. No markdown fences."""


def _get(url: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  fetch failed {url}: {e}", file=sys.stderr)
        return None


def load_seen_urls() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    data = json.loads(SEEN_FILE.read_text())
    return {e["url"] for e in data.get("urls", [])}


def search_hn(query: str) -> list[dict]:
    r = _get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "tags": "story",
            "query": query,
            "numericFilters": "points>10",
            "hitsPerPage": 10,
        },
    )
    if not r:
        return []
    return [
        {
            "title": hit.get("title", ""),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "text": f"HN: {hit.get('points', 0)} pts, {hit.get('num_comments', 0)} comments",
        }
        for hit in r.json().get("hits", [])
    ]


def search_github(query: str) -> list[dict]:
    since = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    gh_headers = {**HEADERS}
    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN")
    if token:
        gh_headers["Authorization"] = f"Bearer {token}"

    try:
        r = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": f"{query} pushed:>{since}", "sort": "stars", "order": "desc", "per_page": 10},
            headers=gh_headers,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  GitHub search failed: {e}", file=sys.stderr)
        return []

    results = []
    for repo in r.json().get("items", []):
        stars = repo.get("stargazers_count", 0)
        desc = repo.get("description") or ""
        # Minimum quality bar: enough stars to indicate real adoption, has a description
        if stars < 50 or not desc:
            continue
        results.append({
            "title": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "text": f"Stars: {stars}. {desc}",
            "stars": stars,
        })
    return results


def call_llm(content: str, preferred_model: str) -> list[dict] | None:
    import re
    api_key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/mcfredrick/tenkai",
        "X-Title": "Tenkai Roundup Agent",
    }
    for candidate in build_candidate_list(preferred_model, api_key):
        print(f"  Trying: {candidate}", file=sys.stderr)
        try:
            payload = {
                "model": candidate,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            }
            r = httpx.post(OPENROUTER_API, json=payload, headers=headers, timeout=120)
            if r.status_code == 429:
                print(f"  Rate limited, skipping", file=sys.stderr)
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  {candidate}: invalid JSON — {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {candidate} error: {e}", file=sys.stderr)
    return None


def build_prompt(topic: dict, candidates: list[dict], seen_urls: set[str]) -> str:
    fresh = [c for c in candidates if c.get("url") not in seen_urls]
    lines = [
        f"TOPIC: {topic['topic']}",
        f"DESCRIPTION: {topic['description']}",
        "",
        f"CANDIDATES ({len(fresh)} items, already filtered for freshness):",
    ]
    for item in fresh[:40]:
        lines.append(f"\nTitle: {item['title']}")
        lines.append(f"URL: {item['url']}")
        lines.append(f"Info: {item['text'][:300]}")
    return "\n".join(lines)


# Broad fallback queries used when topic-specific searches return thin results
_BROAD_FALLBACK_QUERIES = {
    "mcp": ["mcp server claude", "model context protocol"],
    "agent": ["llm agent framework", "ai coding agent"],
    "token": ["llm token optimization", "context compression"],
    "memory": ["llm memory agent", "long term memory llm"],
    "rag": ["rag retrieval augmented", "vector database llm"],
}

MIN_QUALITY_CANDIDATES = 8  # trigger broad fallback if below this


def _broad_queries_for_topic(topic_name: str) -> list[str]:
    """Pick broad fallback queries based on keywords in the topic name."""
    lower = topic_name.lower()
    for keyword, queries in _BROAD_FALLBACK_QUERIES.items():
        if keyword in lower:
            return queries
    return []


def validate_items(items: list[dict], candidate_urls: set[str]) -> list[dict]:
    """Drop items whose URLs weren't in the candidates list (likely hallucinated)."""
    valid, dropped = [], []
    for item in items:
        url = item.get("url", "")
        # Normalise trailing slashes for comparison
        if url.rstrip("/") in {u.rstrip("/") for u in candidate_urls}:
            valid.append(item)
        else:
            dropped.append(item.get("name", url))
    if dropped:
        print(f"  Dropped {len(dropped)} hallucinated items: {dropped}", file=sys.stderr)
    return valid


def main() -> None:
    if not TOPIC_FILE.exists():
        raise RuntimeError(f"Topic file not found: {TOPIC_FILE}")

    topic = json.loads(TOPIC_FILE.read_text())
    print(f"Researching topic: {topic['topic']}", file=sys.stderr)

    model = os.environ.get("RESEARCH_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    print(f"Research model: {model}", file=sys.stderr)

    seen_urls = load_seen_urls()

    candidates: list[dict] = []
    for query in topic.get("search_queries", []):
        print(f"  Searching HN: {query}", file=sys.stderr)
        candidates.extend(search_hn(query))
        print(f"  Searching GitHub: {query}", file=sys.stderr)
        candidates.extend(search_github(query))

    # If topic-specific searches are thin, try broad fallback queries
    if len(candidates) < MIN_QUALITY_CANDIDATES:
        print(f"  Only {len(candidates)} candidates — trying broad fallbacks", file=sys.stderr)
        for query in _broad_queries_for_topic(topic["topic"]):
            candidates.extend(search_hn(query))
            candidates.extend(search_github(query))

    # Deduplicate by URL
    seen_in_batch: set[str] = set()
    deduped = []
    for c in candidates:
        if c["url"] not in seen_in_batch:
            seen_in_batch.add(c["url"])
            deduped.append(c)
    candidates = deduped
    print(f"Found {len(candidates)} unique candidates", file=sys.stderr)

    if not candidates:
        raise RuntimeError("No candidates found for topic — cannot produce roundup")

    candidate_urls = {c["url"] for c in candidates}
    prompt = build_prompt(topic, candidates, seen_urls)
    items = call_llm(prompt, model)

    if not items:
        raise RuntimeError("LLM returned no items")

    # Drop any items the LLM invented that weren't in the candidates
    items = validate_items(items, candidate_urls)

    if len(items) < 4:
        raise RuntimeError(f"Only {len(items)} valid items after hallucination check (minimum 4)")

    result = {"topic": topic, "items": items}
    RESEARCH_FILE.write_text(json.dumps(result, indent=2))
    print(f"Wrote {len(items)} items to {RESEARCH_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
