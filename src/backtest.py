"""Is a team's wOBA - xwOBA gap (results vs. contact quality) a skill or noise?

Uses Savant team expected stats 2021-2026: 30 teams x 5 season pairs = 150 pairs.
  - year-to-year correlation of the gap, with a team-clustered bootstrap CI
  - teams with a gap of -.010 or worse: their gap and wOBA change the next season
  - 2026 split-half (odd vs. even team games) correlation of the gap
Output: outputs/backtest.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import diagnosis as dg

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "outputs"


def season_pairs(side: str) -> pd.DataFrame:
    d = pd.concat(pd.read_csv(f) for f in sorted(RAW.glob(f"team_{side}_*.csv")))
    d = d[d["half"] == "full"].assign(gap=lambda x: x["woba"] - x["xwoba"])
    w = d.pivot(index="team", columns="season", values=["gap", "woba"])
    rows = []
    for s in range(2021, 2026):
        for t in w.index:
            rows.append({"team": t, "season": s, "gap": w.loc[t, ("gap", s)], "gap_next": w.loc[t, ("gap", s + 1)],
                         "woba": w.loc[t, ("woba", s)], "woba_next": w.loc[t, ("woba", s + 1)]})
    return pd.DataFrame(rows)


def clustered_r(d: pd.DataFrame, n_boot: int = 2000, seed: int = 3) -> dict:
    r = np.corrcoef(d["gap"], d["gap_next"])[0, 1]
    teams = d["team"].unique()
    rng = np.random.default_rng(seed)
    g = {t: x for t, x in d.groupby("team")}
    b = []
    for _ in range(n_boot):
        s = pd.concat([g[t] for t in rng.choice(teams, len(teams))])
        b.append(np.corrcoef(s["gap"], s["gap_next"])[0, 1])
    lo, hi = np.percentile(b, [2.5, 97.5])
    return {"r": r, "ci": [lo, hi], "pairs": len(d)}


def split_half(side: str) -> float:
    p = pd.read_pickle(OUT / "pitches_prepared.pkl")
    key = "bat_team" if side == "bat" else "fld_team"
    n = p.groupby(key)["game_pk"].rank(method="dense")
    a, b = dg.batting(p[n % 2 == 1], key), dg.batting(p[n % 2 == 0], key)
    return float(np.corrcoef(a["woba"] - a["xwoba"], b["woba"] - b["xwoba"])[0, 1])


if __name__ == "__main__":
    bat, pit = season_pairs("bat"), season_pairs("pit")
    low = bat[bat["gap"] <= -0.010]
    high = bat[bat["gap"] >= 0.010]
    out = {
        "batting_gap_year_to_year": clustered_r(bat),
        "pitching_gap_year_to_year": clustered_r(pit),
        "teams_gap_minus_010_or_worse": {"n": len(low), "gap": low["gap"].mean(),
                                         "gap_next": low["gap_next"].mean(),
                                         "woba_change_next": (low["woba_next"] - low["woba"]).mean()},
        "teams_gap_plus_010_or_better": {"n": len(high), "gap": high["gap"].mean(),
                                         "gap_next": high["gap_next"].mean()},
        "split_half_2026_batting": split_half("bat"),
        "split_half_2026_pitching": split_half("pit"),
    }
    (OUT / "backtest.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print(json.dumps(out, indent=2, default=float))
