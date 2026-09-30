"""Cross-validate the two performance sources and build the player crosswalk.

Matching, per season, one-to-one:
  1. name pass:  (season, normalized name), after mapping the audited
                 nickname / legal-name pairs in data/manual/aliases.csv.
                 Same-name players (two Eddie Johnsons in 1985-86) are
                 assigned greedily by closest (games, points), so each row
                 on either side is used at most once.
  2. stats pass: leftover rows with identical (season, games, points) and a
                 similar name, accepted only when the candidate is unique.

Every matched row is graded. Identity (is this the same player-season?)
rests on games and points; minutes are a separate measurement question,
because for 1996-97 through 2004-05 a minority of players (the
per-season count is in the output) have stats.nba.com minutes that differ
from Basketball-Reference's in both LeagueDash and LeagueLeaders
(Darvin Ham 2004-05: 256.55 vs 275). The per-season median gap stays near
zero, so this is not a league-wide offset.

  exact        games and points equal, minutes within max(1, 2%)
  close        games within 1 and points within max(5, 1%), minutes within
               max(1, 2%); a few 1996-97 point totals differ by 1 to 4,
               scorer corrections applied by one source only
  minutes_gap  games and points within the close bounds, minutes outside
  gross        games or points outside the close bounds: a wrong match or
               a real data error

Gate (non-zero exit): no gross rows, and from 1977-78 on every season has
match rate >= 0.97 once the documented LeagueLeaders gap (traded players
absent before 1986-87) is excluded from the denominator.

Writes output/source_reconcile_by_season.csv, output/source_mismatches.csv,
and data/crosswalk.csv.
"""

from __future__ import annotations

import sys
from difflib import SequenceMatcher
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE_MATCH = 0.97
# LeagueLeaders omits players who changed teams mid-season before this
# season (checked: Kevin Porter and Jim Price 1977-78 are absent entirely).
LEADERS_TRADED_GAP_BEFORE = 1987


def greedy_pairs(cand: pl.DataFrame) -> pl.DataFrame:
    """One-to-one assignment: take candidate pairs in ascending distance,
    keeping a pair only if neither side is already used."""
    used_b: set[tuple[int, str]] = set()
    used_n: set[tuple[int, int]] = set()
    keep = []
    for r in cand.sort("dist").iter_rows(named=True):
        kb, kn = (r["season"], r["bbref_id"]), (r["season"], r["nba_id"])
        if kb in used_b or kn in used_n:
            continue
        used_b.add(kb)
        used_n.add(kn)
        keep.append(r)
    return pl.DataFrame(keep, schema=cand.schema)


def grade(df: pl.DataFrame) -> pl.DataFrame:
    dg = (pl.col("games") - pl.col("games_n")).abs()
    dp = (pl.col("pts") - pl.col("pts_n")).abs()
    dm = (pl.col("mp") - pl.col("mp_n")).abs()
    same = (dg <= 1) & (dp <= pl.max_horizontal(5, 0.01 * pl.col("pts")))
    mp_ok = dm <= pl.max_horizontal(1, 0.02 * pl.col("mp"))
    return df.with_columns(
        pl.when(~same).then(pl.lit("gross"))
        .when(~mp_ok).then(pl.lit("minutes_gap"))
        .when((dg == 0) & (dp == 0)).then(pl.lit("exact"))
        .otherwise(pl.lit("close")).alias("grade"),
        ((pl.col("mp_n") - pl.col("mp")) / pl.col("mp")).alias("mp_rel_diff"))


def main() -> None:
    b = pl.read_csv(ROOT / "data" / "bbref_player_seasons.csv", infer_schema_length=None)
    n = pl.read_csv(ROOT / "data" / "nba_player_seasons.csv", infer_schema_length=None)
    alias = pl.read_csv(ROOT / "data" / "manual" / "aliases.csv")
    to_bbref = {norm(a): norm(bn) for bn, a in zip(alias["bbref_name"], alias["nba_name"])}

    b = b.with_columns(pl.col("name").map_elements(norm, return_dtype=pl.String).alias("key"))
    n = n.with_columns(pl.col("name").map_elements(
        lambda s: to_bbref.get(norm(s), norm(s)), return_dtype=pl.String).alias("key"))
    bx = b.select("season", "key", "bbref_id", "name", "n_teams", "games", "mp", "pts")
    nx = n.select("season", "key", "nba_id", pl.col("name").alias("nba_name"),
                  pl.col("games").alias("games_n"), pl.col("mp").alias("mp_n"),
                  pl.col("pts").alias("pts_n"), "nba_source")

    dist = ((pl.col("games") - pl.col("games_n")).abs()
            + (pl.col("pts") - pl.col("pts_n")).abs() / 10).alias("dist")
    p1 = greedy_pairs(bx.join(nx, on=["season", "key"]).with_columns(dist)) \
        .with_columns(pl.lit("name").alias("match_pass"))

    lb = bx.join(p1.select("season", "bbref_id"), on=["season", "bbref_id"], how="anti")
    ln = nx.join(p1.select("season", "nba_id"), on=["season", "nba_id"], how="anti")
    c2 = lb.join(ln.drop("key").rename({"games_n": "games", "pts_n": "pts"}),
                 on=["season", "games", "pts"]).with_columns(
        pl.col("games").alias("games_n"), pl.col("pts").alias("pts_n"),
        pl.struct("name", "nba_name").map_elements(
            lambda s: SequenceMatcher(None, norm(s["name"]), norm(s["nba_name"])).ratio(),
            return_dtype=pl.Float64).alias("sim"))
    c2 = c2.filter(pl.col("sim") >= 0.6)
    c2 = c2.filter((pl.len().over(["season", "bbref_id"]) == 1) & (pl.len().over(["season", "nba_id"]) == 1))
    p2 = c2.with_columns(pl.lit(0.0).alias("dist"), pl.lit("stats").alias("match_pass")) \
        .select(p1.columns)

    matched = grade(pl.concat([p1, p2]))
    unmatched = bx.join(matched.select("season", "bbref_id"), on=["season", "bbref_id"], how="anti") \
        .with_columns(((pl.col("season") < LEADERS_TRADED_GAP_BEFORE) & (pl.col("n_teams") > 1))
                      .alias("known_gap"))

    by = (bx.group_by("season").agg(pl.len().alias("bbref_rows"))
          .join(matched.group_by("season").agg(
              pl.len().alias("matched"),
              (pl.col("grade") == "exact").sum().alias("exact"),
              (pl.col("grade") == "close").sum().alias("close"),
              (pl.col("grade") == "minutes_gap").sum().alias("minutes_gap"),
              pl.col("mp_rel_diff").median().alias("mp_rel_diff_median"),
              (pl.col("grade") == "gross").sum().alias("gross")), on="season", how="left")
          .join(unmatched.group_by("season").agg(pl.col("known_gap").sum().alias("known_gap")),
                on="season", how="left")
          .fill_null(0)
          .with_columns((pl.col("matched") / (pl.col("bbref_rows") - pl.col("known_gap")))
                        .alias("match_rate_ex_gap"),
                        (pl.col("matched") / pl.col("bbref_rows")).alias("match_rate_raw"))
          .sort("season"))

    (ROOT / "output").mkdir(exist_ok=True)
    by.write_csv(ROOT / "output" / "source_reconcile_by_season.csv")
    pl.concat([
        unmatched.select("season", "bbref_id", "name", "games", "pts",
                         pl.when(pl.col("known_gap")).then(pl.lit("unmatched_known_gap"))
                         .otherwise(pl.lit("unmatched")).alias("kind")),
        matched.filter(pl.col("grade") != "exact").select(
            "season", "bbref_id", "name", "games", "pts", pl.col("grade").alias("kind")),
    ]).sort("season", "kind", "name").write_csv(ROOT / "output" / "source_mismatches.csv")
    matched.select("bbref_id", "nba_id").unique().sort("bbref_id").write_csv(ROOT / "data" / "crosswalk.csv")

    with pl.Config(tbl_rows=60, tbl_cols=12):
        print(by)
    tot = matched.group_by("grade").len().sort("grade")
    print("grades:", dict(tot.iter_rows()), "| unmatched:", unmatched.height,
          f"(known LeagueLeaders gap {unmatched['known_gap'].sum()})")
    failing = by.filter((pl.col("season") >= 1978) & (pl.col("match_rate_ex_gap") < GATE_MATCH))
    gross = matched.filter(pl.col("grade") == "gross")
    if gross.height:
        print(gross.select("season", "name", "nba_name", "games", "games_n", "pts", "pts_n", "mp", "mp_n"))
    print(f"seasons below match gate: {failing.height}; gross rows: {gross.height}")
    if failing.height or gross.height:
        sys.exit(1)
    print("SOURCE RECONCILE PASSED")


if __name__ == "__main__":
    main()
