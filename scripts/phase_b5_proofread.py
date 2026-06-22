#!/usr/bin/env python3
"""
Phase B5: Comprehensive Proofreading with Gemini
- Split text thành chunks vừa phải (~4-5K chars)
- Gemini proofread: fix typos, Phật học terms, paragraph structure
- Preserve markdown structure (headings, lists, tables, italic Pali)
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
INPUT = WORKDIR / "clean-paragraphs3.txt"
OUTPUT = WORKDIR / "clean-proofread.txt"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

N_WORKERS = 5
CHUNK_SIZE = 5000  # chars per chunk

PROMPT_TPL = """Bạn là chuyên gia hiệu đính sách Phật học A-Tỳ-Đàm bản tiếng Việt.

NHIỆM VỤ: Sửa lỗi chính tả tiếng Việt và thuật ngữ Phật học trong đoạn text dưới đây.

QUY TẮC NGHIÊM NGẶT:
1. PHẢI giữ NGUYÊN tất cả markdown structure: `# `, `## `, `### `, `#### `, `**text**`, `*text*`, `1. `, `<table>`, `<tr>`, `<td>`, `<em>`, `<br/>`, etc.
2. PHẢI giữ NGUYÊN tất cả từ Pali Latin trong ngoặc (như `(citta)`, `(cetasika)`, `(akusalacetasika)`)
3. CHỈ sửa lỗi chính tả tiếng Việt và lỗi nhận dạng thuật ngữ Phật học sai
4. KHÔNG thay đổi nội dung, KHÔNG paraphrase, KHÔNG thêm/bớt ý
5. KHÔNG cắt ngắn, KHÔNG tóm tắt

CÁC LỖI THƯỜNG GẶP CẦN SỬA:
- Thuật ngữ Phật học sai (Hộn → Hôn, Hối → Hoài, Tinh → Tịnh, Khái → Khai, Đoạn → Đoán, ...)
- Dấu thanh sai (sắc/huyền/hỏi/ngã/nặng)
- Dấu mũ sai (â/ă/ô/ơ/ê)
- Từ bị tách giữa: "tâm sở" "tâm thức" "sát-na"
- Lỗi đánh máy nhẹ

OUTPUT: CHỈ trả về đoạn text đã sửa, KHÔNG thêm giải thích, KHÔNG markdown code block wrapper.

TEXT GỐC:
---
__TEXT__
---

TEXT ĐÃ SỬA:"""

_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def call_gemini(prompt, timeout=90):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
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
    return text, data.get("usageMetadata", {})


def proofread_chunk(idx, chunk_text):
    """Send 1 chunk to Gemini for proofreading."""
    prompt = PROMPT_TPL.replace("__TEXT__", chunk_text)
    for retry in range(3):
        try:
            t0 = time.time()
            result, usage = call_gemini(prompt)
            dt = time.time() - t0
            
            # Validate: must not be much shorter (>50% loss means truncation)
            in_len = len(chunk_text)
            out_len = len(result)
            ratio = out_len / in_len if in_len > 0 else 1.0
            
            if ratio < 0.5:
                safe_print(f"  [{idx}] TRUNCATED retry {retry+1}/3: {in_len}→{out_len} ({ratio*100:.0f}%)")
                time.sleep(2)
                continue
            
            # Strip wrapper if any
            result = re.sub(r'^```\w*\n?', '', result.strip())
            result = re.sub(r'\n?```\s*$', '', result)
            
            in_tok = usage.get("promptTokenCount", 0)
            out_tok = usage.get("candidatesTokenCount", 0)
            return idx, result, dt, in_tok, out_tok
        except Exception as e:
            err = str(e)[:200]
            safe_print(f"  [{idx}] ERR (try {retry+1}/3): {err[:120]}")
            time.sleep(5)
    
    # Fallback: return original
    safe_print(f"  [{idx}] FAILED, returning original")
    return idx, chunk_text, 0, 0, 0


def split_by_paragraphs(text, target_size=CHUNK_SIZE):
    """Split text into chunks at paragraph boundaries, respecting tables (don't split inside <table>)."""
    chunks = []
    current = []
    current_size = 0
    in_table = False
    
    lines = text.split("\n")
    for line in lines:
        # Track table boundaries
        if '<table' in line:
            in_table = True
        if '</table>' in line:
            in_table = False
            current.append(line)
            continue
        
        current.append(line)
        current_size += len(line) + 1
        
        # If reached target size and not in table and at paragraph boundary
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

print("📖 Reading clean-paragraphs3.txt...")
text = INPUT.read_text(encoding="utf-8")
print(f"  Input: {len(text):,} chars")

chunks = split_by_paragraphs(text)
print(f"  Chunks: {len(chunks)} (avg {len(text)//len(chunks):,} chars each)")

print(f"\n🧠 Proofreading with {N_WORKERS} workers, gemini-2.5-flash paid...")
print(f"  Estimated time: ~{len(chunks)*8/N_WORKERS:.0f}s")
print()

t_start = time.time()
results = [None] * len(chunks)
total_in_tok = 0
total_out_tok = 0

with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
    futures = {executor.submit(proofread_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
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
            safe_print(f"  [{idx:2d}/{len(chunks)}] OK {dt:.1f}s, in={in_tok}tok out={out_tok}tok ({completed}/{len(chunks)}, ETA={eta:.0f}s)")
        except Exception as e:
            i = futures[fut]
            safe_print(f"  [{i}] FATAL: {e}")
            results[i] = chunks[i]  # fallback

# Reassemble
merged = "\n".join(r if r else c for r, c in zip(results, chunks))
OUTPUT.write_text(merged, encoding="utf-8")

elapsed = time.time() - t_start
# Cost estimate (Gemini 2.5 Flash paid tier)
cost = total_in_tok * 0.30 / 1_000_000 + total_out_tok * 2.50 / 1_000_000

print()
print(f"✅ Done in {elapsed:.0f}s")
print(f"📊 Total tokens: in={total_in_tok:,}, out={total_out_tok:,}")
print(f"💰 Cost: ${cost:.4f}")
print(f"📦 Output: {OUTPUT} ({len(merged):,} chars, change: {len(merged)-len(text):+d})")
