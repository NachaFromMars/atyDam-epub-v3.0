#!/usr/bin/env python3
"""
Phase A: Smart Extract
- Extract all images → images/
- Build chapter map (9 chapters, page boundaries)
- Detect TOC pages (skip)
- Detect Index section (separate handle)
- Detect blank pages (skip)
- Extract font metadata (for italic Pali markup later)
"""
import fitz
import re
import json
from pathlib import Path
from collections import defaultdict

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
PDF = '/root/.openclaw/media/inbound/Trie_t_Ho_c_A-Ty_-Đa_m_-_Dr._Mehm_Tin_Mon---4bcc8e1f-532a-4403-8418-6294c816bd18.pdf'
IMAGES_DIR = WORKDIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)
META_FILE = WORKDIR / "extract_meta.json"

doc = fitz.open(PDF)
N = len(doc)

meta = {
    "total_pages": N,
    "chapters": [],
    "toc_pages": [],
    "blank_pages": [],
    "index_start_page": None,
    "images": [],
    "italic_spans_per_page": {},
    "page_headers_blacklist": [],
}

# ===== 1. CHAPTERS — 9 chương thật =====
print("📖 Detecting chapters...")
chapter_starts = {}
for i in range(N):
    text = doc[i].get_text()
    # Pattern: standalone "CHƯƠNG X" line followed by chapter title
    m = re.search(r'\n\s*(CHƯƠNG\s+(\d+))\s*\n\s*([A-ZĐÂÊÔƠƯĨ][^\n]{5,60})', text)
    if m:
        ch_num = int(m.group(2))
        if ch_num not in chapter_starts:
            chapter_starts[ch_num] = (i + 1, m.group(3).strip())

for ch_num in sorted(chapter_starts.keys()):
    page, title = chapter_starts[ch_num]
    meta["chapters"].append({"num": ch_num, "page": page, "title": title})
print(f"  Found {len(meta['chapters'])} chapters")
for c in meta["chapters"]:
    print(f"    Ch.{c['num']} p.{c['page']}: {c['title']}")

# Calculate chapter end pages
for i, ch in enumerate(meta["chapters"]):
    if i + 1 < len(meta["chapters"]):
        ch["end_page"] = meta["chapters"][i+1]["page"] - 1
    else:
        ch["end_page"] = None  # Will be set later

# ===== 2. TOC PAGES =====
print("\n📚 Detecting TOC pages...")
for i in range(20):  # TOC always in first 20 pages
    text = doc[i].get_text()
    if "MỤC LỤC" in text.upper():
        meta["toc_pages"].append(i + 1)
    # TOC entries pattern: chapter/section ... page_num
    elif re.search(r'\.{5,}\s*\d+', text) and len(re.findall(r'\.{5,}\s*\d+', text)) > 3:
        meta["toc_pages"].append(i + 1)

print(f"  TOC pages: {meta['toc_pages']}")

# ===== 3. BLANK PAGES =====
print("\n⬜ Detecting blank pages...")
for i in range(N):
    text = doc[i].get_text().strip()
    if len(text) < 30:
        meta["blank_pages"].append(i + 1)
print(f"  Blank pages: {meta['blank_pages']}")

# ===== 4. INDEX START =====
print("\n📑 Detecting Index section...")
# Index thường ở cuối, có pattern alphabetical word + " · " + page
for i in range(N - 30, N):
    if i < 0: continue
    text = doc[i].get_text()
    # Heuristic: 5+ lines matching "Word · page"
    idx_matches = re.findall(r'[A-ZĐ][\wáàảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệiíìỉĩịóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵñṃṇṭḍḷāīū\s]+·\s+\d+', text)
    if len(idx_matches) >= 5:
        meta["index_start_page"] = i + 1
        print(f"  Index starts at page {i + 1}")
        break

# ===== 5. EXTRACT IMAGES =====
print("\n🖼️  Extracting images...")
img_count = 0
for page_idx in range(N):
    page = doc[page_idx]
    imgs = page.get_images(full=True)
    if not imgs:
        continue

    # Find "Hình X-" caption nearby
    page_text = page.get_text()
    captions = re.findall(r'(H[íi]nh\s+\d+[\-\.][\s\S]{5,100}?)(?:\n\s*\n|$)', page_text)

    for img_idx, img_info in enumerate(imgs):
        xref = img_info[0]
        try:
            # Get image rectangles (positions on page)
            rects = page.get_image_rects(xref)
            bbox = list(rects[0]) if rects else None

            # Get nearby text for context
            context_above = ""
            context_below = ""
            if bbox:
                r = fitz.Rect(bbox)
                above_rect = fitz.Rect(0, max(0, r.y0 - 50), page.rect.width, r.y0)
                below_rect = fitz.Rect(0, r.y1, page.rect.width, min(page.rect.height, r.y1 + 60))
                context_above = page.get_textbox(above_rect).strip()[:100]
                context_below = page.get_textbox(below_rect).strip()[:100]

            # Extract image
            img_data = doc.extract_image(xref)
            ext = img_data.get("ext", "png")
            img_bytes = img_data["image"]

            filename = f"fig_p{page_idx+1:03d}_{img_idx}.{ext}"
            out_path = IMAGES_DIR / filename
            out_path.write_bytes(img_bytes)

            # Match to caption if possible
            matched_caption = None
            for cap in captions:
                # Caption often appears below image
                if cap.strip() in context_below or any(cap.strip()[:30] in t for t in [context_below, context_above]):
                    matched_caption = cap.strip()[:120]
                    break
            if not matched_caption and captions:
                matched_caption = captions[0].strip()[:120]

            meta["images"].append({
                "page": page_idx + 1,
                "idx": img_idx,
                "file": filename,
                "size": len(img_bytes),
                "bbox": bbox,
                "caption": matched_caption,
                "context_above": context_above,
                "context_below": context_below,
            })
            img_count += 1
        except Exception as e:
            print(f"  Error img p.{page_idx+1} idx={img_idx}: {e}")

print(f"  Extracted {img_count} images to {IMAGES_DIR}/")

# ===== 6. ITALIC SPANS (Pali markers) =====
print("\n🪷 Mapping italic spans per page...")
for page_idx in range(N):
    page = doc[page_idx]
    italic_runs = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0: continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font", "")
                text = span.get("text", "").strip()
                if not text: continue
                if "Italic" in font or "Oblique" in font:
                    italic_runs.append(text)
    if italic_runs:
        meta["italic_spans_per_page"][str(page_idx + 1)] = italic_runs
print(f"  Pages with italic Pali: {len(meta['italic_spans_per_page'])}")

# ===== 7. BUILD HEADER/FOOTER BLACKLIST =====
print("\n🔁 Building running headers blacklist (lines repeating >5 times)...")
line_counter = defaultdict(int)
for i in range(N):
    text = doc[i].get_text()
    for line in text.split("\n"):
        line = line.strip()
        if 5 < len(line) < 100:
            line_counter[line] += 1

blacklist = []
for line, cnt in line_counter.items():
    if cnt >= 5:
        # Filter to suspected headers/footers
        if (re.match(r'^CHƯ[ƠỚ]NG\s+\d+', line) or
            re.match(r'^\s*\d+\s+[A-ZĐ]', line) or
            re.match(r'^[IVX]+\.\s+[A-Z]', line) or
            "HƯỚNG" in line or "TÂM PHÁP" in line):
            blacklist.append((line, cnt))

# Sort by count desc
blacklist.sort(key=lambda x: -x[1])
meta["page_headers_blacklist"] = [b[0] for b in blacklist[:100]]
print(f"  Blacklisted {len(meta['page_headers_blacklist'])} repeating lines")
for line, cnt in blacklist[:10]:
    print(f"    ×{cnt}: {line[:80]}")

# ===== 8. GENERATE COVER from page 1 =====
print("\n🎨 Generating cover image from page 1...")
page1 = doc[0]
mat = fitz.Matrix(2, 2)  # 2x scale for high res
pix = page1.get_pixmap(matrix=mat)
cover_path = WORKDIR / "cover.png"
pix.save(str(cover_path))
print(f"  Cover saved: {cover_path} ({pix.width}x{pix.height}, {cover_path.stat().st_size//1024} KB)")
meta["cover_file"] = "cover.png"

# Save metadata
META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
print(f"\n✅ Phase A done. Metadata: {META_FILE}")
print(f"\n📊 Summary:")
print(f"  Chapters: {len(meta['chapters'])}")
print(f"  Images: {len(meta['images'])}")
print(f"  TOC pages: {len(meta['toc_pages'])}")
print(f"  Blank pages: {len(meta['blank_pages'])}")
print(f"  Index starts: page {meta['index_start_page']}")
print(f"  Italic pages: {len(meta['italic_spans_per_page'])}")
print(f"  Headers blacklist: {len(meta['page_headers_blacklist'])} lines")
