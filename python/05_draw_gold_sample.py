"""Draw the stratified player sample for the hand-verified contract gold set.

The gold set measures how accurately the inferred contract-year labels
match reality, so it must be built from sources the labeler never reads
(news archives, team releases, Wikipedia biographies; never
Basketball-Reference salary or transaction data).

Strata: 4 eras (by career midpoint season) x 2 tiers.
  star  at least one All-NBA selection or a top-5% VORP season
  role  3+ seasons of 1,000+ minutes and never a star by the rule above
Players with fewer than three 1,000-minute seasons are out of scope here
(fringe players rarely have multi-year contracts to verify).

Seed fixed so the draw is reproducible. Output: data/manual/gold_sample.csv
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260929
ERAS = [(1977, 1988, "1977-1988"), (1989, 1999, "1989-1999"), (2000, 2012, "2000-2012"),
        (2013, 2026, "2013-2026")]
PER_STRATUM = {"star": 5, "role": 10}


def main() -> None:
    b = pl.read_csv(ROOT / "data" / "bbref_player_seasons.csv", infer_schema_length=None)
    b = b.with_columns((pl.col("vorp") >= pl.col("vorp").quantile(0.95).over("season")).alias("top_vorp"))
    p = b.group_by("bbref_id").agg(
        pl.col("name").last(),
        pl.col("season").min().alias("first"), pl.col("season").max().alias("last"),
        (pl.col("mp") >= 1000).sum().alias("big_seasons"),
        (pl.col("all_nba") | pl.col("top_vorp")).any().alias("star"))
    p = p.filter(pl.col("big_seasons") >= 3).with_columns(
        ((pl.col("first") + pl.col("last")) / 2).floor().cast(pl.Int64).alias("mid"),
        pl.when(pl.col("star")).then(pl.lit("star")).otherwise(pl.lit("role")).alias("tier"))
    draws = []
    for lo, hi, label in ERAS:
        for tier, k in PER_STRATUM.items():
            pool = p.filter(pl.col("mid").is_between(lo, hi) & (pl.col("tier") == tier)).sort("bbref_id")
            draws.append(pool.sample(n=k, seed=SEED).with_columns(pl.lit(label).alias("era")))
    out = pl.concat(draws).select("era", "tier", "bbref_id", "name", "first", "last").sort("era", "tier", "name")
    (ROOT / "data" / "manual").mkdir(parents=True, exist_ok=True)
    out.write_csv(ROOT / "data" / "manual" / "gold_sample.csv")
    print(out.group_by("era", "tier").len().sort("era", "tier"))
    with pl.Config(tbl_rows=80):
        print(out)


if __name__ == "__main__":
    main()
