"""Estimate the contract-year effect as pre-specified in docs/design.md.

Groups: contract year (cy_strict) vs guaranteed non-contract year
(nc_strict), seasons with at least 250 minutes and an expectation.
Eras: 1977-1988, 1989-1999, 2000-2026 (the 1999-00+ headline), and
1974-1976 as the no-incentive baseline (labels there are exploratory).

Estimators, per tier (star/starter/role/fringe) and era:
  diff      minutes-weighted mean residual BPM, contract year minus
            comparison; 95% interval from a player-clustered bootstrap
  fe        player fixed-effects WLS of the residual on the contract-year
            flag (weights = minutes), SE clustered by player
  placebo   the diff recomputed after shuffling the contract-year flag
            within each player's labeled seasons: its spread is the null
            distribution the real diff is read against
Sensitivities: cy_broad in place of cy_strict; high-confidence labels
only; honors-based star tier; regression minutes fixed at 1,000 (rebuild
the panel with --fixed-1000 and rerun with --tag fixed1000).
Secondary outcomes (Holm-corrected within each tier x era cell): change
from t-1, minus the age-bin mean change among non-contract pairs, for
minutes per game, games, TS%, usage %, WS/48, PER.
Post-contract: for contract-year seasons, share with an NBA season t+1,
and residual BPM in t+1 against players who were in the comparison group
at t.

Outputs: output/effect_{primary,sensitivity,secondary,post}_python.csv
(R/11_contract_effect.R writes the _r twins; 12_reconcile.py compares them)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260929
N_BOOT = 2000
N_PLACEBO = 500
MIN_MP = 250
ERAS = [("1974-1976", 1974, 1976), ("1977-1988", 1977, 1988), ("1989-1999", 1989, 1999), ("2000-2026", 2000, 2026)]
TIERS = ["star", "starter", "role", "fringe", "all"]
SECONDARY = ["mpg", "games", "ts_pct", "usg_pct", "ws_per_48", "per"]


def wmean(x: np.ndarray, w: np.ndarray) -> float:
    return float((x * w).sum() / w.sum())


def diff_boot(df: pl.DataFrame, flag: str, rng: np.random.Generator) -> dict:
    """Weighted diff and player-clustered bootstrap interval."""
    y, w, f = df["resid"].to_numpy(), df["mp"].to_numpy(), df[flag].to_numpy()
    pid = df["bbref_id"].to_numpy()
    if f.sum() == 0 or (~f).sum() == 0:
        return {}
    est = wmean(y[f], w[f]) - wmean(y[~f], w[~f])
    players, inv = np.unique(pid, return_inverse=True)
    # Per-player sums so each bootstrap draw is a weighted count of players.
    s_cy = np.bincount(inv, weights=(y * w) * f, minlength=len(players))
    w_cy = np.bincount(inv, weights=w * f, minlength=len(players))
    s_nc = np.bincount(inv, weights=(y * w) * ~f, minlength=len(players))
    w_nc = np.bincount(inv, weights=w * ~f, minlength=len(players))
    draws = rng.multinomial(len(players), np.full(len(players), 1 / len(players)), size=N_BOOT)
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = draws @ s_cy / (draws @ w_cy) - draws @ s_nc / (draws @ w_nc)
    boot = boot[np.isfinite(boot)]
    return {"diff": est, "ci_lo": float(np.quantile(boot, 0.025)), "ci_hi": float(np.quantile(boot, 0.975)),
            "n_cy": int(f.sum()), "n_nc": int((~f).sum()), "players": len(players),
            "mean_cy": wmean(y[f], w[f]), "mean_nc": wmean(y[~f], w[~f])}


def fe(df: pl.DataFrame, flag: str) -> dict:
    """Within-player WLS: demean by player (minutes-weighted), cluster SE."""
    x = df.select("bbref_id", "resid", "mp", pl.col(flag).cast(pl.Float64).alias("f"))
    x = x.with_columns(
        (pl.col("resid") - (pl.col("resid") * pl.col("mp")).sum().over("bbref_id") / pl.col("mp").sum().over("bbref_id")).alias("y_d"),
        (pl.col("f") - (pl.col("f") * pl.col("mp")).sum().over("bbref_id") / pl.col("mp").sum().over("bbref_id")).alias("f_d"))
    # Players with no within-variation in the flag carry no information.
    x = x.filter(pl.col("f_d").abs().max().over("bbref_id") > 1e-12)
    if x.height < 20 or x["bbref_id"].n_unique() < 10:
        return {}
    groups = x["bbref_id"].cast(pl.Categorical).to_physical().to_numpy()
    m = sm.WLS(x["y_d"].to_numpy(), x["f_d"].to_numpy(), weights=x["mp"].to_numpy()).fit(
        cov_type="cluster", cov_kwds={"groups": groups})
    return {"fe_coef": float(m.params[0]), "fe_se": float(m.bse[0]), "fe_players": x["bbref_id"].n_unique()}


def placebo(df: pl.DataFrame, flag: str, rng: np.random.Generator) -> dict:
    y, w = df["resid"].to_numpy(), df["mp"].to_numpy()
    f = df[flag].to_numpy().copy()
    pid = df["bbref_id"].to_numpy()
    order = np.argsort(pid, kind="stable")
    bounds = np.flatnonzero(np.r_[True, pid[order][1:] != pid[order][:-1], True])
    vals = []
    for _ in range(N_PLACEBO):
        g = f.copy()
        for a, b in zip(bounds[:-1], bounds[1:]):
            idx = order[a:b]
            g[idx] = rng.permutation(f[idx])
        if g.sum() and (~g).sum():
            vals.append(wmean(y[g], w[g]) - wmean(y[~g], w[~g]))
    v = np.array(vals)
    return {"placebo_mean": float(v.mean()), "placebo_sd": float(v.std())}


def cells(panel: pl.DataFrame, flag_cy: str, tier_col: str):
    for era, lo, hi in ERAS:
        e = panel.filter(pl.col("season").is_between(lo, hi))
        for tier in TIERS:
            t = e if tier == "all" else e.filter(pl.col(tier_col) == tier)
            yield era, tier, t


def analysis_sample(panel: pl.DataFrame, cy: str, extra: pl.Expr | None = None) -> pl.DataFrame:
    s = panel.filter((pl.col("mp") >= MIN_MP) & pl.col("resid_bpm").is_not_null()
                     & (pl.col(cy).fill_null(False) | pl.col("nc_strict").fill_null(False)))
    if extra is not None:
        s = s.filter(extra)
    return s.with_columns(pl.col("resid_bpm").alias("resid"), pl.col(cy).fill_null(False).alias("cy"))


def main() -> None:
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "main"
    rng = np.random.default_rng(SEED)
    panel = pl.read_csv(ROOT / "data" / ("panel.csv" if tag == "main" else f"panel_{tag}.csv"), infer_schema_length=None)
    panel = panel.with_columns(pl.when(pl.col("honors_star")).then(pl.lit("star")).otherwise(pl.lit("non_star"))
                               .alias("honors_tier"))
    out = ROOT / "output"

    rows = []
    for era, tier, t in cells(analysis_sample(panel, "cy_strict"), "cy", "tier"):
        r = diff_boot(t, "cy", rng)
        if not r:
            continue
        rows.append({"spec": "strict", "era": era, "tier": tier, **r, **fe(t, "cy"), **placebo(t, "cy", rng)})
    prim = pl.DataFrame(rows)
    prim.write_csv(out / ("effect_primary_python.csv" if tag == "main" else f"effect_primary_{tag}_python.csv"))

    sens = []
    specs = [("broad", "cy_broad", None, "tier"),
             # High confidence applies to the contract-year group only:
             # comparison seasons rest on the absence of end signals, so
             # they are never "high" and filtering them would empty the group.
             ("strict_high_conf", "cy_strict",
              ~pl.col("cy_strict").fill_null(False) | (pl.col("confidence") == "high"), "tier"),
             ("strict_honors_tier", "cy_strict", None, "honors_tier")]
    for name, cy, extra, tier_col in specs:
        s = analysis_sample(panel, cy, extra)
        for era, lo, hi in ERAS:
            e = s.filter(pl.col("season").is_between(lo, hi))
            tiers = ["star", "non_star"] if tier_col == "honors_tier" else TIERS
            for tier in tiers:
                t = e if tier == "all" else e.filter(pl.col(tier_col) == tier)
                r = diff_boot(t, "cy", rng)
                if r:
                    sens.append({"spec": name, "era": era, "tier": tier, **r, **fe(t, "cy")})
    pl.DataFrame(sens).write_csv(out / ("effect_sensitivity_python.csv" if tag == "main" else f"effect_sensitivity_{tag}_python.csv"))

    if tag == "main":
        secondary(panel, rng, out)
        post(panel, out)
    with pl.Config(tbl_rows=40, tbl_cols=14, float_precision=3):
        print(prim.select("era", "tier", "n_cy", "n_nc", "diff", "ci_lo", "ci_hi", "fe_coef", "fe_se",
                          "placebo_sd"))


def secondary(panel: pl.DataFrame, rng: np.random.Generator, out: Path) -> None:
    p = panel.with_columns((pl.col("mp") / pl.col("games")).alias("mpg"))
    lag = p.select("bbref_id", (pl.col("season") + 1).alias("season"),
                   *[pl.col(c).alias(f"{c}_l1") for c in SECONDARY])
    p = p.join(lag, on=["bbref_id", "season"], how="left")
    rows = []
    for c in SECONDARY:
        q = p.with_columns((pl.col(c) - pl.col(f"{c}_l1")).alias("chg"))
        base = q.filter(~pl.col("cy_broad").fill_null(False) & ~pl.col("cy_strict").fill_null(False)
                        & pl.col("chg").is_not_null())
        ag = base.group_by("age_bin").agg(((pl.col("chg") * pl.col("mp")).sum() / pl.col("mp").sum()).alias("age_chg"))
        q = q.join(ag, on="age_bin", how="left").with_columns((pl.col("chg") - pl.col("age_chg")).alias("resid_bpm"))
        s = analysis_sample(q, "cy_strict").filter(pl.col("resid").is_not_null() & pl.col("resid").is_finite())
        for era, tier, t in cells(s, "cy", "tier"):
            r = diff_boot(t, "cy", rng)
            if r:
                se = (r["ci_hi"] - r["ci_lo"]) / (2 * 1.96)
                from scipy.stats import norm as _n
                pval = float(2 * (1 - _n.cdf(abs(r["diff"]) / se))) if se > 0 else float("nan")
                rows.append({"outcome": c, "era": era, "tier": tier, **r, "p_boot_normal": pval})
    sec = pl.DataFrame(rows)
    # Holm across the six outcomes within each era x tier cell.
    sec = sec.sort("era", "tier", "p_boot_normal").with_columns(
        pl.col("p_boot_normal").rank("ordinal").over("era", "tier").alias("rank"),
        pl.len().over("era", "tier").alias("m"))
    sec = sec.with_columns((pl.col("p_boot_normal") * (pl.col("m") - pl.col("rank") + 1)).clip(upper_bound=1.0).alias("p_step"))
    sec = sec.with_columns(pl.col("p_step").cum_max().over("era", "tier").alias("p_holm")).drop("p_step")
    sec.write_csv(out / "effect_secondary_python.csv")


def post(panel: pl.DataFrame, out: Path) -> None:
    nxt = panel.select("bbref_id", (pl.col("season") - 1).alias("season"),
                       pl.col("resid_bpm").alias("resid_next"), pl.col("mp").alias("mp_next"))
    p = panel.filter((pl.col("mp") >= MIN_MP) & pl.col("resid_bpm").is_not_null()
                     & (pl.col("cy_strict").fill_null(False) | pl.col("nc_strict").fill_null(False))
                     & (pl.col("season") < 2026)).join(nxt, on=["bbref_id", "season"], how="left")
    rows = []
    for era, lo, hi in ERAS:
        for tier in TIERS:
            t = p.filter(pl.col("season").is_between(lo, hi))
            t = t if tier == "all" else t.filter(pl.col("tier") == tier)
            for grp, g in (("contract_year", t.filter(pl.col("cy_strict").fill_null(False))),
                           ("comparison", t.filter(~pl.col("cy_strict").fill_null(False)))):
                if g.height == 0:
                    continue
                nx = g.filter(pl.col("resid_next").is_not_null() & (pl.col("mp_next") >= MIN_MP))
                rows.append({"era": era, "tier": tier, "group": grp, "n": g.height,
                             "share_played_next": g.filter(pl.col("mp_next").is_not_null()).height / g.height,
                             "n_next_250": nx.height,
                             "resid_next": wmean(nx["resid_next"].to_numpy(), nx["mp_next"].to_numpy()) if nx.height else None})
    pl.DataFrame(rows).write_csv(out / "effect_post_python.csv")


if __name__ == "__main__":
    main()
