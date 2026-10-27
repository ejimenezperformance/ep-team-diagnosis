"""Download the public Statcast data behind the team diagnosis (regular season).

  pitches_2026.csv     every 2026 regular-season pitch (needed columns only),
                       pulled in 4-day windows (Savant caps a query at 25,000 rows)
  team_bat_<y>.csv     team batting wOBA / xwOBA by season and half, 2021-2026
  team_pit_<y>.csv     team pitching wOBA / xwOBA allowed by season and half
  oaa_team_2026.csv    Outs Above Average by team (plus splits by batter side)
  framing_catchers_2026  catcher framing runs by catcher
  fielding_players / baserunning_players 2026: player run values (summed to team)
  sprint_2026.csv      sprint speed by player

Usage: python src/pull_data.py
"""
import io
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
SAVANT = "https://baseballsavant.mlb.com"
COLS = ["game_pk", "game_date", "home_team", "away_team", "inning", "inning_topbot",
        "at_bat_number", "pitch_number", "batter", "pitcher", "player_name", "stand", "p_throws",
        "pitch_type", "pitch_name", "release_speed", "zone", "description", "type", "events",
        "bb_type", "launch_speed", "launch_angle", "launch_speed_angle", "hc_x", "hc_y",
        "estimated_woba_using_speedangle", "woba_value", "woba_denom", "delta_run_exp",
        "delta_pitcher_run_exp", "bat_speed", "n_thruorder_pitcher", "post_home_score",
        "post_away_score", "home_score", "away_score", "fielder_2", "balls", "strikes",
        "outs_when_up", "on_1b", "on_2b", "on_3b"]
SEASON = {2021: ("04-01", "10-03"), 2022: ("04-07", "10-05"), 2023: ("03-30", "10-01"),
          2024: ("03-20", "09-30"), 2025: ("03-18", "09-28"), 2026: ("03-25", "09-27")}
HALF_SPLIT = "07-15"   # first half = games before Jul 15 (about the All-Star break)


def get(url: str, params: dict) -> pd.DataFrame:
    for attempt in range(6):
        try:
            r = requests.get(url, params=params, timeout=300)
            if r.ok:
                text = r.content.decode("utf-8-sig").strip()
                return pd.read_csv(io.StringIO(text), low_memory=False) if text else pd.DataFrame()
        except requests.RequestException:
            pass
        time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"failed: {url} {params}")


def pitches(year: int = 2026) -> None:
    out = RAW / f"pitches_{year}.csv"
    if out.exists():
        return
    start, end = (date.fromisoformat(f"{year}-{s}") for s in SEASON[year])
    parts, d = [], start
    while d <= end:
        e = min(d + timedelta(days=3), end)
        df = get(f"{SAVANT}/statcast_search/csv", {
            "all": "true", "hfGT": "R|", "hfSea": f"{year}|", "player_type": "pitcher",
            "game_date_gt": d.isoformat(), "game_date_lt": e.isoformat(),
            "min_pitches": 0, "min_results": 0, "type": "details"})
        if len(df) >= 24_999:
            raise RuntimeError(f"row cap hit {d}..{e}: use smaller windows")
        if not df.empty:
            parts.append(df[COLS])
        print(year, d, e, len(df), flush=True)
        d = e + timedelta(days=1)
    pd.concat(parts).to_csv(out, index=False, encoding="utf-8")


def team_by_half(year: int, side: str) -> None:
    out = RAW / f"team_{side}_{year}.csv"
    if out.exists():
        return
    s, e = SEASON[year]
    rows = []
    for half, (a, b) in {"full": (s, e), "first": (s, HALF_SPLIT), "second": (HALF_SPLIT, e)}.items():
        if half == "second":
            a = (date.fromisoformat(f"{year}-{HALF_SPLIT}") + timedelta(days=1)).isoformat()[5:]
        df = get(f"{SAVANT}/statcast_search/csv", {
            "hfGT": "R|", "hfSea": f"{year}|", "player_type": "batter" if side == "bat" else "pitcher",
            "group_by": "team", "game_date_gt": f"{year}-{a}", "game_date_lt": f"{year}-{b}",
            "min_pitches": 0, "min_results": 0, "sort_col": "pitches", "sort_order": "desc"})
        df = df[["player_name", "pa", "woba", "xwoba"]].rename(columns={"player_name": "team"})
        df["season"], df["half"] = year, half
        rows.append(df)
    pd.concat(rows).to_csv(out, index=False, encoding="utf-8")


def leaderboards(year: int = 2026) -> None:
    jobs = {
        "oaa_team": (f"{SAVANT}/leaderboard/outs_above_average",
                     {"type": "Fielding_Team", "startYear": year, "endYear": year, "split": "yes",
                      "team": "", "range": "year", "min": "q", "pos": "", "roles": "", "viz": "hide",
                      "csv": "true"}),
        "sprint": (f"{SAVANT}/leaderboard/sprint_speed",
                   {"year": year, "position": "", "team": "", "min": 10, "csv": "true"}),
    }
    for name, (url, params) in jobs.items():
        out = RAW / f"{name}_{year}.csv"
        if not out.exists():
            get(url, params).to_csv(out, index=False, encoding="utf-8")
    # Fielding runs prevented and baserunning runs, by player (summed to team in report.py)
    extra = {
        "fielding_players": (f"{SAVANT}/leaderboard/outs_above_average",
                             {"type": "Fielder", "startYear": year, "endYear": year, "split": "no",
                              "team": "", "range": "year", "min": 1, "pos": "", "roles": "",
                              "viz": "hide", "csv": "true"}),
        "baserunning_players": (f"{SAVANT}/leaderboard/baserunning-run-value",
                                {"game_type": "Regular", "season_start": year, "season_end": year,
                                 "split": "no", "n": 1, "team": "", "type": "Player",
                                 "with_team_only": 1, "csv": "true"}),
    }
    for name, (url, params) in extra.items():
        out = RAW / f"{name}_{year}.csv"
        if not out.exists():
            get(url, params).to_csv(out, index=False, encoding="utf-8")
    # Catcher framing runs by catcher (report.py splits each catcher's runs across
    # teams by the share of pitches he caught for each, which handles trades)
    out = RAW / f"framing_catchers_{year}.csv"
    if not out.exists():
        get(f"{SAVANT}/leaderboard/catcher-framing",
            {"type": "catcher", "seasonStart": year, "seasonEnd": year, "team": "", "min": 1,
             "csv": "true"}).to_csv(out, index=False, encoding="utf-8")

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    leaderboards()
    for y in range(2021, 2027):
        team_by_half(y, "bat")
        team_by_half(y, "pit")
        print("team", y, "done", flush=True)
    pitches(2026)
