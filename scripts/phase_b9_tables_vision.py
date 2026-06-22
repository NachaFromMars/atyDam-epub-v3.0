#!/usr/bin/env python3
"""
Phase B9: Table Reconstruction with GEMINI VISION
- Use book_page to render PDF page as image
- Send image + caption to Gemini Vision
- Gemini sees actual table layout → reconstruct HTML accurately
"""
import re
import os
import json
import time
import base64
import urllib.request
import threading
import fitz
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
INPUT = WORKDIR / "clean-perfect.txt"  # use V4 source (clean-perfect from Phase B7)
OUTPUT = WORKDIR / "clean-tables-vision.txt"
PDF = "/root/.openclaw/media/inbound/Trie_t_Ho_c_A-Ty_-Đa_m_-_Dr._Mehm_Tin_Mon---4bcc8e1f-532a-4403-8418-6294c816bd18.pdf"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
N_WORKERS = 5

# Book page → PDF page offset (front matter is ~19 pages)
PAGE_OFFSET = 19

doc = fitz.open(PDF)
meta = json.load(open(WORKDIR / "extract_meta.json"))
tables_with_pages = meta.get("tables_with_pages", {})

PROMPT_TPL = """Phân tích bảng (table) trong trang sách A-Tỳ-Đàm này.

CAPTION: __CAPTION__

NHIỆM VỤ:
1. Nhìn HÌNH ẢNH trang sách
2. Tìm bảng có caption "__CAPTION__" (có thể bị méo do font subset PDF)
3. Phân tích cấu trúc grid: rows, columns, headers, merged cells
4. Xuất HTML <table> chính xác như bảng trong hình

QUY TẮC NGHIÊM NGẶT:
- Header row dùng <th>, data rows dùng <td>
- Dùng rowspan/colspan nếu cell bị merge
- Giữ NGUYÊN từ Pali Latin (dùng <em>...</em> nếu cần italic)
- Tiếng Việt phải có dấu đúng (vì PDF bị méo font, dựa vào ngữ cảnh A-Tỳ-Đàm để sửa)
- KHÔNG dùng <caption>, <ul>, <ol>, <li> trong <td>
- KHÔNG dùng inline style hay class
- Output CHỈ HTML table (từ <table> đến </table>)

HTML TABLE:"""


def render_pdf_page_to_b64(pdf_page_idx, scale=2.0):
    """Render PDF page to base64 PNG."""
    page = doc[pdf_page_idx]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")


def call_gemini_vision(prompt, image_b64, timeout=90):
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "image/png", "data": image_b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
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


def clean_html(html):
    html = re.sub(r'^```\w*\n?', '', html.strip())
    html = re.sub(r'\n?```\s*$', '', html)
    html = re.sub(r'<caption[^>]*>[^<]*</caption>\s*', '', html)
    # No nested lists in cells
    html = re.sub(r'<(ul|ol)[^>]*>', '', html)
    html = re.sub(r'</(ul|ol)>', '', html)
    html = re.sub(r'<li[^>]*>\s*', '• ', html)
    html = re.sub(r'</li>\s*', '<br/>', html)
    # Self-closing
    html = re.sub(r'<br\s*>', '<br/>', html)
    # Balance check
    if '<table' not in html or '</table>' not in html:
        return None
    for tag in ['table', 'thead', 'tbody', 'tr', 'th', 'td']:
        opens = len(re.findall(f'<{tag}\\b', html, re.IGNORECASE))
        closes = len(re.findall(f'</{tag}>', html, re.IGNORECASE))
        if opens != closes:
            return None
    return html


_lock = threading.Lock()


def process_table(num, caption, book_page):
    pdf_page = book_page + PAGE_OFFSET - 1  # convert to 0-based PDF index
    # Try pdf_page and pdf_page+1 (table may span pages)
    
    for offset in [0, 1, -1, 2]:
        try_page = pdf_page + offset
        if try_page < 0 or try_page >= len(doc):
            continue
        try:
            img_b64 = render_pdf_page_to_b64(try_page, scale=2.0)
            prompt = PROMPT_TPL.replace("__CAPTION__", caption)
            
            for retry in range(2):
                try:
                    result, usage = call_gemini_vision(prompt, img_b64)
                    validated = clean_html(result)
                    if validated:
                        with _lock:
                            print(f"  Bảng {num}: ✓ (page {try_page+1}, {len(validated)} chars)", flush=True)
                        return num, validated, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
                except Exception as e:
                    print(f"    Bảng {num} retry {retry+1}: {str(e)[:80]}")
                    time.sleep(3)
        except Exception as e:
            print(f"  Bảng {num} page error: {e}")
    
    with _lock:
        print(f"  Bảng {num}: ✗ failed", flush=True)
    return num, None, 0, 0


# ===== MAIN =====
if not API_KEY:
    print("❌ No API key")
    exit(1)

print("📖 Reading clean-perfect.txt...")
text = INPUT.read_text(encoding="utf-8")

# Find tables to rebuild
to_rebuild = []
for m in re.finditer(r'(\*\*Bảng\s+(\d+)-[^*]+\*\*\s*\n+<table[^>]*>.*?</table>)', text, re.DOTALL):
    num = int(m.group(2))
    cap_m = re.search(r'\*\*(Bảng\s+\d+-[^*]+)\*\*', m.group(1))
    if cap_m and str(num) in tables_with_pages:
        book_page = tables_with_pages[str(num)]["book_page"]
        to_rebuild.append((num, cap_m.group(1).strip(), book_page, m.start(), m.end()))

print(f"Tables to rebuild with Vision: {len(to_rebuild)}\n")

t_start = time.time()
results = {}
total_in_tok = 0
total_out_tok = 0


def runner(args):
    num, caption, book_page, _, _ = args
    return process_table(num, caption, book_page)


with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
    futures = {executor.submit(runner, args): args for args in to_rebuild}
    for fut in as_completed(futures):
        try:
            num, html, in_tok, out_tok = fut.result()
            if html:
                results[num] = html
            total_in_tok += in_tok
            total_out_tok += out_tok
        except Exception as e:
            args = futures[fut]
            print(f"FATAL Bảng {args[0]}: {e}")

# Apply replacements
new_text = text
for num, caption, _, start, end in sorted(to_rebuild, key=lambda x: -x[3]):
    new_html = results.get(num)
    if new_html:
        new_text = new_text[:start] + f"**{caption}**\n\n{new_html}" + new_text[end:]

OUTPUT.write_text(new_text, encoding="utf-8")

elapsed = time.time() - t_start
cost = total_in_tok * 0.30 / 1_000_000 + total_out_tok * 2.50 / 1_000_000

print()
print(f"✅ Done in {elapsed:.0f}s")
print(f"Rebuilt: {len(results)}/{len(to_rebuild)}")
print(f"Tokens: in={total_in_tok:,}, out={total_out_tok:,}")
print(f"💰 Cost: ${cost:.4f}")
print(f"📦 Output: {OUTPUT}")
