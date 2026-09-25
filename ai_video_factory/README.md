# AIVideoEngineFactory

A modular, free-tier AI video generation pipeline built on **Hermes Desktop** + **specialist agent team**.

Generate a 10-minute horror story → final validated MP4 — fully automated, quota-aware, and resumable.

```
User: "Create a 10-minute horror story."
        ↓
  Story Engine → Character Bible → Visual Bible → Scene Planner
        ↓                        ↓                        ↓
  Prompt Compiler → Quota Manager → Provider Adapter → FFmpeg Assembly
        ↓
  Final Video + QA Report
```

## Key Principles

| Principle | How |
|-----------|-----|
| **Free-tier only** | No ToS bypass, no quota circumvention, configurable provider limits |
| **Mock-first testing** | All tests use `MockVideoProvider`; real providers opt-in |
| **Resumable** | Every state persisted; restart resumes from saved state |
| **Repair-over-retry** | Failed scenes are repaired (not blindly repeated) |
| **Provider abstraction** | SnapGen isolated behind `VideoGenerationProvider` ABC |

## Project Structure

```
ai_video_factory/
├── app/
│   ├── api/        → FastAPI REST endpoints
│   ├── core/       → Config, settings, ProviderRegistry, orchestrator
│   ├── providers/  → VideoGenerationProvider ABC + Mock + SnapGen
│   ├── accounts/   → Authorized account pool + session lifecycle
│   ├── quota/      → QuotaManager + persisted quota rows
│   ├── story/      → HermesStoryEngine + character/visual bible
│   ├── scenes/     → ScenePlanner, SceneOptimizer, continuity DNA
│   ├── prompts/    → Prompt model + PromptCompiler + PromptQA
│   ├── queue/      → GenerationQueue + RepairEngine
│   ├── downloader/ → DownloadManager + clip storage
│   ├── qa/         → VideoQA (FFmpeg-based clip validation)
│   ├── assembly/   → FFmpegAssembler + narration + final output
│   ├── project/    → Project aggregate + lifecycle service
│   └── ui/         → CLI dashboard (Typer) / future React dashboard
├── config/         → YAML configuration (factory, providers, quota, templates)
├── database/       → SQLite + migrations
├── docs/           → Architecture, DB schema, API spec, state machine, ADRs
├── adr/            → Architecture Decision Records
├── projects/       → Project workspaces + artifacts + clips
├── tests/          → pytest test suite
└── pyproject.toml  → Python project metadata
```

## Quick Start

```bash
# 1. Set up Python environment
uv venv
source .venv/bin/activate

# 2. Initialize config + database
aivf init

# 3. Add a provider account (interactive — opens browser for auth)
aivf account add --provider snapgen

# 4. Create + run a project
aivf project create --name "Horror 1" --niche horror --topic "haunted doll" --duration 600
aivf project start <project_id>

# 5. Watch live progress
aivf project watch <project_id>
```

## Architecture Docs

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | System architecture, module boundaries, layered pipeline |
| `docs/DB_SCHEMA.md` | SQLite schema for all 9 models |
| `docs/API_SPEC.md` | FastAPI REST API contract |
| `docs/PROVIDER_INTERFACE.md` | `VideoGenerationProvider` ABC (10 methods) |
| `docs/STATE_MACHINE.md` | Generation job + project state machine |
| `docs/DEPENDENCY_GRAPH.md` | Task breakdown + phase execution plan |
| `docs/CONFIG_SPEC.md` | Configuration file reference |
| `adr/0001-audio-*.md` | Audio/narration approach decision |
| `adr/0002-story-*.md` | Story engine approach decision |
| `adr/0003-ui-*.md` | UI scope decision (MVP CLI → React) |

## Development

This is a **multi-agent project**. The Personal Agent decomposes work and assigns to specialists:

| Phase | Focus | Specialist Agents |
|-------|-------|------------------|
| 1. Planning | Architecture | Architecture Agent |
| 2. Foundation | Backend, UI, Story, Video, Security (parallel) | 5 agents |
| 3. Core Engine | Story pipeline, queue, quota | AI Content + Backend |
| 4. Provider | SnapGen browser automation | Browser Automation Agent |
| 5. Integration | E2E wiring | Integration Agent |
| 6. QA | Tests | QA Agent |
| 7. Release | Docs, security review, final test | All agents |

See `docs/DEPENDENCY_GRAPH.md` for the full task graph.

## License

Free-tier only. No bypassing of provider restrictions.
