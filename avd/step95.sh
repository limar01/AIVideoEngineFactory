#!/bin/sh
# step95 — harvest the step92 multi-shot batch, stitch a multi-shot film, narrate it, publish a preview.
# Runs on the rig (PC). Detached; log: ~/arenabridge/net/step95.log
D=/home/limar01/Android/Sdk/platform-tools/adb
F=$HOME/factory; N=$HOME/arenabridge/net; AVD=$HOME/Projects/workspace/project/avd
exec >>$N/step95.log 2>&1
echo "=== step95 $(date +%T) multi-shot assembly ==="

# 1. locate each shot's harvested clip (metaai_gen2.sh v4 prints "OK <path>")
: > $N/batch_clips.txt
for k in shot1 shot2 shot3 shot1_repeat shot4; do
  p=$(grep -m1 '^OK ' /tmp/g_$k.out 2>/dev/null | awk '{print $2}')
  echo "$k -> ${p:-MISSING}"
  [ -n "$p" ] && [ -f "$p" ] && echo "$k $p" >> $N/batch_clips.txt
done
echo "--- determinism: shot1 vs shot1_repeat"
a=$(awk '$1=="shot1"{print $2}' $N/batch_clips.txt)
b=$(awk '$1=="shot1_repeat"{print $2}' $N/batch_clips.txt)
if [ -n "$a" ] && [ -n "$b" ]; then
  sa=$(sha256sum "$a" | cut -c1-16); sb=$(sha256sum "$b" | cut -c1-16)
  ba=$(stat -c%s "$a"); bb=$(stat -c%s "$b")
  echo "shot1        sha16=$sa bytes=$ba"
  echo "shot1_repeat sha16=$sb bytes=$bb"
  [ "$sa" = "$sb" ] && echo "VERDICT: deterministic (identical bytes)" || echo "VERDICT: NONDETERMINISTIC (same prompt, different render)"
else
  echo "VERDICT: skipped (a clip is missing)"
fi

# 2. friendly names
ren() { [ -f "$2" ] && mv -n "$2" "$F/clips/$1" && echo "renamed -> $F/clips/$1"; }
ren tc09_moto.mp4        "$(awk '$1=="shot1"{print $2}' $N/batch_clips.txt)"
ren tc10_city.mp4        "$(awk '$1=="shot2"{print $2}' $N/batch_clips.txt)"
ren tc11_astro.mp4       "$(awk '$1=="shot3"{print $2}' $N/batch_clips.txt)"
ren tc12_moto_repeat.mp4 "$(awk '$1=="shot1_repeat"{print $2}' $N/batch_clips.txt)"
ren tc13_boat.mp4        "$(awk '$1=="shot4"{print $2}' $N/batch_clips.txt)"
ls -l $F/clips/*.mp4 | awk '{print $5, $9}'

# 3. multi-shot film: the extended motorcycle shot + city + astronaut + paper boat
LIST=""
for c in tc08_extend5.mp4 tc10_city.mp4 tc11_astro.mp4 tc13_boat.mp4; do
  [ -f "$F/clips/$c" ] && LIST="$LIST $F/clips/$c"
done
echo "--- stitching:$LIST"
sh $AVD/factory_stitch.sh $F/out/multishot_film.mp4 $LIST
ffprobe -v error -show_entries format=duration -of csv=p=0 $F/out/multishot_film.mp4 2>/dev/null | sed 's/^/multishot_film duration: /'

# 4. narration + bed + mux (AI audio engine, stage 1)
cat > /tmp/multishot_narration.txt <<'TXT'
Four scenes, one film. Every frame here was generated inside Messenger, by Meta AI, driven by a script through the phone's own interface. A motorcycle in the rain, a city at sunset, an astronaut on a red planet, a paper boat in a gutter. The factory harvested each clip from the app cache, stitched them offline with ffmpeg, and then this voice spoke. The narration and the room tone underneath were synthesized on the rig itself, no cloud, no uploads. Clip extension tops out near twenty four and a half seconds; beyond that the factory concatenates scenes. This is stage one of the automation pipeline. Lip sync is stage two.
TXT
sh $AVD/audio_engine.sh tts "$(cat /tmp/multishot_narration.txt)" $F/out/multishot_voice.wav
sh $AVD/audio_engine.sh bed $F/out/multishot_bed.wav 45 room
ffmpeg -hide_banner -loglevel error -y -i $F/out/multishot_bed.wav -i $F/out/multishot_voice.wav \
  -filter_complex "[1:a]adelay=1200|1200[v];[0:a][v]amix=inputs=2:duration=first:normalize=0[a]" \
  -map "[a]" -ac 2 $F/out/multishot_mix.wav
sh $AVD/audio_engine.sh mux $F/out/multishot_film.mp4 $F/out/multishot_mix.wav $F/out/multishot_film_narrated.mp4 replace

# 5. small preview for transfer
ffmpeg -hide_banner -loglevel error -y -i $F/out/multishot_film_narrated.mp4 \
  -vf scale=360:-2 -c:v libx264 -crf 31 -preset veryfast -c:a aac -b:a 96k $F/out/multishot_preview.mp4

echo "--- results"
for f in multishot_film.mp4 multishot_film_narrated.mp4 multishot_preview.mp4; do
  [ -f $F/out/$f ] || continue
  printf '%s  %s B  %s s  ' "$f" "$(stat -c%s $F/out/$f)" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 $F/out/$f)"
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 $F/out/$f | tr -d '\r\n'
  printf '  audio=%s\n' "$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 $F/out/$f | tr -d '\r\n')"
done
echo "=== step95 done $(date +%T) ==="
