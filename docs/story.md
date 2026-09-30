# Do NBA players play better in contract years?

The idea is older than most box scores: a player about to hit free agency
plays harder, because the next contract depends on it. This study tests it
across 1999-00 to 2025-26, one season at a time, by comparing each player's
contract years with seasons where the next deal was already guaranteed. The
answer depends on who you ask about. Role players show a small, real bump.
Stars show none, and if anything slip.

<div class="tiles">
<div class="tile"><div class="label">Role players</div>
<div class="value">+0.21</div>
<div class="sub">Box Plus/Minus per 100 possessions above expectation in a contract year (95% interval +0.06 to +0.36).</div></div>
<div class="tile"><div class="label">Stars</div>
<div class="value">−0.25</div>
<div class="sub">No boost. The interval runs from −0.54 to +0.05.</div></div>
<div class="tile"><div class="label">Contract years</div>
<div class="value">2,921</div>
<div class="sub">Seasons labeled as the last of a deal with the next one not yet secured.</div></div>
<div class="tile"><div class="label">Comparison seasons</div>
<div class="value">3,185</div>
<div class="sub">Seasons where the player's deal was certain to continue.</div></div>
</div>

<div class="eyebrow beat">The question</div>

## Why this is harder than it looks

Two things make a naive comparison wrong. The first is regression to the
mean: players often reach a contract year right after a good season, so
their next season looks worse whatever the contract says. The second is
aging: contract years cluster at particular ages, and players at those ages
are already rising or falling.

So the outcome here is not raw Box Plus/Minus. It is Box Plus/Minus against
an expectation built only from the player's earlier seasons, pulled toward
the league average and adjusted for age. A contract-year effect has to show
up on top of both. Players are grouped into four tiers (stars, starters,
role players, and fringe players) by their value in the two seasons
before, never by the contract year itself.

<div class="eyebrow beat">The answer</div>

## Role players rise a little; stars do not

{{fig:fig1_tier_effects_py|Contract-year difference by tier, with two independent estimates. The first compares contract years with guaranteed years across players, with an interval from resampling players. The second compares each player only with their own other seasons. Role players land above zero in both (+0.21 and +0.37). Stars land at or below zero in both (−0.25 and −0.34). Pooling every tier hides the split: the all-tier difference is −0.06 (−0.15 to +0.03).}}

The size matters as much as the sign. About a fifth of a point of Box
Plus/Minus per 100 possessions is small: a real effect, not a
transformation. For stars the estimate points the other way. One possible
reading is that stars have little to prove and a lot to protect, but the
data here can only say that no boost shows up.

<div class="eyebrow beat">Stress test</div>

## The pattern survives every specification

The analysis plan was written before any contract-year comparison was run,
and its two amendments were dated before any outcome was looked at. The
checks below were also fixed in advance.

{{fig:fig2_sensitivity_py|Role players and stars under each pre-specified alternative: a broad contract-year definition (any final contract season), only the labels held with high confidence, the original 1,000 regression minutes for the expectation, and stars defined by All-NBA or All-Star honors instead of value. Role players stay above zero in every version, from +0.19 to +0.29. Stars defined by honors fall further, to −0.39 (−0.71 to −0.08).}}

The contract-year boost does not spread into other measures much. Of six
secondary outcomes checked across five tier groups, only two survive a
correction for multiple comparisons, both across all tiers: players appear
in +1.73 more games than their age alone predicts, and their true shooting
rises by +0.32 percentage points.

<div class="eyebrow beat">Afterward</div>

## The season after

A contract year is also a sorting event. Of the contract-year role players,
20% never played another NBA season (stars: 10%).

{{fig:fig3_season_after_py|Next-season Box Plus/Minus against expectation, for players who played at least 250 minutes the following season. Stars, starters, and role players coming off a contract year do worse the next season than players coming off a guaranteed year (role players: −0.02 against +0.11). Fringe players are level. This is descriptive: the players who returned after a contract year are a selected group, since the market has just decided who got a new deal.}}

<div class="eyebrow beat">Limits</div>

## What the labels can and cannot support

No public source lists contract status as a clean field, so every season is
labeled from signing and extension events, team moves, the rookie-scale
schedule, departures from the league, and Wikipedia's free-agent tables.
Checked against a hand-verified gold set and Patricia Bender's 2017-18
contracts snapshot, the labels are strong for recent seasons and weaker
before about 2012. Mislabeled seasons mostly blur a real effect toward
zero, so the role-player estimate is more likely understated than
overstated. Earlier eras are reported in the README for context only,
because their labels could not be checked against independent records.

Performance comes from Basketball-Reference, cross-checked season by season
against stats.nba.com before any modeling. The raw pages stay local; only
derived estimates are published.
