"""Compare every recomputed number with the value published on the six EP team
dashboards (validation/<team>.json, extracted from the live pages).

A value MATCHES when it agrees to the precision it was published at
(for example .321 vs 0.3205 matches; 41.7 vs 41.66 matches).
Output: validation/validation_report.csv and a summary printed to screen.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VAL, OUT = ROOT / "validation", ROOT / "outputs"
TEAMS = {"mets": "NYM", "marlins": "MIA", "royals": "KC", "redsox": "BOS", "astros": "HOU", "angels": "LAA"}
KPI_KEYS = ["wins", "losses", "runs_scored", "runs_allowed", "run_diff", "rd_wins",
            "one_run_w", "one_run_l", "oaa", "oaa_rank"]


def decimals(v) -> int:
    s = repr(float(v))
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


def close(pub, new, tol_units=1.0) -> bool:
    """Equal at the published precision, allowing one unit in the last place
    (the published value may have been rounded from a different intermediate)."""
    if pub is None or new is None:
        return False
    d = max(decimals(pub), 0)
    unit = 10 ** (-d) if d > 0 else 1
    return abs(float(pub) - float(new)) <= tol_units * unit + 1e-9


def rows_for(team_key: str, abbr: str) -> list:
    pub = json.loads((VAL / f"{team_key}.json").read_text(encoding="utf-8"))
    new = json.loads((OUT / f"{abbr}_diagnosis.json").read_text(encoding="utf-8"))
    out = []

    def add(section, item, p, n, tol=1.0):
        out.append({"team": abbr, "section": section, "item": item, "published": p,
                    "recomputed": None if n is None else round(n, 4), "match": close(p, n, tol)})

    pk = {r["metric"]: r["value"] for r in pub["kpis"]}
    for k in KPI_KEYS:
        if k in pk:
            add("kpis", k, pk[k], new["kpis"][k])
    tcol = "mets" if "mets" in pub["offense"][0] else "team"
    no = {r["metric"]: r for r in new["offense"]}
    for r in pub["offense"]:
        n = no.get(r["metric"])
        if n:
            add("offense", r["metric"], r[tcol], n["team"])
            add("offense", r["metric"] + " (MLB)", r["mlb"], n["mlb"])
            add("offense", r["metric"] + " (rank)", r["rank"], n["rank"], tol=0)
    nh = {r["half"]: r for r in new["halves"]}
    for r in pub["halves"]:
        for k in ("woba", "xwoba"):
            add("halves", f"{r['half']} {k}", r[k], nh[r["half"]][k])
    tcol = "mets" if "mets" in pub["prevention"][0] else "team"
    npv = {r["area"]: r for r in new["prevention"]}
    for r in pub["prevention"]:
        n = npv.get(r["area"])
        if n:
            add("prevention", r["area"], r[tcol], n["team"])
            add("prevention", r["area"] + " (rank)", r["rank"], n["rank"], tol=0)
        else:
            out.append({"team": abbr, "section": "prevention", "item": r["area"], "published": r[tcol],
                        "recomputed": None, "match": None})
    nb = {r["step"].replace("below", "vs").replace("above", "vs"): r for r in new["bridge"]}
    for r in pub["bridge"]:
        key = r["step"].replace("Results below contact", "Results vs contact").replace(
            "Results above contact", "Results vs contact").replace("Run differential", "Run differential vs. MLB average") \
            if r["step"] in ("Results below contact", "Results above contact", "Run differential") else r["step"]
        n = nb.get(key)
        add("bridge", r["step"], r["runs"], None if n is None else n["runs"], tol=1.5)
    npt = {r["pitch"]: r for r in new["pitches"]}
    for r in pub.get("pitches", []):
        n = npt.get(r["pitch"]) or npt.get({"Four-seam": "4-Seam Fastball"}.get(r["pitch"], r["pitch"]))
        for k in ("rv100", "runs_vs_mlb", "whiff"):
            add("pitches", f"{r['pitch']} {k}", r[k], None if n is None else n[k], tol=1.5)
    nt = {r["pitcher"]: r for r in new["tto"]}
    for r in pub.get("tto", []):
        n = nt.get(r["pitcher"])
        for k in ("first", "second", "third"):
            add("tto", f"{r['pitcher']} {k}", r[k], None if n is None else n[k])
    return out


if __name__ == "__main__":
    rows = sum((rows_for(k, a) for k, a in TEAMS.items()), [])
    v = pd.DataFrame(rows)
    v.to_csv(VAL / "validation_report.csv", index=False, encoding="utf-8")
    s = v.dropna(subset=["match"]).groupby("section")["match"].agg(["sum", "size"])
    s["pct"] = (100 * s["sum"] / s["size"]).round(1)
    print(s)
    print("TOTAL", int(v["match"].sum()), "/", int(v["match"].notna().sum()))
    pd.set_option("display.width", 200)
    print(v[v["match"] == False].to_string(index=False))  # noqa: E712
