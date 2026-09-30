"""Score the inferred contract labels against three references, separately.

  wikipedia  Wikipedia free-agent tables (pages 2000-01, 2004-05 onward). A
             player listed as signing in league year Y after playing season
             Y-1 with the former team ended a deal after Y-1. Semi-independent
             of Basketball-Reference.
  bender     Patricia Bender's 2017-18 contracts snapshot: FA year 2018 means
             2017-18 was the deal's last season; a later FA year means it
             continued. Independent source, one season.
  gold       the hand-verified gold set (data/manual/gold/*.csv), built from
             news archives and team releases only. Each contract row gives
             its seasons; the last one is 'final', the others 'continues'.

For each reference the script reports, per era:
  final_recall      share of reference-final seasons the labeler calls final
  final_as_cont     share of reference-final seasons labeled 'continues'
                    (the costly error: a contract year in the control group)
  cont_recall       share of reference-continues seasons labeled continues
  cont_as_final     share of reference-continues labeled final
  unknown_share     share left unknown
Only rows the labeler has scored (player page harvested) count.
Output: output/label_validation.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def era(season: int) -> str:
    return ("1977-1988" if season <= 1988 else "1989-1999" if season <= 1999
            else "2000-2012" if season <= 2012 else "2013-2026")


def name_index(players: pl.DataFrame) -> pl.DataFrame:
    """(season, key) -> bbref_id, keeping only names unique within a season."""
    x = players.select("season", "bbref_id", pl.col("name").map_elements(norm, return_dtype=pl.String).alias("key"))
    return x.filter(pl.len().over("season", "key") == 1)


def score(ref: pl.DataFrame, lab: pl.DataFrame, name: str) -> pl.DataFrame:
    """ref: bbref_id, season, truth in {final, continues}."""
    j = ref.join(lab.select("bbref_id", "season", "status", "terminated"), on=["bbref_id", "season"], how="inner")
    j = j.filter(~pl.col("terminated")).with_columns(pl.col("season").map_elements(era, return_dtype=pl.String).alias("era"))
    out = []
    for keys, g in j.group_by("era", "truth"):
        e, truth = keys
        n = g.height
        rate = lambda s: g.filter(pl.col("status") == s).height / n  # noqa: E731
        out.append({"reference": name, "era": e, "truth": truth, "n": n,
                    "labeled_final": rate("final"), "labeled_continues": rate("continues"),
                    "labeled_unknown": rate("unknown")})
    return pl.DataFrame(out).sort("era", "truth") if out else pl.DataFrame()


def wiki_ref(lab: pl.DataFrame, idx: pl.DataFrame) -> pl.DataFrame:
    w = pl.read_csv(ROOT / "data" / "wiki_signings.csv", infer_schema_length=None)
    # Offseason or undated signings from an NBA former team (the team name
    # appears among Basketball-Reference salary-table teams).
    teams = set(pl.read_csv(ROOT / "data" / "player_salaries.csv")["team"].unique().to_list())
    w = w.filter(pl.col("former_team").is_in(list(teams)))
    w = w.filter(pl.col("date").is_null() | (pl.col("date").str.slice(5, 2).cast(pl.Int64) >= 7))
    w = w.with_columns((pl.col("page_season") - 1).alias("season"))
    ref = w.join(idx, on=["season", "key"], how="inner").select("bbref_id", "season").unique()
    return ref.with_columns(pl.lit("final").alias("truth"))


def bender_ref(idx: pl.DataFrame) -> pl.DataFrame:
    b = pl.read_csv(ROOT / "data" / "bender_2017_18.csv", infer_schema_length=None).filter(
        pl.col("fa_year").is_not_null() & ~pl.col("nbadl"))
    b = b.with_columns(pl.col("name").map_elements(norm, return_dtype=pl.String).alias("key"),
                       pl.lit(2018).alias("season"))
    # An option season makes the end ambiguous; keep only option-free rows.
    b = b.filter(pl.col("option") == "")
    b = b.with_columns(pl.when(pl.col("fa_year") == 2018).then(pl.lit("final"))
                       .otherwise(pl.lit("continues")).alias("truth"))
    return b.join(idx, on=["season", "key"], how="inner").select("bbref_id", "season", "truth")


def gold_ref(min_verification: set[str]) -> pl.DataFrame:
    files = sorted((ROOT / "data" / "manual" / "gold").glob("gold_*.csv"))
    if not files:
        return pl.DataFrame(schema={"bbref_id": pl.String, "season": pl.Int64, "truth": pl.String})
    # Agents write "unknown" where a season could not be established.
    g = pl.concat([pl.read_csv(f, infer_schema_length=0).select(
        "bbref_id", "first_season", "last_season", "verification", "how_ended") for f in files]).with_columns(
        pl.col("first_season").cast(pl.Int64, strict=False), pl.col("last_season").cast(pl.Int64, strict=False))
    g = g.filter(pl.col("verification").is_in(list(min_verification))
                 & pl.col("first_season").is_not_null() & pl.col("last_season").is_not_null())
    # Terminated deals (released, bought out) end early: their last season is
    # not a contract-expiry season, so only the continuing seasons count.
    rows = []
    for r in g.iter_rows(named=True):
        for s in range(r["first_season"], r["last_season"] + 1):
            if s == r["last_season"]:
                if r["how_ended"] in ("released", "bought_out", "waived_stretched", "running", "unknown", None):
                    continue
                rows.append({"bbref_id": r["bbref_id"], "season": s, "truth": "final"})
            else:
                rows.append({"bbref_id": r["bbref_id"], "season": s, "truth": "continues"})
    return pl.DataFrame(rows, schema={"bbref_id": pl.String, "season": pl.Int64, "truth": pl.String}).unique()


def main() -> None:
    # Wikipedia scores only the labeler that never read it (bbref-only);
    # Bender and the gold set score both labelers.
    both = pl.read_csv(ROOT / "data" / "contract_labels.csv", infer_schema_length=None)
    bonly = pl.read_csv(ROOT / "data" / "contract_labels_bbref.csv", infer_schema_length=None)
    players = pl.read_csv(ROOT / "data" / "bbref_player_seasons.csv", infer_schema_length=None)
    idx = name_index(players)
    parts = []
    for tag, lab in (("bbref_only", bonly), ("bbref_wiki", both)):
        got = [score(bender_ref(idx), lab, "bender_2017_18"),
               score(gold_ref({"verified"}), lab, "gold_verified"),
               score(gold_ref({"verified", "single_source"}), lab, "gold_verified_or_single")]
        if tag == "bbref_only":
            got.insert(0, score(wiki_ref(lab, idx), lab, "wikipedia"))
        parts += [g.with_columns(pl.lit(tag).alias("labeler")) for g in got if g.height]
    out = pl.concat(parts).select("labeler", pl.exclude("labeler"))
    out.write_csv(ROOT / "output" / "label_validation.csv")
    with pl.Config(tbl_rows=60, float_precision=3):
        print(out)


if __name__ == "__main__":
    main()
