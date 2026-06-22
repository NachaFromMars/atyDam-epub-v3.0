#!/usr/bin/env python3
"""
Phase B2: SMART PARAGRAPH RECONSTRUCTION
- Phân tích cấu trúc PDF text:
  * Physical lines (~42 chars) = artifact của PDF layout
  * Paragraph thật = nhiều physical lines join lại
- Detect paragraph boundaries dùng heuristics:
  1. Empty line → hard break
  2. Line ending with '.', '?', '!', ':' + next line starts with capital → maybe new paragraph
  3. Heading lines (CHƯƠNG, I., A., 1., etc.) → standalone
  4. List items → preserve
  5. Image/Bảng captions → standalone
  6. Indented line (different from prev) → new paragraph
- Output: clean text với paragraph thật + heading + list preserved
"""
import re
from pathlib import Path

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean.txt"
OUTPUT = WORKDIR / "clean-paragraphs.txt"


def is_heading(line):
    """Detect heading line — should remain standalone."""
    s = line.strip()
    if not s: return False
    # CHƯƠNG N standalone
    if re.match(r'^CHƯƠNG\s+\d+\s*$', s): return True
    # Roman numeral section: "I. TÂM DỤC GIỚI"
    if re.match(r'^[IVX]+\.\s+[A-ZĐÂÊÔƠƯĨ]', s) and len(s) < 100: return True
    # Letter section: "A. Sắc Tứ Đại"
    if re.match(r'^[A-Z]\.\s+[A-ZĐÂÊÔƠƯĨa-záàảãạâ]', s) and len(s) < 80: return True
    # Numbered subsection with capital start
    if re.match(r'^\d{1,2}\.\s+[A-ZĐÂÊÔƠƯĨ]', s) and len(s) < 100:
        # Distinguish from enumerated list items in body
        # Heuristic: heading if has Pali in parens (often case)
        if '(' in s and ')' in s: return True
        # Or if very short
        if len(s) < 50: return True
    # All caps title (with possible Pali in parens)
    if re.match(r'^[A-ZĐÂÊÔƠƯĨ\s\(\)āīūṃṇṭḍñṅ\-]+$', s) and 5 < len(s) < 80:
        # Mostly uppercase letters
        upper_ratio = sum(1 for c in s if c.isupper()) / max(1, sum(1 for c in s if c.isalpha()))
        if upper_ratio > 0.7: return True
    return False


def is_list_item(line):
    """Detect list item line."""
    s = line.strip()
    if not s: return False
    # Bullet markers
    if re.match(r'^[\-\*•○◦]\s+\S', s): return True
    # Numbered list "1. ", "1) ", "1.1 "
    if re.match(r'^\d{1,2}[\.\)]\s+[a-záàảãạâ]', s): return True  # lowercase = body list
    # Hint: "a." "b." "i." "ii." for nested lists
    if re.match(r'^[a-z][\.\)]\s+\S', s) and len(s) < 200: return True
    return False


def is_caption(line):
    """Detect figure/table caption."""
    s = line.strip()
    return bool(re.match(r'^(Hình|Bảng)\s+\d+[\-\.]', s))


def is_image_or_special(line):
    """Detect markdown image, bold caption, etc."""
    s = line.strip()
    if not s: return False
    return s.startswith(('![', '**', '*', '#', '>'))


def reconstruct_paragraphs(text):
    """
    Main algorithm:
    - Walk through lines, group into paragraphs
    - Hard breaks: empty line, heading, image, caption, list change
    - Soft join: regular text lines with no sentence-ending marker
    """
    lines = text.split("\n")
    out = []
    current_para = []
    prev_was_list = False
    prev_was_heading = False
    
    def flush_para():
        nonlocal current_para
        if current_para:
            # Join with single space, normalize whitespace
            para_text = " ".join(l.strip() for l in current_para if l.strip())
            para_text = re.sub(r'\s+', ' ', para_text)
            if para_text:
                out.append(para_text)
            current_para = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # ===== Empty line = paragraph break =====
        if not stripped:
            flush_para()
            if out and out[-1] != "":
                out.append("")
            prev_was_list = False
            continue
        
        # ===== Heading =====
        if is_heading(stripped):
            flush_para()
            if out and out[-1] != "":
                out.append("")
            out.append(stripped)
            out.append("")
            prev_was_heading = True
            prev_was_list = False
            continue
        
        # ===== Image/special markup (already markdown) =====
        if is_image_or_special(stripped):
            flush_para()
            if out and out[-1] != "":
                out.append("")
            out.append(stripped)
            prev_was_heading = False
            prev_was_list = False
            continue
        
        # ===== Caption =====
        if is_caption(stripped):
            flush_para()
            if out and out[-1] != "":
                out.append("")
            out.append(stripped)
            out.append("")
            prev_was_heading = False
            prev_was_list = False
            continue
        
        # ===== List item =====
        if is_list_item(stripped):
            flush_para()
            if not prev_was_list and out and out[-1] != "":
                out.append("")
            out.append(stripped)
            prev_was_list = True
            prev_was_heading = False
            continue
        
        # ===== Regular body text — accumulate into paragraph =====
        # End list mode
        if prev_was_list:
            prev_was_list = False
            if out and out[-1] != "":
                out.append("")
        
        # Heuristic: check if this is start of new paragraph
        # Sign of new paragraph:
        # - Previous line in current_para ends with .!?: AND
        # - Current line starts with capital letter / number
        if current_para:
            prev_line = current_para[-1].strip()
            if prev_line:
                last_char = prev_line[-1]
                first_char = stripped[0]
                # End with sentence-end punctuation
                ends_sentence = last_char in '.!?'
                # Start with capital or quote
                starts_new = (first_char.isupper() or 
                             first_char in '«"\'' or
                             first_char.isdigit())
                # Indent change (current line starts deeper than prev)
                cur_indent = len(line) - len(line.lstrip())
                prev_indent = 0  # assume base
                
                # New paragraph if: prev ends sentence + current starts new
                # BUT: only if prev line is "full length" (not last short line of para)
                if ends_sentence and starts_new and len(prev_line) > 30:
                    flush_para()
                    out.append("")
        
        current_para.append(line)
        prev_was_heading = False
    
    flush_para()
    
    # ===== Post-process: fix page-break artifacts =====
    # Pattern: paragraph ends with single letter (T, I, V, D...) = first letter of word
    # split across pages. Merge with next paragraph.
    result_paras = []
    skip_next = False
    paras_temp = [l for l in out]
    
    # First pass: gather as list of (line, is_empty)
    blocks = []
    cur = []
    for line in out:
        if not line:
            if cur:
                blocks.append(" ".join(cur))
                cur = []
            blocks.append("")
        else:
            cur.append(line)
    if cur:
        blocks.append(" ".join(cur))
    
    # Merge orphan letter at end with next paragraph
    fixed = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        # Check if block (non-empty) ends with single letter artifact
        m = re.search(r'\s([A-Z])\s*$', block)
        if block and m and len(block) > 50:
            # Find next non-empty block to merge
            j = i + 1
            while j < len(blocks) and not blocks[j].strip():
                j += 1
            if j < len(blocks) and not is_heading(blocks[j]) and not is_caption(blocks[j]):
                # Merge: drop trailing letter, prepend to next block
                trail_letter = m.group(1)
                cleaned = re.sub(r'\s[A-Z]\s*$', '', block).rstrip()
                next_block = blocks[j]
                # If next starts lowercase, the orphan letter is first letter of first word
                if next_block and next_block[0].islower():
                    merged = cleaned + " " + trail_letter + next_block
                else:
                    merged = cleaned + " " + next_block
                fixed.append(merged)
                fixed.append("")  # separator
                i = j + 1
                continue
        fixed.append(block)
        i += 1
    
    # Remove standalone single-letter paragraphs (page break artifacts that couldn't be merged)
    fixed2 = []
    for block in fixed:
        # Skip if block is just a single letter
        if re.match(r'^[A-Z]$', block.strip()):
            continue
        fixed2.append(block)
    
    # Collapse multiple empty lines
    result = []
    prev_empty = False
    for line in fixed2:
        if not line:
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False
    
    return "\n".join(result)


# ===== MAIN =====
print("📖 Reading clean.txt...")
text = INPUT.read_text(encoding="utf-8")
print(f"  Input: {len(text):,} chars, {text.count(chr(10))+1} lines")

print("\n🔧 Reconstructing paragraphs...")
reconstructed = reconstruct_paragraphs(text)
print(f"  Output: {len(reconstructed):,} chars, {reconstructed.count(chr(10))+1} lines")

# Stats
in_paragraphs = [p for p in reconstructed.split("\n\n") if p.strip()]
print(f"  Paragraphs: {len(in_paragraphs)}")
para_lengths = [len(p) for p in in_paragraphs]
if para_lengths:
    print(f"  Avg paragraph length: {sum(para_lengths)//len(para_lengths)} chars")
    print(f"  Median: {sorted(para_lengths)[len(para_lengths)//2]} chars")
    print(f"  Max: {max(para_lengths)} chars")

OUTPUT.write_text(reconstructed, encoding="utf-8")
print(f"\n✅ Saved: {OUTPUT}")

# Sample preview
print("\n📋 SAMPLE — Chương 1 first paragraphs:")
for i, p in enumerate(in_paragraphs[2:8]):
    print(f"\n  [{i+1}] ({len(p)} chars):")
    print(f"  {p[:300]}{'...' if len(p) > 300 else ''}")
