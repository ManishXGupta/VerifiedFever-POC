"""Weekly wILI series and CDC onset weeks for 11 locations x 9 seasons (2010/11-2018/19)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[2] / "data" / "ilinet" / "flusight_target_multivals.csv"


def load() -> list[dict]:
    d = pd.read_csv(SRC)
    out = []
    for (loc, season), g in d.groupby(["Location", "Season"], sort=True):
        g = g.sort_values("Model Week")
        one = g[g.Target == "1 wk ahead"].drop_duplicates("Model Week")
        weeks = list(one["Calendar Week"].astype(int))
        # value on row for week w is wILI of the next week; label each value with that next week
        vals = [float(v) for v in one["Valid Bin_start_incl"]]
        next_weeks = weeks[1:] + [None]
        if next_weeks[-1] is None:
            last = weeks[-1]
            next_weeks[-1] = 1 if last >= 52 and last + 1 > (53 if 53 in weeks else 52) else last + 1
        onset = g[g.Target == "Season onset"]["Valid Bin_start_incl"].iloc[0]
        peak = g[g.Target == "Season peak week"]["Valid Bin_start_incl"].astype(str).tolist()
        onset_idx = next_weeks.index(int(onset)) if onset != "none" and int(onset) in next_weeks else None
        out.append({"location": loc, "season": season, "weeks": next_weeks, "wili": vals,
                    "onset_week": None if onset == "none" else int(onset), "onset_idx": onset_idx,
                    "peak_weeks": sorted({int(float(p)) for p in peak if p != "none"})})
    return out


if __name__ == "__main__":
    S = load()
    print(len(S), "location-seasons;", sum(s["onset_idx"] is not None for s in S), "with onset")
    s = [x for x in S if x["location"] == "US National" and x["season"] == "2014/2015"][0]
    print(s["weeks"][:14], s["wili"][:14], s["onset_week"], s["onset_idx"])
