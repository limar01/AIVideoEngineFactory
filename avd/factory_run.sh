#!/bin/sh
# factory_run.sh — batch-generate Meta AI clips in Messenger, stitch them into one long video, and
# (optionally) narrate it with the offline audio engine.
#
#   sh factory_run.sh prompts.txt [OUT.mp4] [TARGET_SECONDS] [NARRATION.txt]
#
# prompts.txt   : one prompt per line (# starts a comment, blank lines ignored)
# OUT.mp4       : default $HOME/factory/out/factory_<timestamp>.mp4
# TARGET        : if given, the stitched sequence repeats until >= TARGET seconds
# NARRATION.txt : if given, its text is spoken by audio_engine.sh and muxed into the film
#
# Needs only: adb + the emulator + Messenger logged into Meta AI + ffmpeg (+ espeak-ng for narration).
# Nothing is downloaded, no pip/python packages are used — safe for a host whose sandbox has no internet.
set -u
PROMPTS="${1:?usage: factory_run.sh prompts.txt [out.mp4] [target_s] [narration.txt]}"
OUT="${2:-$HOME/factory/out/factory_$(date +%H%M%S).mp4}"
TARGET="${3:-0}"
NARRATION="${4:-}"
HERE=$(dirname "$(readlink -f "$0")")
CLIPS="$HOME/factory/clips"
mkdir -p "$CLIPS" "$(dirname "$OUT")"

[ -f "$PROMPTS" ] || { echo "no prompt file: $PROMPTS" >&2; exit 2; }
n=$(grep -cve '^[[:space:]]*#' -e '^[[:space:]]*$' "$PROMPTS")
echo "== factory_run: $n prompt(s) -> $OUT (target=${TARGET}s) $(date +%T)"
i=0
: > /tmp/factory_list.txt
while IFS= read -r line; do
  case "$line" in ''|\#*) continue;; esac
  i=$((i+1))
  echo "-- [$i/$n] $line"
  before=$(ls -t "$CLIPS" 2>/dev/null | head -1)
  sh "$HERE/metaai_gen2.sh" --send "$line" 300 || echo "   (generation failed for prompt $i — continuing)"
  after=$(ls -t "$CLIPS" 2>/dev/null | head -1)
  if [ -n "$after" ] && [ "$after" != "$before" ]; then
    echo "   clip: $CLIPS/$after"
    echo "$CLIPS/$after" >> /tmp/factory_list.txt
  fi
  sleep 8            # be gentle with rate limits between generations
done < "$PROMPTS"

[ -s /tmp/factory_list.txt ] || { echo "no clips were produced" >&2; exit 3; }
echo "== stitching $(wc -l < /tmp/factory_list.txt) clip(s)"
if [ "$TARGET" = "0" ]; then
  sh "$HERE/factory_stitch.sh" "$OUT" $(cat /tmp/factory_list.txt)
else
  TARGET="$TARGET" sh "$HERE/factory_stitch.sh" "$OUT" $(cat /tmp/factory_list.txt)
fi

# optional motion polish: near-static AI scenes look "frozen"; MOTION=1 pans/zooms them gently
if [ "${MOTION:-0}" = "1" ] && [ -f "$HERE/factory_polish.sh" ]; then
  echo "== motion polish"
  sh "$HERE/factory_polish.sh" motion "$OUT" "${OUT%.mp4}_motion.mp4" && OUT="${OUT%.mp4}_motion.mp4"
fi

if [ -n "$NARRATION" ] && [ -f "$NARRATION" ]; then
  echo "== audio stage (AI audio engine)"
  VOICE="${OUT%.mp4}_voice.wav"; BED="${OUT%.mp4}_bed.wav"; MIXED="${OUT%.mp4}_mix.wav"
  DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" | awk '{printf "%d", $1+1}')
  sh "$HERE/audio_engine.sh" tts "$(cat "$NARRATION")" "$VOICE" || echo "   (tts failed — film stays silent)"
  if [ -f "$VOICE" ]; then
    sh "$HERE/audio_engine.sh" bed "$BED" "$DUR" room
    ffmpeg -hide_banner -loglevel error -y -i "$BED" -i "$VOICE" \
      -filter_complex "[1:a]adelay=1200|1200[v];[0:a][v]amix=inputs=2:duration=first:normalize=0[a]" \
      -map "[a]" -ac 2 "$MIXED"
    sh "$HERE/audio_engine.sh" mux "$OUT" "$MIXED" "${OUT%.mp4}_narrated.mp4" replace
    echo "== narrated: ${OUT%.mp4}_narrated.mp4"
  fi
fi
# a film that is not faststart shows a still frame while the audio plays in browsers/streamed players
ensure_faststart() {
  f="$1"; [ -f "$f" ] || return 0
  if head -c 2000 "$f" | grep -aq moov; then
    echo "   faststart OK: $(basename "$f")"
  elif [ -f "$HERE/factory_polish.sh" ]; then
    echo "   moov at end -> remuxing $(basename "$f")"
    mv "$f" "$f.pre" && sh "$HERE/factory_polish.sh" faststart "$f.pre" "$f" && rm -f "$f.pre"
  else
    echo "   WARN: $(basename "$f") is not faststart (moov at end) - browsers may show a still frame"
  fi
}
ensure_faststart "$OUT"
ensure_faststart "${OUT%.mp4}_narrated.mp4"
echo "== done: $OUT"
