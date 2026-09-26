#!/bin/sh
# factory_stitch.sh — build LONG videos out of short Meta AI clips, entirely offline (ffmpeg only).
#
#   sh factory_stitch.sh out.mp4 clip1.mp4 clip2.mp4 ...        # concat in order
#   TARGET=60 sh factory_stitch.sh out.mp4 clips/*.mp4          # repeat the sequence until >= TARGET s
#   FPS=24 W=624 H=624 sh factory_stitch.sh out.mp4 ...         # override normalisation
#
# Steps: normalise every clip (same size/fps/SAR + AAC stereo; silent track added when a clip has
# no audio) -> optionally repeat to hit TARGET -> concat -> verify with ffprobe.
# Pure POSIX sh + ffmpeg/ffprobe/awk: no network, no python, no pip, no bc.
set -e
[ $# -ge 2 ] || { echo "usage: $0 out.mp4 clip1.mp4 [clip2.mp4 ...]"; exit 2; }
OUT="$1"; shift
TARGET="${TARGET:-0}"      # 0 = just concat what is given
FPS="${FPS:-24}"
W="${W:-624}"; H="${H:-624}"
MAXREP="${MAXREP:-200}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
LIST="$TMP/list.txt"

dur_of() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" | awk '{printf "%.3f", $1}'; }
has_audio() { ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$1" | grep -q .; }

i=0
for f in "$@"; do
  [ -f "$f" ] || { echo "skip missing: $f" >&2; continue; }
  i=$((i+1)); n=$(printf '%03d' "$i")
  VF="scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=${FPS},setsar=1,format=yuv420p"
  if has_audio "$f"; then
    ffmpeg -v error -y -i "$f" -vf "$VF" -c:v libx264 -preset veryfast -crf 20 \
           -c:a aac -ar 44100 -ac 2 -movflags +faststart "$TMP/$n.mp4"
  else
    ffmpeg -v error -y -i "$f" -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
           -map 0:v:0 -map 1:a:0 -vf "$VF" -c:v libx264 -preset veryfast -crf 20 \
           -c:a aac -ar 44100 -ac 2 -shortest "$TMP/$n.mp4"
  fi
  echo "  clip $n  $(dur_of "$TMP/$n.mp4")s  $(basename "$f")"
done
[ -f "$TMP/001.mp4" ] || { echo "no usable input clips" >&2; exit 3; }

per=$( { for f in "$TMP"/[0-9][0-9][0-9].mp4; do dur_of "$f"; echo; done; } | awk '{s+=$1} END{printf "%.3f", s+0}' )

: > "$LIST"
if [ "$TARGET" = "0" ]; then
  reps=1
else
  reps=$(awk -v t="$TARGET" -v p="$per" 'BEGIN{ if (p<=0) {print 1} else { r=int(t/p)+1; if (r<1) r=1; print r } }')
  [ "$reps" -gt "$MAXREP" ] && reps="$MAXREP"
  echo "sequence=${per}s  target=${TARGET}s  repeats=$reps"
fi
r=1; while [ $r -le $reps ]; do
  for f in "$TMP"/[0-9][0-9][0-9].mp4; do echo "file '$f'" >> "$LIST"; done
  r=$((r+1))
done

ffmpeg -v error -y -f concat -safe 0 -i "$LIST" -c copy -movflags +faststart "$OUT"
DUR=$(dur_of "$OUT"); SZ=$(stat -c%s "$OUT")
V=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,avg_frame_rate -of csv=p=0 "$OUT")
A=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,channels,sample_rate -of csv=p=0 "$OUT")
echo "OUT $OUT bytes=$SZ duration=${DUR}s video=$V audio=${A:-none}"
