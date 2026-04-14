#!/usr/bin/env python3
"""
Test script: does reading content before LLM selection improve item quality?

Hypothesis: the current pipeline selects based on title+description metadata alone.
Adding a content-fetch step (README excerpts, article intros) before selection
should surface better, more relevant items.

Usage:
    OPENROUTER_API_KEY=... python agents/test_content_research.py

Prints two side-by-side selections for comparison:
  - METADATA ONLY (current behaviour)
  - WITH CONTENT    (proposed improvement)
"""

import base64
import json
import os
import re
import sys

import httpx

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from model_selector import build_candidate_list

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {"User-Agent": "tenkai-bot/1.0 (github.com/mcfredrick/tenkai)"}
TIMEOUT = 20
CONTENT_CHARS = 600  # chars of content to include per candidate

TOPIC = "Token optimization for coding agents"
TOPIC_DESC = (
    "How engineers reduce token waste in LLM-powered coding assistants and agents — "
    "covering prompt compression, context management, tool call pruning, and "
    "environment design to get more reliable output at lower cost."
)

# Candidates that came out of the last run (metadata only, as the current pipeline sees them)
EXISTING_CANDIDATES = [
    {
        "title": "russelleNVy/three-man-team",
        "url": "https://github.com/russelleNVy/three-man-team",
        "text": "Stars: 52. Three-agent coordination: Architect, Builder, Reviewer",
    },
    {
        "title": "langchain-ai/langchain",
        "url": "https://github.com/langchain-ai/langchain",
        "text": "Stars: 99000. Build context-aware reasoning applications",
    },
    {
        "title": "langchain-ai/langgraph",
        "url": "https://github.com/langchain-ai/langgraph",
        "text": "Stars: 12000. Build resilient language agents as graphs",
    },
    {
        "title": "openai/openai-agents-python",
        "url": "https://github.com/openai/openai-agents-python",
        "text": "Stars: 8000. Lightweight multi-agent orchestration framework",
    },
    {
        "title": "warpdotdev/Warp",
        "url": "https://github.com/warpdotdev/Warp",
        "text": "Stars: 22000. The intelligent terminal",
    },
]

# Additional candidates we expect to be highly relevant but didn't surface
SEEDED_CANDIDATES = [
    {
        "title": "anthropics/claude-code",
        "url": "https://github.com/anthropics/claude-code",
        "text": "Stars: 14000. Claude Code is Anthropic's agentic coding tool",
    },
    {
        "title": "BerriAI/litellm",
        "url": "https://github.com/BerriAI/litellm",
        "text": "Stars: 18000. Call 100+ LLMs using the OpenAI format — includes token tracking and cost management",
    },
    {
        "title": "microsoft/promptflow",
        "url": "https://github.com/microsoft/promptflow",
        "text": "Stars: 10000. Build and evaluate LLM apps with prompt flow — includes token budget tooling",
    },
    {
        "title": "simonw/llm",
        "url": "https://github.com/simonw/llm",
        "text": "Stars: 6000. Run LLMs from the command line with token usage logging",
    },
    {
        "title": "Aider AI coder",
        "url": "https://github.com/Aider-AI/aider",
        "text": "Stars: 25000. AI pair programming in your terminal — includes repo map for context optimization",
    },
]

ALL_CANDIDATES = EXISTING_CANDIDATES + SEEDED_CANDIDATES

SYSTEM_PROMPT = """You are a research assistant for Tenkai, a weekly AI/dev tools digest for senior engineers.

Given a topic and candidate items, select 4-6 items that BEST address the topic.

Quality bar:
- Real adoption: significant stars or engagement
- Actively maintained
- Directly addresses the stated topic (not just tangentially related)
- Engineers can use it today

Return ONLY a JSON array. Each item:
{
  "name": "project or tool name",
  "url": "canonical URL",
  "summary": "2-3 sentences: what it is, what problem it solves, why relevant to the topic"
}

No markdown fences."""


def fetch_github_readme(owner_repo: str) -> str:
    """Fetch first CONTENT_CHARS of a GitHub repo's README via API."""
    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN")
    headers = {**HEADERS}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.get(
            f"https://api.github.com/repos/{owner_repo}/readme",
            headers=headers,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        content = base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")
        # Strip markdown links/images, collapse whitespace
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
        content = re.sub(r'<[^>]+>', '', content)
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        return content[:CONTENT_CHARS]
    except Exception as e:
        return f"[README fetch failed: {e}]"


def fetch_page_content(url: str) -> str:
    """Fetch first CONTENT_CHARS of a web page, stripped of HTML."""
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        text = re.sub(r'<style[^>]*>.*?</style>', '', r.text, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:CONTENT_CHARS]
    except Exception as e:
        return f"[fetch failed: {e}]"


def enrich_with_content(candidates: list[dict]) -> list[dict]:
    """Add a 'content' field to each candidate by fetching its actual page."""
    enriched = []
    for c in candidates:
        url = c["url"]
        print(f"  Fetching: {url}", file=sys.stderr)
        gh_match = re.match(r'https://github\.com/([^/]+/[^/]+)/?$', url)
        if gh_match:
            content = fetch_github_readme(gh_match.group(1))
        else:
            content = fetch_page_content(url)
        enriched.append({**c, "content": content})
    return enriched


def build_metadata_prompt(candidates: list[dict]) -> str:
    lines = [f"TOPIC: {TOPIC}", f"DESCRIPTION: {TOPIC_DESC}", "", "CANDIDATES:"]
    for c in candidates:
        lines += [f"\nTitle: {c['title']}", f"URL: {c['url']}", f"Info: {c['text']}"]
    return "\n".join(lines)


def build_content_prompt(candidates: list[dict]) -> str:
    lines = [f"TOPIC: {TOPIC}", f"DESCRIPTION: {TOPIC_DESC}", "", "CANDIDATES:"]
    for c in candidates:
        lines += [
            f"\nTitle: {c['title']}",
            f"URL: {c['url']}",
            f"Info: {c['text']}",
            f"Content excerpt: {c.get('content', '')}",
        ]
    return "\n".join(lines)


def call_llm(prompt: str, label: str) -> list[dict] | None:
    api_key = os.environ["OPENROUTER_API_KEY"]
    preferred = "meta-llama/llama-3.3-70b-instruct:free"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/mcfredrick/tenkai",
        "X-Title": "Tenkai Research Test",
    }
    print(f"\n[{label}] Calling LLM...", file=sys.stderr)
    for model in build_candidate_list(preferred, api_key):
        print(f"  Trying: {model}", file=sys.stderr)
        try:
            r = httpx.post(
                OPENROUTER_API,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                headers=headers,
                timeout=120,
            )
            if r.status_code == 429:
                print(f"  Rate limited, trying next model", file=sys.stderr)
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  {model}: invalid JSON — {e}", file=sys.stderr)
        except Exception as e:
            print(f"  {model} error: {e}", file=sys.stderr)
    return None


def print_results(label: str, items: list[dict] | None) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if not items:
        print("  (no results)")
        return
    for i, item in enumerate(items, 1):
        print(f"\n{i}. {item.get('name')} — {item.get('url')}")
        print(f"   {item.get('summary', '')}")


def main() -> None:
    if "OPENROUTER_API_KEY" not in os.environ:
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print("=== METADATA-ONLY selection (current pipeline) ===", file=sys.stderr)
    metadata_prompt = build_metadata_prompt(ALL_CANDIDATES)
    metadata_results = call_llm(metadata_prompt, "METADATA ONLY")

    print("\n=== Fetching content for all candidates ===", file=sys.stderr)
    enriched = enrich_with_content(ALL_CANDIDATES)

    print("\n=== WITH CONTENT selection (proposed) ===", file=sys.stderr)
    content_prompt = build_content_prompt(enriched)
    content_results = call_llm(content_prompt, "WITH CONTENT")

    print_results("METADATA ONLY (current)", metadata_results)
    print_results("WITH CONTENT (proposed)", content_results)

    print(f"\n{'='*60}")
    print("  DIFF")
    print(f"{'='*60}")
    meta_urls = {i.get("url") for i in (metadata_results or [])}
    content_urls = {i.get("url") for i in (content_results or [])}
    for url in sorted(meta_urls - content_urls):
        print(f"  - dropped:  {url}")
    for url in sorted(content_urls - meta_urls):
        print(f"  + added:    {url}")
    for url in sorted(meta_urls & content_urls):
        print(f"    kept:     {url}")


if __name__ == "__main__":
    main()
