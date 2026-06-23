# atyDam-epub-v3.0 — PDF→EPUB with GPT-style bold emphasis

> The same 9-phase PDF→EPUB pipeline as v2.0, extended with AI-powered bold keyword highlighting for scannable, easy-to-read output.

[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blueviolet)](https://github.com/NachaFromMars)

## Overview
atyDam-epub-v3.0 builds on the v2.0 pipeline with an additional Phase B10: AI-driven GPT-style bold emphasis. The AI reads and understands each paragraph, then bolds the most important keywords — definitions, list items, numbers, conclusions, proper names, contrasts, key instructions, and scan anchors. The result is approximately 1,500 bold patterns per 400-page book, giving readers fast visual navigation through dense material. For plain text output without bolding, use v2.0.

## What GPT-Style Bold Means
Bold is applied to 7 categories:
- **Definitions** — key concepts being explained
- **Lists** — important items in series
- **Numbers** — quantities and counts
- **Conclusions** — summary sentences
- **Proper names** — Buddhist terms, entities
- **Contrasts** — comparative phrases
- **Key instructions** — "remember…", "note that…"

**Result:** ~1,500 bold patterns / 400-page book → 1–3 bold per paragraph.

## Usage / Quick Start
Trigger with a bold-EPUB request. Phase B10 runs after the standard 9-phase pipeline.

## Trigger Keywords (OpenClaw)
epub với bold, gpt-style epub, bold emphasis epub, chatgpt style epub

## Related Skills
- [atyDam-epub-v2.0](https://github.com/NachaFromMars/atyDam-epub-v2.0) — plain text version without bold emphasis

---
Part of the [NachaFromMars](https://github.com/NachaFromMars) OpenClaw skill ecosystem.
