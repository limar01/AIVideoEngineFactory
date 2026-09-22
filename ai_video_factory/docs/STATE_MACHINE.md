# AI Video Factory — State Machine Design

**Doc ID:** STATE_MACHINE.md  
**Status:** Approved (Phase 1 — Planning)  
**Source:** Master Spec §11 (Generation States), §17 (Quota Manager), §22 (Retry Policy)  
**Related:** `docs/ARCHITECTURE.md`, `docs/DB_SCHEMA.md`, `docs/API_SPEC.md`

---

## 1. Generation Job State Machine

There are two state machines: **Project-level** (coarse) and **GenerationJob-level** (fine-grained).

### 1.1 Project States

| State | Meaning | Transitions |
|-------|---------|-------------|
| `DRAFT` | Created, not started | → `BUILDING` |
| `BUILDING` | Story/Scenes/Prompts being generated | → `READY_TO_GENERATE` \| → `FAILED` |
| `READY_TO_GENERATE` | All prompts ready, queue primed | → `GENERATING` \| → `QUOTA_WAIT` |
| `GENERATING` | One or more jobs actively running | → `GENERATING` \| → `QUOTA_WAIT` \| → `ASSEMBLING` \| → `FAILED` |
| `QUOTA_WAIT` | Quota exhausted, project paused | → `GENERATING` (on resume/user action) |
| `ASSEMBLING` | FFmpeg concat in progress | → `COMPLETED` \| → `FAILED` |
| `COMPLETED` | Final video assembled + validated | (terminal) |
| `FAILED` | Unrecoverable error | → `CANCELLED` (user) |
| `CANCELLED` | User cancelled | (terminal) |
| `PAUSED` | User paused manually | → `GENERATING` (on resume) |

### 1.2 GenerationJob States

| State | Meaning | Transitions |
|-------|---------|-------------|
| `PENDING` | Created, awaiting scheduling | → `READY` \| → `QUOTA_WAIT` |
| `READY` | Quota available, ready to submit | → `SUBMITTED` \| → `QUOTA_WAIT` \| → `BLOCKED` |
| `SUBMITTED` | Prompt submitted to provider | → `GENERATING` \| → `FAILED` \| → `QUOTA_WAIT` |
| `GENERATING` | Provider is generating the clip | → `COMPLETED` \| → `FAILED` |
| `COMPLETED` | Provider finished generation | → `DOWNLOADING` \| → `FAILED` |
| `DOWNLOADING` | Downloading clip file | → `DOWNLOADED` \| → `FAILED` |
| `DOWNLOADED` | Clip downloaded to local disk | → `VALIDATING` |
| `VALIDATING` | Running VideoQA checks | → `VALID` \| → `INVALID` |
| `VALID` | Clip passed all QA checks | (terminal — never regenerated) |
| `INVALID` | Clip failed QA — triggers repair | → `RETRY` \| → `FAILED` |
| `FAILED` | Irreversible failure | → `RETRY` (after repair) \| → `CANCELLED` |
| `RETRY` | Queued for retry after repair | → `READY` |
| `BLOCKED` | Waiting on external condition (auth, quota) | → `READY` \| → `SUBMITTED` (on resume) |
| `QUOTA_WAIT` | Waiting for quota reset | → `READY` (after reset_time passes) |
| `SKIPPED` | Optional scene skipped | (terminal) |
| `CANCELLED` | Project cancelled | (terminal) |

---

## 2. State Transition Rules

### 2.1 Normal Flow

```
PENDING → READY → SUBMITTED → GENERATING → COMPLETED → DOWNLOADING → DOWNLOADED
        → VALIDATING → VALID
```

### 2.2 Quota Exhaustion (spec §17)

- If `QuotaManager.check()` returns `remaining == 0`:
  - `PENDING → QUOTA_WAIT`
  - `READY → QUOTA_WAIT`
  - `SUBMITTED` stays, but polling detects `detect_quota_exhaustion()` → `QUOTA_WAIT`

- On resume (after `quota.reset_time`):
  - `QUOTA_WAIT → READY` (if quota refreshed)
  - Project state: `QUOTA_WAIT → GENERATING`

### 2.3 Repair Loop (spec §22 — Never blind retry)

```
VALIDATING → INVALID
    ↓
RepairEngine.diagnose(clip, error_details)
    ↓
IF repair possible:
    Prompt.version++ (new prompt with repairs)
    GenerationJob.state → RETRY
    ↓
    RETRY → READY → SUBMITTED → ... (one retry leg only)
    
IF max_retries reached OR repair impossible:
    GenerationJob.state → FAILED
    IF mandatory scene: Project → FAILED
    IF optional scene: Scene → SKIPPED, project continues
```

### 2.4 Recovery on Restart

`RecoveryWorker.run()` on application startup:

1. **SELECT** all `GenerationJob` rows WHERE `state IN (SUBMITTED, GENERATING, DOWNLOADING, DOWNLOADED, VALIDATING, QUOTA_WAIT, BLOCKED)`
2. **FOR EACH** job:
   a. Check `account.session_expires` — if expired, set `state = BLOCKED`.
   b. Check `quota.remaining` — if 0 and before reset_time, set `state = QUOTA_WAIT`.
   c. If `state = SUBMITTED` or `GENERATING` and account/quota OK → keep state (resume polling).
   d. If `state = GENERATING` > 30 min with no status change → set `state = FAILED` (stuck generation).
3. **Never** resume a `VALID` job — skip entirely (spec §11: "Never regenerate a valid completed scene").
4. **UPDATE** `Project` status based on aggregate job states.

---

## 3. Persistence Guarantees

- **Every state change commits to DB immediately** — no in-memory-only states.
- **`updated_at` timestamp** on `GenerationJob` updated on every transition.
- **`error_reason`** column on `GenerationJob` captures failure text for repair diagnosis.
- **`retry_count`** and **`max_retries`** enforce the retry policy at the DB level.
- **`repair_applied`** column stores what RepairEngine changed (audit trail for §22).

```sql
-- Recovery-friendly queries
SELECT * FROM generation_job WHERE state != 'VALID' AND state NOT IN ('SKIPPED', 'CANCELLED');
SELECT * FROM project WHERE status IN ('GENERATING', 'QUOTA_WAIT', 'ASSEMBLING', 'BUILDING');
```

---

## 4. Timeout Handling

| State | Timeout | Action |
|-------|---------|--------|
| `GENERATING` | 30 min | → `FAILED` (stuck) |
| `SUBMITTED` | 15 min | → check status; if still queued, → `BLOCKED` |
| `DOWNLOADING` | 5 min | → retry (network) or `FAILED` |
| `QUOTA_WAIT` | Until reset_time | Resume eligible at reset_time + 1 min |
| `BLOCKED` | Manual resolution | Wait for user to re-auth |

---

## 5. State Machine Diagram (ASCII)

```
                    ┌─────────┐
                    │ PENDING │──quota=0──> QUOTA_WAIT
                    └───┬─────┘
                        │
                    ┌───▼────┐
                    │  READY │
                    └───┬────┘
                       / \
                quota=0  │
              ┌──────────┘
              ▼
         QUOTA_WAIT
              │
     (after reset_time)
              │
              ▼
          SUBMITTED
              │
              ▼
         GENERATING
              │
          provider done
              ▼
        ┌── COMPLETED ◄──(server error)──┐
        │          │                      │
        │    download failed             │
        │          │                      │
        ▼          ▼                      │
   DOWNLOADING  FAILED                  │
        │          │                      │
        │ retry      │ repair possible?   │
        ▼          ▼   yes              │
     DOWNLOADED   RETRY ◄──             │
        │          │                     │
        ▼          ▼                     │
    VALIDATING   (loop back to READY)    │
        │                                 │
    ┌───▼───┐                             │
    │ VALID │ (terminal — never changes)  │
    └───────┘                             │
        │                                 │
        ▼                                 ▼
    INTEGRATE INTO FINAL VIDEO
```
