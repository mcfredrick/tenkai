# Phase 4: Integrate Tenkai-lib into Todai

Once tenkai-lib is published to PyPI, we'll refactor Tenkai to use it. **No rewriting — only replacing boilerplate with library calls.**

## Goals

1. Reduce code duplication (model selection, retry logic, validators)
2. Make agents simpler and more testable
3. Keep all behavior identical (no behavior changes)
4. Prepare for Phase 2 (search lib) and Phase 3 (research skill)

## What Will Change

### 1. Model Selection (agents/model_selector.py)

**Before:**
```python
# ~100 lines of code
def fetch_free_models() -> list[dict]: ...
def pick_research_model() -> str: ...
def pick_writing_model() -> str: ...
def parse_param_count() -> int: ...
```

**After:**
```python
from tenkai_lib.openrouter import ModelSelector

selector = ModelSelector(api_key=os.environ["OPENROUTER_API_KEY"])
research_model = selector.pick_research_model(selector.fetch_free_models())
writing_model = selector.pick_writing_model(selector.fetch_free_models())
```

**What we delete:** `agents/model_selector.py` (or replace with single wrapper)

### 2. Writing Agent (agents/writing_agent.py)

**Before:**
```python
# ~700 lines
# - call_llm() with manual retry loop (lines 100-150)
# - _try_model() with rate-limit handling
# - Validators (has_sections) embedded
# - Model rotation logic
```

**After:**
```python
from tenkai_lib.openrouter import (
    LLMClient,
    has_markdown_sections_with_links,
)

model = os.environ.get("WRITING_MODEL", "...")
client = LLMClient(api_key=os.environ["OPENROUTER_API_KEY"], preferred_model=model)

# Replace entire call_llm() call with:
bullets_body = client.call(
    system_prompt=SYSTEM_PROMPT,
    user_prompt=writing_prompt,
    validators=[has_markdown_sections_with_links],
    max_retries_preferred=3,
    backoff_base=30,
)
```

**What we delete:** 
- `call_llm()` function (~50 lines)
- `_try_model()` function (~30 lines)
- `_has_sections()` function (~5 lines)
- Manual model rotation logic

**What we keep:**
- `SYSTEM_PROMPT` (domain-specific)
- Prompt building logic (`build_writing_prompt()`, `build_synthesis_prompt()`)
- Post structure logic (`clean_post_body()`, `extract_tags()`)
- QC/revision loops (can use lib too, but more custom)

### 3. Research Agent (agents/research_agent.py)

**Before:**
```python
# ~250 lines
# - call_llm() with manual retry loop
# - Model fetching
# - JSON parsing and validation
```

**After:**
```python
from tenkai_lib.openrouter import LLMClient, is_valid_json, parse_json_from_text

model = os.environ.get("RESEARCH_MODEL", "...")
client = LLMClient(api_key=os.environ["OPENROUTER_API_KEY"], preferred_model=model)

# Replace call_llm() with:
response = client.call(
    system_prompt=SYSTEM_PROMPT,
    user_prompt=content,
    validators=[is_valid_json],
)

items = parse_json_from_text(response)
```

**What we delete:**
- `call_llm()` function (~40 lines)
- Manual retry logic
- Manual JSON extraction

**What we keep:**
- `SYSTEM_PROMPT` (domain-specific extraction rules)
- Source fetching (`ALL_SOURCES`)
- Item categorization and deduplication logic

### 4. Validators (agents/validate_post.py)

**Opportunity for Phase 3:**
Extract structural checks into lib:

```python
# Before: embedded in validate_post.py
if not _has_sections_with_links(body):
    errors.append("No ## sections with linked items")

# After: import from lib
from tenkai_lib.openrouter.validators import has_markdown_sections_with_links

if not has_markdown_sections_with_links(body):
    errors.append("No ## sections with linked items")
```

**What we keep:**
- Domain-specific checks (minimum item count, synthesis present, no dupes)
- Post structure validation (front matter parsing)

## Refactoring Order

1. **Update imports** — Add `tenkai-lib` to `pyproject.toml`
2. **Replace model selection** — Use `ModelSelector` in workflow
3. **Replace writing agent LLM calls** — Use `LLMClient`, keep domain logic
4. **Replace research agent LLM calls** — Use `LLMClient` + validators
5. **Update validators** — Use library validators where applicable
6. **Update tests** — Mock `LLMClient` instead of `httpx.post`
7. **Run workflow end-to-end** — Verify behavior unchanged

## No Behavior Changes

The refactoring is **purely mechanical:**
- Same prompts → same responses
- Same retry strategy → same reliability
- Same model selection → same performance
- Same validators → same quality checks

If it breaks anything, it's a bug in tenkai-lib (unlikely since we tested it heavily).

## PR Strategy

**One PR per agent:**

1. **PR 1: Model selection** (small, easy to review)
   - Add `tenkai-lib` to dependencies
   - Replace model selection
   - Update tests

2. **PR 2: Writing agent** (medium)
   - Replace LLM calls with `LLMClient`
   - Keep all domain logic
   - Update tests to mock `LLMClient.call()`

3. **PR 3: Research agent** (medium)
   - Replace LLM calls + JSON parsing
   - Keep source handling + categorization
   - Update tests

4. **PR 4: Post validation** (small)
   - Use lib validators where applicable
   - Keep domain-specific checks

## Testing Approach

**Unit tests:** Mock `LLMClient` at call site

```python
def test_writing_produces_post():
    with patch("tenkai_lib.openrouter.LLMClient") as mock_client:
        mock_instance = Mock()
        mock_instance.call.return_value = """## Model Releases
- **[Foo](https://...)**"""
        mock_client.return_value = mock_instance
        
        # Run writing_agent.main()
        
        assert post_exists()
```

**Integration tests:** Optional, if we want to test against real OpenRouter

```python
def test_writing_agent_with_real_llm():
    """Slow test, only run in CI with rate-limit warnings."""
    # Uses real LLMClient, real models
    # Verifies end-to-end behavior
```

## Migration Risk

**Low risk:**
- Library is battle-tested (51 tests)
- Behavior is identical to current code
- Changes are localized (one agent at a time)
- Can roll back easily (git revert)

**Contingency:**
If something breaks:
1. Revert the PR
2. Open issue in tenkai-lib
3. Fix in tenkai-lib, test locally
4. Retry with patched version

## Timeline

- **Tenkai-lib published:** Now
- **Phase 4 refactoring:** 1-2 weeks (4 PRs)
  - Each PR: 1-2 days development + review
  - Conservative testing to ensure safety
- **Phase 4 complete:** Todai uses tenkai-lib end-to-end

## Post-Phase-4 Benefits

Once integrated, we unlock:

1. **Phase 2 (Search)** — Can use `SemanticIndex` in build pipeline
2. **Phase 3 (Research Skill)** — New research agents inherit retry logic
3. **Code clarity** — Agents focus on domain logic, lib handles LLM mechanics
4. **Testing speed** — Mocking at library level is cleaner
5. **Reusability** — Tenkai code patterns can be copied to other projects

## Checklist

Before starting Phase 4:

- [ ] tenkai-lib published to PyPI
- [ ] GitHub repo created (`github.com/mcfredrick/tenkai-lib`)
- [ ] `tenkai-lib` tested in isolation with real API key
- [ ] Phase 4 plan reviewed and approved

## Questions?

See:
- `/Users/matt/Code/tenkai-lib/CLAUDE.md` — How to use the library
- `/Users/matt/Code/tenkai-lib/ARCHITECTURE.md` — Design decisions
- `/Users/matt/Code/tenkai-lib/ECOSYSTEM.md` — How search/research fit in
