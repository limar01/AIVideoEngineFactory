from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.scenes.planner import PlanarScene

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


@dataclass
class SceneFinding:
    """A single optimization finding for a scene."""
    severity: str  # INFO | WARNING | CRITICAL
    code: str      # e.g. TOO_MANY_CHARACTERS, SIMULTANEOUS_ACTIONS
    message: str
    suggestion: str


# --------------------------------------------------------------------------- #
# SceneOptimizer
# --------------------------------------------------------------------------- #


class SceneOptimizer:
    """Analyzes scenes for generation compatibility and produces fixes.

    Source: docs/ARCHITECTURE.md §5.5, Master Spec §19
    """

    SIMULTANEOUS_PATTERNS = [
        (r'\bwhile\s+\w+', "Simultaneous action — AI video struggles with 'while'"),
        (r'\bmeanwhile\b', "Simultaneous action — 'meanwhile' implies parallel events"),
        (r'\bsimultaneously\b', "Explicit simultaneous action"),
        (r'\bas\s+\w+\s+(is|does|goes)\b', "Concurrent framing — 'as X is Y' implies simultaneity"),
        (r'\bat the same time\b', "Explicit simultaneous framing"),
    ]

    MULTI_CHARACTER_PATTERNS = [
        (r'\b(character|person|man|woman|child|figure|people)\b.*\band\b.*\b(character|person|man|woman|child|figure|people)\b',
         "Multiple characters in one description"),
        (r'\b\d+\s+(characters|people|figures)\b', "Explicit count of multiple characters"),
    ]

    COMPLEX_ACTION_PATTERNS = [
        (r'\b(runs|walks|turns|grabs|opens|closes|holds|reaches|steps|falls)\b.*\b(runs|walks|turns|grabs|opens|closes|holds|reaches|steps|falls)\b',
         "Multiple distinct actions in one scene"),
    ]

    def __init__(self, max_characters_per_clip: int = 2, max_actions_per_clip: int = 3):
        self.max_characters = max_characters_per_clip
        self.max_actions = max_actions_per_clip

    def analyze(self, scene: PlanarScene) -> list[SceneFinding]:
        findings: list[SceneFinding] = []
        description = scene.description or ""
        if scene.complexity == "HIGH":
            findings.append(SceneFinding("CRITICAL", "HIGH_COMPLEXITY",
                f"Scene complexity is HIGH — high risk of generation failure.",
                "Simplify the description: reduce to one clear action, one subject."))
        for pattern, msg in self.SIMULTANEOUS_PATTERNS:
            if re.search(pattern, description, re.IGNORECASE):
                findings.append(SceneFinding("CRITICAL", "SIMULTANEOUS_ACTIONS", msg,
                    "Rewrite as sequential actions using 'and then'."))
                break
        if scene.continuity_dna:
            try:
                dna = json.loads(scene.continuity_dna)
                n_chars = len(dna.get("characters", []))
                if n_chars > self.max_characters:
                    findings.append(SceneFinding("WARNING", "TOO_MANY_CHARACTERS",
                        f"{n_chars} characters (max: {self.max_characters}).",
                        "Reduce to 1-2 characters."))
                if "visual_anchors" not in dna:
                    findings.append(SceneFinding("WARNING", "MISSING_VISUAL_ANCHORS",
                        "Missing visual_anchors.", "Add color_palette, lighting, camera_style."))
            except (json.JSONDecodeError, TypeError):
                findings.append(SceneFinding("CRITICAL", "INVALID_CONTINUITY_DNA",
                    "Continuity DNA is not valid JSON.", "Fix the story engine."))
        action_verbs = ["runs", "walks", "turns", "looks", "grabs", "opens",
                         "closes", "holds", "reaches", "steps", "falls", "flees"]
        found = [v for v in action_verbs if v in description.lower()]
        if len(found) > self.max_actions:
            findings.append(SceneFinding("WARNING", "TOO_MANY_ACTIONS",
                f"{len(found)} distinct actions (max: {self.max_actions}).",
                "Simplify to 1-2 core actions."))
        severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        findings.sort(key=lambda f: severity_order.get(f.severity, 3))
        return findings

    def get_optimization_summary(self, findings: list[SceneFinding]) -> dict[str, Any]:
        critical = [f for f in findings if f.severity == "CRITICAL"]
        warnings = [f for f in findings if f.severity == "WARNING"]
        return {
            "total": len(findings),
            "critical": len(critical),
            "warnings": len(warnings),
            "info": len(findings) - len(critical) - len(warnings),
            "optimization_applied": len(critical) == 0 and len(warnings) == 0,
            "critical_findings": [{"code": f.code, "message": f.message, "suggestion": f.suggestion} for f in critical],
            "warning_findings": [{"code": f.code, "message": f.message, "suggestion": f.suggestion} for f in warnings],
        }


def optimize_scene_description(description: str, findings: list[SceneFinding]) -> str:
    optimized = description.strip()
    for finding in findings:
        if finding.code == "SIMULTANEOUS_ACTIONS":
            optimized = re.sub(r'\b(simultaneously|meanwhile|at the same time)\b', 'and then', optimized, flags=re.IGNORECASE)
            optimized = re.sub(r'\bwhile\s+(\w+)', r'and then \1', optimized, flags=re.IGNORECASE)
            optimized = re.sub(r'\bas\s+(\w+)\s+(is|does|goes)', r'and then \1 is', optimized, flags=re.IGNORECASE)
        elif finding.code == "LONG_DESCRIPTION":
            words = optimized.split()
            if len(words) > 50:
                optimized = " ".join(words[:50]) + "."
        elif finding.code == "TOO_MANY_ACTIONS":
            action_verbs = ["runs", "walks", "turns", "looks", "grabs", "opens",
                             "closes", "holds", "reaches", "steps", "falls", "flees"]
            action_positions = []
            for verb in action_verbs:
                pattern = re.compile(rf'\b{re.escape(verb)}\b', re.IGNORECASE)
                match = pattern.search(optimized)
                if match:
                    action_positions.append((match.start(), verb))
            if len(action_positions) > 3:
                cutoff_pos = action_positions[2][0]
                remaining = optimized[cutoff_pos:]
                sentence_end = re.search(r'[.!?]', remaining)
                if sentence_end:
                    optimized = optimized[:cutoff_pos + sentence_end.start() + 1]
                else:
                    optimized = optimized[:cutoff_pos] + "."
    return optimized.strip()