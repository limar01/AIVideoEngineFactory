# ADR-0002: Story Engine Selection

- **Status:** Proposed
- **Deciders:** Personal Agent, Architecture Agent, AI Content Agent
- **Date:** 2026-09-22
- **Related:** `ARCHITECTURE.md` §5.1, `DEPENDENCY_GRAPH.md` §3.1, `config/story.yaml` (pending creation)
- **Tags:** scope:content, axis:story, impact:architecture

### Context

The pipeline's first content layer is the Story Engine: it produces the story,
character bible, and visual bible (Master Spec §10). The Master Spec §4.4
delegates this to the AI Content Agent, and §26 requires escalating only decisions
the agents cannot make. Whether the engine is a local template engine or an
external LLM is one of the three decision axes the Architecture Agent scoped as
undecided at ARCH-001 so the surrounding architecture (modules, DB, state
machine) could be designed against an adapter.

`ARCHITECTURE.md` §5.1 defines the `StoryEngine` ABC so no other layer depends on
a concrete story implementation.

### Assumptions

- The pipeline must be able to produce a *complete* story (acts + scenes)
  without any external API key, so end-to-end runs and QA-001 can proceed
  offline and on free tier.
- Any real LLM provider must use user-supplied credentials only.
- The Story Engine's output contract (`StoryDoc`, `BibleDoc`, `VisualBible`) is
  fixed by `DB_SCHEMA.md` §3.8 (`stories`) and `ARCHITECTURE.md` §5.1; therefore
  swapping the engine cannot change downstream scenes/prompts except via the
  documented artifact shape.

### Options

| # | Option | Sketch | Free-tier? | ToS risk | Couples story layer to concrete? |
|---|--------|--------|------------|----------|----------------------------------|
| A | **HermesStoryEngine** (default) | Build stories from modular `config/templates/<niche>.yaml` (Horror, Comedy, … §23) using free-tier local logic; no external call. | Yes (offline) | None | No — behind `StoryEngine` ABC |
| B | **OpenAIStoryEngine** | ChatGPT/Chat Completions with user key via vault; richer narrative. | Free-tier only (limited RPM/$) | Honors ToS; no bypass | No — behind ABC |
| C | **GeminiStoryEngine** | Google Gemini via user key. | Free-tier only (limited) | Honors ToS; no bypass | No — behind ABC |

### Decision

Adopt **Option A (HermesStoryEngine)** as the *default* until a user decision is
recorded. It produces stories purely from `config/templates/*`, so the system is
fully functional and testable with zero external calls — satisfying Master Spec
§27 (test without consuming real provider quota) and the free-tier-only mandate.

A real engine (B/C) is selectable via `config/story.yaml::engine`, resolved
through the `StoryEngine` registry — the single seam in
`DEPENDENCY_GRAPH.md` §3.1.

### Consequences

- **Positive:** Zero-config, offline, fully testable story layer; no credit
  budget to drain during development/QA.
- **Negative:** Narrative richness is bounded by template authoring; a real LLM
  engine yields higher quality once chosen and authorized.
- **Adapter seam:** `app/story/engine.py::StoryEngine` ABC
  (`generate_story`, `generate_character_bible`, `generate_visual_bible`).
  `HermesStoryEngine` reads `config/templates/`. Swapping to B/C is a
  `config/story.yaml::engine` key change — consumers (`app/scenes`,
  `app/prompts`) depend only on the returned `StoryDoc`/`Bible`/`VisualBible`
  shape, never on the concrete engine.
- **Testing:** pytest uses `HermesStoryEngine` (default); no external API is
  called in CI (Master Spec §27).
- **Security:** a real engine's key is resolved from the vault, never embedded.

### How to revisit

Pick B/C → add the concrete engine under `app/story/engine.py`, register in
`config/story.yaml::engine`, update this ADR to Accepted & note the swap. No
downstream module imports the concrete engine (`DEPENDENCY_GRAPH.md` §3.1
guarantees story layer → ABC only).

### Links

- Master Spec: §4.4 (AI Content Agent), §10 (Core Pipeline), §27 (testing)
- `ARCHITECTURE.md` §5.1
- `DB_SCHEMA.md` §3.8 (`stories`)
- `DEPENDENCY_GRAPH.md` §3.1 (story axis isolation)
- `config/templates/` (Horror, Comedy, Drama/Romance, … §23)
