"""Pure functions shared by the contract-year pipeline scripts.

Deterministic and free of I/O so they can be unit-tested against
hand-computed fixtures and mirrored in R/functions.R.
"""

from __future__ import annotations

import re
import unicodedata

# Basketball-Reference labels a traded player's combined season row "2TM",
# "3TM", ... (older pages used "TOT").
MULTI_TEAM = re.compile(r"^(TOT|\dTM)$")


def norm(name: str) -> str:
    """Collapse a player name to a cross-source comparison key.

    Same rules as draft-potential-by-team/python/draftlib.py::norm: strip
    diacritics, casefold (sharp s), Turkish dotless i, generational suffixes,
    and every non-alphanumeric character.
    """
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.casefold().replace("ı", "i")
    name = re.sub(r"[\s,]+(jr|sr|ii|iii|iv)\.?$", "", name.strip())
    return re.sub(r"[^a-z0-9]", "", name)


def season_label(end_year: int) -> str:
    """1998 -> '1997-98'."""
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def parse_awards(text: str) -> dict[str, bool]:
    """Flags from a Basketball-Reference season 'awards' cell.

    The cell is a comma list such as 'MVP-3,AS,NBA1' or 'DPOY-1,AS,NBA2,DEF1'.
    NBA1/NBA2/NBA3 are All-NBA teams; AS is an All-Star selection; a vote
    finish like MVP-1 counts as winning only when the rank is 1.
    """
    parts = {p.strip() for p in text.split(",") if p.strip()}
    return {
        "all_star": "AS" in parts,
        "all_nba": bool(parts & {"NBA1", "NBA2", "NBA3"}),
        "mvp": "MVP-1" in parts,
        "dpoy": "DPOY-1" in parts,
    }


def raise_breaks(salaries: list[int | None], usable: list[bool], tol: float = 0.015) -> list[bool | None]:
    """Where does a new contract start, judged by the salary path alone?

    Since the 1999 CBA a contract's annual raises are a fixed dollar amount
    (a percentage of the first-year salary), so within one contract the
    salary path is arithmetic: s[j] = s[j-1] + d. A season whose salary
    departs from the running progression by more than tol x the spell's
    first salary starts a new spell. Returns, per season, True (break
    before this season), False (continues the spell), or None (cannot tell:
    this or the previous salary is unusable, e.g. an imputed minimum).
    Index 0 is always None.

    Ray Allen 1999-00 to 2004-05 (9.0, 10.13, 11.25, 12.375, 13.5, 14.625
    million, straight through a 2003 trade) is one spell; the 2005-06 drop to
    13.22 is a break.

    The second season of a spell only defines the raise, so it stays None
    until a third season confirms the pattern, which then marks it False
    retroactively. A break found at the third season leaves the second None:
    the new deal may have started at either one.
    """
    n = len(salaries)
    out: list[bool | None] = [None] * n
    start = None  # index of the current spell's first season
    for j in range(1, n):
        a, b = salaries[j - 1], salaries[j]
        if not (usable[j - 1] and usable[j]) or a is None or b is None:
            start = None
            continue
        if start is None:
            start = j - 1
        if j == start + 1:
            continue  # this pair defines the raise; nothing to test yet
        d = salaries[start + 1] - salaries[start]
        # Expected salary comes from the spell's start, not the previous
        # season, so one off-path season cannot drag the path with it.
        fits = abs(b - (salaries[start] + d * (j - start))) <= tol * salaries[start]
        # A one-season blip that the next season snaps back from is a cap
        # figure quirk (BBRef mixes salaries and cap figures), not a new
        # deal: Ray Allen 2008-09 sits $1M above a path that 2009-10 rejoins.
        if not fits and j + 1 < n and usable[j + 1] and salaries[j + 1] is not None:
            expect_next = salaries[start] + d * (j + 1 - start)
            fits = abs(salaries[j + 1] - expect_next) <= tol * salaries[start]
        if fits:
            out[j] = False
            out[start + 1] = False if out[start + 1] is None else out[start + 1]
        else:
            out[j] = True
            start = j
    return out


def rookie_scale_seasons(draft_year: int, draft_round: int) -> int | None:
    """Scheduled length of a first-round rookie-scale contract, in seasons,
    counting team options as exercised (declines are caught by events).

    1995-97 drafts: 3 guaranteed seasons. 1998-2004: 3 + a fourth-year team
    option (1999 CBA Art. XI 11.4, which also extends the option to 1995-97
    picks not yet signed). 2005 onward: 2 guaranteed + 2 team options.
    Second-round picks and pre-1995 drafts have no scale (None).
    """
    if draft_round != 1 or draft_year < 1995:
        return None
    return 3 if draft_year <= 1997 else 4


def to_num(s: str) -> float | None:
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None
