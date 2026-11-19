"""Cost and time saved when a verified digital certificate replaces a clinic visit
made only to obtain an absence note for a minor fever.

Inputs (2026 sources; low and high values are scenario assumptions):
  visit_price      average price of an urgent care visit $220 and of a primary care visit $224
                   (HCCI report, Jan. 2026, employer-insured claims); scenarios $150 / $220 / $300
  parent_hours     travel + waiting + visit time for one parent; assumption 1.5 / 2.0 / 3.0 h
  wage             average hourly earnings, private nonfarm, $37.53 (BLS, May 2026)
  miles            round trip to the clinic; assumption 10 / 15 / 25 miles
  cost_per_mile    IRS 2026 business standard mileage rate from July 1, 2026, $0.76 (vehicle operating cost)
  note_visit_share share of students who would otherwise make one note-only visit per school year;
                   assumption 10% / 20% / 30% (many districts require medical documentation after
                   3 to 10 illness absences, e.g. Mississippi SB 2103, effective July 2026)
  nurse_minutes    nurse time to review and approve one certificate; assumption 3 minutes
  nurse_wage       assumption $45/h
  device_cost      one registered thermometer per student, assumption $30 one-time

Usage:  python experiments/cost_model.py
Output: experiments/results/cost_results.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "results"

WAGE = 37.53
COST_PER_MILE = 0.76
SCENARIOS = {
    "low": dict(visit_price=150, parent_hours=1.5, miles=10, note_visit_share=0.10),
    "base": dict(visit_price=220, parent_hours=2.0, miles=15, note_visit_share=0.20),
    "high": dict(visit_price=300, parent_hours=3.0, miles=25, note_visit_share=0.30),
}
SCHOOL_SIZE = 500
NURSE_MIN, NURSE_WAGE, DEVICE_COST = 3, 45.0, 30.0


def per_visit(s: dict) -> dict:
    time_cost = s["parent_hours"] * WAGE
    travel = s["miles"] * COST_PER_MILE
    gross = s["visit_price"] + time_cost + travel
    nurse = NURSE_MIN / 60 * NURSE_WAGE
    return dict(visit_price=s["visit_price"], parent_time_cost=round(time_cost, 2), travel=round(travel, 2),
                gross_saving=round(gross, 2), nurse_review_cost=round(nurse, 2),
                net_saving=round(gross - nurse, 2), parent_hours_saved=s["parent_hours"])


def per_school(s: dict) -> dict:
    v = per_visit(s)
    visits = SCHOOL_SIZE * s["note_visit_share"]
    annual = visits * v["net_saving"]
    devices = SCHOOL_SIZE * DEVICE_COST
    return dict(students=SCHOOL_SIZE, visits_avoided=visits, annual_net_saving=round(annual),
                parent_hours_saved=round(visits * s["parent_hours"]),
                one_time_device_cost=round(devices), payback_years=round(devices / annual, 2))


def main():
    res = {k: {"per_visit": per_visit(s), "per_school_year": per_school(s), "inputs": s} for k, s in SCENARIOS.items()}
    res["constants"] = dict(wage=WAGE, cost_per_mile=COST_PER_MILE, school_size=SCHOOL_SIZE,
                            nurse_minutes=NURSE_MIN, nurse_wage=NURSE_WAGE, device_cost=DEVICE_COST)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_results.json").write_text(json.dumps(res, indent=2))
    for k in SCENARIOS:
        print(k, res[k]["per_visit"], res[k]["per_school_year"])


if __name__ == "__main__":
    main()
