#!/usr/bin/env python3
"""
Pipeline parallel V2 (REST API): PDF lỗi font → recovered chunks
Triết Học A-Tỳ-Đàm — Dr. Mehm Tin Mon

V2 FIXES:
- Dùng REST API trực tiếp (SDK 0.8.6 cũ không support thinkingConfig)
- thinkingBudget=0 → output không bị truncate (tested ratio 86%)
- maxOutputTokens=16384 safety net
- Validate truncation, auto-retry
- 5 workers song song (paid tier)
"""
import os
import json
import time
import sys
import threading
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
CHUNKS_DIR = WORKDIR / "chunks"
RECOVERED_DIR = WORKDIR / "recovered"
PROGRESS_FILE = WORKDIR / "progress.json"

CHUNKS_DIR.mkdir(exist_ok=True)
RECOVERED_DIR.mkdir(exist_ok=True)

MODEL_NAME = "gemini-2.5-flash"
N_WORKERS = 5
MAX_OUTPUT_TOKENS = 16384
MIN_OUTPUT_RATIO = 0.5

API_KEY = os.environ.get("GEMINI_API_KEY", "")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"

PROMPT_TPL = """Bạn là chuyên gia phục hồi văn bản tiếng Việt + Pali bị lỗi font encoding PDF.

Nguồn: Sách Phật pháp "Triết Học A-Tỳ-Đàm" (Buddha Abhidhamma) của Dr. Mehm Tin Mon, Tỳ-khưu Giác Nguyên dịch.

LỖI TRONG PDF (do font subset bị tách):
- Tiếng Việt: mất dấu mũ (â→a), dấu thanh điệu thay sai (sắc↔huyền↔hỏi↔ngã↔nặng), thừa space giữa từ
- Pali Latin: BỊ THÊM DẤU SẮC SAI và SPACE THỪA, ví dụ:
   • SAI: "pá kádá nápáriyá yá" → ĐÚNG: "pakadanapariyaya"
   • SAI: "ákusálákámmápáthá" → ĐÚNG: "akusalakammapatha"
   • SAI: "upá dá ru pá" → ĐÚNG: "upadarupa"
   • SAI: "máhá bhu tá" → ĐÚNG: "mahabhuta"
- CHƯỚNG → CHƯƠNG (lỗi font, không phải nghĩa "chướng ngại")

NHIỆM VỤ:
1. PHỤC HỒI tiếng Việt về chính tả ĐÚNG theo ngữ cảnh Abhidhamma
2. PHỤC HỒI Pali Latin về dạng chuẩn (bỏ dấu sắc sai, ghép từ liền lại, giữ diacritic Pali đúng: ā ī ū ṃ ṇ ṭ ḍ ñ)
3. Giữ nguyên cấu trúc, line breaks, ===PAGE_XX===, số La Mã, số thứ tự, dấu chấm chấm trong TOC
4. KHÔNG thêm/bớt nội dung, KHÔNG giải thích, KHÔNG cắt ngắn

⚠️ QUAN TRỌNG: Phải output ĐẦY ĐỦ TOÀN BỘ text đã sửa, không được dừng giữa chừng.

OUTPUT: CHỈ text đã sửa (đầy đủ), không thêm gì khác.

TEXT LỖI:
---
{text}
---

TEXT ĐÃ SỬA (đầy đủ):"""

_prog_lock = threading.Lock()
_print_lock = threading.Lock()


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "failed": [], "total": 0}


def save_progress(prog):
    PROGRESS_FILE.write_text(json.dumps(prog, indent=2))


def mark_done(i):
    with _prog_lock:
        prog = load_progress()
        if i not in prog["done"]:
            prog["done"].append(i)
            prog["done"].sort()
        if i in prog["failed"]:
            prog["failed"].remove(i)
        save_progress(prog)


def mark_failed(i):
    with _prog_lock:
        prog = load_progress()
        if i not in prog["failed"]:
            prog["failed"].append(i)
        save_progress(prog)


def remove_done(i):
    with _prog_lock:
        prog = load_progress()
        if i in prog["done"]:
            prog["done"].remove(i)
        save_progress(prog)


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


def call_gemini(prompt, timeout=120):
    """Call Gemini via REST API, returns (text, finish_reason, in_tokens, out_tokens)."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
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
    finish = cand.get("finishReason", "?")
    usage = data.get("usageMetadata", {})
    return text, finish, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)


def recover_chunk(i):
    """Recover single chunk."""
    chunk_file = CHUNKS_DIR / f"chunk_{i:04d}.txt"
    out_file = RECOVERED_DIR / f"chunk_{i:04d}.txt"

    text = chunk_file.read_text(encoding="utf-8")
    if not text.strip():
        out_file.write_text("", encoding="utf-8")
        mark_done(i)
        return (i, True, "empty chunk")

    in_len = len(text)
    prompt = PROMPT_TPL.format(text=text)

    for retry in range(5):
        try:
            t0 = time.time()
            recovered, finish, in_tok, out_tok = call_gemini(prompt)
            dt = time.time() - t0
            out_len = len(recovered)
            ratio = out_len / in_len if in_len > 0 else 1.0

            if finish == "MAX_TOKENS" or ratio < MIN_OUTPUT_RATIO:
                safe_print(
                    f"   [{i:3d}] TRUNCATED retry {retry+1}/5: "
                    f"{in_len}→{out_len} ({ratio*100:.0f}%, finish={finish}, out_tok={out_tok})"
                )
                time.sleep(2)
                continue

            out_file.write_text(recovered, encoding="utf-8")
            mark_done(i)
            return (i, True, f"{dt:.1f}s, {in_len}→{out_len} ({ratio*100:.0f}%, {out_tok}tok)")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            is_quota = e.code == 429
            wait = 30 if is_quota else 5
            safe_print(f"   [{i:3d}] HTTP {e.code} (try {retry+1}/5): {err_body[:120]}, wait {wait}s")
            time.sleep(wait)
        except Exception as e:
            err = str(e)[:200]
            safe_print(f"   [{i:3d}] ERR (try {retry+1}/5): {err[:120]}, wait 5s")
            time.sleep(5)

    mark_failed(i)
    return (i, False, "failed after 5 retries")


def main():
    if not API_KEY:
        print("❌ GEMINI_API_KEY not set")
        sys.exit(1)

    # Identify truncated chunks (need re-process)
    truncated = []
    for i in range(129):
        rec = RECOVERED_DIR / f"chunk_{i:04d}.txt"
        chunk = CHUNKS_DIR / f"chunk_{i:04d}.txt"
        if rec.exists() and chunk.exists():
            in_s = chunk.stat().st_size
            out_s = rec.stat().st_size
            if in_s > 100 and out_s / in_s < MIN_OUTPUT_RATIO:
                truncated.append(i)
                remove_done(i)

    prog = load_progress()
    total = prog.get("total", 129)
    done_set = set(prog["done"])
    todo = [i for i in range(total) if i not in done_set]

    safe_print(f"🧠 Pipeline parallel V2 REST (workers={N_WORKERS}, model={MODEL_NAME})")
    safe_print(f"   Total: {total}, Done: {len(done_set)}, Todo: {len(todo)}")
    if truncated:
        safe_print(f"   ⚠️  Re-processing {len(truncated)} truncated chunks")
    safe_print(f"   ETA ({N_WORKERS}-parallel, ~10s/chunk): {len(todo)*10/N_WORKERS/60:.1f} min")
    safe_print("")

    t_start = time.time()
    completed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = {executor.submit(recover_chunk, i): i for i in todo}

        for fut in as_completed(futures):
            i = futures[fut]
            try:
                idx, ok, info = fut.result()
                completed += 1
                if not ok:
                    failed += 1
                elapsed = time.time() - t_start
                rate = completed / elapsed * 60
                rem = len(todo) - completed
                eta_min = rem / rate if rate > 0 else 0
                status = "OK" if ok else "FAIL"
                safe_print(
                    f"   [{idx:3d}/{total}] {status} {info} "
                    f"({completed}/{len(todo)}, rate={rate:.1f}/min, ETA={eta_min:.1f}min)"
                )
            except Exception as e:
                safe_print(f"   [{i}] FATAL: {e}")
                failed += 1

    elapsed = time.time() - t_start
    safe_print(f"\n✅ Done in {elapsed/60:.1f} min. Completed: {completed-failed}, Failed: {failed}")
    final_prog = load_progress()
    safe_print(
        f"   Final: {len(final_prog['done'])}/{total} done, "
        f"{len(final_prog['failed'])} failed"
    )


if __name__ == "__main__":
    main()
