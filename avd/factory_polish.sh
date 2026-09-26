#!/bin/sh
# factory_polish.sh — finish a factory film so that real players behave, and (optionally) make
# near-static AI scenes visibly move.
#
#   sh factory_polish.sh faststart IN OUT                 # remux only: moov to the front (+faststart)
#   sh factory_polish.sh motion    IN OUT [zoom] [ax] [ay]  # gentle pan/zoom so the picture never looks frozen
#   sh factory_polish.sh preview   IN OUT [height]          # small web preview, faststart, yuv420p
#   sh factory_polish.sh check     IN                       # container + stream facts
#
# Why: ffmpeg writes moov at the END by default. Streamed/browser players then show a still frame
# while the audio plays (they must fetch the whole file before they can seek the header). The
# original Meta AI clips are faststart; our outputs were not. Also: Meta AI's extended clips are
# near-static for seconds at a time, which reads as "frozen" even in a local player.
set -u
CMD="${1:?usage: factory_polish.sh faststart|motion|preview|check IN [OUT] [args]}"
IN="${2:?missing input}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING $1" >&2; exit 4; }; }
need ffmpeg; need ffprobe

case "$CMD" in
check)
  ffprobe -v error -show_entries stream=codec_name,profile,level,pix_fmt,avg_frame_rate,nb_frames,width,height \
          -show_entries format=duration,size -of default=nw=1 "$IN"
  if head -c 2000 "$IN" | grep -aq moov; then echo "faststart=YES (moov at front)"; else echo "faststart=NO (moov at end -> still-frame-while-audio-plays in browsers)"; fi
  ;;
faststart)
  OUT="${3:?missing output}"
  ffmpeg -hide_banner -loglevel error -y -i "$IN" -c copy -movflags +faststart "$OUT"
  echo "FASTSTART $IN -> $OUT ($(stat -c%s "$OUT") B)"
  ;;
motion)
  OUT="${3:?missing output}"; Z="${4:-1.06}"; AX="${5:-14}"; AY="${6:-10}"
  W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$IN" | tr -d '\r')
  H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$IN" | tr -d '\r')
  CW=$(awk -v w="$W" -v z="$Z" 'BEGIN{v=w/z; printf "%d", (v%2==0)?v:v-1}')
  CH=$(awk -v h="$H" -v z="$Z" 'BEGIN{v=h/z; printf "%d", (v%2==0)?v:v-1}')
  ffmpeg -hide_banner -loglevel error -y -i "$IN" \
    -vf "crop=${CW}:${CH}:x='(iw-ow)/2+${AX}*sin(2*PI*t/17)':y='(ih-oh)/2+${AY}*sin(2*PI*t/11)',scale=${W}:${H}:flags=bicubic,format=yuv420p" \
    -c:v libx264 -crf 20 -preset medium -profile:v high -level 4.0 -pix_fmt yuv420p \
    -c:a copy -movflags +faststart "$OUT"
  echo "MOTION $IN -> $OUT ($(stat -c%s "$OUT") B, zoom=${Z} pan=${AX}/${AY}px, faststart)"
  ;;
preview)
  OUT="${3:?missing output}"; PH="${4:-360}"
  ffmpeg -hide_banner -loglevel error -y -i "$IN" \
    -vf "scale=-2:${PH}:flags=bicubic,format=yuv420p" \
    -c:v libx264 -crf 30 -preset veryfast -profile:v high -level 4.0 -pix_fmt yuv420p \
    -c:a aac -b:a 96k -movflags +faststart "$OUT"
  echo "PREVIEW $IN -> $OUT ($(stat -c%s "$OUT") B)"
  ;;
*) echo "unknown command $CMD" >&2; exit 2 ;;
esac
