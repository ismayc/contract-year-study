# Do NBA players perform better in contract years?

A study of whether role players and stars raise their play in the final
season of a contract, across the decades of NBA free agency. Every number
below is generated from the committed outputs by `python/13_findings.py`;
none is typed by hand.

<!-- terms -->
> **Terms used in this analysis.** Dotted-underlined terms anywhere below repeat these definitions on hover ([full glossary](https://github.com/ismayc/basketball-data-science/blob/main/docs/glossary.md)).
>
> *(no specialized metric terms in this document)*
<!-- /terms -->

## Headline

<!-- gen:headline -->
**Role players do a little better in contract years; stars do not.** Over 1999-00 to 2025-26, role players beat their expected Box Plus/Minus by +0.21 points per 100 possessions more in a contract year than in a guaranteed non-contract year (95% interval +0.06 to +0.36; within-player estimate +0.37 (SE 0.10)). Stars show no contract-year boost: −0.25 (−0.54 to +0.05), within-player −0.34 (SE 0.19). Defining stars by All-NBA or All-Star honors instead gives −0.39 (−0.71 to −0.08).
<!-- /gen:headline -->

## How it works

- **Performance** comes from two independent sources, Basketball-Reference
  and stats.nba.com, reconciled player-season by player-season before any
  modeling.
- **Contract status** is not published anywhere as a clean field, so each
  season is labeled from independent signals: signing and extension events,
  team moves, the rookie-scale schedule, departures from the league, and
  Wikipedia's free-agent tables. A season counts as a contract year only when
  it was the last of a deal and the next deal had not already been secured.
  The comparison group is seasons with the deal certain to continue.
- **The outcome** is Box Plus/Minus against an expectation built only from
  the player's prior seasons, shrunk toward the league mean and adjusted for
  age, so regression to the mean and aging sit in the baseline rather than in
  the effect.
- **Tiers** (star, starter, role, fringe) come from value in the two seasons
  before, never from the contract year itself.
- The analysis plan, its two dated amendments, and the reasons for them are in
  [`docs/design.md`](docs/design.md). Both amendments were made before any
  contract-year comparison was run.

## Results by tier

<!-- gen:results -->
| Tier | Contract-year seasons | Comparison seasons | Difference (95% interval) | Within-player estimate | Placebo spread |
|---|---|---|---|---|---|
| Stars | 246 | 638 | −0.25 (−0.54 to +0.05) | −0.34 (SE 0.19) | 0.12 |
| Starters | 726 | 950 | −0.19 (−0.33 to −0.05) | −0.04 (SE 0.10) | 0.06 |
| Role players | 1,123 | 838 | +0.21 (+0.06 to +0.36) | +0.37 (SE 0.10) | 0.05 |
| Fringe players | 826 | 759 | +0.20 (+0.02 to +0.39) | +0.76 (SE 0.14) | 0.06 |
| All tiers | 2,921 | 3,185 | −0.06 (−0.15 to +0.03) | +0.16 (SE 0.06) | 0.04 |
<!-- /gen:results -->

The difference compares minutes-weighted residuals; its interval comes from a
bootstrap that resamples players. The within-player estimate compares each
player's contract years with their own other seasons. The placebo spread is the
standard deviation of the difference when contract years are shuffled within
each player's career.

## Does it hold up?

<!-- gen:sensitivity -->
| Specification | Role players | Stars |
|---|---|---|
| Primary (strict definition, fitted expectation) | +0.21 (+0.06 to +0.36) | −0.25 (−0.54 to +0.05) |
| Broad definition (any final contract season) | +0.19 (+0.05 to +0.34) | −0.11 (−0.34 to +0.14) |
| High-confidence contract-year labels only | +0.29 (+0.13 to +0.44) | −0.19 (−0.50 to +0.09) |
| Expectation with the pre-specified 1,000 regression minutes | +0.20 (+0.05 to +0.35) | −0.25 (−0.54 to +0.04) |
| Stars defined by honors (All-NBA or All-Star in the prior two seasons) | n/a | −0.39 (−0.71 to −0.08) |
<!-- /gen:sensitivity -->

### Secondary outcomes

<!-- gen:secondary -->
Across 6 secondary outcomes and 5 tier groups (the four tiers plus all tiers together), 2 contract-year differences stay below 0.05 after a Holm correction within each group: all tiers, games played (+1.73 games against the age-adjusted change, corrected p below 0.01); all tiers, true shooting (+0.32 percentage points against the age-adjusted change, corrected p 0.04).
<!-- /gen:secondary -->

### The season after

<!-- gen:post -->
20% of contract-year role players never played another NBA season (stars: 10%). Role players who did return landed at −0.02 against expectation the next season, against +0.11 for role players who had been in a guaranteed non-contract year.
<!-- /gen:post -->

## How accurate are the contract labels?

<!-- gen:labels -->
| Reference | Seasons labeled contract year that truly were | True contract years caught |
|---|---|---|
| Patricia Bender's 2017-18 contracts snapshot | 81% | 74% |
| Gold set, 2012-13 to 2025-26 | 98% | 94% |
| Gold set, 1999-00 to 2011-12 | 83% | 83% |
<!-- /gen:labels -->

Mislabeled seasons mostly dilute a real effect toward zero, so the
role-player estimate is more likely understated than overstated.

## Data

<!-- gen:data -->
22,103 of 22,105 Basketball-Reference player-seasons have an independent stats.nba.com counterpart, with 0 wrong matches. The expectation shrinks prior performance by 500 regression minutes, fit on non-contract seasons.
<!-- /gen:data -->

Basketball-Reference pages were harvested politely and stay local; only
derived estimates are published. Spotrac, HoopsHype, ProSportsTransactions,
and RealGM were not used: their robots rules or blocks forbid it.

## Earlier eras (exploratory)

<!-- gen:eras -->
For 1988-89 to 1998-99 the all-tier difference is −0.35 (−0.57 to −0.14). For 1976-77 to 1987-88 only 26 seasons qualify as guaranteed non-contract years, too few for any conclusion. Neither era's labels could be validated against independent records.
<!-- /gen:eras -->

Before free agency existed there was no contract-year incentive to test, and
the early free-agency eras could not be checked against independent contract
records, so they are reported for context only.

## Reproducing

Run `./run_checks.sh` for the full chain: unit tests in Python and R, the
cross-source gate, both implementations of the analysis, the R versus Python
reconciliation gate, and the findings drift check.

This repository publishes the code, the tests, and the derived outputs in
`output/`, but not the tables parsed from Basketball-Reference, Wikipedia,
or Patricia Bender's contracts file (see `.gitignore`). A fresh clone can
therefore rerun the findings drift check against the committed outputs, but
rebuilding the panel needs a local harvest first (`python/01..09`).
