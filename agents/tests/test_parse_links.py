"""Unit tests for parse_links in build_index."""
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
