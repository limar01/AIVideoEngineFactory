# AI Video Factory — Configuration Specification

**Doc ID:** CONFIG_SPEC.md  
**Status:** Approved (Phase 1 — Planning)  
**Related:** `docs/ARCHITECTURE.md` §5 (Adapters), `adr/*`

---

## 1. Configuration Strategy

All project configuration lives under `config/` as YAML files. Environment-specific values (credentials, secrets) are resolved via environment variables or a secrets file that is never committed.

```
config/
├── factory.yaml          # Main app config (paths, provider selection, logging)
├── providers.yaml        # Provider-specific settings (snapgen, mock)
├── accounts.yaml         # Account pool configuration (account IDs, labels)
├── quota.yaml            # Quota policy (fallbacks, refresh intervals)
├── story.yaml            # Story engine selection + template settings
├── audio.yaml            # Audio/TTS provider selection + voice profiles
├── templates/            # Niche templates (horror.yaml, comedy.yaml, ...)
│   ├── horror.yaml
│   ├── comedy.yaml
│   ├── drama.yaml
│   └── ...
├── secrets.yaml.example  # Template for secrets (never committed)
└── secrets.yaml          # ACTUAL secrets (gitignored, via secrets.yaml.example)
```

## 2. factory.yaml

```yaml
app:
  name: "AI Video Factory"
  environment: "development"  # development | production | testing
  log_level: "INFO"
  
paths:
  projects_dir: "/home/limar01/Data/Projects/workspace/project/ai_video_factory/projects"
  database: "/home/limar01/Data/Projects/workspace/project/ai_video_factory/database/factory.db"
  logs_dir: "/home/limar01/Data/Projects/workspace/project/ai_video_factory/logs"
  clips_dir: "/home/limar01/Data/AI_Video_Factory/clips"  # large; on Data drive

api:
  host: "0.0.0.0"
  port: 8890  # matches user's web app port
  api_key: "${VAF_API_KEY}"  # env var override

pipeline:
  default_clip_seconds: 8  # spec §1: 600/8 = 75 units
  max_concurrent_jobs: 1   # serial per provider account (spec §2 free-tier)
  default_niche: "horror"
  default_target_seconds: 600
```

## 3. providers.yaml

```yaml
provider: "mock"  # mock | snapgen (never hard-code "10/day")

mock:
  quota_limit: 10000  # never exhausts in tests
  fail_on_call: null   # for failure injection tests
  min_duration: 2.0
  max_duration: 5.0

snapgen:
  base_url: "https://snapgen.ai"  # to be confirmed by PROVIDER-000 recon
  session_timeout_minutes: 30
  generation_timeout_minutes: 15
  polling_interval_seconds: 10
  # Quota is fetched live from provider — never hard-coded
```

## 4. quota.yaml

```yaml
policy:
  # Fallback if provider doesn't expose quota — conservative
  fallback_daily_limit: 5
  fallback_reset_time: "next_midnight_utc"
  
  refresh_interval_seconds: 30
  # When quota is exhausted, how long to wait before checking again
  quota_wait_check_interval_seconds: 300
  
  # If multiple accounts are authorized (provider must allow this per spec §2)
  account_rotation: false  # default: no rotation to exceed limits
```

## 5. story.yaml

```yaml
engine: "hermes"  # hermes | openai | gemini (config-only swap)
template_dir: "config/templates"

hermes:
  # Subagent settings
  model_preferences:
    horror: "poolside/laguna-s-2.1:free"
    default: "poolside/laguna-s-2.1:free"
```

## 6. audio.yaml

```yaml
provider: "piper"  # piper | silent | elevenlabs | openai (config-only swap)

piper:
  model_dir: "/home/limar01/.local/share/piper/models"
  default_voice: "en_US-amy-low"
  on_demand_download: true

silent:
  track_type: "muted_silence_for_assembly"

voices_by_niche:
  horror:
    piper: "en_US-ryan-low"
  comedy:
    piper: "en_US-kathleen-low"
  default:
    piper: "en_US-amy-low"
```

## 7. secrets.yaml.example

```yaml
# COPY THIS FILE TO secrets.yaml AND FILL IN
# NEVER COMMIT secrets.yaml
#
# SnapGen session (cookie-based; populated by browser automation after user auth)
snapgen:
  session_cookies: {}  # populated at runtime; never hand-written

# Optional: LLM API keys (only needed if engine != hermes)
openai:
  api_key: ""

gemini:
  api_key: ""

# Optional: TTS API keys (only needed if audio.provider != piper/silent)
elevenlabs:
  api_key: ""
```

## 8. accounts.yaml

```yaml
# Account pool — only user-authorized accounts
accounts:
  - id: "snapgen-primary"
    provider: "snapgen"
    label: "Primary SnapGen Account"
    authorized: true
    # credentials are stored encrypted in the database Account table,
    # not in this file. This file only defines metadata.
    
    # Multiple accounts only if provider explicitly permits:
    # - snapgen.ai terms of service must allow
    # - each account must have its own independent quota
    # - no credential rotation to exceed limits
```

## 9. Niche Template Format (`templates/horror.yaml`)

```yaml
niche: "horror"
story_structure:
  acts: 3
  pacing: "slow_burn"
  tension_curve: [0.2, 0.5, 0.9, 0.7, 1.0]
  
scene_types:
  - exposition
  - rising_tension
  - jump_scare
  - revelation
  - climax

visual_guidance:
  color_palette: ["deep_red", "dark_blue", "black"]
  lighting: "low_contrast_with_sporadic_highlights"
  camera_style: "tight_closeups_then_wide_reveal"

prompt_rules:
  - "include jump scare timing in narration"
  - "describe lighting contrast explicitly"
  - "specify character eye contact for tension"

narration_style:
  tone: "whispered_then_loud"
  pacing: "slow_then_punctuated"

qa_rules:
  - min_clips_passing: 0.85  # 85% of clips must pass QA
  - max_repeated_elements: 2  # continuity check
```
