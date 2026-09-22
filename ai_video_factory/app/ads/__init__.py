"""Hermes Meta Ads media-buying automation — modular multi-agent team.

Subtask of AI Video Factory (aivideofactory). Master spec §§1–6 implemented;
downstream pipeline stages (§7+) land as typed stubs with approval enforcement
so the full CLIENT → NEXT TEST chain is wired end-to-end from day one.

Human approval layer: any financially significant or destructive action
(spend, publish, budget change, delete) requires a granted approval id.
The orchestrator and execution agent refuse without it — never blind-spend.
"""
from app.ads.approvals import ApprovalGate
from app.ads.architect import CampaignArchitectAgent
from app.ads.orchestrator import CampaignOrchestrator
from app.ads.research import ClientResearchAgent

__all__ = [
    "ApprovalGate",
    "CampaignArchitectAgent",
    "CampaignOrchestrator",
    "ClientResearchAgent",
]
