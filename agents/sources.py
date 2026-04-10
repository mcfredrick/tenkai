"""Source fetchers for the research agent. Each returns raw content or []."""

import re
import sys
from typing import Any

import feedparser
import httpx

HEADERS = {"User-Agent": "tenkai-bot/1.0 (github.com/mattdlong/tenkai)"}
TIMEOUT = 20

AI_KEYWORDS = re.compile(
    r"\b(llm|gpt|bert|transformer|diffusion|embedding|rag|vector|"
    r"langchain|llamaindex|ollama|hugging.?face|openai|anthropic|"
    r"pytorch|tensorflow|jax|triton|vllm|inference|fine.?tun|"
    r"tokeniz|neural|generative|foundation.model|ai|ml|nlp)\b",
    re.IGNORECASE,
)


def _get(url: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  fetch failed {url}: {e}", file=sys.stderr)
        return None


def _quality_score(repo: dict) -> float:
    """Compute a 0–1 quality score for a GitHub search result.

    Uses signals available in the search API response with no extra requests.
    Higher = more likely to be a quality, actively-maintained project.
    """
    from datetime import datetime, timezone

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


def huggingface_new_models() -> list[dict]:
    """Fetch trending HuggingFace models by likes."""
    r = _get(
        "https://huggingface.co/api/models",
        params={"sort": "likes7d", "direction": -1, "limit": 20},
    )
    if not r:
        return []

    results = []
    for model in r.json():
        model_id = model.get("id", "")
        url = f"https://huggingface.co/{model_id}"
        tags = " ".join(model.get("tags", []))
        results.append({"title": model_id, "url": url, "text": tags})
    return results


def papers_with_code() -> list[dict]:
    """Fetch recent LLM papers from Papers With Code."""
    r = _get(
        "https://paperswithcode.com/api/v1/papers/",
        params={"ordering": "-published", "q": "llm", "items_per_page": 20},
    )
    if not r:
        return []

    results = []
    for paper in r.json().get("results", []):
        results.append({
            "title": paper.get("title", ""),
            "url": paper.get("url_pdf") or paper.get("url_abs", ""),
            "text": paper.get("abstract", ""),
        })
    return results


def arxiv_feeds() -> list[dict]:
    """Fetch recent papers from ArXiv cs.AI, cs.LG, cs.CL."""
    results = []
    for category in ("cs.AI", "cs.LG", "cs.CL"):
        feed = feedparser.parse(f"https://arxiv.org/rss/{category}")
        for entry in feed.entries[:15]:
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "text": entry.get("summary", ""),
            })
    return results


def hacker_news() -> list[dict]:
    """Fetch high-scoring HN threads about AI/LLM."""
    r = _get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "tags": "story",
            "query": "AI LLM",
            "numericFilters": "points>50",
            "hitsPerPage": 20,
        },
    )
    if not r:
        return []

    results = []
    for hit in r.json().get("hits", []):
        results.append({
            "title": hit.get("title", ""),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "text": f"Points: {hit.get('points', 0)}, Comments: {hit.get('num_comments', 0)}",
        })
    return results


def pypi_updates() -> list[dict]:
    """Fetch recent PyPI package updates filtered by AI keywords."""
    feed = feedparser.parse("https://pypi.org/rss/updates.xml")
    results = []
    for entry in feed.entries[:50]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        if AI_KEYWORDS.search(title) or AI_KEYWORDS.search(summary):
            results.append({
                "title": title,
                "url": entry.get("link", ""),
                "text": summary,
            })
    return results


def _hn_search(query: str, min_points: int = 30, limit: int = 15) -> list[dict]:
    r = _get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "tags": "story",
            "query": query,
            "numericFilters": f"points>{min_points}",
            "hitsPerPage": limit,
        },
    )
    if not r:
        return []
    return [
        {
            "title": hit.get("title", ""),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "text": f"Points: {hit.get('points', 0)}, Comments: {hit.get('num_comments', 0)}",
        }
        for hit in r.json().get("hits", [])
    ]


def hacker_news_devtools() -> list[dict]:
    """Fetch HN threads about agentic coding assistants and AI dev tools."""
    return _hn_search("claude code cursor windsurf")


def hacker_news_mcp() -> list[dict]:
    """Fetch HN threads about MCP and the model context protocol ecosystem."""
    return _hn_search("MCP model context protocol")


def smithery_trending() -> list[dict]:
    """Fetch top MCP servers by install count. Capped at 10 to avoid flooding the post."""
    r = _get("https://registry.smithery.ai/servers", params={"pageSize": 50})
    if not r:
        return []

    results = []
    for server in r.json().get("servers", []):
        use_count = server.get("useCount", 0)
        if use_count < 500:
            continue
        name = server.get("displayName") or server.get("qualifiedName", "")
        url = server.get("homepage") or f"https://smithery.ai/server/{server.get('qualifiedName', '')}"
        results.append({
            "title": name,
            "url": url,
            "text": f"Installs: {use_count:,}. {server.get('description', '')}",
        })
    return results[:10]


def github_ai_tool_releases() -> list[dict]:
    """Fetch recent releases from key AI dev tool repos via GitHub Atom feeds."""
    repos = [
        "anthropics/claude-code",
        "block/goose",
        "modelcontextprotocol/servers",
        "continuedev/continue",
        "paul-gauthier/aider",
    ]
    results = []
    for repo in repos:
        feed = feedparser.parse(f"https://github.com/{repo}/releases.atom")
        for entry in feed.entries[:3]:
            results.append({
                "title": f"{repo}: {entry.get('title', '')}",
                "url": entry.get("link", ""),
                "text": entry.get("summary", "")[:400],
            })
    return results


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
