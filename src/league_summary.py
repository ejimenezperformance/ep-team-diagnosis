"""All 30 teams: split each run differential into process and results.

process = runs from contact quality (offense and pitching, xwOBA), fielding,
          framing and baserunning
results = runs from results vs. contact (wOBA - xwOBA, both sides) and sequencing
Output: outputs/league_summary.csv
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
PROCESS = {"Contact quality (xwOBA)", "Baserunning", "Starting pitching (xwOBA)",
           "Relief pitching (xwOBA)", "Fielding (Savant)", "Catcher framing"}
RESULTS = {"Results vs contact", "Sequencing, other", "Results allowed vs. contact, other"}

rows = []
for f in sorted(OUT.glob("*_diagnosis.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    b = {r["step"]: r["runs"] for r in d["bridge"]}
    k = d["kpis"]
    rows.append({"team": d["team"], "name": d["name"], "wins": k["wins"], "losses": k["losses"],
                 "run_diff": k["run_diff"],
                 "process_runs": sum(b[s] for s in PROCESS),
                 "results_runs": sum(b[s] for s in RESULTS),
                 "offense_results_vs_contact": b["Results vs contact"],
                 "oaa": k["oaa"]})
s = pd.DataFrame(rows)
s["process_wins"] = 81 + s["process_runs"] / 10.5
s = s.sort_values("process_runs", ascending=False).round(1)
s.to_csv(OUT / "league_summary.csv", index=False, encoding="utf-8")
print(s.to_string(index=False))
