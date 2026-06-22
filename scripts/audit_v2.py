#!/usr/bin/env python3
"""
🔍 AUDIT V2 — Apply remaining AI suggestions + Deep iteration
- A: Apply variant capitalization + Pali style fixes
- B: Deep audit iteration 4-5 với chunks nhỏ hơn để Gemini focus
"""
import re
import os
import json
import time
import urllib.request
import urllib.error
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean-tables-vision.txt"
OUTPUT = WORKDIR / "clean-audited-v2.txt"
AUDIT_LOG = WORKDIR / "audit-log-v2.json"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

audit_log = {
    "timestamp": datetime.now().isoformat(),
    "phase_a_fixes": [],
    "phase_b_issues": [],
    "tokens_used": {"in": 0, "out": 0},
    "cost_usd": 0.0,
}

_lock = threading.Lock()
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
    usage = data.get("usageMetadata", {})
    with _lock:
        audit_log["tokens_used"]["in"] += usage.get("promptTokenCount", 0)
        audit_log["tokens_used"]["out"] += usage.get("candidatesTokenCount", 0)
    return text


# ============================================================
# PHASE A: Apply remaining AI suggestions
# ============================================================
def phase_a_apply_fixes(text):
    """Apply variant capitalization và Pali style fixes."""
    safe_print("\n📝 PHASE A: Apply AI suggestions...")
    
    # Phật học style: chỉ viết hoa thuật ngữ đứng độc lập, lowercase trong body
    # Em chỉ apply những cái em CHẮC CHẮN đúng (không thay variant capitalization
    # because variant capitalization may be intentional in Vietnamese Buddhist tradition)
    
    SAFE_PHASE_A_FIXES = {
        # Pali compound words (proper spacing)
        "uddhacakukkucca": "uddhacca-kukkucca",
        "anottappa": "anottappa",  # confirm correct
        "thīnamiddha": "thīna-middha",
        "Thīna-middha": "thīna-middha",
        "Thīnamiddha": "thīna-middha",
        
        # Common Vietnamese typos
        "lãng tháng": "lang thang",
        "tính trạng": "tình trạng",
        "hiện hiện": "hiện rõ",
        "cấu niệm": "câu niệm",
        "trộn 10 hướng": "trong 10 hướng",
        "vỏ ngoài của một gỗ mục": "vỏ ngoài của một khúc gỗ mục",
        "Cội tâm các là 6 vật": "Cội của các tâm là 6 vật",
        "Bỏ thêm chi Tứ hành giả": "Bỏ chi Tứ, hành giả",
        "2 tâm sanh": "2 tâm song sinh",
        
        # Subset font residuals
        "Bộá c": "Bộc",
        "Hộá i": "Hoài",
        "Tâ m ": "Tâm ",  # standalone with trailing space
        "Tá m ": "Tám ",
        "Bộá": "Bộ",
        "Hộá": "Hoà",
        "ấi": "ái",  # PALI artifact
        "đôi tươn": "đối tượn",
        
        # Numbers
        " ột tâm": " một tâm",
        " ột pháp": " một pháp",
    }
    
    count = 0
    for wrong, right in SAFE_PHASE_A_FIXES.items():
        n = text.count(wrong)
        if n > 0:
            text = text.replace(wrong, right)
            count += n
            audit_log["phase_a_fixes"].append({"wrong": wrong, "right": right, "count": n})
            safe_print(f"  '{wrong}' → '{right}': {n}x")
    
    safe_print(f"  Total Phase A fixes: {count}")
    return text


# ============================================================
# PHASE B: Deep AI audit với chunks nhỏ
# ============================================================
DEEP_AUDIT_PROMPT = """Bạn là biên tập viên SOÁT LỖI CUỐI CÙNG cho sách Phật học A-Tỳ-Đàm bản EPUB.

Tìm lỗi TINH TẾ trong đoạn text dưới đây.

LOẠI LỖI CẦN TÌM (chỉ những lỗi RÕ RÀNG là LỖI, không phải style choice):

1. **Chính tả tiếng Việt SAI rõ ràng:**
   - Dấu thanh điệu đặt sai vị trí (vd: "đối tươn" thay vì "đối tượn")
   - Dấu mũ thiếu hoặc thừa (vd: "Tâ m" có space, "Tỳ-khưu" → đúng)
   - Từ ghép sai (vd: "lãng tháng" → "lang thang")

2. **Thuật ngữ Phật học SAI:**
   - Pali viết liền/ngắt sai (vd: "uddhacakukkucca" → "uddhacca-kukkucca")
   - Diacritic Pali thiếu (vd: "samadhi" → "samādhi")

3. **Câu cụt / vô nghĩa:**
   - Câu thiếu chủ ngữ/vị ngữ rõ rệt
   - Đoạn không liên kết với context

4. **Footnote/page header LẠC vào body:**
   - Số trang trần (vd: "37 41 47") giữa text
   - Header chương lạc (vd: "TÂM PHÁP 39")

5. **Cấu trúc list/heading sai:**
   - Numbering bị nhảy (1, 2, 4, 5)
   - Heading level sai (#### thay vì ###)

⚠️ KHÔNG báo các trường hợp sau (KHÔNG phải lỗi):
- Capitalization variants (Phóng Dật vs Phóng dật — Phật học có truyền thống viết hoa)
- Word order trong dấu ngoặc
- Style choice của tác giả

OUTPUT FORMAT (1 lỗi/dòng, max 30 lỗi):
ISSUE: "<quote nguyên văn 80 chars>" | TYPE: <typo|pali|fragment|footer|structure> | FIX: "<sửa thành>"

Nếu không có lỗi: CLEAN

INPUT (chunk size nhỏ, đọc kỹ):
---
__TEXT__
---

ISSUES (max 30, chỉ lỗi RÕ RÀNG):"""


def deep_audit_chunk(idx, chunk_text):
    prompt = DEEP_AUDIT_PROMPT.replace("__TEXT__", chunk_text)
    for retry in range(3):
        try:
            result = call_gemini(prompt)
            issues = []
            for line in result.strip().split("\n"):
                if line.startswith("ISSUE:"):
                    issues.append(line.strip())
            return idx, issues
        except urllib.error.HTTPError as e:
            if e.code == 429:
                safe_print(f"  L{idx}: 429, sleep 20s")
                time.sleep(20)
            else:
                safe_print(f"  L{idx}: HTTP {e.code}")
                return idx, []
        except Exception as e:
            safe_print(f"  L{idx} err: {str(e)[:80]}")
            time.sleep(5)
    return idx, []


def phase_b_deep_audit(text):
    """Deep audit với chunks nhỏ 3000 chars + Gemini focus."""
    safe_print("\n🔬 PHASE B: Deep AI audit (chunks 3000 chars)...")
    
    # Split into smaller chunks for focused review
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
        if cur_size > 3000 and not in_table and not line.strip():
            chunks.append("\n".join(current))
            current = []
            cur_size = 0
    if current:
        chunks.append("\n".join(current))
    
    safe_print(f"  Scanning {len(chunks)} chunks (3K chars each)...")
    
    all_issues = []
    completed = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(deep_audit_chunk, i, c): i for i, c in enumerate(chunks)}
        for fut in as_completed(futures):
            idx, issues = fut.result()
            all_issues.extend([(idx, iss) for iss in issues])
            completed += 1
            if completed % 10 == 0:
                safe_print(f"  Progress: {completed}/{len(chunks)} chunks")
    
    safe_print(f"  Total deep issues found: {len(all_issues)}")
    return all_issues


def phase_b_auto_apply(text, issues):
    """Auto-apply confident fixes from deep audit."""
    safe_print("\n🛠️  Auto-applying confident fixes...")
    
    # Parse "ISSUE: ..." | "FIX: ..." patterns
    fixes_applied = 0
    fix_log = []
    
    for chunk_idx, issue in issues:
        # Parse fix
        m = re.search(r'ISSUE:\s*"([^"]+)"\s*\|\s*TYPE:\s*(\w+)\s*\|\s*FIX:\s*"([^"]+)"', issue)
        if not m:
            continue
        
        wrong = m.group(1).strip()
        issue_type = m.group(2).strip()
        right = m.group(3).strip()
        
        # Only auto-apply for clear typos + Pali fixes
        if issue_type not in ('typo', 'pali'):
            continue
        
        # Skip if wrong/right are too similar (likely capitalization)
        if wrong.lower() == right.lower():
            continue
        
        # Skip if either is too short or too long
        if len(wrong) < 4 or len(wrong) > 80 or len(right) < 2 or len(right) > 100:
            continue
        
        # Apply if found in text
        if wrong in text:
            text = text.replace(wrong, right)
            fixes_applied += 1
            fix_log.append({"wrong": wrong, "right": right, "type": issue_type})
            if fixes_applied <= 20:
                safe_print(f"  '{wrong[:60]}' → '{right[:60]}'")
    
    safe_print(f"  Total Phase B auto-fixes: {fixes_applied}")
    audit_log["phase_b_issues"] = fix_log
    return text


# ============================================================
# MAIN
# ============================================================
def main():
    if not API_KEY:
        print("❌ No API key")
        return
    
    text = INPUT.read_text(encoding="utf-8")
    
    # Phase A: Apply remaining AI suggestions
    text = phase_a_apply_fixes(text)
    
    # Phase B: Deep audit + auto-apply
    issues = phase_b_deep_audit(text)
    text = phase_b_auto_apply(text, issues)
    
    # Save
    OUTPUT.write_text(text, encoding="utf-8")
    
    # Cost
    in_tok = audit_log["tokens_used"]["in"]
    out_tok = audit_log["tokens_used"]["out"]
    cost = in_tok * 0.30 / 1_000_000 + out_tok * 2.50 / 1_000_000
    audit_log["cost_usd"] = round(cost, 4)
    
    AUDIT_LOG.write_text(json.dumps(audit_log, ensure_ascii=False, indent=2))
    
    print(f"\n{'='*60}")
    print(f"📊 AUDIT V2 COMPLETE")
    print(f"  Phase A fixes: {len(audit_log['phase_a_fixes'])}")
    print(f"  Phase B issues found: {len(issues)}")
    print(f"  Phase B fixes applied: {len(audit_log['phase_b_issues'])}")
    print(f"  Tokens: in={in_tok:,}, out={out_tok:,}")
    print(f"  Cost: ${cost:.4f}")
    print(f"  Output: {OUTPUT}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
