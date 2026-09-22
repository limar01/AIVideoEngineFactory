"""ORCHESTRATOR — campaign_orchestrator. The manager, not the worker.

Owns the CLIENT → NEXT TEST state machine: validates stage dependencies,
delegates to specialist agents, collects outputs, detects failures, requests
human approval before anything financial, and keeps an audit log.

Stage order (master spec §2):
CLIENT → RESEARCH → STRATEGY → CAMPAIGN ARCHITECTURE → COPY →
CREATIVE CONCEPTS → TRACKING → QA → HUMAN APPROVAL → META EXECUTION →
MONITORING → ANALYSIS → OPTIMIZATION → TESTING → REPORTING → LEARNING → NEXT TEST
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.ads.approvals import ApprovalGate

logger = logging.getLogger(__name__)

STAGES: tuple[str, ...] = (
    "CLIENT",
    "RESEARCH",
    "STRATEGY",
    "CAMPAIGN_ARCHITECTURE",
    "COPY",
    "CREATIVE_CONCEPTS",
    "TRACKING",
    "QA",
    "HUMAN_APPROVAL",
    "META_EXECUTION",
    "MONITORING",
    "ANALYSIS",
    "OPTIMIZATION",
    "TESTING",
    "REPORTING",
    "LEARNING",
    "NEXT_TEST",
)

#: Stages whose outputs must exist before META_EXECUTION may run.
PRE_EXECUTION_REQUIREMENTS: tuple[str, ...] = (
    "RESEARCH",
    "STRATEGY",
    "CAMPAIGN_ARCHITECTURE",
    "COPY",
    "CREATIVE_CONCEPTS",
    "TRACKING",
    "QA",
    "HUMAN_APPROVAL",
)


@dataclass
class CampaignWorkflow:
    id: str
    client_name: str
    current_stage: str = "CLIENT"
    completed: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)  # stage -> artifact ref
    failures: list[str] = field(default_factory=list)
    approval_id: str | None = None  # grants META_EXECUTION (publish_campaign)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CampaignOrchestrator:
    """Manages workflow state, delegation order, approvals, and audit."""

    name = "campaign_orchestrator"

    def __init__(self, approvals: ApprovalGate | None = None) -> None:
        self.approvals = approvals or ApprovalGate()
        self.audit: list[str] = []
        self.workflows: dict[str, CampaignWorkflow] = {}

    # ------------------------------------------------------------------ #
    def start(self, client_name: str) -> CampaignWorkflow:
        wf = CampaignWorkflow(id="wf_" + uuid4().hex[:8], client_name=client_name)
        self.workflows[wf.id] = wf
        self._log(wf.id, f"START client={client_name}")
        return wf

    def complete_stage(self, wf: CampaignWorkflow, stage: str,
                       artifact_ref: str = "") -> CampaignWorkflow:
        """Mark a stage done after validating it is the expected next step."""
        expected = self.next_stage(wf)
        if stage != expected:
            raise ValueError(
                f"Out-of-order stage: got {stage}, expected {expected} "
                f"(workflow {wf.id}). Dependencies are enforced."
            )
        wf.completed.append(stage)
        if artifact_ref:
            wf.outputs[stage] = artifact_ref
        wf.current_stage = self.next_stage(wf)
        self._log(wf.id, f"STAGE_OK {stage} -> next={wf.current_stage}")
        return wf

    def next_stage(self, wf: CampaignWorkflow) -> str:
        for stage in STAGES:
            if stage not in wf.completed and stage != "CLIENT":
                # CLIENT is the intake (start()), first real stage is RESEARCH.
                return stage
        return "NEXT_TEST" if "LEARNING" in wf.completed else "DONE"

    def record_failure(self, wf: CampaignWorkflow, stage: str, reason: str) -> None:
        wf.failures.append(f"{stage}: {reason}")
        self._log(wf.id, f"STAGE_FAIL {stage}: {reason}")

    # ------------------------------------------------------------------ #
    def request_execution_approval(self, wf: CampaignWorkflow,
                                   subject: str) -> str:
        """Human gate before META_EXECUTION. Returns the approval id for the
        operator to grant. Never auto-grants."""
        missing = [s for s in PRE_EXECUTION_REQUIREMENTS if s not in wf.completed]
        if missing:
            raise ValueError(
                f"Cannot request execution approval: stages incomplete: {missing}"
            )
        approval = self.approvals.request("publish_campaign", subject,
                                          detail=f"workflow={wf.id}")
        wf.approval_id = approval.id
        self._log(wf.id, f"APPROVAL_REQUESTED {approval.id} for {subject}")
        return approval.id

    def can_execute(self, wf: CampaignWorkflow) -> bool:
        return self.approvals.check("publish_campaign", wf.approval_id)

    # ------------------------------------------------------------------ #
    def _log(self, wf_id: str, line: str) -> None:
        entry = f"{datetime.now(timezone.utc).isoformat()} [{wf_id}] {line}"
        self.audit.append(entry)
        logger.info("orchestrator: %s", line)
