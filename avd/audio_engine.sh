#!/bin/sh
# audio_engine.sh — the "AI audio engine" stage of the video factory (offline-first).
#
#   sh audio_engine.sh check                                  what is available on this host
#   sh audio_engine.sh tts   "<text>" out.wav [voice]         text -> speech (espeak-ng, normalised)
#   sh audio_engine.sh bed   out.wav <seconds> [style]        synthesized bed/room-tone via ffmpeg
#   sh audio_engine.sh mux   in.mp4 voice.wav out.mp4 [mode]  narrate (mixed under) | replace
#   sh audio_engine.sh lipsync in.mp4 voice.wav out.mp4       Wav2Lip if installed, else the install plan
#
# Everything here is offline (no network, no API keys). Optional better engines are detected and used
# automatically when present: piper (neural TTS) > espeak-ng (formant TTS), CUDA torch (fast lip-sync).
set -u

espeak_bin()  { command -v espeak-ng || command -v espeak; }
piper_bin()   { command -v piper; }
have_cuda()   { command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L 2>/dev/null | grep -q GPU; }
w2l_dir()     { echo "${WAV2LIP_DIR:-$HOME/tools/Wav2Lip}"; }
norm() { ffmpeg -hide_banner -loglevel error -y -i "$1" -af "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100" -ac 2 "$2"; }

cmd="${1:-check}"; shift 2>/dev/null || true

case "$cmd" in
check)
  printf 'espeak   : %s\n' "$(espeak_bin || echo MISSING)"
  printf 'piper    : %s\n' "$(piper_bin || echo MISSING)"
  printf 'gpu      : %s\n' "$(have_cuda && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo none)"
  printf 'wav2lip  : %s\n' "$([ -f "$(w2l_dir)/inference.py" ] && echo "$(w2l_dir)" || echo MISSING)"
  printf 'ffmpeg   : %s\n' "$(command -v ffmpeg || echo MISSING)"
  ;;

tts)   # $1 text  $2 out.wav  [$3 voice]
  TEXT="${1:?text required}"; OUT="${2:?out.wav required}"; VOICE="${3:-en-us+f3}"
  TMP=$(mktemp /tmp/ttsXXXX.wav)
  if P=$(piper_bin); then
    # piper expects a voice model; if one is configured use it
    MODEL="${PIPER_MODEL:-}"; [ -n "$MODEL" ] && echo "$TEXT" | "$P" -m "$MODEL" -f "$TMP" || { echo "piper present but PIPER_MODEL unset" >&2; exit 4; }
  else
    E=$(espeak_bin) || { echo "no TTS engine (install espeak-ng or piper)" >&2; exit 3; }
    "$E" -v "$VOICE" -s "${SPEED:-165}" -p "${PITCH:-45}" -w "$TMP" "$TEXT"
  fi
  norm "$TMP" "$OUT"; rm -f "$TMP"
  printf 'TTS %s -> %s (%s s)\n' "$(basename "$OUT")" "$OUT" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")"
  ;;

bed)   # $1 out.wav  $2 seconds  [$3 style: room|wind|hum]
  OUT="${1:?out.wav}"; SECS="${2:-60}"; STYLE="${3:-room}"
  case "$STYLE" in
    wind) SRC="anoisesrc=color=pink:amplitude=0.05,lowpass=f=900,highpass=f=120" ;;
    hum)  SRC="sine=frequency=58:beep_factor=0,volume=0.05" ;;
    *)    SRC="anoisesrc=color=brown:amplitude=0.035,lowpass=f=600" ;;
  esac
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i "$SRC" -t "$SECS" -af "afade=t=in:d=2,afade=t=out:st=$(awk -v s="$SECS" 'BEGIN{print s-3}'):d=3,aresample=44100" -ac 2 "$OUT"
  printf 'BED %s (%s s, %s)\n' "$OUT" "$SECS" "$STYLE"
  ;;

mux)   # $1 video  $2 voice.wav  $3 out.mp4  [$4 narrate|replace]
  V="${1:?video}"; A="${2:?audio}"; OUT="${3:?out.mp4}"; MODE="${4:-narrate}"
  if [ "$MODE" = replace ]; then
    ffmpeg -hide_banner -loglevel error -y -i "$V" -i "$A" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 160k -shortest -movflags +faststart "$OUT"
  else
    ffmpeg -hide_banner -loglevel error -y -i "$V" -i "$A" \
      -filter_complex "[1:a]adelay=${DELAY_MS:-800}|${DELAY_MS:-800},apad[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]" \
      -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k -movflags +faststart "$OUT"
  fi
  printf 'MUX %s -> %s (mode=%s)\n' "$(basename "$V")" "$OUT" "$MODE"
  ffprobe -v error -show_entries format=duration:stream=codec_name,channels -of default=nw=1 "$OUT" | tr '\n' ' '; echo
  ;;

lipsync)
  V="${1:?video}"; A="${2:?audio}"; OUT="${3:?out.mp4}"
  W=$(w2l_dir)
  if [ -f "$W/inference.py" ]; then
    DEV=$([ "$(have_cuda)" = true ] && echo cuda || echo cpu 2>/dev/null || echo cpu)
    echo "running Wav2Lip ($DEV) — this is the slow stage"
    ( cd "$W" && python3 inference.py --checkpoint_path "$(ls checkpoints/*.pth 2>/dev/null | head -1)" \
        --face "$V" --audio "$A" --outfile "$OUT" --$DEV )
    printf 'LIPSYNC %s\n' "$OUT"
  else
    cat <<'EOF'
Wav2Lip not installed. The factory path (once installed) is:
  git clone https://github.com/Rudrabha/Wav2Lip
  pip install -r requirements.txt            # torch (CUDA build if you have the GPU) + opencv + librosa
  # download wav2lip_gan.pth (~436 MB) into Wav2Lip/checkpoints/
  # then:  sh audio_engine.sh lipsync faceclip.mp4 voice.wav out.mp4
Notes
  * input video must contain a face (Meta AI scene clips have none) — generate a "person talking to
    camera" clip first, then lip-sync it to the TTS line;
  * disk: ~11 GB free on this host; weights+venv ≈ 3-4 GB (fine, but keep an eye on it);
  * GPU is present but torch installed is the CPU build (2.14.0+cpu) — a CUDA torch wheel makes the
    difference between minutes and seconds per clip.
EOF
    exit 10
  fi
  ;;

*) echo "usage: $0 {check|tts|bed|mux|lipsync} ..." >&2; exit 2 ;;
esac
