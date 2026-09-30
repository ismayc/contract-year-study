"""Generate every number in the README from computed outputs.

No number in the write-up is typed by hand. The generator owns the marked
regions of README.md (<!-- gen:NAME --> ... <!-- /gen:NAME -->) and rewrites
them from output/*.csv; prose outside the regions carries no numbers. Python
outputs are the source (the R run is gated equal by 12_reconcile.py first).

Regions: headline, results, sensitivity, secondary, post, labels, data, eras.

Run:    python python/13_findings.py           rewrite the regions
        python python/13_findings.py --check   fail if README.md differs from
                                               what a rewrite would produce
                                               (abbr tags stripped first)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
README = ROOT / "README.md"
ABBR = re.compile(r'<abbr title="[^"]*">([^<]*)</abbr>')
REGION = re.compile(r"(<!-- gen:(\w+) -->)(.*?)(<!-- /gen:\2 -->)", re.S)
HEADLINE_ERA = "2000-2026"
TIER_ORDER = ["star", "starter", "role", "fringe", "all"]
TIER_NAME = {"star": "Stars", "starter": "Starters", "role": "Role players", "fringe": "Fringe players",
             "all": "All tiers", "non_star": "Everyone else"}


def era_label(e: str) -> str:
    a, b = e.split("-")
    return f"{int(a) - 1}-{a[-2:]} to {int(b) - 1}-{b[-2:]}"


def f2(x: float) -> str:
    return f"{x:+.2f}".replace("-", "−")


def ci(r: dict) -> str:
    return f"{f2(r['diff'])} ({f2(r['ci_lo'])} to {f2(r['ci_hi'])})"


def fe(r: dict) -> str:
    return f"{f2(r['fe_coef'])} (SE {r['fe_se']:.2f})" if r.get("fe_coef") is not None else "n/a"


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def row(df: pl.DataFrame, **keys) -> dict:
    d = df
    for k, v in keys.items():
        d = d.filter(pl.col(k) == v)
    if d.height != 1:
        raise SystemExit(f"expected one row for {keys}, found {d.height}")
    return d.row(0, named=True)


def precision_recall(v: pl.DataFrame, reference: str, era: str) -> tuple[float, float, int, int]:
    """Precision of 'final' labels and recall of true finals, from the
    per-truth label shares in label_validation.csv."""
    x = v.filter((pl.col("labeler") == "bbref_wiki") & (pl.col("reference") == reference) & (pl.col("era") == era))
    fin = row(x, truth="final")
    con = row(x, truth="continues")
    tp = fin["n"] * fin["labeled_final"]
    fp = con["n"] * con["labeled_final"]
    return tp / (tp + fp), fin["labeled_final"], fin["n"], con["n"]


def build() -> dict[str, str]:
    prim = pl.read_csv(OUT / "effect_primary_python.csv")
    sens = pl.read_csv(OUT / "effect_sensitivity_python.csv")
    fixed = pl.read_csv(OUT / "effect_primary_fixed1000_python.csv")
    sec = pl.read_csv(OUT / "effect_secondary_python.csv")
    post = pl.read_csv(OUT / "effect_post_python.csv")
    val = pl.read_csv(OUT / "label_validation.csv")
    src = pl.read_csv(OUT / "source_reconcile_by_season.csv")
    scal = pl.read_csv(OUT / "panel_scalars_python.csv")
    H = prim.filter(pl.col("era") == HEADLINE_ERA)
    role, star = row(H, tier="role"), row(H, tier="star")
    hstar = row(sens, spec="strict_honors_tier", era=HEADLINE_ERA, tier="star")
    g = {}

    g["headline"] = (
        f"\n**Role players do a little better in contract years; stars do not.** Over "
        f"{era_label(HEADLINE_ERA)}, role players beat their expected Box Plus/Minus by "
        f"{f2(role['diff'])} points per 100 possessions more in a contract year than in a guaranteed "
        f"non-contract year (95% interval {f2(role['ci_lo'])} to {f2(role['ci_hi'])}; within-player "
        f"estimate {fe(role)}). Stars show no contract-year boost: {ci(star)}, within-player {fe(star)}. "
        f"Defining stars by All-NBA or All-Star honors instead gives {ci(hstar)}.\n")

    lines = ["", "| Tier | Contract-year seasons | Comparison seasons | Difference (95% interval) | Within-player estimate | Placebo spread |",
             "|---|---|---|---|---|---|"]
    for t in TIER_ORDER:
        r = row(H, tier=t)
        lines.append(f"| {TIER_NAME[t]} | {r['n_cy']:,} | {r['n_nc']:,} | {ci(r)} | {fe(r)} | {r['placebo_sd']:.2f} |")
    g["results"] = "\n".join(lines) + "\n"

    lines = ["", "| Specification | Role players | Stars |", "|---|---|---|"]
    lines.append(f"| Primary (strict definition, fitted expectation) | {ci(role)} | {ci(star)} |")
    for spec, label in (("broad", "Broad definition (any final contract season)"),
                        ("strict_high_conf", "High-confidence contract-year labels only")):
        lines.append(f"| {label} | {ci(row(sens, spec=spec, era=HEADLINE_ERA, tier='role'))} | "
                     f"{ci(row(sens, spec=spec, era=HEADLINE_ERA, tier='star'))} |")
    fh = fixed.filter(pl.col("era") == HEADLINE_ERA)
    lines.append(f"| Expectation with the pre-specified 1,000 regression minutes | {ci(row(fh, tier='role'))} | "
                 f"{ci(row(fh, tier='star'))} |")
    lines.append(f"| Stars defined by honors (All-NBA or All-Star in the prior two seasons) | n/a | {ci(hstar)} |")
    g["sensitivity"] = "\n".join(lines) + "\n"

    s = sec.filter(pl.col("era") == HEADLINE_ERA)
    sig = s.filter(pl.col("p_holm") < 0.05).sort("p_holm")
    outcome_name = {"mpg": "minutes per game", "games": "games played", "ts_pct": "true shooting",
                    "usg_pct": "usage", "ws_per_48": "win shares per 48", "per": "PER"}
    pfmt = lambda p: "below 0.01" if p < 0.01 else f"{p:.2f}"  # noqa: E731
    def amount(outcome: str, x: float) -> str:
        # TS% is stored as a fraction; show it in percentage points.
        if outcome == "ts_pct":
            return f"{f2(100 * x)} percentage points"
        if outcome == "ws_per_48":
            return f"{x:+.3f}".replace("-", "−")
        unit = {"games": " games", "mpg": " minutes per game", "usg_pct": " usage points", "per": " PER"}[outcome]
        return f"{f2(x)}{unit}"

    listed = "; ".join(f"{TIER_NAME[r['tier']].lower()}, {outcome_name[r['outcome']]} "
                       f"({amount(r['outcome'], r['diff'])} against the age-adjusted change, "
                       f"corrected p {pfmt(r['p_holm'])})"
                       for r in sig.iter_rows(named=True))
    g["secondary"] = (
        f"\nAcross {s['outcome'].n_unique()} secondary outcomes and {s['tier'].n_unique()} tier groups "
        f"(the four tiers plus all tiers together), {sig.height} contract-year differences stay below 0.05 "
        f"after a Holm correction within each group" + (f": {listed}.\n" if sig.height else ".\n"))

    P = post.filter(pl.col("era") == HEADLINE_ERA)
    rc, rn = row(P, tier="role", group="contract_year"), row(P, tier="role", group="comparison")
    sc = row(P, tier="star", group="contract_year")
    g["post"] = (
        f"\n{pct(1 - rc['share_played_next'])} of contract-year role players never played another NBA "
        f"season (stars: {pct(1 - sc['share_played_next'])}). Role players who did return landed at "
        f"{f2(rc['resid_next'])} against expectation the next season, against {f2(rn['resid_next'])} for "
        f"role players who had been in a guaranteed non-contract year.\n")

    pb, rb, nbf, nbc = precision_recall(val, "bender_2017_18", "2013-2026")
    pg1, rg1, _, _ = precision_recall(val, "gold_verified_or_single", "2013-2026")
    pg0, rg0, _, _ = precision_recall(val, "gold_verified_or_single", "2000-2012")
    g["labels"] = (
        "\n| Reference | Seasons labeled contract year that truly were | True contract years caught |\n"
        "|---|---|---|\n"
        f"| Patricia Bender's 2017-18 contracts snapshot | {pct(pb)} | {pct(rb)} |\n"
        f"| Gold set, 2012-13 to 2025-26 | {pct(pg1)} | {pct(rg1)} |\n"
        f"| Gold set, 1999-00 to 2011-12 | {pct(pg0)} | {pct(rg0)} |\n")

    matched = int(src["matched"].sum())
    rows_ = int(src["bbref_rows"].sum())
    gross = int(src["gross"].sum())
    rmin = int(row(scal, quantity="regression_minutes")["value"])
    g["data"] = (
        f"\n{matched:,} of {rows_:,} Basketball-Reference player-seasons have an independent "
        f"stats.nba.com counterpart, with {gross} wrong matches. The expectation shrinks prior "
        f"performance by {rmin:,} regression minutes, fit on non-contract seasons.\n")

    e89 = row(prim, era="1989-1999", tier="all")
    e77 = row(prim, era="1977-1988", tier="all")
    g["eras"] = (
        f"\nFor {era_label('1989-1999')} the all-tier difference is {ci(e89)}. For "
        f"{era_label('1977-1988')} only {e77['n_nc']} seasons qualify as guaranteed non-contract years, "
        f"too few for any conclusion. Neither era's labels could be validated against independent records.\n")
    return g


def render(text: str, gen: dict[str, str]) -> str:
    seen = set()

    def sub(m: re.Match) -> str:
        seen.add(m.group(2))
        if m.group(2) not in gen:
            raise SystemExit(f"README region gen:{m.group(2)} has no generator")
        return m.group(1) + gen[m.group(2)] + m.group(4)

    out = REGION.sub(sub, text)
    missing = set(gen) - seen
    if missing:
        raise SystemExit(f"README is missing regions: {sorted(missing)}")
    return out


def main() -> None:
    text = README.read_text()
    new = render(ABBR.sub(r"\1", text), build())
    if "--check" in sys.argv:
        if ABBR.sub(r"\1", text) != new:
            print("FINDINGS DRIFT: README.md differs from the generated regions; run python/13_findings.py")
            sys.exit(1)
        print("FINDINGS CHECK PASSED")
        return
    README.write_text(new)
    print("README regions regenerated")


if __name__ == "__main__":
    main()
