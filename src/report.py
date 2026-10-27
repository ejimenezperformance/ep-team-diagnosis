"""Build the data-driven parts of a team diagnosis for any 2026 team.

Usage: python src/report.py NYM        (writes outputs/<TEAM>_diagnosis.json)
       python src/report.py ALL        (all 30 teams)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import diagnosis as dg

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "outputs"
HALF_CUT = "2026-07-16"     # first game after the All-Star break (no games Jul 13-15)


def load() -> dict:
    cache = OUT / "pitches_prepared.pkl"
    if cache.exists():
        p = pd.read_pickle(cache)
    else:
        p = dg.prepare(pd.read_csv(RAW / "pitches_2026.csv", low_memory=False))
        p.to_pickle(cache)
    oaa = pd.read_csv(RAW / "oaa_team_2026.csv")
    oaa["abbr"] = oaa["team_name"].map({v: k for k, v in dg.TEAM_NAMES.items()})
    fc = pd.read_csv(RAW / "framing_catchers_2026.csv")
    frp = pd.read_csv(RAW / "fielding_players_2026.csv")
    frp["abbr"] = frp["display_team_name"].map({v: k for k, v in dg.TEAM_NAMES.items()})
    br = pd.read_csv(RAW / "baserunning_players_2026.csv")
    caught = p.groupby(["fielder_2", "fld_team"]).size().rename("n").reset_index()
    caught["share"] = caught["n"] / caught.groupby("fielder_2")["n"].transform("sum")
    caught = caught.merge(fc[["id", "rv_tot"]], left_on="fielder_2", right_on="id", how="inner")
    framing = (caught["share"] * caught["rv_tot"]).groupby(caught["fld_team"]).sum()
    return {"p": p, "res": dg.results(p), "off": dg.batting(p, "bat_team"),
            "allowed": dg.batting(p, "fld_team"), "lg": dg.league(p),
            "oaa": oaa.set_index("abbr"), "framing": framing - framing.mean(),   # runs vs. the average team
            "fielding": frp.groupby("abbr")["fielding_runs_prevented"].sum(),
            "baserunning": br.groupby("team_name")["runner_runs_tot"].sum()}


def role_tables(p: pd.DataFrame) -> dict:
    return {r: dg.batting(p[p["role"] == r], "fld_team") for r in ("SP", "RP")}


def pitch_types(p: pd.DataFrame, team: str) -> list:
    t = p[p["fld_team"] == team]
    rows = []
    lg_rv = p.groupby("pitch_name")["delta_run_exp"].mean() * 100
    sw = p[p["swing"]]
    lg_wh = 100 * sw.assign(w=sw["description"].isin(dg.WHIFFS)).groupby("pitch_name")["w"].mean()
    for name, g in t.groupby("pitch_name"):
        if len(g) < 300:
            continue
        s = g[g["swing"]]
        rv = 100 * g["delta_run_exp"].mean()
        rows.append({"pitch": name, "pitches": len(g), "rv100": rv, "mlb_rv100": lg_rv[name],
                     "runs_vs_mlb": (rv - lg_rv[name]) * len(g) / 100,
                     "whiff": 100 * s["description"].isin(dg.WHIFFS).mean(), "mlb_whiff": lg_wh[name]})
    return sorted(rows, key=lambda r: -r["runs_vs_mlb"])


def tto(p: pd.DataFrame, team: str, min_bf: int = 200) -> list:
    sp = p[(p["fld_team"] == team) & (p["role"] == "SP") & p["is_pa"]]
    rows = []
    for (pid, name), g in sp.groupby(["pitcher", "player_name"]):
        if len(g) < min_bf:
            continue
        x = g.groupby("n_thruorder_pitcher")["xwoba_num"].mean()   # 1st, 2nd and 3rd time through
        last, first = name.split(", ", 1)
        rows.append({"pitcher": f"{first} {last}", "bf": len(g),
                     "first": x.get(1, np.nan), "second": x.get(2, np.nan), "third": x.get(3, np.nan)})
    return sorted(rows, key=lambda r: -r["bf"])


def team_report(team: str, D: dict) -> dict:
    p, res, off, allowed, lg = D["p"], D["res"], D["off"], D["allowed"], D["lg"]
    roles = role_tables(p)
    lg_roles = {r: dg.league(p[p["role"] == r]) for r in roles}
    slope = dg.runs_per_woba(off, res)
    o = off.loc[team]
    mean_rs, mean_ra = res["rs"].mean(), res["ra"].mean()

    kpis = {"wins": int(res.loc[team, "w"]), "losses": int(res.loc[team, "l"]),
            "runs_scored": int(res.loc[team, "rs"]), "runs_allowed": int(res.loc[team, "ra"]),
            "run_diff": int(res.loc[team, "run_diff"]), "rd_wins": round(res.loc[team, "rd_wins"]),
            "one_run_w": int(res.loc[team, "one_w"]), "one_run_l": int(res.loc[team, "one_l"]),
            "oaa": int(D["oaa"].loc[team, "outs_above_average"]),
            "oaa_rank": dg.rank(D["oaa"]["outs_above_average"], team)}

    offense = []
    for key, label, hib in (("ev", "Avg exit velocity (mph)", True), ("hard_hit", "Hard-hit % (95+ mph)", True),
                            ("barrel", "Barrel %", True), ("xwoba", "xwOBA", True), ("woba", "wOBA", True),
                            ("obp", "OBP", True), ("bb", "BB %", True), ("k", "K %", False),
                            ("chase", "Chase %", False)):
        offense.append({"metric": label, "team": o[key], "mlb": lg[key], "rank": dg.rank(off[key], team, hib)})

    halves = []
    for half, sub in (("First half", p[p["game_date"] < HALF_CUT]), ("Second half", p[p["game_date"] >= HALF_CUT])):
        b = dg.batting(sub[sub["bat_team"] == team], "bat_team").iloc[0]
        halves.append({"half": half, "woba": b["woba"], "xwoba": b["xwoba"], "gap": b["woba"] - b["xwoba"]})

    oaa = D["oaa"]
    prevention = [
        {"area": "Outs Above Average, team", "team": oaa.loc[team, "outs_above_average"],
         "rank": dg.rank(oaa["outs_above_average"], team)},
        {"area": "OAA vs. left-handed hitters", "team": oaa.loc[team, "outs_above_average_lhh"],
         "rank": dg.rank(oaa["outs_above_average_lhh"], team)},
        {"area": "OAA vs. right-handed hitters", "team": oaa.loc[team, "outs_above_average_rhh"],
         "rank": dg.rank(oaa["outs_above_average_rhh"], team)},
        {"area": "OAA on balls in front of the fielder", "team": oaa.loc[team, "outs_above_average_infront"],
         "rank": dg.rank(oaa["outs_above_average_infront"], team)},
    ]
    for r, lab in (("SP", "Starters"), ("RP", "Relievers")):
        t, l = roles[r], lg_roles[r]
        for key, name, hib in (("xwoba", "xwOBA allowed", False), ("bb", "walk rate", False),
                               ("k_bb", "K-BB %", True), ("fb_velo", "fastball velocity (mph)", True)):
            prevention.append({"area": f"{lab}: {name}", "team": t.loc[team, key], "mlb": l[key],
                               "rank": dg.rank(t[key], team, hib)})
    prevention.append({"area": "Catcher framing (runs)", "team": D["framing"][team],
                       "rank": dg.rank(D["framing"], team)})

    # Run bridge: runs vs an MLB-average team
    contact = slope * (o["xwoba"] - lg["xwoba"]) * o["pa"]
    vs_contact = slope * ((o["woba"] - o["xwoba"]) - (lg["woba"] - lg["xwoba"])) * o["pa"]
    br = D["baserunning"]
    baserun = br.get(team, 0.0) - br.mean()
    off_total = res.loc[team, "rs"] - mean_rs
    sp, rp = roles["SP"].loc[team], roles["RP"].loc[team]
    sp_runs = -slope * (sp["xwoba"] - lg_roles["SP"]["xwoba"]) * sp["pa"]
    rp_runs = -slope * (rp["xwoba"] - lg_roles["RP"]["xwoba"]) * rp["pa"]
    fielding = D["fielding"][team] - D["fielding"].mean()
    framing = D["framing"][team]
    prev_total = mean_ra - res.loc[team, "ra"]
    bridge = [
        {"step": "Contact quality (xwOBA)", "runs": contact, "group": "Offense"},
        {"step": "Results vs contact", "runs": vs_contact, "group": "Offense"},
        {"step": "Baserunning", "runs": baserun, "group": "Offense"},
        {"step": "Sequencing, other", "runs": off_total - contact - vs_contact - baserun, "group": "Offense"},
        {"step": "Offense total", "runs": off_total, "group": "Offense"},
        {"step": "Starting pitching (xwOBA)", "runs": sp_runs, "group": "Run prevention"},
        {"step": "Relief pitching (xwOBA)", "runs": rp_runs, "group": "Run prevention"},
        {"step": "Fielding (Savant)", "runs": fielding, "group": "Run prevention"},
        {"step": "Catcher framing", "runs": framing, "group": "Run prevention"},
        {"step": "Results allowed vs. contact, other",
         "runs": prev_total - sp_runs - rp_runs - fielding - framing, "group": "Run prevention"},
        {"step": "Run prevention total", "runs": prev_total, "group": "Run prevention"},
        {"step": "Run differential vs. MLB average", "runs": off_total + prev_total, "group": "Total"},
    ]
    return {"team": team, "name": dg.TEAM_NAMES[team], "runs_per_woba_point": slope, "kpis": kpis,
            "offense": offense, "halves": halves, "prevention": prevention, "bridge": bridge,
            "pitches": pitch_types(p, team), "tto": tto(p, team)}


def to_jsonable(x):
    if isinstance(x, dict):
        return {k: to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if np.isnan(x) else round(float(x), 4)
    if isinstance(x, np.integer):
        return int(x)
    return x


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    D = load()
    teams = sorted(D["res"].index) if sys.argv[1] == "ALL" else [sys.argv[1]]
    for t in teams:
        r = to_jsonable(team_report(t, D))
        (OUT / f"{t}_diagnosis.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(t, r["kpis"]["wins"], "-", r["kpis"]["losses"])
