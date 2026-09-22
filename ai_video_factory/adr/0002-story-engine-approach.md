# ADR-0002: Story Engine Approach

- **Date:** 2026-09-22
- **Status:** Accepted
- **Deciders:** User (via Personal Agent), Architecture Agent
- **Related:** Master Spec §4.4 (AI Content Agent), §9 (shared stack), §23 (niche templates)

---

## Context

The Master Spec §9 lists "AI: Provider abstraction" but does not specify which LLM generates story content. The architecture doc (§5.1) supports both local (adapter-pattern) and API-based story engines.

Options:
1. **Hermes-generated:** Use Hermes subagents (the architecture agent, AI content agent, etc.) to produce story artifacts directly. Free — no API keys, no token costs.
2. **External LLM API:** App calls GPT-4, Claude, Gemini, etc. to generate story/character bible/visual bible. Costs tokens, requires API keys.

## Decision

**Hermes-generated content (default), with external LLM as an optional swap.**

- Default implementation: `HermesStoryEngine` — delegates to Hermes Desktop subagents to generate `StoryDoc`, `CharacterBible`, `VisualBible` artifacts
- The story engine adapter interface (`StoryEngine`) is defined in `app/story/engine.py` with: `generate_story()`, `generate_character_bible()`, `generate_visual_bible()`
- Generated artifacts are serialized to the project's artifact folder and persisted (a row in `Prompt` links them), so restarts never re-run the story layer (per spec §11)
- Optional real implementations: `OpenAIStoryEngine`, `GeminiStoryEngine` — swap via `config/story.yaml::engine`

### How it works in the pipeline

1. User creates a project with `niche + topic + target_seconds`
2. `HermesStoryEngine.generate_story()` is triggered as a Hermes subagent task
3. Subagent produces structured JSON: story outline, act/scene breakdown, narration text per scene
4. `generate_character_bible()` → character list with appearance/clothing/props
5. `generate_visual_bible()` → visual style, color palette, reference imagery notes
6. Artifacts saved to `projects/{id}/artifacts/` and indexed in DB
7. `ScenePlanner` consumes these to create `Scene` rows with continuity DNA baked in

## Consequences

### Positive
- **Free-tier**: no LLM API costs for content generation (only the video provider's free tier matters)
- **No API keys**: aligns with user's constraint (CDP auth only, no API keys anywhere)
- **Rich output**: Hermes subagents can produce higher-quality, niche-tailored content than templated generation
- **Agnostic swap**: adapter interface means adding an external LLM later is a config change + new class

### Negative
- **Slower**: subagent spawning adds latency vs. a raw API call
- **Less reproducible**: LLM output varies between runs (mitigated by artifact persistence)

### Neutral
- The adapter pattern ensures the backend pipeline code never knows or cares whether content came from Hermes or an API

## Alternatives Considered

1. **External LLM API (GPT-4/Claude/Gemini):** Faster and more reproducible, but violates the user's "no API keys" constraint and adds quota/cost complexity. Rejected for v1.
2. **Template-only generation:** Pre-written story templates per niche. Too rigid; doesn't scale to arbitrary topics. Rejected.

## Notes

`config/templates/{niche}.yaml` files define niche-specific structure (pacing, scene types, visual guidance, prompt rules, QA rules per spec §23). The `HermesStoryEngine` loads these as context for subagent generation. This satisfies the "modular templates" requirement while enabling high-quality, topic-specific output.
