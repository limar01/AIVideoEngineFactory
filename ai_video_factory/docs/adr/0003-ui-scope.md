# ADR-0003: UI Scope Selection

- **Status:** Proposed
- **Deciders:** Personal Agent, Architecture Agent, Frontend Agent
- **Date:** 2026-09-22
- **Related:** `ARCHITECTURE.md` §5.3, `DEPENDENCY_GRAPH.md` §3.1, `API_SPEC.md`, `config/ui.yaml` (pending creation)
- **Tags:** scope:interface, axis:ui, impact:architecture

### Context

The user interacts with the factory through a UI. The Master Spec §4.3 delegates
the UI to the Frontend Agent (React + TypeScript), and §26 limits user
escalation to genuinely ambiguous requirements. The *scope* of the UI — full
React dashboard vs. a minimal CLI that drives the REST API — is one of the three
decision axes the Architecture Agent scoped as undecided at ARCH-001 so the
backend contract could be finalized first and treated as immutable by whichever
UI is built.

`ARCHITECTURE.md` §5.3 mandates that the backend exposes a pure FastAPI API and
the UI is a consumer, so this decision cannot drift the backend contract — the
UI talks to `API_SPEC.md` endpoints only.

### Assumptions

- The backend REST API (`API_SPEC.md`) is the stable, version-locked contract;
  any UI must use only its documented endpoints.
- A usable factory can be driven without a React build, via a CLI shim, so the
  project is runnable end-to-end before a React dashboard exists.
- Free-tier / development runs should not require a browser-based UI build step.

### Options

| # | Option | Sketch | Free-tier? | ToS risk | Couples to backend? |
|---|--------|--------|------------|----------|----------------------|
| A | **CLIDashboard (MVP)** | Typer/Click CLI that calls the REST API (`/api/v1/*`); no React build required to run a pipeline. | Yes | None | Via `API_SPEC.md` only |
| B | **React Dashboard (full)** | React + TypeScript SPA talking to `API_SPEC.md`; richer progress/quota/Q views. | Yes (dev server) | None | Via `API_SPEC.md` only |
| C | **Hybrid** | CLI MVP first (A), React added later (B); both behind the same API contract. | Yes | None | Via `API_SPEC.md` only |

### Decision

Adopt **Option A (CLIDashboard, MVP)** as the *default* until a user decision is
recorded, with the architecture explicitly supporting **Option C** (add React
later). The CLI is sufficient to create projects, start/pause/resume runs, and
monitor per-scene job state through the documented REST endpoints, so the factory
is fully operable without a browser UI and without consuming any provider quota
beyond real video generation.

This is the only choice that satisfies "operable today, zero extra build step"
while keeping the full React path open behind the stable API contract.

### Consequences

- **Positive:** Factory is runnable end-to-end immediately; no React toolchain
  needed for development or QA; CI can exercise the full pipeline via the CLI
  against `MockVideoProvider`.
- **Negative:** No rich visual progress/quota dashboard until (and unless) the
  React UI is adopted; CLI UX is text-only.
- **Adapter seam / isolation:** `app/ui/adapter.py::UIAdapter` ABC
  (`present_project`, `present_job`, `prompt_user(action)` for auth/2FA
  handoff). `CLIDashboard` is the default implementation; `ReactDashboard` is the
  full path. The backend (`app/api`) knows only the ABC for any user-facing
  callbacks, never the concrete UI. Choosing B or C is a
  `config/ui.yaml::adapter` key change — no backend edits (`DEPENDENCY_GRAPH.md`
  §3.1 keeps UI as a consumer, not an importable dependency).
- **Testing:** pytest drives the HTTP API directly (via FastAPI's test client
  against `MockVideoProvider`); the CLI is covered by an integration smoke test.
  No UI choice affects backend tests (Master Spec §27).
- **Auth handoff:** when a provider requires 2FA (Browser Automation Agent,
  §4.5), `UIAdapter.prompt_user` is the seam the CLI/React both implement to
  escalate to the user (Master Spec §26).

### How to revisit

Pick B/C → implement the concrete UI behind the `UIAdapter` ABC in `app/ui/`,
select it via `config/ui.yaml::adapter`. The backend contract
(`API_SPEC.md`) is unchanged; no downstream module imports the UI. Update this
ADR to Accepted (note the swap) or leave it Proposed as long as MVP remains.

### Links

- Master Spec: §4.3 (Frontend Agent), §26 (escalation), §27 (testing)
- `ARCHITECTURE.md` §5.3
- `API_SPEC.md` (stable contract the UI consumes)
- `DEPENDENCY_GRAPH.md` §3.1 (UI as consumer / adapter seam)
