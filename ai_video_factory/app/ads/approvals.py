"""Human approval gate — the money layer. No approval, no spend.

Every financially significant or destructive action (publish, spend, budget
change, delete, strategy override) must carry a granted approval id issued
here. Approvals are explicit, auditable, and revocable. Deny-by-default.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

#: Ops that ALWAYS require a granted approval before execution.
GATED_OPS = frozenset(
    {
        "publish_campaign",
        "spend",
        "budget_change",
        "bid_change",
        "delete_campaign",
        "delete_adset",
        "delete_ad",
        "strategy_override",
        "account_change",
    }
)


@dataclass
class Approval:
    id: str
    op: str
    subject: str  # e.g. campaign name / id the op targets
    detail: str = ""
    granted: bool = False
    decided_at: str = ""
    requested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ApprovalGate:
    """Request/grant/deny store with an audit trail. Deny-by-default."""

    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}
        self.audit: list[str] = []

    # ------------------------------------------------------------------ #
    def request(self, op: str, subject: str, detail: str = "") -> Approval:
        approval = Approval(id="apr_" + uuid4().hex[:8], op=op, subject=subject,
                            detail=detail)
        self._approvals[approval.id] = approval
        self._log(f"REQUEST {approval.id} op={op} subject={subject}")
        return approval

    def grant(self, approval_id: str) -> Approval:
        approval = self._require(approval_id)
        approval.granted = True
        approval.decided_at = datetime.now(timezone.utc).isoformat()
        self._log(f"GRANT {approval.id} op={approval.op}")
        return approval

    def deny(self, approval_id: str) -> Approval:
        approval = self._require(approval_id)
        approval.granted = False
        approval.decided_at = datetime.now(timezone.utc).isoformat()
        self._log(f"DENY {approval.id} op={approval.op}")
        return approval

    def check(self, op: str, approval_id: str | None) -> bool:
        """True only when op is gated AND the id exists AND was granted.

        Non-gated ops return True (no approval needed). Unknown/denied ids
        return False — execution must refuse.
        """
        if op not in GATED_OPS:
            return True
        if not approval_id:
            return False
        approval = self._approvals.get(approval_id)
        return bool(approval and approval.granted and approval.op == op)

    def require(self, op: str, approval_id: str | None, subject: str) -> None:
        """Raise PermissionError unless the op is approved. Execution agents
        call this first — it is the spend guardrail."""
        if not self.check(op, approval_id):
            self._log(f"BLOCKED op={op} subject={subject} (no approval)")
            raise PermissionError(
                f"Human approval required for '{op}' on '{subject}'. "
                "Request via ApprovalGate.request() and have the operator grant it."
            )

    # ------------------------------------------------------------------ #
    def _require(self, approval_id: str) -> Approval:
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise KeyError(f"Unknown approval id: {approval_id}") from None

    def _log(self, line: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        entry = f"{stamp} {line}"
        self.audit.append(entry)
        logger.info("approvals: %s", line)
