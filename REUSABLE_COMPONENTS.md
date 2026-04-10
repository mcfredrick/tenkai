# Reusable Components from Tenkai

## Executive Summary

Tenkai's core strengths fall into **three reusable patterns**:
1. **LLM Orchestration** — intelligent model selection, rate-limit recovery, structured output validation
2. **Semantic Search** — zero-dependency client-side search with pre-computed embeddings
3. **Research Pipelines** — deduplication, source aggregation, structured extraction

These can serve projects beyond autonomous blogs. A **modular library** (`tenkai-lib`) can bundle the LLM orchestration patterns; search and research infrastructure remain **template-driven** (copy into your project with customization).

---

## 1. LLM Orchestration (Extract → Library)

**What it does:** Handles OpenRouter free-tier model selection, rate limiting, retries, and fallbacks.

**Why it's valuable:** Free-tier models have per-minute rate limits and variable availability. The current logic eliminates manual retry loops and model-rotation logic from application code.

**Current implementation:** 
- `agents/model_selector.py` — dynamic model discovery & ranking
- `agents/writing_agent.py:call_llm()` — retry loop with validation, exponential backoff (30/60/120s), model rotation
- `agents/research_agent.py:call_llm()` — simpler retry loop (2^attempt * 5s backoff)

**Extraction plan:**

```
tenkai-lib/
├── tenkai_lib/
│   ├── __init__.py
│   ├── openrouter/
│   │   ├── models.py          # fetch_free_models(), pick_research_model(), pick_writing_model()
│   │   ├── llm.py             # LLMClient with retry/backoff/rotation
│   │   └── validators.py      # _has_sections(), _parse_json_response()
│   └── patterns/
│       └── structured_output.py # Validator protocol for model outputs
├── tests/
├── pyproject.toml
└── README.md
```

**API design:**

```python
from tenkai_lib.openrouter import LLMClient, ModelSelector

# Dynamic model selection (first time)
models = ModelSelector.fetch_free_models(api_key)
research_model = models.pick_research_model()
writing_model = models.pick_writing_model()

# LLM calls with intelligent retry
client = LLMClient(api_key=key, preferred_model=writing_model)

# With structured output validation
def validate_sections(text: str) -> bool:
    return bool(re.search(r'##.+\]\(https?://', text))

response = client.call(
    system_prompt="...",
    user_prompt="...",
    validators=[validate_sections],  # Reject if validation fails
    max_retries=3,  # Retries only on rate-limit or validation failure
    backoff_base=30,  # 30/60/120s
)
```

**Why a library works:**
- Stateless, pure functions (no blog-specific logic)
- Reusable across different LLM tasks (writing, research, QC, revision, etc.)
- Small surface area (just HTTP + retry logic)
- No breaking changes if OpenRouter API changes

**Scope for v1:**
- `ModelSelector` (fetch, rank, pick)
- `LLMClient` (call, rate-limit handling, backoff)
- Validator protocol (pluggable output validation)
- Documentation with examples (writing, research, QC loops)

**What stays in Tenkai:**
- Domain-specific prompts (system prompts are app-specific)
- Research source management (`sources.py`)
- Holiday-specific prompt tweaks
- Post front-matter generation

---

## 2. Semantic Search (Template-Driven)

**What it does:** Client-side semantic search using a shared embedding model across indexing and query time.

**Why it's valuable:** No backend required; search works without API calls; results are instant.

**Current implementation:**
- **Index builder:** `agents/build_index.py` — parses posts, embeds links with fastembed (BAAI/bge-small-en-v1.5)
- **Frontend:** `themes/tenkai/static/search.js` — loads transformers.js version of same model, client-side search
- **Hugo layout:** `themes/tenkai/layouts/_default/search.html` (not shown, assumed standard)

**Extraction plan:**

Create a template repo (`tenkai-search-template`) with:
```
tenkai-search-template/
├── build_index.py              # Customizable indexing script
├── _index.html                 # Drop-in Hugo layout template
├── search.js                   # Drop-in static asset
├── styles/search.css           # Drop-in styles
└── README.md
```

**Customization points:**
- **Parse function:** What constitutes an indexable item? (currently: bullet points in posts)
- **Embedding model:** Swap out for different BAAI variant or Xenova model (must match both sides)
- **Index JSON location:** `static/search-index.json` is expected; can be overridden
- **UI styling:** CSS variables for colors, layout flexibility

**Why a template works:**
- Embedding model is fixed per implementation (choosing a different model requires re-indexing + JS changes together)
- UI customization is per-project (CSS variables, text, layout)
- Easy to fork and adapt; avoids parameterization complexity

**Adoption path for other projects:**
1. Copy template
2. Customize `parse_links()` for your content format
3. Run `build_index.py` in your build pipeline
4. Drop `.html` and `.js` into theme
5. Done — no backend

---

## 3. Research Pipeline (Pattern + Template)

**What it does:** Fetch multiple sources, extract/categorize items with LLM, deduplicate over 60 days.

**Current implementation:**
- `agents/sources.py` — RSS/HTML scraping, source registry
- `agents/research_agent.py` — LLM extraction, deduplication, output structuring
- `agents/seen.json` — rolling 60-day URL window

**Extraction plan:**

This is **harder to generalize** because source handling is domain-specific. Instead of a library, create a **documented pattern**:

```
tenkai-research-template/
├── sources.py                  # Template: replace with your sources
├── research_agent.py           # Template: customize categories, system prompt
├── extraction_schema.json      # Example JSON schema for LLM output
└── README.md                   # Pattern docs: how to adapt
```

**Pattern documentation should cover:**
1. How to define sources (RSS, HTML parsing, API calls)
2. How to structure the LLM extraction prompt
3. How to implement deduplication (rolling window, exact URL match, or semantic)
4. How to categorize items in your domain
5. How to integrate with downstream steps (writing agent, aggregation, etc.)

**Why not a library:**
- Source handling is inherently app-specific
- Extraction categories vary by domain (AI blog: papers/releases/tools; cooking blog: recipes/techniques/equipment)
- Deduplication strategy depends on content (60 days for news; forever for recipes)
- Better as a well-documented template to clone + customize

---

## 4. Post Validation & QC (Minor Utility)

**What it does:** Validate post structure, run LLM-based QC, apply targeted fixes.

**Could go in `tenkai-lib`:**
- `validators.py` — structural checks (sections exist, links present, no dupes)
- `qc.py` — protocol for pluggable QC agents

**Current implementation:**
- `agents/validate_post.py` — regex-based structural checks
- `agents/writing_agent.py:run_qc()`, `run_revision()` — LLM QC loop

**Plan:**
- Extract structural validators into lib (reusable, no LLM calls)
- Leave QC/revision patterns in project code (domain-specific prompts, thresholds)

---

## Implementation Roadmap

### Phase 1: Extract LLM Orchestration (2-3 weeks, highest ROI)
**Goal:** Ship `tenkai-lib` v0.1 with core LLM client

**Deliverables:**
- [ ] Extract `ModelSelector` class with tests
- [ ] Extract `LLMClient` class with retry/backoff/validation
- [ ] Add docstrings and usage examples
- [ ] Publish to PyPI (or internal package index)
- [ ] Update Tenkai to use `tenkai-lib`
- [ ] Document in USAGE.md with real examples

**Benefits:**
- Instantly reusable in any Python project
- Eliminates boilerplate retry logic
- First new project can drop in `LLMClient`, save 500+ LoC

### Phase 2: Templatize Search (1 week, solid for any content site)
**Goal:** Ship `tenkai-search-template` — copy-paste semantic search

**Deliverables:**
- [ ] Extract search indexer into standalone script
- [ ] Extract search.js into reusable module
- [ ] Document embedding model choice and swapping options
- [ ] Add Hugo layout template example
- [ ] Create example integration for a non-blog project (e.g., docs site)

**Benefits:**
- Any static site (blog, docs, portfolio) can add semantic search
- No backend required
- Model is pinned per-project (no surprise upgrades)

### Phase 3: Document Research Pattern (1 week, for reference)
**Goal:** Create `tenkai-research-template` with adaptation guide

**Deliverables:**
- [ ] Extract `sources.py` as template with comments
- [ ] Extract `research_agent.py` as template with TODOs
- [ ] Write pattern doc: "How to build a research pipeline for your domain"
- [ ] Example adaptation for a different domain (e.g., security news)

**Benefits:**
- Clear roadmap for anyone wanting to build similar pipelines
- Reduces time to "working research agent" from scratch

### Phase 4: Polish & Cross-Project Integration (ongoing)
**Goal:** Use extracted components in real new projects

**Milestones:**
- First new autonomous blog uses `tenkai-lib` + custom research pipeline
- First content site adds semantic search via template
- Identify gaps, iterate on lib API

---

## Repository Structure

After extraction:

```
/Users/matt/Code/
├── todai/                          # Main blog (now uses tenkai-lib)
│   ├── agents/
│   ├── content/
│   └── CLAUDE.md
├── tenkai-lib/                     # NEW: Shared Python library
│   ├── tenkai_lib/
│   │   ├── openrouter/
│   │   ├── validators/
│   │   └── __init__.py
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
├── tenkai-search-template/         # NEW: Copy-paste search
│   ├── build_index.py
│   ├── search.js
│   ├── _default.search.html
│   └── README.md
└── tenkai-research-template/       # NEW: Research pattern
    ├── sources.py
    ├── research_agent.py
    ├── PATTERN.md
    └── README.md
```

---

## Quick Wins for Other Projects

| Project | Component | Time | Benefit |
|---------|-----------|------|---------|
| **New autonomous blog** | `tenkai-lib` + custom research template | 1 week | Reuses LLM logic, model selection |
| **Existing blog** | `tenkai-search-template` | 3 days | Add semantic search, 0 backend |
| **Documentation site** | `tenkai-search-template` | 3 days | Docs search, better than regex |
| **Podcast/video site** | `tenkai-lib` + custom extraction | 2 weeks | Auto-generate show notes with LLM |
| **Product feedback tool** | `tenkai-lib` + custom validators | 1 week | Route feedback via LLM classification |

---

## Design Principles (Keep These)

1. **No cloud lock-in** — OpenRouter free tier only, no Anthropic/OpenAI/Vertex dependencies
2. **Stateless functions** — LLMClient doesn't manage state; retries are transparent
3. **Pluggable validation** — Validators are user-provided callbacks; lib doesn't dictate output format
4. **Static search** — No backend, no database, works offline
5. **Copy-paste-able** — Templates should be self-contained; minimal dependencies

---

## Next Steps

1. **This week:** Review this plan, get buy-in on approach (lib + templates)
2. **Next week:** Kick off Phase 1 (extract LLMClient)
3. **Simultaneously:** Start planning first downstream project using the lib

Would you like me to start with Phase 1 (extracting `tenkai-lib`), or dive deeper into any section first?
