# AI Video Factory — Provider Interface

**Doc ID:** PROVIDER_INTERFACE.md
**Status:** Approved (Phase 1 — Planning)
**Source:** Master Spec §18 (Provider Abstraction), §2 (Free-Tier Rules), §27 (Testing Strategy); consumes `docs/ARCHITECTURE.md`, `docs/DB_SCHEMA.md`
**Produces for:** PROVIDER-001 (interface), SNAPGEN-001 (SnapGenProvider), QA-001 (mock tests)

---

## 1. Design Mandate

The provider abstraction exists to satisfy three mandates from the Master Spec:

1. **Free-tier compliance (§2):** No bypass of quotas, CAPTCHA, 2FA, rate
   limits, or ToS. Multiple accounts are permitted **only** where the provider
   explicitly allows it.
2. **Authorized Account Pool:** Provider limits must be configurable; never
   hard-code assumptions such as "10 videos per day" anywhere in code.
3. **Mock-first testing (§27):** All automated tests use `MockVideoProvider`;
   real providers are opt-in and isolated behind a lazy import.

The contract is an **Abstract Base Class** (`VideoGenerationProvider`,
`app/providers/base.py`). Both `MockVideoProvider` and `SnapGenProvider`
implement exactly these 10 methods. No module between `core/` and `providers/`
may import a concrete provider by name — resolution goes through the
`ProviderRegistry` keyed by string (`config/providers.yaml::provider`).

---

## 2. The 10-Method Interface

```python
# app/providers/base.py
import abc
from typing import Optional

class VideoGenerationProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    # 1
    @abc.abstractmethod
    def authenticate(self, account) -> AuthResult: ...
    # 2
    @abc.abstractmethod
    def check_session(self) -> bool: ...
    # 3
    @abc.abstractmethod
    def get_capabilities(self) -> Capabilities: ...
    # 4
    @abc.abstractmethod
    def get_quota(self) -> QuotaInfo: ...
    # 5
    @abc.abstractmethod
    def submit_generation(self, prompt, context) -> ProviderJob: ...
    # 6
    @abc.abstractmethod
    def get_generation_status(self, provider_job_id: str) -> JobStatus: ...
    # 7
    @abc.abstractmethod
    def download_result(self, provider_job_id: str, dest) -> str: ...
    # 8
    @abc.abstractmethod
    def detect_error(self, provider_job_id: str) -> Optional[ErrorDetail]: ...
    # 9
    @abc.abstractmethod
    def detect_quota_exhaustion(self, error) -> bool: ...
    # 10
    @abc.abstractmethod
    def close_session(self) -> None: ...
```

> This is the **exact** 10-method set from Master Spec §18. Signatures below
> bind those names to concrete parameter types; the type names live in
> `app/providers/types.py` and mirror `DB_SCHEMA.md` fields.

### 2.1 Method reference

| # | Method | Signature (bound) | Purpose |
|---|--------|-------------------|---------|
| 1 | `authenticate` | `authenticate(account: Account) -> AuthResult` | Start an authorized provider session for the account (browser login / token). Returns `requires_user_interaction=True` when 2FA/CAPTCHA is pending — the caller then **escalates to the user** (§26); the provider never solves challenges. |
| 2 | `check_session` | `check_session() -> bool` | Return True if the session is live & authenticated. Raise `SessionExpired` if not (drives `blocked` state). |
| 3 | `get_capabilities` | `get_capabilities() -> Capabilities` | Return supported models / resolutions / aspect-ratios / durations / max prompt length. Used by the PromptCompiler to constrain prompts so they are submission-ready. |
| 4 | `get_quota` | `get_quota() -> QuotaInfo` | Fetch the live free-tier quota status (`daily_limit`, `used_today`, `remaining`, `reset_time`). Does **not** mutate the DB `Quota` table; `QuotaManager` persists the result. Never hard-codes a limit. |
| 5 | `submit_generation` | `submit_generation(prompt: CompiledPrompt, context: SubmitContext) -> ProviderJob` | Submit one provider-ready prompt + parameters. Returns the opaque `provider_job_id` assigned by the provider. |
| 6 | `get_generation_status` | `get_generation_status(provider_job_id: str) -> JobStatus` | Poll one job. Maps provider status → `{running, completed, failed}`. |
| 7 | `download_result` | `download_result(provider_job_id: str, dest: Path) -> str` | Download the finished clip to `dest`. **Idempotent** — skip if file exists and is non-empty (Master Spec §11: never regenerate a valid clip). |
| 8 | `detect_error` | `detect_error(provider_job_id: str) -> Optional[ErrorDetail]` | Inspect a failed job and return a structured, machine-readable cause (code + category). Redact all tokens/secrets from `message`. |
| 9 | `detect_quota_exhaustion` | `detect_quota_exhaustion(error: ErrorDetail) -> bool` | Return True iff the failure cause is a free-tier quota/rate limit → drives the `quota_wait` state (Master Spec §17). |
| 10 | `close_session` | `close_session() -> None` | Tear down the browser context / revoke tokens. Called on shutdown and on account revocation. |

### 2.2 Supporting types

```python
class JobStatus(enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

@dataclass
class Capabilities:
    max_prompt_length: int
    supported_aspect_ratios: list[str]
    supported_resolutions: list[str]
    supported_models: list[str]
    max_duration_seconds: float
    min_duration_seconds: float
    supports_narration: bool

@dataclass
class QuotaInfo:
    provider: str
    account_id: str
    daily_limit: int          # value the provider reported TODAY (data, not policy)
    used_today: int
    remaining: int
    reset_time: str           # ISO-8601 UTC
    hard_exhausted: bool      # True = cannot submit anything more today

@dataclass
class CompiledPrompt:
    prompt_text: str
    parameters: dict          # aspect, resolution, steps, seed, duration, …
    scene_dna: dict           # continuity DNA folded in (Master Spec §20)

@dataclass
class SubmitContext:
    account: Account
    provider: str
    preferred_model: str | None

@dataclass
class ProviderJob:
    provider_job_id: str
    status: JobStatus
    submitted_at: datetime

@dataclass
class AuthResult:
    session_id: str
    expires_at: datetime | None
    requires_user_interaction: bool
    login_url: str | None

@dataclass
class ErrorDetail:
    code: str
    message: str              # redacted; no tokens
    category: str             # rate_limit | content_policy | network | provider_error | session | user_auth
```

> `QuotaInfo` is the provider's *view* of quota; the persisted `Quota` table
> (`DB_SCHEMA.md` §3.5) is `QuotaManager`'s responsibility, not the provider's.

---

## 3. State Mapping (provider ↔ job)

`get_generation_status` returns `JobStatus`; the Queue/Orchestrator maps this to
the persisted `GenerationJob.state` per `docs/STATE_MACHINE.md` §2.1:

| Provider `JobStatus` | `GenerationJob.state` (after) |
|---|---|
| `RUNNING` / `GENERATING` | `generating` |
| `COMPLETED` | `completed` → trigger download |
| `FAILED` | `failed` → `detect_error` → repair leg |
| `PENDING`/`SUBMITTED` | `submitted` (queued at provider) |
| `UNKNOWN` | inspect `detect_error`; may become `failed` |

Quota exhaustion surfaced by **either** `get_quota` (`hard_exhausted=True`)
**or** `detect_quota_exhaustion` after a `submit_generation`/`get_generation_status`
failure → project → `quota_wait` and all jobs parked (never failed)
(Master Spec §17, §11).

---

## 4. Implementations

### 4.1 `MockVideoProvider` (default, test-only)
- `config/providers.yaml::provider` defaults to `mock` at package import.
- **Deterministic:** `submit_generation` returns a `provider_job_id` whose
  result is a known fixture clip under `tests/fixtures/clips/`.
- `get_generation_status` flips `GENERATING → COMPLETED` after a configurable
  latency (default instant).
- `get_quota` reads `daily_limit`/`used_today` from `config/quota.yaml::mock` so
  the `QUOTA_WAIT` path is testable without a real account.
- `MockFailureProvider(MockVideoProvider)` subclass simulates each failure mode
  (corrupt, too-short, wrong-codec, network, quota) for QA-001.
- **Import guard:** `MockVideoProvider` is always importable; `SnapGenProvider`
  is lazy-imported only when `config/providers.yaml::provider == snapgen`. A
  `mock`-only pytest run can therefore never load SnapGen code (Master Spec §27).

### 4.2 `SnapGenProvider` (real, isolated)
- Located under `app/providers/snapgen/`; imports Playwright **only here**.
- Implements all 10 methods. `authenticate` launches a headed Chromium context
  and returns `requires_user_interaction=True` on a 2FA/CAPTCHA wall — the
  orchestrator escalates to the user (§26) and parks jobs `blocked`.
- `submit_generation` / `download_result` drive SnapGen's UI via Playwright;
  `detect_error` parses the on-page failure reason. All SnapGen selectors live
  inside this module — the provider layer never leaks SnapGen concepts upward.
- **Never** imported by the test path; only resolved through the registry.

---

## 5. Usage Contract

- **Selection:** `config/providers.yaml::provider` ∈ `{mock, snapgen}`. Unknown
  value → fail-fast at startup (never a silent default).
- **Session ownership:** `BrowserSessionManager` (`app/accounts/sessions.py`,
  Security Agent) calls `authenticate` once per `Account` and
  `close_session` on shutdown/revoke. The provider instance is reused across
  `GenerationJob`s for that account.
- **No hard-coded limits:** `get_quota` returns the live number; `QuotaManager`
  is the sole decision-maker for `QUOTA_WAIT`.
- **Isolation rule:** no module between `core` and `providers` may import a
  concrete provider by name; the `ProviderRegistry` resolves by string. Swapping
  `mock → snapgen` is a config + restart, no code edits.

---

## 6. Test Matrix (drives QA-001)

| Test scenario (spec §27) | Provider used | Methods exercised |
|---|---|---|
| Happy-path generation | Mock | 5, 6, 7 |
| Status polling | Mock | 6 |
| Corrupt / too-short / wrong-codec clip | MockFailureProvider | 6 → 7 → 8 |
| Quota exhaustion mid-run | Mock | 4, 9 (→ True) |
| Session expiry | MockFailureProvider | 2 (→ False → `blocked`) |
| Submit without a live session | Mock (guard) | 2 pre-check before 5 |
| Download resume / idempotent | Mock | 7 (second call skipped) |

The real `SnapGenProvider` is **never** imported by any pytest collection.
