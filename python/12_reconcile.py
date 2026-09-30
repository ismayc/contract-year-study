"""Gate: the R and Python implementations must agree before anything is published.

Two independent implementations disagree wherever a definition was
ambiguous; that disagreement is the signal worth catching.

Compared (row sets must match exactly in every table):
  panel        exp_bpm_raw, age_adj, exp_bpm, resid_bpm, vorp_pct   |diff| <= 1e-9
               tier, honors_star                                    equal
  scalars      regression minutes, fit rows                         equal
  aging curve  age_adj <= 1e-9, pairs equal
  effects      diff, mean_cy, mean_nc (<= 1e-9); n_cy, n_nc, players, n,
               n_next_250 (equal); share_played_next, resid_next (<= 1e-9);
               fe_coef, fe_se (<= 1e-6: different linear-algebra paths)
  bootstrap    the two languages use different RNGs, so interval endpoints
               must agree within 15% of the Python interval's width
  placebo      placebo_sd within 25% relative; placebo means within half a
               placebo sd of each other
  p_holm       depends on the bootstrap; reported, not gated

Exit code is non-zero on any failure. Run after both implementations:
  python python/10_build_panel.py && python python/11_contract_effect.py
  Rscript R/10_build_panel.R && Rscript R/11_contract_effect.R
  python python/12_reconcile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
TOL = 1e-9
TOL_MODEL = 1e-6
BOOT_FRAC = 0.15
PLACEBO_REL = 0.25

failures: list[str] = []


def load(name: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    return (pl.read_csv(OUT / f"{name}_python.csv", infer_schema_length=None),
            pl.read_csv(OUT / f"{name}_r.csv", infer_schema_length=None))


def joined(name: str, keys: list[str]) -> pl.DataFrame:
    p, r = load(name)
    # Writers differ on numeric key spelling (Python 20.0, R 20).
    for k in keys:
        if p[k].dtype.is_numeric() or r[k].dtype.is_numeric():
            p, r = p.with_columns(pl.col(k).cast(pl.Float64)), r.with_columns(pl.col(k).cast(pl.Float64))
    j = p.join(r, on=keys, how="full", suffix="_r", coalesce=True)
    one_sided = j.filter(pl.any_horizontal([pl.col(c).is_null() for c in p.columns if c not in keys][:1])
                         != pl.any_horizontal([pl.col(f"{c}_r").is_null() for c in p.columns if c not in keys][:1]))
    rows_p, rows_r = p.height, r.height
    if rows_p != rows_r or one_sided.height:
        failures.append(f"{name}: row sets differ (python {rows_p}, r {rows_r}, one-sided {one_sided.height})")
    return j


def close(j: pl.DataFrame, name: str, cols: list[str], tol: float) -> None:
    for c in cols:
        a, b = pl.col(c).cast(pl.Float64), pl.col(f"{c}_r").cast(pl.Float64)
        null_mismatch = j.filter(a.is_null() != b.is_null()).height
        d = j.select((a - b).abs().max()).item()
        d = 0.0 if d is None else d
        status = "ok" if d <= tol and null_mismatch == 0 else "FAIL"
        print(f"  {name:22s} {c:18s} max |diff| {d:.2e}  null mismatches {null_mismatch}  {status}")
        if status == "FAIL":
            failures.append(f"{name}.{c}: max diff {d:.3g}, null mismatches {null_mismatch}")


def equal(j: pl.DataFrame, name: str, cols: list[str]) -> None:
    for c in cols:
        bad = j.filter(pl.col(c).cast(pl.String).fill_null("") != pl.col(f"{c}_r").cast(pl.String).fill_null("")).height
        # Booleans print as true/TRUE across the two writers.
        if bad and j[c].dtype == pl.Boolean or bad and str(j[c].dtype).startswith(("Int", "Float")):
            bad = j.filter(pl.col(c).cast(pl.Float64) != pl.col(f"{c}_r").cast(pl.Float64)).height
        print(f"  {name:22s} {c:18s} mismatched rows {bad}  {'ok' if not bad else 'FAIL'}")
        if bad:
            failures.append(f"{name}.{c}: {bad} mismatched rows")


def bootstrap(j: pl.DataFrame, name: str) -> None:
    width = pl.col("ci_hi") - pl.col("ci_lo")
    worst = j.select(pl.max_horizontal((pl.col("ci_lo") - pl.col("ci_lo_r")).abs() / width,
                                       (pl.col("ci_hi") - pl.col("ci_hi_r")).abs() / width).max()).item()
    ok = worst is not None and worst <= BOOT_FRAC
    print(f"  {name:22s} {'bootstrap CI':18s} worst endpoint gap {worst:.3f} of width  {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append(f"{name}: bootstrap endpoints differ by {worst:.3f} of width")


def main() -> None:
    print("panel")
    j = joined("panel", ["bbref_id", "season"])
    close(j, "panel", ["exp_bpm_raw", "age_adj", "exp_bpm", "resid_bpm", "vorp_pct"], TOL)
    equal(j, "panel", ["tier", "honors_star"])
    j = joined("panel_scalars", ["quantity"])
    close(j, "panel_scalars", ["value"], 0.0)
    j = joined("aging_curve", ["age_bin"])
    close(j, "aging_curve", ["age_adj"], TOL)
    equal(j, "aging_curve", ["pairs"])

    print("effects")
    for name, keys in (("effect_primary", ["spec", "era", "tier"]),
                       ("effect_sensitivity", ["spec", "era", "tier"]),
                       ("effect_secondary", ["outcome", "era", "tier"])):
        j = joined(name, keys)
        close(j, name, ["diff", "mean_cy", "mean_nc"], TOL)
        equal(j, name, ["n_cy", "n_nc", "players"])
        if "fe_coef" in j.columns:
            close(j, name, ["fe_coef", "fe_se"], TOL_MODEL)
        bootstrap(j, name)
        if name == "effect_primary":
            rel = j.select(((pl.col("placebo_sd") - pl.col("placebo_sd_r")).abs()
                            / pl.max_horizontal(pl.col("placebo_sd"), pl.lit(1e-12))).max()).item()
            gap = j.select(((pl.col("placebo_mean") - pl.col("placebo_mean_r")).abs()
                            - 0.5 * pl.max_horizontal(pl.col("placebo_sd"), pl.col("placebo_sd_r"))).max()).item()
            # Cells with a single contract-year arrangement per player have a
            # placebo sd of zero in both languages; they compare exactly.
            ok = (rel <= PLACEBO_REL) and (gap <= 1e-12)
            print(f"  {name:22s} {'placebo':18s} worst sd gap {rel:.3f}, mean gap beyond 0.5 sd {max(gap, 0):.3f}  {'ok' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"{name}: placebo disagreement (sd rel {rel:.3f}, mean excess {gap:.3f})")
        if name == "effect_secondary":
            d = j.select((pl.col("p_holm") - pl.col("p_holm_r")).abs().max()).item()
            print(f"  {name:22s} {'p_holm (info)':18s} max |diff| {d:.3f} (bootstrap-dependent, not gated)")
    j = joined("effect_post", ["era", "tier", "group"])
    close(j, "effect_post", ["share_played_next", "resid_next"], TOL)
    equal(j, "effect_post", ["n", "n_next_250"])

    if failures:
        print("\nRECONCILE FAILED")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nRECONCILE PASSED")


if __name__ == "__main__":
    main()
