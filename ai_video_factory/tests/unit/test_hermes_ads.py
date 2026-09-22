"""Hermes Meta Ads team — guardrail tests (mock-first, no network, no spend)."""
import pytest

from app.ads.approvals import ApprovalGate
from app.ads.architect import CampaignArchitectAgent
from app.ads.orchestrator import CampaignOrchestrator, PRE_EXECUTION_REQUIREMENTS
from app.ads.pipeline import MetaExecutionAgent, QAAgent
from app.ads.research import ClientResearchAgent, Evidence, Finding


def _research():
    agent = ClientResearchAgent()
    return agent.build("TestCafe", {
        "profile": [Finding(Evidence.FACT, "Cafe in Makati", source="client brief")],
        "offer": [Finding(Evidence.ASSUMPTION, "20% off converts", source="owner claim")],
        "audiences": [Finding(Evidence.HYPOTHESIS, "Commuters respond to video")],
        "competitors": [],
        "pain_points": [Finding(Evidence.UNKNOWN, "Review sentiment (no access)")],
    })


def test_fact_requires_source():
    with pytest.raises(ValueError):
        Finding(Evidence.FACT, "Unsourced claim")


def test_research_renders_five_documents():
    docs = _research().documents()
    assert set(docs) == {"CLIENT_PROFILE.md", "OFFER_ANALYSIS.md",
                         "AUDIENCE_HYPOTHESES.md", "COMPETITOR_RESEARCH.md",
                         "CUSTOMER_PAIN_POINTS.md"}
    assert "UNKNOWN" in docs["CUSTOMER_PAIN_POINTS.md"]


def test_approval_gate_deny_by_default():
    gate = ApprovalGate()
    assert gate.check("publish_campaign", None) is False
    assert gate.check("publish_campaign", "apr_nope") is False
    assert gate.check("non_gated_op", None) is True  # non-money ops pass through


def test_approval_grant_flow():
    gate = ApprovalGate()
    apr = gate.request("publish_campaign", "TestCafe")
    assert gate.check("publish_campaign", apr.id) is False
    gate.grant(apr.id)
    assert gate.check("publish_campaign", apr.id) is True


def test_orchestrator_enforces_order():
    orch = CampaignOrchestrator()
    wf = orch.start("TestCafe")
    with pytest.raises(ValueError):
        orch.complete_stage(wf, "COPY")
    orch.complete_stage(wf, "RESEARCH", artifact_ref="research/")
    assert wf.current_stage == "STRATEGY"


def test_orchestrator_blocks_execution_approval_until_ready():
    orch = CampaignOrchestrator()
    wf = orch.start("TestCafe")
    with pytest.raises(ValueError):
        orch.request_execution_approval(wf, "TestCafe")
    for stage in PRE_EXECUTION_REQUIREMENTS:
        orch.complete_stage(wf, stage)
    apr_id = orch.request_execution_approval(wf, "TestCafe")
    assert orch.can_execute(wf) is False  # requested, not granted
    orch.approvals.grant(apr_id)
    assert orch.can_execute(wf) is True


def test_architect_refuses_strategy_override_without_approval():
    agent = CampaignArchitectAgent()
    research = _research()
    with pytest.raises(PermissionError):
        agent.build(research, objective="SALES", conversion_event="Purchase",
                    budget_total=500.0, approved_strategy="LEADS",
                    strategy_override=True, override_approval_id=None)


def test_architect_allows_granted_override():
    gate = ApprovalGate()
    agent = CampaignArchitectAgent(gate)
    research = _research()
    apr = gate.request("strategy_override", "TestCafe")
    gate.grant(apr.id)
    plan = agent.build(research, objective="SALES", conversion_event="Purchase",
                       budget_total=500.0, approved_strategy="LEADS",
                       strategy_override=True, override_approval_id=apr.id)
    assert plan.structure.objective == "SALES"
    assert "CAMPAIGN_STRUCTURE.json" in plan.documents()


def test_qa_blocks_incomplete():
    qa = QAAgent()
    bad = qa.validate({"tracking_ready": True})
    assert bad.ok is False
    good = qa.validate({c: True for c in QAAgent.CHECKS})
    assert good.ok is True


def test_execution_refuses_without_approval():
    gate = ApprovalGate()
    agent = MetaExecutionAgent(gate)
    plan_holder = CampaignArchitectAgent().build(
        _research(), objective="LEADS", conversion_event="Lead",
        budget_total=100.0)
    with pytest.raises(PermissionError):
        agent.publish(plan_holder, None)
    apr = gate.request("publish_campaign", "TestCafe")
    gate.grant(apr.id)
    res = agent.publish(plan_holder, apr.id)
    assert res.ok is True and "dry_run" in res.artifact_ref
