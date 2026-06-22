---
name: atyDam-epub-v3.0
aliases:
  - pdf-epub-v3
  - pdf-epub v3
  - pdf2epub-v3
  - pdf2epub v3
  - pdf-to-epub-v3
  - pdf to epub v3
  - gpt-style-epub
  - gpt-style epub
  - bold-epub
  - epub-bold
  - epub-gpt-style
trigger_phrases:
  - "convert pdf sang epub với gpt-style"
  - "pdf to epub gpt-style"
  - "epub với bold"
  - "bold emphasis epub"
  - "in đậm từ khóa"
  - "chatgpt style epub"
  - "make epub easy-read"
description: Automated PDF→EPUB conversion pipeline v3.0 with GPT-STYLE bold emphasis. Same 9-phase pipeline as v2.0 PLUS Phase B10 (AI bold emphasis). Produces scannable, easy-to-read EPUB with ~1,500 bold keywords per 400-page book, following ChatGPT writing style. For plain text version without bold, use atyDam-epub v2.0.
---

# atyDam-epub v3.0 — PDF→EPUB with GPT-STYLE Bold Emphasis

## When to use this skill

When user wants to convert a PDF book to **easy-read EPUB with bold keywords** (GPT-style):
- PDF with broken font encoding (Vietnamese + Pali Buddhist texts)
- Books with complex tables, figures, footnotes
- **Want bold emphasis** for scanability (ChatGPT style)
- Want keywords highlighted for quick reference

For **plain text version without bold**, use **atyDam-epub v2.0** instead.

## What is GPT-Style?

**GPT-Style** = AI reads & understands content, then **bolds important keywords** per ChatGPT writing conventions:
1. **Definitions** — key concepts being explained
2. **Lists** — important items in series
3. **Numbers** — quantities emphasized (12 tâm, 18 tâm)
4. **Conclusions** — summary sentences
5. **Proper names** — Phật học terms & entities
6. **Contrasts** — comparative phrases ("different from...", "unlike...")
7. **Key instructions** — "remember..." or "note that..."
8. **Scan keywords** — quick-reference terms

**Result:** ~1,500 bold patterns per 400-page book → 1-3 bold per paragraph → dễ scan, dễ đọc.

## Pipeline Overview — 10 Phases + Audit Loop + GPT-Style

```
PDF input
  │
  ├─► Phase A: EXTRACT (PyMuPDF)
  │     • Extract images, render cover, chapters/TOC
  │     • Output: extract_meta.json
  │
  ├─► Phase 1: TEXT RECOVERY (Gemini Flash)
  │     • Fix Vietnamese diacritics + Pali font damage
  │     • thinkingBudget=0 (CRITICAL)
  │
  ├─► Phase B2-B3: STRUCTURE PREP (regex)
  │     • Paragraph reconstruct + inline list split
  │
  ├─► Phase B6-B7: AI STRUCTURE (Gemini)
  │     • Heading hierarchy + semantic paragraphs
  │
  ├─► Phase B9: TABLE VISION (Gemini Vision)
  │     • PDF image → HTML table with rowspan/colspan
  │
  ├─► Phase B5: PROOFREAD (Gemini)
  │     • Spelling + Phật học terminology
  │
  ├─► Phase B10: GPT-STYLE BOLD (Gemini)
  │     ◄─── NEW IN v3.0 ────────────
  │     • AI reads & understands paragraphs
  │     • Bold keywords per 8 ChatGPT rules
  │     • ~1,500 patterns per 400 pages
  │     • Cost: ~$0.38
  │
  ├─► Phase C-D: MARKUP + BUILD (Python + Pandoc)
  │     • YAML front matter + Pali italic
  │     • Cover + CSS + EPUB 3.2
  │
  └─► AUDIT LOOP (7 layers)
        • Structural, semantic, spelling, tables, images, cross-ref, meta
```

## Step-by-step Execution

### Step 1: Setup workspace
```bash
WORKDIR="/root/.openclaw/workspace/<book-name>-epub"
mkdir -p "$WORKDIR/{chunks,recovered,images}"
cd "$WORKDIR"
cp scripts/* .  # Copy all phase scripts including phase_b10_bold_emphasis.py
```

### Step 2: Run pipeline
```bash
export GEMINI_API_KEY="..."

# Phase A: Extract
python3 phase_a_extract.py

# Phase 1: Recovery
python3 pipeline_parallel.py

# Phase B2-B3: Structure prep
python3 phase_b2_paragraphs.py
python3 phase_b3_smart_list.py

# Phase B6-B7: AI structure  
python3 phase_b6_smart_structure.py
python3 phase_b7_perfect_structure.py

# Phase B9: Vision tables
python3 phase_b9_tables_vision.py

# Phase B5: Proofread
python3 phase_b5_proofread.py

# ─── Phase B10: GPT-STYLE BOLD (NEW) ───
python3 phase_b10_bold_emphasis.py

# Phase C-D: Build
python3 phase_c_markup.py
python3 phase_d_build.py

# Audit loop
python3 audit_loop.py
python3 audit_v2.py

# Final build
python3 phase_d_build.py
```

### Step 3: Validate
```bash
java -jar /usr/share/java/epubcheck.jar TrietHoc-*.epub
# Expected: 0 fatals / 0 errors / 0 warnings
```

## Cost per book (~420 pages)

| Phase | Cost |
|-------|------|
| Phase 1 Recovery | $0.54 |
| Phase 2 Tables | $0.20 |
| Phase 5 Proofread | $0.40 |
| Phase 7 Structure | $0.42 |
| Phase 8 Perfect | $0.42 |
| **Phase B10 Bold** | **$0.38** ← v3.0 only |
| Audit V1 | $0.79 |
| Audit V2 | $0.38 |
| **TOTAL v3.0** | **$3.53** (~85,000 VNĐ) |

vs v2.0: $3.15 (no B10 phase)

## Quality Indicators (v3.0)

- ✅ Avg paragraph length 150-380 chars
- ✅ 9 chapters proper hierarchy
- ✅ All tables HTML with thead/tbody/th/td
- ✅ Italic Pali wrapping (~1,100+ terms)
- ✅ epubcheck: 0 errors / 0 warnings
- ✅ Images embedded (~30 figures)
- ✅ Cover from PDF page 1
- ✅ **~1,500 bold patterns** (GPT-style)
- ✅ 1-3 bold per paragraph (readable, not overwhelming)
- ✅ No bold in tables, headings, Pali italic

## Difference: v2.0 vs v3.0

| Feature | v2.0 | v3.0 |
|---------|------|------|
| Text recovery | ✅ | ✅ |
| Structure detection | ✅ | ✅ |
| Tables rebuild | ✅ | ✅ |
| Proofreading | ✅ | ✅ |
| **GPT-Style bold** | ❌ NO | ✅ YES |
| Bold patterns | 0 | ~1,500 |
| Cost per book | ~$3.15 | ~$3.53 |

## Files Structure

```
<book>-epub/
├── chunks/              
├── recovered/           
├── images/              
├── extract_meta.json    
├── cover.png            
├── style-v2-premium.css 
├── pipeline_parallel.py 
├── phase_a_extract.py   
├── phase_b2_paragraphs.py  
├── phase_b3_smart_list.py  
├── phase_b5_proofread.py   
├── phase_b6_smart_structure.py  
├── phase_b7_perfect_structure.py 
├── phase_b9_tables_vision.py    
├── phase_b10_bold_emphasis.py  ◄─── v3.0 NEW
├── phase_c_markup.py    
├── phase_d_build.py     
├── audit_loop.py        
├── audit_v2.py          
├── audit-log.json       
└── TrietHoc-A-Ty-Dam-VN.epub  # Final output WITH BOLD
```

## Trigger Auto-run

When user explicitly requests v3.0 or GPT-style:
- "convert PDF sang EPUB với gpt-style"
- "pdf to epub gpt-style"
- "epub với bold"
- "chatgpt style epub"
- etc.

Em will run v3.0 (includes Phase B10).

For standard conversion **without bold**, default is **v2.0**.

## Memory Note

atyDam-epub v3.0 is the **GPT-style bold version**. 
- Produced from work done 16/05/2026
- Phase B10 (AI bold emphasis) added to standard v2.0 pipeline
- V11 of Triết Học A-Tỳ-Đàm: example v3.0 output (1,524 bold patterns)

For **plain text version**, see **atyDam-epub v2.0** skill.
