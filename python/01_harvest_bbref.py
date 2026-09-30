"""Harvest Basketball-Reference pages for the contract-year study.

Raw HTML is cached under data/raw/bbref/ (gitignored). Per the study's
decision record (docs/design.md), only derived estimates are ever published,
never these tables. The harvest is polite and resumable:

- at least DELAY seconds between requests (robots.txt Crawl-delay is 3);
- a cached page is never fetched again;
- HTTP 429 triggers a long back-off instead of a retry burst.

Stages, in order (each can be run alone with --stage):
  seasons       league totals, advanced, and transactions pages per season
  honors        All-NBA page and one All-Star page per season
  players       every player page for anyone in a harvested totals table

Usage:
  python 01_harvest_bbref.py [--stage seasons|honors|players|all] [--limit N]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bbref"
LOG = ROOT / "data" / "harvest_bbref.log"
BASE = "https://www.basketball-reference.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DELAY = 4.0
BACKOFF_429 = 3600

# BPM and VORP start in 1973-74; the pre-1976 seasons serve only as the
# no-incentive baseline. Transactions pages start with 1976-77.
STAT_SEASONS = range(1974, 2027)
TX_SEASONS = range(1977, 2027)
# No All-Star Game was played in 1999 (lockout).
ALLSTAR_SEASONS = [y for y in range(1974, 2027) if y != 1999]

_last = 0.0


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def fetch(path: str, dest: Path) -> bool:
    """Fetch BASE+path into dest unless cached. Returns True if on disk."""
    global _last
    if dest.exists() and dest.stat().st_size > 5_000:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        wait = DELAY - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            r = requests.get(BASE + path, headers={"User-Agent": UA}, timeout=60)
        except requests.RequestException as e:
            log(f"ERR {path} {type(e).__name__} attempt {attempt + 1}")
            time.sleep(30)
            continue
        if r.status_code == 200:
            dest.write_bytes(r.content)
            log(f"OK  {path} {len(r.content)}")
            return True
        if r.status_code == 404:
            log(f"404 {path}")
            return False
        if r.status_code == 429:
            log(f"429 {path}: backing off {BACKOFF_429}s")
            time.sleep(BACKOFF_429)
            continue
        log(f"HTTP {r.status_code} {path} attempt {attempt + 1}")
        time.sleep(60)
    return False


def stage_seasons(limit: int | None) -> None:
    jobs = []
    for y in STAT_SEASONS:
        for kind in ("totals", "advanced"):
            jobs.append((f"/leagues/NBA_{y}_{kind}.html", RAW / "seasons" / f"NBA_{y}_{kind}.html"))
    for y in TX_SEASONS:
        jobs.append((f"/leagues/NBA_{y}_transactions.html", RAW / "transactions" / f"NBA_{y}_transactions.html"))
    run(jobs, limit)


def stage_honors(limit: int | None) -> None:
    jobs = [("/awards/all_league.html", RAW / "honors" / "all_league.html")]
    for y in ALLSTAR_SEASONS:
        jobs.append((f"/allstar/NBA_{y}.html", RAW / "honors" / f"allstar_{y}.html"))
    run(jobs, limit)


def player_ids() -> list[str]:
    ids: set[str] = set()
    # Player cells: <td data-stat="name_display" ...><a href="/players/m/mcadobo01.html">
    pat = re.compile(r'data-stat="name_display"[^>]*><a href="/players/[a-z]/([a-z0-9.\'-]+)\.html"')
    for f in sorted((RAW / "seasons").glob("NBA_*_totals.html")):
        ids.update(pat.findall(f.read_text(errors="replace")))
    if not ids:
        sys.exit("no totals pages cached; run --stage seasons first")
    return sorted(ids)


def stage_players(limit: int | None) -> None:
    jobs = [(f"/players/{pid[0]}/{pid}.html", RAW / "players" / f"{pid}.html") for pid in player_ids()]
    log(f"players stage: {len(jobs)} player ids")
    run(jobs, limit)


def run(jobs: list[tuple[str, Path]], limit: int | None) -> None:
    todo = [j for j in jobs if not (j[1].exists() and j[1].stat().st_size > 5_000)]
    log(f"{len(jobs)} pages, {len(jobs) - len(todo)} cached, {len(todo)} to fetch")
    missing = 0
    for path, dest in todo[:limit]:
        if not fetch(path, dest):
            missing += 1
    log(f"stage done: {missing} pages not retrieved")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["seasons", "honors", "players", "all"])
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if a.stage in ("seasons", "all"):
        stage_seasons(a.limit)
    if a.stage in ("honors", "all"):
        stage_honors(a.limit)
    if a.stage in ("players", "all"):
        stage_players(a.limit)


if __name__ == "__main__":
    main()
