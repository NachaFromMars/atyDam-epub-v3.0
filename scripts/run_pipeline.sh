#!/usr/bin/env bash
# atyDam-epub v2.0 — One-command PDF→EPUB pipeline
#
# Usage:
#   ./run_pipeline.sh <PDF_PATH> [BOOK_NAME]
#
# Required env:
#   GEMINI_API_KEY — Paid tier Gemini 2.5 Flash API key
#
# Output:
#   <workspace>/<book-name>-epub/TrietHoc-<book-name>-V10.epub

set -e

PDF_PATH="${1:?Usage: run_pipeline.sh <PDF_PATH> [BOOK_NAME]}"
BOOK_NAME="${2:-$(basename "$PDF_PATH" .pdf | tr -dc '[:alnum:]-')}"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/root/.openclaw/workspace}"
WORKDIR="$WORKSPACE_ROOT/${BOOK_NAME}-epub"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==============================================="
echo "📚 atyDam-epub v2.0 — PDF→EPUB Pipeline"
echo "==============================================="
echo "📄 Input PDF:  $PDF_PATH"
echo "📁 Workdir:    $WORKDIR"
echo "🔑 API key:    ${GEMINI_API_KEY:0:10}..."
echo "==============================================="

if [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ GEMINI_API_KEY env var required (paid tier)"
    exit 1
fi

if [ ! -f "$PDF_PATH" ]; then
    echo "❌ PDF not found: $PDF_PATH"
    exit 1
fi

# Setup workspace
mkdir -p "$WORKDIR"/{chunks,recovered,images}
cd "$WORKDIR"

# Copy scripts + CSS
cp "$SCRIPT_DIR"/*.py .
cp "$SCRIPT_DIR"/style-v2-premium.css .

# Update PDF path in scripts
PDF_ESC=$(echo "$PDF_PATH" | sed 's|/|\\/|g')
for f in phase_a_extract.py phase_b9_tables_vision.py pipeline_parallel.py; do
    if [ -f "$f" ]; then
        sed -i "s|PDF_PATH = .*|PDF_PATH = \"$PDF_PATH\"|" "$f"
        sed -i "s|PDF = .*\"$|PDF = \"$PDF_PATH\"|" "$f"
    fi
done

# Phase A: Smart Extract
echo ""
echo "🔧 Phase A: EXTRACT (images, chapters, TOC)..."
python3 phase_a_extract.py

# Phase 1: Recovery (parallel, paid tier)
echo ""
echo "🧠 Phase 1: RECOVERY (Gemini 2.5 Flash, paid)..."
python3 pipeline_parallel.py

# Phase B2: Paragraph reconstruction
echo ""
echo "📝 Phase B2: PARAGRAPH RECONSTRUCT..."
python3 phase_b2_paragraphs.py

# Phase B3: Inline list split
echo ""
echo "📋 Phase B3: SMART LIST SPLIT..."
python3 phase_b3_smart_list.py

# Phase B6: AI structure detection
echo ""
echo "🧠 Phase B6: AI STRUCTURE..."
python3 phase_b6_smart_structure.py

# Phase B7: Perfect paragraph structure
echo ""
echo "✨ Phase B7: PERFECT STRUCTURE..."
python3 phase_b7_perfect_structure.py

# Phase B9: Table Vision
echo ""
echo "👁️  Phase B9: TABLE VISION (Gemini Vision)..."
python3 phase_b9_tables_vision.py

# Phase B5: Proofreading
echo ""
echo "🔤 Phase B5: PROOFREADING..."
python3 phase_b5_proofread.py

# Phase C-D: Markup + Build
echo ""
echo "🛠️  Phase C-D: MARKUP + BUILD..."
python3 phase_c_markup.py
python3 phase_d_build.py

# Audit Loop (closed)
echo ""
echo "🔍 AUDIT LOOP V1 (7 layers)..."
python3 audit_loop.py

# Audit V2 (deep)
echo ""
echo "🔬 AUDIT V2 (deep AI)..."
python3 audit_v2.py

# Final rebuild from audited text
echo ""
echo "🎨 FINAL BUILD..."
# Update Phase C to use audited file
sed -i 's|clean-perfect.txt|clean-audited-v2.txt|' phase_c_markup.py
python3 phase_c_markup.py
python3 phase_d_build.py

# Find final EPUB
FINAL_EPUB=$(ls *.epub | grep -v V1 | tail -1)

# Validate
echo ""
echo "✅ VALIDATING..."
java -jar /usr/share/java/epubcheck.jar "$FINAL_EPUB"

# Summary
echo ""
echo "==============================================="
echo "🎉 PIPELINE COMPLETE"
echo "==============================================="
echo "📦 Output: $WORKDIR/$FINAL_EPUB"
echo "📊 Size: $(du -h "$FINAL_EPUB" | cut -f1)"
echo ""
echo "💰 Cost breakdown saved in audit-log*.json"
echo "==============================================="
