---
title: "Claude Code ecosystem and AGENTS.md support"
date: 2026-05-04
draft: false
tags: [roundup]
description: "This week: x1xhlol/system-prompts-and-models-of-ai-tools, Opencode: AI coding agent, built for the terminal, Yolobox – Run AI coding agents with full sudo without nuking home dir and more."
---

If you've been trying to use Claude Code seriously this past month, you already know: the gap between "cool demo" and "daily driver" is mostly about configuration, limits, and trust. The community has been busy filling those gaps — from leaked prompt repos to sandboxing tools to open-source alternatives. Here's what actually matters right now.

## [x1xhlol/system-prompts-and-models-of-ai-tools](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools)

This repo is a goldmine: reverse-engineered system prompts from Claude Code, Cursor, Devin, Windsurf, and a bunch of other tools, all in one place. If you've ever wondered how Claude Code structures its AGENTS.md or what instructions it actually ingests, this is where you go to find out. Engineers are using it to reverse-engineer effective prompt patterns and build better custom configurations for their own agents. The obvious caveat: these are leaked internals, so they can drift from what's actually shipping today. But as a reference for understanding how these tools think about context windows, tool use, and agent boundaries, it's unmatched.

## [Opencode: AI coding agent, built for the terminal](https://github.com/sst/opencode)

The SST team built this as a terminal-native AI coding agent, and with nearly 400 HN points it's clear people are hungry for Claude Code alternatives. It's open-source, it runs in your terminal, and you can install it today without waiting for an invite or worrying about Anthropic's rate limits. The tradeoff is that it's younger and less battle-tested — you won't get the same depth of tool integration or the polish of Claude Code's file editing. But if you're hitting walls with Claude Code's availability, this is the most credible drop-in replacement that respects the terminal-first workflow.

## [Yolobox – Run AI coding agents with full sudo without nuking home dir](https://github.com/finbarr/yolobox)

Here's a problem every Claude Code user eventually hits: the agent needs sudo to install packages or modify system files, and you're one bad command away from a destroyed dev environment. Yolobox sandboxes the agent so it gets full sudo inside the container while your actual home directory stays untouched. It's a simple idea but it solves a real trust issue — the kind of thing that stops engineers from letting agents run unsupervised. The catch is that it adds a layer of setup and you need to be comfortable with container-based workflows. But if you're running agents on real infrastructure, this is the kind of guardrail that makes "let the agent handle it" actually viable.

## [Claude Code weekly rate limits](https://news.ycombinator.com/item?id=44713757)

609 points and 705 comments — this is the thread where the Claude Code community collectively lost its mind over weekly rate limits. It's the single most important discussion for anyone trying to use Claude Code in a real workflow, because it surfaces every workaround, alternative, and coping strategy in one place. You'll find people splitting usage across accounts, falling back to other models, scheduling heavy tasks off-peak, and debating whether the limits are a business model signal or a capacity problem. The thread is essential reading not because it has answers, but because it maps the entire landscape of frustration — and the creative ways engineers are working around it.

## The Takeaway

The Claude Code ecosystem right now is defined by friction: rate limits that break real workflows, missing configuration standards like AGENTS.md support, and a trust gap around what agents can safely touch. The community response is telling — people aren't just complaining, they're building alternatives (Opencode), tooling (Yolobox), and reference libraries (the prompt repo) to fill the gaps. If you're adopting Claude Code today, the smart move is to assume the limits and rough edges are permanent for now, and build your workflow around them: sandbox aggressively, keep a terminal-native alternative ready, and study how the best prompts are structured. The engineers who thrive in this ecosystem are the ones treating it as a tool with constraints, not a magic wand.