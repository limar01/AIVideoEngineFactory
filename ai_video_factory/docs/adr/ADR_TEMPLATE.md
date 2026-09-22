# ADR Template — AI Video Factory

**Status:** Template (copy & fill before use)
**Format:** MADR-style, one file per decision, in `docs/adr/`
**Naming:** `NNN-short-title-slug.md` (zero-padded, chronological by proposal order)

---

## ADR-NNN: [Title]

- **Status:** Proposed | Accepted | Superseded-by ADR-NNN | Rejected
- **Deciders:** Personal Agent, Architecture Agent, affected specialist owner
- **Date:** YYYY-MM-DD (proposal)
- **Tags:** scope:<project|module>, axis:<audio|story|ui|provider|...>, impact:<local|architecture>

### Context

What is the decision forced by? (Cite Master Spec § and the relevant deliverable
doc). Include the constraints the architecture imposes: free-tier only, no ToS
bypass, mock-first testing, adapter pattern.

### Assumptions

List the assumptions this decision rests on (e.g., "a free local TTS runtime is
acceptable", "an external LLM key is available at runtime").

### Options

| Option | Sketch | Cost | Free-tier? | ToS impact | Couples to |
|--------|--------|------|------------|------------|------------|
| A |        |      |            |            |            |
| B |        |      |            |            |            |

### Decision

The chosen option and **why**, referencing the architecture's adapter seam so
the reader can see exactly what changes if this is revisited.

### Consequences

- Positive
- Negative / risks
- **Adapter seam:** name the concrete class + the config key + the ABC it
  implements, so future re-decisions are a config swap, not a code rewrite.
- **Testing:** which provider the test matrix uses (must remain `mock` / default
  for pytest per Master Spec §27).

### How to revisit

If this decision changes, the only touch points are: the adapter listed above +
its config selector + the relevant ADR (link). No other module imports the
concrete implementation (see `DEPENDENCY_GRAPH.md` §3.1).

### Links

- Master Spec: §…
- `ARCHITECTURE.md` §…
- Affected: `config/…`
