---
name: zillion-metaai-factory
description: "AI video factory — drive Meta AI video generation inside the Messenger app on the rooted emulator (generate → extend → harvest the clip from the ExoPlayer cache), stitch clips offline into long films with ffmpeg, and narrate them with the offline audio engine (TTS + ambience bed + mux). Ships the long-video QA report and the lip-sync design."
version: 1.0.0
author: Zillion Agent
license: MIT
---

# Meta AI video factory (Messenger lane)

Produces video with a phone UI as the only API: prompts are typed into Meta AI inside the native
Messenger app, the app renders a reel, and the factory harvests the finished file from the app's own
ExoPlayer cache — then everything after that (stitching, narration, muxing) is offline ffmpeg.

## Quick start

```sh
# one clip: type prompt -> send -> wait -> harvest -> ~/factory/clips + manifest.jsonl row
sh metaai_gen2.sh --send "a red vintage motorcycle on a rainy Tokyo street at night, cinematic" 300
sh metaai_gen2.sh --send-existing 300        # composer already holds the text (e.g. "extend it")

# batch -> one long video -> narration, in one call
sh factory_run.sh prompts.txt out/film.mp4 60 narration.txt

# sound on its own (AI audio engine, stage 1)
sh audio_engine.sh check
sh audio_engine.sh tts "line one. line two." out/voice.wav
sh audio_engine.sh bed out/bed.wav 60 room
sh audio_engine.sh mux out/film.mp4 out/voice.wav out/narrated.mp4 replace
sh audio_engine.sh lipsync                   # stage 2: exits 10 with the Wav2Lip install plan
```

## Files

| file | purpose |
|---|---|
| `metaai_gen2.sh` | v4 per-clip harness: composer → Send → cache-diff watch → **play-to-fetch** → verify → manifest |
| `factory_run.sh` | prompt file → batch → stitch → (optional) loop to target length → narrate |
| `factory_polish.sh` | finishing stage: `check` (codecs + faststart), `faststart` (remux, moov to front), `motion` (pan/zoom so near-static AI scenes do not look frozen), `preview` |
| `factory_stitch.sh` | normalise size/fps/SAR, concat, add silent AAC when a clip has no audio |
| `audio_engine.sh` | TTS / ambience bed / mix / mux / lip-sync stub (offline, espeak-ng today) |
| `net_proxy.sh` | mitm capture rig for URL + POST visibility (must be OFF while reels play) |
| `echoform.py` | tiny form server for POST-capture proof |
| `META_AI_LONG_VIDEO_QA.md` | the full QA report: 19 test cases, the extend ladder, measured numbers, failure matrix |
| `AI_AUDIO_ENGINE.md` | audio + lip-sync design (pipeline stages, upgrade paths, open decisions) |
| `README.md` | long-form command reference + all rules |

## Rules that cost the most time

1. **Play-to-fetch**: a generated reel is NOT downloaded until it is played. Press *Play* on the
   newest bubble before concluding anything (v4 does this automatically after 40 s, then every 48 s).
2. Detect new clips by diffing the ExoPlayer cache, never by counting UI nodes — the chat list is
   virtualised.
3. Tap the Send button through the uiautomator tree; fixed coordinates break when the prompt wraps.
4. The capture rig must be OFF for playback: reels show *"Couldn't play reel"* while mitm is on.
5. Never pull a cache file while it is still growing: settle-check size, pull, then assert
   `nb_read_frames == nb_frames` and zero decode errors.
6. **Finish every film with `factory_polish.sh`** — ffmpeg puts `moov` at the end by default, so a
   streamed/browser player shows a still frame while the audio runs; `faststart` is mandatory, and
   `motion` fixes the near-static look of Meta AI's extend tail.
7. Extends plateau at ≈24.5 s per clip — beyond that, stitch multiple clips.
8. Generation is stochastic: the same prompt twice gives different bytes; always record `sha16`.
9. Long waits must run detached (`setsid nohup … > log`) — a >2 min synchronous hive call can 524.

## Measured baseline

5.208 s fresh clip (624×624, 24 fps, silent) → extends to 9.04 / 12.88 / 16.71 / 24.38 / 24.67 s
(plateau). 5-prompt batch: 95–108 s wall time each, zero failures. Narrated four-scene film:
40.315 s, 10,485,917 B, H.264 + AAC stereo, produced fully offline in ~10 min of rig time.
