"""Personal-baseline fever rule engine.

Normal body temperature differs between people (Obermeyer et al., BMJ 2017),
so one fixed cutoff misses early fever in people whose normal is low. The
engine keeps the school's fixed policy cutoff and adds a personal rule:

  febrile  = temp >= fixed_cutoff
             OR (temp >= floor AND temp - baseline >= delta)

  ESCALATE if temp >= high_grade, or if febrile for repeat_days consecutive days
  CERTIFY  if febrile
  WATCH    if temp - baseline >= watch_delta (informational, no certificate)
  NORMAL   otherwise

The baseline is the median of the most recent afebrile readings in a sliding
window. Until enough readings exist, a population default is used.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence


class Decision(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    CERTIFY = "certify"
    ESCALATE = "escalate"


FEBRILE = {Decision.CERTIFY, Decision.ESCALATE}


@dataclass(frozen=True)
class Policy:
    fixed_cutoff_c: float = 38.0
    floor_c: float = 37.5
    delta_c: float = 1.0
    watch_delta_c: float = 0.7
    high_grade_c: float = 39.5
    repeat_days: int = 3
    baseline_window: int = 14
    baseline_min_readings: int = 5
    baseline_exclude_at_or_above_c: float = 37.5
    default_baseline_c: float = 36.8
    fever_free_hours_before_return: int = 24


@dataclass(frozen=True)
class Baseline:
    value_c: float
    n_readings: int
    is_default: bool


@dataclass
class Evaluation:
    decision: Decision
    baseline: Baseline
    deviation_c: float
    reasons: list[str] = field(default_factory=list)

    @property
    def febrile(self) -> bool:
        return self.decision in FEBRILE


def personal_baseline(history_c: Sequence[float], policy: Policy = Policy()) -> Baseline:
    """history_c: previous accepted readings, oldest first."""
    afebrile = [t for t in history_c if t < policy.baseline_exclude_at_or_above_c]
    recent = afebrile[-policy.baseline_window:]
    if len(recent) < policy.baseline_min_readings:
        return Baseline(policy.default_baseline_c, len(recent), True)
    return Baseline(round(statistics.median(recent), 3), len(recent), False)


def is_febrile(temp_c: float, baseline_c: float, policy: Policy = Policy()) -> bool:
    return temp_c >= policy.fixed_cutoff_c or (
        temp_c >= policy.floor_c and temp_c - baseline_c >= policy.delta_c
    )


def evaluate(
    temp_c: float,
    history_c: Sequence[float],
    prior_consecutive_febrile_days: int = 0,
    policy: Policy = Policy(),
) -> Evaluation:
    base = personal_baseline(history_c, policy)
    dev = round(temp_c - base.value_c, 3)
    reasons: list[str] = []
    febrile = is_febrile(temp_c, base.value_c, policy)
    if temp_c >= policy.fixed_cutoff_c:
        reasons.append(f"at or above school cutoff {policy.fixed_cutoff_c:.1f} C")
    elif febrile:
        reasons.append(f"{dev:+.1f} C above personal baseline {base.value_c:.1f} C")

    if temp_c >= policy.high_grade_c:
        reasons.append(f"high-grade fever (>= {policy.high_grade_c:.1f} C): refer to clinician")
        return Evaluation(Decision.ESCALATE, base, dev, reasons)
    if febrile and prior_consecutive_febrile_days + 1 >= policy.repeat_days:
        reasons.append(f"fever on {prior_consecutive_febrile_days + 1} consecutive days: refer to clinician")
        return Evaluation(Decision.ESCALATE, base, dev, reasons)
    if febrile:
        return Evaluation(Decision.CERTIFY, base, dev, reasons)
    if dev >= policy.watch_delta_c:
        reasons.append(f"{dev:+.1f} C above personal baseline: watch, no certificate")
        return Evaluation(Decision.WATCH, base, dev, reasons)
    return Evaluation(Decision.NORMAL, base, dev, reasons)


def fixed_rule(temp_c: float, cutoff_c: float) -> bool:
    """Comparator used in the experiments: one cutoff for everyone."""
    return temp_c >= cutoff_c


def consecutive_days_ending(days_febrile: Iterable[bool]) -> int:
    """Count trailing True values (most recent day last)."""
    n = 0
    for flag in reversed(list(days_febrile)):
        if not flag:
            break
        n += 1
    return n
