# Pure helpers for the contract-year study's R implementation.
#
# Deterministic and free of I/O so tests/R/test_functions.R can check them
# against hand-worked fixtures. The Python twins live in python/10 and
# python/11; python/12_reconcile.py checks the two implementations agree.

# Minutes-weighted mean.
wmean <- function(x, w) sum(x * w) / sum(w)

# Weighted prior-BPM expectation: sum(w_k m_k b_k) / (sum(w_k m_k) + R),
# NA when the player has no prior minutes. Missing lags count as zero.
expected_bpm <- function(num, den, regress_min) {
  ifelse(den > 0, num / (den + regress_min), NA_real_)
}

# Tier from the within-season VORP percentile.
tier_of <- function(pct) {
  dplyr::case_when(pct > 0.90 ~ "star", pct > 0.70 ~ "starter",
                   pct > 0.30 ~ "role", TRUE ~ "fringe")
}

# Cluster-robust SE for a no-intercept WLS of y on x (both already demeaned
# within player), matching the small-sample factor G/(G-1) * (N-1)/(N-K)
# with K = 1. Returns c(coef, se).
wls_cluster <- function(y, x, w, cluster) {
  sxx <- sum(w * x * x)
  beta <- sum(w * x * y) / sxx
  e <- y - beta * x
  score <- tapply(w * x * e, cluster, sum)
  g <- length(score)
  n <- length(y)
  # (n - 1) / (n - K) is exactly 1 when K = 1, leaving G / (G - 1).
  v <- sum(score^2) / sxx^2 * (g / (g - 1)) * ((n - 1) / (n - 1L))
  c(coef = beta, se = sqrt(v))
}

# Holm step-down adjustment (same as stats::p.adjust(p, "holm")).
holm <- function(p) stats::p.adjust(p, method = "holm")
