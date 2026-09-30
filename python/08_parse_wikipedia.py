"""Parse the free-agent tables in Wikipedia's season transaction lists.

Each "List of YYYY-YY NBA season transactions" page has a free agency
table (Player, Date signed, New team, Former team, Ref). A row whose team
cell spans both columns (colspan=2) is a same-team re-signing. The page for
season Y lists signings in league year Y, so an offseason signing there
means the player's previous deal ended after season Y-1.

Wikipedia is only semi-independent of Basketball-Reference (editors may
consult it); the rows carry team press releases as references, and the
labeler's validation reports this source separately from the gold set.

Output: data/wiki_signings.csv with page_season, player, date, new_team,
former_team, same_team, rfa.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctlib import norm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wikipedia"
SECTION = re.compile(r"^==+\s*(Free [Aa]gen(?:cy|ts)|Signed from free agency|Signings|Free agency)\s*==+\s*$", re.M)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def clean(cell: str) -> str:
    # {{dts||July|13}} / {{dts|July|13}} date templates -> "July 13"
    cell = re.sub(r"\{\{dts\|+(?:\d{4}\|)?(%s)\|(\d{1,2})[^}]*\}\}" % MONTHS, r"\1 \2", cell)
    cell = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", cell, flags=re.S)
    cell = re.sub(r"<small>.*?</small>|<br\s*/?>", " ", cell, flags=re.S)
    cell = re.sub(r"\{\{sortname\|([^|}]+)\|([^|}]+)[^}]*\}\}", r"\1 \2", cell)
    cell = re.sub(r"\{\{[^}]*\}\}", "", cell)
    cell = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", cell)
    cell = re.sub(r"'''?|\*+", "", cell)
    return re.sub(r"\s+", " ", cell).strip()


def top_level_pipes(s: str) -> list[int]:
    """Positions of '|' not inside {{...}} or [[...]]."""
    depth, out, i = 0, [], 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("{{", "[["):
            depth, i = depth + 1, i + 2
            continue
        if two in ("}}", "]]"):
            depth, i = max(0, depth - 1), i + 2
            continue
        if s[i] == "|" and depth == 0:
            out.append(i)
        i += 1
    return out


def split_cells(row: str) -> list[tuple[str, int, int]]:
    """Cells of one wikitable row as (text, colspan, rowspan). A cell is
    'attrs | content' only when the first top-level pipe follows attribute
    syntax; pipes inside templates and links never split."""
    out = []
    for line in row.split("\n"):
        line = line.strip()
        if not line.startswith("|") or line.startswith("|-") or line.startswith("|}"):
            continue
        body = line[1:]
        pipes = top_level_pipes(body)
        parts, prev, k = [], 0, 0
        while k < len(pipes):  # "||" separates inline cells
            p = pipes[k]
            if k + 1 < len(pipes) and pipes[k + 1] == p + 1:
                parts.append(body[prev:p])
                prev, k = p + 2, k + 2
                continue
            k += 1
        parts.append(body[prev:])
        for part in parts:
            pp = top_level_pipes(part)
            if pp and re.match(r'^\s*(align|colspan|rowspan|style|class)\s*=', part[:pp[0]]):
                attrs, text = part[:pp[0]], part[pp[0] + 1:]
            else:
                attrs, text = "", part
            cs = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
            rs = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            out.append((text, int(cs.group(1)) if cs else 1, int(rs.group(1)) if rs else 1))
    return out


def parse_table(tbl: str, page_season: int) -> list[dict]:
    rows = re.split(r"\n\|-[^\n]*", tbl)
    carry_date: tuple[str, int] | None = None
    out = []
    for r in rows:
        cells = split_cells(r)
        if len(cells) < 2 or "sortname" not in r and not re.search(r"\[\[[^]]+\]\]", cells[0][0]):
            continue
        name = clean(cells[0][0])
        rest = cells[1:]
        if rest and re.search(rf"\b({MONTHS})\b", clean(rest[0][0])):
            d_text, _, rs = rest[0]
            carry_date = (clean(d_text), rs - 1)
            rest = rest[1:]
        elif carry_date and carry_date[1] > 0:
            carry_date = (carry_date[0], carry_date[1] - 1)
        else:
            carry_date = None
        if not rest:
            continue
        same = rest[0][1] >= 2
        new_team = clean(rest[0][0])
        former = new_team if same else (clean(rest[1][0]) if len(rest) > 1 else "")
        d = None
        if carry_date:
            m = re.search(rf"({MONTHS}) (\d{{1,2}})", carry_date[0])
            if m:
                month = datetime.strptime(m.group(1), "%B").month
                year = page_season - 1 if month >= 7 else page_season
                d = date(year, month, int(m.group(2)))
        out.append({"page_season": page_season, "player": name, "key": norm(name),
                    "date": d.isoformat() if d else None, "new_team": new_team,
                    "former_team": former, "same_team": same, "rfa": "RFA" in r})
    return out


def main() -> None:
    rows = []
    for f in sorted(RAW.glob("transactions_*.wikitext")):
        y = int(f.stem.split("_")[1])
        w = f.read_text()
        m = SECTION.search(w)
        if not m:
            print(f"{y}: no free agency section")
            continue
        end = re.search(r"^==[^=]", w[m.end():], re.M)
        sec = w[m.end(): m.end() + end.start()] if end else w[m.end():]
        got = []
        for tbl in re.findall(r"\{\|.*?\n\|\}", sec, re.S):
            if "Former team" in tbl or "former team" in tbl.lower():
                got += parse_table(tbl, y)
        print(f"{y}: {len(got)} signings, {sum(g['same_team'] for g in got)} same-team, "
              f"{sum(g['date'] is None for g in got)} undated")
        rows += got
    pl.DataFrame(rows, infer_schema_length=None).write_csv(ROOT / "data" / "wiki_signings.csv")


if __name__ == "__main__":
    main()
