# AI VIDEO ENGINE × AI AUDIO ENGINE — scene-declared duration contract (v1)

**Lane:** PC `omarchy` (`/home/limar01/Projects/workspace/project`) · **AVD:** `zillion_root_avd` / `emulator-5554`
**Status:** video path implemented (`avd/metaai_gen2.sh`, `factory_run.sh`, `factory_stitch.sh`) · audio engine stage 1 implemented (`avd/audio_engine.sh`), stage 2 lip-sync specced · **this document adds the missing piece: the scene duration contract + planner/validator (`avd/scene_plan.py`)** · 2026-09-27

---

## 1. The two pipelines and their handshake

```
  STORY ─► SCENE PLAN (scenes.json) ─┬─► AI VIDEO ENGINE ──► clips/scene_NN.mp4 ──┐
        declared durations per scene │   base + N extends (silent, 624x624)      │
        (single source of truth)     │                                           ├─► CONFORM ─► MASTER TIMELINE ─► film.mp4
                                     └─► AI AUDIO ENGINE ──► audio/scene_NN.wav ──┘
                                         TTS narration + bed, time-fit to scene
```

Both engines read the **same** `scenes.json`. Neither engine invents its own timing. The video side
conforms picture to the declared scene duration; the audio side fits narration to the same declared
duration. That is the sync.

## 2. Duration per video generate — MEASURED (this is the number Boss asked for)

Real Messenger clips, TC-01..TC-16 (2026-09-26), every clip 624×624 @ 24 fps, **no audio track**:

| generate chain | measured duration | how |
|---|---|---|
| base clip | **5.2083 s** | one prompt |
| base + 1 extend | **9.0417 s** | "extend it" |
| base + 2 extends | **12.8750 s** | extend ×2 |
| base + 3 extends | **16.7083 s** | extend ×3 |
| base + 4 extends | **20.5417 s** (formula; not yet probed) | extend ×4 |
| base + 5 extends | **24.3750 – 24.6667 s** | extend ×5 — chain cap |
| chain cap | **~24.4–24.7 s** | app ceiling; longer scenes = 2+ clips |

- Rule: **duration = 5.2083 + n × 3.8333 s** (n = extends, 0…5). Everything else is rounding.
- **TC-16 result: prompt words do NOT change duration.** "make it 10 seconds" generates nothing by
  itself — declaring a scene duration means **choosing the extend count**, not writing it in the prompt.
- Default declared durations for scenes: **5.21 / 9.04 / 12.88 / 16.71 s** (quality cap n=3, per Meta AI's
  "~15 s before quality drops"); use n=4–5 only when a scene must be one continuous shot.

## 3. Scene manifest — the sync contract (`scenes.json`)

```json
{
  "schema": "aivideo.scenes/1",
  "provider": {"name":"meta_ai_messenger","base_s":5.2083,"extend_s":3.8333,"max_ext":3,
               "cap_s":24.667,"resolution":"624x624","fps":24,"native_audio":false},
  "audio_engine": {"tts":"espeak-ng","wps":3.8,"mux":"narrate","fit_max_atempo":1.10,"tolerance_s":0.15},
  "target_s": 600, "planned_s": 601.25, "scene_count": 36,
  "scenes": [
    {"id":"scene_01","index":1,"start_s":0.0,"end_s":16.7083,"declared_s":16.7083,
     "extends":3,"clip_plan":"base + 3 extend(s)","narration_words":63,
     "prompt":"<video prompt>","narration":"<voice line>","bed":"wind",
     "sync":{"video_conform":"trim|pad to declared_s","audio_fit":"atempo <= 1.10 else pad silence",
             "tolerance_s":0.15}}
  ]
}
```

Per-scene fields every asset later inherits: `start_s · end_s · declared_s · scene_id · layer · sync status`
(the layer/asset model from the Vibes master spec §4 stays authoritative).

## 4. Procedure per scene (both engines, same declared number)

1. **Plan** — `scene_plan.py plan --target 600` → scenes quantised to the ladder.
2. **Video** — per scene: send prompt; for n>0 send "extend it" n times; the capturer saves the newest
   cache clip (`metaai_gen2.sh`); QA: duration ≈ declared (else regenerate/conform); conform = trim/pad
   to `declared_s` at assembly, so the timeline never drifts.
3. **Audio** — per scene: `audio_engine.sh tts "<narration>" scene_NN.wav` (budget ≈ **3.0 words/s measured on this host** ×
   declared_s — scripts written to that budget need no stretch; see §6); measure; if |actual−declared| ≤ 0.15 s
   → nothing to do; else `atempo ≤ 1.10` (≤10 % speed-up is invisible), otherwise pad/trim the bed
   (never speed narration past 1.10).
   Fit rule: **underrun → pad** (silence under the bed, always safe) · **overrun ≤ 10 % → atempo** (invisible) ·
   **overrun > 10 % → rewrite shorter or split the scene** (never stretch past 1.10 or trim words).
4. **Mux** — `audio_engine.sh mux scene_NN.mp4 scene_NN.wav scene_NN_av.mp4 narrate`.
5. **Check** — `scene_plan.py check scenes.json --clips clips --audio audio` → PASS/WARN/FAIL per scene +
   `scenes.json.report.json`. Anything FAIL is regenerated before assembly.
6. **Assemble** — `factory_stitch.sh film.mp4 scene_*_av.mp4` (normalises size/fps/SAR, keeps the
   timeline in the declared order).

## 5. Long video math (the factory's own example)

`"10-minute Filipino horror story"` → 600 s → with the quality cap (16.71 s/scene) ≈ **36 scenes**
(base + 3 extends each) → narration budget ≈ **1,800 words total ≈ 50 words/scene** (at the measured
3.0 words/s).
With the max cap (24.38 s/scene) ≈ 25 scenes. Nothing is manual: the planner prints this and the
prompts/narration sheets (`scene_plan.py export`).

## 6. Status / open items

- **Verified today:** the ladder above (ffprobe of TC clips), scene planner + validator written and run
  (`avd/scene_plan.py`), audio TTS path works (espeak-ng), stitcher normalises silent clips and can add a
  silent AAC track for later narration.
- **Vibes app (`com.facebook.vibes`, v35.0.0.1.106, installed 2026-09-26 22:28)** — the master spec's
  "8-second unit" assumption is **NOT yet measured on this rig**. If Vibes clips come with audio/lip-sync
  natively, its unit duration must be added to the ladder here before planning against it.
- **Audio decisions still open** (from `AI_AUDIO_ENGINE.md` §6, unchanged): voice engine (espeak-ng vs
  piper), language (EN vs Tagalog — PH market), lip-sync scope (Wav2Lip needs a face clip; Meta AI scenes
  have none), and disk (was 11 GB free; now **9.1 GB** — Wav2Lip ≈3–4 GB would need a cleanup first).
- **Word-rate calibration (v1.1):** measured **3.0 words/s** on this host (36-word comma-rich line →
  11.88 s). The earlier 3.8 came from a 44-word line with different prosody — the default is now 3.0
  (conservative: narration that runs short is padded, narration that runs long has to be rewritten).
  Re-measure on piper/ElevenLabs install and update `audio_engine.wps`.
