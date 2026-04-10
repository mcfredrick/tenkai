"""Build semantic search index from all posts.

Outputs static/search-index.json — served by the static site for client-side
semantic search and loadable by Python agents for RAG retrieval.

Model: BAAI/bge-small-en-v1.5 (384-dim, ONNX via fastembed)
Browser counterpart: Xenova/bge-small-en-v1.5 (same weights, same vector space)
"""
import json
import re
from pathlib import Path

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
    from fastembed import TextEmbedding

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
