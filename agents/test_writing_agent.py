"""Tests for writing_agent post-processing logic."""

from writing_agent import clean_post_body

# The broken body from 2026-03-19: Exa Search duplicated across 3 sections,
# Tutorials & Guides containing only "None."
BROKEN_BODY = """\
## Open Source Releases
**[unsloth](https://github.com/unslothai/unsloth)** — Fine-tuning framework for open-weight LLMs.

## AI Dev Tools
**[Exa Search](https://smithery.ai/servers/exa)** — Fast web search and crawling for AI agents.

## MCP Servers & Integrations
**[Exa Search](https://smithery.ai/servers/exa)** — Fast, intelligent web search and crawling capabilities for AI agents.

## Community Finds
**[Exa Search](https://smithery.ai/servers/exa)** — Fast, intelligent web search and crawling capabilities for AI agents.

## Tutorials & Guides
None.

## Today's Synthesis
Some synthesis paragraph here."""


def test_first_section_wins_for_duplicate_urls():
    result = clean_post_body(BROKEN_BODY)
    # Exa Search appears once (in AI Dev Tools, the first section it appeared in)
    assert result.count("smithery.ai/servers/exa") == 1
    assert "## AI Dev Tools" in result


def test_empty_sections_after_dedup_are_omitted():
    result = clean_post_body(BROKEN_BODY)
    assert "## MCP Servers & Integrations" not in result
    assert "## Community Finds" not in result


def test_none_literal_sections_are_omitted():
    result = clean_post_body(BROKEN_BODY)
    assert "## Tutorials & Guides" not in result
    assert "None." not in result


def test_sections_with_content_are_preserved():
    result = clean_post_body(BROKEN_BODY)
    assert "## Open Source Releases" in result
    assert "unsloth" in result
    assert "## Today's Synthesis" in result
    assert "Some synthesis paragraph here." in result
