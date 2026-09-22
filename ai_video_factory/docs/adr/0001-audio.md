# ADR-0001: Audio Provider Selection

- **Status:** Proposed
- **Deciders:** Personal Agent, Architecture Agent, Video Processing Agent
- **Date:** 2026-09-22
- **Related:** `ARCHITECTURE.md` §5.2, `DEPENDENCY_GRAPH.md` §3.1, `config/audio.yaml` (pending creation)
- **Tags:** scope:pipeline, axis:audio, impact:architecture

### Context

The final assembly step (`app/assembly`) must produce a video with audio. The
Master Spec §23 requires modular templates and §2 mandates free-tier only with no
ToS bypass. "Audio" is one of the three decision axes the Architecture Agent
explicitly scoped as undecided at ARCH-001 approval time so the rest of the
system could be architected against an adapter.

The architecture (`ARCHITECTURE.md` §5.2) defines the `AudioProvider` ABC so
assembly never depends on a concrete audio implementation.

### Assumptions

- A default audio path that is **free and offline** must exist so the pipeline
  can run end-to-end (and so QA-001 can test assembly) without any external key.
- Any real paid/free-tier TTS provider must be invoked with user-supplied
  credentials only (not stored by the app) per Security Agent rules.
- Per-scene narration text is already captured in `Scene.narration_text`
  (`DB_SCHEMA.md` §3.4) and timing in `Scene.duration_seconds`, so the adapter
  choice does not affect scene planning.

### Options

| # | Option | Sketch | Free-tier? | ToS risk | Couples assembly to concrete? |
|---|--------|--------|------------|----------|-------------------------------|
| A | **SilentTrackProvider** (default) | Generate a muted/normalized track matching scene duration via FFmpeg `anullsrc`; assembly proceeds with no audio. | Yes (offline) | None | No — behind `AudioProvider` ABC |
| B | **PiperLocalProvider** | Local Piper binary + a permissive CC voice model downloaded once. | Yes (offline) | None | No — behind ABC |
| C | **ElevenLabsProvider** | Paid/free-tier API; user supplies API key via vault. | Free-tier only (limited) | Honors ToS; no bypass | No — behind ABC |
| D | **OpenAITTSProvider** | OpenAI TTS; user key via vault. | Free-tier only (limited) | Honors ToS; no bypass | No — behind ABC |

### Decision

Adopt **Option A (SilentTrackProvider)** as the *default* until a user decision
is recorded. The pipeline runs end-to-end with silent tracks; final quality
improves when a real voice is selected. This is the only safe zero-config,
zero-ToS-surface default, and it satisfies QA-001's "final assembly" test without
any external dependency.

A real provider (B/C/D) is selectable via `config/audio.yaml::provider`; the
`AudioProvider` registry is the single seam (`DEPENDENCY_GRAPH.md` §3.1).

### Consequences

- **Positive:** Zero-config end-to-end pipeline; offline; no credential surface.
- **Negative:** Final video has no synthesized voice; a real provider must be
  chosen and authorized (user escalation) to get narration.
- **Adapter seam:** `app/assembly/audio.py::AudioProvider` ABC
  (`synthesize`, `available_voices`). `SilentTrackProvider` is the default.
  Swapping to B/C/D is a `config/audio.yaml` key change — `app/assembly` never
  imports the concrete class.
- **Testing:** all pytest uses `SilentTrackProvider` (or a `SilentTrackProvider`
  subclass fixture); no external TTS is called in CI (Master Spec §27).
- **Security:** if a paid/free-tier provider is chosen, the API key is resolved
  from the vault (`Account.vault_ref`), never from config or code.

### How to revisit

Pick B/C/D → add the concrete class under `app/assembly/audio.py`, register it in
`config/audio.yaml::provider` mapping, update this ADR to Accepted & add a
Superseded-by if needed. No other module imports the audio implementation
(`DEPENDENCY_GRAPH.md` §3.1 guarantees assembly → ABC only).

### Links

- Master Spec: §23 (modular templates), §26 (escalation), §27 (testing)
- `ARCHITECTURE.md` §5.2
- `DB_SCHEMA.md` §3.4 (`Scene.narration_text`, `Scene.duration_seconds`)
- `DEPENDENCY_GRAPH.md` §3.1 (audio axis isolation)
