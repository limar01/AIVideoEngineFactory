# Hermes Meta Ads Automation — `app/ads/`

Subtask of AI Video Factory. Implements master spec §§1–6 (role, objective,
multi-agent architecture, orchestrator, research, campaign architect) with the
full CLIENT → NEXT TEST chain wired; stages past §6 ship as typed stubs
awaiting the rest of the spec.

## Layout

```
app/ads/
├── __init__.py       → public surface (gate, orchestrator, research, architect)
├── approvals.py      → ApprovalGate (human money layer, deny-by-default)
├── orchestrator.py   → campaign_orchestrator (state machine + audit)
├── research.py       → client_research_agent (FACT/ASSUMPTION/HYPOTHESIS/UNKNOWN)
├── architect.py      → campaign_architect_agent (plan + structure + testing plan)
└── pipeline.py       → copy/creative/tracking/QA/execution/monitor/diagnose/
                        optimize/test/report/learn (QA + execution real,
                        rest are typed stubs)
```

## Human approval layer

| Op | Gate |
|----|------|
| `publish_campaign`, `spend`, `budget_change`, `bid_change` | granted approval required |
| `delete_campaign/adset/ad`, `strategy_override`, `account_change` | granted approval required |
| research / drafting / QA / monitoring / reporting | no approval (read-only) |

Execution agents call `ApprovalGate.require()` first and raise
`PermissionError` without a grant. The orchestrator will not even request
execution approval until RESEARCH → HUMAN_APPROVAL are all complete.

## Key rules (from spec)

- Never fabricate research: `Finding(FACT, …)` without a source raises; use
  `UNKNOWN`.
- Never override an approved strategy without a granted `strategy_override`.
- QA `PASS` (all five checks) is required before the human approval request.
- Execution is dry-run until the Meta transport lands with §§7+ of the spec.

## Tests

`tests/unit/test_hermes_ads.py` — guardrails only, no network, no spend.
Run: `pytest tests/unit/test_hermes_ads.py -q` from the project root.
