"""TTS provider abstraction (Sprint A). Free-tier compliant: no bypasses."""
import os, wave
from abc import ABC, abstractmethod

def estimate_duration_s(text, wps=2.6):
    words = len(text.split())
    return max(1.0, words / float(wps))

class TTSProvider(ABC):
    name = "base"
    @abstractmethod
    def synthesize(self, text, dest_path, voice=None):
        """Render text to audio file. Returns dict(path, duration_s, provider)."""

class MockTTSProvider(TTSProvider):
    name = "mock"
    def synthesize(self, text, dest_path, voice=None):
        dur = estimate_duration_s(text)
        rate = 16000
        n = int(dur * rate)
        with wave.open(dest_path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(b"\x00\x00" * n)
        return {"path": dest_path, "duration_s": dur, "provider": self.name}

class EdgeTTSProvider(TTSProvider):
    name = "edge"
    def synthesize(self, text, dest_path, voice=None):
        try:
            import edge_tts  # noqa: F401
        except Exception:
            raise RuntimeError("edge-tts not installed; approve install or use MockTTSProvider")
        import asyncio
        voice = voice or "en-US-AriaNeural"
        async def run():
            c = edge_tts.Communicate(text, voice)
            await c.save(dest_path)
        asyncio.run(run())
        return {"path": dest_path, "duration_s": probe_duration(dest_path), "provider": self.name}

def probe_duration(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return -1.0
