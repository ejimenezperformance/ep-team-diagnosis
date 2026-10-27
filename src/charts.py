"""EP-branded charts. Labels carry the information; color is never the only cue."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import backtest as bt

ROOT = Path(__file__).resolve().parents[1]
OUT, FIG = ROOT / "outputs", ROOT / "figures"
NAVY, GOLD, GRAY, BG, INK, MUTED = "#0B1B33", "#D4A53A", "#8A94A3", "#F5F3EC", "#0B1B33", "#4A5363"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED})
CREDIT = "Data: Baseball Savant, 716,792 pitches (2026 regular season). Analysis: Emerson Jimenez, Emerson Performance (EP)"
SIX = {"NYM", "MIA", "KC", "BOS", "HOU", "LAA"}


def process_vs_actual():
    s = pd.read_csv(OUT / "league_summary.csv")
    fig, ax = plt.subplots(figsize=(10, 8.2), facecolor=BG)
    ax.set_facecolor(BG)
    lim = (56, 108)
    ax.plot(lim, lim, color=GRAY, lw=1.2, ls="--", zorder=1)
    ax.text(100, 102.5, "record = process", color=MUTED, fontsize=9, ha="center", rotation=38)
    big = (s["wins"] - s["process_wins"]).abs() >= 9
    for _, r in s.iterrows():
        six = r.team in SIX
        ax.scatter(r.process_wins, r.wins, s=95 if six else 55, color=NAVY if six else GRAY,
                   edgecolor=BG, linewidth=1.5, zorder=3)
        if six or big[_]:
            dx, ha = (1.0, "left") if r.team != "DET" else (-1.0, "right")
            ax.text(r.process_wins + dx, r.wins, f"{r.team} {int(r.wins)}-{int(r.losses)}", va="center",
                    ha=ha, fontsize=9.5, color=INK, fontweight="bold" if six else "normal")
    ax.set_xlim(*lim); ax.set_ylim(*lim)
    ax.set_xlabel("Wins implied by process (contact quality, defense, framing, baserunning)")
    ax.set_ylabel("Actual 2026 wins")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(color="#DAD6CB", lw=0.7); ax.set_axisbelow(True)
    ax.text(58, 104, "Above the line: won more than\ntheir process (results ran hot)", fontsize=9.5, color=MUTED, va="top")
    ax.text(106, 59, "Below the line: won less than\ntheir process (results ran cold)", fontsize=9.5, color=MUTED, ha="right")
    ax.set_title("2026: which records were real?", loc="left", color=INK, fontsize=15, fontweight="bold", pad=26)
    ax.text(0, 1.015, "Bold navy = the six teams with a full EP dashboard. Process wins = 81 + process runs / 10.5.",
            transform=ax.transAxes, color=MUTED, fontsize=9.5)
    fig.text(0.01, 0.01, CREDIT, color=MUTED, fontsize=8.3)
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    fig.savefig(FIG / "fig1_process_vs_actual.png", dpi=180, facecolor=BG)


def backtest_chart():
    d = bt.season_pairs("bat")
    b = json.loads((OUT / "backtest.json").read_text(encoding="utf-8"))["batting_gap_year_to_year"]
    fig, ax = plt.subplots(figsize=(9, 6.6), facecolor=BG)
    ax.set_facecolor(BG)
    ax.scatter(1000 * d["gap"], 1000 * d["gap_next"], s=40, color=NAVY, alpha=0.75, edgecolor=BG, lw=1)
    m, c = np.polyfit(1000 * d["gap"], 1000 * d["gap_next"], 1)
    xs = np.array([-30, 30])
    ax.plot(xs, m * xs + c, color=GOLD, lw=2.5)
    ax.text(26, m * 26 + c + 2.5, f"r = {b['r']:.2f}\n(95% CI {b['ci'][0]:.2f}-{b['ci'][1]:.2f})",
            color=INK, fontsize=10.5, fontweight="bold", ha="right")
    ax.axhline(0, color=GRAY, lw=1); ax.axvline(0, color=GRAY, lw=1)
    ax.set_xlabel("Team batting wOBA - xwOBA, season t (points)")
    ax.set_ylabel("Same team, season t+1 (points)")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Results vs. contact: only part of it carries over", loc="left", color=INK,
                 fontsize=14, fontweight="bold", pad=26)
    ax.text(0, 1.015, f"{b['pairs']} team-season pairs, 2021-2026. A slope well below 1 means most of the gap regresses.",
            transform=ax.transAxes, color=MUTED, fontsize=9.5)
    fig.text(0.01, 0.01, "Data: Baseball Savant team expected stats. Analysis: Emerson Jimenez, EP",
             color=MUTED, fontsize=8.3)
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    fig.savefig(FIG / "fig2_backtest.png", dpi=180, facecolor=BG)


def bridge(team="NYM"):
    d = json.loads((OUT / f"{team}_diagnosis.json").read_text(encoding="utf-8"))
    steps = d["bridge"][::-1]
    fig, ax = plt.subplots(figsize=(10, 7), facecolor=BG)
    ax.set_facecolor(BG)
    for i, s in enumerate(steps):
        total = s["step"].endswith("total") or s["step"].startswith("Run differential")
        col = GRAY if total else (GOLD if s["runs"] >= 0 else NAVY)
        ax.barh(i, s["runs"], color=col, height=0.66, edgecolor=BG)
        ax.text(s["runs"] + (1.5 if s["runs"] >= 0 else -1.5), i, f"{s['runs']:+.1f}", va="center",
                ha="left" if s["runs"] >= 0 else "right", fontsize=10, color=INK,
                fontweight="bold" if total else "normal")
    ax.set_yticks(range(len(steps)))
    ax.set_yticklabels([("   " if not (s["step"].endswith("total") or s["step"].startswith("Run diff")) else "")
                        + s["step"] for s in steps], fontsize=10)
    for t, s in zip(ax.get_yticklabels(), steps):
        if s["step"].endswith("total") or s["step"].startswith("Run diff"):
            t.set_fontweight("bold")
    ax.axvline(0, color=MUTED, lw=1)
    lo = min(s["runs"] for s in steps); hi = max(s["runs"] for s in steps)
    ax.set_xlim(lo - 14, hi + 14)
    ax.set_xlabel("Runs vs. an MLB-average team (gold = gained, navy = lost, gray = total)")
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    k = d["kpis"]
    ax.set_title(f"{d['name']} 2026 ({k['wins']}-{k['losses']}): where the runs went", loc="left",
                 color=INK, fontsize=14, fontweight="bold")
    fig.text(0.01, 0.01, CREDIT, color=MUTED, fontsize=8.3)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / f"fig3_bridge_{team}.png", dpi=180, facecolor=BG)


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    process_vs_actual(); backtest_chart(); bridge("NYM")
    print("saved")
