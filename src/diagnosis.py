"""Team diagnosis from public 2026 Statcast pitch-level data.

Everything here is computed from data/raw; no number is typed in by hand.
Definitions follow the method note published with the EP team dashboards.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SWINGS = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
          "foul_bunt", "missed_bunt", "bunt_foul_tip"}
WHIFFS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}   # foul tips = contact
HITS = {"single", "double", "triple", "home_run"}
OBP_ON = HITS | {"walk", "intent_walk", "hit_by_pitch"}
OBP_DEN_EXTRA = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_fly_double_play"}
NOT_AB = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt", "sac_fly_double_play",
          "sac_bunt_double_play", "catcher_interf", "truncated_pa"}
FASTBALLS = {"FF", "SI"}   # four-seam and sinker (Statcast fastballs; cutter excluded)
# Weights used by Savant's pitch-level woba_value column
WOBA_WEIGHTS = {"walk": 0.7, "hit_by_pitch": 0.7, "single": 0.9, "double": 1.25,
                "triple": 1.6, "home_run": 2.0}
TEAM_NAMES = {"AZ": "D-backs", "ATH": "Athletics", "ATL": "Braves", "BAL": "Orioles",
              "BOS": "Red Sox", "CHC": "Cubs", "CWS": "White Sox", "CIN": "Reds", "CLE": "Guardians",
              "COL": "Rockies", "DET": "Tigers", "HOU": "Astros", "KC": "Royals", "LAA": "Angels",
              "LAD": "Dodgers", "MIA": "Marlins", "MIL": "Brewers", "MIN": "Twins", "NYM": "Mets",
              "NYY": "Yankees", "PHI": "Phillies", "PIT": "Pirates", "SD": "Padres", "SF": "Giants",
              "SEA": "Mariners", "STL": "Cardinals", "TB": "Rays", "TEX": "Rangers", "TOR": "Blue Jays",
              "WSH": "Nationals"}


PITCH_NAMES = {"4-Seam Fastball": "Four-seam", "Split-Finger": "Splitter", "Knuckle Curve": "Knuckle curve"}


def prepare(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["pitch_name"] = p["pitch_name"].replace(PITCH_NAMES)
    p["game_date"] = pd.to_datetime(p["game_date"])
    top = p["inning_topbot"] == "Top"
    p["bat_team"] = np.where(top, p["away_team"], p["home_team"])
    p["fld_team"] = np.where(top, p["home_team"], p["away_team"])
    # PA for wOBA: Savant's denominator, minus catcher's interference
    p["is_pa"] = (p["woba_denom"].fillna(0) == 1) & (p["events"] != "catcher_interf")
    # balls in play with a tracked exit velocity (the denominator for EV, hard-hit and barrel rates)
    p["is_bbe"] = (p["type"] == "X") & p["launch_speed"].notna()
    # Event values: reaching on an error or a fielder's choice counts as an out,
    # as in the official wOBA (the pitch-level woba_value column credits them as hits)
    p["woba_ev"] = p["events"].map(WOBA_WEIGHTS).fillna(0.0)
    # xwOBA numerator: speed/angle estimate on balls in play, event value otherwise
    p["xwoba_num"] = np.where(p["is_bbe"], p["estimated_woba_using_speedangle"], p["woba_ev"])
    p["swing"] = p["description"].isin(SWINGS)
    p["out_zone"] = p["zone"].isin([11, 12, 13, 14])
    # starter = the fielding team's first pitcher in each game
    first = (p.sort_values(["game_pk", "at_bat_number", "pitch_number"])
               .groupby(["game_pk", "fld_team"])["pitcher"].first().rename("starter"))
    p = p.join(first, on=["game_pk", "fld_team"])
    p["role"] = np.where(p["pitcher"] == p["starter"], "SP", "RP")
    return p


def results(p: pd.DataFrame) -> pd.DataFrame:
    """Final score per game, then RS, RA, W, L, one-run games per team."""
    g = p.groupby("game_pk").agg(home=("home_team", "first"), away=("away_team", "first"),
                                 hs=("post_home_score", "max"), as_=("post_away_score", "max"))
    rows = []
    for _, r in g.iterrows():
        for team, rs, ra in ((r.home, r.hs, r.as_), (r.away, r.as_, r.hs)):
            rows.append({"team": team, "rs": rs, "ra": ra, "w": int(rs > ra), "l": int(rs < ra),
                         "one_w": int(rs - ra == 1), "one_l": int(ra - rs == 1)})
    t = pd.DataFrame(rows).groupby("team").sum()
    t["run_diff"] = t["rs"] - t["ra"]
    # Wins implied by run differential: 81 + RD / 10.5 runs per win
    t["rd_wins"] = 81 + t["run_diff"] / 10.5
    return t


def batting(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Rate stats grouped by `key` (bat_team for offense, fld_team for pitching allowed)."""
    pa = df[df["is_pa"]]
    bbe = df[df["is_bbe"]]
    ev = df["events"]
    out = pd.DataFrame({
        "pa": pa.groupby(key).size(),
        "woba": pa.groupby(key)["woba_ev"].mean(),
        "xwoba": pa.groupby(key)["xwoba_num"].mean(),
        "ev": bbe.groupby(key)["launch_speed"].mean(),
        "hard_hit": 100 * bbe.assign(h=bbe["launch_speed"] >= 95).groupby(key)["h"].mean(),
        "barrel": 100 * bbe.assign(b=bbe["launch_speed_angle"] == 6).groupby(key)["b"].mean(),
    })
    # BB% and K% use every plate appearance (including intentional walks and bunts)
    allpa = df[df["events"].notna() & (df["events"] != "truncated_pa")]
    out["bb"] = 100 * allpa.assign(b=allpa["events"].isin(["walk", "intent_walk"])).groupby(key)["b"].mean()
    out["k"] = 100 * allpa.assign(k=allpa["events"].isin(["strikeout", "strikeout_double_play"])).groupby(key)["k"].mean()
    evs = df[ev.notna()]
    ab = evs[~evs["events"].isin(NOT_AB)].groupby(key).size()
    on = evs[evs["events"].isin(OBP_ON)].groupby(key).size()
    extra = evs[evs["events"].isin(OBP_DEN_EXTRA)].groupby(key).size()
    out["obp"] = on / (ab + extra)
    oz = df[df["out_zone"]]
    out["chase"] = 100 * oz.groupby(key)["swing"].mean()
    sw = df[df["swing"]]
    out["whiff"] = 100 * sw.assign(w=sw["description"].isin(WHIFFS)).groupby(key)["w"].mean()
    out["k_bb"] = out["k"] - out["bb"]
    fb = df[df["pitch_type"].isin(FASTBALLS)]
    out["fb_velo"] = fb.groupby(key)["release_speed"].mean()
    return out


def league(df: pd.DataFrame) -> pd.Series:
    """League-level version of batting() (one row, all PA pooled)."""
    return batting(df.assign(_all="MLB"), "_all").iloc[0]


def runs_per_woba(off: pd.DataFrame, res: pd.DataFrame) -> float:
    """Slope of runs per PA on wOBA across 30 teams."""
    x = off["woba"].reindex(res.index)
    y = (res["rs"] / off["pa"]).reindex(res.index)
    return float(np.polyfit(x, y, 1)[0])


def rank(series: pd.Series, team: str, higher_is_better: bool = True) -> int:
    return int(series.rank(ascending=not higher_is_better, method="min")[team])
