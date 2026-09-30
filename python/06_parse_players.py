"""Parse cached Basketball-Reference player pages into contract inputs.

The salary, transaction, and contract tables live inside HTML comments, so
they are located in the raw text rather than through the parsed DOM.

Outputs (data/):
  player_salaries.csv   bbref_id, season (end year), team, salary, row
  player_events.csv     bbref_id, date, season_of_event, kind, team, text
  player_draft.csv      bbref_id, draft_year, round, pick, team
  player_contract_now.csv  bbref_id, season, salary, option (player/team/'')
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "data" / "raw" / "bbref" / "players"

# Event taxonomy, first match wins; built from the phrase census of the
# cached pages (python/06_parse_players.py --census reprints it).
KINDS = [
    ("extension", r"^Signed a contract extension|extension on deal signed"),
    ("resigned", r"^Re-signed"),
    ("two_way", r"two-way contract"),
    ("ten_day", r"\d+-day contract|10-day"),
    ("exhibit10", r"Exhibit \d+ contract"),
    ("rest_of_season", r"for the rest of the season"),
    ("signed_multi", r"^Signed a multi-year contract"),
    ("signed_fa", r"^Signed as (?:a|an) (?:veteran |unrestricted |restricted )?free agent"),
    ("signed_other", r"^Signed"),
    ("converted", r"^Converted from a two-way"),
    ("drafted", r"^Drafted by"),
    ("traded", r"[Tt]raded by"),
    ("waived", r"^Waived by"),
    ("released", r"^Released by"),
    ("claimed", r"^Claimed on waivers"),
    ("retired", r"[Rr]etire"),
    ("assigned", r"^(Assigned to|Recalled from|Sent to)"),
]
DATE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})\s*:\s*")
DRAFT = re.compile(r"Drafted by the (?P<team>.+?) in the (?P<round>\d)(?:st|nd|rd|th) round "
                   r"\((?P<pick>\d+)(?:st|nd|rd|th) pick\) of the (?P<year>\d{4}) (?:NBA|ABA) Draft")


def raw_table(html: str, table_id: str) -> BeautifulSoup | None:
    m = re.search(r'<table[^>]*id="%s".*?</table>' % re.escape(table_id), html, re.S)
    return BeautifulSoup(m.group(0), "lxml") if m else None


def season_of(d: date) -> int:
    """NBA season end year a date belongs to, with the league year turning
    over on July 1 (a July 2004 signing belongs to the 2004-05 league year)."""
    return d.year + 1 if d.month >= 7 else d.year


def classify(text: str) -> str:
    for kind, pat in KINDS:
        if re.search(pat, text):
            return kind
    return "other"


def parse_page(pid: str, html: str) -> tuple[list, list, list, list]:
    sal, ev, dr, now = [], [], [], []
    t = raw_table(html, "all_salaries")
    if t is not None:
        for i, tr in enumerate(t.find_all("tr")):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) >= 4 and re.match(r"^\d{4}-\d{2}$", cells[0]) and cells[2] == "NBA":
                amount = re.sub(r"[^0-9]", "", cells[3])
                sal.append({"bbref_id": pid, "season": int(cells[0][:4]) + 1, "team": cells[1],
                            "salary": int(amount) if amount else None, "row": i})
    i = html.find('id="div_transactions"')
    if i >= 0:
        text = BeautifulSoup(html[i - 10:html.find("</div>", i)], "lxml").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        parts = DATE.split(text)[1:]
        for d_str, body in zip(parts[0::2], parts[1::2]):
            d = datetime.strptime(d_str, "%B %d, %Y").date()
            body = body.strip()
            kind = classify(body)
            team = re.search(r"(?:with|by|to) the ([A-Z][A-Za-z0-9. ]+?)(?: \.| in | for | to | with |\.|$)", body)
            ev.append({"bbref_id": pid, "date": d.isoformat(), "league_year": season_of(d), "kind": kind,
                       "team": team.group(1).strip() if team else "", "text": body[:300]})
            m = DRAFT.search(body)
            if m and m.group(0).endswith("NBA Draft"):
                dr.append({"bbref_id": pid, "draft_year": int(m["year"]), "round": int(m["round"]),
                           "pick": int(m["pick"]), "team": m["team"]})
    for m in re.finditer(r'<table[^>]*id="contracts_[a-z0-9]+".*?</table>', html, re.S):
        rows = BeautifulSoup(m.group(0), "lxml").find_all("tr")
        heads = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        for tr in rows[1:]:
            cells = tr.find_all(["th", "td"])
            for h, c in zip(heads[1:], cells[1:]):
                span = c.find("span")
                cls = " ".join(span.get("class", [])) if span else ""
                amount = re.sub(r"[^0-9]", "", c.get_text())
                now.append({"bbref_id": pid, "season": int(h[:4]) + 1,
                            "salary": int(amount) if amount else None,
                            "option": "player" if "salary-pl" in cls else "team" if "salary-tm" in cls else ""})
    return sal, ev, dr, now


def main() -> None:
    files = sorted(PAGES.glob("*.html"))
    S, E, D, N = [], [], [], []
    for f in files:
        s, e, d, n = parse_page(f.stem, f.read_text(errors="replace"))
        S += s
        E += e
        D += d
        N += n
    out = ROOT / "data"
    pl.DataFrame(S, schema={"bbref_id": pl.String, "season": pl.Int64, "team": pl.String,
                            "salary": pl.Int64, "row": pl.Int64}).write_csv(out / "player_salaries.csv")
    ev = pl.DataFrame(E, schema={"bbref_id": pl.String, "date": pl.String, "league_year": pl.Int64,
                                 "kind": pl.String, "team": pl.String, "text": pl.String})
    ev.write_csv(out / "player_events.csv")
    pl.DataFrame(D, schema={"bbref_id": pl.String, "draft_year": pl.Int64, "round": pl.Int64,
                            "pick": pl.Int64, "team": pl.String}).unique("bbref_id", keep="first") \
        .write_csv(out / "player_draft.csv")
    pl.DataFrame(N, schema={"bbref_id": pl.String, "season": pl.Int64, "salary": pl.Int64,
                            "option": pl.String}).write_csv(out / "player_contract_now.csv")
    print(f"{len(files)} pages: {len(S)} salary rows, {len(E)} events, {len(D)} draft rows, {len(N)} future-contract cells")
    print(ev.group_by("kind").len().sort("len", descending=True))
    if "--census" in sys.argv:
        print(ev.filter(pl.col("kind") == "other").select("text").head(30))


if __name__ == "__main__":
    main()
