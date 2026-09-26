#!/bin/sh
# metaai_gen2.sh v4 — drive Meta AI video generation/extend in Messenger (unattended, CLI-driven).
#
#   sh metaai_gen2.sh --send "<prompt>" [tmo]
#   sh metaai_gen2.sh --send-existing [tmo]        # composer already has the text (e.g. "extend it...")
#
# v4 changes vs v3: PRESSES PLAY to force the fetch (reels are never downloaded until played), taps
# Reload on playback errors, and keeps the capture rig off because reels cannot stream through mitm.
D="/home/limar01/Android/Sdk/platform-tools/adb -s emulator-5554"
CACHE=/data/user/0/com.facebook.orca/files/ExoPlayerCacheDir/videocache
NET_DIR="${AVD_NET_DIR:-$HOME/arenabridge/net}"
OUT="$HOME/factory/clips"; MAN="$HOME/factory/manifest.jsonl"
HERE=$(dirname "$(readlink -f "$0")")
mkdir -p "$OUT" "$HOME/factory"

MODE="$1"; PROMPT="$2"
case "$MODE" in
  --send)          TMO=${3:-300} ;;
  --send-existing) TMO=${2:-300} ;;
  *) echo "usage: $0 --send \"<prompt>\" [tmo] | --send-existing [tmo]"; exit 2 ;;
esac

dump()   { $D shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; $D shell cat /sdcard/ui.xml 2>/dev/null | tr '>' '\n'; }
tap_of() { set -- $(echo "$1" | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p')
           [ -z "$1" ] && return 1; $D shell input tap $(( ($1+$3)/2 )) $(( ($2+$4)/2 )); }
cache_list() { $D shell "ls $CACHE/*/* 2>/dev/null" | tr -d '\r' | sort; }

# 0. media will not stream through the capture rig
if [ "$($D shell settings get global http_proxy | tr -d '\r')" != "null" ]; then
  echo "[0] capture rig ON -> stopping it"; sh "$HERE/net_proxy.sh" stop 2>/dev/null || $D shell settings put global http_proxy :0 >/dev/null 2>&1; sleep 2
fi

# 1. typing
if [ "$MODE" = "--send" ]; then
  echo "[1] typing prompt"
  tap_of "$(dump | grep -m1 'Ask anything')" || { echo "composer not found"; exit 5; }
  sleep 2
  $D shell input text "$(printf '%s' "$PROMPT" | sed 's/ /%s/g')"
  sleep 2
fi

# 2. send via the UI tree ("Send" with text, "Send ✨" when empty)
echo "[2] sending"
ok=no; i=0
while [ $i -lt 4 ]; do
  i=$((i+1))
  tap_of "$(dump | grep -m1 'content-desc="Send')" || { sleep 2; continue; }
  sleep 4
  dump | grep -q 'text="Ask anything' && { ok=yes; break; }
  sleep 2
done
[ "$ok" = yes ] || echo "   WARN: composer did not clear"
sent_at=$(date +%T); echo "   sent at $sent_at"

# 3. wait for the clip; force playback when the app is being coy
base=$(cache_list)
echo "[3] waiting for the clip ($(printf '%s\n' "$base" | grep -c .) cached before)"
i=0; new=; lastplay=0
while [ $i -lt $((TMO / 8)) ]; do
  sleep 8; i=$((i+1)); el=$((i*8))
  $D shell input swipe 519 1500 519 1150 250 >/dev/null 2>&1
  new=$(printf '%s\n' "$(cache_list)" | grep -vxF "$base" | head -1)
  [ -n "$new" ] && break
  UI=$(dump)
  if echo "$UI" | grep -q 'text="Reload"'; then
    echo "   playback error -> Reload ($(date +%T))"; tap_of "$(echo "$UI" | grep -m1 'text="Reload"')"; continue
  fi
  # play-to-fetch: after 40s, and every 48s after that, press Play on the bottom-most bubble
  if [ $el -ge 40 ] && [ $((el - lastplay)) -ge 48 ]; then
    PB=$(echo "$UI" | grep 'content-desc="Play video"' | tail -1)
    if [ -n "$PB" ]; then echo "   pressing Play to force the fetch ($(date +%T))"; tap_of "$PB"; lastplay=$el; fi
  fi
  [ $((i % 5)) -eq 0 ] && echo "   ...${el}s"
done
if [ -z "$new" ]; then
  echo "NO_CLIP within ${TMO}s — last visible text:"; dump | grep -oE 'text="[^"]{8,}"' | tail -6; exit 3
fi

# 4. settle + verify + harvest
prev=-1; j=0
while [ $j -lt 10 ]; do
  s=$($D shell "stat -c%s '$new' 2>/dev/null" | tr -d '\r')
  [ -n "$s" ] && [ "$s" = "$prev" ] && break
  prev=$s; sleep 5; j=$((j+1))
done
name=$($D shell "basename '$new'" | tr -d '\r')
LOCAL="$OUT/$name.mp4"
$D pull "$new" "$LOCAL" >/dev/null 2>&1
sz=$(stat -c%s "$LOCAL" 2>/dev/null)
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$LOCAL" 2>/dev/null)
nbf=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames -of csv=p=0 "$LOCAL" 2>/dev/null)
rd=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$LOCAL" 2>/dev/null)
aud=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$LOCAL" 2>/dev/null)
errs=$(ffmpeg -v error -i "$LOCAL" -f null - 2>&1 | wc -l)
sha=$(sha256sum "$LOCAL" | cut -c1-16)
echo "[4] pulled=$(basename "$LOCAL") bytes=$sz dur=$dur video=$nbf read=$rd decode_errs=$errs audio=${aud:-none} sha16=$sha"
printf '{"ts":"%s","mode":"%s","prompt":"%s","sent":"%s","file":"%s","bytes":%s,"duration":%s,"video":"%s","read_frames":"%s","decode_errors":%s,"audio":"%s","sha16":"%s"}\n' \
  "$(date -Is)" "$MODE" "${PROMPT:-<existing composer text>}" "$sent_at" "$(basename "$LOCAL")" "${sz:-0}" "${dur:-0}" "$nbf" "$rd" "${errs:-0}" "${aud:-none}" "$sha" >> "$MAN"
echo "OK $LOCAL"
