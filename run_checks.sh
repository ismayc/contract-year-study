#!/bin/bash
# Every check in this study: unit tests, the cross-source gate, both
# implementations of the analysis, the R vs Python reconciliation gate, and
# the findings drift check. Non-zero exit on any failure. PY overrides the
# interpreter (the family orchestrator sets it to a shared venv).
#
# The harvest and labeling steps (01-09) need the local, gitignored raw pages
# and are not rerun here; this chain starts from the committed derived tables.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-../.venv/bin/python}

echo "=== unit tests: Python (pytest) ==="
$PY -m pytest tests/python -q

echo
echo "=== unit tests: R (testthat) ==="
Rscript tests/R/run_tests.R

echo
echo "=== cross-source gate: Basketball-Reference vs stats.nba.com ==="
$PY python/03_reconcile_sources.py | tail -1

echo
echo "=== analysis: Python ==="
$PY python/10_build_panel.py | head -1
$PY python/11_contract_effect.py > /dev/null
$PY python/10_build_panel.py --fixed-1000 | head -1
$PY python/11_contract_effect.py --tag fixed1000 > /dev/null

echo
echo "=== analysis: R ==="
Rscript R/10_build_panel.R
Rscript R/11_contract_effect.R

echo
echo "=== reconciliation: R vs Python ==="
$PY python/12_reconcile.py | tail -1

echo
echo "=== findings: README numbers regenerate from outputs ==="
$PY python/13_findings.py --check
