"""Parse Patricia Bender's 2017-18 contracts snapshot into a validation table.

Source: https://www.eskimo.com/~pbender/contracts (fetched September 29,
2026; robots.txt allows it). Its own caveat: figures come from newspapers,
media guides, and leaks and "may not be accurate". It is the only verified
source that states contract terms directly, so it validates the inferred
labels for the 2017-18 season; it cannot provide coverage.

Output data/bender_2017_18.csv: one row per listed contract, with
  fa_year        summer the player becomes a free agent (2018 means the
                 2017-18 season is the contract's last)
  rookie_scale   'rc' flag
  option         p-opt / t-opt / x-opt / p&t-opt, declined options (xp/xt)
  restricted     'r' flag or rookie-scale (restricted after year 4)
  extension      '(ext)' present
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "bender" / "contracts_2017-18.txt"

TEAM = re.compile(r"^([A-Z][A-Za-z0-9. ]+?)\s{2,}Date\s")
ROW = re.compile(r"^(?P<name>.+?)\s\.{2,}\s+(?P<rest>.*)$")
FA = re.compile(r"'(\d{2})(?:[-+](\d{2}))?\s*$")
OPTS = ["xp-opt", "xt-opt", "p&t-opt", "p-opt", "t-opt", "x-opt"]


def parse_line(team: str, line: str) -> dict | None:
    m = ROW.match(line.rstrip())
    if not m:
        return None
    rest = m.group("rest")
    fa = FA.search(rest)
    opt = next((o for o in OPTS if o in rest), "")
    dates = re.findall(r"\d{1,2}/\d{1,2}/\d{2}", rest)
    return {
        "team": team,
        "name": m.group("name").strip(),
        "signed_dates": "|".join(dates),
        "fa_year": 2000 + int(fa.group(1)) if fa else None,
        "fa_year_alt": 2000 + int(fa.group(2)) if fa and fa.group(2) else None,
        "rookie_scale": bool(re.search(r"\brc\b", rest)),
        "option": opt,
        "restricted_flag": bool(re.search(r"\s[r]\s+'", rest)),
        "extension": "(ext)" in rest,
        "nbadl": "nbadl" in rest,
        "raw": rest,
    }


def main() -> None:
    team = None
    rows = []
    last_line = None
    for line in SRC.read_text(errors="replace").splitlines():
        t = TEAM.match(line)
        if t:
            team, last_line = t.group(1).strip(), None
            continue
        if team and last_line and line.startswith(" ") and line.strip():
            # Long contract histories wrap: "James Harden .... dates  4+5+4+4"
            # continues on an indented line carrying the salaries and FA year.
            last_line = last_line.rstrip() + " " + line.strip()
            rows[-1] = parse_line(team, last_line)
            continue
        if team and ". ." in line.replace("..", ". .") and "Player" not in line:
            r = parse_line(team, line)
            if r:
                rows.append(r)
                last_line = line
            continue
        last_line = None
    df = pl.DataFrame(rows)
    df.write_csv(ROOT / "data" / "bender_2017_18.csv")
    print(f"{df.height} contracts, {df['team'].n_unique()} teams; "
          f"fa_year missing on {df['fa_year'].null_count()}")
    print(df.group_by("fa_year").len().sort("fa_year"))


if __name__ == "__main__":
    main()
