"""Harvest stats.nba.com tables (via nba_api) as the second, independent
performance source for the contract-year study.

- LeagueLeaders, scope "S", Totals: one row per player-season back to
  1973-74 (LeagueDashPlayerStats returns zero rows before 1996-97, checked
  September 29, 2026).
- LeagueDashPlayerStats, Totals: 1996-97 onward, the fuller table where it
  exists.
- DraftHistory: every draft, used for rookie-scale contract lengths and as a
  cross-check on Basketball-Reference draft data.

nba_api returns pandas; frames are converted to polars at the boundary and
written as CSV under data/raw/nba_api/ (gitignored, resumable).
"""

from __future__ import annotations

import time
from pathlib import Path

import polars as pl
from nba_api.stats.library import http

# nba_api's shipped browser UA gets hung by Akamai; a generic UA does not
# (family note, lineup-valuation-study/python/05_build_stints.py).
http.STATS_HEADERS["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

from nba_api.stats.endpoints import drafthistory, leaguedashplayerstats, leagueleaders  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "nba_api"
DELAY = 1.5


def season_str(end_year: int) -> str:
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def save(name: str, fetch) -> None:
    dest = OUT / name
    if dest.exists():
        return
    for attempt in range(4):
        try:
            df = pl.from_pandas(fetch().get_data_frames()[0])
            break
        except Exception as e:  # network errors surface under several types
            print(f"ERR {name} attempt {attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(20 * (attempt + 1))
    else:
        print(f"FAILED {name}", flush=True)
        return
    df.write_csv(dest)
    print(f"OK  {name} rows={df.height}", flush=True)
    time.sleep(DELAY)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    save("draft_history.csv", lambda: drafthistory.DraftHistory(timeout=90))
    for y in range(1974, 2027):
        s = season_str(y)
        save(f"leaders_{y}.csv", lambda s=s: leagueleaders.LeagueLeaders(
            season=s, per_mode48="Totals", scope="S", season_type_all_star="Regular Season",
            stat_category_abbreviation="PTS", timeout=90))
        if y >= 1997:
            save(f"dash_{y}.csv", lambda s=s: leaguedashplayerstats.LeagueDashPlayerStats(
                season=s, per_mode_detailed="Totals", season_type_all_star="Regular Season", timeout=90))


if __name__ == "__main__":
    main()
