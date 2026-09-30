"""The effect estimators recover a planted effect and the placebo centers
on zero, on synthetic data where the truth is known."""

import importlib.util
from pathlib import Path

import numpy as np
import polars as pl

_spec = importlib.util.spec_from_file_location(
    "ce", Path(__file__).resolve().parents[2] / "python" / "11_contract_effect.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)


def synthetic(effect: float, seed: int = 1) -> pl.DataFrame:
    """400 players x 8 seasons; every third season a contract year. Player
    levels vary widely, so the fixed-effects estimator must remove them."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(400):
        level = rng.normal(0, 2)
        for k in range(8):
            cy = k % 3 == 2
            rows.append({"bbref_id": f"p{p}", "season": 2005 + k, "mp": float(rng.integers(300, 2500)),
                         "resid": level + rng.normal(0, 2) + (effect if cy else 0.0), "cy": cy})
    return pl.DataFrame(rows)


def test_diff_and_fe_recover_planted_effect():
    df = synthetic(1.0)
    rng = np.random.default_rng(2)
    d = ce.diff_boot(df, "cy", rng)
    f = ce.fe(df, "cy")
    assert d["ci_lo"] < 1.0 < d["ci_hi"]
    assert abs(f["fe_coef"] - 1.0) < 3 * f["fe_se"]
    assert d["n_cy"] == 800 and d["n_nc"] == 2400 and d["players"] == 400


def test_null_effect_interval_covers_zero_and_placebo_centers():
    df = synthetic(0.0, seed=3)
    rng = np.random.default_rng(4)
    d = ce.diff_boot(df, "cy", rng)
    assert d["ci_lo"] < 0.0 < d["ci_hi"]
    ce.N_PLACEBO = 100
    pb = ce.placebo(synthetic(1.0), "cy", rng)
    assert abs(pb["placebo_mean"]) < 3 * pb["placebo_sd"]


def test_empty_group_returns_nothing():
    df = synthetic(0.0).with_columns(pl.lit(False).alias("cy"))
    assert ce.diff_boot(df, "cy", np.random.default_rng(0)) == {}
