"""Explainer diagrams for the family page (docs/story.md), drawn with the
family's famdiagram (../basketball-analysis-tools/famdiagram.py) and saved to
figures/<ref>.svg plus a <ref>_narrow.svg phone layout. report_builder.py
inlines them so they follow the page theme.

Every number drawn is read from a committed output (or from the panel
script's own constants, for the expectation weights); none is typed here.
No diagram shows any player's contract status: the contract labels are
parsed from local sources and stay local (.gitignore).

Diagrams:
  dg1_expectation  how one real season is scored: a player's prior Box
                   Plus/Minus, the expectation pulled toward the league
                   average and adjusted for age, and the season's residual,
                   beside the naive change from the season before
                   (output/panel_python.csv, panel_scalars_python.csv,
                   aging_curve_python.csv; the name from data/crosswalk.csv
                   and data/nba_player_seasons.csv)
  dg2_study_map    which seasons feed which part of the study: the
                   expectation and the tier from the seasons before, the
                   test in season t, and the season after, with the
                   headline results at each step (output/panel_python.csv
                   for the tier cut points, effect_primary_python.csv,
                   effect_post_python.csv)
  dg3_labels       how a season gets its contract label and how often the
                   labels match the references, by era
                   (output/label_validation.csv, via 13_findings.py's
                   precision_recall)

Run:     python python/15_diagrams.py
--check: rebuild every SVG in memory and fail if a committed one differs.
"""
from __future__ import annotations

import argparse
import math
import importlib.util
import sys
import tempfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "basketball-analysis-tools"))
sys.path.insert(0, str(HERE))
import famdiagram as fd  # noqa: E402
from ctlib import season_label  # noqa: E402

ERA = "2000-2026"
# dg1's example: a text key into panel_python.csv (bbref id, season end
# year). Every number drawn for it is read from the panel.
EXAMPLE = ("randlju01", 2022)


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PANEL = _load("build_panel", "10_build_panel.py")      # WEIGHTS
FINDINGS = _load("findings", "13_findings.py")          # era_label, precision_recall


def sgn(v: float, d: int = 2) -> str:
    return f"{v:+.{d}f}".replace("-", "−")


def num(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}".replace("-", "−")


def pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def wrap(s: str, width: float, size: float) -> list[str]:
    """Greedy word wrap on an estimated glyph width."""
    per = size * 0.55
    out, cur = [], ""
    for w in s.split():
        t = f"{cur} {w}".strip()
        if len(t) * per > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def para(d: fd.Diagram, x, y, s, width, size, lh=None, **kw) -> float:
    """Wrapped text from baseline y; returns the baseline of the last line."""
    lh = lh or size * 1.35
    lines = wrap(s, width, size)
    for i, line in enumerate(lines):
        d.text(x, y + i * lh, line, size=size, **kw)
    return y + (len(lines) - 1) * lh


def arrow(d: fd.Diagram, x1, y1, x2, y2, stroke="ink3", sw=1.5) -> None:
    """A line with a drawn arrowhead. famdiagram's marker arrows share one
    id, and on phones the first SVG holding it is display:none, so the
    marker does not render; a drawn triangle always does."""
    ang = math.atan2(y2 - y1, x2 - x1)
    hl, hw = 9, 5
    bx, by = x2 - hl * math.cos(ang), y2 - hl * math.sin(ang)
    d.line(x1, y1, bx, by, stroke=stroke, sw=sw)
    px, py = -math.sin(ang) * hw, math.cos(ang) * hw
    d.path(f"M{x2:.1f},{y2:.1f} L{bx + px:.1f},{by + py:.1f} L{bx - px:.1f},{by - py:.1f} Z",
           fill=stroke, stroke=None)


def one(df: pl.DataFrame, **keys) -> dict:
    for k, v in keys.items():
        df = df.filter(pl.col(k) == v)
    if df.height != 1:
        raise SystemExit(f"expected one row for {keys}, found {df.height}")
    return df.row(0, named=True)


# ---------------------------------------------------------------- dg1
def example_rows() -> dict:
    p = pl.read_csv(OUT / "panel_python.csv")
    pid, season = EXAMPLE
    me = p.filter(pl.col("bbref_id") == pid).with_columns(
        (pl.col("exp_bpm") + pl.col("resid_bpm")).alias("bpm"))
    cur = one(me, season=season)
    priors = []
    for k in sorted(PANEL.WEIGHTS, reverse=True):
        r = one(me, season=season - k)
        if r["bpm"] is None:
            raise SystemExit(f"{pid} {season - k}: no BPM recoverable from the panel")
        priors.append((season - k, PANEL.WEIGHTS[k], round(r["bpm"], 1)))
    curve = pl.read_csv(OUT / "aging_curve_python.csv")
    age = curve.filter((pl.col("age_adj") - cur["age_adj"]).abs() < 1e-12)
    if age.height != 1:
        raise SystemExit("age adjustment does not identify one age bin")
    cw = pl.read_csv(ROOT / "data" / "crosswalk.csv")
    nba_id = one(cw, bbref_id=pid)["nba_id"]
    names = pl.read_csv(ROOT / "data" / "nba_player_seasons.csv")
    name = one(names, nba_id=nba_id, season=season)["name"]
    rm = one(pl.read_csv(OUT / "panel_scalars_python.csv"), quantity="regression_minutes")["value"]
    return {"name": name, "season": season, "priors": priors, "raw": cur["exp_bpm_raw"],
            "age_adj": cur["age_adj"], "age": int(age["age_bin"][0]), "exp": cur["exp_bpm"],
            "bpm": round(cur["bpm"], 1), "resid": cur["resid_bpm"], "reg_min": int(rm)}


def expectation(narrow: bool) -> fd.Diagram:
    e = example_rows()
    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (15, 14, 20)
    pad = 12
    d = fd.Diagram(W, 10, f"How one season is scored: {e['name']}, {season_label(e['season'])}")
    y = 28
    y = para(d, pad, y, f"Scoring one season: {e['name']}, {season_label(e['season'])}",
             W - 2 * pad, head, display=True, weight="600")

    # ---- plot: prior seasons, the expectation, and the season itself
    px0 = pad + 34
    pw = (W - px0 - pad) if narrow else 420
    ptop = y + 44
    ph = 250 if narrow else 270
    vals = [b for _, _, b in e["priors"]] + [e["bpm"], e["exp"], e["raw"], 0.0]
    lo, hi = min(vals) - 0.6, max(vals) + 0.6
    yof = lambda v: ptop + ph * (hi - v) / (hi - lo)  # noqa: E731
    # prior seasons share 62% of the width; the season column gets the
    # rest, room for its labels
    step = pw * 0.62 / len(e["priors"])
    xof = lambda i: (px0 + step * (i + 0.5) if i < len(e["priors"])  # noqa: E731
                     else px0 + pw * 0.62 + 34)
    d.rect(px0, ptop, pw, ph, fill="surface2", rx=6)
    # league average
    d.line(px0, yof(0), px0 + pw, yof(0), stroke="ink3", sw=1, dash="4 4")
    d.text(px0 + 6, yof(0) - 6, "league average (0)", size=small, fill="ink3")
    # y ticks: whole BPM values inside the range
    for t in range(math.ceil(lo), math.floor(hi) + 1):
        d.text(px0 - 6, yof(t) + 4, num(t, 0), size=small, fill="ink3", anchor="end")
    d.text(pad, ptop - 8, "BPM", size=small, fill="ink2")
    # prior seasons
    for i, (s, w, b) in enumerate(e["priors"]):
        x = xof(i)
        d.circle(x, yof(b), 7, fill="ink2")
        # the newest prior's label goes left of its dot: the naive-change
        # guides leave it to the right, and a label there sat on them
        newest = i == len(e["priors"]) - 1
        d.text(x - 11 if newest else x + 11, yof(b) + 5, num(b), size=small, fill="ink2",
               weight="600", anchor="end" if newest else "start")
        d.text(x, ptop + ph + 18, season_label(s), size=small, fill="ink2", anchor="middle")
        d.text(x, ptop + ph + 18 + small * 1.3, f"weight {w:.1f}", size=small, fill="ink3",
               anchor="middle")
    # the season itself
    i = len(e["priors"])
    x = xof(i)
    d.text(x, ptop + ph + 18, season_label(e["season"]), size=small, fill="ink", anchor="middle",
           weight="700")
    d.text(x, ptop + ph + 18 + small * 1.3, "the season", size=small, fill="ink3", anchor="middle")
    last = e["priors"][-1][2]
    # naive change from last season (ink3, dashed)
    xn = x - 64
    d.line(xof(i - 1) + 10, yof(last), xn, yof(last), stroke="ink3", sw=1, dash="2 3")
    d.line(xn, yof(last), xn, yof(e["bpm"]), stroke="ink3", sw=2, dash="3 3")
    # expectation tick and residual
    d.line(x - 18, yof(e["exp"]), x + 18, yof(e["exp"]), stroke="nba", sw=3)
    d.line(x, yof(e["exp"]), x, yof(e["bpm"]), stroke="c8", sw=3)
    d.circle(x, yof(e["bpm"]), 7, fill="nba")
    d.text(x + 22, yof(e["exp"]) - 4, "expected", size=small, fill="nba", weight="700")
    d.text(x + 22, yof(e["exp"]) - 4 + small * 1.25, sgn(e["exp"]), size=small, fill="nba",
           weight="700")
    d.text(x + 14, yof(e["bpm"]) + 5, f"actual {num(e['bpm'])}", size=small, fill="ink",
           weight="700")
    d.text(x - 8, (yof(e["exp"]) + yof(e["bpm"])) / 2 + 4, sgn(e["resid"]), size=small,
           fill="c8", anchor="end", weight="700")
    d.text(xn - 6, yof(last) + (yof(e["bpm"]) - yof(last)) * 0.3 + 4, sgn(e["bpm"] - last, 1),
           size=small,
           fill="ink3", anchor="end", weight="600")
    y_plot_end = ptop + ph + 18 + small * 1.3

    # ---- the arithmetic
    if narrow:
        ax, ay, aw = pad, y_plot_end + 22, W - 2 * pad
    else:
        ax, ay, aw = px0 + pw + 22, ptop, W - (px0 + pw + 22) - pad
    tx, tw = ax + 12, aw - 24
    lines = [
        ("1", f"Weight the three prior seasons by recency "
              f"({', '.join(f'{w:.1f}' for _, w, _ in e['priors'])}, oldest to newest) "
              f"and by minutes."),
        ("2", f"Pull that toward the league average by adding {e['reg_min']:,} minutes of an "
              f"average season: {sgn(e['raw'])}."),
        ("3", f"Add the league's typical change at age {e['age']}: {sgn(e['age_adj'])}. "
              f"Expected: {sgn(e['exp'])}."),
        ("4", f"Actual minus expected: {num(e['bpm'])} − {num(e['exp'], 2)} = {sgn(e['resid'])}. "
              f"This residual is what the study compares."),
    ]
    yy = ay + 22
    blocks = []
    for k, s in lines:
        n = len(wrap(s, tw - 24, fs))
        blocks.append((k, s, n))
    ah = 22 + sum(n * fs * 1.35 + 12 for _, _, n in blocks) + 4
    d.rect(ax, ay, aw, ah, fill="surface2", stroke="rule", rx=8)
    for k, s, n in blocks:
        d.circle(tx + 8, yy - 5, 10, fill="nba" if k == "4" else "ink3")
        d.text(tx + 8, yy, k, size=small, fill="surface", anchor="middle", weight="700")
        para(d, tx + 24, yy, s, tw - 24, fs, fill="ink" if k == "4" else "ink2",
             weight="600" if k == "4" else None)
        yy += n * fs * 1.35 + 12
    y = max(y_plot_end, ay + ah) + 30
    last_y = para(d, pad, y, f"The naive change from the season before ({sgn(e['bpm'] - last, 1)}) "
                  f"mixes in regression to the mean: a player's best season is usually followed by a "
                  f"lower one. Against the expectation the drop is {sgn(e['resid'])}.",
                  W - 2 * pad, fs, fill="ink2")
    d.h = last_y + 14
    return d


# ---------------------------------------------------------------- dg2
def study_map(narrow: bool) -> fd.Diagram:
    p = pl.read_csv(OUT / "panel_python.csv")
    cuts = {t: round(p.filter(pl.col("tier") == t)["vorp_pct"].min(), 2)
            for t in ("star", "starter", "role")}
    shares = [("Stars", 1 - cuts["star"], "c4", 1.0),
              ("Starters", cuts["star"] - cuts["starter"], "c4", 0.45),
              ("Role players", cuts["starter"] - cuts["role"], "c3", 1.0),
              ("Fringe players", cuts["role"], "ink3", 0.6)]
    where = {"Stars": "top", "Starters": "next", "Role players": "middle",
             "Fringe players": "bottom"}
    prim = pl.read_csv(OUT / "effect_primary_python.csv")
    post = pl.read_csv(OUT / "effect_post_python.csv")
    allr = one(prim, era=ERA, tier="all")
    role, star = one(prim, era=ERA, tier="role"), one(prim, era=ERA, tier="star")
    pr_cy = one(post, era=ERA, tier="role", group="contract_year")
    pr_nc = one(post, era=ERA, tier="role", group="comparison")
    ps_cy = one(post, era=ERA, tier="star", group="contract_year")
    weights = ", ".join(f"{PANEL.WEIGHTS[k]:.1f}" for k in sorted(PANEL.WEIGHTS, reverse=True))
    rm = int(one(pl.read_csv(OUT / "panel_scalars_python.csv"), quantity="regression_minutes")["value"])

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 16) if narrow else (14, 14, 18)
    pad = 12
    gap = 26
    d = fd.Diagram(W, 10, "Which seasons feed which part of the study")
    bw = W - 2 * pad if narrow else (W - 2 * pad - 2 * gap) / 3
    tw = bw - 24

    def block(x, y, title, sub, color, body) -> float:
        """Draw a stage block; body(x, y, width) draws inside and returns its end y."""
        d.rect(x, y, bw, 6, fill=color, rx=3)
        d.text(x + 12, y + 30, title, size=head, display=True, weight="600", fill="ink")
        d.text(x + 12, y + 30 + small * 1.4, sub, size=small, fill="ink3")
        end = body(x + 12, y + 30 + small * 1.4 + 26, tw)
        return end

    def before(x, y, w):
        d.text(x, y, "Expected BPM", size=fs, weight="700", fill="ink")
        y = para(d, x, y + fs * 1.4, f"Prior seasons weighted {weights} (oldest to newest) and "
                 f"by minutes, pulled toward average by {rm:,} minutes, plus the age adjustment.",
                 w, small, fill="ink2")
        y += 30
        d.text(x, y, "Tier", size=fs, weight="700", fill="ink")
        y = para(d, x, y + fs * 1.4, "Value over the two seasons before, ranked within the "
                 "season:", w, small, fill="ink2")
        y += 12
        bx = x
        for lab, sh, col, op in shares:
            bwid = w * sh
            d.rect(bx, y, bwid - 2, 18, fill=col, rx=2, opacity=op)
            bx += bwid
        y += 18 + 8
        for lab, sh, col, op in shares:
            y += small * 1.45
            d.rect(x, y - small + 1, 12, 12, fill=col, rx=2, opacity=op)
            d.text(x + 18, y, f"{lab}: {where[lab]} {pct(sh)}", size=small, fill="ink",
                   weight="600" if lab == "Role players" else None)
        return y

    def during(x, y, w):
        for lab, n, desc in (("Contract year", allr["n_cy"], "last season of a deal, the next "
                              "not yet secured"),
                             ("Guaranteed year", allr["n_nc"], "the deal was certain to "
                              "continue")):
            d.text(x, y, f"{lab}: {n:,}", size=fs, weight="700", fill="ink")
            y = para(d, x, y + fs * 1.4, desc, w, small, fill="ink2") + 26
        d.text(x, y, "The comparison", size=fs, weight="700", fill="ink")
        y = para(d, x, y + fs * 1.4, "Residual (actual minus expected BPM), contract year "
                 "minus guaranteed year:", w, small, fill="ink2") + 28
        for lab, r, col in (("Role players", role, "c3"), ("Stars", star, "c4")):
            d.rect(x, y - 16, w, 26, fill=col, rx=13, opacity=0.9)
            d.text(x + w / 2, y + 2, f"{lab} {sgn(r['diff'])}", size=fs, fill="surface",
                   anchor="middle", weight="700")
            y += 34
        return y - 34 + 10

    def after(x, y, w):
        d.text(x, y, "Did they play again?", size=fs, weight="700", fill="ink")
        y = para(d, x, y + fs * 1.4, f"{pct(1 - pr_cy['share_played_next'])} of contract-year role "
                 f"players never played another NBA season (stars: "
                 f"{pct(1 - ps_cy['share_played_next'])}).", w, small, fill="ink2") + 30
        d.text(x, y, "Returners, next season", size=fs, weight="700", fill="ink")
        y = para(d, x, y + fs * 1.4, "Role players against expectation:", w, small,
                 fill="ink2") + 24
        for lab, r, col in (("after a contract year", pr_cy, "c3"),
                            ("after a guaranteed year", pr_nc, "ink3")):
            d.text(x, y, sgn(r["resid_next"]), size=fs + 2, weight="700", fill=col)
            d.text(x + 52, y, lab, size=small, fill="ink2")
            y += fs * 1.6
        return y - fs * 1.6

    stages = [("Seasons before", "t−3 to t−1", "ink3", before),
              ("The season", "t: the test", "nba", during),
              ("The season after", "t+1", "ink3", after)]
    y0 = 14
    if narrow:
        y = y0
        for i, (t, s, c, fn) in enumerate(stages):
            end = block(pad, y, t, s, c, fn)
            if i < 2:
                arrow(d, W / 2, end + 14, W / 2, end + 40)
            y = end + 52
        d.h = y - 16
    else:
        # the season timeline the three stages sit on
        y0 = 70
        ay = 30
        d.line(pad, ay, W - pad, ay, stroke="ink3", sw=1.5)
        ticks = [(pad + bw * (k + 0.5) / 3, lab) for k, lab in enumerate(("t−3", "t−2", "t−1"))]
        ticks += [(pad + bw + gap + bw / 2, "t"), (pad + 2 * (bw + gap) + bw / 2, "t+1")]
        for tx_, lab in ticks:
            big = lab == "t"
            d.circle(tx_, ay, 7 if big else 5, fill="nba" if big else "ink3")
            d.text(tx_, ay - 14, lab, size=small, fill="nba" if big else "ink2",
                   anchor="middle", weight="700" if big else None)
            d.line(tx_, ay + 8, tx_, y0 - 6, stroke="rule", sw=1, dash="2 3")
        ends = []
        for i, (t, s, c, fn) in enumerate(stages):
            x = pad + i * (bw + gap)
            ends.append(block(x, y0, t, s, c, fn))
            if i < 2:
                arrow(d, x + bw + 4, y0 + 26, x + bw + gap - 4, y0 + 26)
        d.h = max(ends) + 18
    return d


# ---------------------------------------------------------------- dg3
def labels(narrow: bool) -> fd.Diagram:
    v = pl.read_csv(OUT / "label_validation.csv")
    refs = [("gold_verified_or_single", "2013-2026", "Gold set"),
            ("gold_verified_or_single", "2000-2012", "Gold set"),
            ("bender_2017_18", "2013-2026", "Bender's snapshot")]
    rows = []
    for ref, era, name in refs:
        r = one(v, labeler="bbref_wiki", reference=ref, era=era, truth="final")
        prec, _, _, _ = FINDINGS.precision_recall(v, ref, era)
        when = (FINDINGS.era_label(era) if ref.startswith("gold") else "2017-18")
        rows.append((f"{name}, {when}", r, prec))

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (15, 14, 20)
    pad = 12
    d = fd.Diagram(W, 10, "How a season gets its contract label, and how often the label is right")
    y = 28
    d.text(pad, y, "1. Read the signals for each season", size=head, display=True, weight="600")
    y += 16
    signals = ["Signing and extension events", "Team moves", "The rookie-scale schedule",
               "Departures from the league", "Wikipedia's free-agent tables"]
    outs = [("Contract year", "last season of a deal, next not yet secured", "nba"),
            ("Guaranteed year", "deal certain to continue", "ink2"),
            ("Unknown", "left out of both groups", "ink3")]
    if narrow:
        sx, sw_ = pad, W - 2 * pad
    else:
        sx, sw_ = pad, 300
    sh = 14 + len(signals) * (fs * 1.5) + 4
    d.rect(sx, y, sw_, sh, fill="surface2", stroke="rule", rx=8)
    for i, s in enumerate(signals):
        d.circle(sx + 16, y + 20 + i * fs * 1.5 - 4, 3, fill="ink3")
        d.text(sx + 26, y + 20 + i * fs * 1.5, s, size=fs, fill="ink")
    if narrow:
        arrow(d, W / 2, y + sh + 6, W / 2, y + sh + 30)
        oy, ox, ow = y + sh + 40, pad, W - 2 * pad
    else:
        ox = sx + sw_ + 60
        ow = W - ox - pad
        oy = y
        arrow(d, sx + sw_ + 8, y + sh / 2, ox - 8, y + sh / 2)
    oh = (sh - 2 * 8) / 3 if not narrow else 48
    for i, (lab, desc, col) in enumerate(outs):
        by = oy + i * (oh + 8)
        d.rect(ox, by, 6, oh, fill=col, rx=2)
        d.text(ox + 16, by + oh / 2 - 3, lab, size=fs, fill="ink", weight="700")
        d.text(ox + 16, by + oh / 2 + small + 1, desc, size=small, fill="ink2")
    y = max(y + sh, oy + 3 * oh + 16) + 40

    y = para(d, pad, y, "2. Check the labels against references", W - 2 * pad, head,
             display=True, weight="600")
    y = para(d, pad, y + 26, "Each dot is 1% of the seasons a reference knows were "
             "contract years, colored by what the labeler called them:", W - 2 * pad, fs,
             fill="ink2")
    y += 26
    keys = (("labeled_final", "called contract year", "nba", 1.0),
            ("labeled_unknown", "unknown (left out)", "ink3", 0.4),
            ("labeled_continues", "called guaranteed", "c8", 1.0))
    lx = pad
    for _, lab, col, op in keys:
        if lx + 18 + len(lab) * small * 0.5 > W - pad:
            lx, y = pad, y + small * 1.6
        d.circle(lx + 6, y - 4, 6, fill=col, opacity=op)
        d.text(lx + 18, y, lab, size=small, fill="ink2")
        lx += 18 + len(lab) * small * 0.5 + 18
    y += 26
    # one unit array of 100 dots per reference
    gap = 22
    aw = W - 2 * pad if narrow else (W - 2 * pad - 2 * gap) / 3
    cols, nrows = 20, 5
    step = aw / cols
    rad = step * 0.36
    ends = []
    for i, (lab, r, prec) in enumerate(rows):
        shares = [r[k] for k, *_ in keys]
        # whole percents, rounded half up; the unknown share absorbs any
        # rounding so the 100 dots and the printed percents agree exactly
        counts = [math.floor(v * 100 + 0.5) for v in shares]
        counts[1] = 100 - counts[0] - counts[2]
        colors = [c for (_, _, col, op), n in zip(keys, counts) for c in [(col, op)] * n]
        ax = pad if narrow else pad + i * (aw + gap)
        ay = y if not narrow else (ends[-1] + 30 if ends else y)
        d.text(ax, ay, lab, size=small, fill="ink", weight="700")
        gy = ay + 14
        for n, (col, op) in enumerate(colors):
            cx = ax + (n % cols + 0.5) * step
            cy = gy + (n // cols + 0.5) * step
            d.circle(cx, cy, rad, fill=col, opacity=op)
        ty = para(d, ax, gy + nrows * step + small + 6, f"{counts[0]}% called contract year, "
                  f"{counts[1]}% unknown, {counts[2]}% called guaranteed", aw, small, fill="ink2")
        ty = para(d, ax, ty + small * 1.45, f"{pct(prec)} of its contract-year labels were right",
                  aw, small, fill="ink2", weight="600")
        ends.append(ty)
    y = max(ends) + 22
    y += 10
    last = para(d, pad, y, "A wrong label puts a season in the other group, which pulls the two "
                "groups' averages together. Label errors shrink a real gap toward zero; they "
                "rarely create one.", W - 2 * pad, fs, fill="ink2")
    d.h = last + 14
    return d


DIAGRAMS = {"dg1_expectation": expectation, "dg2_study_map": study_map, "dg3_labels": labels}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        fails = []
        with tempfile.TemporaryDirectory() as tmp:
            for ref, fn in DIAGRAMS.items():
                for p in fd.save(Path(tmp), ref, fn(False), fn(True)):
                    old = FIG / p.name
                    if not old.exists() or old.read_text() != p.read_text():
                        fails.append(p.name)
        for f in fails:
            print("FAIL", f, "differs from a fresh build")
        print("DIAGRAMS", "FAILED" if fails else
              f"PASSED: {len(DIAGRAMS)} diagrams rebuild identically")
        return 1 if fails else 0
    for ref, fn in DIAGRAMS.items():
        for p in fd.save(FIG, ref, fn(False), fn(True)):
            print("wrote", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
