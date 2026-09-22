from app.scenes.timing import reconcile_scene_durations, ALLOWED_CLIP_DURATIONS

def test_reconcile_picks_allowed_and_covers():
    narr = ["word " * 10, "word " * 40]
    out = reconcile_scene_durations(narr)
    assert all(s["clip_s"] in ALLOWED_CLIP_DURATIONS for s in out["scenes"])
    assert out["scenes"][0]["clip_s"] == 4
    assert out["scenes"][1]["clip_s"] == 10
    assert out["total_s"] == sum(s["clip_s"] for s in out["scenes"])
    assert out["units"] == 2
