"""Tests for research_agent categorization logic."""

import json
from pathlib import Path

import pytest
from research_agent import load_watchlist, recategorize, save_watchlist


def item(title, url, summary, category="release"):
    return {"title": title, "url": url, "summary": summary, "category": category}


# --- URL-based rules (deterministic) ---

@pytest.mark.parametrize("url,expected", [
    ("https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16", "model"),
    ("https://huggingface.co/Jackrong/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled", "model"),
    ("https://huggingface.co/Tesslate/OmniCoder-9B", "model"),
    ("https://huggingface.co/Lightricks/LTX-2.3", "model"),
    ("https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4", "model"),
    ("https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8", "model"),
])
def test_huggingface_urls_become_model(url, expected):
    result = recategorize(item("Some Model", url, "A language model."))
    assert result["category"] == expected


@pytest.mark.parametrize("url", [
    "https://arxiv.org/abs/2603.17233",
    "https://arxiv.org/abs/2603.17305",
])
def test_arxiv_urls_become_paper(url):
    result = recategorize(item("Some Paper", url, "A research paper."))
    assert result["category"] == "paper"


def test_smithery_servers_url_becomes_mcp():
    result = recategorize(item(
        "Exa Search",
        "https://smithery.ai/servers/exa",
        "Fast web search and crawling for AI agents.",
    ))
    assert result["category"] == "mcp"


# --- Keyword-based rules (GitHub repos from today's post) ---

@pytest.mark.parametrize("title,url,summary", [
    (
        "open-swe",
        "https://github.com/langchain-ai/open-swe",
        "Asynchronous coding agent framework automating bug fixes, feature impl, and code reviews via LLM orchestration.",
    ),
    (
        "MaxKB",
        "https://github.com/1Panel-dev/MaxKB",
        "Enterprise agent platform for knowledge retrieval, tool use, and multi-agent orchestration with easy deployment.",
    ),
    (
        "letta-code",
        "https://github.com/letta-ai/letta-code",
        "Memory-first coding agent retaining context across sessions for code generation/debugging.",
    ),
    (
        "honcho",
        "https://github.com/plastic-labs/honcho",
        "Memory library for stateful AI agents, enabling persistent storage/retrieval with vector search.",
    ),
    (
        "unsloth",
        "https://github.com/unslothai/unsloth",
        "Unified UI for training/fine-tuning open-weight LLMs (Qwen/DeepSeek) with LoRA quantization, targeting developers avoiding vendor lock-in.",
    ),
])
def test_github_dev_tool_keywords_become_dev_tool(title, url, summary):
    result = recategorize(item(title, url, summary))
    assert result["category"] == "dev-tool"


# --- GitHub repos with no strong signals stay as release ---

@pytest.mark.parametrize("title,url,summary", [
    (
        "pyodide",
        "https://github.com/pyodide/pyodide",
        "Python distribution for browsers/Node.js via WebAssembly, enabling NumPy/pandas/scikit-learn client-side execution for notebooks and serverless ML.",
    ),
    (
        "newton",
        "https://github.com/newton-physics/newton",
        "GPU-accelerated physics simulation engine for robotics, offering rigid/soft-body dynamics and integration with control pipelines.",
    ),
    (
        "chatterbox",
        "https://github.com/resemble-ai/chatterbox",
        "High-fidelity open-source TTS system supporting multilingual real-time speech synthesis.",
    ),
])
def test_github_without_dev_tool_signals_stays_release(title, url, summary):
    result = recategorize(item(title, url, summary))
    assert result["category"] == "release"


# --- URL rules take priority over LLM-assigned category ---

def test_url_rule_overrides_llm_category():
    # LLM called it a "release" but it's on HuggingFace — should become "model"
    result = recategorize(item(
        "Some Model",
        "https://huggingface.co/org/some-model",
        "A fine-tuned language model.",
        category="release",
    ))
    assert result["category"] == "model"


# --- Other fields are preserved ---

def test_recategorize_preserves_other_fields():
    original = {
        "title": "Draft-and-Prune",
        "url": "https://arxiv.org/abs/2603.17233",
        "summary": "Two-stage auto-formalization pipeline.",
        "category": "release",
        "relevance_score": 8,
    }
    result = recategorize(original)
    assert result["title"] == original["title"]
    assert result["summary"] == original["summary"]
    assert result["relevance_score"] == 8
    assert result["category"] == "paper"


def test_load_watchlist_missing_file(tmp_path):
    result = load_watchlist(set(), path=tmp_path / "watchlist.txt")
    assert result == []


def test_load_watchlist_returns_urls(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("https://example.com/a\nhttps://example.com/b\n")
    result = load_watchlist(set(), path=wl)
    assert result == ["https://example.com/a", "https://example.com/b"]


def test_load_watchlist_strips_seen_urls(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("https://example.com/a\nhttps://example.com/b\n")
    result = load_watchlist({"https://example.com/a"}, path=wl)
    assert result == ["https://example.com/b"]
    assert "https://example.com/a" not in wl.read_text()
    assert "https://example.com/b" in wl.read_text()


def test_load_watchlist_preserves_comments_and_blanks(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("# my note\nhttps://example.com/a\n\nhttps://example.com/seen\n")
    result = load_watchlist({"https://example.com/seen"}, path=wl)
    assert result == ["https://example.com/a"]
    text = wl.read_text()
    assert "# my note" in text
    assert "https://example.com/seen" not in text


def test_load_watchlist_empty_file(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("")
    result = load_watchlist(set(), path=wl)
    assert result == []


def test_save_watchlist_missing_file(tmp_path):
    # No file → no error, nothing created
    save_watchlist({"https://example.com/a"}, path=tmp_path / "watchlist.txt")
    assert not (tmp_path / "watchlist.txt").exists()


def test_save_watchlist_removes_consumed(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("https://example.com/a\nhttps://example.com/b\n")
    save_watchlist({"https://example.com/a"}, path=wl)
    text = wl.read_text()
    assert "https://example.com/a" not in text
    assert "https://example.com/b" in text


def test_save_watchlist_preserves_comments(tmp_path):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("# keep me\nhttps://example.com/a\nhttps://example.com/b\n")
    save_watchlist({"https://example.com/b"}, path=wl)
    text = wl.read_text()
    assert "# keep me" in text
    assert "https://example.com/a" in text
    assert "https://example.com/b" not in text
