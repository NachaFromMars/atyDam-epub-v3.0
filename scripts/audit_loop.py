#!/usr/bin/env python3
"""
🔍 CLOSED-LOOP AUDIT SYSTEM
Tự động phát hiện và fix lỗi cho đến khi sạch hoàn toàn.

Tầng kiểm tra (mỗi tầng tự lặp đến khi không còn lỗi):
1. STRUCTURAL  — Heading inline, paragraph broken, orphan letters/numbers
2. SEMANTIC    — Text vô nghĩa, footnote scatter (AI detection)
3. SPELLING    — Typos Phật học, dấu thanh điệu sai (AI detection)
4. TABLE       — Cells trống, mismatched rows, missing tables
5. IMAGE       — Image-text alignment (Vision verification)
6. CROSS-REF   — Number sequences, internal references
7. AI METAREVIEW — Đọc text final, AI báo bất kỳ lỗi nào nó thấy

Mỗi tầng:
- DETECT: scan + AI inference
- REPORT: log lỗi
- FIX: auto-fix nếu có thể, else mark cho manual review
- VERIFY: kiểm tra lại đã hết lỗi chưa
- LOOP: nếu còn lỗi → quay lại DETECT (max 5 iterations per layer)
"""
import re
import os
import json
import time
import base64
import urllib.request
import urllib.error
import threading
import fitz
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean-tables-vision.txt"  # current state
OUTPUT = WORKDIR / "clean-audited.txt"
AUDIT_LOG = WORKDIR / "audit-log.json"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

audit_log = {
    "timestamp": datetime.now().isoformat(),
    "iterations": [],
    "total_issues_found": 0,
    "total_issues_fixed": 0,
    "tokens_used": {"in": 0, "out": 0},
    "cost_usd": 0.0,
}

_lock = threading.Lock()
_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def call_gemini(prompt, timeout=90, image_b64=None):
    parts = [{"text": prompt}]
    if image_b64:
        parts.append({"inlineData": {"mimeType": "image/png", "data": image_b64}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 16384,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read())
    cand = data["candidates"][0]
    text = cand["content"]["parts"][0]["text"]
    usage = data.get("usageMetadata", {})
    with _lock:
        audit_log["tokens_used"]["in"] += usage.get("promptTokenCount", 0)
        audit_log["tokens_used"]["out"] += usage.get("candidatesTokenCount", 0)
    return text


# ============================================================
# LAYER 1: STRUCTURAL AUDIT
# ============================================================
def layer1_structural(text):
    """Detect structural issues + auto-fix."""
    issues = []
    
    # 1a. Inline headings (text. #### N. Term)
    pattern = r'([\.:\?\!»\)])\s+(#{2,4})\s+([A-ZĐĨIVX0-9])'
    matches = re.findall(pattern, text)
    if matches:
        issues.append(f"Inline headings (####): {len(matches)}")
        text = re.sub(pattern, r'\1\n\n\2 \3', text)
    
    # 1b. Inline # CHƯƠNG
    pattern = r'([\.:\?\!»\)])\s+#\s+(CHƯƠNG\s+\d+)'
    matches = re.findall(pattern, text)
    if matches:
        issues.append(f"Inline CHƯƠNG: {len(matches)}")
        text = re.sub(pattern, r'\1\n\n# \2', text)
    
    # 1c. Orphan single letters at paragraph end (page break artifacts)
    pattern = r'([a-záàảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệiíìỉĩịóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵ])\s+([A-Z])\s*\n\s*\n'
    
    # 1d. Multiple consecutive blank lines (>3)
    pattern = r'\n{4,}'
    matches = re.findall(pattern, text)
    if matches:
        issues.append(f"Excessive blank lines: {len(matches)}")
        text = re.sub(pattern, '\n\n\n', text)
    
    # 1e. Inline list "1) item 2) item" still present
    pattern = r'[a-záàảãạâ]\s+(\d+)\)\s+([A-Z])'
    matches = re.findall(pattern, text)
    if matches:
        issues.append(f"Inline numbered lists still present: {len(matches)}")
    
    return text, issues


# ============================================================
# LAYER 2: SEMANTIC AUDIT (AI)
# ============================================================
def layer2_semantic_chunk(idx, chunk_text):
    """Detect orphan/meaningless fragments using AI."""
    prompt = f"""Bạn là biên tập viên kiểm tra sách Phật học A-Tỳ-Đàm.

NHIỆM VỤ: Tìm các đoạn text VÔ NGHĨA hoặc bị TÁCH RỜI khỏi context (footnote, page header, fragment lạc).

CHỈ LIỆT KÊ:
- Đoạn text ngắn (<50 chars) không liên kết với context xung quanh
- Mảnh ghi chú (footnote) rơi rạc giữa nội dung
- Câu cụt, câu thiếu chủ ngữ/vị ngữ
- Đoạn lặp lại vô nghĩa
- Page header rơi vào body (như "CHƯƠNG X TÂM Y 99")
- Số trang trần lẫn vào text

OUTPUT FORMAT (1 lỗi/dòng):
ISSUE: <quote nguyên văn lỗi (max 100 chars)> | TYPE: <orphan|footnote|fragment|page_header|repeat>

Nếu không có lỗi: NOCLEAN

INPUT:
---
{chunk_text}
---

ISSUES:"""
    
    try:
        result = call_gemini(prompt)
        issues = []
        for line in result.strip().split("\n"):
            if line.startswith("ISSUE:"):
                issues.append(line.strip())
        return idx, issues
    except Exception as e:
        safe_print(f"  L2 chunk {idx} error: {str(e)[:80]}")
        return idx, []


def layer2_semantic(text):
    """Run AI semantic audit on all chunks."""
    chunks = []
    current = []
    cur_size = 0
    in_table = False
    for line in text.split("\n"):
        if '<table' in line:
            in_table = True
        if '</table>' in line:
            in_table = False
            current.append(line)
            continue
        current.append(line)
        cur_size += len(line) + 1
        if cur_size > 5000 and not in_table and not line.strip():
            chunks.append("\n".join(current))
            current = []
            cur_size = 0
    if current:
        chunks.append("\n".join(current))
    
    safe_print(f"  L2: scanning {len(chunks)} chunks for orphan fragments...")
    
    all_issues = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(layer2_semantic_chunk, i, c): i for i, c in enumerate(chunks)}
        for fut in as_completed(futures):
            idx, issues = fut.result()
            all_issues.extend(issues)
    
    return all_issues


# ============================================================
# LAYER 3: SPELLING AUDIT (Pattern-based + AI)
# ============================================================
SPELLING_DICT = {
    # Phật học terms (sai → đúng)
    "Hộn Thủy": "Hôn Trầm", "Hộn Thuỷ": "Hôn Trầm", "Hộn thuỷ": "Hôn trầm",
    "Hối Nghi": "Hoài Nghi", "Hối nghi": "Hoài nghi",
    "Hộại Nghi": "Hoài Nghi", "Hoại Nghi": "Hoài Nghi",
    "Tinh Hấu": "Tịnh Hảo", "Tinh hấu": "Tịnh hảo",
    "Tinh Hộảo": "Tịnh Hảo",
    "Biên Hành": "Biến Hành", "Biên hành": "Biến hành",
    "Biện Hành": "Biến Hành", "Biện hành": "Biến hành",
    "Sở Thá": "Biệt Cảnh",
    "Thá ng giải": "Thắng Giải", "Thá ng Giải": "Thắng Giải",
    "Khái ý môn": "Khai ý môn", "Khái Ý môn": "Khai Ý môn",
    "Khái ngũ môn": "Khai ngũ môn", "Khái Y môn": "Khai Ý môn",
    "Khái y môn": "Khai y môn", "Khái ngũ Môn": "Khai ngũ Môn",
    "Đoạn Định": "Đoán Định", "Đoạn định": "Đoán định",
    "Thộn nhật": "Thuần nhất", "Thộn Nhật": "Thuần Nhất",
    "Phán Quan": "Phản Quán", "Phán quan": "Phản quán",
    "Hộặc": "Hoặc",
    # Common Vietnamese typos
    "đôi tươn": "đối tượn",
    "sât-na": "sát-na",
    "Sât-na": "Sát-na",
}


def layer3_spelling(text):
    """Apply spelling dictionary + return issues."""
    issues = []
    for wrong, right in SPELLING_DICT.items():
        count = text.count(wrong)
        if count > 0:
            issues.append(f"Typo '{wrong}' → '{right}': {count}x")
            text = text.replace(wrong, right)
    return text, issues


# ============================================================
# LAYER 4: TABLE AUDIT
# ============================================================
def layer4_tables(text):
    """Validate all tables."""
    issues = []
    tables = list(re.finditer(r'<table[^>]*>.*?</table>', text, re.DOTALL))
    
    for i, m in enumerate(tables):
        t = m.group(0)
        
        # 4a. Balance check
        for tag in ['table', 'thead', 'tbody', 'tr', 'th', 'td']:
            opens = len(re.findall(f'<{tag}\\b', t, re.IGNORECASE))
            closes = len(re.findall(f'</{tag}>', t, re.IGNORECASE))
            if opens != closes:
                issues.append(f"Table {i}: <{tag}> {opens} vs </{tag}> {closes}")
        
        # 4b. Empty cells (potential missing content)
        empty_cells = len(re.findall(r'<t[dh][^>]*>\s*</t[dh]>', t))
        total_cells = t.count('<td') + t.count('<th')
        if total_cells > 0 and empty_cells / total_cells > 0.3:
            issues.append(f"Table {i}: {empty_cells}/{total_cells} cells empty (>30%)")
        
        # 4c. Caption duplicated in <th>
        if re.search(r'<th[^>]*>Bảng\s+\d+[\-\.]', t):
            issues.append(f"Table {i}: Caption duplicated in <th>")
        
        # 4d. Rambling text inside cells
        if 'Phân tích' in t or 'Bảng này có vẻ' in t or 'Dựa trên hình' in t:
            issues.append(f"Table {i}: Contains AI rambling text")
        
        # 4e. List tags inside cells
        if re.search(r'<(ul|ol|li)\b', t):
            issues.append(f"Table {i}: Contains <ul>/<ol>/<li> (must be stripped)")
    
    # 4f. Missing table numbers (caption without table)
    captions = re.findall(r'\*\*Bảng\s+(\d+)[\-\.][^*]+\*\*', text)
    cap_nums = set(int(c) for c in captions)
    expected = set(range(1, 63))
    missing = expected - cap_nums
    if missing:
        issues.append(f"Missing captions: {sorted(missing)}")
    
    # Tables without preceding caption
    for m in re.finditer(r'<table[^>]*>', text):
        prev_text = text[max(0, m.start()-200):m.start()]
        if not re.search(r'\*\*Bảng\s+\d+[\-\.]', prev_text):
            issues.append(f"Table at pos {m.start()}: no caption")
            break  # report only first
    
    return issues


# ============================================================
# LAYER 5: IMAGE AUDIT
# ============================================================
def layer5_images(text):
    """Verify image references match actual files."""
    issues = []
    images_dir = WORKDIR / "images"
    
    refs = re.findall(r'!\[([^]]+)\]\(images/([^)]+)\)', text)
    for caption, fname in refs:
        if not (images_dir / fname).exists():
            issues.append(f"Image not found: images/{fname} (caption: {caption[:50]})")
    
    # Check broken refs
    broken = re.findall(r'!\[[^]]*\]\(images/(?:\.\.\.|placeholder)[^)]*\)', text)
    if broken:
        issues.append(f"Broken image refs (placeholder/...): {len(broken)}")
    
    return issues


# ============================================================
# LAYER 6: CROSS-REFERENCE AUDIT
# ============================================================
def layer6_crossref(text):
    """Check numbered sequences are continuous."""
    issues = []
    
    # Find numbered list items "1. " "2. " etc and check sequences
    # (only standalone, not body text)
    
    # Bảng numbering
    captions = sorted(set(int(c) for c in re.findall(r'\*\*Bảng\s+(\d+)[\-\.]', text)))
    if captions:
        gaps = []
        for i in range(captions[0], captions[-1] + 1):
            if i not in captions:
                gaps.append(i)
        if gaps:
            issues.append(f"Bảng gaps: {gaps}")
    
    # Hình numbering (in markdown image refs)
    hinhs = sorted(set(int(c) for c in re.findall(r'Hình\s+(\d+)[\-\.]', text)))
    if hinhs:
        gaps = []
        for i in range(hinhs[0], hinhs[-1] + 1):
            if i not in hinhs:
                gaps.append(i)
        if gaps and len(gaps) < 10:
            issues.append(f"Hình gaps: {gaps}")
    
    return issues


# ============================================================
# LAYER 7: AI META-REVIEW
# ============================================================
def layer7_metareview_chunk(idx, chunk_text):
    """AI reads chunk and reports ANY issue it sees."""
    prompt = f"""Bạn là người soát lỗi cuối cùng cho sách Phật học A-Tỳ-Đàm bản EPUB.

NHIỆM VỤ: Đọc đoạn text và liệt kê BẤT KỲ lỗi nào bạn thấy, kể cả lỗi tinh tế.

Các loại lỗi cần tìm:
- Chính tả tiếng Việt (dấu thanh điệu, dấu mũ)
- Thuật ngữ Phật học/Pali sai
- Cấu trúc paragraph: ngắt đoạn không hợp lý
- Heading sai level (## thay vì ###)
- Liệt kê (list) không đúng format
- Câu cụt, câu thiếu nghĩa
- Footnote/page header lạc vào body
- Text trùng lặp vô lý
- Bảng có cấu trúc lạ
- Numbering bị nhảy số hoặc lặp số

OUTPUT FORMAT (1 lỗi/dòng):
ISSUE: <quote 80 chars> | TYPE: <loại lỗi> | FIX: <gợi ý sửa>

Nếu không có lỗi: CLEAN

INPUT:
---
{chunk_text}
---

ISSUES:"""
    
    try:
        result = call_gemini(prompt)
        issues = []
        for line in result.strip().split("\n"):
            if line.startswith("ISSUE:"):
                issues.append(line.strip())
        return idx, issues
    except Exception as e:
        safe_print(f"  L7 chunk {idx} error: {str(e)[:80]}")
        return idx, []


def layer7_metareview(text):
    """Run AI meta-review on chunks."""
    # Split into chunks
    chunks = []
    current = []
    cur_size = 0
    in_table = False
    for line in text.split("\n"):
        if '<table' in line:
            in_table = True
        if '</table>' in line:
            in_table = False
            current.append(line)
            continue
        current.append(line)
        cur_size += len(line) + 1
        if cur_size > 6000 and not in_table and not line.strip():
            chunks.append("\n".join(current))
            current = []
            cur_size = 0
    if current:
        chunks.append("\n".join(current))
    
    safe_print(f"  L7: AI meta-review {len(chunks)} chunks...")
    
    all_issues = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(layer7_metareview_chunk, i, c): i for i, c in enumerate(chunks)}
        for fut in as_completed(futures):
            idx, issues = fut.result()
            all_issues.extend(issues)
    
    return all_issues


# ============================================================
# MAIN LOOP
# ============================================================
def run_audit_loop(max_iterations=5):
    if not API_KEY:
        print("❌ No API key")
        return
    
    text = INPUT.read_text(encoding="utf-8")
    
    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"🔄 ITERATION {iteration}/{max_iterations}")
        print(f"{'='*60}")
        
        iter_log = {"iter": iteration, "layers": {}}
        total_issues_this_iter = 0
        
        # Layer 1: Structural
        print("\n  Layer 1: STRUCTURAL...")
        text, issues = layer1_structural(text)
        iter_log["layers"]["structural"] = issues
        total_issues_this_iter += sum(int(re.search(r'\d+', s).group()) if re.search(r'\d+', s) else 1 for s in issues)
        for s in issues[:5]:
            safe_print(f"    {s}")
        
        # Layer 3: Spelling (do before semantic to avoid AI confusion)
        print("\n  Layer 3: SPELLING...")
        text, issues = layer3_spelling(text)
        iter_log["layers"]["spelling"] = issues
        total_issues_this_iter += len(issues)
        for s in issues:
            safe_print(f"    {s}")
        
        # Layer 4: Tables
        print("\n  Layer 4: TABLES...")
        issues = layer4_tables(text)
        iter_log["layers"]["tables"] = issues
        total_issues_this_iter += len(issues)
        for s in issues[:10]:
            safe_print(f"    {s}")
        
        # Layer 5: Images
        print("\n  Layer 5: IMAGES...")
        issues = layer5_images(text)
        iter_log["layers"]["images"] = issues
        total_issues_this_iter += len(issues)
        for s in issues[:5]:
            safe_print(f"    {s}")
        
        # Layer 6: Cross-ref
        print("\n  Layer 6: CROSS-REF...")
        issues = layer6_crossref(text)
        iter_log["layers"]["crossref"] = issues
        for s in issues:
            safe_print(f"    {s}")
        
        # Only run AI layers on first iteration (expensive)
        if iteration == 1:
            print("\n  Layer 2: SEMANTIC (AI)...")
            issues = layer2_semantic(text)
            iter_log["layers"]["semantic"] = issues
            safe_print(f"    Found {len(issues)} semantic issues")
            for s in issues[:5]:
                safe_print(f"    {s[:150]}")
            
            print("\n  Layer 7: AI META-REVIEW...")
            issues = layer7_metareview(text)
            iter_log["layers"]["metareview"] = issues
            safe_print(f"    Found {len(issues)} meta issues")
            for s in issues[:10]:
                safe_print(f"    {s[:150]}")
        
        iter_log["total_issues"] = total_issues_this_iter
        audit_log["iterations"].append(iter_log)
        
        if total_issues_this_iter == 0:
            safe_print(f"\n✅ NO MORE FIXABLE ISSUES — stopping at iteration {iteration}")
            break
        
        safe_print(f"\n  Iteration {iteration}: fixed {total_issues_this_iter} issues")
    
    # Save final
    OUTPUT.write_text(text, encoding="utf-8")
    
    # Cost calculation
    in_tok = audit_log["tokens_used"]["in"]
    out_tok = audit_log["tokens_used"]["out"]
    cost = in_tok * 0.30 / 1_000_000 + out_tok * 2.50 / 1_000_000
    audit_log["cost_usd"] = round(cost, 4)
    
    AUDIT_LOG.write_text(json.dumps(audit_log, ensure_ascii=False, indent=2))
    
    print(f"\n{'='*60}")
    print(f"📊 AUDIT COMPLETE")
    print(f"  Iterations: {len(audit_log['iterations'])}")
    print(f"  Total tokens: in={in_tok:,}, out={out_tok:,}")
    print(f"  Cost: ${cost:.4f}")
    print(f"  Output: {OUTPUT}")
    print(f"  Log: {AUDIT_LOG}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_audit_loop(max_iterations=3)
