# AI Video Factory — System Architecture

**Doc ID:** ARCHITECTURE.md
**Status:** Approved (Phase 1 — Planning)
**Source:** Master Spec v1.0 §4, §9–§11, §17–§27
**Related:** `docs/DB_SCHEMA.md`, `docs/API_SPEC.md`, `docs/PROVIDER_INTERFACE.md`, `docs/STATE_MACHINE.md`, `docs/DEPENDENCY_GRAPH.md`, `adr/*`

---

## 1. Purpose & Scope

This document defines the system architecture for the AI Video Factory: a modular, free-tier-only pipeline that turns a one-line request ("Create a 10-minute horror story.") into a final, validated video. It covers module boundaries, the layered process flow, the database-backed state machine, the REST API surface, and the provider abstraction that keeps SnapGen (and any real provider) isolated and mock-testable.

**Non-goals:** implementation of the React UI (FRONTEND-001), the real SnapGen provider (PROVIDER-000/SNAPGEN-001), or the external story-engine LLM (AI-001/DECISION-STORY). Those live behind adapter contracts documented here so this design stays agnostic until user decisions are recorded.

---

## 2. Mandates (from Master Spec)

| # | Rule | How it is encoded |
|---|------|-------------------|
| 1 | **Free-tier only — no ToS bypass** | `Account.status` enum; `Quota` reset-time driven; no hard-coded limits (spec §17). All provider counts come from `Quota` table / `get_quota()`. |
| 2 | **Authorized Account Pool, not circumvention** | §17 — accounts must be user-authorized; provider rules honored. No rotation of credentials to exceed limits. |
| 3 | **Provider limits configurable** | `config/quota.yaml` + DB `Quota` rows; `QuotaManager` reads both. Code never assumes "10/day". |
| 4 | **Mock-first provider testing** | `MockVideoProvider` implements the same `VideoGenerationProvider` ABC. Integration & QA use the mock; real providers are opt-in and isolated (§27, §4.4). |
| 5 | **Resumable state machine** | All states persisted in `GenerationJob.state`; on startup `RecoveryWorker` reconciles running jobs against `Quota` + `Account` and resumes. Never regenerates a `VALID` clip (§11). |
| 6 | **Repair-over-retry logic** | Failure → `RepairEngine` mutates the `Prompt` (simplify action/camera, reduce characters, fix continuity) → single `RETRY` leg → only re-submit after a successful repair diagnosis (§22). Blind retries are forbidden. |

---

## 3. Module Map (process boundaries)

Modules live under `app/`. Each maps to a specialist-agent ownership boundary from Master Spec §4.

```
app/
├── api/          → API routes (FastAPI routers). OWNER: Backend Agent.
├── core/         → Config, settings, errors, constants, the ProviderRegistry. OWNER: Backend.
├── providers/     → VideoGenerationProvider ABC + Mock + concrete providers. OWNER: Browser Automation / Backend.
├── accounts/      → Authorized Account Pool + session lifecycle. OWNER: Security / Browser.
├── quota/         → QuotaManager + persisted Quota rows. OWNER: Backend.
├── story/         → StoryEngineAdapter + character bible + visual bible. OWNER: AI Content.
├── scenes/        → ScenePlanner, SceneOptimizer, continuity DNA. OWNER: AI Content.
├── prompts/       → Prompt model + PromptCompiler + PromptQA. OWNER: AI Content.
├── queue/         → GenerationQueue + scheduler + RepairEngine. OWNER: Backend.
├── downloader/    → DownloadManager + clip storage. OWNER: Backend.
├── qa/            → VideoQA (ffmpeg-based clip validation) + QAResult. OWNER: QA / Video.
├── assembly/      → FFmpegAssembler + final validation. OWNER: Video.
├── project/       → Project aggregate + lifecycle service. OWNER: Backend.
└── ui/            → (future) React dashboard + CLI shim. OWNER: Frontend.
```

**Cross-module coupling rule:** modules communicate *only* across the documented adapter interfaces (App Core → Provider Core, App Core → Story Adapter, CLI/UI → App Core API). No module imports another's private internals; shared state flows through the DB + the App Core service layer.

---

## 4. Layered Process Architecture

The pipeline in Master Spec §10 is realized as a **state-driven layer cake**. Each layer is a service with a single entry point `run(project_id)` and is itself resumable.

```
┌────────────────────────────────────────────┐
│ Layer 8  Assembly            (app/assembly) │
├────────────────────────────────────────────┤
│ Layer 7  Video QA           (app/qa)        │
├────────────────────────────────────────────┤
│ Layer 6  Retry / Repair     (app/queue.RepairEngine)│
├────────────────────────────────────────────┤
│ Layer 5  Download Manager   (app/downloader)│
├────────────────────────────────────────────┤
│ Layer 4  Provider Adapter   (app/providers)  │
├────────────────────────────────────────────┤
│ Layer 3  Quota Manager      (app/quota)     │
├────────────────────────────────────────────┤
│ Layer 2  Prompt Compiler    (app/prompts)   │
├────────────────────────────────────────────┤
│ Layer 1  Story Engine      (app/story)      │
└────────────────────────────────────────────┘
      ↓  orchestrated by GenerationCoordinator (core)
```

**Orchestrator.** `app/core/orchestrator.py::GenerationCoordinator` owns the *project-level* state machine (see `docs/STATE_MACHINE.md`) and drives layers 1→8 in sequence, persisting after each step. It is the only component that mutates cross-layer state, which keeps layer ordering testable and the design agnostic to which concrete story engine or provider is plugged in.

---

## 5. Adapter Pattern: Design Agnosticism

Three user-decision axes (audio, story engine, UI scope) are isolated behind adapters so ARCH-001 can be approved before they are resolved. Each adapter has a default (free-tier, no external API) and a real implementation slot.

### 5.1 Story Engine Adapter (`app/story/engine.py`)
- **Interface** `StoryEngine`: `generate_story(topic, niche, target_seconds) → StoryDoc`; `generate_character_bible(story) → BibleDoc`; `generate_visual_bible(story, bible) → VisualBible`.
- **Default (free, pending DECISION-STORY):** `HermesStoryEngine` — builds the story from modular niche templates in `config/templates/` (Horror, Comedy, … §23). No external API call, so the pipeline end-to-end works without an LLM key.
- **Real:** `OpenAIStoryEngine`, `GeminiStoryEngine` — swap via `config/story.yaml::engine` (ADR-0002).
- **Persistence:** the returned `StoryDoc`/`Bible`/`VisualBible` are serialized to the Project's artifact folder and a `Prompt`-linked row, so a restart never re-runs the story layer for a completed project.

### 5.2 Audio Adapter (`app/assembly/audio.py`)
- **Interface** `AudioProvider`: `synthesize(scene, text, voice) → TrackPath`; `available_voices() → list`.
- **Default (free, pending DECISION-AUDIO):** `SilentTrackProvider` — produces a muted track matching scene duration so assembly proceeds; `PiperLocalProvider` stub reserved (local binary, no quota).
- **Real:** `ElevenLabsProvider`, `OpenAITTSProvider` (ADR-0001).
- `NarrationStyle` + per-scene timing metadata is captured in the `Scene` model so whichever adapter is chosen, scene durations already carry narration intent.

### 5.3 UI Adapter (`app/ui/adapter.py`)
- The backend exposes a pure FastAPI API (§`docs/API_SPEC.md`). The UI is a consumer.
- **MVP path (pending DECISION-UI):** `CLIDashboard` — a Typer CLI that drives the REST API; no React build required to run a full pipeline.
- **Full path:** React+TypeScript dashboard (Frontend Agent, FRONTEND-001).
- Either UI talks only to the documented REST endpoints, so the UI decision cannot drift the backend contract.

### 5.4 Provider Adapter (`app/providers/`)
- `VideoGenerationProvider` ABC (§`docs/PROVIDER_INTERFACE.md`, 10 methods).
- `MockVideoProvider` — deterministic fake used by all automated tests (spec §27).
- `SnapGenProvider` — isolated under `app/providers/snapgen/` and imported only when `config/providers.yaml::provider == snapgen`; never imported by the test path.

---

## 6. Data Flow (single scene)

```
Project ──create──> ScenePlan ──> [optimize + continuity] ──> Prompt
   │                                                         │
   │                                                         v
   │            QuotaManager.check() ──ok──> GenerationQueue.enqueue(Prompt)
   │                                                        │
   │           GenerationJob(PENDING)                       │
   │                                                        v
   │            ProviderAdapter.submit_generation(prompt)   │
   │            state: SUBMITTED ──poll──> GENERATING        │
   │                                                        │
   └──────── RecoveryCoordinator.resume() <────────────────┘
                                                             v
        if GENERATING/COMPLETED ──download──> DOWNLOADING ─> DOWNLOADED
                                                             v
        VideoQA.validate(clip) ──fail──> RepairEngine.fix(prompt) ──RETRY
                                 ──ok──> VALID
        if QuotaExhausted ──> QUOTA_WAIT (project paused, resumes later)
```

See `docs/STATE_MACHINE.md` for the full transition table including pause/resume and repair legs.

---

## 7. Core Cross-Cutting Concerns

### 7.1 Persistence & Transactions
- SQLite (`database/app.db`) via SQLAlchemy Core / `aiosqlite` for async FastAPI.
- All layer outputs are written inside the same DB transaction that advances the state machine, so a crash mid-layer leaves a consistent, recoverable row.
- Artifact files (clips, story JSON, prompts) live under `projects/<project_id>/artifacts/` keyed by `GenerationJob.id` so re-runs are idempotent.

### 7.2 Security (Security Agent, §4.8)
- Provider credentials NEVER touch the DB. Sessions are held in the `BrowserSessionManager` (a Playwright context) or a credentials vault abstraction.
- `Account` rows store only a display label + quota metadata + `last_used` — the auth tokens live in an OS keychain abstraction injected at runtime (ADR-0010 placeholder).
- All logs are redacted of any `api_key`, `token`, or `password` field via `core/log.py`.

### 7.3 Concurrency Model
- FastAPI runs on Uvicorn with a background task worker pool (`asyncio.Semaphore`-gated by `config/quota.yaml::max_concurrent`).
- A single `GenerationCoordinator` coroutine holds the project lock per `project_id`; quota exhaustion is communicated project-wide via `QuotaEventBus`.

### 7.4 Configuration
- `config/*.yaml` — non-secret operational config. Schema in `docs/STATE_MACHINE.md` notes where quota/story/provider knobs live. Secrets come from env / vault, never from `config/`.

---

## 8. Failure Handling Matrix

| Failure mode | Detection | Response | State move |
|---|---|---|---|
| Provider quota exhausted (free tier) | `detect_quota_exhaustion()` | Stop project, mark jobs `QUOTA_WAIT` | Project paused |
| Clip too short / corrupt / wrong codec | `VideoQA.validate()` | `RepairEngine` simplifies prompt | `FAILED → RETRY → SUBMITTED` |
| Network error mid-download | `download_result()` raises | idempotent re-download | `DOWNLOADING` stays |
| Session expired / 2FA challenged | `check_session()` / `detect_error()` | halt + escalate to user | `BLOCKED` + notify |
| Mandatory scene fails after N repairs | `RetryTracker` | Mark scene `FAILED`, mark project `FAILED` | terminal |
| Optional scene fails after N repairs | `RetryTracker` | Drop scene, continue assembly | skipped in assembly |

"Repair-over-retry" is encoded once in `RepairEngine` so no layer duplicates the retry policy.

---

## 9. Technology Stack (concrete)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| API | Python 3.12 + FastAPI + Uvicorn | spec §9, async, OpenAPI auto-gen |
| DB | SQLite (SQLAlchemy Core) | spec §9, single-file, restart-safe |
| Browser | Playwright (Chromium) | spec §9, SnapGen isolation |
| Video | FFmpeg (CLI via subprocess) | spec §9 |
| Queue | In-process `asyncio` + SQLite persistence | no extra broker; free tier |
| Tests | pytest + MockVideoProvider | spec §27 |
| Config | YAML (PyYAML) | spec §9 |
| Future UI | React + TypeScript | spec §9, behind adapter |

---

## 10. Boundaries with Specialist Agents

| Agent | Delivers against this doc | Consumes |
|-------|---------------------------|----------|
| Backend | `DB_SCHEMA`, `API_SPEC` → persistence, queue, quota | §3 modules, `core` |
| Frontend | `API_SPEC` → React dashboard or CLI MVP | `API_SPEC`, `STATE_MACHINE` |
| AI Content | story/scenes/prompts data models | adapter §5.1, `DB_SCHEMA` |
| Browser Automation | `PROVIDER_INTERFACE` → SnapGenProvider | `PROVIDER_INTERFACE` |
| Video Processing | FFmpeg integration | state machine §`STATE_MACHINE` |
| QA | tests against every layer | MockVideoProvider, `API_SPEC` |
| Security | credential/session model | §7.2, ADR-0010 |
| Integration | end-to-end wiring | all of the above |

---

## 11. Document Map

| Concern | Doc |
|--------|-----|
| This architecture | `ARCHITECTURE.md` (this file) |
| Database & schema | `DB_SCHEMA.md` |
| REST API contract | `API_SPEC.md` |
| Provider interface | `PROVIDER_INTERFACE.md` |
| State machine | `STATE_MACHINE.md` |
| Dependency graph | `DEPENDENCY_GRAPH.md` |
| Pending decisions | `adr/0001-…`, `adr/0002-…`, `adr/0003-…` |
| ADR format | `adr/ADR_TEMPLATE.md` |
