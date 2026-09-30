# Run the R unit tests: Rscript tests/R/run_tests.R (from the study root).
suppressPackageStartupMessages(library(testthat))
root <- normalizePath(".")
Sys.setenv(STUDY_ROOT = root)
res <- test_dir(file.path(root, "tests", "R"), reporter = "summary", stop_on_failure = TRUE)
