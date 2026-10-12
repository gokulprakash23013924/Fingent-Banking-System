from __future__ import annotations

from ..util import fmt_ts
from .base import AgentResult, BaseAgent


class NotificationAgent(BaseAgent):
    """Customer alerts: reads the alert feed and writes confirmations after actions."""
    name = "notification"

    def send(self, message: str, severity: str = "info", txn_id: str | None = None):
        return self.call("send_alert", customer_id=self.cid, message=message, severity=severity, txn_id=txn_id)

    def _view_alerts(self, ent) -> AgentResult:
        r = self.call("list_alerts", customer_id=self.cid, limit=5)
        if not r.ok:
            return self.fail("view_alerts", r)
        al = r.data["alerts"]
        if not al:
            return AgentResult(self.name, "view_alerts", "ok", "You have no alerts.", {"alerts": []})
        lines = [f"• [{a['severity']}] {fmt_ts(a['created_at'])}: {a['message']}" for a in al]
        return AgentResult(self.name, "view_alerts", "ok", "Your latest alerts:\n" + "\n".join(lines),
                           {"alerts": [{"alert_id": a["alert_id"], "severity": a["severity"], "message": a["message"], "created_at": a["created_at"]} for a in al]})
