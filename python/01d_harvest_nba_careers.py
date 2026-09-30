"""Fill the one documented hole in the second performance source.

stats.nba.com's LeagueLeaders table omits players who changed teams
mid-season before 1986-87 (output/source_mismatches.csv kind
'unmatched_known_gap'). For each such player, fetch PlayerCareerStats (one
row per team stint) so 03_reconcile_sources.py can cross-check those
seasons too.

The nba_id comes from the crosswalk when the player matched in any other
season; otherwise from CommonAllPlayers by normalized name, accepted only
when exactly one player with that name was active that season.
Output: data/raw/nba_api/career_<nba_id>.csv
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import polars as pl
from nba_api.stats.library import http

http.STATS_HEADERS["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
from nba_api.stats.endpoints import commonallplayers, playercareerstats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "nba_api"


def main() -> None:
    # Every unmatched row, not only the known gap: a few players (Negele
    # Knight 1990-91 to 1994-95, Mark Jones 1983-84) are missing from the
    # NBA's league tables although they have NBA ids.
    gap = pl.read_csv(ROOT / "output" / "source_mismatches.csv").filter(
        pl.col("kind").is_in(["unmatched_known_gap", "unmatched"]))
    xw = pl.read_csv(ROOT / "data" / "crosswalk.csv")
    ids = gap.join(xw, on="bbref_id", how="left")
    need = ids.filter(pl.col("nba_id").is_null())

    allp_path = OUT / "common_all_players.csv"
    if not allp_path.exists():
        allp = pl.from_pandas(commonallplayers.CommonAllPlayers(
            is_only_current_season=0, timeout=90).get_data_frames()[0])
        allp.write_csv(allp_path)
    allp = pl.read_csv(allp_path, infer_schema_length=None).with_columns(
        pl.col("DISPLAY_FIRST_LAST").map_elements(norm, return_dtype=pl.String).alias("key"),
        pl.col("FROM_YEAR").cast(pl.Int64, strict=False), pl.col("TO_YEAR").cast(pl.Int64, strict=False))

    found = []
    for r in need.iter_rows(named=True):
        # FROM_YEAR/TO_YEAR are season start years (1977 = 1977-78).
        c = allp.filter((pl.col("key") == norm(r["name"]))
                        & (pl.col("FROM_YEAR") <= r["season"] - 1) & (pl.col("TO_YEAR") >= r["season"] - 1))
        if c.height == 1:
            found.append({"bbref_id": r["bbref_id"], "nba_id": c["PERSON_ID"][0]})
        else:
            print(f"no unique id: {r['season']} {r['name']} ({c.height} candidates)")
    lookup = pl.DataFrame(found, schema={"bbref_id": pl.String, "nba_id": pl.Int64}).unique()
    lookup.write_csv(ROOT / "data" / "crosswalk_gap_lookup.csv")

    todo = sorted(set(ids["nba_id"].drop_nulls().to_list()) | set(lookup["nba_id"].to_list()))
    print(f"{gap.height} gap seasons, {len(todo)} players to fetch")
    for pid in todo:
        dest = OUT / f"career_{pid}.csv"
        if dest.exists():
            continue
        for attempt in range(4):
            try:
                df = pl.from_pandas(playercareerstats.PlayerCareerStats(
                    player_id=pid, per_mode36="Totals", timeout=90).get_data_frames()[0])
                df.write_csv(dest)
                break
            except Exception as e:
                print(f"ERR {pid} attempt {attempt + 1}: {type(e).__name__}", flush=True)
                time.sleep(20 * (attempt + 1))
        time.sleep(1.5)
    print("done")


if __name__ == "__main__":
    main()
