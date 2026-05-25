---
title: "Claude Code usage limits and access restrictions"
date: 2026-05-25
draft: false
tags: [roundup]
description: "This week: Anthropic unveils new rate limits to curb Claude Code power users, Tell HN: Don't use Claude Design, lost access to my projects after unsubscribing, Claude Code new limits – Important updates to your Max account usage limits and more."
---

The Claude Code situation this week is a mess. Engineers are bumping into new hard limits, getting cut off after subscription changes, and realizing they can't trust the tool for a full workday without quota interruptions. The threads and announcements paint a picture of Anthropic tightening the screws, and it's worth looking at what's actually happening under the hood.

## [Anthropic unveils new rate limits to curb Claude Code power users](https://techcrunch.com/2025/07/28/anthropic-unveils-new-rate-limits-to-curb-claude-code-power-users/)
Anthropic is now capping high-volume usage patterns specifically in Claude Code, which means the days of running long agentic sessions without hitting a wall are over for power users. The limits seem targeted at API-heavy workflows rather than casual prompting, which hits engineers doing multi-file refactors or sustained agent runs the hardest. If you were relying on Claude Code as your primary pair programmer, the ceiling just got a lot lower — and Anthropic isn't saying exactly where.

## [Tell HN: Don't use Claude Design, lost access to my projects after unsubscribing](https://news.ycombinator.com/item?id=48128003)
This thread is a warning label. Multiple users report that dropping a Claude subscription nuked their access to projects they'd been actively working on, with no graceful downgrade path. The takeaway isn't abstract — it's that your Claude-stored context and tool access are tied to your billing status, and revoking that subscription can pull the rug out mid-work. If you're building anything real with Claude Code, you need a plan for what happens when your quota or your subscription doesn't renew.

## [Claude Code new limits – Important updates to your Max account usage limits](https://news.ycombinator.com/item?id=44713837)
This HN discussion threads concrete numbers: people are seeing their daily and weekly quotas shrink to the point where a single extended coding session eats most of their allowance. The frustration is palpable because these limits weren't communicated well before they hit, so engineers walked into their day expecting normal access and got rate-limited after an hour. The pattern here is consistent across the other threads — limits are tightening, and the communication around them is poor.

## [YouMind-OpenLab/nano-banana-pro-prompts-recommend-skill](https://github.com/YouMind-OpenLab/nano-banana-pro-prompts-recommend-skill)
This is a Claude Code skill with over 1,500 stars that pulls from a library of 10,000+ image prompts, letting you call it from within a Claude Code session. It's a solid example of the ecosystem around Claude Code — people are building extensions and skills to get more value out of it. But it also quietly underscores the dependency risk: when the platform shifts limits or access, every skill that leans on it inherits those restrictions. The high star count tells you engineers find it useful; the access problems tell you they may not be able to rely on it.

## The Takeaway
The common thread across all of these is that Claude Code's reliability as a daily driver is in question right now. Anthropic is enforcing limits more aggressively, subscription changes can cut access abruptly, and there's no clear migration path if your quota runs dry mid-task. If you're using it seriously, treat it as a best-effort tool with hard ceilings, not a guaranteed resource — and start thinking about fallback strategies before the next quota reduction drops.