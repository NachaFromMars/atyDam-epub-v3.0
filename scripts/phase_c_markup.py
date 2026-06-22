#!/usr/bin/env python3
"""
Phase C: Semantic Markup
- Convert clean.txt → Markdown with:
  * Proper heading levels (H1=Chapter, H2=Roman section, H3=A. B. C., H4=1. 2. 3.)
  * Italic Pali terms <em class="pali"> (from italic_spans_per_page)
  * Image embeds (using PDF figure pages rendered)
  * Bảng X- → blockquote (table representation)
  * Hình X- → image with caption
  * Index section separation
"""
import re
import json
from pathlib import Path

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
CLEAN_FILE = WORKDIR / "clean-structured.txt"  # V2.4: AI-reconstructed tables
MD_FILE = WORKDIR / "atyDam-v2.md"

meta = json.load(open(WORKDIR / "extract_meta.json"))

# ===== 1. Load clean text =====
text = CLEAN_FILE.read_text(encoding="utf-8")
print(f"📖 Clean text: {len(text):,} chars")

# ===== 2. Build italic Pali term database =====
print("🪷 Building italic Pali term database...")
italic_terms = set()
for page, spans in meta["italic_spans_per_page"].items():
    for s in spans:
        s = s.strip()
        # Pali terms are short (1-30 chars), alphabetic with diacritics
        if 1 < len(s) < 50 and re.match(r'^[A-Za-z\u0100-\u017fāīūṃṇṭḍḷñṅ\s\-\(\)]+$', s):
            italic_terms.add(s)
# Clean up: remove generic words
italic_terms = {t for t in italic_terms if not t.lower() in ('the', 'and', 'of', 'a', 'in')}
print(f"  Italic Pali terms collected: {len(italic_terms)}")
print(f"  Sample: {list(italic_terms)[:10]}")

# ===== 3. Build figure & table map =====
figures = {f["num"]: f for f in meta.get("figures_toc", [])}
tables = {t["num"]: t for t in meta.get("tables_toc", [])}

# Map: which images extracted correspond to which figure?
# Strategy: order by page, match to figures detected on those pages
images = meta.get("images", [])
images_by_page = {}
for img in images:
    if img["size"] < 1000: continue  # skip decorations
    images_by_page.setdefault(img["page"], []).append(img)

# Use pre-computed mapping from extract_meta.json (sequential mapping)
figure_to_image = {int(k): v for k, v in meta.get("fig_to_img", {}).items()}

print(f"\n🖼️  Figures: {len(figures)}, with matched images: {len(figure_to_image)}")

# ===== 4. Process text → Markdown =====
print("\n📝 Converting to Markdown...")

lines = text.split("\n")
md_lines = []
i = 0
in_index = False  # Detect Index section by end pattern
chapters_seen = 0

def is_index_entry(line):
    """Index entries: 'Word · 123' or 'Word, 123, 456'"""
    return bool(re.match(r'^[A-ZĐÂÊÔƠƯĨ\w][\w\s\(\)\-,]+(\s·\s|\s,\s)\d+', line.strip()))

# Detect TOC entries (Bảng X / Hình X listings)
def is_toc_listing(line):
    return bool(re.match(r'^(Bảng|Hình|CHƯƠNG)\s+\d+[\-\.][^\n]{5,}\s+\d{1,3}\s*$', line.strip()))

while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    # ===== H1: Chapter starts =====
    # Pattern: "CHƯƠNG N" alone + next non-blank line is title
    m = re.match(r'^CHƯƠNG\s+(\d+)\s*$', stripped)
    if m:
        ch_num = m.group(1)
        # Look ahead for title
        title = ""
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines):
            title = lines[j].strip()
            i = j + 1
        else:
            i += 1
        md_lines.append("")
        md_lines.append(f"# CHƯƠNG {ch_num} — {title}")
        md_lines.append("")
        chapters_seen += 1
        continue

    # ===== H2: Roman numeral sections (I. ... VII.) =====
    # E.g. "I. TÂM DỤC GIỚI (kāmāvacaracitta)"
    m = re.match(r'^([IVX]+)\.\s+([A-ZĐÂÊÔƠƯĨ\w][^\n]{3,100})$', stripped)
    if m and len(stripped) < 120 and not re.search(r'\d{2,}', stripped):
        # Only if next line is blank or sub-heading (not body)
        title_text = m.group(2).strip().rstrip('.')
        md_lines.append("")
        md_lines.append(f"## {m.group(1)}. {title_text}")
        md_lines.append("")
        i += 1
        continue

    # ===== H3: A. B. C. sub-sections =====
    m = re.match(r'^([A-Z])\.\s+([A-ZĐÂÊÔƠƯĨ\w][^\n]{3,100})$', stripped)
    if m and len(stripped) < 120 and not re.search(r'\d{2,}', stripped):
        sub_text = m.group(2).strip().rstrip('.')
        md_lines.append("")
        md_lines.append(f"### {m.group(1)}. {sub_text}")
        md_lines.append("")
        i += 1
        continue

    # ===== H4: 1. 2. 3. enumerated items =====
    # Pattern A: "1. Term (pali)" then body follows  → heading
    # Pattern B: "1. Term (pali): definition text..." → split heading + body
    # Pattern C: "1. Just plain text..." → list item, not heading
    
    # Try to detect h4-like definition: "N. Term (pali): explanation..."
    m_def = re.match(r'^(\d{1,2})\.\s+([ĐÂÊÔƠƯĨA-Z][\w\s,āīūṃṇṭḍñṅ\-]{2,40}?\s*\([^)]+\))\s*[:\.]?\s*(.*)$', stripped, re.UNICODE)
    if m_def and len(m_def.group(2)) < 80:
        num = m_def.group(1)
        term = m_def.group(2).strip()
        rest = m_def.group(3).strip()
        md_lines.append("")
        md_lines.append(f"#### {num}. {term}")
        md_lines.append("")
        # Merge: rest + following body lines (skip 1 blank line allowed)
        merged_body = rest
        j = i + 1
        # Skip exactly one blank line after heading (paragraph break)
        skipped_blank = False
        while j < len(lines):
            next_line = lines[j].strip()
            if not next_line:
                if skipped_blank:
                    # Two blanks = real paragraph break, stop
                    break
                skipped_blank = True
                j += 1
                continue
            # Stop if next is heading-like / list / image / caption
            if (re.match(r'^(CHƯƠNG|[IVX]+\.|[A-Z]\.\s|\d+\.\s|!\[|\*\*|Bảng|Hình)', next_line) or
                next_line.startswith(('#', '\u00ab'))):
                break
            # Stop if this is yet another short standalone Pali subtitle
            if re.match(r'^\([A-Zāīūṃṇṭḍñṅ]+\)$', next_line):
                break
            if merged_body:
                merged_body += " " + next_line
            else:
                merged_body = next_line
            j += 1
            skipped_blank = False
        if merged_body:
            md_lines.append(merged_body)
            md_lines.append("")
        i = j
        continue
    
    # Pattern A: Short heading with parens (no colon)
    m = re.match(r'^(\d{1,2})\.\s+([ĐÂÊÔƠƯĨA-Z][^.\n:]{3,60}\([^)]+\))$', stripped)
    if m and len(stripped) < 100:
        md_lines.append("")
        md_lines.append(f"#### {m.group(1)}. {m.group(2).strip()}")
        md_lines.append("")
        i += 1
        continue
    
    # Pattern D: All-caps short heading
    m = re.match(r'^(\d{1,2})\.\s+([ĐÂÊÔƠƯĨA-Z][ĐÂÊÔƠƯĨA-Z\s]{3,60})$', stripped)
    if m and len(stripped) < 80 and m.group(2).strip().isupper():
        md_lines.append("")
        md_lines.append(f"#### {m.group(1)}. {m.group(2).strip()}")
        md_lines.append("")
        i += 1
        continue

    # ===== Hình X- ... → Image embed =====
    m = re.match(r'^Hình\s+(\d+)\s*[\-\.]+\s*(.+?)(?:\s*\.{3,}\s*\d+)?$', stripped)
    if m:
        fig_num = int(m.group(1))
        fig_title = m.group(2).strip().rstrip('.')
        img_file = figure_to_image.get(fig_num)
        # If TOC listing (with dots and page num), skip
        if re.search(r'\.{5,}\s*\d+\s*$', stripped):
            i += 1
            continue
        # Otherwise insert image
        if img_file:
            md_lines.append("")
            md_lines.append(f"![Hình {fig_num}- {fig_title}](images/{img_file})")
            md_lines.append("")
            md_lines.append(f"*Hình {fig_num}- {fig_title}*")
            md_lines.append("")
        else:
            md_lines.append("")
            md_lines.append(f"**Hình {fig_num}- {fig_title}**")
            md_lines.append("")
        i += 1
        continue

    # ===== Bảng X- ... → Marked as table caption =====
    m = re.match(r'^Bảng\s+(\d+)\s*[\-\.]+\s*(.+?)(?:\s*\.{3,}\s*\d+)?$', stripped)
    if m:
        tbl_num = m.group(1)
        tbl_title = m.group(2).strip().rstrip('.')
        # Skip if TOC listing
        if re.search(r'\.{5,}\s*\d+\s*$', stripped):
            i += 1
            continue
        md_lines.append("")
        md_lines.append(f"**Bảng {tbl_num}- {tbl_title}**")
        md_lines.append("")
        i += 1
        continue

    # ===== Index detection =====
    if is_index_entry(stripped):
        if not in_index:
            md_lines.append("")
            md_lines.append("# MỤC LỤC TỪ ĐIỂN")
            md_lines.append("")
            in_index = True
        md_lines.append(stripped + "  ")  # markdown line break
        i += 1
        continue

    # ===== Skip TOC listings (Bảng X- ...... 37) =====
    if is_toc_listing(stripped):
        i += 1
        continue

    # ===== Regular body line =====
    md_lines.append(line)
    i += 1

# ===== 5. Apply italic Pali markup (BODY ONLY, skip headings) =====
print("🪷 Applying italic Pali markup (body only)...")

# Match Pali terms in parentheses: (term)
# Pali pattern: contains diacritics or specific Pali endings
pali_pattern = re.compile(r'\(([a-zāīūṃṇṭḍḷñṅ\-\s]+)\)', re.IGNORECASE)

def wrap_pali(m):
    term = m.group(1).strip()
    if len(term) < 3:
        return m.group(0)
    has_diacritic = any(c in term.lower() for c in 'āīūṃṇṭḍḷñṅ')
    pali_suffix = bool(re.search(r'(tta|sika|gaha|āna|ariya|kāra|catta|ñāṇa)$', term.lower()))
    if has_diacritic or pali_suffix:
        return f'(*{term}*)'  # Use markdown italic instead of inline HTML
    return m.group(0)

# Apply line-by-line, skip heading lines
result_lines = []
pali_count = 0
for line in md_lines:
    # Skip headings (start with #) — Pandoc handles italic in headings differently
    if line.startswith('#'):
        result_lines.append(line)
        continue
    new_line = pali_pattern.sub(wrap_pali, line)
    if '*' in new_line and new_line != line:
        pali_count += new_line.count('*') // 2
    result_lines.append(new_line)

md_text = "\n".join(result_lines)
print(f"  Wrapped {pali_count} Pali terms with *italic* (markdown)")

# ===== 6. Cleanup excessive blank lines =====
md_text = re.sub(r'\n{4,}', '\n\n\n', md_text)

# ===== 7. Add title page + front matter =====
front = """---
title: "Triết Học A-Tỳ-Đàm"
subtitle: "của Phật giáo Truyền thống Theravāda"
author: "Dr. Mehm Tin Mon"
translator: "Tỳ-khưu Giác Nguyên"
publisher: "NXB Hồng Đức"
date: "2015"
lang: "vi"
description: "Buddha Abhidhamma — Ultimate Science. Bản tiếng Việt do Tỳ-khưu Giác Nguyên dịch."
---

"""
md_text = front + md_text

MD_FILE.write_text(md_text, encoding="utf-8")
print(f"\n✅ Phase C done. Markdown: {MD_FILE}")
print(f"   Size: {len(md_text):,} chars")
print(f"   Chapters: {chapters_seen}")
print(f"   Pali markup: {pali_count} terms")
