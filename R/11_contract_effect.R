# Contract-year study: effect estimates, independent R / tidyverse implementation.
#
# Mirrors the definitions in docs/design.md and python/11_contract_effect.py:
# contract year (cy_strict) vs guaranteed non-contract year (nc_strict),
# seasons with 250+ minutes and an expectation, per era x tier:
#   diff     minutes-weighted mean residual BPM, contract year minus comparison,
#            with a player-clustered bootstrap interval
#   fe       within-player WLS (weights = minutes), SE clustered by player
#   placebo  diff after shuffling the flag within each player's seasons
# plus sensitivities (broad definition, high-confidence contract years,
# honors-based stars), Holm-corrected secondary outcomes, and the
# post-contract season.
#
# The bootstrap and placebo use R's RNG, so they are reconciled against the
# Python run by tolerance, not equality (python/12_reconcile.py).
#
# Writes output/effect_{primary,sensitivity,secondary,post}_r.csv
# Run:  Rscript R/11_contract_effect.R   (after R/10_build_panel.R)

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(purrr)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")
source(file.path(ROOT, "R", "functions.R"))

set.seed(20260929)
N_BOOT <- 2000
N_PLACEBO <- 500
MIN_MP <- 250
ERAS <- tibble(era = c("1974-1976", "1977-1988", "1989-1999", "2000-2026"),
               lo = c(1974, 1977, 1989, 2000), hi = c(1976, 1988, 1999, 2026))
TIERS <- c("star", "starter", "role", "fringe", "all")
SECONDARY <- c("mpg", "games", "ts_pct", "usg_pct", "ws_per_48", "per")

panel <- read_csv(file.path(ROOT, "data", "panel_r.csv"), show_col_types = FALSE, guess_max = 100000) |>
  select(bbref_id, season, mp, age_bin, resid_bpm, tier, honors_star)
labels <- read_csv(file.path(ROOT, "data", "contract_labels.csv"), show_col_types = FALSE, guess_max = 100000) |>
  select(bbref_id, season, cy_strict, cy_broad, nc_strict, confidence)
stats <- read_csv(file.path(ROOT, "data", "bbref_player_seasons.csv"), show_col_types = FALSE, guess_max = 100000) |>
  select(bbref_id, season, games, ts_pct, usg_pct, ws_per_48, per)
panel <- panel |>
  left_join(labels, by = c("bbref_id", "season")) |>
  left_join(stats, by = c("bbref_id", "season")) |>
  mutate(across(c(cy_strict, cy_broad, nc_strict), \(x) coalesce(x, FALSE)),
         honors_tier = if_else(honors_star, "star", "non_star"))

# ---- estimators -------------------------------------------------------------

diff_boot <- function(df) {
  if (!any(df$cy) || all(df$cy)) return(NULL)
  y <- df$resid; w <- df$mp; f <- df$cy
  pid <- factor(df$bbref_id)
  G <- nlevels(pid)
  agg <- function(v) as.numeric(tapply(v, pid, sum))
  s_cy <- agg(y * w * f); w_cy <- agg(w * f); s_nc <- agg(y * w * !f); w_nc <- agg(w * !f)
  draws <- rmultinom(N_BOOT, G, rep(1 / G, G))  # G x N_BOOT player counts
  boot <- colSums(draws * s_cy) / colSums(draws * w_cy) - colSums(draws * s_nc) / colSums(draws * w_nc)
  boot <- boot[is.finite(boot)]
  tibble(diff = wmean(y[f], w[f]) - wmean(y[!f], w[!f]),
         ci_lo = unname(quantile(boot, 0.025)), ci_hi = unname(quantile(boot, 0.975)),
         n_cy = sum(f), n_nc = sum(!f), players = G,
         mean_cy = wmean(y[f], w[f]), mean_nc = wmean(y[!f], w[!f]))
}

fe <- function(df) {
  x <- df |>
    group_by(bbref_id) |>
    mutate(f = as.numeric(cy),
           y_d = resid - sum(resid * mp) / sum(mp),
           f_d = f - sum(f * mp) / sum(mp)) |>
    filter(max(abs(f_d)) > 1e-12) |>
    ungroup()
  if (nrow(x) < 20 || n_distinct(x$bbref_id) < 10) return(tibble(fe_coef = NA_real_, fe_se = NA_real_, fe_players = NA_integer_))
  est <- wls_cluster(x$y_d, x$f_d, x$mp, x$bbref_id)
  tibble(fe_coef = est[["coef"]], fe_se = est[["se"]], fe_players = n_distinct(x$bbref_id))
}

placebo <- function(df) {
  o <- order(df$bbref_id)
  pid <- df$bbref_id[o]; y <- df$resid[o]; w <- df$mp[o]; f <- df$cy[o]
  vals <- map_dbl(seq_len(N_PLACEBO), \(i) {
    g <- f[order(pid, runif(length(f)))]  # within-player permutation
    if (!any(g) || all(g)) return(NA_real_)
    wmean(y[g], w[g]) - wmean(y[!g], w[!g])
  })
  vals <- vals[!is.na(vals)]
  tibble(placebo_mean = mean(vals), placebo_sd = sqrt(mean((vals - mean(vals))^2)))
}

analysis_sample <- function(p, cy_col, extra = NULL) {
  s <- p |> filter(mp >= MIN_MP, !is.na(resid_bpm), .data[[cy_col]] | nc_strict)
  if (!is.null(extra)) s <- filter(s, !!extra)
  mutate(s, resid = resid_bpm, cy = .data[[cy_col]])
}

cells <- function(s, tier_col, tiers) {
  pmap(ERAS, \(era, lo, hi) {
    e <- filter(s, season >= lo, season <= hi)
    map(tiers, \(t) list(era = era, tier = t,
                         df = if (t == "all") e else filter(e, .data[[tier_col]] == t)))
  }) |> list_flatten()
}

# ---- primary ------------------------------------------------------------------

prim <- map(cells(analysis_sample(panel, "cy_strict"), "tier", TIERS), \(c) {
  r <- diff_boot(c$df)
  if (is.null(r)) return(NULL)
  bind_cols(tibble(spec = "strict", era = c$era, tier = c$tier), r, fe(c$df), placebo(c$df))
}) |> list_rbind()
write_csv(prim, file.path(ROOT, "output", "effect_primary_r.csv"), na = "")

# ---- sensitivity --------------------------------------------------------------

specs <- list(
  list(name = "broad", cy = "cy_broad", extra = NULL, tier_col = "tier", tiers = TIERS),
  # High confidence restricts the contract-year group only.
  list(name = "strict_high_conf", cy = "cy_strict", extra = quote(!cy_strict | confidence == "high"),
       tier_col = "tier", tiers = TIERS),
  list(name = "strict_honors_tier", cy = "cy_strict", extra = NULL, tier_col = "honors_tier",
       tiers = c("star", "non_star")))
sens <- map(specs, \(sp) {
  s <- analysis_sample(panel, sp$cy, sp$extra)
  map(cells(s, sp$tier_col, sp$tiers), \(c) {
    r <- diff_boot(c$df)
    if (is.null(r)) return(NULL)
    bind_cols(tibble(spec = sp$name, era = c$era, tier = c$tier), r, fe(c$df))
  }) |> list_rbind()
}) |> list_rbind()
write_csv(sens, file.path(ROOT, "output", "effect_sensitivity_r.csv"), na = "")

# ---- secondary outcomes -------------------------------------------------------

p2 <- panel |> mutate(mpg = mp / games)
lag1 <- p2 |> transmute(bbref_id, season = season + 1, across(all_of(SECONDARY), .names = "{.col}_l1"))
p2 <- left_join(p2, lag1, by = c("bbref_id", "season"))
sec <- map(SECONDARY, \(v) {
  q <- p2 |> mutate(chg = .data[[v]] - .data[[paste0(v, "_l1")]])
  ag <- q |> filter(!cy_broad, !cy_strict, !is.na(chg)) |>
    group_by(age_bin) |> summarise(age_chg = sum(chg * mp) / sum(mp), .groups = "drop")
  q <- q |> left_join(ag, by = "age_bin") |> mutate(resid_bpm = chg - age_chg)
  s <- analysis_sample(q, "cy_strict") |> filter(is.finite(resid))
  map(cells(s, "tier", TIERS), \(c) {
    r <- diff_boot(c$df)
    if (is.null(r)) return(NULL)
    se <- (r$ci_hi - r$ci_lo) / (2 * 1.96)
    bind_cols(tibble(outcome = v, era = c$era, tier = c$tier), r,
              tibble(p_boot_normal = if (se > 0) 2 * (1 - pnorm(abs(r$diff) / se)) else NA_real_))
  }) |> list_rbind()
}) |> list_rbind() |>
  group_by(era, tier) |> mutate(p_holm = holm(p_boot_normal)) |> ungroup()
write_csv(sec, file.path(ROOT, "output", "effect_secondary_r.csv"), na = "")

# ---- post-contract season -----------------------------------------------------

nxt <- panel |> transmute(bbref_id, season = season - 1, resid_next = resid_bpm, mp_next = mp)
pp <- panel |>
  filter(mp >= MIN_MP, !is.na(resid_bpm), cy_strict | nc_strict, season < 2026) |>
  left_join(nxt, by = c("bbref_id", "season"))
post <- pmap(ERAS, \(era, lo, hi) {
  map(TIERS, \(t) {
    d <- filter(pp, season >= lo, season <= hi)
    if (t != "all") d <- filter(d, tier == t)
    map(list(contract_year = TRUE, comparison = FALSE), \(g) filter(d, cy_strict == g)) |>
      imap(\(g, name) {
        if (nrow(g) == 0) return(NULL)
        nx <- filter(g, !is.na(resid_next), mp_next >= MIN_MP)
        tibble(era = era, tier = t, group = name, n = nrow(g),
               share_played_next = mean(!is.na(g$mp_next)), n_next_250 = nrow(nx),
               resid_next = if (nrow(nx)) wmean(nx$resid_next, nx$mp_next) else NA_real_)
      }) |> list_rbind()
  }) |> list_rbind()
}) |> list_rbind()
write_csv(post, file.path(ROOT, "output", "effect_post_r.csv"), na = "")

cat(sprintf("R effects: %d primary cells, %d sensitivity cells, %d secondary rows, %d post rows\n",
            nrow(prim), nrow(sens), nrow(sec), nrow(post)))
