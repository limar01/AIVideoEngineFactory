-- AI Video Factory — Initial Schema (SQLite)
-- Source: docs/DB_SCHEMA.md §3
-- Master Spec §3.2 (SQLite for single-writer durability)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Track applied migrations
CREATE TABLE IF NOT EXISTS _migrations (
    filename TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3.1: Project aggregate root
CREATE TABLE IF NOT EXISTS project (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    niche         TEXT NOT NULL,
    topic         TEXT NOT NULL,
    target_seconds INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'DRAFT',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    started_at    TEXT,
    completed_at  TEXT,
    artifact_path TEXT,
    qa_report_path TEXT,
    deleted_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_name        ON project(name);
CREATE INDEX IF NOT EXISTS idx_project_status      ON project(status);
CREATE INDEX IF NOT EXISTS idx_project_target_secs ON project(target_seconds);
CREATE INDEX IF NOT EXISTS idx_project_deleted     ON project(deleted_at);

-- 3.2: Scene
CREATE TABLE IF NOT EXISTS scene (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL,
    scene_number       INTEGER NOT NULL,
    act_number         INTEGER,
    title              TEXT NOT NULL,
    description        TEXT NOT NULL,
    narration_text     TEXT,
    narration_seconds  REAL,
    target_clip_seconds REAL NOT NULL DEFAULT 8.0,
    complexity         TEXT CHECK (complexity IN ('LOW', 'MEDIUM', 'HIGH')),
    continuity_dna     TEXT,
    status             TEXT NOT NULL DEFAULT 'PLANNED',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES project(id)
);

CREATE INDEX IF NOT EXISTS idx_scene_project      ON scene(project_id);
CREATE INDEX IF NOT EXISTS idx_scene_project_seq  ON scene(project_id, scene_number);
CREATE INDEX IF NOT EXISTS idx_scene_status       ON scene(status);

-- 3.3: Prompt
CREATE TABLE IF NOT EXISTS prompt (
    id                TEXT PRIMARY KEY,
    scene_id          TEXT NOT NULL,
    provider          TEXT NOT NULL,
    prompt_text       TEXT NOT NULL,
    compiled_metadata TEXT,
    version           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scene_id) REFERENCES scene(id)
);

CREATE INDEX IF NOT EXISTS idx_prompt_scene       ON prompt(scene_id);
CREATE INDEX IF NOT EXISTS idx_prompt_version     ON prompt(scene_id, version);

-- 3.4: Account (authorized provider credentials)
CREATE TABLE IF NOT EXISTS account (
    id                  TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    label               TEXT,
    credentials_encrypted TEXT,
    session_state       TEXT,
    session_expires     TEXT,
    status              TEXT NOT NULL DEFAULT 'PENDING_AUTH' CHECK (status IN ('PENDING_AUTH', 'AUTHORIZED', 'AUTH_EXPIRED', 'BANNED', 'DISABLED')),
    last_used_at        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_account_provider   ON account(provider);
CREATE INDEX IF NOT EXISTS idx_account_status     ON account(status);

-- 3.5: Quota (per-account, configurable — never hard-coded)
CREATE TABLE IF NOT EXISTS quota (
    id            TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL,
    provider      TEXT NOT NULL,
    daily_limit   INTEGER NOT NULL,
    used_today    INTEGER NOT NULL DEFAULT 0,
    remaining     INTEGER NOT NULL,
    reset_time    TEXT NOT NULL,
    last_check_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_generation TEXT,
    error_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES account(id)
);

CREATE INDEX IF NOT EXISTS idx_quota_account      ON quota(account_id);
CREATE INDEX IF NOT EXISTS idx_quota_provider     ON quota(provider);

-- 3.6: Generation Job (one per scene per provider attempt)
CREATE TABLE IF NOT EXISTS generation_job (
    id                  TEXT PRIMARY KEY,
    prompt_id           TEXT NOT NULL,
    account_id          TEXT,
    provider            TEXT,
    state               TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING', 'READY', 'SUBMITTED', 'GENERATING', 'COMPLETED', 'DOWNLOADING', 'DOWNLOADED', 'VALIDATING', 'VALID', 'INVALID', 'FAILED', 'RETRY', 'QUOTA_WAIT', 'BLOCKED', 'SKIPPED', 'CANCELLED')),
    retry_count         INTEGER NOT NULL DEFAULT 0,
    max_retries         INTEGER NOT NULL DEFAULT 2,
    submitted_at        TEXT,
    generating_started_at TEXT,
    completed_at        TEXT,
    download_path       TEXT,
    error_reason        TEXT,
    error_code          TEXT,
    repair_applied      TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (prompt_id) REFERENCES prompt(id),
    FOREIGN KEY (account_id) REFERENCES account(id)
);

CREATE INDEX IF NOT EXISTS idx_job_prompt         ON generation_job(prompt_id);
CREATE INDEX IF NOT EXISTS idx_job_state          ON generation_job(state);
CREATE INDEX IF NOT EXISTS idx_job_account        ON generation_job(account_id);

-- 3.7: Retry Attempt (audit trail for repair-over-retry)
CREATE TABLE IF NOT EXISTS retry_attempt (
    id                TEXT PRIMARY KEY,
    generation_job_id TEXT NOT NULL,
    attempt_number    INTEGER NOT NULL,
    prompt_version    INTEGER NOT NULL,
    repair_description TEXT,
    result            TEXT CHECK (result IN ('SUCCESS', 'FAILED')),
    error_reason      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (generation_job_id) REFERENCES generation_job(id)
);

CREATE INDEX IF NOT EXISTS idx_retry_job          ON retry_attempt(generation_job_id);

-- 3.8: QA Result
CREATE TABLE IF NOT EXISTS qa_result (
    id                  TEXT PRIMARY KEY,
    generation_job_id   TEXT NOT NULL,
    clip_path           TEXT NOT NULL,
    duration_seconds    REAL,
    expected_min        REAL,
    expected_max        REAL,
    resolution          TEXT,
    aspect_ratio        TEXT,
    codec               TEXT,
    has_audio           INTEGER,
    file_size_bytes     INTEGER,
    black_frame_ratio   REAL,
    corruption_detected INTEGER NOT NULL DEFAULT 0,
    passed              INTEGER NOT NULL DEFAULT 0,
    failure_details     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (generation_job_id) REFERENCES generation_job(id)
);

CREATE INDEX IF NOT EXISTS idx_qa_job             ON qa_result(generation_job_id);

-- 3.9: Download tracking
CREATE TABLE IF NOT EXISTS download (
    id                  TEXT PRIMARY KEY,
    generation_job_id   TEXT NOT NULL,
    url                 TEXT,
    local_path          TEXT NOT NULL,
    file_size_bytes     INTEGER,
    download_started    TEXT,
    download_completed  TEXT,
    checksum            TEXT,
    status              TEXT NOT NULL DEFAULT 'PENDING',
    error_reason        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (generation_job_id) REFERENCES generation_job(id)
);

CREATE INDEX IF NOT EXISTS idx_download_job       ON download(generation_job_id);
CREATE INDEX IF NOT EXISTS idx_download_status    ON download(status);
