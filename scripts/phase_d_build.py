#!/usr/bin/env python3
"""
Phase D: Build EPUB Premium
- Cover image (rendered from PDF page 1)
- Premium CSS with Pali italic styling
- Embed all 31 images
- Validate with epubcheck
"""
import subprocess
import json
import shutil
from pathlib import Path

WORKDIR = Path("/root/.openclaw/workspace/atyDam-epub")
MD = WORKDIR / "atyDam-v2.md"
EPUB = WORKDIR / "TrietHoc-A-Ty-Dam-V2.epub"
CSS_FILE = WORKDIR / "style-v2-premium.css"
COVER = WORKDIR / "cover.png"
IMAGES_DIR = WORKDIR / "images"

# ===== Premium CSS =====
CSS = """@charset "UTF-8";

/* ===== Base typography ===== */
@namespace epub "http://www.idpf.org/2007/ops";

body {
  font-family: "Noto Serif", "Times New Roman", Georgia, serif;
  line-height: 1.75;
  margin: 0.8em;
  text-align: justify;
  color: #2C2C2C;
  hyphens: auto;
}

/* ===== Headings ===== */
h1 {
  font-size: 1.85em;
  color: #8B1A2F;
  text-align: center;
  page-break-before: always;
  border-bottom: 3px double #C9A96E;
  padding-bottom: 0.6em;
  margin: 2.5em 0 1.2em;
  font-weight: bold;
  letter-spacing: 0.02em;
}

h2 {
  font-size: 1.4em;
  color: #2C2C2C;
  border-left: 5px solid #C9A96E;
  padding-left: 0.7em;
  margin: 1.8em 0 0.9em;
  font-weight: bold;
}

h3 {
  font-size: 1.18em;
  color: #5a4a35;
  margin: 1.4em 0 0.7em;
  font-weight: bold;
}

h4 {
  font-size: 1.05em;
  color: #6b5340;
  margin: 1.2em 0 0.5em;
  font-weight: bold;
  font-style: italic;
}

/* ===== Body text ===== */
p {
  text-indent: 1.5em;
  margin: 0 0 0.4em;
  text-align: justify;
}

p.no-indent,
h1 + p, h2 + p, h3 + p, h4 + p {
  text-indent: 0;
}

/* ===== Pali terms ===== */
em.pali {
  font-style: italic;
  color: #6b5340;
  font-family: "Noto Sans", "Cambria", "Times New Roman", serif;
}

em {
  color: #5a4a35;
}

strong {
  color: #2C2C2C;
  font-weight: bold;
}

/* ===== Blockquotes ===== */
blockquote {
  border-left: 4px solid #C9A96E;
  padding: 0.6em 0 0.6em 1em;
  font-style: italic;
  color: #555;
  margin: 1em 0;
  background: #faf6f0;
  border-radius: 0 4px 4px 0;
}

/* ===== Lists ===== */
ul, ol {
  padding-left: 1.6em;
  margin: 0.5em 0 0.8em;
}

li {
  margin: 0.2em 0;
}

/* ===== Images ===== */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1.2em auto;
  border: 1px solid #e0d6c4;
  border-radius: 4px;
  padding: 4px;
  background: #fbf8f0;
}

/* Image caption (italic line after image) */
em:not(.pali) {
  display: block;
  text-align: center;
  font-size: 0.95em;
  color: #6b5340;
  margin: 0 auto 1.5em;
  font-style: italic;
  font-weight: normal;
}

/* ===== Table representation ===== */
table {
  border-collapse: collapse;
  margin: 1em auto;
  width: 100%;
}

th, td {
  border: 1px solid #C9A96E;
  padding: 0.4em 0.6em;
  text-align: left;
}

th {
  background: #faf6f0;
  font-weight: bold;
}

/* ===== Cover page ===== */
.title-page {
  text-align: center;
  margin-top: 25%;
}

.title-page h1 {
  border: none;
  font-size: 2.8em;
  color: #8B1A2F;
  padding-bottom: 0;
}

.subtitle {
  font-size: 1.15em;
  color: #6b5340;
  margin: 1em 0;
  font-style: italic;
}

.author {
  margin-top: 3em;
  font-style: italic;
  color: #5a4a35;
}

/* ===== Index ===== */
.index-section p {
  text-indent: 0;
  margin: 0.15em 0;
}

/* ===== Page breaks ===== */
.chapter {
  page-break-before: always;
}
"""

# CSS is already saved by hand-edited file; skip overwrite if file exists with newer content
if not CSS_FILE.exists():
    CSS_FILE.write_text(CSS, encoding="utf-8")
    print(f"✓ CSS written from template: {len(CSS)} chars")
else:
    print(f"✓ Using existing CSS: {CSS_FILE.stat().st_size} bytes")

# ===== Build EPUB with Pandoc =====
print("\n📦 Building EPUB...")

# Use markdown_strict + raw_html to avoid Pandoc's automatic list detection
# from "a.", "i.", "1)" patterns inside raw HTML tables
MD_FORMAT = "markdown-fancy_lists-startnum"
cmd = [
    "pandoc",
    "-f", MD_FORMAT,
    str(MD),
    "-o", str(EPUB),
    "--metadata", "title=Triết Học A-Tỳ-Đàm",
    "--metadata", "author=Dr. Mehm Tin Mon",
    "--metadata", "lang=vi",
    "--metadata", "description=Buddha Abhidhamma — Ultimate Science. Bản tiếng Việt do Tỳ-khưu Giác Nguyên dịch.",
    "--metadata", "publisher=NXB Hồng Đức",
    "--css", str(CSS_FILE),
    "--epub-cover-image", str(COVER),
    "--toc",
    "--toc-depth=3",
    "--split-level=1",
    "--resource-path", f".:{IMAGES_DIR}:..",
]

result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKDIR)
if result.returncode != 0:
    print(f"❌ ERROR: {result.stderr}")
    exit(1)
if result.stderr:
    print(f"  WARN: {result.stderr[:500]}")

epub_size = EPUB.stat().st_size
print(f"✓ EPUB built: {EPUB.name} ({epub_size:,} bytes = {epub_size//1024} KB)")

# ===== Validate =====
print("\n🔍 Validating EPUB...")
result = subprocess.run(
    ["java", "-jar", "/usr/share/java/epubcheck.jar", str(EPUB)],
    capture_output=True, text=True
)
print(result.stdout[-2000:])
if result.stderr:
    print("STDERR:", result.stderr[-500:])

print("\n🎉 Phase D done.")
