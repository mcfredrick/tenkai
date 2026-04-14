# Weekly Roundup Feature Plan

**Target**: Monday-only themed deep-dive posts alongside the daily digest.

## Concept

A 3-step pipeline that produces a "This Week in AI: {Topic}" post every Monday:

1. **Topic agent** — picks a hot, specific topic from recent signals
2. **Roundup research agent** — finds 4-6 tools/techniques/projects that address it
3. **Roundup writing agent** — writes a cohesive editorial post (not a news digest)

## Pipeline Design

### Step 1: `agents/topic_agent.py`

- **Input**: same raw sources as `research_agent.py` (HN, Reddit, GitHub trending) + recent Tenkai post titles (to avoid repeating last week's topic)
- **LLM prompt**: "Given these recent AI/dev discussions, pick one specific, actionable topic that engineers are actively talking about this week. Return JSON: `{topic, description, rationale, search_queries[]}`"
- **Output**: `/tmp/roundup_topic.json`
- **Validation**: topic must be specific (not "LLMs are cool") and have suggested search queries

### Step 2: `agents/roundup_agent.py`

- **Input**: `roundup_topic.json`
- Uses the `search_queries` to fetch targeted results (GitHub search, HN, blogs)
- LLM extracts 4-6 items: each with `{name, url, what_it_does, why_relevant}`
- **Output**: `/tmp/roundup_research.json`
- Same URL deduplication against `seen.json` (roundup items go into seen.json too)

### Step 3: `agents/roundup_writer.py`

- **Input**: `roundup_topic.json` + `roundup_research.json`
- **Output format** (different from daily digest):
  ```markdown
  ---
  title: "This Week in AI: {topic}"
  date: YYYY-MM-DD
  draft: false
  tags: [weekly-roundup, ...]
  description: "..."
  ---

  Opening paragraph: what the topic is, why it's live right now (2-4 sentences).

  ## {item name}
  2-4 sentences. What it is, concrete example of how you'd use it, honest take.

  ## {item name}
  ...

  ## The Takeaway
  Synthesis paragraph tying items together — what does this week's crop say about where things are heading?
  ```
- Each item gets its own `##` header (unlike daily's flat bullet list)
- 2-4 sentences per item (more depth than daily 1-2 sentence bullets)
- Validation: must have ≥4 items, must have opening + takeaway sections

## Content Structure

**New Hugo section**: `content/weekly/YYYY-MM-DD.md`  
Rationale: keeps roundups separate from daily digests in the list view; can have its own layout later.

The daily post still runs on Mondays. The roundup is *additive*.

## Workflow

New file: `.github/workflows/weekly-roundup.yml`

```
cron: '0 9 * * 1'   # 09:00 UTC Mondays (1hr after daily)
workflow_dispatch (for testing)
```

Steps mirror `daily-post.yml`:
1. Guard: skip if `content/weekly/$(date +%Y-%m-%d).md` already exists
2. Select models (reuse `model_selector.py`)
3. Run `topic_agent.py`
4. Run `roundup_agent.py`
5. Run `roundup_writer.py`
6. Validate with new `validate_roundup.py`
7. Commit + push
8. Trigger rebuild-index (reuses existing workflow)

## Open Questions

1. **Monday vs. other day?** Monday works well (captures weekend discussion). Friday is an alternative (end-of-week recap). Either is trivial to change in the cron.

2. **Topic seeding**: Should there be a `roundup_watchlist.txt` file (like `watchlist.txt`) where you can seed topic ideas? Or fully autonomous?

3. **Seen.json integration**: Roundup items should be added to `seen.json` so the daily digest doesn't re-surface them that week. Agree?

4. **Content path**: `content/weekly/` requires a Hugo content section config. Alternatively, `content/posts/YYYY-MM-DD-roundup.md` reuses the existing section with no Hugo changes. Simpler to start.

## Testing Plan

All three agents can be run locally end-to-end:

```bash
OPENROUTER_API_KEY=... python agents/topic_agent.py
# inspect /tmp/roundup_topic.json

OPENROUTER_API_KEY=... python agents/roundup_agent.py
# inspect /tmp/roundup_research.json

OPENROUTER_API_KEY=... python agents/roundup_writer.py
# inspect content/weekly/YYYY-MM-DD.md (or content/posts/)
```

The workflow `workflow_dispatch` also lets us trigger a one-off run from GitHub Actions UI.

## Implementation Sequence

1. `topic_agent.py` — simplest, just LLM + JSON output
2. `roundup_agent.py` — adapts research_agent patterns for targeted search
3. `roundup_writer.py` — new system prompt, different post format
4. `validate_roundup.py` — validates ≥4 items, opening para, takeaway section
5. `weekly-roundup.yml` — wires it together
6. Hugo content section (if using `content/weekly/`)
