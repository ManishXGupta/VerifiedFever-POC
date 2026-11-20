"""Physician-in-the-loop triage with guardrails.

TriageAgent    turns each individual fever flag into a queue item for the person's physician
               (urgent first: >= 39.5 C, third fever day in a row, or an older adult), or into a
               self-care notice when the person has not shared data with a physician.
CohortAgent    turns daily cohort alerts into a counts-only draft for public health; a human
               (physician or public health officer) must confirm before anything is sent, and an
               alert for the same group is not repeated within 7 days.
Guard          every action and message is checked and written to the hash-chained audit log:
               clinical decisions and alert confirmations are human-only; public health receives
               counts for groups of at least K_MIN reporters and no identifiers or temperatures;
               a physician receives only consenting patients; free text is treated as data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from verifiedfever.agents import TEMP_PATTERN, AuditLog

from .registry import K_MIN, Registry

HUMAN_ONLY = {"clinical_decision", "confirm_outbreak_alert"}
PID_PATTERN = re.compile(r"\bP\d{3,}\b")


class Guard:
    def __init__(self, registry: Registry, audit: AuditLog):
        self.reg, self.audit, self.blocked = registry, audit, 0

    def action(self, actor: str, action: str, detail: dict) -> bool:
        ok = not (action in HUMAN_ONLY and actor != "human")
        self.audit.add(actor, action, ok, detail, "" if ok else "human-only action")
        self.blocked += not ok
        return ok

    def outbound(self, actor: str, recipient: str, msg: dict) -> bool:
        reason = ""
        text = str(msg.get("text", ""))
        if recipient == "public_health":
            if PID_PATTERN.search(text) or "person_id" in msg:
                reason = "identifier in a public health message"
            elif TEMP_PATTERN.search(text):
                reason = "individual temperature in a public health message"
            elif any((g.get("reporters") or 0) < K_MIN for g in msg.get("groups", [])):
                reason = "group below the small-cell threshold"
        elif recipient == "physician":
            pid = msg.get("person_id")
            if not pid or not self.reg.has_consent(pid, "physician"):
                reason = "person has not shared data with a physician"
        elif recipient != "person":
            reason = f"recipient '{recipient}' not allowed"
        ok = not reason
        self.audit.add(actor, f"send_to_{recipient}", ok, {k: v for k, v in msg.items() if k != "text"}, reason)
        self.blocked += not ok
        return ok


@dataclass
class QueueItem:
    item_id: int
    person_id: str
    priority: str
    summary: dict
    note: str = ""
    decision: str | None = None


@dataclass
class Triage:
    registry: Registry
    audit: AuditLog = field(default_factory=AuditLog)
    queue: list = field(default_factory=list)
    alerts_sent: list = field(default_factory=list)
    _last_alert: dict = field(default_factory=dict)
    counts: dict = field(default_factory=lambda: {"agent_actions": 0, "human_actions": 0, "self_care": 0})

    def __post_init__(self):
        self.guard = Guard(self.registry, self.audit)

    # ---- individual
    def on_reading(self, result: dict, note: str = "") -> QueueItem | None:
        if not result.get("accepted") or not result.get("fever"):
            return None
        urgent = result["temp_c"] >= 39.5 or result["fever_days_in_row"] >= 3 or result["age_band"] == "older"
        msg = {"person_id": result["person_id"], "day": result["day"],
               "summary": f"fever day {result['fever_days_in_row']}, {result['deviation_c']:+.1f} C vs own baseline"}
        self.counts["agent_actions"] += 1
        if not self.guard.outbound("triage_agent", "physician", msg):
            self.guard.outbound("triage_agent", "person", {"person_id": result["person_id"],
                                                           "text": "Fever recorded. Rest, fluids; seek care if worse."})
            self.counts["self_care"] += 1
            return None
        item = QueueItem(len(self.queue) + 1, result["person_id"], "urgent" if urgent else "routine", msg, note)
        self.queue.append(item)
        return item

    def pending(self) -> list[QueueItem]:
        items = [q for q in self.queue if q.decision is None]
        return sorted(items, key=lambda q: (q.priority != "urgent", q.item_id))

    def decide(self, actor: str, item_id: int, decision: str) -> bool:
        if not self.guard.action(actor, "clinical_decision", {"item": item_id, "decision": decision}):
            return False
        next(q for q in self.queue if q.item_id == item_id).decision = decision
        self.counts["human_actions"] += 1
        return True

    # ---- cohort
    def on_day(self, day: int, alerts: list[dict]) -> list[dict]:
        drafts = []
        for a in alerts:
            key = (a["group_type"], a["group"])
            if day - self._last_alert.get(key, -99) < 7:
                continue
            self._last_alert[key] = day
            text = (f"Possible respiratory illness cluster in {a['group_type'].replace('_', ' ')} {a['group']}: "
                    + (f"{a['fevers']} of {a['reporters']} members febrile today." if a["rule"] == "count"
                       else f"synchronized temperature rise across {a['reporters']} members (z = {a['z']})."))
            drafts.append({"day": day, "group_type": a["group_type"], "group": a["group"], "rule": a["rule"],
                           "groups": [{"group": a["group"], "reporters": a["reporters"]}], "text": text})
            self.counts["agent_actions"] += 1
        return drafts

    def confirm_alert(self, actor: str, draft: dict) -> bool:
        if not self.guard.action(actor, "confirm_outbreak_alert", {"group": draft["group"], "day": draft["day"]}):
            return False
        self.counts["human_actions"] += 1
        if self.guard.outbound("cohort_agent", "public_health", draft):
            self.alerts_sent.append(draft)
            return True
        return False
