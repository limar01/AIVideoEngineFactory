"""Minimal story engine (Sprint A): template-driven horror beats with narration."""
BEATS = [
    ("HOOK", "They found the door in the basement that was never there before."),
    ("ESTABLISHING", "The house had been empty for thirty years, and it showed."),
    ("CHARACTER_INTRODUCTION", "Mara carried her grandfather's flashlight like a weapon."),
    ("ACTION", "The door opened by itself, slow, patient, hungry."),
    ("CLIMAX", "Something on the other side counted to three in her own voice."),
    ("RESOLUTION", "By morning the door was gone, but Mara still heard it breathing."),
]

def generate_story(topic="horror"):
    scenes = [{"scene_id": i, "type": t, "narration": n} for i, (t, n) in enumerate(BEATS)]
    return {"title": "The Door That Counted", "scenes": scenes}
