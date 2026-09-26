# Meta AI (Messenger) → Long Video: QA + Test Cases

**Date:** 2026-09-26 · **Surface:** Meta AI chat inside the native Messenger app (`com.facebook.orca`
556.0.0.59.68, x86_64) on the rooted AVD `zillion_root_avd` (Pixel 7, API 36, emulator-5554)
**Host:** omarchy PC (adb + ffmpeg/ffprobe; no internet needed by any of these tools)
**Artifacts:** every clip, manifest row, screenshot and assembled video referenced below is listed at
the end of this file. Nothing here is estimated — all durations/bytes come from `ffprobe`/`stat`.

---

## 1. What one Meta AI clip actually is

| property | value |
|---|---|
| container / codec | MP4, H.264 (`ftypisom`, moov+mdat) |
| resolution | 624 × 624 (square) |
| frame rate | 24 fps |
| duration (fresh generation) | **5.208 s** (125 frames) |
| audio | **none — the clip is silent** (no audio track at all) |
| size on device | ≈ 6.5 MB (first partial pull 1.8 MB) |
| where it lives before export | `…/com.facebook.orca/files/ExoPlayerCacheDir/videocache/<n>/<id>.mp4.0.<ts>.v2.exo` |

**Rule of thumb:** one prompt ≈ 5.2 s of silent 624² video. Anything longer is either **Extend**
(section 3) or **offline stitching** (section 4).

---

## 2. Test cases and results

Artifact tags (TC-01b, TC-06-extend3, TC-07-extend4, TC-08-extend5 …) are the row IDs in `manifest.jsonl` and the clip file names on the rig.

Legend: PASS = reproduced with captured evidence · FAIL = expected behaviour not observed ·
BLOCKED = cannot be tested as designed (reason given) · PENDING = queued.

| # | Test | Result | Evidence |
|---|---|---|---|
| TC-00 | Ask Meta AI about its own limits | PASS (self-report) | reply: *"initial clips are ~5 seconds. Max is ~12-15 sec with extensions, I can chain 2-3 extends"* |
| TC-01 | Generate one video from a text prompt | **PASS** | `5.208 s / 125 fr` (clip: motorcycle, rainy Tokyo neon) |
| TC-01a | Play a generated reel **while the mitm capture rig is on** | **FAIL (known cause)** | app shows *"Couldn't play reel — technical error [Reload]"*; reels do not stream through mitmproxy |
| TC-01b | Same, rig off | PASS | reel auto-streamed, clip harvested |
| TC-03 | Extend #1: *"Extend that video by another 5 seconds, keep the same scene and style"* | **PASS** | **9.042 s / 217 fr** (+3.83 s) |
| TC-04 | Extend #2: *"Extend this video once more by 5 seconds, same scene"* | **PASS** | **12.875 s / 309 fr** (+3.83 s) |
| TC-05 | Play-to-fetch (clip generated but absent from the cache) | **PASS** | extend #3 was **only** recoverable by tapping **Play** on the newest bubble — see note below |
| TC-06 | Extend #3: *"Extend it one more time by 5 seconds"* | **PASS** | **16.708 s / 401 fr** (+3.83 s) → `tc06_extend3.mp4` |
| TC-07 | Extend #4: *"Extend it by 5 more seconds please"* | **PASS** | **24.375 s / 585 fr** (+7.67 s) → `tc07_extend4.mp4` (again only after Play) |
| TC-08 | Extend #5: *"Extend the video by 5 more seconds again"* | **PLATEAU** | **24.667 s / 592 fr** (+0.29 s) → `tc08_extend5.mp4`; single-clip ceiling ≈24.5 s |
| TC-09 | Offline assembly of several clips (ffmpeg concat) | **PASS** | 4 clips → **43.857 s** (`ladder_demo4.mp4`) |
| TC-10 | Loop-to-duration (`TARGET=60`) | PASS (with caveat) | 3 × 27.1 s sequence → **81.4 s**; the repeat count is whole sequences, so overshoot is normal — trim with `-t` |
| TC-11 | Browser HTTP capture (URL + headers + POST body) | **PASS** | `POST https://httpbin.org/post → 200`, body captured from mitmproxy log |
| TC-12 | Third-party app capture (URLs / bodies) | **PASS for unpinned apps** | F-Droid `HEAD f-droid.org/repo/entry.jar`, googleapis POSTs with bodies |
| TC-13 | Capture the **media URL** of a generated clip | BLOCKED | rig on ⇒ playback fails; media never loads while intercepting. Workarounds in §6 |
| TC-14 | Determinism: same prompt twice | filled by the step92 batch | shot1 vs shot1_repeat — same prompt, independent generations; `sha16` compared |
| TC-15 | Rate limits / spam behaviour | filled by the step92 batch | 5 prompts back-to-back, 12 s apart: no refusal, all rc=0 (latency table in §3) |
| TC-16 | Explicit duration prompt (*"make a 10 second video"*) | PENDING | expected: ignored — length comes from Extend, not from wording |
| TC-17 | Audio / lip-sync (the 8 s spec) | OUT OF SCOPE for Meta AI, **covered by the new stage** | Meta AI clips are silent; speech is added by the AI audio engine (`AI_AUDIO_ENGINE.md`) — narration + bed verified on the 60 s film; lip-sync specced (Wav2Lip on the GTX 1060) |
| TC-19 | Multi-shot film + narration, end to end | **PASS** | 4 scenes (24.667 s extend + 3 × 5.208 s) → **40.315 s** film, then TTS narration + room bed muxed (`multishot_film_narrated.mp4`, 10,485,917 B, h264 + AAC stereo) |
| TC-18 | Continuity across a stitch (do the pieces belong to one film?) | **PASS** | frame 30 of TC-01 vs frame 395 of the 16.708 s extend: same motorcycle, same street, same style; the camera has moved, no hard cut — evidence `proof/f_tc01.jpg`, `proof/f_tc06.jpg` |

### TC-05 note — the important one
The third extend looked like it had failed (no new file for ~4 minutes, a re-encoded 9.04 s copy
appeared in the cache instead). It had **not** failed: the 16.708 s reel only materialised once the
bubble was **played**. Lesson baked into the harness: *a generated reel is not downloaded until it is
played; press Play (bottom-most bubble) before concluding anything.*

---

## 3. The native long-video path: Extend

```
generate          5.208 s
+ extend #1       9.042 s     (+3.83)
+ extend #2      12.875 s     (+3.83)
+ extend #3      16.708 s     (+3.83)
+ extend #4      24.375 s     (+7.67)
+ extend #5      24.667 s     (+0.29)  <- plateau
```
The increment is **+3.8333 s** for the first three extends (≈92 frames each), then **+7.667 s** on the
4th — i.e. Meta AI appends what it decides, not the 5 s you asked for — and the 5th adds only 7 frames
(a re-render, no new story). **Single-clip ceiling ≈ 24.5 s.** Prompt wording that works (verbatim):
*"Extend that video by another 5 seconds, keep the same scene and style"* → *"Extend this video once
more by 5 seconds, same scene"* → *"Extend it one more time by 5 seconds"* → *"Extend it by 5 more
seconds please"*.

Practical recipe: extend while the number grows (3–4 times), then switch to offline stitching (§4) for
anything longer than ~25 s, or when you want several different shots instead of one continuous take.

---

## 4. The factory path: generate many, stitch offline (`factory_stitch.sh`)

```sh
# 5.2 + 9.0 + 12.9 + 16.7 s ladder → one 43.9 s file (identical size/fps/SAR, silent AAC added)
sh factory_stitch.sh out/ladder_demo4.mp4 clips/tc01_final.mp4 clips/tc03_final.mp4 \
                                        clips/tc04_final.mp4 clips/tc06_extend3.mp4

# any length: repeat the sequence until >= TARGET seconds, then trim
TARGET=60 sh factory_stitch.sh out/film.mp4 clips/*.mp4      # → 81.4 s (whole repeats)
ffmpeg -i out/film.mp4 -t 60 -c copy out/film_60s.mp4        # → 60.107 s (lands on the next
                                                              #   keyframe — re-encode for exactly 60.000)
```
Measured: **43.857 s / 16.1 MB** (4 clips) and **68.232 s / 22.7 MB** (5 clips, incl. the 24.375 s
extend) in one pass each; a hard-trimmed **60.107 s** film (`ffmpeg -t 60 -c copy`) from the 5-clip
ladder. Runtime is seconds, fully offline, no python packages. Because Meta AI clips are silent, the
stitcher adds a silent AAC track so editors/players behave.

Sound is a separate, equally offline stage — `audio_engine.sh tts|bed|mix|mux` (see
`AI_AUDIO_ENGINE.md`): narration + a room-tone bed are synthesized on the rig, muxed onto the film
(`film_60s_audio.mp4`, 60.209 s, h264 + AAC stereo). `factory_run.sh prompts.txt out.mp4 60 script.txt`
runs the whole chain — generate → stitch → narrate — in one call.

### 4.1 Batch behaviour: latency, refusals, determinism (step92, 5 prompts back-to-back)
| # | prompt | wall time | result |
|---|---|---|---|
| shot1 | red vintage motorcycle, rainy Tokyo, neon | 96 s | rc=0, 5.208 s / 125 fr, 5,109,587 B |
| shot2 | futuristic city skyline at sunset, flying cars | 99 s | rc=0, 5.208 s / 125 fr, 3,510,119 B |
| shot3 | astronaut on a red desert planet, two moons | 95 s | rc=0, 5.208 s / 125 fr, 3,524,226 B |
| shot1_repeat | *same text as shot1* (determinism check) | 108 s | rc=0, 5.208 s / 125 fr, 5,166,834 B |
| shot4 | paper boat in a rain-soaked gutter, macro | 95 s | rc=0, 5.208 s / 125 fr, 3,369,846 B |

* **No refusals, no rate-limiting** at 5 prompts with 12 s between them — every run rc=0, first try.
* **Latency 95–108 s per clip** (mean ≈ 98.6 s) — but that includes a fixed 60 s harvest window, so the
  real generation time is roughly **35–50 s**; the harness stops early once the cache settles.
* **Generation is stochastic**: the same prompt twice gave *different* renders —
  `sha16 f4959122e7248349 / 5,109,587 B` vs `sha16 fb0afa4638a83d91 / 5,166,834 B`, same 5.208333 s /
  125 frames. Byte-identical repeats are **not** achievable; treat each clip as unique footage and keep
  the manifest (`manifest.jsonl` rows record prompt + sha16 + frame counts per clip).

Every clip came out at **624×624 / 125 frames / silent**, with `read_frames == nb_frames` and zero
decode errors — i.e. the pulls are intact, not truncated.

### 4.2 Multi-shot assembly — four scenes in one narrated film (step95)
The five batch clips were renamed into the manifest scheme (`tc09_moto`, `tc10_city`, `tc11_astro`,
`tc12_moto_repeat`, `tc13_boat` — the repeat kept as the determinism artifact), and the four *different*
scenes were stitched with the extended motorcycle shot in front:

| stage | output | measured |
|---|---|---|
| stitch 4 clips (24.667 + 5.208 × 3) | `out/multishot_film.mp4` | 9,688,504 B · **40.314860 s** · 624×624 · silent AAC track |
| TTS narration (offline, espeak-ng) | `out/multishot_voice.wav` | 39.827 s, loudnorm I=-16 |
| room-tone bed + voice, mixed | `out/multishot_mix2.wav` | voice delayed 300 ms (keeps the last line inside the film) |
| mux onto the film | `out/multishot_film_narrated.mp4` | 10,485,917 B · 40.314860 s · h264 + AAC 2ch · audio stream 40.309841 s |
| transfer copy | `out/multishot_preview.mp4` | 1,182,651 B · 360×360 · 40.333334 s |

So a *complete* film — four different shots, speech, ambience, single file — is produced **fully offline
in about 10 minutes of rig time** (≈8 min of it waiting on Meta AI). The same run also proved the
harness drives multi-scene batches unattended: 5 prompts, 12 s apart, no manual touch, no failures.

### 4.3 Finishing stage (`factory_polish.sh`) — the film must move *and* start
`faststart` is **mandatory**: without it the player shows one frame while the audio plays (this bit us
on the first multi-shot film — the rig-side check reported `faststart=NO`). `motion` is the fix for
near-static AI scenes. `factory_stitch.sh`, `audio_engine.sh` and `factory_run.sh` now pass
`-movflags +faststart` themselves, and `factory_run.sh` re-checks its outputs; `MOTION=1` inserts the
pan/zoom pass before the narration mux.

```sh
sh factory_polish.sh check    out/film.mp4                     # codecs + faststart=YES/NO
sh factory_polish.sh faststart out/film.mp4 out/film_web.mp4   # lossless remux, moov to the front
sh factory_polish.sh motion    out/film.mp4 out/film_move.mp4 1.12 26 18
sh factory_polish.sh preview   out/film_move.mp4 out/prev.mp4 360
```
Measured on the 40.315 s multi-shot film: faststart-only 10,485,917 B (same picture, plays correctly);
motion 1.12/26/18 → 9,831,726 B · 40.333334 s; previews 1.34 MB (motion) / 1.29 MB (faststart-only).
The 60.209 s narrated film was re-finished the same way (`film_60s_audio_fs.mp4` 22,589,963 B,
`film_60s_motion.mp4` 20,134,844 B).

### 4.4 Batch generation (`factory_run.sh`)
`sh factory_run.sh prompts.txt out.mp4 60 narration.txt` walks a prompt file, calls the per-clip harness
(`metaai_gen2.sh`), then stitches, loops to the target length if asked, and — when a 4th argument is given — runs the
audio stage (TTS → bed → mix → mux) so one call yields a finished narrated film. Nothing downloads
anything — POSIX sh + adb + ffmpeg (espeak-ng for narration) only, which is what a sandbox without
internet can run.

---

## 5. Harness behaviour (what had to be learned the hard way)

`metaai_gen2.sh` is click-driven (uiautomator), no root tricks needed inside the app:

1. **Send via the UI tree, not coordinates.** A multi-line prompt grows the composer and pushes the
   Send button ~120 px down; fixed-coordinate taps then silently miss. The node is
   `content-desc="Send"` (text present) / `"Send ✨"` (empty) — tap its bounds centre.
2. **Detection = cache diff, not node counting.** The chat is a virtualized list: only the *visible*
   bubble is in the accessibility tree, so counting `content-desc="Play video"` nodes sees 1 forever.
   Poll `…/videocache/*/*` for a filename that was not there before.
3. **Press Play.** If no new file appears, tap the bottom-most `Play video` node; that is what makes
   the app stream (and cache) the reel. A `Reload` button means the stream failed — tap it.
4. **Never pull mid-download.** First pulls were truncated (37/125, 40/217, 17/309 frames decode,
   h264 "Error splitting the input into NAL units"). Wait for `stat -c%s` to stop changing, then pull
   and verify `nb_read_frames == nb_frames` + `ffmpeg -v error … -f null -` silent.
5. **The capture rig must be OFF for playback.** With `net_proxy.sh start` active the reel shows
   *"Couldn't play reel"*; with it stopped the same reel streams (and the app clears the error by
   itself). Generation traffic itself is captured fine — it is media playback that breaks.
6. **Session/long jobs:** run long waits detached (`setsid nohup … > log`), because the PC tunnel can
   return HTTP 524 on a >~2 min synchronous call and kill the client side.

---

## 6. Failure matrix

| Symptom | Cause | Fix |
|---|---|---|
| "Something went wrong. Please try again." loop after login | Meta invalidated the session (error 190) | `pm clear com.facebook.orca`, set timezone, relaunch, log in again |
| "Couldn't play reel / technical error" | capture rig (mitmproxy) intercepting media | `net_proxy.sh stop`, tap Reload — the reel streams |
| New reel never appears in the cache | it is only fetched when played | tap Play on the newest bubble |
| Pulled clip decodes only first N frames | pulled mid-download | settle-check size, re-pull, verify frame count |
| Extend "does nothing" | the longer reel is pending in the UI, not the cache | play it first (TC-05 story) |
| `ffmpeg -ss …` fails, `-frames:v 1` writes 0 B | truncated cache pull (see above) | re-pull; or use `select=eq(n,N)` frame selection |
| `*.trycloudflare.com` → NXDOMAIN inside the emulator | emulator DNS will not resolve CF quick-tunnel hosts | use a public endpoint (e.g. httpbin) for browser tests |
| Tunnel HTTP 524 during a long job | synchronous exec outlived the tunnel limit | detached job + log file, poll the log |
| **Video plays but the picture sits on one frame while the audio runs** | ffmpeg writes `moov` at the **end** of the file (`faststart=NO`) — streamed/browser players must fetch the whole file before they can start the video, so they show a still frame and play the audio | `factory_polish.sh faststart in out` (remux, `-c copy`, lossless); every factory script now passes `-movflags +faststart` and `factory_run.sh` re-checks each output |
| Same symptom even with faststart, in a local player | the *content* is near-static: Meta AI renders very little movement in the extend tail (measured mean frame-to-frame luma delta drops to ~1.6 vs ~8 during active motion) | `factory_polish.sh motion in out 1.12 26 18` — crops 12% and pans ±26/±18 px on a 17 s/11 s sine, which lifts the minimum to ~2.4–3.9 and reads as a slow camera move |

---

## 7. Honesty notes / limits

* Durations, frame counts and bytes above are measured; the *content* claims (motorcycle etc.) are
  from looking at the frames, not inferred.
* Meta AI's own answer (TC-00) is a **self-report** and was treated as a hypothesis; the ladder in §3
  is the measurement that confirms/refines it (+3.83 s per extend, not +5 s).
* Meta AI produces **no audio**; "8 s with audio/lip-sync" is therefore assembled downstream — speech,
  bed and mux are implemented and verified (`AI_AUDIO_ENGINE.md`), lip-sync is specced but not installed
  yet (it also needs face footage, which Meta AI's scene clips do not contain).
* The media URL of a generated clip was **not** captured; §6 lists the cause. If that URL is required,
  the options are: (a) mitmproxy with the media CDN excluded from interception (`--ignore-hosts` +
  `--set stream_large_bodies` on a dedicated run), (b) tcpdump on the host for hostnames/IPs only,
  (c) a playback endpoint that streams plain HTTP.
* Automation against a Messenger account carries a ban risk: burn account, low volume, human-ish
  pacing (`sleep` between generations is already in `factory_run.sh`).

---

## 8. Artifacts

Device cache (complete assets):
`2/27943142692032298…` (5.208 s sample) · `3/4013971692078173…` (9.042 s) ·
`4/1031246199944205…` (5.208 s) · `4/3295041920702572…` (16.708 s) · `5/4576184052594465…` (12.875 s)

PC (`~/factory/clips/`, 17 files): ladder — `tc01_final.mp4` 5.208 s · `tc03_final.mp4` 9.042 s ·
`tc04_final.mp4` 12.875 s · `tc06_extend3.mp4` 16.708 s · `tc07_extend4.mp4` 24.375 s ·
`tc08_extend5.mp4` 24.667 s; batch — `tc09_moto.mp4` 5,109,587 B · `tc10_city.mp4` 3,510,119 B ·
`tc11_astro.mp4` 3,524,226 B · `tc12_moto_repeat.mp4` 5,166,834 B (determinism artifact) ·
`tc13_boat.mp4` 3,369,846 B (all 5.208 s / 125 fr / 624×624 / silent).
(`tc01_motorcycle` / `tc03_extended` / `tc04_extended2` = the early **truncated** pulls, kept only as
evidence of the failure mode.)
PC (`~/factory/out/`): `ladder_demo4.mp4` 43.857 s · `ladder5.mp4` 68.232 s / 22.7 MB ·
`film_60s.mp4` 60.107 s / 21,401,003 B · `long_60s_film.mp4` 81.4 s / 31,977,012 B ·
`preview_60s_v2.mp4` 2,207,166 B · `film_60s_audio.mp4` 22,589,963 B / 60.209 s (narrated) ·
`preview_60s_audio.mp4` 2,676,879 B · **multi-shot:** `multishot_film.mp4` 9,688,504 B / 40.315 s ·
`multishot_film_narrated.mp4` 10,485,917 B / 40.315 s · `multishot_preview.mp4` 1,182,651 B
(+ intermediate `multishot_voice/mix2/bed.wav`)
Finishing variants (PC `out/`): `multishot_film_fs.mp4` 10,485,917 B (faststart) ·
`multishot_motion_narrated.mp4` 9,873,617 B / zoom 1.06 · `multishot_motion2_narrated.mp4` 9,831,726 B /
zoom 1.12 · `film_60s_audio_fs.mp4` 22,589,963 B · `film_60s_motion.mp4` 20,134,844 B · previews
`multishot_motion2_preview.mp4` 1,337,299 B, `multishot_fs_preview.mp4` 1,286,923 B, `film_60s_fs_preview.mp4` 2,389,976 B
Sandbox (this workspace): `factory_multishot_motion2_narrated.mp4` 9,831,726 B (faststart, motion 1.12) ·
`factory_multishot_motion2_preview.mp4` 1,337,299 B · `factory_multishot_fs_preview.mp4` 1,286,923 B ·
`factory_film_60s_fs_preview.mp4` 2,389,976 B · `factory_multishot_film_narrated.mp4` 10,485,917 B / 40.315 s ·
`factory_multishot_preview.mp4` 1,182,651 B · `factory_film_60s.mp4` (60.1 s, full quality 21.4 MB) ·
`factory_film_60s_preview.mp4` (2.2 MB) · `factory_film_60s_narrated.mp4` 2,676,879 B / 60.27 s ·
`factory_ladder_5to17s.mp4` (43.9 s preview) · `factory_long_60s.mp4` (81.4 s looped preview) ·
`metaai_sample_video.mp4` (first clip, 5.208 s)
Manifest: `~/factory/manifest.jsonl` — **12 rows** (ladder TC-01b…TC-08-extend5 + the five batch shots),
each with ts, mode, prompt, file, bytes, duration, video, read_frames, decode_errors, audio, sha16
Screenshots: `~/Projects/workspace/project/avd/proof/qa_tc00_reply.jpg`,
`qa_tc01_state.jpg` (prompt sent, placeholder generating), `qa_tc01_error.jpg` ("Couldn't play reel"),
`qa_tc01_reload.png`, `play_click_*.png`, `qa_post_body.png` (browser POST proof),
`f_tc01.jpg` / `f_tc04.jpg` / `f_tc06.jpg` (frames 30 / 290 / 395 — continuity evidence)
