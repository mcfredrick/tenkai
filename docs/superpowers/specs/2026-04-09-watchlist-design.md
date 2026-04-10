# Watchlist Design

**Date:** 2026-04-09
**Status:** Approved

## Overview

A simple mechanism for the author to surface URLs found organically into upcoming blog posts. URLs are added to a plain-text file, processed as high-priority sources by the research agent, and automatically removed once published.

## Data Format

`watchlist.txt` at the repo root. One URL per line. Blank lines and lines starting with `#` are ignored.

```
# Added 2026-04-09
https://example.com/cool-paper
https://github.com/someone/cool-tool
```

- No expiry — items persist until consumed or manually removed
- File absence is treated as an empty watchlist (graceful skip)

## Pipeline Integration

### research_agent.py changes

Two new functions:

- `load_watchlist(seen_urls: set[str]) -> list[str]` — reads `watchlist.txt`, removes URLs already in `seen_urls`, rewrites the file in-place with duplicates removed, returns the remaining URLs
- `save_watchlist(remaining: list[str])` — rewrites `watchlist.txt` preserving comment lines and blank lines, keeping only URLs in `remaining`

In `main()`:

1. After `load_seen_urls()`, call `load_watchlist(seen_urls)` to get curated URLs and strip already-seen ones from the file
2. Fetch each curated URL using the existing `_get()` helper; skip silently on fetch failure
3. Build a prompt block for curated items, labeled `[CURATED - author hand-picked]`, and prepend it to the source processing order
4. After all sources are processed and `results` is finalized, collect all output URLs across all sources and call `save_watchlist()` removing any that appear in the output

### System prompt addition

One sentence appended to the existing research system prompt:

> Items marked [CURATED - author hand-picked] were personally selected by the author — treat them as high-priority and include at least one per post if they meet the minimum quality bar.

### Prompt block format

```
[CURATED - author hand-picked]

URL: https://...
Text: <fetched page text, truncated to 400 chars>

URL: https://...
Text: <fetched page text, truncated to 400 chars>
```

## Workflow Change

In `.github/workflows/daily-post.yml`, the commit step adds `watchlist.txt`:

```yaml
git add "$POST" agents/seen.json watchlist.txt
```

This is a no-op if `watchlist.txt` hasn't changed or doesn't exist.

## Deduplication Invariants

| Scenario | Outcome |
|---|---|
| URL in watchlist already in `seen.json` | Removed from `watchlist.txt` at startup, never fetched |
| URL in watchlist makes it into the post | Removed from `watchlist.txt` after LLM processing; added to `seen.json` by existing logic |
| URL in watchlist filtered out by LLM | Stays in `watchlist.txt`, retried next run |
| URL fetch fails | Skipped silently, stays in `watchlist.txt` |

## Future: Mac/iPhone Quick-Add

The file format (plain text, one URL per line, committed to git) is intentionally compatible with simple automation:

- **Mac**: a Shortcut that runs `echo "<url>" >> watchlist.txt && git commit && git push` via SSH or Working Copy
- **iPhone**: a Shortcut using Working Copy's git actions to append and commit
- **Share Sheet**: a system share extension that appends the URL and pushes

No changes to the file format are needed to support these — the plain-text append pattern works as-is.

## Files Changed

| File | Change |
|---|---|
| `watchlist.txt` | New file (created by author, managed by pipeline) |
| `agents/research_agent.py` | Add `load_watchlist()`, `save_watchlist()`, integrate into `main()`, update system prompt |
| `.github/workflows/daily-post.yml` | Add `watchlist.txt` to commit step |
