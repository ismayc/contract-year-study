# Contract-year study: design notes

Started September 29, 2026. Status: **design, no data harvested yet.** Nothing
here is a finding about players. Every claim about a source was checked by
loading it on September 29, 2026, unless marked UNVERIFIED.

## Decisions (Chester, September 29, 2026)

1. **Sports-Reference:** polite harvest at or above the 3 s crawl delay,
   raw HTML cached locally and gitignored; publish only derived estimates,
   never the scraped salary or transaction tables themselves.
2. **Eras:** headline results from 1999-00 onward; 1988-99 and 1976-88 as
   separate panels carrying their measured label accuracy; pre-1976 only as a
   no-incentive baseline.
3. **Definition:** strict primary (no next deal secured, options excluded),
   broad "final season of any contract" as the sensitivity check.
4. **Tiers:** prior-two-season value percentile (star, starter, role,
   fringe) as primary; All-NBA or All-Star in the prior two seasons as the
   robustness definition of "star."
5. **Pre-2000 eras exploratory** (decided later on September 29, 2026). The
   gold-set research verified only 1 contract for 1977-88 and 3 for
   1989-99, because the newspaper archives that would settle them are
   blocked to the research tools. Those eras are reported with unvalidated
   labels, clearly marked exploratory; no archive pass or hand check is
   planned. Only 2000-2026 carries a validated label accuracy.

## Questions

1. Do role players perform better in contract years?
2. Do stars?
3. Across the decades of the NBA: does the answer change as the labor rules
   that create the incentive change?

## What "contract year" can mean (and why it matters)

Two different samples hide behind the phrase:

- **Final season of a contract.** Easy to approximate, but it includes players
  who already signed an extension before the season (Kevin Garnett's
  October 1997 extension came before his final rookie-deal season, so that
  season carried no contract pressure).
- **A season played without the next deal secured.** This is the season that
  actually tests the incentive. Ryan (2015) goes further and also excludes
  seasons followed by any option, because opting out selects on good
  performance.

Proposed primary definition: the second one, with option seasons excluded,
and the broad "final season" version reported as a sensitivity check.

## Labor-rule eras (the incentive did not exist for most of NBA history)

Checked against sources: SI on Tom Chambers ("In July of 1988, Chambers
became the first unrestricted free agent in NBA history") and the 1999 CBA
text (§11.4 Fourth Year Option for First Round Picks, §11.5 Qualifying Offers
for restricted free agency). The rest comes from the rules-timeline survey,
with its UNVERIFIED items listed there.

| Era | Seasons | Contract-year incentive | Role in study |
|---|---|---|---|
| Reserve / option clause | 1946-47 to 1975-76 | None: no free agency at a contract's end | Excluded (performance data exists, the question does not apply) |
| Right of first refusal + compensation | 1976-77 to 1987-88 | Weak: old team can match or be compensated; cap from 1984-85 | Exploratory, low label quality |
| First unrestricted free agency | 1988-89 to 1998-99 | Real for veterans (initially 7+ seasons, third contract); rookie scale from 1995 | Secondary, flagged |
| Max-contract CBAs | 1999-00 onward | Stable modern regime: max tiers, rookie option + restricted FA, Bird rights, regulated options and extensions | Primary sample |

Sub-eras inside the primary sample give sharper tests of the star question:

- **Max contracts cap a star's upside** (25/30/35% tiers from 1999), which
  predicts a smaller contract-year effect for max-level stars.
- **Rose Rule (2011 CBA) and Designated Veteran supermax (2017 CBA)** tie a
  higher maximum to All-NBA, MVP, or DPOY selection. That is an explicit,
  dated, performance-linked incentive for a known set of eligible stars, a
  natural experiment inside the star group.
- **Restricted free agency** lets a rookie-scale player's team match any
  offer, predicting a weaker effect for players coming off rookie deals.

## Data sources

### Performance (two independent sources, cross-validated)

- stats.nba.com via `nba_api` (already in the family venv; see the
  User-Agent gotcha in the family notes).
- Basketball-Reference season tables.
- Plan: reconcile box-score totals between the two per player-season before
  any modeling, and publish the reconcile rate.

### Contract status (no single source exists; the label must be inferred)

| Source | Verified coverage | Records same-team re-signings / extensions? | Access |
|---|---|---|---|
| Basketball-Reference league transactions `/leagues/NBA_YYYY_transactions.html` | 1977 onward loads | Poorly before ~2010s: Tim Duncan's 2000 and 2003 re-signings and Garnett's 1997 extension are all absent; later years annotate extensions | Crawl-delay 3; see terms below |
| Basketball-Reference player-page Salaries table | Duncan and McGrady series visible | Indirectly: a new salary level marks a new deal | Same terms; **imputed values**: "Minimum salaries were given to all players without salary data in 1988-89, and 1990-91 through 2004-05" |
| Patricia Bender contracts file (eskimo.com/~pbender/contracts) | 639 lines, 2017-18 snapshot | Yes: signing date, years, rookie-contract flag, options, free-agency year | Robots allow; single season only, so validation not coverage |
| Wikipedia season transaction lists | Exists 2000-01, 2003-04 to 2005-06, 2015-16, 2019-20 onward (gaps) | UNVERIFIED | CC BY-SA |
| Rookie-scale rules (1995 CBA onward) | Rule-based | Contract length follows from draft year and round | Derived, no scraping |
| Spotrac | n/a | Best modern source | **Excluded**: its robots.txt blocks AI crawlers from data pages ("so AI can describe Spotrac as a source, but not scrape data") |
| HoopsHype | n/a | n/a | **Excluded**: robots.txt disallows `Claude`, `ClaudeBot`, `anthropic-ai` |
| ProSportsTransactions | n/a | Reportedly back to 1947 (UNVERIFIED) | **Excluded**: 403 to scripts; not bypassed |
| RealGM transactions | n/a | UNVERIFIED | 403 to scripts; not bypassed |

**Sports-Reference terms** (sports-reference.com/data_use.html, read
September 29, 2026): "you should not create websites or tools based on data
you scrape from Sports Reference or any of our sites or use our data to train
generative artificial intelligence models without our permission." Custom
data requests start at $5,000. This needs a decision before any harvest.

### Proposed contract-year labeler (multi-source, graded confidence)

1. Signing events from the transaction log.
2. Salary-structure breaks, **excluding seasons whose salary is an imputed
   league minimum** (detectable as exactly the minimum in the listed years).
3. Rookie-scale contract lengths from draft year and round.
4. Validation, reported per era as precision and recall:
   - Bender's 2017-18 file (direct contract terms for one season).
   - Wikipedia transaction lists where they exist.
   - A hand-verified gold set of contracts, each confirmed by two independent
     news sources (Ryan's 2015 standard), sampled across eras and across
     stars and role players.

Each labeled season carries a confidence grade. Era estimates are only
reported where the labeler's validated accuracy supports them.

## Prior research (checked items marked)

- **White and Sheldon (2014), Motivation and Emotion 38:196-205.** Checked in
  the PDF: 510 NBA player-years; PER 14.78 before, 15.41 in, 14.24 after the
  contract year. No regression-to-the-mean control; requiring a post season
  conditions on survival.
- **Ryan (2015), Harvard thesis.** Strictest definition (guaranteed contract
  year vs guaranteed non-contract year, options excluded); roughly a 3 to 5
  percentile boost for a median player, OLS with player fixed effects; IV
  estimates "undeniably muddled." Contract data from three sources
  reconciled by hand; not released.
- **Stiroh (2007), Berri and Krautmann (2006):** abstracts only (full text
  blocked). Pre-contract boost (Stiroh); shirking result depends on the
  metric (Berri and Krautmann).
- **Owsik and Tan (2026), Applied Economics Letters:** no significant
  contract-year gain, post-contract declines. Abstract snippet only.
- **Krautmann and Solow (2009, MLB):** players less likely to get another
  contract underperform expectation. The closest analog to a star vs role
  split.
- **No NBA study found that answers the star vs role-player question on a
  real sample.** Gaffaney (2013) splits by career PER on one season of data
  (abstract only).

Pitfalls the design must handle, from that literature:

1. Naive means show a negative effect because weaker players get shorter
   deals (Ryan, Table V).
2. Regression to the mean mimics both the contract-year spike and
   post-contract "shirking" (Krautmann 1990).
3. Requiring a post-contract season conditions on getting paid.
4. Defining stars from contract-year performance builds in the selection.
5. Metric choice can flip the conclusion (Berri and Krautmann).
6. No paper corrects for testing many box-score stats.

## Pre-specified analysis (fixed September 29, 2026, before any outcome comparison)

Written down before any contract-year performance comparison was run, so
the primary metric, tiers, and model cannot drift toward a result.

- **Primary outcome:** Box Plus/Minus (BPM, points per 100 possessions
  above average), available from 1973-74, minus its pre-season expectation.
- **Expectation (from prior seasons only):** minutes-weighted average of
  BPM in t-1, t-2, t-3 with weights 5/4/3, regressed toward the league
  mean by adding 1,000 minutes of a league-average (0.0) season, plus an
  age adjustment from an aging curve fit by the delta method on consecutive
  season pairs in which the later season is not a contract year (either
  definition). Seasons t with no prior NBA season have no expectation and
  are excluded.
- **Sample floor:** at least 250 minutes in season t; each player-season
  weighted by its minutes in the pooled estimates.
- **Tiers (from t-1 and t-2 only):** summed VORP over t-1 and t-2,
  percentile among players who appear in season t: star = top 10%,
  starter = 10-30%, role = 30-70%, fringe = bottom 30%. Robustness: star =
  All-NBA or All-Star selection in t-1 or t-2.
- **Groups:** contract year = `cy_strict`; comparison = `nc_strict`
  (guaranteed non-contract year). Seasons labeled unknown, terminated, or
  cut in the offseason are in neither. Sensitivity: `cy_broad`, and
  high-confidence labels only.
- **Estimate:** difference in mean residual (contract year minus
  comparison), minutes-weighted, with 95% intervals from a player-clustered
  bootstrap; per tier and per era. A player fixed-effects regression of the
  residual on the contract-year indicator (clustered by player) as the
  second estimator.
- **Secondary outcomes** (Holm correction across them): minutes per game,
  games played, true shooting %, usage %, WS/48, PER.
- **Post-contract season:** residual in t+1 for contract-year players who
  signed a new NBA deal, and exit rates for those who did not, reported
  side by side so survival is never conditioned on silently.
- **Label quality gate:** era results are published only with that era's
  validated label accuracy beside them; an era without validation is
  labeled exploratory.

### Amendment 1 (September 29, 2026, still before any outcome comparison)

The pre-specified expectation (1,000 regression minutes) was miscalibrated by
tier on the pooled data: minutes-weighted mean residual +0.51 BPM for stars,
-0.56 for fringe players. The expectation shrank everyone too far toward the
league mean, and since the contract-year and comparison groups can differ in
prior level inside a tier, that bias could leak into the estimate.

Change: the regression minutes are now fit, by minutes-weighted least
squares on a 0 to 5,000 grid, on non-contract seasons only (neither
definition) with at least 250 minutes. The fit chose 500 on the partial
harvest; tier residuals moved to -0.13 to +0.26. The 1,000-minute version
stays available (`10_build_panel.py --fixed-1000`) and will be reported as
a sensitivity check. No contract-year comparison had been computed when this
change was made.

### Amendment 2 (September 29, 2026, still before any outcome comparison)

Full-data validation (2000-2026) showed that seasons labeled "continues"
were right 96% (Bender 2017-18, 84 seasons) and 97% (gold set, 78 seasons)
of the time, but seasons labeled "final" were right only 70% (Bender, 135)
and 69% (gold, 104). Most false finals (48 of about 70) rested on a salary
break with no other signal: cap-figure quirks and irregular contract
structures. Mixing mid-contract seasons into the contract-year group would
pull any effect toward zero.

Change: a salary break alone leaves a season "unknown"; it still raises
confidence when another signal agrees. Checked before adoption: label
precision for "final" rose to 82% (Bender) and 93% (gold), with 74% and 88%
of true final seasons still caught. No contract-year comparison had been
computed when this change was made.

## Proposed analysis

- **Unit:** player-season, primary sample 1999-00 onward, earlier eras
  reported separately with their label-quality grade.
- **Outcome:** performance relative to an out-of-sample expectation built
  only from prior seasons (weighted multi-season baseline plus an aging
  curve fit on non-contract seasons), so regression to the mean and aging
  are in the baseline rather than in the effect. One primary metric chosen
  before looking at contract-year results; others reported as secondary with
  a multiple-testing correction.
- **Tiers:** star vs starter vs role player vs fringe, defined from the prior
  two seasons only (value percentile, plus All-NBA / All-Star as a second
  definition). Sensitivity check: salary tier.
- **Models:** player fixed effects, clustered by player; the expectation-gap
  model as the headline. Placebos on shuffled contract years. Post-contract
  season analyzed separately without requiring players to survive into it
  (exit modeled as an outcome).
- **Sharp star test:** Rose Rule and supermax eligibility windows versus
  otherwise similar ineligible stars.
- **Minutes and role:** effects on playing time reported separately from
  per-minute efficiency (a coach's choice vs the player's output).
- **Family standards:** dual Python (polars) and R implementations with a
  reconcile gate, findings generator with no hand-typed numbers, family page
  through `report_builder.py`.
