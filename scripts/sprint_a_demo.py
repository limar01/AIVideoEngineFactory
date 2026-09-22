import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.story.min_engine import generate_story
from app.scenes.timing import reconcile_scene_durations
from app.audio.tts import MockTTSProvider
from app.assembly import assemble

def make_clip(sec, out):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                    "-i", "testsrc2=duration=%d:size=640x360:rate=24" % sec,
                    "-pix_fmt", "yuv420p", out], check=True, capture_output=True)

def main():
    outdir = "output/sprint_a"; os.makedirs(outdir, exist_ok=True)
    story = generate_story()
    plan = reconcile_scene_durations([s["narration"] for s in story["scenes"]])
    tts = MockTTSProvider()
    clips, wavs = [], []
    for s, p in zip(story["scenes"], plan["scenes"]):
        c = os.path.join(outdir, "clip_%02d.mp4" % s["scene_id"]); make_clip(p["clip_s"], c); clips.append(c)
        w = os.path.join(outdir, "narr_%02d.wav" % s["scene_id"]); tts.synthesize(s["narration"], w); wavs.append(w)
    vcat = os.path.join(outdir, "video_concat.mp4"); assemble.concat_videos(clips, vcat)
    acat = os.path.join(outdir, "narr_concat.wav"); assemble.concat_audios(wavs, acat)
    final = os.path.join(outdir, "final_60s.mp4"); assemble.mux(vcat, acat, final)
    print("FINAL=%s duration_s=%.1f units=%d planned_total_s=%d" % (
        final, assemble.probe_duration(final), plan["units"], plan["total_s"]))

if __name__ == "__main__":
    main()
