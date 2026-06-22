# atyDam-epub v2.0 — Flow Chart

## Big Picture

```
                    ┌─────────────────────────┐
                    │   PDF Input (any book)  │
                    └────────────┬────────────┘
                                 │
                                 ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE A — SMART EXTRACT (PyMuPDF, free)        │
       │  • Detect chapters, TOC pages, blank pages       │
       │  • Extract images (47 figures for atyDam)        │
       │  • Render cover from page 1                       │
       │  • Build extract_meta.json                       │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE 1 — TEXT RECOVERY (Gemini, $0.50)        │
       │  • Split into 4500-char chunks                    │
       │  • Fix Vietnamese diacritics + Pali subset font  │
       │  • thinkingBudget=0 (CRITICAL)                   │
       │  • 5 workers parallel                             │
       │  • Output: recovered/chunk_NNNN.txt              │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE B2-B3 — STRUCTURE PREP (regex, free)     │
       │  • Join physical lines into paragraphs           │
       │  • Split inline "1) 2) 3)" lists                 │
       │  • Mark table boundaries (TABLE_START/END)       │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE B6-B7 — AI STRUCTURE ($0.85)             │
       │  • Detect heading hierarchy (CHƯƠNG > I > A > 1)│
       │  • Semantic paragraph boundaries (8 rules)       │
       │  • Merge broken lines, split topic shifts        │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE B9 — TABLE VISION ($0.20)                │
       │  • Render PDF page → image (2x scale)            │
       │  • Gemini Vision reads visual layout              │
       │  • Output HTML <table> with rowspan/colspan      │
       │  • All 60 tables from atyDam example             │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE B5 — PROOFREADING ($0.40)                │
       │  • Vietnamese spelling fixes                       │
       │  • Phật học terminology corrections               │
       │  • Dictionary + AI suggestions                    │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  PHASE C-D — MARKUP + BUILD (Pandoc, free)      │
       │  • Add YAML front matter                          │
       │  • Pali italic wrapping                          │
       │  • Build EPUB 3.2 with cover + CSS               │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  AUDIT LOOP (closed-loop, max 5 iterations)     │
       │                                                   │
       │   Layer 1: Structural (regex)                    │
       │   Layer 2: Semantic (AI)                         │
       │   Layer 3: Spelling (dict + AI)                  │
       │   Layer 4: Tables (validation)                   │
       │   Layer 5: Images (file verify)                  │
       │   Layer 6: Cross-ref (sequences)                 │
       │   Layer 7: AI meta-review (deep read)            │
       │                                                   │
       │   ◄─── LOOP UNTIL 0 ISSUES ───►                  │
       └────────────────────┬────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  FINAL EPUB (validated, premium quality)        │
       │  • 0 errors / 0 warnings (epubcheck)             │
       │  • ~1.4 MB                                        │
       │  • 9 chapters proper hierarchy                    │
       │  • All tables HTML with proper structure          │
       │  • ~1,100 Pali italic terms                       │
       │  • ~30 embedded images                            │
       │  • Cover from PDF page 1                          │
       │  • Reader-theme friendly tables                   │
       └─────────────────────────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────────┐
       │  📦 Send via Telegram to user                    │
       └─────────────────────────────────────────────────┘
```

## Decision Tree — When to apply which phase?

```
PDF has broken font (Vietnamese + Pali)?
├─ YES → Phase 1 RECOVERY required
└─ NO  → Skip Phase 1

Book has complex tables?
├─ YES → Phase B9 VISION required
└─ NO  → Phase B8 (PDF text context) sufficient

Book has many footnotes/page headers leaking?
├─ YES → Audit Layer 2 SEMANTIC critical
└─ NO  → Lighter audit OK

Book in Vietnamese with Buddhist terms?
├─ YES → Phase B5 PROOFREAD with custom dict
└─ NO  → Generic spelling dict

User wants premium output?
├─ YES → All phases + 2 audit rounds
└─ NO  → Lighter pipeline (Phase 1 + C + D)
```

## Cost Estimator

| Book pages | Est. cost (Gemini 2.5 Flash paid) |
|------------|-----------------------------------|
| 100        | $0.80                              |
| 200        | $1.60                              |
| 400        | $3.20                              |
| 800        | $6.40                              |

(Vietnamese + Pali compounds: ~1.5x multiplier due to token-per-char ratio)

## Quality Metrics — Target

- ✅ Paragraph length: 150-380 chars avg (proper semantic)
- ✅ Heading hierarchy: 4 levels (H1=Chương, H2=Roman, H3=Letter, H4=Number)
- ✅ Tables: 100% HTML structure (no flat text)
- ✅ Italic Pali: 90%+ terms wrapped
- ✅ epubcheck: 0 fatals / 0 errors / 0 warnings
- ✅ Image embedding: 100% real figures (skip decorations <5KB)
- ✅ Cover: rendered from PDF page 1

## Failure Recovery

| Issue                      | Auto-fix                                     |
|----------------------------|----------------------------------------------|
| Gemini truncation          | thinkingBudget=0 (already set)               |
| Rate limit 429             | Sleep 20s + retry 3x                         |
| Pandoc auto-list           | Replace `N. ` → `(N) ` in cells              |
| Empty cells in table       | Re-run B9 Vision with stricter prompt        |
| Caption duplicate in <th>  | Regex strip after generation                 |
| Unbalanced <em> in cells   | Auto-add closing tag                         |
| Image refs broken          | Restore from extract_meta.json fig_to_img    |
| Click table trắng xóa      | CSS: no background-color, only borders       |
