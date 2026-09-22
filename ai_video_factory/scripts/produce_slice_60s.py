#!/usr/bin/env python3
"""60-second vertical slice production — mock provider + mock TTS (free-tier safe).

Pipeline (Master Spec §1): story -> bibles -> plan -> optimize -> compile ->
generate (MockVideoProvider, real ffmpeg MP4s) -> download -> QA -> gate ->
assemble with per-clip narration -> final MP4 + report.

Run:  .venv/bin/python scripts/produce_slice_60s.py [OUT_DIR]
"""
import json
import subprocess
import sys
from pathlib import Path

from app.assembly import AssemblyConfig, AssemblyInput, VideoAssembler
from app.audio.tts import MockTTSProvider
from app.downloader import ClipDownloader
from app.prompts.compiler import PromptCompiler, SnapGenPromptAdapter
from app.providers.mock import MockVideoProvider
from app.qa import AssemblyGate, VideoQA
from app.scenes.optimizer import SceneOptimizer
from app.scenes.planner import ScenePlanner
from app.story.engine import HermesStoryEngine

CLIP = 8.0
TARGET = 60.0


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return float(proc.stdout.strip() or -1)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/slice_60s")
    out.mkdir(parents=True, exist_ok=True)

    engine = HermesStoryEngine()
    story = engine.generate_story("haunted doll", "horror", int(TARGET))
    cb = engine.generate_character_bible(story)
    vb = engine.generate_visual_bible(story, cb)

    planner = ScenePlanner(target_clip_seconds=CLIP)
    scenes = planner.plan(story, cb, vb, target_clip_seconds=CLIP)
    optimizer = SceneOptimizer()
    scenes = [optimizer.optimize(s) for s in scenes]

    compiler = PromptCompiler()
    compiled = compiler.compile(
        scenes, story=story, character_bible=cb, visual_bible=vb,
        adapters=[SnapGenPromptAdapter()],
    )
    for orig, cp in zip(scenes, compiled):
        orig.prompts = [{"text": cp.text, "provider": cp.provider, "version": cp.version}]

    provider = MockVideoProvider(
        quota_limit=200, output_dir=str(out / "mock_clips"),
        min_duration=CLIP, max_duration=CLIP,
    )
    provider.authenticate({})
    downloader = ClipDownloader(provider, clips_dir=str(out / "clips"))
    tts = MockTTSProvider()

    clips, tracks = [], []
    for i, cp in enumerate(compiled):
        meta = {
            "scene_number": cp.scene_number,
            "act_number": cp.act_number,
            "target_clip_seconds": cp.clip_seconds,
            "aspect_ratio": "16:9",
        }
        res = provider.submit_generation(cp.text, meta)
        if not res.success:
            print(f"GENERATION FAILED scene {cp.scene_number}: {res.error_message}")
            return 1
        clips.append(downloader.download(res.result_id, filename=f"clip_{i:02d}"))
        wav = out / f"narr_{i:02d}.wav"
        tts.synthesize(scenes[i].narration_text or scenes[i].title, str(wav))
        tracks.append(wav)

    qa = VideoQA()
    qa_results = [qa.check_clip(p, clip_id=f"clip_{i:02d}") for i, p in enumerate(clips)]
    gate = AssemblyGate(min_pass_rate=0.5, max_failures=5)
    allowed, reasons = gate.evaluate(qa_results)

    cfg = AssemblyConfig(output_dir=str(out), target_resolution=(1280, 720),
                         crossfade_duration=0.0)
    assembler = VideoAssembler(cfg)
    assembly = assembler.assemble(AssemblyInput(clips=clips, narration_tracks=tracks, config=cfg))
    if not assembly.success or not assembly.output_path:
        print(f"ASSEMBLY FAILED: {assembly.error_message}")
        return 1

    planned = len(clips) * CLIP
    actual = probe_duration(assembly.output_path)
    report = {
        "target_seconds": TARGET,
        "clip_seconds": CLIP,
        "scenes": len(compiled),
        "planned_video_seconds": planned,
        "actual_seconds": actual,
        "qa_passed": sum(1 for r in qa_results if r.overall_pass),
        "qa_total": len(qa_results),
        "gate_allowed": allowed,
        "gate_reasons": reasons,
        "final_video": str(assembly.output_path),
        "file_size_bytes": assembly.file_size_bytes,
        "tts_provider": "mock",
    }
    (out / "slice_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    ok = assembly.success and actual >= TARGET - 2.0
    print("SLICE_OK" if ok else "SLICE_SHORT")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
