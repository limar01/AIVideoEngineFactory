# ADR-0003: UI Scope — MVP CLI vs Full React Dashboard

- **Date:** 2026-09-22
- **Status:** Accepted
- **Deciders:** User (via Personal Agent), Architecture Agent, Frontend Agent
- **Related:** Master Spec §4.3 (Frontend), §28 (Final Acceptance Test), §25 (Status Report)

---

## Context

The Master Spec §4.3 assigns the Frontend Agent to build a React + TypeScript dashboard. However:
- The backend exposes a pure FastAPI REST API (decoupled from UI)
- The MVP goal is to reach Phase 5 (Integration) and Phase 6 (QA) as fast as possible
- Full React dashboard is a large upfront investment before any pipeline functionality is tested
- The user has expressed preference for minimal, autonomous execution

## Decision

**Build a Typer CLI dashboard (MVP) first; defer full React dashboard.**

### MVP UI: `app/ui/cli.py` — Typer-based CLI driving the REST API

```bash
$ aivf project create --name "Horror 1" --niche horror --topic "haunted doll" --duration 600
$ aivf project start <project_id>       # triggers full pipeline
$ aivf project status <project_id>       # shows pipeline progress + QA summary
$ aivf queue list                        # shows all jobs and states
$ aivf project watch <project_id>        # live progress (WebSocket)
```

### Full UI: React + TypeScript dashboard (deferred to Phase 2 frontend task)

- Built behind the same REST API endpoints
- No backend changes needed when the full UI is added
- The adapter pattern (`app/ui/adapter.py`) isolates UI consumers from backend changes

## Consequences

### Positive
- **Fast path to Phase 5+6:** CLI tests the full pipeline end-to-end without React build complexity
- **Usable in headless environments:** CLI works over SSH, tmux, etc.
- **Lower token/cognitive overhead:** simpler to build and test than a React SPA
- **No risk of UI drift:** backend contract is frozen by API_SPEC.md before UI starts

### Negative
- **Not visually appealing:** CLI is less impressive than a React dashboard
- **Deferred frontend work:** Frontend Agent has nothing to do until Phase 2+ (but can build React dashboard in parallel with other Phase 2 work)

### Neutral
- The REST API is the source of truth; both CLI and future React UI consume the same endpoints

## Alternatives Considered

1. **Build React dashboard first:** More work upfront, delays end-to-end testing. The API contract can be used with `curl` or CLI in the meantime. Rejected for speed.
2. **HTMX dashboard:** A middle ground (server-rendered HTML), but the CLI is even simpler for a local tool and the user already has terminal tooling familiarity.
3. **No UI at all — pure API:** Possible but user can't see progress easily; CLI adds minimal cost for big UX win.

## Notes

The CLI is implemented as a `typer` app with a `--api-url` flag defaulting to `http://localhost:8890/api/v1`. It includes color-coded progress output and a `watch` command that consumes the WebSocket endpoint (API_SPEC.md §3.7) for live state updates. When the full React dashboard is built (Frontend Agent task FRONTEND-001), it uses the identical REST endpoints.
