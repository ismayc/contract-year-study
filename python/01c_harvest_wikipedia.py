"""Cache the wikitext of Wikipedia's "List of YYYY-YY NBA season
transactions" pages (CC BY-SA), the independent record of same-team
re-signings used to validate the contract-year labels.

Existing pages checked September 29, 2026: 2000-01, then 2003-04 through
2025-26 (24 pages). Missing titles are skipped. Output:
data/raw/wikipedia/transactions_<end_year>.wikitext
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "wikipedia"
API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "contract-year-study/0.1 (basketball research; https://github.com/ismayc/contract-year-study)"}


def title(end_year: int) -> str:
    return f"List of {end_year - 1}–{str(end_year)[-2:]} NBA season transactions"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for y in range(1995, 2027):
        dest = OUT / f"transactions_{y}.wikitext"
        if dest.exists():
            continue
        r = requests.get(API, params={"action": "parse", "page": title(y), "prop": "wikitext",
                                      "format": "json", "redirects": 1}, headers=UA, timeout=60)
        j = r.json()
        if "error" in j:
            print(f"missing {y}: {j['error'].get('code')}")
        else:
            dest.write_text(j["parse"]["wikitext"]["*"])
            print(f"OK {y} {dest.stat().st_size}")
        time.sleep(1)


if __name__ == "__main__":
    main()
