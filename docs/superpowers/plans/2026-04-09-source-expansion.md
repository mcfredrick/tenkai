# Source Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the research pipeline to surface niche community AI tools and the full agentic coding assistant ecosystem.

**Architecture:** Two changes to `agents/sources.py` — replace the Python/TS language-filtered trending scraper with an all-languages scraper filtered by `AI_KEYWORDS`, and add a new `github_search_tools()` fetcher that queries the GitHub search API with 4 targeted queries and a composite quality score pre-filter. A new `agents/test_sources.py` harness enables local parameter tuning before deployment.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup4, GitHub search API (unauthenticated), HN Algolia API. No new dependencies.

---

### Task 1: Fix `github_trending` — all-languages with AI_KEYWORDS filter

**Files:**
- Modify: `agents/sources.py`

- [ ] **Step 1: Replace `_scrape_github_trending` and `github_trending`**

Open `agents/sources.py`. Delete lines 32–58 (the `_scrape_github_trending` helper and `github_trending` function) and replace with:

```python
def github_trending() -> list[dict]:
    """Scrape all-languages GitHub trending repos, pre-filtered by AI keywords."""
    from bs4 import BeautifulSoup

    r = _get("https://github.com/trending?since=daily")
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for article in soup.select("article.Box-row"):
        try:
            name_tag = article.select_one("h2 a")
            if not name_tag:
                continue
            repo_path = name_tag["href"].lstrip("/")
            url = f"https://github.com/{repo_path}"
            desc_tag = article.select_one("p")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""
            if not AI_KEYWORDS.search(repo_path) and not AI_KEYWORDS.search(desc):
                continue
            results.append({"title": repo_path, "url": url, "text": desc})
        except Exception:
            continue
    return results
```

- [ ] **Step 2: Verify it runs without error**

```bash
cd /Users/matt/Code/todai
python -c "from agents.sources import github_trending; items = github_trending(); print(f'{len(items)} items'); [print(f'  {i[\"title\"]}') for i in items]"
```

Expected: prints 0–25 items with AI-relevant repo names (or 0 if today's trending has no AI repos — that's fine). No exceptions.

- [ ] **Step 3: Commit**

```bash
git add agents/sources.py
git commit -m "feat: expand github_trending to all languages with AI_KEYWORDS pre-filter"
```

---

### Task 2: Add `_quality_score` helper and unit tests

**Files:**
- Modify: `agents/sources.py`
- Create: `agents/tests/test_quality_score.py`

- [ ] **Step 1: Write the failing test**

Create `agents/tests/__init__.py` (empty) and `agents/tests/test_quality_score.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta

# We'll import after implementing
# from sources import _quality_score


def make_repo(stars=50, forks=5, days_old=10, pushed_days_ago=3,
              description="An AI coding tool", topics=["llm"], license_name="MIT"):
    now = datetime.now(timezone.utc)
    return {
        "stargazers_count": stars,
        "forks_count": forks,
        "created_at": (now - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pushed_at": (now - timedelta(days=pushed_days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": description,
        "topics": topics,
        "license": {"name": license_name} if license_name else None,
    }


def test_high_velocity_repo_scores_above_threshold():
    from sources import _quality_score
    repo = make_repo(stars=100, forks=15, days_old=5)
    assert _quality_score(repo) >= 0.4


def test_stale_no_description_repo_scores_below_threshold():
    from sources import _quality_score
    repo = make_repo(stars=5, forks=0, days_old=300, pushed_days_ago=200,
                     description="", topics=[], license_name=None)
    assert _quality_score(repo) < 0.4


def test_score_is_between_0_and_1():
    from sources import _quality_score
    repo = make_repo(stars=10000, forks=5000, days_old=1)
    assert 0.0 <= _quality_score(repo) <= 1.0


def test_score_increases_with_more_signals():
    from sources import _quality_score
    bare = make_repo(stars=20, forks=0, days_old=30, pushed_days_ago=20,
                     description="", topics=[], license_name=None)
    rich = make_repo(stars=20, forks=5, days_old=30, pushed_days_ago=5,
                     description="AI tool", topics=["llm"], license_name="MIT")
    assert _quality_score(rich) > _quality_score(bare)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/matt/Code/todai
python -m pytest agents/tests/test_quality_score.py -v 2>&1 | head -20
```

Expected: ImportError on `from sources import _quality_score` — function doesn't exist yet.

- [ ] **Step 3: Implement `_quality_score` in `sources.py`**

Add after the `_get` function (after line 29 in the original file, now after the updated `github_trending`):

```python
def _quality_score(repo: dict) -> float:
    """Compute a 0–1 quality score for a GitHub search result.

    Uses signals available in the search API response with no extra requests.
    Higher = more likely to be a quality, actively-maintained project.
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)

    created_at = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
    pushed_at = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
    age_days = max((now - created_at).days, 1)
    pushed_days_ago = (now - pushed_at).days

    score = 0.0

    # Star velocity (up to 0.30)
    velocity = stars / age_days
    if velocity >= 10:
        score += 0.30
    elif velocity >= 5:
        score += 0.20
    elif velocity >= 1:
        score += 0.10

    # Fork ratio (up to 0.20)
    if stars > 0:
        ratio = forks / stars
        if ratio >= 0.15:
            score += 0.20
        elif ratio >= 0.05:
            score += 0.10

    # Pushed recently (0.15)
    if pushed_days_ago <= 14:
        score += 0.15

    # Has description (0.10)
    if repo.get("description"):
        score += 0.10

    # Has topics (0.10)
    if repo.get("topics"):
        score += 0.10

    # Has license (0.05)
    if repo.get("license"):
        score += 0.05

    # Minimum star threshold — at least some real users (0.10)
    if stars >= 20:
        score += 0.10

    return min(score, 1.0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/matt/Code/todai
python -m pytest agents/tests/test_quality_score.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/sources.py agents/tests/__init__.py agents/tests/test_quality_score.py
git commit -m "feat: add _quality_score helper with unit tests"
```

---

### Task 3: Add `github_search_tools()` source

**Files:**
- Modify: `agents/sources.py`

- [ ] **Step 1: Add `github_search_tools` function**

Add after `_quality_score` in `agents/sources.py`:

```python
def github_search_tools(since_days: int = 30, score_threshold: float = 0.4) -> list[dict]:
    """Search GitHub for early-trending AI coding tools and community projects.

    Runs 4 targeted queries against the GitHub search API (unauthenticated).
    Pre-filters by composite quality score before returning to keep LLM payload lean.
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    since_date = (now - timedelta(days=since_days)).strftime("%Y-%m-%d")
    since_14d = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    queries = [
        f"topic:claude-code OR topic:mcp-server OR topic:llm-agent pushed:>{since_date}",
        f"stars:10..500 created:>{since_date} claude OR llm OR mcp OR \"ai agent\" OR \"coding assistant\" in:name,description",
        "opencode OR nanoclaw OR openclaw OR \"codex cli\" OR \"pi editor\" OR \"coding assistant\" in:name stars:5..500",
        f"\"coding assistant\" OR \"agentic coding\" in:description stars:20..1000 pushed:>{since_14d}",
    ]

    seen_urls: set[str] = set()
    results = []

    for query in queries:
        r = _get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 30},
        )
        if not r:
            continue

        for repo in r.json().get("items", []):
            url = repo.get("html_url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            if _quality_score(repo) < score_threshold:
                continue

            desc = repo.get("description") or ""
            topics = " ".join(repo.get("topics", []))
            results.append({
                "title": repo.get("full_name", ""),
                "url": url,
                "text": f"Stars: {repo['stargazers_count']}, Forks: {repo['forks_count']}. {desc}. Topics: {topics}",
            })

    return results
```

- [ ] **Step 2: Register in `ALL_SOURCES`**

In `ALL_SOURCES` at the bottom of `sources.py`, add `github_search_tools` after `github_trending`:

```python
ALL_SOURCES: dict[str, Any] = {
    "github_trending": github_trending,
    "github_search": github_search_tools,
    "huggingface_releases": huggingface_new_models,
    "papers": papers_with_code,
    "arxiv": arxiv_feeds,
    "hn_threads": hacker_news,
    "hn_devtools": hacker_news_devtools,
    "hn_mcp": hacker_news_mcp,
    "smithery_mcp": smithery_trending,
    "github_tool_releases": github_ai_tool_releases,
    "pypi_updates": pypi_updates,
}
```

- [ ] **Step 3: Smoke test**

```bash
cd /Users/matt/Code/todai
python -c "
from agents.sources import github_search_tools
items = github_search_tools(since_days=30, score_threshold=0.4)
print(f'{len(items)} items passed quality filter')
for i in items[:5]:
    print(f'  {i[\"title\"]} — {i[\"url\"]}')
"
```

Expected: 0–30 items, no exceptions. Rate limit note: if you see a 403 or 429, wait 60s and retry.

- [ ] **Step 4: Commit**

```bash
git add agents/sources.py
git commit -m "feat: add github_search_tools source with quality score pre-filter"
```

---

### Task 4: Expand HN devtools query

**Files:**
- Modify: `agents/sources.py`

- [ ] **Step 1: Update the query string in `hacker_news_devtools`**

Change line 176 from:
```python
    return _hn_search("claude code cursor windsurf")
```
to:
```python
    return _hn_search("claude code cursor windsurf opencode codex pi nanoclaw openclaw aider goose")
```

Also update the docstring:
```python
def hacker_news_devtools() -> list[dict]:
    """Fetch HN threads about agentic coding assistants and AI dev tools."""
    return _hn_search("claude code cursor windsurf opencode codex pi nanoclaw openclaw aider goose")
```

- [ ] **Step 2: Verify it returns results**

```bash
cd /Users/matt/Code/todai
python -c "
from agents.sources import hacker_news_devtools
items = hacker_news_devtools()
print(f'{len(items)} items')
for i in items[:5]:
    print(f'  {i[\"title\"]}')
"
```

Expected: 0–15 items, no exceptions.

- [ ] **Step 3: Commit**

```bash
git add agents/sources.py
git commit -m "feat: expand HN devtools query to cover full agentic coding ecosystem"
```

---

### Task 5: Write `test_sources.py` local harness

**Files:**
- Create: `agents/test_sources.py`

- [ ] **Step 1: Create the test harness**

```python
#!/usr/bin/env python3
"""Local test harness for research sources. Enables parameter tuning before deployment.

Usage:
    python agents/test_sources.py                          # run all sources
    python agents/test_sources.py --source github_search   # single source
    python agents/test_sources.py --since 2026-03-01       # historical window
    python agents/test_sources.py --score-threshold 0.3    # tune quality cutoff
    python agents/test_sources.py --find JuliusBrussee/caveman  # check a specific repo
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources import ALL_SOURCES, github_search_tools

# Repos to explicitly check for in github_search results (validation targets)
VALIDATION_TARGETS = [
    "JuliusBrussee/caveman",
    "drona23/claude-token-efficient",
]


def run_source(name: str, fetcher, since_days: int, score_threshold: float) -> list[dict]:
    if name == "github_search":
        return github_search_tools(since_days=since_days, score_threshold=score_threshold)
    return fetcher()


def print_source_results(name: str, items: list[dict], find: str | None) -> None:
    print(f"\n{'=' * 60}")
    print(f"SOURCE: {name}  ({len(items)} items)")
    print("=" * 60)
    for item in items[:10]:
        title = item.get("title", "")
        url = item.get("url", "")
        text = item.get("text", "")[:120]
        marker = " *** MATCH ***" if find and find.lower() in (title + url).lower() else ""
        print(f"  {title}{marker}")
        print(f"    {url}")
        if text:
            print(f"    {text}")


def check_validation_targets(all_results: dict[str, list[dict]]) -> None:
    print(f"\n{'=' * 60}")
    print("VALIDATION TARGETS")
    print("=" * 60)
    for target in VALIDATION_TARGETS:
        found_in = []
        for source_name, items in all_results.items():
            for item in items:
                if target.lower() in (item.get("title", "") + item.get("url", "")).lower():
                    found_in.append(source_name)
                    break
        status = "FOUND in: " + ", ".join(found_in) if found_in else "NOT FOUND"
        print(f"  {target}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test research sources locally")
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Recency window start date (default: 30 days ago)",
    )
    parser.add_argument(
        "--source",
        help=f"Run a single source. Options: {', '.join(list(ALL_SOURCES) + ['github_search'])}",
    )
    parser.add_argument(
        "--score-threshold", type=float, default=0.4, metavar="N",
        help="Quality score cutoff for github_search (0.0–1.0, default: 0.4)",
    )
    parser.add_argument(
        "--find", metavar="TERM",
        help="Highlight results containing this term (e.g. JuliusBrussee/caveman)",
    )
    args = parser.parse_args()

    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        since_days = max((datetime.now(timezone.utc) - since_dt).days, 1)
    else:
        since_days = 30

    print(f"Settings: since_days={since_days}, score_threshold={args.score_threshold}")

    sources_to_run: dict = {}
    if args.source:
        if args.source == "github_search":
            sources_to_run = {"github_search": None}
        elif args.source in ALL_SOURCES:
            sources_to_run = {args.source: ALL_SOURCES[args.source]}
        else:
            valid = ", ".join(list(ALL_SOURCES) + ["github_search"])
            print(f"Unknown source '{args.source}'. Valid: {valid}", file=sys.stderr)
            sys.exit(1)
    else:
        sources_to_run = dict(ALL_SOURCES)
        sources_to_run["github_search"] = None

    all_results: dict[str, list[dict]] = {}
    for name, fetcher in sources_to_run.items():
        try:
            items = run_source(name, fetcher, since_days, args.score_threshold)
            all_results[name] = items
            print_source_results(name, items, args.find)
        except Exception as e:
            print(f"\nERROR in {name}: {e}", file=sys.stderr)
            all_results[name] = []

    if not args.source:
        check_validation_targets(all_results)

    print(f"\n{'=' * 60}")
    total = sum(len(v) for v in all_results.values())
    print(f"TOTAL: {total} items across {len(all_results)} sources")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs**

```bash
cd /Users/matt/Code/todai
python agents/test_sources.py --source github_search --score-threshold 0.4
```

Expected: prints items from `github_search`, no exceptions.

- [ ] **Step 3: Commit**

```bash
git add agents/test_sources.py
git commit -m "feat: add test_sources.py local harness for parameter tuning"
```

---

### Task 6: Local tuning — validate targets surface and tune threshold

**No files changed in this task — this is a tuning/observation session.**

- [ ] **Step 1: Check if validation targets surface with 30-day window**

```bash
cd /Users/matt/Code/todai
python agents/test_sources.py --source github_search --since 2026-03-10 --find caveman
python agents/test_sources.py --source github_search --since 2026-03-10 --find claude-token-efficient
```

Expected: at least one of the validation targets appears. If neither appears, proceed to Step 2.

- [ ] **Step 2: If targets not found, lower threshold and widen window**

```bash
python agents/test_sources.py --source github_search --since 2026-03-01 --score-threshold 0.2 --find caveman
```

Note the lowest threshold at which the target appears without flooding results with noise. If the target doesn't appear at any threshold, it means it doesn't match our query set — note this and move on (the GitHub search queries are best-effort, not exhaustive).

- [ ] **Step 3: Run full suite and check overall quality**

```bash
python agents/test_sources.py --since 2026-03-10
```

Read through the `github_search` section results. Check for obvious noise (non-AI repos, unrelated projects). If noise is significant, note the threshold needed to reduce it. Adjust `score_threshold` default in `github_search_tools()` signature in `sources.py` if needed.

- [ ] **Step 4: Run trending check**

```bash
python agents/test_sources.py --source github_trending
```

Verify the all-languages trending returns AI-relevant repos and has filtered out non-AI repos.

- [ ] **Step 5: If threshold adjustment needed, update default in `sources.py` and commit**

If tuning reveals the default 0.4 is too high or too low, update the default in `sources.py`:

```python
def github_search_tools(since_days: int = 30, score_threshold: float = <TUNED_VALUE>) -> list[dict]:
```

```bash
git add agents/sources.py
git commit -m "chore: tune github_search score_threshold to <TUNED_VALUE> based on local testing"
```

If 0.4 is fine, skip this step.

---

### Task 7: Expand `github_ai_tool_releases` based on testing findings

**Files:**
- Modify: `agents/sources.py`

- [ ] **Step 1: Check which candidate repos have active release Atom feeds**

```bash
cd /Users/matt/Code/todai
python -c "
import feedparser

candidates = [
    'sst/opencode',
    'coder/opencode',
    'opencode-ai/opencode',
    'sigoden/aichat',
    'plandex-ai/plandex',
    'cline/cline',
    'RooVetGit/Roo-Code',
]
for repo in candidates:
    feed = feedparser.parse(f'https://github.com/{repo}/releases.atom')
    count = len(feed.entries)
    latest = feed.entries[0].get('title', 'n/a') if feed.entries else 'no entries'
    print(f'{repo}: {count} releases, latest: {latest}')
"
```

Expected: output showing which repos have active release feeds (>0 entries with real titles).

- [ ] **Step 2: Add repos with active feeds to `github_ai_tool_releases`**

In `agents/sources.py`, update the `repos` list in `github_ai_tool_releases` to include the repos confirmed active in Step 1. For example, if `sst/opencode` and `plandex-ai/plandex` both have feeds:

```python
def github_ai_tool_releases() -> list[dict]:
    """Fetch recent releases from key AI dev tool repos via GitHub Atom feeds."""
    repos = [
        "anthropics/claude-code",
        "block/goose",
        "modelcontextprotocol/servers",
        "continuedev/continue",
        "paul-gauthier/aider",
        # Added: broader agentic coding ecosystem
        "sst/opencode",          # add only if confirmed active in Step 1
        "plandex-ai/plandex",    # add only if confirmed active in Step 1
        "cline/cline",           # add only if confirmed active in Step 1
    ]
```

Only add repos that returned >0 entries in Step 1. Do not add repos with empty feeds.

- [ ] **Step 3: Verify**

```bash
cd /Users/matt/Code/todai
python -c "
from agents.sources import github_ai_tool_releases
items = github_ai_tool_releases()
print(f'{len(items)} release items')
for i in items:
    print(f'  {i[\"title\"]}')
"
```

Expected: more items than before (was 15 max with 5 repos × 3 entries each).

- [ ] **Step 4: Commit**

```bash
git add agents/sources.py
git commit -m "feat: expand github_ai_tool_releases with additional ecosystem repos"
```

---

### Task 8: Final integration check

**No files changed — validation only.**

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/matt/Code/todai
python -m pytest agents/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run full source harness**

```bash
python agents/test_sources.py
```

Read the VALIDATION TARGETS section at the bottom. Check overall item counts per source are reasonable (not 0 everywhere, not 200+ in one source).

- [ ] **Step 3: Verify `ALL_SOURCES` is complete**

```bash
python -c "
from agents.sources import ALL_SOURCES
print('Sources registered:')
for name in ALL_SOURCES:
    print(f'  {name}')
"
```

Expected output includes: `github_trending`, `github_search`, `huggingface_releases`, `papers`, `arxiv`, `hn_threads`, `hn_devtools`, `hn_mcp`, `smithery_mcp`, `github_tool_releases`, `pypi_updates`.

- [ ] **Step 4: Final commit if any loose changes**

```bash
git status
# If clean, nothing to do. If any changes remain:
git add -p
git commit -m "chore: final cleanup after source expansion"
```
