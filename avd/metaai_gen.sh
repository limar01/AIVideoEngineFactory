#!/bin/sh
# metaai_gen.sh "<prompt>" [timeout_s] — drive the Meta AI chat in Messenger:
# type prompt, send, wait for a NEW clip in the player cache, pull it, record metadata.
# usage: sh metaai_gen.sh "prompt text" [180]
D="/home/limar01/Android/Sdk/platform-tools/adb -s emulator-5554"
CACHE=/data/user/0/com.facebook.orca/files/ExoPlayerCacheDir/videocache
OUT=$HOME/factory/clips
MAN=$HOME/factory/manifest.jsonl
PROMPT="$1"
TMO=${2:-180}
mkdir -p "$OUT"

$D root >/dev/null 2>&1
sleep 2

# coordinates of the chat input + send (1080x2400 screen, measured in step64)
IN_X=519; IN_Y=2242
SEND_X=984; SEND_Y=2241

before=$($D shell "ls -t $CACHE/*/* 2>/dev/null | head -1" | tr -d '\r')
echo "baseline cache file: $before"

# type the prompt (adb input text: spaces must be %s)
ESC=$(printf '%s' "$PROMPT" | sed 's/ /%s/g')
$D shell input tap $IN_X $IN_Y
sleep 2
$D shell input text "$ESC"
sleep 1
$D shell input tap $SEND_X $SEND_Y
sent=$(date +%T)
echo "sent at $sent"

new="$before"
i=0
while [ $i -lt $((TMO / 5)) ]; do
  sleep 5
  i=$((i+1))
  new=$($D shell "ls -t $CACHE/*/* 2>/dev/null | head -1" | tr -d '\r')
  [ "$new" != "$before" ] && [ -n "$new" ] && break
  if [ $((i % 6)) -eq 0 ]; then
    echo "  ...${i}0% : $(avd text 2>/dev/null | tr '\n' ' ' | head -c 120)"
  fi
done
done_at=$(date +%T)
if [ -z "$new" ] || [ "$new" = "$before" ]; then
  echo "NO_NEW_CLIP within ${TMO}s (reply text below)"
  avd text 2>/dev/null | head -c 700
  exit 3
fi

echo "new clip: $new"
name=$($D shell "basename '$new'" | tr -d '\r')
LOCAL="$OUT/$name.mp4"
$D pull "$new" "$LOCAL" >/dev/null 2>&1
sz=$(stat -c%s "$LOCAL" 2>/dev/null)
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$LOCAL" 2>/dev/null)
wh=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name,nb_frames -of csv=p=0 "$LOCAL" 2>/dev/null)
aud=$(ffprobe -v error -select_streams a -show_entries stream=codec_name,channels -of csv=p=0 "$LOCAL" 2>/dev/null)
sha=$(sha256sum "$LOCAL" | cut -c1-16)
echo "pulled=$LOCAL bytes=$sz duration=$dur video=$wh audio=${aud:-none} sha=$sha"
printf '{"ts":"%s","prompt":"%s","sent":"%s","done":"%s","file":"%s","bytes":%s,"duration":%s,"video":"%s","audio":"%s","sha16":"%s"}\n' \
  "$(date -Is)" "$PROMPT" "$sent" "$done_at" "$(basename $LOCAL)" "${sz:-0}" "${dur:-0}" "$wh" "${aud:-none}" "$sha" >> "$MAN"
echo "manifest: $MAN"
