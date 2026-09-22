"""AGENT 01 (spec §5) — client_research_agent.

Researches the business and labels every claim so downstream agents (and the
human operator) can tell evidence from guesswork. Never fabricates: anything
not evidenced is UNKNOWN, never stated as fact.

Output documents: CLIENT_PROFILE.md · OFFER_ANALYSIS.md ·
AUDIENCE_HYPOTHESES.md · COMPETITOR_RESEARCH.md · CUSTOMER_PAIN_POINTS.md
(represented here as a typed bundle; rendering to markdown is deterministic).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Evidence(str, Enum):
    FACT = "FACT"  # directly evidenced (client source, observed data)
    ASSUMPTION = "ASSUMPTION"  # working belief, flagged for validation
    HYPOTHESIS = "HYPOTHESIS"  # testable prediction for campaigns
    UNKNOWN = "UNKNOWN"  # asked-for data that was not available


@dataclass(frozen=True)
class Finding:
    label: Evidence
    statement: str
    source: str = ""  # where it came from; empty only for UNKNOWN

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Finding statement must not be empty.")
        if self.label == Evidence.FACT and not self.source.strip():
            raise ValueError("FACT findings require a source. Use UNKNOWN instead "
                             "of stating unsourced claims as fact.")


@dataclass
class ClientResearch:
    client_name: str
    profile: list[Finding] = field(default_factory=list)       # CLIENT_PROFILE.md
    offer: list[Finding] = field(default_factory=list)         # OFFER_ANALYSIS.md
    audiences: list[Finding] = field(default_factory=list)     # AUDIENCE_HYPOTHESES.md
    competitors: list[Finding] = field(default_factory=list)   # COMPETITOR_RESEARCH.md
    pain_points: list[Finding] = field(default_factory=list)   # CUSTOMER_PAIN_POINTS.md

    def documents(self) -> dict[str, str]:
        """Render the five output documents as markdown."""
        return {
            "CLIENT_PROFILE.md": _render("Client Profile", self.client_name,
                                         self.profile),
            "OFFER_ANALYSIS.md": _render("Offer Analysis", self.client_name,
                                         self.offer),
            "AUDIENCE_HYPOTHESES.md": _render("Audience Hypotheses",
                                              self.client_name, self.audiences),
            "COMPETITOR_RESEARCH.md": _render("Competitor Research",
                                              self.client_name, self.competitors),
            "CUSTOMER_PAIN_POINTS.md": _render("Customer Pain Points",
                                               self.client_name, self.pain_points),
        }

    def unknowns(self) -> list[str]:
        out = []
        for section in (self.profile, self.offer, self.audiences,
                        self.competitors, self.pain_points):
            out.extend(f.statement for f in section if f.label == Evidence.UNKNOWN)
        return out


def _render(title: str, client: str, findings: list[Finding]) -> str:
    lines = [f"# {title} — {client}", ""]
    if not findings:
        lines.append("_No findings recorded._")
        return "\n".join(lines) + "\n"
    for f in findings:
        src = f" (source: {f.source})" if f.source else ""
        lines.append(f"- **{f.label.value}**: {f.statement}{src}")
    return "\n".join(lines) + "\n"


class ClientResearchAgent:
    """Collects labeled findings. Refuses to present guesses as facts."""

    name = "client_research_agent"

    def build(self, client_name: str, findings: dict[str, list[Finding]]) -> ClientResearch:
        research = ClientResearch(
            client_name=client_name,
            profile=list(findings.get("profile", [])),
            offer=list(findings.get("offer", [])),
            audiences=list(findings.get("audiences", [])),
            competitors=list(findings.get("competitors", [])),
            pain_points=list(findings.get("pain_points", [])),
        )
        logger.info("research: built bundle for %s (%d unknowns)",
                    client_name, len(research.unknowns()))
        return research
