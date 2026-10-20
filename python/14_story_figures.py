"""Build the interactive figures for the family page (docs/story.md).

Every value comes from the committed Python outputs, which 12_reconcile.py
gates equal to the R run. Figures are plotly originals written to figures/;
report_builder.py swaps in the family's famplot engine at publish time.

Figures:
  fig1_tier_effects_py      contract-year difference and within-player
                            estimate, by tier, 1999-00 onward
  fig2_sensitivity_py       role players and stars under each specification
  fig3_season_after_py      share who played another NBA season, by tier

Run:  python python/14_story_figures.py
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"
ERA = "2000-2026"
TIERS = ["star", "starter", "role", "fringe", "all"]
TIER_NAME = {"star": "Stars", "starter": "Starters", "role": "Role players",
             "fringe": "Fringe players", "all": "All tiers"}
Z = 1.959964


def one(df: pl.DataFrame, **keys) -> dict:
    for k, v in keys.items():
        df = df.filter(pl.col(k) == v)
    if df.height != 1:
        raise SystemExit(f"expected one row for {keys}, found {df.height}")
    return df.row(0, named=True)


def zero_line() -> dict:
    return dict(type="line", xref="x", yref="paper", x0=0, x1=0, y0=0, y1=1,
                line=dict(width=1, dash="dot"))


def base_layout(title: str, xtitle: str, height: int) -> dict:
    return dict(title=title, xaxis_title=xtitle, template="plotly_white",
                height=height, margin=dict(l=190, r=30, t=60, b=60),
                legend=dict(orientation="h", y=-0.2),
                yaxis=dict(type="category", autorange="reversed"))


def fig_tiers(prim: pl.DataFrame) -> go.Figure:
    rows = [one(prim, era=ERA, tier=t) for t in TIERS]
    names = [TIER_NAME[t] for t in TIERS]
    f = go.Figure()
    f.add_trace(go.Scatter(
        x=[r["diff"] for r in rows], y=names, mode="markers",
        name="Contract year vs guaranteed year (95% interval)",
        error_x=dict(type="data", symmetric=False,
                     array=[r["ci_hi"] - r["diff"] for r in rows],
                     arrayminus=[r["diff"] - r["ci_lo"] for r in rows]),
        customdata=[[r["n_cy"], r["n_nc"]] for r in rows],
        hovertemplate=("%{y}: %{x:+.2f} BPM<br>%{customdata[0]:,} contract-year"
                       " and %{customdata[1]:,} comparison seasons<extra></extra>")))
    f.add_trace(go.Scatter(
        x=[r["fe_coef"] for r in rows], y=names, mode="markers",
        name="Within-player estimate (95% interval)",
        error_x=dict(type="data", array=[Z * r["fe_se"] for r in rows]),
        hovertemplate="%{y}, within-player: %{x:+.2f} BPM<extra></extra>"))
    f.update_layout(**base_layout(
        "Role players gain a little in contract years; stars do not",
        "Box Plus/Minus against expectation, contract year minus comparison",
        440), shapes=[zero_line()])
    return f


def fig_sensitivity(prim, sens, fixed) -> go.Figure:
    specs = [
        ("Primary", prim, None),
        ("Broad definition", sens, "broad"),
        ("High-confidence labels", sens, "strict_high_conf"),
        ("1,000 regression minutes", fixed, None),
        ("Stars by honors", sens, "strict_honors_tier"),
    ]
    f = go.Figure()
    for tier in ("role", "star"):
        xs, ys, lo, hi = [], [], [], []
        for label, df, spec in specs:
            if spec == "strict_honors_tier" and tier == "role":
                continue
            d = df.filter(pl.col("spec") == spec) if spec else df
            r = one(d, era=ERA, tier=tier)
            xs.append(r["diff"]); ys.append(label)
            lo.append(r["diff"] - r["ci_lo"]); hi.append(r["ci_hi"] - r["diff"])
        f.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers", name=TIER_NAME[tier],
            error_x=dict(type="data", symmetric=False, array=hi, arrayminus=lo),
            hovertemplate=f"{TIER_NAME[tier]}, %{{y}}: %{{x:+.2f}} BPM<extra></extra>"))
    f.update_layout(**base_layout(
        "Role players stay above zero under every specification",
        "Contract-year difference in Box Plus/Minus (95% interval)", 420),
        shapes=[zero_line()])
    return f


def fig_season_after(post: pl.DataFrame) -> go.Figure:
    # Only players who returned have a next season to score. The comparison
    # group's return rate is 1 by construction (its deal continued), so the
    # share who left is a contract-year-only fact and stays in the prose.
    tiers = [t for t in TIERS if t != "all"]
    f = go.Figure()
    for group, label in (("contract_year", "After a contract year"),
                         ("comparison", "After a guaranteed year")):
        rows = [one(post, era=ERA, tier=t, group=group) for t in tiers]
        f.add_trace(go.Bar(
            x=[r["resid_next"] for r in rows],
            y=[TIER_NAME[t] for t in tiers], orientation="h", name=label,
            customdata=[[r["n_next_250"]] for r in rows],
            hovertemplate=("%{y}, " + label.lower()
                           + ": %{x:+.2f} BPM (%{customdata[0]:,} players with 250+ minutes)"
                           "<extra></extra>")))
    f.update_layout(**base_layout(
        "The next season, for players who returned, 1999-00 to 2025-26",
        "Box Plus/Minus against expectation the following season", 380),
        barmode="group", shapes=[zero_line()])
    return f


def main() -> None:
    FIG.mkdir(exist_ok=True)
    prim = pl.read_csv(OUT / "effect_primary_python.csv")
    sens = pl.read_csv(OUT / "effect_sensitivity_python.csv")
    fixed = pl.read_csv(OUT / "effect_primary_fixed1000_python.csv")
    post = pl.read_csv(OUT / "effect_post_python.csv")
    for name, fig in (("fig1_tier_effects_py", fig_tiers(prim)),
                      ("fig2_sensitivity_py", fig_sensitivity(prim, sens, fixed)),
                      ("fig3_season_after_py", fig_season_after(post))):
        fig.write_html(FIG / f"{name}.html", include_plotlyjs="cdn")
        print(f"wrote figures/{name}.html")


if __name__ == "__main__":
    main()
