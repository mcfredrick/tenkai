# Link-Level Search Design

**Date:** 2026-04-09
**Status:** Approved

## Problem

The current search surfaces blog posts that may contain relevant links. Users want to find the specific links themselves — not hunt through a daily digest to find what they're looking for.

## Goal

Replace post-level search results with individual link results. Searching "GPU memory" returns the specific `dynabatch` link with its description, not the April 8 post that happened to mention it.

## Architecture

Three files change; no new dependencies.

| File | Change |
|---|---|
| `agents/build_index.py` | Emit one index entry per link instead of per post |
| `themes/tenkai/static/search.js` | Render link cards instead of post cards |
| `static/search-index.json` | Regenerated automatically (not hand-edited) |
| `agents/tests/test_parse_links.py` | New: unit tests for the parsing function |

## Data Layer: `build_index.py`

### Parsing strategy

Anchor on bullet lines (lines starting with `- `) that contain a markdown link. This is robust to:
- Section name variation (`## Open Source Releases`, `## AI Dev Tools`, etc.)
- Bold-wrapped links: `**[Title](URL)**`
- Trailing emojis in descriptions
- LLM-generated format drift

The "Today's Synthesis" section contains inline cross-reference links in prose — these are skipped automatically because they don't appear on bullet lines.

### Per-bullet extraction

For each bullet line containing a markdown link:
1. Extract the first `[text](url)` match (strip optional `**...**` wrapping)
2. Extract description: text after ` — ` on the same line, stripped of trailing whitespace/emojis
3. If no ` — ` separator is present, use an empty description (don't skip the link)
4. Emit: `{title, url, description, date}`

### Embedding

Embed `"title. description"` per link — focused signal, no noise from unrelated bullets in the same post.

### Index entry shape

```json
{
  "title": "dynabatch 0.1.9",
  "url": "https://pypi.org/project/dynabatch/0.1.9/",
  "description": "A PyTorch DataLoader extension that predicts GPU memory usage to dynamically adjust batch sizes.",
  "date": "2026-04-08",
  "embedding": [0.01234, ...]
}
```

Dropped fields vs. current: `body`, `snippet`, `tags`, `raw`, post `url`. The `url` field now points to the external resource, not a post.

### Index size

~7× more entries than today (6–8 links per post). Each entry is much smaller (no `body` field). Net JSON size is comparable to the current index.

## Search Logic: `search.js`

The `search()` function is **unchanged** — same model, same dot-product cosine similarity, same top-10 results.

`renderResults` is updated to render link cards:

```
[Title ↗]                     (external link, opens in new tab)
Description text from post
2026-04-08
```

All links use `target="_blank" rel="noopener noreferrer"`.

No tags, no snippet field, no post-internal navigation.

## Unit Tests: `agents/tests/test_parse_links.py`

Tests for `parse_links(body: str, date: str) -> list[dict]`:

| Case | What it verifies |
|---|---|
| Plain link with description | Basic happy path |
| Bold-wrapped link `**[T](U)**` | Strips `**` correctly |
| Trailing emoji in description | Description cleaned up |
| Multiple sections | All bullets captured, not just first section |
| Synthesis section with inline links | Not included (prose, not bullet line) |
| Bullet with no ` — ` separator | Returns entry with empty description, not skipped |
| Non-link bullet line | Skipped cleanly |

Tests use inline post text strings — no file I/O, no mocks.

## Out of Scope

- Keeping a "posts" search mode alongside links (fully replaced)
- Section labels on result cards (fragile, dropped)
- Any changes to the embedding model or similarity algorithm
