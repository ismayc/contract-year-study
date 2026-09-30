# Contract-year study: analysis panel, independent R / tidyverse implementation.
#
# Same definitions as docs/design.md (pre-specified section plus Amendment 1):
# expected BPM from t-1..t-3 (weights 1.0/0.8/0.6 times minutes), shrunk by
# regression minutes fit on non-contract seasons (grid 0..5000 by 100,
# minutes-weighted squared error), plus a delta-method aging curve from
# consecutive pairs whose later season is not a contract year; tiers from the
# within-season percentile of VORP summed over t-1 and t-2.
#
# Writes output/panel_r.csv, output/panel_scalars_r.csv, output/aging_curve_r.csv,
# and data/panel_r.csv (full panel for R/11_contract_effect.R).
#
# Run:  Rscript R/10_build_panel.R

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(purrr)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")
source(file.path(ROOT, "R", "functions.R"))

FIXED_1000 <- "--fixed-1000" %in% commandArgs(trailingOnly = TRUE)
W <- c(1.0, 0.8, 0.6)

seasons <- read_csv(file.path(ROOT, "data", "bbref_player_seasons.csv"), show_col_types = FALSE,
                    guess_max = 100000) |>
  select(bbref_id, season, age, mp, bpm, vorp, all_star, all_nba)
labels <- read_csv(file.path(ROOT, "data", "contract_labels.csv"), show_col_types = FALSE,
                   guess_max = 100000) |>
  select(bbref_id, season, cy_strict, cy_broad)

b <- seasons |>
  left_join(labels, by = c("bbref_id", "season")) |>
  mutate(cy_any = coalesce(cy_strict, FALSE) | coalesce(cy_broad, FALSE))

lagged <- function(k) {
  seasons |>
    transmute(bbref_id, season = season + k,
              "mp_l{k}" := mp, "bpm_l{k}" := bpm, "vorp_l{k}" := vorp,
              "hon_l{k}" := all_star | all_nba)
}
for (k in 1:3) b <- left_join(b, lagged(k), by = c("bbref_id", "season"))

z <- function(x) coalesce(x, 0)
b <- b |>
  mutate(num = W[1] * z(mp_l1) * z(bpm_l1) + W[2] * z(mp_l2) * z(bpm_l2) + W[3] * z(mp_l3) * z(bpm_l3),
         den = W[1] * z(mp_l1) + W[2] * z(mp_l2) + W[3] * z(mp_l3))

# Regression minutes (Amendment 1), fit on non-contract seasons only.
fit_rows <- b |> filter(!cy_any, den > 0, mp >= 250, !is.na(bpm))
grid <- seq(0, 5000, by = 100)
sse <- map_dbl(grid, \(r) sum((fit_rows$bpm - fit_rows$num / (fit_rows$den + r))^2 * fit_rows$mp))
regress_min <- if (FIXED_1000) 1000 else grid[which.min(sse)]
cat(sprintf("regression minutes: %d (fit on %d non-contract seasons)\n", as.integer(regress_min), nrow(fit_rows)))

b <- b |>
  mutate(exp_bpm_raw = expected_bpm(num, den, regress_min),
         vorp_prior2 = z(vorp_l1) + z(vorp_l2),
         honors_star = coalesce(hon_l1, FALSE) | coalesce(hon_l2, FALSE),
         age_bin = pmin(pmax(age, 20), 37))

# Aging curve: harmonic-mean-minutes weighted mean BPM change by age at t.
curve <- b |>
  filter(!is.na(mp_l1), !is.na(bpm), !is.na(bpm_l1), !cy_any, mp > 0, mp_l1 > 0) |>
  mutate(delta = bpm - bpm_l1, hw = 2 / (1 / mp + 1 / mp_l1)) |>
  group_by(age_bin) |>
  summarise(age_adj = sum(delta * hw) / sum(hw), pairs = n(), .groups = "drop") |>
  arrange(age_bin)

b <- b |>
  left_join(select(curve, age_bin, age_adj), by = "age_bin") |>
  mutate(exp_bpm = exp_bpm_raw + age_adj,
         resid_bpm = bpm - exp_bpm) |>
  group_by(season) |>
  mutate(vorp_pct = rank(vorp_prior2, ties.method = "average") / n()) |>
  ungroup() |>
  mutate(tier = tier_of(vorp_pct))

out <- file.path(ROOT, "output")
write_csv(curve, file.path(out, "aging_curve_r.csv"))
write_csv(b |> select(bbref_id, season, exp_bpm_raw, age_adj, exp_bpm, resid_bpm, vorp_pct, tier, honors_star) |>
            arrange(bbref_id, season), file.path(out, "panel_r.csv"), na = "")
write_csv(tibble(quantity = c("regression_minutes", "fit_rows"), value = c(regress_min, nrow(fit_rows))),
          file.path(out, "panel_scalars_r.csv"))
write_csv(b, file.path(ROOT, "data", "panel_r.csv"), na = "")
