"""Parse cached season pages into player-season tables.

Outputs (data/, gitignored raw inputs, committed derived tables later):
  bbref_player_seasons.csv   one row per player-season (combined row for
                             traded players), totals + advanced + awards
  nba_player_seasons.csv     one row per player-season from stats.nba.com
                             (LeagueDashPlayerStats where it exists, else
                             LeagueLeaders)
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import MULTI_TEAM, parse_awards, season_label, to_num  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
TOTALS = ["games", "games_started", "mp", "fg", "fga", "fg3", "fg3a", "ft", "fta",
          "orb", "drb", "trb", "ast", "stl", "blk", "tov", "pf", "pts"]
ADV = ["per", "ts_pct", "usg_pct", "ows", "dws", "ws", "ws_per_48", "obpm", "dbpm", "bpm", "vorp"]


def table_rows(path: Path, table_id: str) -> list[dict]:
    soup = BeautifulSoup(path.read_text(errors="replace"), "lxml")
    t = soup.find("table", id=table_id)
    if t is None:
        raise SystemExit(f"{path.name}: no table#{table_id}")
    out = []
    for tr in t.find("tbody").find_all("tr"):
        cells = {c.get("data-stat"): c for c in tr.find_all(["th", "td"])}
        name = cells.get("name_display")
        if name is None or name.find("a") is None:
            continue  # repeated header rows and the league-average row
        row = {k: c.get_text(strip=True) for k, c in cells.items()}
        row["bbref_id"] = name.find("a")["href"].rsplit("/", 1)[-1].removesuffix(".html")
        out.append(row)
    return out


def collapse(rows: list[dict]) -> dict[str, dict]:
    """Keep one row per player: the multi-team combined row when present.
    Records the per-team stints in order as 'teams'."""
    by: dict[str, dict] = {}
    stints: dict[str, list[str]] = {}
    for r in rows:
        pid, team = r["bbref_id"], r["team_name_abbr"]
        if MULTI_TEAM.match(team):
            by[pid] = r
        else:
            stints.setdefault(pid, []).append(team)
            by.setdefault(pid, r)
    for pid, r in by.items():
        r["teams"] = "|".join(stints.get(pid, []))
        r["n_teams"] = len(stints.get(pid, []))
    return by


def bbref() -> pl.DataFrame:
    recs = []
    for y in range(1974, 2027):
        tp = RAW / "bbref" / "seasons" / f"NBA_{y}_totals.html"
        ap = RAW / "bbref" / "seasons" / f"NBA_{y}_advanced.html"
        if not (tp.exists() and ap.exists()):
            print(f"skip {y}: season pages not cached", file=sys.stderr)
            continue
        tot = collapse(table_rows(tp, "totals_stats"))
        adv = collapse(table_rows(ap, "advanced"))
        if set(tot) != set(adv):
            raise SystemExit(f"{y}: totals and advanced player sets differ "
                             f"({len(set(tot) ^ set(adv))} ids)")
        for pid, t in tot.items():
            a = adv[pid]
            aw = parse_awards(t.get("awards", ""))
            rec = {"season": y, "season_label": season_label(y), "bbref_id": pid,
                   "name": t["name_display"], "age": to_num(t.get("age", "")),
                   "pos": t.get("pos", ""), "teams": t["teams"], "n_teams": t["n_teams"],
                   "awards_raw": t.get("awards", ""), **aw}
            rec.update({k: to_num(t.get(k, "")) for k in TOTALS})
            rec.update({k: to_num(a.get(k, "")) for k in ADV})
            recs.append(rec)
    return pl.DataFrame(recs, infer_schema_length=None)


def nba() -> pl.DataFrame:
    frames = []
    d = RAW / "nba_api"
    for y in range(1974, 2027):
        dash, lead = d / f"dash_{y}.csv", d / f"leaders_{y}.csv"
        if dash.exists():
            df = pl.read_csv(dash, infer_schema_length=None).select(
                pl.col("PLAYER_ID").alias("nba_id"), pl.col("PLAYER_NAME").alias("name"),
                pl.col("GP").alias("games"), pl.col("MIN").alias("mp"), pl.col("PTS").alias("pts"),
                pl.col("REB").alias("trb"), pl.col("AST").alias("ast"), pl.col("FGA").alias("fga"),
                pl.col("FTA").alias("fta"), pl.lit("dash").alias("nba_source"))
        elif lead.exists():
            df = pl.read_csv(lead, infer_schema_length=None).select(
                pl.col("PLAYER_ID").alias("nba_id"), pl.col("PLAYER").alias("name"),
                pl.col("GP").alias("games"), pl.col("MIN").alias("mp"), pl.col("PTS").alias("pts"),
                pl.col("REB").alias("trb"), pl.col("AST").alias("ast"), pl.col("FGA").alias("fga"),
                pl.col("FTA").alias("fta"), pl.lit("leaders").alias("nba_source"))
        else:
            continue
        frames.append(df.with_columns(pl.lit(y).alias("season")).with_columns(
            pl.col(c).cast(pl.Float64) for c in ["games", "mp", "pts", "trb", "ast", "fga", "fta"]))
    league = pl.concat(frames)

    # PlayerCareerStats (01d) fills LeagueLeaders' pre-1986-87 omission of
    # traded players: the TOT row, used only where LeagueLeaders has no row.
    careers = []
    for f in sorted(d.glob("career_*.csv")):
        c = pl.read_csv(f, infer_schema_length=None)
        if c.height == 0:
            continue
        # The TOT row for a traded season, otherwise the season's only row
        # (players missing from the league tables entirely, e.g. Negele
        # Knight, played single-team seasons).
        c = c.filter((pl.col("TEAM_ABBREVIATION") == "TOT") | (pl.len().over("SEASON_ID") == 1))
        tot = c.select(
            pl.col("PLAYER_ID").alias("nba_id"),
            (pl.col("SEASON_ID").str.slice(0, 4).cast(pl.Int64) + 1).alias("season"),
            pl.col("GP").cast(pl.Float64).alias("games"), pl.col("MIN").cast(pl.Float64).alias("mp"),
            pl.col("PTS").cast(pl.Float64).alias("pts"), pl.col("REB").cast(pl.Float64).alias("trb"),
            pl.col("AST").cast(pl.Float64).alias("ast"), pl.col("FGA").cast(pl.Float64).alias("fga"),
            pl.col("FTA").cast(pl.Float64).alias("fta"))
        careers.append(tot)
    if careers:
        names = league.group_by("nba_id").agg(pl.col("name").last())
        allp = d / "common_all_players.csv"
        if allp.exists():
            names = pl.concat([names, pl.read_csv(allp, infer_schema_length=None).select(
                pl.col("PERSON_ID").alias("nba_id"), pl.col("DISPLAY_FIRST_LAST").alias("name"))]
            ).unique("nba_id", keep="first")
        fill = (pl.concat(careers).join(league.select("season", "nba_id"), on=["season", "nba_id"], how="anti")
                .join(names, on="nba_id", how="left")
                .with_columns(pl.lit("career").alias("nba_source")))
        league = pl.concat([league, fill.select(league.columns).cast(league.schema)])
    return league


def main() -> None:
    b = bbref()
    b.write_csv(ROOT / "data" / "bbref_player_seasons.csv")
    print(f"bbref: {b.height} player-seasons, {b['season'].n_unique()} seasons")
    n = nba()
    n.write_csv(ROOT / "data" / "nba_player_seasons.csv")
    print(f"nba:   {n.height} player-seasons, {n['season'].n_unique()} seasons")


if __name__ == "__main__":
    main()
