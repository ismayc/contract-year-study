source(file.path(Sys.getenv("STUDY_ROOT", "."), "R", "functions.R"))

test_that("wmean weights by minutes", {
  expect_equal(wmean(c(1, 3), c(1, 3)), 2.5)
})

test_that("expected_bpm shrinks toward zero and is NA without prior minutes", {
  # 1,000 weighted minutes at +4 BPM, 500 regression minutes: 4000 / 1500.
  expect_equal(expected_bpm(4000, 1000, 500), 4000 / 1500)
  expect_true(is.na(expected_bpm(0, 0, 500)))
})

test_that("tier_of uses the pre-specified cutoffs", {
  expect_equal(tier_of(c(0.95, 0.90, 0.75, 0.70, 0.5, 0.30, 0.1)),
               c("star", "starter", "starter", "role", "role", "fringe", "fringe"))
})

test_that("wls_cluster matches a hand-worked two-cluster example", {
  # Two players, x and y already demeaned, unit weights.
  y <- c(1, -1, 2, -2); x <- c(1, -1, 1, -1); w <- rep(1, 4); g <- c("a", "a", "b", "b")
  est <- wls_cluster(y, x, w, g)
  # beta = sum(xy)/sum(x^2) = 6/4; residuals (-0.5, 0.5, 0.5, -0.5);
  # cluster scores: a = 1*-0.5 + -1*0.5 = -1, b = 0.5 + 0.5 = 1;
  # V = (1 + 1) / 4^2 * G/(G-1) = 2/16 * 2 = 0.25.
  expect_equal(est[["coef"]], 1.5)
  expect_equal(est[["se"]], 0.5)
})

test_that("holm matches p.adjust", {
  p <- c(0.01, 0.04, 0.03)
  expect_equal(holm(p), c(0.03, 0.06, 0.06))
})
