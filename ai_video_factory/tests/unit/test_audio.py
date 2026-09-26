import os, wave
from app.audio.tts import MockTTSProvider, estimate_duration_s

def test_estimate_duration():
    assert estimate_duration_s("one two three four five six") > 1.0

def test_mock_tts_writes_wav(tmp_path):
    p = tmp_path / "n.wav"
    r = MockTTSProvider().synthesize("hello world " * 5, str(p))
    assert os.path.exists(r["path"]) and r["provider"] == "mock"
    with wave.open(str(p)) as w:
        assert w.getnframes() > 0 and w.getframerate() == 16000
