# AI Video Factory — Database Schema (SQLite)

**Doc ID:** DB_SCHEMA.md  
**Status:** Approved (Phase 1 — Planning)  
**Source:** Master Spec §6 (task contract models), §11, §17  
**Related:** `docs/ARCHITECTURE.md`, `docs/API_SPEC.md`

---

## 1. Design Principles

1. **Single database file** — SQLite at `database/factory.db`. WAL mode for concurrent reads.
2. **All generation states persisted** — Master Spec §11. A restart never loses state.
3. **No hard-coded provider limits** — quota comes from the `Quota` table (Master Spec §2, §17).
4. **One row per scene** — the `GenerationJob` is the work unit; one job per scene per account attempt.
5. **Artifacts referenced, not stored in DB** — clips live in `projects/{project_id}/clips/`, paths stored in DB.
6. **Soft deletes** — `deleted_at` columns; never hard-delete a clip row.

---

## 2. Entity-Relationship Overview

```
Project (1) ──< Scene (1) ──< Prompt (1) ──< GenerationJob (1) ──< Download (1)
                          │                          ├──< QAResult
                          │                          └──< RetryAttempt
Project (1) ──< Account (1) ──< Quota (1) ──< GenerationJob
```

---

## 3. Table Definitions

### 3.1 Project

```sql
CREATE TABLE project (
    id              TEXT PRIMARY KEY,      -- UUID
    name            TEXT NOT NULL,
    description     TEXT,
    niche           TEXT NOT NULL,        -- "horror", "comedy", ..."
    topic           TEXT NOT NULL,
    target_seconds  INTEGER NOT NULL,     -- e.g. 600
    status          TEXT NOT NULL DEFAULT 'DRAFT', -- DRAFT|BUILDING|GENERATING|ASSEMBLING|COMPLETED|FAILED|CANCELLED
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at      TIMESTAMP,            -- first generation job created
    completed_at    TIMESTAMP,            -- final video validated
    artifact_path   TEXT,                 -- path to final video
    qa_report_path  TEXT,                 -- path to QA report
    deleted_at      TIMESTAMP
);
```

### 3.2 Scene

```sql
CREATE TABLE scene (
    id              TEXT PRIMARY KEY,      -- UUID
    project_id      TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    scene_number    INTEGER NOT NULL,     -- 1-based within project
    act_number      INTEGER,              -- nullable if no act structure
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,        -- what happens in this scene
    narration_text  TEXT,                 -- voice-over text
    narration_seconds REAL,               -- derived from audio/adapter
    target_clip_seconds REAL NOT NULL,    -- 8 recommended (spec §19)
    complexity      TEXT,                 -- LOW|MEDIUM|HIGH (for optimizer)
    continuity_dna  JSONB,                -- character/clothing/prop/location snapshot (spec §20)
    status          TEXT NOT NULL DEFAULT 'PLANNED', -- PLANNED|PROMPTED|GENERATED|SKIPPED|FAILED
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_scene_project ON scene(project_id, scene_number);
```

### 3.3 Prompt

```sql
CREATE TABLE prompt (
    id              TEXT PRIMARY KEY,      -- UUID
    scene_id        TEXT NOT NULL REFERENCES scene(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,        -- "snapgen", "runway", etc.
    prompt_text     TEXT NOT NULL,        -- the actual prompt sent to provider
    compiled_metadata JSONB,              -- scene DNA baked into prompt
    version         INTEGER NOT NULL DEFAULT 1,   -- incremented on each repair (spec §22)
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_prompt_scene ON prompt(scene_id);
```

### 3.4 Account

```sql
CREATE TABLE account (
    id              TEXT PRIMARY KEY,      -- UUID
    provider        TEXT NOT NULL,        -- "snapgen"
    label           TEXT,                 -- user-friendly name
    credentials_encrypted TEXT,            -- encrypted credentials (spec §18.2 / Security Agent)
    session_state   TEXT,                 -- serialized session (cookies, tokens)
    session_expires TIMESTAMP,            -- when session is valid through
    status          TEXT NOT NULL DEFAULT 'PENDING_AUTH', -- PENDING_AUTH|AUTHORIZED|AUTH_EXPIRED|BANNED|DISABLED
    last_used_at    TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_account_provider_status ON account(provider, status);
-- Only one authorized account per provider at a time (per spec §2)
CREATE UNIQUE INDEX uq_account_provider ON account(provider, status) WHERE status = 'AUTHORIZED';
```

### 3.5 Quota

```sql
CREATE TABLE quota (
    id              TEXT PRIMARY KEY,      -- UUID
    account_id      TEXT NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    daily_limit     INTEGER NOT NULL,     -- from provider; NOT hard-coded in code
    used_today      INTEGER NOT NULL DEFAULT 0,
    remaining       INTEGER NOT NULL,     -- daily_limit - used_today
    reset_time      TIMESTAMP NOT NULL,   -- when used_today resets to 0
    last_check_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_generation TIMESTAMP,
    error_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_quota_account ON quota(account_id);
CREATE INDEX idx_quota_reset ON quota(reset_time);
```

### 3.6 GenerationJob

```sql
-- Master Spec §11 state machine
CREATE TABLE generation_job (
    id              TEXT PRIMARY KEY,      -- UUID
    prompt_id       TEXT NOT NULL REFERENCES prompt(id) ON DELETE CASCADE,
    account_id      TEXT,                  -- nullable; set when submitted
    provider        TEXT,                  -- snapshot of provider at creation
    state           TEXT NOT NULL DEFAULT 'PENDING',
        -- PENDING|READY|SUBMITTED|GENERATING|COMPLETED|DOWNLOADING|DOWNLOADED|
        -- VALIDATING|VALID|FAILED|RETRY|QUOTA_WAIT|BLOCKED|SKIPPED|CANCELLED
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 2,    -- configurable (spec §22)
    submitted_at    TIMESTAMP,
    generating_started_at TIMESTAMP,
    completed_at    TIMESTAMP,
    download_path   TEXT,                  -- path to downloaded clip
    error_reason    TEXT,                  -- if FAILED
    error_code      TEXT,                  -- provider-specific error code
    repair_applied  TEXT,                  -- what RepairEngine changed
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_job_state ON generation_job(state);
CREATE INDEX idx_job_prompt ON generation_job(prompt_id);
CREATE INDEX idx_job_account ON generation_job(account_id);
```

### 3.7 RetryAttempt

```sql
CREATE TABLE retry_attempt (
    id              TEXT PRIMARY KEY,      -- UUID
    generation_job_id TEXT NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE,
    attempt_number  INTEGER NOT NULL,
    prompt_version  INTEGER NOT NULL,      -- which prompt version was tried
    repair_description TEXT,              -- what was changed
    result          TEXT,                  -- SUCCESS|FAILED
    error_reason    TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_retry_job ON retry_attempt(generation_job_id);
```

### 3.8 QAResult

```sql
CREATE TABLE qa_result (
    id              TEXT PRIMARY KEY,      -- UUID
    generation_job_id TEXT NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE,
    clip_path       TEXT NOT NULL,
    duration_seconds REAL,
    expected_min    REAL,                  -- from scene.target_clip_seconds
    expected_max    REAL,
    resolution      TEXT,                  -- "1080x1920" etc.
    aspect_ratio    TEXT,                  -- "9:16"
    codec           TEXT,
    has_audio       BOOLEAN,
    file_size_bytes INTEGER,
    black_frame_ratio REAL,               -- percentage of black frames
    corruption_detected BOOLEAN,
    passed          BOOLEAN NOT NULL,
    failure_details JSONB,                 -- structured failure reasons
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_qa_job ON qa_result(generation_job_id);
```

### 3.9 Download

```sql
CREATE TABLE download (
    id              TEXT PRIMARY KEY,      -- UUID
    generation_job_id TEXT NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE,
    url             TEXT,                  -- source URL
    local_path      TEXT NOT NULL,
    file_size_bytes INTEGER,
    download_started TIMESTAMP,
    download_completed TIMESTAMP,
    checksum        TEXT,                  -- sha256 of downloaded file
    status          TEXT NOT NULL,         -- PENDING|DOWNLOADING|COMPLETED|FAILED
    error_reason    TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_download_job ON download(generation_job_id);
```

---

## 4. Migrations

Migrations live in `database/migrations/` as numbered SQL files:

```
database/migrations/
├── 001_initial_schema.sql       -- core tables
├── 002_add_retry_attempt.sql    -- retry tracking
├── 003_add_download_table.sql    -- download tracking
├── 004_add_qa_failure_json.sql   -- structured QA failures
└── 005_add_continuity_dna.sql     -- spec §20 continuity
```

Each migration is idempotent and forward-only. `alembic` is the recommended migration tool.

---

## 5. ORM Model Mapping (SQLModel / Pydantic v2)

```python
# app/core/models.py (summary — see DB_SCHEMA.md §3 for full schema)

class Project(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=uuid4)
    name: str
    niche: str
    topic: str
    target_seconds: int
    status: str = "DRAFT"
    # ... timestamps, artifact_path, qa_report_path

class Scene(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=uuid4)
    project_id: str = Field(foreign_key="project.id")
    scene_number: int
    narration_text: Optional[str] = None
    target_clip_seconds: float
    complexity: Optional[str] = None
    continuity_dna: Optional[dict] = None
    status: str = "PLANNED"

class Prompt(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=uuid4)
    scene_id: str = Field(foreign_key="scene.id")
    prompt_text: str
    version: int = 1

class GenerationJob(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=uuid4)
    prompt_id: str = Field(foreign_key="prompt.id")
    account_id: Optional[str] = None
    state: str = "PENDING"
    retry_count: int = 0
    max_retries: int = 2

# ... Account, Quota, QAResult, Download, RetryAttempt
```

---

## 6. Recovery Semantics

On application restart, `RecoveryWorker` (see `docs/STATE_MACHINE.md`) performs:

1. Load all `GenerationJob` rows with state in (`SUBMITTED`, `GENERATING`, `DOWNLOADING`, `DOWNLOADED`, `VALIDATING`).
2. For each: check `account.session_expires` and `quota.remaining` / `quota.reset_time`.
3. If account still authorized + quota > 0: resume in current state.
4. If account expired or quota exhausted: set state to `QUOTA_WAIT` or `BLOCKED`.
5. Skip any job in `VALID` state — never regenerate (Master Spec §11: "Never regenerate a valid completed scene").
6. Reconcile `quota.used_today` against `reset_time` — if reset_time has passed, set `used_today = 0`, `remaining = daily_limit`.
