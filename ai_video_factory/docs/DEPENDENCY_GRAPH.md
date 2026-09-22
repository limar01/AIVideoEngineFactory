# AI Video Factory — Dependency Graph & Task Breakdown

**Doc ID:** DEPENDENCY_GRAPH.md  
**Status:** Approved (Phase 1 — Planning)  
**Source:** Master Spec §7 (Dependency Graph), §8 (Phases), §5 (Task Routing)  
**Related:** `docs/ARCHITECTURE.md`, `tasks.json`

---

## 1. Task Dependency Graph

From Master Spec §7, with additional tasks identified from the 3 user decisions and SnapGen recon.

```
ARCH-001 (Architecture — Phase 1)
  ├── DB-001 (Database Schema)
  │     └── BACKEND-001 (Project Persistence)
  ├── API-001 (REST API Contract)
  │     └── BACKEND-002 (API Implementation)
  ├── AI-001 (Story Engine + Data Models)
  │     └── PROMPT-001 (Prompt Compiler)
  │           └── SNAPGEN-001 (SnapGen Provider)
  ├── PROVIDER-000 (SnapGen Browser Recon — Spike)
  │     └── SNAPGEN-001 (SnapGen Provider)
  ├── AUDIO-001 (Audio/Narration Adapter)
  │     └── ASSEMBLY-001 (FFmpeg Assembly)
  ├── VIDEO-001 (FFmpeg Module)
  │     └── ASSEMBLY-001 (FFmpeg Assembly)
  └── SECURITY-001 (Credential/Secret Architecture)
        └── BACKEND-003 (Account/Quota Management)

BACKEND-001 (Project Persistence)
  └── QUEUE-001 (Job Queue Service)
        └── INTEGRATION-001 (E2E Integration)

QUEUE-001 (Job Queue Service)
  └── SNAPGEN-001 (SnapGen Provider)

AI-001 (Story Engine)
  └── PROMPT-001 (Prompt Compiler)
        └── SNAPGEN-001 (SnapGen Provider)

VIDEO-001 (FFmpeg Module)
  └── ASSEMBLY-001 (FFmpeg Assembly)
        └── INTEGRATION-001 (E2E Integration)

INTEGRATION-001 (E2E Integration)
  └── QA-001 (Full Test Suite)

QA-001 (Full Test Suite)
  └── RELEASE-001 (Release)
```

---

## 2. Phase Execution Plan

### Phase 1 — Planning (in-progress)

| Task | Owner | Status |
|------|-------|--------|
| ARCH-001 | Architecture Agent | ✅ Complete |
| DB-001 | Architecture Agent | ✅ Complete |
| API-001 | Architecture Agent | ✅ Complete |
| PROVIDER_IFACE-001 | Architecture Agent | ✅ Complete |
| STATE MACHINE | Architecture Agent | ✅ Complete |
| PROVIDER-000 (SnapGen recon) | Browser Automation Agent | ⏳ Pending (needs SnapGen URL confirmation) |
| DECISION-STORY | User | ✅ Resolved (Hermes-generated, free) |
| DECISION-AUDIO | User | ✅ Resolved (local Piper TTS, adapter pattern) |
| DECISION-UI | User | ✅ Resolved (MVP CLI → REST API, not full React) |

### Phase 2 — Foundation (next, can run in parallel)

| Task | Owner | Dependencies |
|------|-------|-------------|
| BACKEND-001 | Backend Agent | DB-001 |
| BACKEND-002 | Backend Agent | API-001 |
| BACKEND-003 | Backend Agent | SECURITY-001 |
| FRONTEND-001 | Frontend Agent | API-001 (contract only) |
| AI-001 | AI Content Agent | ARCH-001 |
| VIDEO-001 | Video Processing Agent | ARCH-001 |
| SECURITY-001 | Security Agent | ARCH-001 |

### Phase 3 — Core Engine

| Task | Owner | Dependencies |
|------|-------|-------------|
| STORY-001 | AI Content | AI-001 |
| CHARACTER-001 | AI Content | STORY-001 |
| VISUAL-001 | AI Content | CHARACTER-001 |
| SCENE-001 | AI Content | VISUAL-001 |
| PROMPT-001 | AI Content | SCENE-001 |
| QUEUE-001 | Backend | BACKEND-001 |
| QUOTA-001 | Backend | QUEUE-001 |

### Phase 4 — Provider

| Task | Owner | Dependencies |
|------|-------|-------------|
| SNAPGEN-001 | Browser Automation | PROMPT-001, PROVIDER-000 |
| MOCK-001 | Browser Automation | PROVIDER_INTERFACE-001 |

Tests use `MockVideoProvider` only until mock tests pass.

### Phase 5 — Integration

| Task | Owner | Dependencies |
|------|-------|-------------|
| INTEGRATION-001 | Integration Agent | QUEUE-001, PROMPT-001, SNAPGEN-001, VIDEO-001 |

### Phase 6 — QA

| Task | Owner | Dependencies |
|------|-------|-------------|
| QA-001 | QA Agent | INTEGRATION-001 |

### Phase 7 — Release

| Task | Owner | Dependencies |
|------|-------|-------------|
| RELEASE-001 | Personal Agent | QA-001, SECURITY-001 |

---

## 3. Parallel Opportunities

**Phase 2 can run fully in parallel:**
- Backend (3 tasks) has no internal dependencies during foundation
- Frontend only needs the API contract (not implementation)
- AI, Video, Security are independent modules

**Phase 3 can partially parallelize:**
- STORY-001 → CHARACTER-001 → VISUAL-001 (sequential chain)
- SCENE-001 can start once STORY is ready
- QUEUE-001 can start once BACKEND-001 is done

**Phase 6 testing strategy:**
- Unit tests: run as each module completes
- Integration tests: require INTEGRATION-001 complete
- End-to-end tests: require QA-001 complete
- All provider tests use `MockVideoProvider` — no real quota consumed

---

## 4. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| SnapGen URL/provider unknown | High | Blocks Phase 4 | PROVIDER-000 spike first |
| Architecture Agent stalled (incomplete docs) | Medium | Blocks Phases 2+ | Personal Agent writes remaining docs directly |
| Story engine generates inconsistent scenes | Medium | High | Character/Visual Bible + continuity DNA (Scene model) |
| Quota exhaustion mid-generation | High | Medium | State machine QUOTA_WAIT + resume |
| Corrupt downloads | Medium | Medium | VideoQA + retry/repair |
| Visual drift across 75 clips | High | High | Continuity DNA baked into every prompt (§20) |
| ffmpeg concat failures | Low | Medium | Pre-validate all clips (codec/res/fmt) |

---

## 5. Critical Path

```
ARCH-001 → DB-001 → BACKEND-001 → QUEUE-001 → INTEGRATION-001 → QA-001 → RELEASE-001
                     ↘
AI-001 → STORY-001 → CHARACTER-001 → VISUAL-001 → SCENE-001 → PROMPT-001 → SNAPGEN-001
                                                                                   ↘
VIDEO-001 → ASSEMBLY-001 ────────────────────────────────────────────────────────→
```

The critical path is ~10 tasks. Parallelizable width is ~4 tasks at Phase 2 peak.
