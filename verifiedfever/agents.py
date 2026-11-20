"""Agentic orchestration layer with policy guardrails and a human in the loop.

Agents (each a goal-directed component that calls tools and records every action):
  IntakeAgent        verify the signed reading and triage it (tools: verifier, rule engine)
  CertificateAgent   prepare a nurse brief and queue the certificate by clinical priority
  CommunicationAgent after human approval, draft the parent notice and the school share package
  SurveillanceAgent  every school day, watch class and school counts of verified fevers,
                     raise an alert, localize it to a class and propose playbook actions
  Orchestrator       routes events between agents and the human nurse queue

Guardrails (PolicyGuard), applied to every agent action and every outbound message:
  * only a human may approve or reject a certificate (agents can only prepare it)
  * messages to a school may contain only the minimal certificate fields, never temperatures
  * messages to public health may contain counts and class labels only, never student identifiers
  * free text supplied by users (for example a parent note) is data, never an instruction
  * every action, allowed or blocked, goes to a hash-chained, tamper-evident audit log

Drafting: a Drafter turns structured facts into text. The default TemplateDrafter is
deterministic; an LLM drafter can be plugged in (see LLMDrafter), and its output passes the
same guardrails, so a model cannot leak data the policy forbids.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

import numpy as np

from . import crypto
from .rules import Decision
from .service import APPROVED, CLINICAL, FeverCertService
from .surveillance import alert_today, localize

# a body temperature: 34-43 with a decimal or a degree unit (plain counts such as "38 students" do not match)
TEMP_PATTERN = re.compile(r"\b(?:3[4-9]|4[0-3])(?:[.,]\d+\s*(?:°\s*)?[CF]?|\s*°\s*[CF]?|\s*(?:deg|degrees)\b)", re.I)
SCHOOL_FIELDS = {"cert_id", "student_id", "reason", "absence_start", "absence_end", "status",
                 "validated_by", "validated_at", "evidence_digest", "issued_at", "issuer_sig", "text"}
HUMAN_ONLY = {"approve_certificate", "reject_certificate"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ audit log
class AuditLog:
    """Append-only log; each entry carries the hash of the previous one."""

    def __init__(self):
        self.entries: list[dict] = []

    def add(self, agent: str, action: str, allowed: bool, detail: dict, reason: str = "") -> dict:
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        body = {"seq": len(self.entries) + 1, "ts": _now(), "agent": agent, "action": action,
                "allowed": allowed, "reason": reason, "detail": detail, "prev": prev}
        body["hash"] = crypto.sha256_hex(crypto.canonical({k: v for k, v in body.items() if k != "hash"}))
        self.entries.append(body)
        return body

    def verify(self) -> bool:
        prev = "0" * 64
        for e in self.entries:
            if e["prev"] != prev:
                return False
            h = crypto.sha256_hex(crypto.canonical({k: v for k, v in e.items() if k != "hash"}))
            if h != e["hash"]:
                return False
            prev = e["hash"]
        return True


# ------------------------------------------------------------------ guardrails
class PolicyGuard:
    def __init__(self, audit: AuditLog, known_student_ids: Callable[[], set], known_names: Callable[[], set]):
        self.audit = audit
        self.ids = known_student_ids
        self.names = known_names
        self.blocked = 0

    def check_action(self, agent: str, action: str, detail: dict) -> bool:
        if action in HUMAN_ONLY and agent != "human":
            self.blocked += 1
            self.audit.add(agent, action, False, detail, "human-only action: agents may prepare, not decide")
            return False
        self.audit.add(agent, action, True, detail)
        return True

    def check_outbound(self, agent: str, recipient: str, message: dict) -> tuple[bool, str]:
        text = json.dumps(message, ensure_ascii=False)
        reason = ""
        if recipient == "school":
            extra = set(message) - SCHOOL_FIELDS
            if extra:
                reason = f"fields not allowed for school: {sorted(extra)}"
            elif TEMP_PATTERN.search(message.get("text", "")):
                reason = "temperature value in message to school"
        elif recipient == "public_health":
            if any(sid in text for sid in self.ids()) or any(n and n in text for n in self.names()):
                reason = "student identifier in public-health message"
            elif TEMP_PATTERN.search(message.get("text", "")):
                reason = "individual temperature in public-health message"
        elif recipient == "parent":
            pass  # parents may see their own child's readings
        elif recipient == "nurse":
            pass
        else:
            reason = f"recipient '{recipient}' not permitted"
        ok = not reason
        if not ok:
            self.blocked += 1
        self.audit.add(agent, f"send:{recipient}", ok, {"keys": sorted(message)}, reason)
        return ok, reason


# ------------------------------------------------------------------ drafting
class Drafter(Protocol):
    def draft(self, kind: str, facts: dict) -> str: ...


class TemplateDrafter:
    def draft(self, kind: str, facts: dict) -> str:
        if kind == "nurse_brief":
            r = facts["readings"][-1]
            pri = "PRIORITY: clinical review. " if facts["escalated"] else ""
            return (f"{pri}{facts['student_name']}: {r['temp_c']:.1f} C on {r['ts'][:10]}, "
                    f"baseline {r['baseline_c']:.1f} C ({r['deviation_c']:+.1f} C). Reasons: {'; '.join(facts['reasons'])}.")
        if kind == "parent_notice":
            return (f"The absence certificate for {facts['absence_start']} to {facts['absence_end']} was approved by "
                    f"{facts['validated_by']}. Share it with the school using code {facts['share_code']}.")
        if kind == "school_notice":
            return (f"Fever-related absence {facts['absence_start']} to {facts['absence_end']}, validated by "
                    f"{facts['validated_by']}. Verify with the issuer key.")
        if kind == "outbreak_alert":
            return (f"Possible respiratory outbreak signal on school day {facts['day']}: {facts['school_count']} "
                    f"verified fevers today (expected about {facts['expected']:.0f}). Most affected: class "
                    f"{facts['class_label']} ({facts['class_count']} today). Suggested: {', '.join(facts['actions'])}.")
        return ""


class LLMDrafter:
    """Optional: drafts with an LLM when ANTHROPIC_API_KEY is set; falls back to templates.

    Not used in the experiments. Whatever it writes still passes PolicyGuard.check_outbound.
    """

    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.model, self.fallback = model, TemplateDrafter()

    def draft(self, kind: str, facts: dict) -> str:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self.fallback.draft(kind, facts)
        try:
            import anthropic  # type: ignore
            msg = anthropic.Anthropic().messages.create(
                model=self.model, max_tokens=200,
                messages=[{"role": "user", "content": f"Write a short, plain {kind.replace('_', ' ')} from these "
                           f"facts only. Do not add facts.\n{json.dumps(facts, default=str)}"}])
            return msg.content[0].text
        except Exception:  # noqa: BLE001
            return self.fallback.draft(kind, facts)


# ------------------------------------------------------------------ agents
@dataclass
class Alert:
    day: int
    rules: list
    class_label: int
    school_count: int
    expected: float
    actions: list
    text: str
    delivered: bool


PLAYBOOK = ["notify school nurse", "remind families of fever-free return rule",
            "increase cleaning and ventilation in the affected class", "inform local public health (counts only)"]


class IntakeAgent:
    name = "intake"

    def __init__(self, svc: FeverCertService, guard: PolicyGuard):
        self.svc, self.guard = svc, guard

    def run(self, signed: dict, claimed_student_id: Optional[str], now, note: Optional[str] = None):
        # A free-text note is stored as data and never read as an instruction.
        self.guard.check_action(self.name, "verify_and_triage",
                                {"device": signed.get("payload", {}).get("device_id"), "has_note": bool(note)})
        return self.svc.submit(signed, claimed_student_id=claimed_student_id, now=now)


class CertificateAgent:
    name = "certificate"

    def __init__(self, svc, guard, drafter: Drafter):
        self.svc, self.guard, self.drafter = svc, guard, drafter

    def prepare(self, cert_id: str) -> dict:
        item = next(c for c in self.svc.nurse_queue() if c["cert_id"] == cert_id)
        brief = self.drafter.draft("nurse_brief", item)
        self.guard.check_action(self.name, "prepare_nurse_brief", {"cert_id": cert_id})
        return {"cert_id": cert_id, "priority": 0 if item["escalated"] else 1, "brief": brief,
                "student": item["student_name"]}

    def try_approve(self, cert_id: str) -> bool:
        """Agents are not allowed to approve. Used to test the guardrail."""
        return self.guard.check_action(self.name, "approve_certificate", {"cert_id": cert_id})


class CommunicationAgent:
    name = "communication"

    def __init__(self, svc, guard, drafter: Drafter):
        self.svc, self.guard, self.drafter = svc, guard, drafter

    def after_approval(self, cert_id: str, now) -> dict:
        sh = self.svc.share(cert_id, now=now)
        rec = sh["package"]["certificate"]
        parent = {"text": self.drafter.draft("parent_notice", {**rec, "share_code": sh["share_code"]})}
        ok_p, _ = self.guard.check_outbound(self.name, "parent", parent)
        school = {**{k: rec[k] for k in rec if k in SCHOOL_FIELDS},
                  "text": self.drafter.draft("school_notice", rec)}
        ok_s, why = self.guard.check_outbound(self.name, "school", school)
        delivered = None
        if ok_s:
            delivered = self.svc.school_receive(share_code=sh["share_code"], school_user="School office (agent relay)",
                                                now=now)["result"]
        return {"parent_sent": ok_p, "school_sent": ok_s, "school_result": delivered, "blocked_reason": why}


class SurveillanceAgent:
    name = "surveillance"

    def __init__(self, guard, drafter: Drafter, n_classes: int, h: float, class_threshold: int, warmup: int = 14):
        self.guard, self.drafter = guard, drafter
        self.h, self.cthr, self.warmup, self.C = h, class_threshold, warmup, n_classes
        self.school: list[int] = []
        self.by_class: list[np.ndarray] = []
        self.alerts: list[Alert] = []

    def observe_day(self, class_counts: np.ndarray) -> Optional[Alert]:
        self.by_class.append(np.asarray(class_counts, dtype=int))
        self.school.append(int(np.sum(class_counts)))
        res = alert_today(self.school, class_counts, self.h, self.cthr, self.warmup)
        if not res:
            return None
        day = res["day"]
        cls = localize(np.stack(self.by_class, axis=1), day)
        base = self.school[max(0, day - 28):max(0, day - 3)] or [0]
        facts = {"day": day, "school_count": self.school[-1], "expected": float(np.mean(base)),
                 "class_label": cls, "class_count": int(class_counts[cls]), "actions": PLAYBOOK}
        msg = {"text": self.drafter.draft("outbreak_alert", facts)}
        ok, _ = self.guard.check_outbound(self.name, "public_health", msg)
        alert = Alert(day, res["rules"], cls, facts["school_count"], facts["expected"], PLAYBOOK, msg["text"], ok)
        self.alerts.append(alert)
        return alert


@dataclass
class Orchestrator:
    svc: FeverCertService
    class_of: dict = field(default_factory=dict)  # student_id -> class index
    n_classes: int = 1
    h: float = 12
    class_threshold: int = 5
    drafter: Drafter = field(default_factory=TemplateDrafter)

    def __post_init__(self):
        self.audit = AuditLog()
        self.guard = PolicyGuard(self.audit,
                                 lambda: {s["student_id"] for s in self.svc.students()},
                                 lambda: {s["student_name"] for s in self.svc.students()})
        self.intake = IntakeAgent(self.svc, self.guard)
        self.certs = CertificateAgent(self.svc, self.guard, self.drafter)
        self.comms = CommunicationAgent(self.svc, self.guard, self.drafter)
        self.surv = SurveillanceAgent(self.guard, self.drafter, self.n_classes, self.h, self.class_threshold)
        self.nurse_queue: dict[str, dict] = {}
        self.today_flags: dict[int, int] = {}
        self.stats = {"readings": 0, "accepted": 0, "certificates": 0, "escalated": 0, "agent_actions": 0,
                      "human_actions": 0, "schools_accepted": 0}

    # event: a reading arrives
    def handle_reading(self, signed, claimed_student_id=None, now=None, note=None):
        res = self.intake.run(signed, claimed_student_id, now, note)
        self.stats["readings"] += 1
        self.stats["agent_actions"] += 1
        if res.verdict.value == "accepted":
            self.stats["accepted"] += 1
            if res.decision in (Decision.CERTIFY, Decision.ESCALATE):
                sid = self.svc.db.execute("SELECT student_id FROM readings WHERE id=?", (res.reading_id,)).fetchone()[0]
                c = self.class_of.get(sid, 0)
                self.today_flags[c] = self.today_flags.get(c, 0) + 1
            if res.certificate_id and res.certificate_id not in self.nurse_queue:
                self.nurse_queue[res.certificate_id] = self.certs.prepare(res.certificate_id)
                self.stats["agent_actions"] += 1
        return res

    def pending_for_nurse(self) -> list[dict]:
        """Nurse sees escalated (clinical review) items first, then by arrival."""
        return sorted(self.nurse_queue.values(), key=lambda x: x["priority"])

    # human-in-the-loop step
    def nurse_decides(self, cert_id: str, approve: bool, nurse: str, now=None):
        self.guard.check_action("human", "approve_certificate" if approve else "reject_certificate", {"cert_id": cert_id})
        self.svc.decide(cert_id, approve, nurse, now=now)
        self.stats["human_actions"] += 1
        self.nurse_queue.pop(cert_id, None)
        if approve:
            out = self.comms.after_approval(cert_id, now)
            self.stats["agent_actions"] += 1
            self.stats["schools_accepted"] += out["school_result"] in ("accepted", "already_accepted")
            return out
        return None

    # event: end of a school day
    def end_of_day(self) -> Optional[Alert]:
        counts = np.zeros(self.n_classes, dtype=int)
        for c, n in self.today_flags.items():
            counts[c] = n
        self.today_flags = {}
        self.stats["agent_actions"] += 1
        return self.surv.observe_day(counts)
