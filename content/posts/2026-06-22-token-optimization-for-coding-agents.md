---
title: "Token optimization for coding agents"
date: 2026-06-22
draft: false
tags: [roundup]
description: "This week: obra/superpowers, bytedance/deer-flow, langchain-ai/langgraph and more."
---

Token optimization is suddenly the bottleneck for any coding agent you spin up. Context windows are capped, costs are climbing, and the difference between a smooth refactoring and a “maximum context length” error is often just a matter of how you slice the problem. This week’s collection gives you concrete ways to keep your agents lean, from skill‑based decomposition to explicit state pruning.

## [obra/superpowers](https://github.com/obra/superpowers)
It treats coding tasks as reusable “skills” that can be called without re‑explaining the whole workflow each time. Imagine a skill that runs `git diff` and another that writes a PR description; each invocation stays small, so the agent never needs to dump the entire repo history into the prompt. The catch is you have to author the skill catalog yourself, which can be a bit of upfront work for complex domains.

## [bytedance/deer-flow](https://github.com/bytedance/deer-flow)
Deer‑Flow orchestrates a hierarchy of subagents and explicitly caps intermediate results to stay within the context window. You can break a large refactor into a planning subagent, a file‑analysis subagent, and a code‑generation subagent, each holding only its slice of the problem. The trade‑off is the added latency of handoffs and the need to manage sandbox execution, which can be fiddly if your environment restricts subprocesses.

## [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)
LangGraph lets you model an agent’s flow as a graph with checkpointing, so you can prune or summarize nodes before passing state forward. If you’re iterating over a bunch of test files, you can store the aggregated test results in a summary node and feed only that back to the next step, dramatically cutting token churn. The downside is the graph DSL can become unwieldy for highly dynamic or conditional workflows.

## [openai/openai-agents-python](https://github.com/openai/openai-agents-python)
This lightweight framework splits work across specialized agents, each with its own bounded context window, using handoff mechanisms. You could have a “lint” agent that only sees the diff you send, then hand off to a “refactor” agent that works on the cleaned‑up version, keeping token usage low. The limitation is you need to design the handoff logic yourself; the library doesn’t provide built‑in optimizations for context compaction.

## [shanraisshan/claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice)
A practical handbook for Claude Code that spells out tricks like prompt chunking, output truncation, and selective tool invocation to stay under the limit. It includes a pattern where you stream a file in chunks, have the agent annotate each chunk, and then merge the annotations in a single follow‑up, avoiding a massive single prompt. The guide is great, but it assumes you’re using Claude Code directly, so it doesn’t cover generic agent frameworks.

## [deepset-ai/haystack](https://github.com/deepset-ai/haystack)
Haystack gives you explicit control over retrieval, routing, and memory, making it easy to implement context compaction and selective memory summarization. You can hook it into a coding agent to fetch only the relevant functions from a large codebase, then discard the rest after each step. The trade‑off is the added complexity of wiring pipelines and the fact that Haystack is more oriented toward RAG‑heavy workloads than pure code generation.

## The Takeaway
All of these tools share a common theme: break the problem into smaller, focused pieces and manage what state you keep alive between steps. Whether you go with a skill framework, a subagent orchestrator, or a graph‑based workflow, the key is to keep each prompt slice tight and to discard or summarize what you don’t need. If I were building a coding agent today, I’d start by sketching out the skills or subagents I need, then pick a framework that matches my existing stack—likely LangGraph for complex control flows or openai‑agents‑python for a quick, lightweight prototype.