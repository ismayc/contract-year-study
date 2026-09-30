"""Build the analysis panel exactly as pre-specified in docs/design.md.

For every player-season t:
  expected BPM   weighted prior BPM from seasons t-1, t-2, t-3 (weights
                 1.0, 0.8, 0.6, the design's 5/4/3 scaled), each weighted by
                 its minutes, regressed toward the league mean (0.0) by
                 adding 1,000 minutes of a 0.0 season:
                   exp = sum(w_k m_k b_k) / (sum(w_k m_k) + 1000)
  age adjustment the delta-method aging curve at age t: the minutes-weighted
                 mean change in BPM from t-1 to t across consecutive-season
                 pairs where t is NOT a contract year under either
                 definition (harmonic-mean minutes weights); ages under 20
                 and over 37 are pooled into the end bins
  residual       BPM_t - (exp + age adjustment)
  tier           summed VORP over t-1 and t-2, percentile among everyone
                 who played season t: star top 10%, starter 10-30%,
                 role 30-70%, fringe bottom 30%
  honors_star    All-NBA or All-Star in t-1 or t-2

No contract-year comparison is computed here; this script only prints
diagnostics (aging curve, calibration of the expectation, tier counts).
Output: data/panel.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {1: 1.0, 2: 0.8, 3: 0.6}
REGRESS_MIN = 1000.0
AGE_LO, AGE_HI = 20, 37


def main() -> None:
    d = ROOT / "data"
    b = pl.read_csv(d / "bbref_player_seasons.csv", infer_schema_length=None).select(
        "bbref_id", "season", "name", "age", "games", "games_started", "mp", "bpm", "vorp", "ts_pct",
        "usg_pct", "ws_per_48", "per", "all_star", "all_nba")
    lab = pl.read_csv(d / "contract_labels.csv", infer_schema_length=None)
    b = b.join(lab.select("bbref_id", "season", "status", "cy_strict", "cy_broad", "nc_strict", "confidence",
                          "signals", "secured", "terminated", "cut_offseason", "rookie_deal"),
               on=["bbref_id", "season"], how="left")

    # Prior seasons by calendar lag.
    for k in (1, 2, 3):
        prev = b.select("bbref_id", (pl.col("season") + k).alias("season"),
                        pl.col("mp").alias(f"mp_l{k}"), pl.col("bpm").alias(f"bpm_l{k}"),
                        pl.col("vorp").alias(f"vorp_l{k}"),
                        (pl.col("all_star") | pl.col("all_nba")).alias(f"hon_l{k}"))
        b = b.join(prev, on=["bbref_id", "season"], how="left")
    num = sum(WEIGHTS[k] * pl.col(f"mp_l{k}").fill_null(0) * pl.col(f"bpm_l{k}").fill_null(0) for k in (1, 2, 3))
    den = sum(WEIGHTS[k] * pl.col(f"mp_l{k}").fill_null(0) for k in (1, 2, 3))
    b = b.with_columns(num.alias("_num"), den.alias("_den"))

    # Amendment 1 (docs/design.md): the regression minutes are fit on
    # non-contract seasons (neither definition) with at least 250 minutes,
    # minimizing minutes-weighted squared error, instead of fixed at 1,000.
    fit_rows = b.filter(~pl.col("cy_broad").fill_null(False) & ~pl.col("cy_strict").fill_null(False)
                        & (pl.col("_den") > 0) & (pl.col("mp") >= 250) & pl.col("bpm").is_not_null())
    grid = list(range(0, 5001, 100))
    sse = []
    for r in grid:
        e = fit_rows.select((((pl.col("bpm") - pl.col("_num") / (pl.col("_den") + r)) ** 2) * pl.col("mp")).sum()).item()
        sse.append(e)
    regress_min = float(grid[sse.index(min(sse))]) if "--fixed-1000" not in sys.argv else REGRESS_MIN
    print(f"regression minutes: {regress_min:.0f} (pre-specified 1,000; fit on {fit_rows.height} non-contract seasons)")
    b = b.with_columns(
        pl.when(pl.col("_den") > 0).then(pl.col("_num") / (pl.col("_den") + regress_min)).otherwise(None).alias("exp_bpm_raw"),
        (pl.col("vorp_l1").fill_null(0) + pl.col("vorp_l2").fill_null(0)).alias("vorp_prior2"),
        (pl.col("hon_l1").fill_null(False) | pl.col("hon_l2").fill_null(False)).alias("honors_star"),
        pl.col("age").clip(AGE_LO, AGE_HI).alias("age_bin"))

    # Aging curve (delta method), excluding pairs whose later season is a
    # contract year under either definition.
    pairs = b.filter(pl.col("mp_l1").is_not_null() & pl.col("bpm").is_not_null() & pl.col("bpm_l1").is_not_null()
                     & ~pl.col("cy_broad").fill_null(False) & ~pl.col("cy_strict").fill_null(False)
                     & (pl.col("mp") > 0) & (pl.col("mp_l1") > 0))
    pairs = pairs.with_columns((pl.col("bpm") - pl.col("bpm_l1")).alias("delta"),
                               (2 / (1 / pl.col("mp") + 1 / pl.col("mp_l1"))).alias("hw"))
    curve = (pairs.group_by("age_bin").agg(((pl.col("delta") * pl.col("hw")).sum() / pl.col("hw").sum()).alias("age_adj"),
                                            pl.len().alias("pairs")).sort("age_bin"))
    b = b.join(curve.select("age_bin", "age_adj"), on="age_bin", how="left")
    b = b.with_columns((pl.col("exp_bpm_raw") + pl.col("age_adj")).alias("exp_bpm"))
    b = b.with_columns((pl.col("bpm") - pl.col("exp_bpm")).alias("resid_bpm"))

    # Tiers from prior value.
    b = b.with_columns((pl.col("vorp_prior2").rank("average").over("season")
                        / pl.len().over("season")).alias("vorp_pct"))
    b = b.with_columns(pl.when(pl.col("vorp_pct") > 0.90).then(pl.lit("star"))
                       .when(pl.col("vorp_pct") > 0.70).then(pl.lit("starter"))
                       .when(pl.col("vorp_pct") > 0.30).then(pl.lit("role"))
                       .otherwise(pl.lit("fringe")).alias("tier"))
    if "--fixed-1000" in sys.argv:
        # Sensitivity panel only: the reconciled outputs stay on the fitted run.
        b.write_csv(d / "panel_fixed1000.csv")
        return
    b.write_csv(d / "panel.csv")
    out = ROOT / "output"
    curve.write_csv(out / "aging_curve_python.csv")
    # What 12_reconcile.py compares against R/10_build_panel.R.
    b.select("bbref_id", "season", "exp_bpm_raw", "age_adj", "exp_bpm", "resid_bpm", "vorp_pct", "tier",
             "honors_star").sort("bbref_id", "season").write_csv(out / "panel_python.csv")
    pl.DataFrame({"quantity": ["regression_minutes", "fit_rows"],
                  "value": [regress_min, float(fit_rows.height)]}).write_csv(out / "panel_scalars_python.csv")

    ok = b.filter(pl.col("exp_bpm").is_not_null() & (pl.col("mp") >= 250))
    with pl.Config(tbl_rows=30, float_precision=3):
        print("aging curve (BPM change t-1 -> t by age at t):")
        print(curve)
        print("calibration by tier (minutes-weighted mean residual, all labels pooled):")
        print(ok.group_by("tier").agg(pl.len().alias("n"),
                                      ((pl.col("resid_bpm") * pl.col("mp")).sum() / pl.col("mp").sum()).alias("wmean_resid"))
              .sort("tier"))
        print("label status counts in the analysis sample (mp >= 250, has expectation):")
        print(ok.group_by("status").len().sort("status"))


if __name__ == "__main__":
    main()
