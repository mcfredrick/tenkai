# Link-Level Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace post-level search with link-level search so each result is a specific external link with its description, not a daily digest post.

**Architecture:** Rewrite `build_index.py` to emit one index entry per bullet-list link instead of one per post; update `search.js` to render link cards. The embedding model, similarity algorithm, and search UI scaffolding are unchanged.

**Tech Stack:** Python 3.12+, fastembed (BAAI/bge-small-en-v1.5), pytest, vanilla JS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `agents/build_index.py` | Modify | Parse links from posts; build link-level index |
| `agents/tests/test_parse_links.py` | Create | Unit tests for `parse_links` |
| `agents/tests/__init__.py` | Create | Make tests a package (empty) |
| `themes/tenkai/static/search.js` | Modify | Render link cards instead of post cards |
| `static/search-index.json` | Regenerate | Rebuilt by running `build_index.py` |

---

### Task 1: Write failing tests for `parse_links`

**Files:**
- Create: `agents/tests/__init__.py`
- Create: `agents/tests/test_parse_links.py`

- [ ] **Step 1: Create the empty `__init__.py`**

```bash
touch agents/tests/__init__.py
```

- [ ] **Step 2: Write the test file**

Create `agents/tests/test_parse_links.py`:

```python
"""Unit tests for parse_links in build_index."""
import pytest
from build_index import parse_links

PLAIN = """
## Open Source Releases
- [Claude Code v2.1.97](https://github.com/anthropics/claude-code/releases/tag/v2.1.97) — Introduces a focus view toggle useful for reducing visual noise.
"""

BOLD = """
## Open Source Releases
- **[dynabatch 0.1.9](https://pypi.org/project/dynabatch/0.1.9/)** — A PyTorch DataLoader extension that predicts GPU memory usage. 🛠️
"""

MULTI_SECTION = """
## Open Source Releases
- [link-a](https://example.com/a) — Description A.

## AI Dev Tools
- [link-b](https://example.com/b) — Description B.
"""

SYNTHESIS = """
## Open Source Releases
- [link-a](https://example.com/a) — Description A.

## Today's Synthesis

Check out [link-a](https://example.com/a) which does great things.
"""

NO_SEPARATOR = """
## Open Source Releases
- [link-no-sep](https://example.com/x)
"""

NON_LINK_BULLET = """
## Open Source Releases
- Just a plain text bullet with no link.
- [real-link](https://example.com/) — Has description.
"""


def test_plain_link():
    links = parse_links(PLAIN, "2026-04-09")
    assert len(links) == 1
    assert links[0]["title"] == "Claude Code v2.1.97"
    assert links[0]["url"] == "https://github.com/anthropics/claude-code/releases/tag/v2.1.97"
    assert "focus view toggle" in links[0]["description"]
    assert links[0]["date"] == "2026-04-09"


def test_bold_wrapped_link():
    links = parse_links(BOLD, "2026-04-08")
    assert len(links) == 1
    assert links[0]["title"] == "dynabatch 0.1.9"
    assert links[0]["url"] == "https://pypi.org/project/dynabatch/0.1.9/"
    assert "PyTorch" in links[0]["description"]


def test_multiple_sections_all_captured():
    links = parse_links(MULTI_SECTION, "2026-03-24")
    assert len(links) == 2
    titles = [l["title"] for l in links]
    assert "link-a" in titles
    assert "link-b" in titles


def test_synthesis_prose_links_excluded():
    links = parse_links(SYNTHESIS, "2026-03-24")
    assert len(links) == 1
    assert links[0]["title"] == "link-a"


def test_no_separator_yields_empty_description():
    links = parse_links(NO_SEPARATOR, "2026-03-24")
    assert len(links) == 1
    assert links[0]["description"] == ""


def test_non_link_bullet_skipped():
    links = parse_links(NON_LINK_BULLET, "2026-03-24")
    assert len(links) == 1
    assert links[0]["title"] == "real-link"
```

- [ ] **Step 3: Run tests to confirm they fail (function doesn't exist yet)**

```bash
uv run pytest agents/tests/test_parse_links.py
```

Expected: `ImportError` or `AttributeError: module 'build_index' has no attribute 'parse_links'`

---

### Task 2: Implement `parse_links` and rewrite `build_index.py`

**Files:**
- Modify: `agents/build_index.py`

- [ ] **Step 1: Rewrite `agents/build_index.py`**

```python
"""Build semantic search index from all posts.

Outputs static/search-index.json — served by the static site for client-side
semantic search and loadable by Python agents for RAG retrieval.

Model: BAAI/bge-small-en-v1.5 (384-dim, ONNX via fastembed)
Browser counterpart: Xenova/bge-small-en-v1.5 (same weights, same vector space)
"""
import json
import re
from pathlib import Path

from fastembed import TextEmbedding

POSTS_DIR = Path("content/posts")
INDEX_PATH = Path("static/search-index.json")
MODEL = "BAAI/bge-small-en-v1.5"

# Matches [Title](url) with optional **bold** wrapping
_LINK_RE = re.compile(r'\*{0,2}\[([^\]]+)\]\(([^)]+)\)\*{0,2}')


def parse_links(body: str, date: str) -> list[dict]:
    """Extract one entry per bullet-list link from a post body."""
    results = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        m = _LINK_RE.search(stripped)
        if not m:
            continue
        title = m.group(1)
        url = m.group(2)
        after = stripped[m.end():]
        description = after.split(" — ", 1)[1].strip() if " — " in after else ""
        results.append({"title": title, "url": url, "description": description, "date": date})
    return results


def _parse_post(path: Path) -> tuple[str, str] | None:
    """Return (body, date) for a post, or None if unparseable."""
    text = path.read_text()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    front, body = parts[1], parts[2].strip()
    m = re.search(r"^date:\s*(.+?)\s*$", front, re.MULTILINE)
    return (body, m.group(1)) if m else None


def main():
    links = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        result = _parse_post(path)
        if not result:
            continue
        body, date = result
        links.extend(parse_links(body, date))

    print(f"Indexing {len(links)} links with {MODEL}...")

    model = TextEmbedding(MODEL)
    texts = [f"{link['title']}. {link['description']}" for link in links]
    embeddings = list(model.embed(texts))

    index = [
        {
            "title": link["title"],
            "url": link["url"],
            "description": link["description"],
            "date": link["date"],
            # Round to 5 decimal places — negligible quality loss, ~40% smaller JSON
            "embedding": [round(float(x), 5) for x in emb],
        }
        for link, emb in zip(links, embeddings)
    ]

    INDEX_PATH.write_text(json.dumps(index, separators=(",", ":")))
    size_kb = INDEX_PATH.stat().st_size // 1024
    print(f"Wrote {INDEX_PATH} ({size_kb} KB, {len(index)} links)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the tests to confirm they pass**

```bash
uv run pytest agents/tests/test_parse_links.py
```

Expected: all 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add agents/build_index.py agents/tests/__init__.py agents/tests/test_parse_links.py
git commit -m "feat: index individual links instead of whole posts"
```

---

### Task 3: Regenerate the search index

**Files:**
- Regenerate: `static/search-index.json`

- [ ] **Step 1: Run the index builder**

```bash
uv run --extra index python agents/build_index.py
```

Expected output (numbers will vary):
```
Indexing 312 links with BAAI/bge-small-en-v1.5...
Wrote static/search-index.json (1842 KB, 312 links)
```

If the model needs to download (~65 MB, cached after first run), it will do so automatically.

- [ ] **Step 2: Verify the index shape**

```bash
uv run python -c "
import json
idx = json.loads(open('static/search-index.json').read())
print(f'{len(idx)} entries')
print('Keys:', list(idx[0].keys()))
print('First entry:', {k: v for k, v in idx[0].items() if k != 'embedding'})
"
```

Expected:
```
312 entries
Keys: ['title', 'url', 'description', 'date', 'embedding']
First entry: {'title': '...', 'url': 'https://...', 'description': '...', 'date': '2026-...'}
```

The `url` value must be an external URL (e.g. `https://github.com/...`), not a `/posts/...` path.

- [ ] **Step 3: Commit the regenerated index**

```bash
git add static/search-index.json
git commit -m "chore: regenerate search index with link-level entries"
```

---

### Task 4: Update `search.js` to render link cards

**Files:**
- Modify: `themes/tenkai/static/search.js`

- [ ] **Step 1: Replace `renderResults` in `search.js`**

Find and replace the entire `renderResults` function (lines 53–76 in the current file):

```javascript
function renderResults(results, container) {
  if (!results.length) {
    container.innerHTML = '<p class="search-empty">No results found.</p>';
    return;
  }
  container.innerHTML = results
    .map(
      (r) => `
    <article class="search-result">
      <h3><a href="${r.url}" target="_blank" rel="noopener noreferrer">${r.title} ↗</a></h3>
      <div class="search-meta">
        <span class="search-date">${r.date}</span>
      </div>
      ${r.description ? `<p class="search-snippet">${r.description}</p>` : ""}
    </article>`
    )
    .join("");
}
```

- [ ] **Step 2: Commit**

```bash
git add themes/tenkai/static/search.js
git commit -m "feat: render link cards in search results"
```

---

### Task 5: Test locally

- [ ] **Step 1: Build and serve the site**

```bash
hugo serve
```

- [ ] **Step 2: Open search in browser**

Navigate to `http://localhost:1313/search/?q=GPU+memory`

Expected: results are individual links (e.g. "dynabatch 0.1.9") with descriptions, each opening in a new tab when clicked. No post cards.

- [ ] **Step 3: Try a few more queries to confirm relevance**

- `http://localhost:1313/search/?q=vector+database` — should surface memory/RAG-related links
- `http://localhost:1313/search/?q=code+generation` — should surface coding assistant links
- `http://localhost:1313/search/?q=kubernetes` — if no matching links, should show "No results found"
