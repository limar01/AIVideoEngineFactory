#!/bin/bash
# AI Video Factory — Live Demo Script
# Run: bash demo.sh
set -e

G="/home/limar01/Projects/workspace/project/ai_video_factory"
cd "$G"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
step() { echo -e "\n${CYAN}=== $1 ===${NC}"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; }

DIR=$(mktemp -d /tmp/aivf-demo-XXXXXX)
trap "rm -rf $DIR" EXIT

step "1. Initialize (run once per install)"
"$G/.venv/bin/python" -m app.ui.cli init 2>&1 | tail -1
log "Database + config created"

step "2. Generate Story"
"$G/.venv/bin/python" -m app.ui.cli pipeline generate-story \
  --topic "haunted doll" \
  --niche horror \
  --duration 300 \
  --output "$DIR/story.json" 2>&1 | grep -E "(Generating|generated|Output)"
log "Story + character bible + visual bible saved"

step "3. Compile Prompts for SnapGen"
"$G/.venv/bin/python" -m app.ui.cli pipeline compile-prompts \
  --story "$DIR/story.json" \
  --provider snapgen \
  --clip 8.0 \
  --output "$DIR/prompts.json" 2>&1 | grep -E "(Compiled|Output)"
log "15 provider-ready prompts compiled"

step "4. Run Full Pipeline (Mock provider — real ffmpeg videos)"
"$G/.venv/bin/python" -m app.ui.cli pipeline run-pipeline \
  --topic "haunted doll" \
  --niche horror \
  --duration 300 \
  --provider mock \
  --output-dir "$DIR/pipeline" \
  --clip 8.0 2>&1

step "5. Verify Output"
echo ""
echo -e "${CYAN}Final video:${NC}"
ls -lh "$DIR/pipeline/final/"*.mp4 2>/dev/null || true
echo ""
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 "$DIR/pipeline/final"/*.mp4 2>/dev/null | paste - - - - - - | \
  awk '{printf "  Duration: %6.1fs  |  Size: %7.0f KB  |  %s  |  %sx%s  |  %s fps\n", \
    $1/1000000, $2/1024, $6, $3, $4, $5}'

step "6. CLI Reference (what you can run yourself)"
echo ""
echo "  aivf init                                 # first-time setup"
echo "  aivf pipeline generate-story --topic TEXT # generate story JSON"
echo "  aivf pipeline compile-prompts --story F   # compile prompts"
echo "  aivf pipeline run-pipeline --topic TEXT   # full pipeline (mock)"
echo "  aivf pipeline run-pipeline --provider snapgen --topic TEXT  # real provider"
echo "  aivf pipeline login-snapgen               # open browser for Google login"
echo ""
echo -e "${GREEN}Demo complete — output in $DIR (cleaned up on exit)${NC}"
