"""Downstream pipeline stages (§7+ of the master spec).

COPY / CREATIVE / TRACKING / QA / EXECUTION / MONITORING / ANALYSIS /
OPTIMIZATION / TESTING / REPORTING / LEARNING — wired end-to-end with the
orchestrator stage order. QA ships a real checklist validator; EXECUTION
refuses without a granted publish approval; the rest are typed capability
stubs with explicit planned/not-planned status so the remainder of the master
spec (past §6) can land without re-wiring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ads.approvals import ApprovalGate
from app.ads.architect import CampaignPlan

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    agent: str
    stage: str
    ok: bool
    artifact_ref: str = ""
    notes: list[str] = field(default_factory=list)


class CopyAgent:
    """Ad-copy variants per ad set. Human reviews before publish (QA gate)."""

    name = "copy_agent"
    stage = "COPY"

    def draft(self, plan: CampaignPlan, variants_per_adset: int = 3) -> StageResult:
        if variants_per_adset < 1:
            raise ValueError("Need at least one copy variant per ad set.")
        return StageResult(
            agent=self.name, stage=self.stage, ok=True,
            artifact_ref=f"copy/{plan.client_name}/{len(plan.structure.adsets)}adsets"
                         f"x{variants_per_adset}.md",
            notes=["Planned: hooks, primary text, headlines, CTAs per variant."],
        )


class CreativeConceptAgent:
    """Creative concepts (image/video briefs). No generation side effects here."""

    name = "creative_concept_agent"
    stage = "CREATIVE_CONCEPTS"

    def concept(self, plan: CampaignPlan, concepts_per_adset: int = 2) -> StageResult:
        if concepts_per_adset < 1:
            raise ValueError("Need at least one creative concept per ad set.")
        return StageResult(
            agent=self.name, stage=self.stage, ok=True,
            artifact_ref=f"creative/{plan.client_name}/concepts.md",
            notes=["Planned: format, hook-frame, script/shot-list, brand checks."],
        )


class TrackingAgent:
    """Tracking readiness: pixel, CAPI, UTMs. Blocks QA on missing pieces."""

    name = "tracking_agent"
    stage = "TRACKING"

    def prepare(self, plan: CampaignPlan, checks: dict[str, bool]) -> StageResult:
        missing = [k for k, v in checks.items() if not v]
        notes = [f"missing: {', '.join(missing)}"] if missing else ["all signals present"]
        return StageResult(
            agent=self.name, stage=self.stage, ok=not missing,
            artifact_ref=f"tracking/{plan.client_name}/readiness.md", notes=notes,
        )


class QAAgent:
    """Pre-flight QA. Real checklist — execution requires a PASS."""

    name = "qa_agent"
    stage = "QA"

    CHECKS = ("tracking_ready", "budget_caps_set", "naming_valid",
              "copy_reviewed", "creative_reviewed")

    def validate(self, results: dict[str, bool]) -> StageResult:
        missing = [c for c in self.CHECKS if not results.get(c, False)]
        extra = [k for k in results if k not in self.CHECKS]
        notes = []
        if missing:
            notes.append(f"FAIL: {', '.join(missing)}")
        if extra:
            notes.append(f"ignored unknown checks: {', '.join(extra)}")
        ok = not missing
        if ok:
            notes.append("QA PASS — eligible for human approval.")
        logger.info("qa: %s", notes)
        return StageResult(agent=self.name, stage=self.stage, ok=ok, notes=notes)


class MetaExecutionAgent:
    """Meta publish lane. REFUSES without a granted publish_campaign approval."""

    name = "meta_execution_agent"
    stage = "META_EXECUTION"

    def __init__(self, approvals: ApprovalGate | None = None) -> None:
        self.approvals = approvals or ApprovalGate()

    def publish(self, plan: CampaignPlan, approval_id: str | None) -> StageResult:
        self.approvals.require("publish_campaign", approval_id, plan.client_name)
        # Transport to the Meta Marketing API lands with the rest of the spec.
        return StageResult(
            agent=self.name, stage=self.stage, ok=True,
            artifact_ref=f"execution/{plan.client_name}/dry_run.md",
            notes=["Approved. Transport pending (§7+ spec): dry-run only, no spend yet."],
        )


class MonitoringAgent:
    name = "monitoring_agent"
    stage = "MONITORING"

    def watch(self, campaign_ref: str) -> StageResult:
        return StageResult(agent=self.name, stage=self.stage, ok=True,
                           artifact_ref=f"monitoring/{campaign_ref}/watch.md",
                           notes=["Planned: spend/pacing/frequency/anomaly alerts."])


class DiagnosticAgent:
    name = "diagnostic_agent"
    stage = "ANALYSIS"

    def diagnose(self, campaign_ref: str) -> StageResult:
        return StageResult(agent=self.name, stage=self.stage, ok=True,
                           artifact_ref=f"analysis/{campaign_ref}/diagnosis.md",
                           notes=["Planned: funnel break-down, creative fatigue signals."])


class OptimizationAgent:
    """Recommendations only. Applying budget/bid changes needs fresh approval."""

    name = "optimization_agent"
    stage = "OPTIMIZATION"

    def recommend(self, campaign_ref: str) -> StageResult:
        return StageResult(
            agent=self.name, stage=self.stage, ok=True,
            artifact_ref=f"optimization/{campaign_ref}/recommendations.md",
            notes=["Advisory only — budget/bid changes require budget_change/bid_change approval."],
        )


class TestingAgent:
    name = "testing_agent"
    stage = "TESTING"

    def next_test(self, campaign_ref: str) -> StageResult:
        return StageResult(agent=self.name, stage=self.stage, ok=True,
                           artifact_ref=f"testing/{campaign_ref}/next_test.md",
                           notes=["Planned: A/B matrix rotation from TESTING_PLAN.md."])


class ReportingAgent:
    name = "reporting_agent"
    stage = "REPORTING"

    def report(self, campaign_ref: str) -> StageResult:
        return StageResult(agent=self.name, stage=self.stage, ok=True,
                           artifact_ref=f"reporting/{campaign_ref}/report.md",
                           notes=["Planned: spend/results/learnings digest."])


class LearningAgent:
    name = "learning_agent"
    stage = "LEARNING"

    def learn(self, campaign_ref: str) -> StageResult:
        return StageResult(agent=self.name, stage=self.stage, ok=True,
                           artifact_ref=f"learning/{campaign_ref}/learnings.md",
                           notes=["Planned: append to campaign knowledge base → NEXT_TEST."])
