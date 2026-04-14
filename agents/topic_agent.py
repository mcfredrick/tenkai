#!/usr/bin/env python3
"""Selects a weekly roundup topic from recent signals and optional watchlist.

Returns the best topic and writes runners-up back to roundup_topics.txt so
persistent pain points accumulate surface count across weeks.

Signal sources (in order of pain-point signal strength):
  - HN Ask HN: explicit questions and frustrations from engineers
  - Stack Overflow: trending questions tagged with AI/LLM keywords
  - Dev.to: trending practitioner posts on AI topics
  - GitHub Issues: high-comment open issues on popular AI repos
  - HN Stories: general news and releases
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from model_selector import build_candidate_list

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
TOPIC_FILE = Path("/tmp/roundup_topic.json")
TOPICS_FILE = Path(__file__).parent.parent / "roundup_topics.txt"
POSTS_DIR = Path(__file__).parent.parent / "content" / "posts"

HEADERS = {"User-Agent": "tenkai-bot/1.0 (github.com/mcfredrick/tenkai)"}
TIMEOUT = 20

SYSTEM_PROMPT = """You are an editor for Tenkai, a weekly AI/dev tools digest for senior engineers.

Your job: identify the 3-5 best roundup topics from this week's signals, ranked by how useful an article would be to the most engineers right now.

Prioritize topics where multiple signals point to a shared pain point — a problem many people hit. Pain-point signals (Ask HN, Stack Overflow, Dev.to, GitHub Issues) outweigh news signals (HN stories, releases).

Carried-forward topics have surfaced as strong candidates in previous weeks. Higher surface count means more durable engineer interest — these are more likely to produce a broadly useful article. Prefer them unless a clearly more urgent topic emerged this week.

Good topics: ecosystem-level tools, workflows, patterns engineers can use in their own work.
Examples: "Token optimization for coding agents", "Long-term memory for AI assistants",
"RAG pipelines in 2025", "Autonomous agents for code review", "MCP server ecosystem".

Bad topics: vague hype, company news, pure academic research, anything already covered recently.

Return ONLY valid JSON (no markdown fences):
{
  "selected": {
    "topic": "short topic name (5-8 words max)",
    "description": "one sentence: what this topic is and why engineers care",
    "rationale": "one sentence: why this is the best pick this week, referencing specific signals",
    "search_queries": ["query1", "query2", "query3"],
    "from_watchlist_index": null
  },
  "runners_up": [
    {
      "topic": "short topic name",
      "rationale": "one sentence: why this is worth tracking"
    }
  ]
}

selected.from_watchlist_index: 1-based index into the carried-forward list if you picked one, else null.
runners_up: 2-4 topics that were strong candidates but didn't make the cut this week."""


# --- Signal fetchers ---

_HN_STORY_QUERIES = [
    "LLM agent", "claude code", "MCP server",
    "AI tools", "coding assistant", "context window",
]

_HN_ASK_QUERIES = ["AI agent", "LLM", "claude", "coding assistant"]

_STACKOVERFLOW_TAGS = ["llm", "langchain", "openai-api", "anthropic", "llm-agent"]

_DEVTO_TAGS = ["ai", "llm", "claudeai", "machinelearning", "agents"]

_GITHUB_PAIN_REPOS = [
    "anthropics/claude-code",
    "openai/openai-python",
    "microsoft/autogen",
    "langchain-ai/langchain",
    "continuedev/continue",
    "block/goose",
    "cline/cline",
]


def _get(url: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  fetch failed {url}: {e}", file=sys.stderr)
        return None


def fetch_hn_stories() -> list[dict]:
    seen: set[str] = set()
    results = []
    for query in _HN_STORY_QUERIES:
        r = _get("https://hn.algolia.com/api/v1/search", params={
            "tags": "story", "query": query, "numericFilters": "points>20", "hitsPerPage": 8,
        })
        if not r:
            continue
        for hit in r.json().get("hits", []):
            title = hit.get("title", "")
            if title and title not in seen:
                seen.add(title)
                results.append({"source": "HN Story", "title": title,
                                 "points": hit.get("points", 0), "comments": hit.get("num_comments", 0)})
    return results


def fetch_hn_ask() -> list[dict]:
    seen: set[str] = set()
    results = []
    for query in _HN_ASK_QUERIES:
        r = _get("https://hn.algolia.com/api/v1/search", params={
            "tags": "ask_hn", "query": query, "numericFilters": "points>5", "hitsPerPage": 8,
        })
        if not r:
            continue
        for hit in r.json().get("hits", []):
            title = hit.get("title", "")
            if title and title not in seen:
                seen.add(title)
                results.append({"source": "HN Ask HN", "title": title,
                                 "points": hit.get("points", 0), "comments": hit.get("num_comments", 0)})
    return results


def fetch_stackoverflow_signals() -> list[dict]:
    seen: set[str] = set()
    results = []
    for tag in _STACKOVERFLOW_TAGS:
        r = _get("https://api.stackexchange.com/2.3/questions", params={
            "order": "desc", "sort": "votes", "tagged": tag,
            "site": "stackoverflow", "pagesize": 8,
        })
        if not r:
            continue
        for q in r.json().get("items", []):
            title = q.get("title", "")
            score = q.get("score", 0)
            if title and title not in seen and score > 2:
                seen.add(title)
                results.append({"source": f"Stack Overflow [{tag}]", "title": title,
                                 "points": score, "comments": q.get("answer_count", 0)})
    return results


def fetch_devto_signals() -> list[dict]:
    seen: set[str] = set()
    results = []
    for tag in _DEVTO_TAGS:
        r = _get("https://dev.to/api/articles", params={"tag": tag, "top": 7, "per_page": 8})
        if not r:
            continue
        for article in r.json():
            title = article.get("title", "")
            reactions = article.get("positive_reactions_count", 0)
            if title and title not in seen and reactions > 5:
                seen.add(title)
                results.append({"source": f"Dev.to [{tag}]", "title": title,
                                 "points": reactions, "comments": article.get("comments_count", 0)})
    return results


def fetch_github_issue_signals() -> list[dict]:
    gh_headers = {**HEADERS}
    token = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN")
    if token:
        gh_headers["Authorization"] = f"Bearer {token}"

    results = []
    for repo in _GITHUB_PAIN_REPOS:
        try:
            r = httpx.get("https://api.github.com/search/issues", params={
                "q": f"repo:{repo} is:issue is:open comments:>3",
                "sort": "reactions", "order": "desc", "per_page": 5,
            }, headers=gh_headers, timeout=TIMEOUT)
            r.raise_for_status()
            for issue in r.json().get("items", []):
                title = issue.get("title", "")
                if title:
                    results.append({"source": f"GitHub Issue ({repo})", "title": title,
                                     "points": issue.get("reactions", {}).get("total_count", 0),
                                     "comments": issue.get("comments", 0)})
        except Exception as e:
            print(f"  GitHub issues failed for {repo}: {e}", file=sys.stderr)
    return results


# --- Watchlist (structured) ---

@dataclass
class WatchlistEntry:
    topic: str
    first_surfaced: str = ""
    times_surfaced: int = 1
    original_line: str = ""  # for preserving manual entries


def load_watchlist() -> list[WatchlistEntry]:
    if not TOPICS_FILE.exists():
        return []
    entries = []
    for line in TOPICS_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) == 3:
            entries.append(WatchlistEntry(
                topic=parts[0],
                first_surfaced=parts[1],
                times_surfaced=int(parts[2]) if parts[2].isdigit() else 1,
                original_line=stripped,
            ))
        else:
            # Manual entry — no date/count fields
            entries.append(WatchlistEntry(topic=stripped, first_surfaced="", times_surfaced=1, original_line=stripped))
    return entries


def save_watchlist(entries: list[WatchlistEntry]) -> None:
    """Rewrite roundup_topics.txt preserving comment lines, replacing data lines."""
    today = str(date.today())
    comment_lines = []
    if TOPICS_FILE.exists():
        for line in TOPICS_FILE.read_text().splitlines():
            if line.strip().startswith("#") or not line.strip():
                comment_lines.append(line)

    data_lines = []
    for e in entries:
        first = e.first_surfaced or today
        data_lines.append(f"{e.topic} | {first} | {e.times_surfaced}")

    content = "\n".join(comment_lines)
    if data_lines:
        content += ("\n" if comment_lines else "") + "\n".join(data_lines)
    TOPICS_FILE.write_text(content + "\n")


# --- LLM ---

def call_llm(content: str, preferred_model: str) -> dict | None:
    api_key = os.environ["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/mcfredrick/tenkai",
        "X-Title": "Tenkai Topic Agent",
    }
    for candidate in build_candidate_list(preferred_model, api_key):
        print(f"  Trying: {candidate}", file=sys.stderr)
        try:
            r = httpx.post(OPENROUTER_API, json={
                "model": candidate,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.5,
                "max_tokens": 800,
            }, headers=headers, timeout=60)
            if r.status_code == 429:
                print("  Rate limited, skipping", file=sys.stderr)
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


def build_prompt(signals: list[dict], watchlist: list[WatchlistEntry], recent_titles: list[str]) -> str:
    lines = []

    if watchlist:
        lines.append("CARRIED-FORWARD CANDIDATES (from previous weeks — higher surface count = more durable pain point):")
        for i, e in enumerate(watchlist, 1):
            age = f", first seen {e.first_surfaced}" if e.first_surfaced else ""
            lines.append(f"  {i}. {e.topic}  [surfaced {e.times_surfaced}x{age}]")
        lines.append("")

    if recent_titles:
        lines.append("RECENT ROUNDUP TOPICS (avoid repeating):")
        for t in recent_titles:
            lines.append(f"  - {t}")
        lines.append("")

    pain = [s for s in signals if not s["source"].startswith("HN Story")]
    news = [s for s in signals if s["source"].startswith("HN Story")]

    if pain:
        lines.append("PAIN-POINT SIGNALS — questions, issues, frustrations (weight heavily):")
        for s in sorted(pain, key=lambda x: x["points"], reverse=True)[:35]:
            lines.append(f"  [{s['source']}] [{s['points']}pts/{s['comments']}cmts] {s['title']}")
        lines.append("")

    if news:
        lines.append("NEWS SIGNALS — stories and releases (context only):")
        for s in sorted(news, key=lambda x: x["points"], reverse=True)[:20]:
            lines.append(f"  [{s['points']}pts/{s['comments']}cmts] {s['title']}")

    return "\n".join(lines)


def fetch_recent_roundup_titles() -> list[str]:
    titles = []
    for path in sorted(POSTS_DIR.glob("*-roundup.md"), reverse=True)[:8]:
        m = re.search(r'^title:\s*"(.+)"', path.read_text(), re.MULTILINE)
        if m:
            titles.append(m.group(1))
    return titles


def main() -> None:
    model = os.environ.get("WRITING_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    print(f"Topic model: {model}", file=sys.stderr)

    all_signals: list[dict] = []

    for label, fetcher in [
        ("HN stories", fetch_hn_stories),
        ("HN Ask HN", fetch_hn_ask),
        ("Stack Overflow", fetch_stackoverflow_signals),
        ("Dev.to", fetch_devto_signals),
        ("GitHub issues", fetch_github_issue_signals),
    ]:
        print(f"Fetching {label}...", file=sys.stderr)
        results = fetcher()
        all_signals.extend(results)
        print(f"  {len(results)} signals", file=sys.stderr)

    print(f"Total signals: {len(all_signals)}", file=sys.stderr)

    watchlist = load_watchlist()
    if watchlist:
        print(f"Loaded {len(watchlist)} carried-forward candidates", file=sys.stderr)
        for e in watchlist:
            print(f"  [{e.times_surfaced}x] {e.topic}", file=sys.stderr)

    recent_titles = fetch_recent_roundup_titles()

    prompt = build_prompt(all_signals, watchlist, recent_titles)
    result = call_llm(prompt, model)

    if not result or "selected" not in result:
        raise RuntimeError("Topic agent failed to produce a topic")

    selected = result["selected"]
    runners_up = result.get("runners_up", [])

    print(f"Selected topic: {selected.get('topic')}", file=sys.stderr)
    print(f"Rationale: {selected.get('rationale')}", file=sys.stderr)
    if runners_up:
        print(f"Runners-up: {', '.join(r['topic'] for r in runners_up)}", file=sys.stderr)

    # Remove selected from watchlist if it came from there
    watchlist_idx = selected.get("from_watchlist_index")
    if watchlist_idx:
        idx = int(watchlist_idx) - 1
        if 0 <= idx < len(watchlist):
            print(f"  Consumed watchlist entry: {watchlist[idx].topic}", file=sys.stderr)
            watchlist.pop(idx)

    # Update watchlist: increment surface count for existing runners-up, add new ones
    today = str(date.today())
    existing = {e.topic.lower(): e for e in watchlist}
    for runner in runners_up:
        topic_lower = runner["topic"].lower()
        if topic_lower in existing:
            existing[topic_lower].times_surfaced += 1
            print(f"  Incremented: {existing[topic_lower].topic} ({existing[topic_lower].times_surfaced}x)", file=sys.stderr)
        else:
            watchlist.append(WatchlistEntry(
                topic=runner["topic"],
                first_surfaced=today,
                times_surfaced=1,
            ))
            print(f"  Added new candidate: {runner['topic']}", file=sys.stderr)

    save_watchlist(watchlist)

    # Write selected topic for downstream agents
    TOPIC_FILE.write_text(json.dumps(selected, indent=2))
    print(f"Wrote {TOPIC_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
