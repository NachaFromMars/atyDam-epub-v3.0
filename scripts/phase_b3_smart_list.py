#!/usr/bin/env python3
"""
Phase B3: Smart List Splitter
- Split paragraphs có inline numbered items "1)...2)...3)..." hoặc "1....2....3...."
- Convert thành proper markdown list
- Preserve tables (Bảng X) bằng cách wrap với <!-- TABLE_START --> ... <!-- TABLE_END -->
"""
import re
from pathlib import Path

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean-paragraphs.txt"
OUTPUT = WORKDIR / "clean-paragraphs2.txt"


def split_inline_numbered_list(paragraph):
    """
    Detect and split inline numbered lists.
    Patterns:
    - "1) item one 2) item two 3) item three"  → bullet list
    - "1. Item One 2. Item Two 3. Item Three"  → ordered list (need ≥3 items)
    """
    # Pattern A: "N)" style — split on "\d+)\s+"
    # Must have at least 2 items "1)" and "2)" within paragraph
    paren_items = re.findall(r'\b(\d+)\)\s+', paragraph)
    if len(paren_items) >= 2:
        # Check items are sequential 1,2,3...
        nums = [int(n) for n in paren_items]
        if nums == list(range(nums[0], nums[0] + len(nums))):
            # Split
            parts = re.split(r'(?=\b\d+\)\s+)', paragraph)
            items = []
            preamble = ""
            for part in parts:
                if re.match(r'^\d+\)\s+', part):
                    items.append(part.strip())
                else:
                    if not items:
                        preamble = part.strip()
            if items:
                out_lines = []
                if preamble:
                    out_lines.append(preamble)
                    out_lines.append("")
                for item in items:
                    # Convert "1) text" to "1. text" (markdown ordered list)
                    m = re.match(r'^(\d+)\)\s+(.+)$', item, re.DOTALL)
                    if m:
                        out_lines.append(f"{m.group(1)}. {m.group(2).strip()}")
                return "\n\n".join(out_lines)
    
    # Pattern B: "N. " style — only if ≥3 items and each item is reasonably long
    # Need to be careful not to split body sentences that happen to have numbers
    # Heuristic: pattern "N. Capital..." multiple times in same paragraph
    dot_items = re.findall(r'\b(\d+)\.\s+[A-ZĐÂÊÔƠƯĨ]', paragraph)
    if len(dot_items) >= 3:
        nums = [int(n) for n in dot_items]
        if nums == list(range(nums[0], nums[0] + len(nums))):
            # Split on the pattern, keep delimiter
            parts = re.split(r'(?=\b\d+\.\s+[A-ZĐÂÊÔƠƯĨ])', paragraph)
            items = []
            preamble = ""
            for part in parts:
                part = part.strip()
                if not part: continue
                if re.match(r'^\d+\.\s+[A-ZĐÂÊÔƠƯĨ]', part):
                    items.append(part)
                else:
                    if not items:
                        preamble = part
            if items and len(items) >= 3:
                out_lines = []
                if preamble:
                    out_lines.append(preamble)
                    out_lines.append("")
                for item in items:
                    out_lines.append(item)
                return "\n\n".join(out_lines)
    
    return paragraph


def detect_table_block(paragraphs, start_idx):
    """
    Detect table block starting from 'Bảng X-' caption.
    Returns (table_text, next_idx) or (None, start_idx) if not a table.
    
    Tables in PDF have specific patterns:
    - Caption: "Bảng X- Title"
    - Content: row data, often with √ marks or columns
    """
    if start_idx >= len(paragraphs):
        return None, start_idx
    
    cap = paragraphs[start_idx].strip()
    m = re.match(r'^Bảng\s+(\d+)\s*[\-\.]\s*(.+)$', cap)
    if not m:
        return None, start_idx
    
    # Skip TOC entries (have dots and trailing page num)
    if re.search(r'\.{5,}\s*\d+\s*$', cap):
        return None, start_idx
    
    table_num = m.group(1)
    table_title = m.group(2).strip().rstrip('.')
    
    # Next paragraph(s) are the table data
    # Heuristic: collect paragraphs until next heading or significantly different content
    j = start_idx + 1
    table_data = []
    while j < len(paragraphs):
        p = paragraphs[j].strip()
        if not p:
            j += 1
            continue
        # Stop if heading or another caption or image
        if re.match(r'^(CHƯƠNG|#|!|Bảng\s+\d+|Hình\s+\d+|\*\*Bảng)', p):
            break
        if re.match(r'^[IVX]+\.\s+[A-ZĐÂÊÔƠƯĨ]', p):
            break
        if re.match(r'^[A-Z]\.\s+[A-ZĐÂÊÔƠƯĨ]', p) and len(p) < 100:
            break
        # Stop if numbered list starts at this paragraph
        if re.match(r'^\d+\.\s+[A-ZĐÂÊÔƠƯĨa-záàảãạâấầẩẫậ]', p) and len(p) < 200:
            break
        # Otherwise add to table data
        table_data.append(p)
        j += 1
        # Stop after collecting reasonable amount (max 3 paragraphs)
        if len(table_data) >= 3:
            break
    
    if not table_data:
        return None, start_idx + 1
    
    # Mark as table block
    table_block = f"<!-- TABLE_START num={table_num} -->\n"
    table_block += f"**Bảng {table_num}- {table_title}**\n\n"
    for row in table_data:
        table_block += row + "\n\n"
    table_block += "<!-- TABLE_END -->\n"
    
    return table_block, j


# ===== MAIN =====
print("📖 Reading clean-paragraphs.txt...")
text = INPUT.read_text(encoding="utf-8")
paragraphs = text.split("\n\n")
print(f"  Input: {len(paragraphs)} paragraphs")

# Process: split inline numbered lists + detect tables
out_paragraphs = []
i = 0
inline_list_splits = 0
table_detected = 0

while i < len(paragraphs):
    p = paragraphs[i]
    s = p.strip()
    
    if not s:
        i += 1
        continue
    
    # ===== Detect table =====
    if re.match(r'^Bảng\s+\d+\s*[\-\.]', s) and not re.search(r'\.{5,}\s*\d+\s*$', s):
        table, next_i = detect_table_block(paragraphs, i)
        if table:
            out_paragraphs.append(table)
            table_detected += 1
            i = next_i
            continue
    
    # ===== Split inline numbered lists =====
    new_p = split_inline_numbered_list(s)
    if new_p != s:
        inline_list_splits += 1
        out_paragraphs.append(new_p)
    else:
        out_paragraphs.append(s)
    i += 1

print(f"\n📊 Processing results:")
print(f"  Inline list splits: {inline_list_splits}")
print(f"  Tables detected: {table_detected}")

result = "\n\n".join(out_paragraphs)
OUTPUT.write_text(result, encoding="utf-8")
print(f"\n✅ Saved: {OUTPUT}")
print(f"  Output: {len(result):,} chars")

# Sample
print("\n📋 SAMPLE — Split result:")
sample_lines = result.split("\n")
shown = 0
for i, line in enumerate(sample_lines):
    if shown >= 20: break
    if re.match(r'^\d+\.\s+', line):
        print(f"  {line[:150]}")
        shown += 1
