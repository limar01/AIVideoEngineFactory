"""AGENT 02 (spec §6) — campaign_architect_agent.

Converts business objectives + research into campaign structure: objective,
conversion event, audiences, geo, budgets, creative-test matrix, naming
conventions, tracking requirements, lifecycle.

Hard rule: never overrides an approved client strategy without explicit
human approval (strategy_override op via ApprovalGate).

Outputs: CAMPAIGN_PLAN.md · CAMPAIGN_STRUCTURE.json · TESTING_PLAN.md
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.ads.approvals import ApprovalGate
from app.ads.research import ClientResearch

logger = logging.getLogger(__name__)


@dataclass
class CampaignStructure:
    objective: str
    conversion_event: str
    geo: list[str] = field(default_factory=list)
    adsets: list[dict] = field(default_factory=list)  # name/audience/budget/creative_slots
    naming_convention: str = ""
    tracking_requirements: list[str] = field(default_factory=list)
    lifecycle: str = "draft"

    def to_json(self) -> str:
        return json.dumps(
            {
                "objective": self.objective,
                "conversion_event": self.conversion_event,
                "geo": self.geo,
                "adsets": self.adsets,
                "naming_convention": self.naming_convention,
                "tracking_requirements": self.tracking_requirements,
                "lifecycle": self.lifecycle,
            },
            indent=2,
            sort_keys=True,
        )


@dataclass
class CampaignPlan:
    client_name: str
    structure: CampaignStructure
    budget_total: float
    testing_plan: str = ""

    def documents(self) -> dict[str, str]:
        plan = (
            f"# Campaign Plan — {self.client_name}\n\n"
            f"- Objective: {self.structure.objective}\n"
            f"- Conversion event: {self.structure.conversion_event}\n"
            f"- Geo: {', '.join(self.structure.geo) or 'TBD'}\n"
            f"- Total budget: {self.budget_total:.2f}\n"
            f"- Ad sets: {len(self.structure.adsets)}\n"
            f"- Naming: `{self.structure.naming_convention}`\n"
            f"- Lifecycle: {self.structure.lifecycle}\n"
        )
        testing = (
            f"# Testing Plan — {self.client_name}\n\n{self.testing_plan.strip()}\n"
            if self.testing_plan.strip()
            else f"# Testing Plan — {self.client_name}\n\n_TBD._\n"
        )
        return {
            "CAMPAIGN_PLAN.md": plan,
            "CAMPAIGN_STRUCTURE.json": self.structure.to_json() + "\n",
            "TESTING_PLAN.md": testing,
        }


class CampaignArchitectAgent:
    """Builds plans from research. Strategy-override requires approval."""

    name = "campaign_architect_agent"

    def __init__(self, approvals: ApprovalGate | None = None) -> None:
        self.approvals = approvals or ApprovalGate()

    def build(
        self,
        research: ClientResearch,
        objective: str,
        conversion_event: str,
        budget_total: float,
        geo: list[str] | None = None,
        approved_strategy: str = "",
        strategy_override: bool = False,
        override_approval_id: str | None = None,
        testing_plan: str = "",
    ) -> CampaignPlan:
        if budget_total <= 0:
            raise ValueError("budget_total must be positive — zero-spend plans hide cost.")
        if approved_strategy and strategy_override:
            # Explicit override path: human must have granted strategy_override.
            self.approvals.require("strategy_override", override_approval_id,
                                   research.client_name)
            logger.info("architect: strategy override approved for %s",
                        research.client_name)
        elif approved_strategy and objective != approved_strategy:
            raise PermissionError(
                "Refusing to override the approved client strategy "
                f"('{approved_strategy}') without explicit approval. "
                "Pass strategy_override=True with a granted override approval."
            )
        structure = CampaignStructure(
            objective=objective,
            conversion_event=conversion_event,
            geo=list(geo or []),
            naming_convention="{client}_{objective}_{geo}_{seq}",
            tracking_requirements=["pixel_present", "capi_present", "utm_naming"],
        )
        plan = CampaignPlan(
            client_name=research.client_name,
            structure=structure,
            budget_total=budget_total,
            testing_plan=testing_plan,
        )
        logger.info("architect: built plan for %s objective=%s",
                    research.client_name, objective)
        return plan
