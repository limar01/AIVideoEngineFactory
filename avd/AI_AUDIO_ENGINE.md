# AI Audio Engine (speech + bed) and Lip-Sync — pipeline design

**Status:** stage 1 (speech + audio bed + mux) **implemented and verified today**; stage 2 (lip-sync)
**specced, not installed**. This file is the contract for the audio engine as a stage of the video
factory automation.

---

## 1. Where it sits in the pipeline

```
 Meta AI (Messenger)                AI AUDIO ENGINE                     assembly
 ───────────────────                ────────────────                    ────────
 prompt ─► 5.2 s clip ─┐
 extend ×3–4 ─► ~24 s ─┤            script.txt ─► TTS ─► voice.wav ─┐
                       ├─ clips/ ──► (optional lip-sync on face ────┼─► mux/stich ─► film.mp4
 more prompts ─────────┘             clips)      ─► bed.wav ───────┘
```

The factory now produces **silent** video only (measured: no audio track in any Meta AI clip, 624×624,
24 fps). Audio is therefore added by this engine, and every downstream artifact is expected to be
"A/V muxed" — the stitcher already writes a silent AAC track for exactly this reason.

## 2. Stage 1 — implemented (`audio_engine.sh`)

```sh
sh audio_engine.sh check                              # what engines exist on this host
sh audio_engine.sh tts   "<text>" voice.wav [voice]   # espeak-ng now, piper when installed
sh audio_engine.sh bed   bed.wav 60 [room|wind|hum]   # synthesized room-tone via ffmpeg lavfi
sh audio_engine.sh mux   film.mp4 voice.wav out.mp4 [narrate|replace]
sh audio_engine.sh lipsync face.mp4 voice.wav out.mp4 # stage 2 (see §4)
```

Verified on this host (2026-09-26):

| step | result |
|---|---|
| `check` | espeak-ng ✓ · piper ✗ · ffmpeg ✓ · GPU **GTX 1060 6 GB** ✓ · Wav2Lip ✗ |
| `tts` (44-word line) | `narration.wav` — 11.44 s, 44.1 kHz stereo, loudness-normalised (`loudnorm I=-16`) |
| `bed` 61 s wind | brown/pink noise + low-pass, 3 s fade in/out |
| `mux` replace | `film_60s_audio.mp4` — **60.21 s, h264 + aac stereo, 22.6 MB** |
| preview | `preview_60s_audio.mp4` 2.68 MB (480p) → delivered to the sandbox as `factory_film_60s_narrated.mp4` |

Contract for automation:

* **artifacts** live next to the clips: `<stem>.wav` (voice), `<stem>_bed.wav`, `<stem>_audio.mp4`;
* `tts` exits non-zero when no engine is present, so the pipeline can skip the stage instead of
  producing a silent film by accident;
* `mux narrate` mixes voice **under** whatever the clip already carries (delay `${DELAY_MS:-800}`),
  `mux replace` swaps the track entirely;
* every step is offline; nothing calls a network API.

## 3. Quality upgrade path (TTS)

| option | pros | cons | action |
|---|---|---|---|
| **espeak-ng** (in use) | already installed, instant, tiny | formant/robotic voice | none — it is the fallback that keeps the pipeline green |
| **piper** (neural, ONNX) | natural, CPU-fast, ~60 MB/voice, fully offline, many voices (incl. multi-lang) | needs a one-time download | `pip install piper-tts` + a voice .onnx; then `audio_engine.sh` picks it up automatically (`PIPER_MODEL=`) |
| Coqui XTTS / voice cloning | high fidelity, voice cloning | ~2 GB torch stack, slower on CPU | only if the Boss wants a specific/cloned voice |
| Cloud (ElevenLabs, Google, Azure) | best quality, instant | API keys, per-character cost, network from the host (the *sandbox* has no internet) | needs a decision + keys |

Recommended: **piper now, Coqui/cloud only on explicit request.** Tagalog/PH voices exist for piper —
worth deciding early because the factory spec is PH-market oriented.

## 4. Stage 2 — lip-sync (specced)

**Blocker to state plainly: Meta AI's generated clips are scenes (motorcycle, city, astronaut) — they
contain no face.** Lip-sync needs a face video as input, so the pipeline must first produce talking-head
footage:

```
script.txt ─► TTS ─► voice.wav ─┐
                                ├─► Wav2Lip ─► synced.mp4 ─┐
 face video (see below) ────────┘                          ├─► assembly ─► film
 scene clips (Meta AI) ────────────────────────────────────┘
```

Face-video options, best → worst for this rig:

1. **Meta AI talking-person clip** — prompt for *"a young woman talking directly to camera, neutral
   background, medium close-up, cinematic"*. Same factory, same harvesting code, same 5.2 s/extend
   ladder. Then Wav2Lip re-syncs the mouth to our TTS line.
2. Stock/anonymous face footage already on the PC (no account involved).
3. Photoreal avatar engines (SadTalker / LivePortrait) — heavier install, no real footage needed.

Install plan for Wav2Lip on this host (GTX 1060 6 GB, 11 GB free disk):

```sh
git clone https://github.com/Rudrabha/Wav2Lip            # GitHub is reachable from the PC
python3 -m venv ~/tools/w2l && ~/tools/w2l/bin/pip install -r requirements.txt
# torch CUDA wheel (~2.5 GB) — currently only +cpu is installed, GPU makes this minutes not seconds
curl -L -o Wav2Lip/checkpoints/wav2lip_gan.pth <public weights URL>   # ~436 MB
sh audio_engine.sh lipsync face.mp4 voice.wav out.mp4     # exits 10 with this plan if not installed
```

Then the stage is wired the same way as audio: a verb, an artifact, a manifest row.

## 5. Manifest / bookkeeping

Every stage appends to the same JSONL philosophy already used for clips:

```json
{"ts":"…","stage":"tts","engine":"espeak-ng","text_sha16":"…","file":"voice.wav","duration":11.44}
{"ts":"…","stage":"bed","style":"wind","file":"bed.wav","duration":61.0}
{"ts":"…","stage":"mux","mode":"replace","video":"film_60s.mp4","audio":"voice_bed.wav","out":"film_60s_audio.mp4"}
{"ts":"…","stage":"lipsync","engine":"wav2lip","device":"cuda","in":"face.mp4","out":"face_sync.mp4"}
```

## 6. Decisions needed (Boss)

1. **Voice**: keep espeak-ng (robotic but instant) / install piper (natural, offline, ~60 MB) / a cloud
   API (best quality, keys + cost)?
2. **Language**: English only, or Tagalog/Filipino for the PH audience (piper has voices for both)?
3. **Lip-sync scope**: (a) install Wav2Lip now (~3–4 GB, GPU present), (b) use a hosted avatar API
   instead, or (c) keep lip-sync out of the automated path and only mux narration?
4. **Disk**: 11 GB free — approve the Wav2Lip install, or clean the 99 GB used first?

## 7. v1.1 fix (2026-09-27)

- `mux` on a SILENT clip (the factory default) previously died -> 0-byte output: the narrate path mixed
  against `[0:a]`, an audio stream that does not exist on Meta AI clips. Now: silent clip -> voice alone,
  delayed, padded to the FULL video length (`-t $D`); the old amix path runs only when the clip has audio.
- `replace` no longer uses `-shortest` (it trimmed scenes to the voice length — shorter than the declared
  scene duration).
- Verified: scene_01 (9.04 s clip + 5.90 s voice) -> A/V 9.04 s with the voice padded to scene length.
