"""Duration reconciliation: narration is source of truth; clips adapt."""
from app.audio.tts import estimate_duration_s

ALLOWED_CLIP_DURATIONS = (4, 6, 8, 10)

def reconcile_scene_durations(narrations, tolerance=1.0):
    plan = []
    for i, text in enumerate(narrations):
        nd = estimate_duration_s(text)
        candidates = [d for d in ALLOWED_CLIP_DURATIONS if d >= nd - tolerance]
        chosen = min(candidates) if candidates else max(ALLOWED_CLIP_DURATIONS)
        plan.append({"scene": i, "narration_s": round(nd, 2), "clip_s": chosen})
    return {"scenes": plan, "total_s": sum(p["clip_s"] for p in plan), "units": len(plan)}
