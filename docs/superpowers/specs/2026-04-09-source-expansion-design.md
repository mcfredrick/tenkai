# Source Expansion Design

**Date:** 2026-04-09
**Status:** Approved

## Problem

The current research pipeline misses niche community projects (e.g. `JuliusBrussee/caveman`, `drona23/claude-token-efficient`) and the broader agentic coding ecosystem (opencode, codex, pi, openclaw, nanoclaw). Root causes:

1. `github_trending` only scrapes Python and TypeScript — projects in JS, Go, Rust etc. are invisible
2. GitHub trending requires mass daily star appeal — small community tools never surface
3. `hacker_news_devtools` searches only `"claude code cursor windsurf"` — misses most of the ecosystem
4. `github_ai_tool_releases` tracks only 5 hardcoded repos

## Goals

- Surface niche but quality community tools early, before they trend broadly
- Cover the full agentic coding assistant ecosystem (pi, opencode, codex, openclaw, nanoclaw, etc.)
- Keep LLM API payload similar to today — pre-filter aggressively before handing to LLM
- Test locally before deploying; support historical date-range testing

## Non-Goals

- Reddit integration (scraping is not feasible)
- Adding paid API access (GitHub unauthenticated 60 req/hr is sufficient)
- Changing the LLM prompt, writing agent, or validation pipeline

---

## Changes to `agents/sources.py`

### 1. Drop language filter from `github_trending`

**Before:** Scrapes `https://github.com/trending/python` and `https://github.com/trending/typescript`
**After:** Scrapes `https://github.com/trending` (all languages, top 25 repos daily)

Pre-filter results by `AI_KEYWORDS` on the repo description before returning — the same keyword filter already used by `pypi_updates`. This keeps LLM payload lean while allowing any language.

Rationale: the language filter was noise-reduction; `AI_KEYWORDS` does that job better and language-agnostically.

### 2. New `github_search_tools()` source

Uses the GitHub search API (unauthenticated, no token required) to discover community tools that are early-trending or niche-but-notable. Runs 4 searches per daily pipeline invocation — well within the 60 req/hr unauthenticated limit.

**Query suite:**

| Query | Intent |
|-------|--------|
| `topic:claude-code OR topic:mcp-server OR topic:llm-agent pushed:>DATE` | Topic-tagged tools — authors who tag intentionally want to be found |
| `stars:10..500 created:>DATE` + AI keyword in name/description | Velocity candidates — recent repos gaining real traction |
| `opencode OR nanoclaw OR openclaw OR "codex cli" OR "pi" OR "coding assistant" in:name stars:5..500` | Named ecosystem tools — explicit coverage of known alternatives |
| `"coding assistant" OR "agentic coding" in:description stars:20..1000 pushed:>14d` | Emerging assistants — broader net with freshness gate |

**Date window:** 30 days rolling. `seen.json` deduplication handles re-surfacing across runs, so a wider window doesn't cause repeat items in posts.

**Pre-filter composite quality score** (computed from fields returned by search API, no extra requests):

| Signal | Weight | Source field |
|--------|--------|-------------|
| Star velocity (stars / days since created) | High | `stargazers_count`, `created_at` |
| Fork ratio (forks / stars > 0.1) | Medium | `forks_count` |
| Has non-empty description | Low | `description` |
| Has topics | Low | `topics[]` |
| Has license | Low | `license` |
| Pushed within 14 days | Medium | `pushed_at` |

Only items above a configurable score threshold are passed to the LLM. Default threshold chosen during local testing.

### 3. Expand `hacker_news_devtools` query

**Before:** `"claude code cursor windsurf"`
**After:** `"claude code cursor windsurf opencode codex pi nanoclaw openclaw aider goose"`

HN Algolia treats multi-term strings as OR matches across tokens, so this requires no structural change — just a wider query string.

### 4. Expand `github_ai_tool_releases` repo list

Add release feed tracking for key community repos once confirmed to have active Atom feeds. Candidates to evaluate during testing:
- `opencode-ai/opencode` (or equivalent)
- `cli/cli` is not relevant, but community CLI tools in the space
- Others surfaced during local testing

Exact additions determined after local testing confirms feed availability.

---

## New `agents/test_sources.py` — Local Test Harness

A standalone script for local development and parameter tuning. Does not require a running pipeline.

**CLI interface:**
```
python agents/test_sources.py [--since YYYY-MM-DD] [--source NAME] [--score-threshold N] [--dry-run]
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--since` | 30 days ago | Controls recency window for GitHub search queries |
| `--source` | all | Run a single named source in isolation |
| `--score-threshold` | 0.4 | Quality cutoff for GitHub search pre-filter (0.0–1.0) |
| `--dry-run` | false | Show pre-filtered items without calling LLM |

**Output per source:**
- Items fetched (raw)
- Items after pre-filter (what would go to LLM)
- Sample items (title, URL, score) for eyeball quality check

**Historical testing:** GitHub search API and HN Algolia both support date range filtering, so `--since` enables genuine historical verification. GitHub trending has no historical data — only current results are testable.

**Target validation during local testing:**
- Confirm `JuliusBrussee/caveman` would be returned for an appropriate `--since` date
- Confirm `drona23/claude-token-efficient` would be returned
- Confirm pi, opencode, and other named tools surface from query #3
- Tune `--score-threshold` to minimize noise while keeping these candidates

---

## Pre-filter Strategy Summary

| Source | Pre-filter method |
|--------|------------------|
| `github_trending` | `AI_KEYWORDS` regex on description (existing pattern) |
| `github_search_tools` | Composite quality score threshold |
| `hacker_news_devtools` | Points threshold (existing: `>30`) |
| All others | Unchanged |

LLM sees at most 30 items per source (existing cap in `build_prompt_for_source`). Pre-filtering ensures GitHub search adds quality candidates without bloating the payload.

---

## Files Changed

| File | Change |
|------|--------|
| `agents/sources.py` | Drop language filter; add `github_search_tools()`; expand HN query; expand release repo list |
| `agents/test_sources.py` | New file — local test harness |

No changes to: `research_agent.py`, `writing_agent.py`, `validate_post.py`, `model_selector.py`, GHA workflows.
