#!/usr/bin/env python3
"""
Phase B7: PERFECT STRUCTURE — Semantic Paragraph Detection
- Gemini hiểu nội dung sâu để quyết định paragraph boundaries
- Focus: xuống hàng hợp lý, không vỡ ý
- Detect logic flow: ý kế tiếp / ý mới / liệt kê / định nghĩa
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
INPUT = WORKDIR / "clean-structured.txt"
OUTPUT = WORKDIR / "clean-perfect.txt"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

N_WORKERS = 5
CHUNK_SIZE = 5000

PROMPT_TPL = """Bạn là biên tập viên cao cấp đang chuẩn hóa cấu trúc bản đọc EPUB cho sách Phật học A-Tỳ-Đàm.

NHIỆM VỤ DUY NHẤT: Sắp xếp lại CẤU TRÚC XUỐNG HÀNG cho hợp lý và ngắt đoạn theo Ý NGHĨA NỘI DUNG.

⚠️ NGUYÊN TẮC VÀNG: HIỂU NGHĨA TRƯỚC KHI QUYẾT ĐỊNH XUỐNG HÀNG

📐 QUY TẮC NGẮT ĐOẠN (RULES):

**RULE 1: Một ý = một paragraph**
- Đọc câu, hiểu ý, gom các câu cùng phát triển 1 ý → 1 paragraph
- Khi ý nghĩa chuyển sang chủ đề mới → ngắt paragraph mới

**RULE 2: Heading + body liền nhau**
- `#### N. Term (pali)` thì body ngay phía dưới (không thêm dòng trống thừa)
- KHÔNG được tách body thành 2-3 paragraphs vụn vặt nếu chúng nói cùng 1 ý

**RULE 3: Definition pattern**
- "1. Thuật ngữ (pali): Định nghĩa..." → giữ làm 1 paragraph hoặc heading+body
- KHÔNG split definition thành mini-paragraphs

**RULE 4: List vs paragraph**
- Nếu thấy danh sách liên tiếp `1) item, 2) item, 3) item` → giữ làm list
- Nếu chỉ là enumeration trong câu văn → để inline trong paragraph
- Nếu 1 list có items dài → mỗi item là 1 paragraph riêng

**RULE 5: NOT-merge signals (ngắt đoạn mới)**
- Dấu chấm + chữ HOA đầu câu kế (`.` + `[A-Z]`) → POSSIBLE new paragraph
- Đại từ chuyển đối tượng (chúng ta → người, ngài → tôi) → new paragraph
- Chuyển không gian/thời gian (Trước hết → Sau đó → Cuối cùng) → new paragraph
- "Tóm lại", "Ví dụ:", "Chẳng hạn", "Nghĩa là" sau dấu chấm thường bắt đầu paragraph mới

**RULE 6: MERGE signals (gộp vào cùng paragraph)**
- Câu kế bắt đầu với chữ thường → CHẮC CHẮN merge
- Câu kế là tiếp vế của câu trước (ngoại tên Pali, ví dụ, định nghĩa) → merge
- Connectives: "tuy nhiên,", "bởi vì,", "do đó,", "vì vậy," → merge với câu trước

**RULE 7: Giữ NGUYÊN:**
- Tất cả `<table>...</table>` HTML
- Tất cả `# `, `## `, `### `, `#### ` markdown headings
- Tất cả `*pali*`, `<em>pali</em>` italic markup
- Tất cả `![Hình X](images/...)` image refs
- Tất cả Pali Latin terms trong ngoặc
- Tất cả numbered lists đã đúng format markdown
- Không thêm/bớt/đổi NỘI DUNG

**RULE 8: SPACING:**
- Giữa heading và body: 1 dòng trống
- Giữa paragraph và paragraph kế: 1 dòng trống
- Không tạo 3 dòng trống liền nhau

📝 KỸ THUẬT:
- Đọc kỹ semantically từng câu
- Câu A và câu B có cùng chủ ngữ? Cùng phát triển 1 ý? → CÙNG paragraph
- Câu A và câu B nói về object khác nhau? Mở topic mới? → KHÁC paragraph

OUTPUT: Markdown đã sắp xếp xuống hàng hợp lý, không thêm gì khác.

INPUT:
---
__TEXT__
---

OUTPUT:"""

_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def call_gemini(prompt, timeout=120):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
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
            
            result = re.sub(r'^```\w*\n?', '', result.strip())
            result = re.sub(r'\n?```\s*$', '', result)
            
            in_tok = usage.get("promptTokenCount", 0)
            out_tok = usage.get("candidatesTokenCount", 0)
            return idx, result, dt, in_tok, out_tok
        except Exception as e:
            err = str(e)[:200]
            safe_print(f"  [{idx}] ERR (try {retry+1}/3): {err[:120]}")
            time.sleep(5)
    
    safe_print(f"  [{idx}] FAILED, keeping original")
    return idx, chunk_text, 0, 0, 0


def split_smart(text, target_size=CHUNK_SIZE):
    """Split text smart at paragraph boundaries, preserving tables."""
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
        
        # At paragraph boundary, not in table, reached target
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

print("📖 Reading clean-structured.txt...")
text = INPUT.read_text(encoding="utf-8")
print(f"  Input: {len(text):,} chars")

chunks = split_smart(text)
print(f"  Chunks: {len(chunks)} (avg {len(text)//len(chunks):,} chars)")

print(f"\n🧠 Perfect Structure Detection ({N_WORKERS} workers)...")
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
            safe_print(f"  [{idx:2d}/{len(chunks)}] OK {dt:.1f}s ({completed}/{len(chunks)}, ETA={eta:.0f}s)")
        except Exception as e:
            i = futures[fut]
            safe_print(f"  [{i}] FATAL: {e}")
            results[i] = chunks[i]

merged = "\n".join(r if r else c for r, c in zip(results, chunks))

# Cleanup: collapse 3+ blank lines to 2
merged = re.sub(r'\n{4,}', '\n\n\n', merged)

OUTPUT.write_text(merged, encoding="utf-8")

elapsed = time.time() - t_start
cost = total_in_tok * 0.30 / 1_000_000 + total_out_tok * 2.50 / 1_000_000

print()
print(f"✅ Done in {elapsed:.0f}s")
print(f"📊 Tokens: in={total_in_tok:,}, out={total_out_tok:,}")
print(f"💰 Cost: ${cost:.4f}")
print(f"📦 Output: {OUTPUT} ({len(merged):,} chars)")
