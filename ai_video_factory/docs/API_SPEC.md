# AI Video Factory — REST API Specification (FastAPI)

**Doc ID:** API_SPEC.md  
**Status:** Approved (Phase 1 — Planning)  
**Source:** Master Spec §4.2 (Backend), §24 (structure)  
**Related:** `docs/ARCHITECTURE.md`, `docs/DB_SCHEMA.md`

---

## 1. Overview

- **Framework:** FastAPI
- **Base URL:** `http://localhost:8890/api/v1` (matches user's web app port)
- **Auth:** API key (single-user local tool; spec §18.2)
- **Format:** JSON request/response
- **OpenAPI:** auto-generated — this doc is the human-readable contract

---

## 2. Authentication

```
POST /api/v1/config/initialize
  → Returns api_key on first setup; stored in config/secrets.yaml
Header: X-API-Key: <key>
```

All subsequent requests require the `X-API-Key` header.

---

## 3. Endpoints

### 3.1 Project

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/projects` | Create a new project |
| `GET` | `/projects` | List all projects |
| `GET` | `/projects/{id}` | Get project details + status |
| `PATCH` | `/projects/{id}` | Update project (name, topic, etc.) |
| `POST` | `/projects/{id}/start` | Begin pipeline (story → assembly) |
| `POST` | `/projects/{id}/pause` | Pause at current checkpoint |
| `POST` | `/projects/{id}/resume` | Resume from saved state |
| `POST` | `/projects/{id}/cancel` | Cancel project |
| `DELETE` | `/projects/{id}` | Soft-delete project |

**Create Project:**
```json
// POST /projects
{
  "name": "My Horror Story",
  "description": "10-minute horror about a haunted doll",
  "niche": "horror",
  "topic": "haunted doll in a Victorian house",
  "target_seconds": 600,
  "template": "horror"  // optional; defaults to niche
}
```

**Response:**
```json
{
  "id": "a1b2c3d4-...",
  "name": "My Horror Story",
  "status": "DRAFT",
  "created_at": "2026-09-22T10:00:00Z"
}
```

---

### 3.2 Scenes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/projects/{id}/scenes` | List scenes for project |
| `GET` | `/scenes/{id}` | Get scene + prompt + job details |

**Scene Detail Response:**
```json
{
  "id": "scene-uuid",
  "project_id": "proj-uuid",
  "scene_number": 3,
  "title": "The Doll Awakens",
  "description": "Clara discovers the doll's eyes follow her.",
  "narration_text": "As Clara approached the doll...",
  "target_clip_seconds": 8,
  "complexity": "MEDIUM",
  "continuity_dna": {"character": "Clara", "clothing": "blue sweater", "location": "bedroom"},
  "status": "PROMPTED",
  "prompts": [{"id": "prompt-uuid", "prompt_text": "...", "version": 1}],
  "generation_job": {
    "id": "job-uuid",
    "state": "VALID",
    "retry_count": 0,
    "download_path": "/home/.../clips/scene_003.mp4",
    "qa_result": {"passed": true, "duration_seconds": 8.1, "resolution": "1080x1920"}
  }
}
```

---

### 3.3 Generation Queue

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/queue` | List all queued jobs with status |
| `GET` | `/queue/stats` | Project-level stats (counts per state) |
| `POST` | `/queue/retry/{job_id}` | Retry a failed job (after repair) |
| `POST` | `/queue/skip/{job_id}` | Skip an optional scene |

**Queue Stats Response:**
```json
{
  "total": 75,
  "pending": 10,
  "ready": 5,
  "submitted": 2,
  "generating": 0,
  "downloaded": 30,
  "valid": 38,
  "failed": 3,
  "quota_wait": 5,
  "retry": 2
}
```

---

### 3.4 Quota & Accounts

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/accounts` | List accounts + status |
| `POST` | `/accounts` | Add new account |
| `GET` | `/quota` | Current quota snapshot |
| `POST` | `/quota/check` | Force quota refresh |

**Quota Response:**
```json
{
  "provider": "snapgen",
  "account_id": "acct-uuid",
  "daily_limit": 10,
  "used_today": 4,
  "remaining": 6,
  "reset_time": "2026-09-23T04:00:00Z",
  "last_generation": "2026-09-22T22:30:00Z",
  "account_status": "AUTHORIZED"
}
```

---

### 3.5 Provider Operations

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/provider/status` | Current provider + session health |
| `POST` | `/provider/refresh-session` | Re-establish provider session |
| `POST` | `/provider/test-connection` | Verify provider is reachable |

---

### 3.6 Final Output

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/projects/{id}/video` | Stream/download final video |
| `GET` | `/projects/{id}/qa-report` | Get QA report |
| `GET` | `/projects/{id}/manifest` | Get full project manifest (JSON) |

**Project Manifest:**
```json
{
  "project": {...},
  "scenes": [...],
  "final_video": "/home/.../output/project_a1b2_final.mp4",
  "qa_report": "/home/.../output/project_a1b2_qa.md",
  "total_clips": 75,
  "valid_clips": 72,
  "failed_clips": 3,
  "skipped_clips": 0,
  "assembly_log": "..."
}
```

---

### 3.7 WebSocket: Live Progress

```
WS /ws/projects/{id}/progress
```

Server pushes JSON updates:
```json
{
  "project_id": "uuid",
  "event": "job_state_changed",
  "job_id": "uuid",
  "old_state": "SUBMITTED",
  "new_state": "DOWNLOADED",
  "timestamp": "2026-09-22T22:30:00Z"
}
```

---

## 4. Error Handling

Standard FastAPI HTTP errors + structured body:

```json
{
  "detail": {
    "code": "QUOTA_EXHAUSTED",
    "message": "SnapGen quota exhausted. Project paused until reset.",
    "retry_after_seconds": 3600
  }
}
```

Common error codes:
- `PROJECT_NOT_FOUND`
- `QUOTA_EXHAUSTED`
- `PROVIDER_UNAVAILABLE`
- `ACCOUNT_AUTH_EXPIRED`
- `SCENE_VALID` (attempted to regenerate a valid clip)
- `REPAIR_FAILED` (retry attempted before successful repair)
