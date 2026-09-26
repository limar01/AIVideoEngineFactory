"Test audio engine scene spec creation."
import json
from app.audio.meta_audio_engine import (
    MetaAudioEngine,
    AudioSceneSpec,
    create_audio_scene_spec,
)

spec = create_audio_scene_spec(
    scene_id='S01',
    dialogue=[
        {'speaker': 'Jun', 'text': 'Teka... ikaw ba siyang hinahanap ni Mama?', 'emotion': 'shocked'},
        {'speaker': 'Apo Lola', 'text': 'Iyon... iyon nga ang pitaka ng anak ko.', 'emotion': 'emotional'},
    ],
    sfx=['motorcycle', 'footsteps'],
    ambience='busy residential barangay street',
    bgm='emotional',
    lipsync=True,
)
print(json.dumps({
    'scene_id': spec.scene_id,
    'dialogue_count': len(spec.dialogue),
    'sfx': spec.sfx,
    'ambience': spec.ambience,
    'bgm': spec.bgm,
    'lipsync': spec.lipsync,
}, indent=2))
