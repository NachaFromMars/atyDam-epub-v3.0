#!/usr/bin/env python3
"""
Phase B6: AI SMART STRUCTURE DETECTOR
- Send each chunk to Gemini with detailed structural analysis instructions
- Detect & fix:
  * Paragraph boundaries (merge broken lines, split inline numbered lists)
  * Numbering hierarchy (Chapter > I.II. > A.B. > 1.2. > a.b.)
  * Table boundaries (preserve existing HTML tables, detect missed ones)
  * Heading levels
- Output: well-structured markdown
"""
import re
import os
import json
import time
import urllib.request
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean-proofread.txt"
OUTPUT = WORKDIR / "clean-structured.txt"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

N_WORKERS = 5
CHUNK_SIZE = 4500  # smaller for higher quality analysis

PROMPT_TPL = """Bạn là chuyên gia chuyển đổi cấu trúc văn bản từ PDF sách Phật học A-Tỳ-Đàm sang Markdown.

NHIỆM VỤ: Phân tích và cấu trúc lại đoạn text dưới đây thành Markdown chuẩn EPUB.

CẤU TRÚC PHÂN CẤP CHUẨN (HIERARCHY) trong sách này:
- `# CHƯƠNG N` = chapter title (đã có sẵn)
- `## I. TITLE` = Roman numeral section (I., II., III., IV.)
- `### A. Title` = Letter subsection (A., B., C., D.)
- `#### 1. Title (pali)` = Numbered definition (1., 2., 3., ...)
- `- text` hoặc `a. text` = bullet/list item bên trong định nghĩa

QUY TẮC PHÂN TÍCH THÔNG MINH:

1. **NUMBERED LIST DETECTION** (ưu tiên cao):
   - Pattern "1)... 2)... 3)..." trong cùng paragraph → SPLIT thành numbered list:
     ```
     1) First item
     
     2) Second item
     
     3) Third item
     ```
   - Pattern "1. Item 2. Item 3. Item" inline → cũng split thành list
   - GIỮ NGUYÊN đánh số gốc (1, 2, 3...)

2. **PARAGRAPH MERGE & SPLIT**:
   - Nếu dòng kết thúc KHÔNG có dấu (. ! ? :) và dòng kế tiếp bắt đầu chữ thường → MERGE
   - Nếu dòng kết thúc bằng (. ! ?) và dòng kế tiếp bắt đầu chữ HOA → đó là paragraph mới
   - KHÔNG để paragraph chỉ có 1 từ hoặc 1 chữ (đó là noise, merge với paragraph kề)
   - Trang PDF có ~42 chars/line là physical line, KHÔNG phải paragraph

3. **HEADING DETECTION**:
   - "I. TÂM DỤC GIỚI" + tiếp theo body text dài → đó là H2
   - "A. SắcTứ Đại (Pali)" + body text → H3
   - "1. Xúc (phassa)" + body text liên tiếp → H4 + body
   - **KHÔNG bỏ heading** dù có short text sau

4. **PRESERVE HTML**:
   - `<table>...</table>`: GIỮ NGUYÊN 100%, không sửa
   - `<em>pali</em>`, `*pali*`: GIỮ NGUYÊN
   - `<br/>`, `&bull;`: giữ nguyên
   - `![Hình X-...](images/...)`: giữ nguyên
   - `**Bảng X- Title**`: giữ nguyên

5. **KHÔNG**:
   - Không thêm/bớt nội dung
   - Không paraphrase
   - Không cắt ngắn
   - Không thay đổi từ Pali
   - Không thay đổi <table>

OUTPUT: CHỈ markdown text đã cấu trúc lại, KHÔNG thêm giải thích, KHÔNG wrap trong code block.

INPUT TEXT:
---
__TEXT__
---

OUTPUT (markdown structured):"""

_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def call_gemini(prompt, timeout=120):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
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
    return text, data.get("usageMetadata", {})


def process_chunk(idx, chunk_text):
    prompt = PROMPT_TPL.replace("__TEXT__", chunk_text)
    in_len = len(chunk_text)
    
    for retry in range(3):
        try:
            t0 = time.time()
            result, usage = call_gemini(prompt)
            dt = time.time() - t0
            
            out_len = len(result)
            ratio = out_len / in_len if in_len > 0 else 1.0
            
            if ratio < 0.5:
                safe_print(f"  [{idx}] TRUNCATED retry {retry+1}/3: {in_len}→{out_len} ({ratio*100:.0f}%)")
                time.sleep(2)
                continue
            
            # Strip wrapper
            result = re.sub(r'^```\w*\n?', '', result.strip())
            result = re.sub(r'\n?```\s*$', '', result)
            
            in_tok = usage.get("promptTokenCount", 0)
            out_tok = usage.get("candidatesTokenCount", 0)
            return idx, result, dt, in_tok, out_tok
        except Exception as e:
            err = str(e)[:200]
            safe_print(f"  [{idx}] ERR (try {retry+1}/3): {err[:120]}")
            time.sleep(5)
    
    safe_print(f"  [{idx}] FAILED, returning original")
    return idx, chunk_text, 0, 0, 0


def split_smart(text, target_size=CHUNK_SIZE):
    """Split at paragraph boundary, preserving tables."""
    chunks = []
    current = []
    current_size = 0
    in_table = False
    
    lines = text.split("\n")
    for line in lines:
        if '<table' in line:
            in_table = True
        
        current.append(line)
        current_size += len(line) + 1
        
        if '</table>' in line:
            in_table = False
            continue
        
        if current_size >= target_size and not in_table and not line.strip():
            chunks.append("\n".join(current))
            current = []
            current_size = 0
    
    if current:
        chunks.append("\n".join(current))
    
    return chunks


# ===== MAIN =====
if not API_KEY:
    print("❌ GEMINI_API_KEY not set")
    exit(1)

print("📖 Reading clean-proofread.txt...")
text = INPUT.read_text(encoding="utf-8")
print(f"  Input: {len(text):,} chars")

chunks = split_smart(text)
print(f"  Chunks: {len(chunks)} (avg {len(text)//len(chunks):,} chars each)")

print(f"\n🧠 AI Structure Detection with {N_WORKERS} workers...")
print(f"  Estimated time: ~{len(chunks)*9/N_WORKERS:.0f}s")
print()

t_start = time.time()
results = [None] * len(chunks)
total_in_tok = 0
total_out_tok = 0

with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
    futures = {executor.submit(process_chunk, i, c): i for i, c in enumerate(chunks)}
    completed = 0
    for fut in as_completed(futures):
        try:
            idx, result, dt, in_tok, out_tok = fut.result()
            results[idx] = result
            total_in_tok += in_tok
            total_out_tok += out_tok
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed * 60 if elapsed > 0 else 0
            rem = len(chunks) - completed
            eta = rem / rate * 60 if rate > 0 else 0
            safe_print(f"  [{idx:2d}/{len(chunks)}] OK {dt:.1f}s tokens={in_tok}/{out_tok} ({completed}/{len(chunks)}, ETA={eta:.0f}s)")
        except Exception as e:
            i = futures[fut]
            safe_print(f"  [{i}] FATAL: {e}")
            results[i] = chunks[i]

merged = "\n".join(r if r else c for r, c in zip(results, chunks))
OUTPUT.write_text(merged, encoding="utf-8")

elapsed = time.time() - t_start
cost = total_in_tok * 0.30 / 1_000_000 + total_out_tok * 2.50 / 1_000_000

print()
print(f"✅ Done in {elapsed:.0f}s")
print(f"📊 Tokens: in={total_in_tok:,}, out={total_out_tok:,}")
print(f"💰 Cost: ${cost:.4f}")
print(f"📦 Output: {OUTPUT} ({len(merged):,} chars)")
