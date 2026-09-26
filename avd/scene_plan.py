#!/usr/bin/env python3
"""scene_plan.py — scene manifest planner + A/V sync validator for the
AI Video Engine + AI Audio Engine pipelines.

AI VIDEO ENGINE  = Meta AI (Messenger, AVD emulator-5554) — silent clips
AI AUDIO ENGINE  = avd/audio_engine.sh (espeak-ng TTS + ffmpeg bed + mux)

MEASURED PROVIDER LADDER (TC-01..TC-16, 2026-09-26, real Messenger clips,
624x624 @ 24 fps, no audio track in ANY clip):
    base clip    = 5.2083 s
    each extend  = +3.8333 s
    n extends    = 5.2083 + n * 3.8333        (n = 0..5)
    cap          = ~24.375 - 24.667 s per generate chain
Duration is MECHANICAL: base + extends. Prompt words do NOT set duration
(TC-16) — declaring a scene duration = choosing the extend count.

SYNC CONTRACT: scenes.json is the single source of truth for both engines.
    1. plan     -> declared per-scene durations, quantised to the ladder
    2. video    -> per scene: generate base + N extends, conform to declared
    3. audio    -> per scene: TTS narration + bed, time-fit to declared
    4. check    -> ffprobe actual vs declared -> PASS / WARN / FAIL + report

Commands:
    ladder                     print the ladder + narration word budget
    plan --target S [opts]     build scenes.json (declared durations)
    timeline scenes.json       print the master timeline table
    export scenes.json         write prompts.txt + narration/scene_NN.txt
    check scenes.json --clips D [--audio D]   verify actual vs declared

Options for plan:
    --target S     total target seconds (required)
    --max-ext N    quality cap: highest extend count per scene (default 3 = 16.7 s)
    --wps W        narration words per second (default 3.0, measured 2026-09-27)
    --story FILE   one story beat / narration line per line -> assigned per scene
    --out FILE     default scenes.json
    --id PREFIX    project id (default: project)
"""
import argparse, json, os, subprocess, sys, time

BASE_S = 5.2083          # measured
EXT_S = 3.8333           # measured per extend
CAP_S = 24.667           # app chain cap (measured 24.375 .. 24.667)
MAX_EXT_HARD = 5
FPS = 24
RES = "624x624"

def ladder(max_ext=3):
    return [round(BASE_S + i * EXT_S, 4) for i in range(0, max_ext + 1)]

def ffprobe_dur(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return round(float(out), 4) if out else None
    except Exception:
        return None

def has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                              "-show_entries", "stream=index", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return bool(out)
    except Exception:
        return False

def cmd_ladder(a):
    print("MEASURED LADDER — Meta AI / Messenger (per generate chain)")
    print(f"  base clip       {BASE_S:8.4f} s   (624x624 @ 24 fps, no audio)")
    for n in range(0, 6):
        v = BASE_S + n * EXT_S
        note = "  <- cap" if v > CAP_S else ""
        v = min(v, CAP_S) if n == 5 else v
        print(f"  base + {n} ext  {v:8.4f} s   {note}")
    print(f"  hard cap        {CAP_S:8.4f} s   (longer = chain 2 clips in one scene)")
    print()
    print("NARRATION BUDGET (measured ~3.0 words/s on this host, comma-heavy espeak-ng prose;")
    for s in (BASE_S + i * EXT_S for i in range(0, 4)):
        print(f"  {s:7.2f} s scene -> ~{int(round(s * 3.0)):3d} words")
    print()
    print("NOTE: duration is mechanical (base + extends). Prompt text does NOT set")
    print("duration (TC-16 result). Declare duration -> choose extend count.")

def cmd_plan(a):
    allowed = ladder(a.max_ext)
    units = sorted(allowed, reverse=True)
    scenes, used, idx = [], 0.0, 0
    while a.target - used >= min(units) - 1e-6:
        rem = a.target - used
        pick = next((u for u in units if u <= rem + 1e-6), None)
        if pick is None:
            break
        idx += 1
        used = round(used + pick, 4)
        scenes.append({"idx": idx, "declared_s": pick})
    # leftover handling: only a GENUINE remainder (> 0.5 s) may upgrade the last scene;
    # float dust (e.g. 0.0001) must never change the plan
    leftover = round(a.target - used, 3)
    if leftover > 0.5 and scenes:
        for u in units:
            if u >= scenes[-1]["declared_s"] + leftover - 0.01 and u <= CAP_S:
                used = round(used - scenes[-1]["declared_s"] + u, 4)
                scenes[-1]["declared_s"] = u
                break
    story = []
    if a.story and os.path.isfile(a.story):
        story = [l.strip() for l in open(a.story, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
    man = {
        "schema": "aivideo.scenes/1",
        "project": a.id,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": {"name": "meta_ai_messenger", "device": "emulator-5554",
                     "base_s": BASE_S, "extend_s": EXT_S, "max_ext": a.max_ext,
                     "cap_s": CAP_S, "resolution": RES, "fps": FPS, "native_audio": False},
        "audio_engine": {"tts": "espeak-ng", "wps": a.wps, "mux": "narrate",
                         "fit_max_atempo": 1.10, "tolerance_s": 0.15},
        "target_s": a.target,
        "planned_s": round(sum(s["declared_s"] for s in scenes), 4),
        "scene_count": len(scenes),
        "scenes": [],
    }
    t = 0.0
    for i, s in enumerate(scenes, 1):
        d = s["declared_s"]
        n_ext = round((d - BASE_S) / EXT_S) if d > BASE_S else 0
        man["scenes"].append({
            "id": f"scene_{i:02d}",
            "index": i,
            "start_s": round(t, 4),
            "end_s": round(t + d, 4),
            "declared_s": d,
            "extends": max(0, int(n_ext)),
            "clip_plan": "base" + (f" + {int(n_ext)} extend(s)" if n_ext else ""),
            "narration_words": int(round(d * a.wps)),
            "prompt": "",
            "narration": story[i - 1] if i - 1 < len(story) else "",
            "bed": "room",
            "sync": {"video_conform": "trim|pad to declared_s",
                     "audio_fit": "atempo <= 1.10 else pad silence",
                     "tolerance_s": 0.15},
        })
        t += d
    out = a.out or "scenes.json"
    json.dump(man, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"planned {man['scene_count']} scenes -> {out}")
    print(f"  target   {man['target_s']:.2f} s")
    print(f"  planned  {man['planned_s']:.2f} s  (delta {man['planned_s'] - man['target_s']:+.2f} s)")
    if leftover > 0.5 and man["planned_s"] < a.target:
        print(f"  WARN leftover {a.target - man['planned_s']:.2f} s could not be quantised "
              f"(adjust target or --max-ext)")
    return man

def cmd_timeline(a):
    man = json.load(open(a.manifest, encoding="utf-8"))
    print(f"{'id':10} {'start':>8} {'end':>8} {'dur':>8} {'ext':>4}  clip plan")
    for s in man["scenes"]:
        print(f"{s['id']:10} {s['start_s']:8.2f} {s['end_s']:8.2f} "
              f"{s['declared_s']:8.2f} {s['extends']:4d}  {s['clip_plan']}")
    print(f"TOTAL {man['planned_s']:.2f} s / target {man['target_s']:.2f} s "
          f"({man['scene_count']} scenes)")

def cmd_export(a):
    man = json.load(open(a.manifest, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(a.manifest))
    pdir = os.path.join(base, "narration")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(base, "prompts.txt"), "w", encoding="utf-8") as f:
        f.write("# prompts.txt — one prompt per scene (duration is MECHANICAL, do not\n"
                "# waste words on it; base + extends come from the manifest).\n")
        for s in man["scenes"]:
            f.write(s["prompt"] or f"[scene {s['index']:02d}] <write the prompt here>")
            f.write("\n")
    for s in man["scenes"]:
        with open(os.path.join(pdir, s["id"] + ".txt"), "w", encoding="utf-8") as f:
            f.write(f"# {s['id']} | declared {s['declared_s']:.2f} s | "
                    f"budget ~{s['narration_words']} words | bed {s['bed']}\n")
            f.write((s["narration"] or "") + "\n")
    print(f"exported -> prompts.txt + narration/ ({len(man['scenes'])} scenes) in {base}")

def find_media(d, sid, index):
    if not d or not os.path.isdir(d):
        return None
    pats = [sid, f"scene_{index:02d}", f"clip_{index:03d}", f"{index:02d}"]
    hits = []
    for f in sorted(os.listdir(d)):
        low = f.lower()
        if not low.endswith((".mp4", ".wav", ".mp3", ".m4a")):
            continue
        if any(low.startswith(p.lower()) for p in pats):
            hits.append(os.path.join(d, f))
    return hits[0] if hits else None

def cmd_check(a):
    man = json.load(open(a.manifest, encoding="utf-8"))
    tol = a.tol if a.tol is not None else man.get("audio_engine", {}).get("tolerance_s", 0.15)
    warn = a.warn
    rows, npass, nwarn, nfail = [], 0, 0, 0
    for s in man["scenes"]:
        vid = find_media(a.clips, s["id"], s["index"])
        aud = find_media(a.audio, s["id"], s["index"])
        vd = ffprobe_dur(vid) if vid else None
        ad = ffprobe_dur(aud) if aud else None
        d = s["declared_s"]
        issues = []
        verdict = "PASS"
        if vd is None:
            verdict, issues = "FAIL", ["video missing"]
        elif abs(vd - d) > warn:
            verdict = "FAIL"; issues.append(f"video {vd:.2f} vs {d:.2f} ({vd - d:+.2f})")
        elif abs(vd - d) > tol:
            verdict = "WARN"; issues.append(f"video drift {vd - d:+.3f}")
        if aud is not None:
            drift = ad - d
            if abs(drift) <= tol:
                fit = "ok"
            elif drift < 0:                      # underrun: always fixable (pad silence under bed)
                verdict = "WARN" if verdict == "PASS" else verdict
                issues.append(f"audio short {drift:+.2f} (pad)")
                fit = f"pad {-drift:.2f}s"
            elif ad / d <= 1.10:                 # overrun <= 10%: time-fit, invisible
                verdict = "WARN" if verdict == "PASS" else verdict
                issues.append(f"audio long {drift:+.2f} (atempo {ad/d:.3f})")
                fit = f"atempo {ad/d:.3f}"
            else:                                # overrun > 10%: rewrite shorter or split scene
                verdict = "FAIL"
                issues.append(f"audio too long {drift:+.2f} ({ad/d:.2f}x) — rewrite/split")
                fit = f"atempo {ad/d:.3f} (>limit)"
        elif a.audio:
            verdict = "WARN" if verdict == "PASS" else verdict
            issues.append("audio missing"); fit = "n/a"
        else:
            fit = "n/a"
        vd_s = f"{vd:.3f}" if vd is not None else "—"
        ad_s = f"{ad:.3f}" if ad is not None else "—"
        rows.append((s["id"], d, vd_s, ad_s, fit, verdict, "; ".join(issues)))
        npass += verdict == "PASS"; nwarn += verdict == "WARN"; nfail += verdict == "FAIL"
    print(f"{'id':10} {'declared':>9} {'video':>9} {'audio':>9}  {'fit':<14} verdict")
    for r in rows:
        print(f"{r[0]:10} {r[1]:9.3f} {r[2]:>9} {r[3]:>9}  {r[4]:<14} {r[5]}"
              + (f"  ({r[6]})" if r[6] else ""))
    print(f"\nSUMMARY  PASS {npass} · WARN {nwarn} · FAIL {nfail}  (tol ±{tol}s, fail > ±{warn}s)")
    rep = {"manifest": a.manifest, "checked": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "tol": tol, "warn": warn, "pass": npass, "warn_n": nwarn, "fail": nfail,
           "rows": [{"id": r[0], "declared_s": r[1], "video_s": r[2], "audio_s": r[3],
                     "fit": r[4], "verdict": r[5], "issues": r[6]} for r in rows]}
    rp = a.manifest + ".report.json"
    json.dump(rep, open(rp, "w", encoding="utf-8"), indent=2)
    print(f"report -> {rp}")
    sys.exit(0 if nfail == 0 else 1)

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ladder").set_defaults(fn=cmd_ladder)
    pp = sub.add_parser("plan")
    pp.add_argument("--target", type=float, required=True)
    pp.add_argument("--max-ext", type=int, default=3)
    pp.add_argument("--wps", type=float, default=3.0)
    pp.add_argument("--story"); pp.add_argument("--out"); pp.add_argument("--id", default="project")
    pp.set_defaults(fn=cmd_plan)
    pt = sub.add_parser("timeline"); pt.add_argument("manifest"); pt.set_defaults(fn=cmd_timeline)
    pe = sub.add_parser("export"); pe.add_argument("manifest"); pe.set_defaults(fn=cmd_export)
    pc = sub.add_parser("check")
    pc.add_argument("manifest")
    pc.add_argument("--clips", default=""); pc.add_argument("--audio", default="")
    pc.add_argument("--tol", type=float, default=None); pc.add_argument("--warn", type=float, default=0.40)
    pc.set_defaults(fn=cmd_check)
    a = p.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
