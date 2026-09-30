"""Label every player-season's contract status from independent signals.

Inputs: data/bbref_player_seasons.csv (who played when, for which teams),
data/player_salaries.csv, data/player_events.csv, data/player_draft.csv,
data/player_contract_now.csv (all from 06_parse_players.py).

For a season t the player played, the question is whether his contract
ended after t, and if so whether his next deal was already secured before
t began. Evidence that the contract ended after t:

  sign     a signing event (free agent, multi-year, re-signed, other; not
           10-day, two-way, or Exhibit 10) dated in league year t+1
  move     a different team in t+1 with no trade or waiver claim between
  salary   a break in the fixed-raise salary path at t+1 (see
           ctlib.raise_breaks); only where both salaries are usable
  rookie   the scheduled final season of a first-round rookie-scale deal
  exit     no NBA season t+1 (t+1 <= last harvested season)

Evidence that the contract continues into t+1 (a "guaranteed non-contract
year", Ryan 2015): an unbroken salary path at t+1 with no end signal, or
an inside-the-rookie-deal season, or a current-contract table listing t+1
(for the latest season only).

Secured: an extension event dated before season t began, whose extension
starts at t+1, means the next deal was secured (Garnett 1997, Adebayo 2020).
An extension dated during season t is "secured_midseason".

Terminated: waived or released during season t (the deal did not expire).

Labels per player-season:
  status      final / continues / unknown
  cy_broad    final and not terminated (any final contract season)
  cy_strict   cy_broad and not secured before or during t
  nc_strict   status == continues (the strict comparison group)
  confidence  high (an event, move, or rookie rule), medium (salary only),
              low (exit only, or nothing)
Options cannot be observed before the 2017-18 Bender snapshot, so the
strict definition here excludes pre-secured seasons but not option years;
the gold set measures how much that matters.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import norm, raise_breaks, rookie_scale_seasons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LAST_SEASON = 2026
SIGN_KINDS = {"signed_fa", "signed_multi", "signed_other", "resigned", "rest_of_season", "converted"}
FRINGE_KINDS = {"ten_day", "two_way", "exhibit10"}
# Imputed salaries: "Minimum salaries were given to all players without
# salary data in 1988-89, and 1990-91 through 2004-05" (BBRef about/salary).
IMPUTED_SEASONS = {1989} | set(range(1991, 2006))
# Regular-season opening days that fell far from late October.
OPENERS = {1999: date(1999, 2, 5), 2012: date(2011, 12, 25), 2021: date(2020, 12, 22)}


def draft_year_plus_one(draft: dict | None) -> int | None:
    """A rookie's first season: his rookie-scale signing is not an extension."""
    return draft["draft_year"] + 1 if draft else None


def opener(season: int) -> date:
    return OPENERS.get(season, date(season - 1, 10, 25))


def usable_salaries(sal: pl.DataFrame) -> pl.DataFrame:
    """One salary per player-season (the first listed row, the contract
    carried into the season) plus a usability flag. In the imputed seasons a
    salary is unusable when it sits at that season's modal minimum value."""
    first = sal.sort("bbref_id", "season", "row").group_by("bbref_id", "season", maintain_order=True).agg(
        pl.col("salary").first(), pl.col("team").first().alias("sal_team"),
        pl.len().alias("sal_rows"))
    # The imputed value is the most frequent salary within each season's
    # bottom decile (a plain mode picks up any common veteran figure).
    low = first.filter(pl.col("season").is_in(list(IMPUTED_SEASONS)) & pl.col("salary").is_not_null())
    low = low.filter(pl.col("salary") <= pl.col("salary").quantile(0.10).over("season"))
    floor = (low.group_by("season", "salary").len()
             .sort("season", "len", descending=[False, True])
             .group_by("season", maintain_order=True).first()
             .select("season", pl.col("salary").alias("modal_min")))
    first = first.join(floor, on="season", how="left").with_columns(
        (pl.col("salary").is_not_null()
         & ~(pl.col("season").is_in(list(IMPUTED_SEASONS)) & (pl.col("salary") <= pl.col("modal_min"))))
        .alias("sal_usable"))
    return first


def label_player(pid: str, seasons: list[dict], sal: dict[int, dict], events: list[dict],
                 draft: dict | None, future: dict[int, int | None],
                 wiki_next: set[int] | None = None) -> list[dict]:
    played = [s["season"] for s in seasons]
    teams = {s["season"]: s["teams"] for s in seasons}

    rookie_final = None
    rookie_seasons: set[int] = set()
    if draft:
        length = rookie_scale_seasons(draft["draft_year"], draft["round"])
        if length:
            rookie_seasons = set(range(draft["draft_year"] + 1, draft["draft_year"] + 1 + length))
            rookie_final = draft["draft_year"] + length

    # Salary path over consecutive played seasons. Rookie-scale salaries
    # follow the scale schedule, not fixed raises (the fourth-year option
    # jumps), so they are left out of the break test; the rookie rule
    # supplies that deal's end instead.
    # Future seasons from the current-contract table extend the path, so an
    # extension already signed for 2026-27 shows as a break after 2025-26.
    path = played + ([s for s in sorted(future) if s > LAST_SEASON] if played and played[-1] == LAST_SEASON else [])
    # A season in which he was waived or released carries a prorated or
    # partial salary (Alex Abrines 2018-19), so it cannot anchor the path.
    cut_in = {e["league_year"] for e in events if e["kind"] in {"waived", "released"}
              and e["date"] >= opener(e["league_year"]).isoformat()}
    s_vals = [sal.get(t, {}).get("salary") if t <= LAST_SEASON else future[t] for t in path]
    s_ok = [(bool(sal.get(t, {}).get("sal_usable")) if t <= LAST_SEASON else future[t] is not None)
            and t not in rookie_seasons and t not in cut_in for t in path]
    breaks = raise_breaks(s_vals, s_ok)
    brk = {path[i]: breaks[i] for i in range(len(path))}
    consecutive = {played[i]: (i + 1 < len(played) and played[i + 1] == played[i] + 1) for i in range(len(played))}

    # Basketball-Reference often logs an extension as "Signed a multi-year
    # contract" (LaMarcus Aldridge, October 16, 2017). A signing with the
    # team already holding his contract, in a league year his current deal
    # still covers (a rookie-scale season other than the last, or an
    # unbroken salary path), is an extension, not the start of a new deal.
    events = [dict(e) for e in events]
    for e in events:
        L = e["league_year"]
        if e["kind"] not in SIGN_KINDS or L not in brk:
            continue
        holder = (sal.get(L, {}).get("sal_team") or "").lower()
        same_team = bool(holder) and holder == e["team"].lower()
        still_covered = (L in rookie_seasons and L != draft_year_plus_one(draft)) or brk.get(L) is False
        if same_team and still_covered:
            e["kind"] = "extension"

    # Each extension secures exactly one season: the final season f of the
    # contract it extends. f is the first played season >= the extension's
    # league year that the salary path or the rookie schedule shows ending
    # (a break at f+1), looking at most two seasons ahead; otherwise the
    # extension's own league year.
    secured_at: dict[int, str] = {}
    for e in events:
        if e["kind"] != "extension":
            continue
        L, d = e["league_year"], date.fromisoformat(e["date"])
        f = next((s for s in (L, L + 1, L + 2)
                  if s in brk and ((s + 1) in brk and brk[s + 1] is True or s == rookie_final)), L)
        kind = "before" if d < opener(f) else "midseason"
        if secured_at.get(f) != "before":
            secured_at[f] = kind

    out = []
    for t in played:
        ev_next = [e for e in events if e["league_year"] == t + 1]
        ev_t = [e for e in events if e["league_year"] == t]
        sig = []
        # A signing in league year t+1 ends the deal that ran through t when
        # it happens in the offseason, or in-season without a waiver or
        # release earlier that league year (Aldridge's March 2021 Nets deal
        # followed his Spurs waiver, so it says nothing about 2019-20).
        cut = [e["date"] for e in ev_next if e["kind"] in {"waived", "released"}]
        if any(e["kind"] in SIGN_KINDS
               and (e["date"] < opener(t + 1).isoformat() or not any(c < e["date"] for c in cut))
               for e in ev_next):
            sig.append("sign")
        nxt = t + 1
        if nxt in teams:
            moved = teams[t].split("|")[-1] != teams[nxt].split("|")[0]
            traded = any(e["kind"] in {"traded", "claimed"} for e in ev_next) or \
                any(e["kind"] in {"traded", "claimed"} and e["date"] >= opener(t).isoformat() for e in ev_t)
            if moved and not traded:
                sig.append("move")
            if consecutive[t] and brk.get(nxt) is True:
                sig.append("salary")
        elif nxt <= LAST_SEASON:
            sig.append("exit")
        if rookie_final == t:
            sig.append("rookie")
        if wiki_next and t in wiki_next:
            sig.append("wiki")

        secured = secured_at.get(t)
        # Cut during t: the deal was terminated, not run out.
        terminated = t in cut_in
        # Cut between t and t+1's opener: his deal still covered t+1 when he
        # was let go (Carmelo Anthony, waived July 30, 2018 with 2018-19 left;
        # Omer Asik, waived October 21, 2018). Not an expiry, and not a clean
        # continuation either, so the season is left out of both groups.
        # Only a cut before any new signing that league year counts; a July
        # signing followed by an October cut ends the new deal, not the old.
        first_sign = min((e["date"] for e in ev_next if e["kind"] in SIGN_KINDS | FRINGE_KINDS), default="9999")
        cut_offseason = any(e["kind"] in {"waived", "released"} and e["date"] < opener(t + 1).isoformat()
                            and e["date"] < first_sign for e in ev_next)
        continues_ev = (
            (consecutive[t] and brk.get(nxt) is False and not {"sign", "move", "rookie", "wiki"} & set(sig))
            or (t in rookie_seasons and t != rookie_final and not {"sign", "wiki"} & set(sig))
            or (t == LAST_SEASON and (t + 1) in future and brk.get(t + 1) is not True)
        )
        # Amendment 2 (docs/design.md): a salary break alone does not make a
        # season final. On the full data it produced most false finals (48 of
        # about 70 against Bender and the gold set); it still counts toward
        # confidence when another signal agrees.
        final_ev = bool({"sign", "move", "rookie", "exit", "wiki"} & set(sig))
        if final_ev and not continues_ev:
            status = "final"
        elif continues_ev and not final_ev:
            status = "continues"
        elif final_ev and continues_ev:
            status = "unknown"  # conflicting signals
        else:
            status = "unknown"
        # An extension signed before t and kicking in at t+1 makes the
        # contract's last season t, even without other end signals.
        if secured == "before" and status == "unknown":
            status = "final"
        if cut_offseason and status != "continues" and "rookie" not in sig:
            status = "unknown"
        conf = ("high" if {"sign", "move", "rookie", "wiki"} & set(sig)
                else "medium" if "salary" in sig else "low")
        cy_broad = status == "final" and not terminated
        out.append({
            "bbref_id": pid, "season": t, "status": status, "signals": "|".join(sig),
            "secured": secured or "", "terminated": terminated, "cut_offseason": cut_offseason,
            "cy_broad": cy_broad, "cy_strict": cy_broad and secured is None,
            "nc_strict": status == "continues" and not terminated,
            "confidence": conf, "rookie_deal": t in rookie_seasons,
            "salary": sal.get(t, {}).get("salary"), "sal_usable": bool(sal.get(t, {}).get("sal_usable")),
        })
    return out


def wiki_endings(d: Path) -> dict[str, set[int]]:
    """bbref_id -> seasons t after which Wikipedia lists an offseason (or
    undated) signing from an NBA team, on the page for season t+1. Names are
    matched only where unique among players who played season t."""
    w = pl.read_csv(d / "wiki_signings.csv", infer_schema_length=None)
    teams = set(pl.read_csv(d / "player_salaries.csv")["team"].unique().to_list())
    w = w.filter(pl.col("former_team").is_in(list(teams))
                 & (pl.col("date").is_null() | (pl.col("date").str.slice(5, 2).cast(pl.Int64) >= 7)))
    p = pl.read_csv(d / "bbref_player_seasons.csv", infer_schema_length=None).select(
        "season", "bbref_id", pl.col("name").map_elements(norm, return_dtype=pl.String).alias("key"))
    p = p.filter(pl.len().over("season", "key") == 1)
    m = w.with_columns((pl.col("page_season") - 1).alias("season")).join(p, on=["season", "key"])
    out: dict[str, set[int]] = {}
    for pid, t in m.select("bbref_id", "season").unique().iter_rows():
        out.setdefault(pid, set()).add(t)
    return out


def main() -> None:
    use_wiki = "--bbref-only" not in sys.argv
    d = ROOT / "data"
    wiki = wiki_endings(d) if use_wiki else {}
    seasons = pl.read_csv(d / "bbref_player_seasons.csv", infer_schema_length=None).select(
        "bbref_id", "season", "teams", "n_teams")
    sal = usable_salaries(pl.read_csv(d / "player_salaries.csv"))
    ev = pl.read_csv(d / "player_events.csv", infer_schema_length=None)
    dr = pl.read_csv(d / "player_draft.csv")
    now = pl.read_csv(d / "player_contract_now.csv")
    have = set(ev["bbref_id"].unique().to_list()) | set(sal["bbref_id"].unique().to_list())

    sal_by = {}
    for r in sal.iter_rows(named=True):
        sal_by.setdefault(r["bbref_id"], {})[r["season"]] = r
    ev_by = {}
    for r in ev.iter_rows(named=True):
        ev_by.setdefault(r["bbref_id"], []).append(r)
    dr_by = {r["bbref_id"]: r for r in dr.iter_rows(named=True)}
    fut_by = {}
    for r in now.iter_rows(named=True):
        fut_by.setdefault(r["bbref_id"], {})[r["season"]] = r["salary"]

    rows = []
    for pid, g in seasons.sort("season").group_by("bbref_id", maintain_order=True):
        pid = pid[0]
        if pid not in have:
            continue  # player page not harvested yet
        # Solo "teams" for a single-team season is empty; fill from salary.
        ss = [dict(r, teams=r["teams"] or (sal_by.get(pid, {}).get(r["season"], {}).get("sal_team") or ""))
              for r in g.iter_rows(named=True)]
        rows += label_player(pid, ss, sal_by.get(pid, {}), ev_by.get(pid, []), dr_by.get(pid),
                             fut_by.get(pid, {}), wiki.get(pid))
    lab = pl.DataFrame(rows, infer_schema_length=None)
    # contract_labels.csv (Basketball-Reference + Wikipedia) feeds the
    # analysis; contract_labels_bbref.csv exists so Wikipedia can score a
    # labeler that never read it.
    lab.write_csv(d / ("contract_labels.csv" if use_wiki else "contract_labels_bbref.csv"))
    print(f"{lab.height} player-seasons labeled for {lab['bbref_id'].n_unique()} players")
    print(lab.group_by("status", "confidence").len().sort("status", "confidence"))
    print("cy_strict", lab["cy_strict"].sum(), "cy_broad", lab["cy_broad"].sum(), "nc_strict", lab["nc_strict"].sum())


if __name__ == "__main__":
    main()
