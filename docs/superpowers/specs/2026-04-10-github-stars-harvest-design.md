# GitHub Stars Harvest — Design Spec

**Date:** 2026-04-10
**Status:** Approved

## Summary

Harvest repos from the user's GitHub starred Lists and feed them into the existing curated pipeline alongside `watchlist.txt`. Starring a repo into a configured GitHub List is enough to nominate it for the blog — no manual URL copying needed.

## Goals

- Make it frictionless to nominate GitHub repos for blog posts (star into a list → done)
- Reuse existing curated pipeline: same LLM treatment, same dedup, same quality filtering
- No new pipeline stages, no new LLM calls

## Non-Goals

- Supporting non-GitHub URLs (that's what `watchlist.txt` is for)
- Harvesting all stars indiscriminately (list-based curation is intentional)
- Mutating the user's GitHub Lists (read-only)

## Architecture

### New files

- **`gh_lists.txt`** — config file at repo root, one GitHub List slug per line, `#` comments supported. Committed to the repo. Never mutated at runtime.

### Modified files

- **`agents/research_agent.py`** — add `load_gh_lists()`, `fetch_gh_lists()`, and merge into curated path
- **`.github/workflows/daily-post.yml`** — add `GH_PAT` env var to the research step
- **`agents/test_research_agent.py`** — add tests for new functions

### Auth

Classic PAT with `read:user` scope, stored as repo secret `GH_PAT`. The existing `GH_TOKEN` (`github.token`) is unchanged and continues to handle repo operations.

## Data Flow

1. `research_agent.py` startup calls `load_gh_lists()` → reads slugs from `gh_lists.txt`
2. `fetch_gh_lists(slugs, seen_urls)` POSTs a single GraphQL query to `api.github.com/graphql`
3. Response is filtered: keep only repos where `starredAt` is within the last 14 days
4. Filtered URLs are deduplicated against `seen_urls`
5. Surviving URLs are merged with `watchlist_urls` into `curated_items`
6. Combined curated list passed to LLM with `[CURATED - author hand-picked]` label — no prompt changes
7. Consumed URLs flow into `seen.json` as normal; `gh_lists.txt` is never modified

## Implementation Details

### `load_gh_lists(path) -> list[str]`

Reads `gh_lists.txt`, returns list of slug strings. Skips blank lines and lines starting with `#`. Returns `[]` if file is missing.

### `fetch_gh_lists(slugs, seen_urls) -> list[str]`

Builds a GraphQL query with one aliased field per slug:

```graphql
{ user(login: "mcfredrick") {
    genai: list(slug: "genai") { items(first: 100) { nodes { ... on Repository { url starredAt } } } }
    ai_coding: list(slug: "ai-coding") { items(first: 100) { nodes { ... on Repository { url starredAt } } } }
    ...
} }
```

- Uses `GH_PAT` from environment for Authorization header
- Filters repos where `starredAt` >= today minus 14 days
- Deduplicates against `seen_urls`
- Returns flat list of `github.com/owner/repo` URL strings
- On missing `GH_PAT`, API error, or exception: logs warning to stderr, returns `[]`

### Recency window

14 days, computed at runtime as `date.today() - timedelta(days=14)`. Not configurable for now (YAGNI).

### Configured lists (initial)

```
genai
ai-coding
video-genai
machine-learning
audio-ai-ml
rag-and-stuff
audioml
```

## Error Handling

All failures in `fetch_gh_lists()` are soft — log to stderr and return `[]`. The pipeline always continues with at least the watchlist. Hard failures are never introduced by this feature.

## Testing

Tests in `agents/test_research_agent.py`:

### Config parsing (`load_gh_lists`)
- Valid slugs are returned
- Blank lines and `#` comments are skipped
- Missing file returns `[]`

### Recency filtering (isolated logic)
- Repo starred 5 days ago → included
- Repo starred 20 days ago → excluded
- Repo starred exactly 14 days ago → included (boundary inclusive)

### `fetch_gh_lists` (mock `httpx.post`)
- URL already in `seen_urls` → dropped from results
- `GH_PAT` absent from env → returns `[]`, no exception raised
- API returns non-200 → returns `[]`, no exception raised
- `httpx` raises exception → returns `[]`, no exception raised
- Configured slugs appear in the GraphQL query payload sent to the API

## Operational Notes

- `GH_PAT` must be a classic PAT with `read:user` scope from the `mcfredrick` account
- If `GH_PAT` is absent the feature silently no-ops — the workflow does not fail
- `gh_lists.txt` can be edited directly on GitHub to add/remove lists without a code change
- A dedicated `tenkai` GitHub List can be created for repos that don't fit existing lists — just add its slug to `gh_lists.txt`
