#!/bin/sh
# Reproduce the 117 tutorial experiment analysis from the raw CSVs.
# See PIPELINE.md for what each step does and where the raw files come from.
#
# Usage:  ./run_pipeline.sh [EXPECTED_COMBINED_SHA256]
#
# With an expected digest, the run stops unless the raw data match it.
set -eu

cd "$(dirname "$0")"
DATA=../Data
CANON=$DATA/canonical
RESULTS=../Results
DRAWS=1000000
mkdir -p "$CANON" "$RESULTS"

echo "== Environment"
python3 -c 'import sys, numpy, scipy; print(f"python {sys.version.split()[0]}, numpy {numpy.__version__}, scipy {scipy.__version__}")' \
    | tee "$RESULTS/environment.txt"

echo "== Step 0: fingerprint the raw data"
if [ $# -ge 1 ]; then
    python3 hash_raw_data.py --data-dir "$DATA" --check "$1" | tee "$RESULTS/raw-sha256.txt"
else
    python3 hash_raw_data.py --data-dir "$DATA" | tee "$RESULTS/raw-sha256.txt"
fi

echo "== Step 1: canonicalize"
python3 canonicalize_data.py --data-dir "$DATA" --outdir "$CANON" \
    | tee "$RESULTS/canonicalize.log"

echo "== Step 2a: fixed-effects analysis of the block design"
python3 block_factor_analysis.py --input "$CANON/grades-with-pretest.csv" \
    --include "$CANON/completed.csv" \
    --latex "$RESULTS/factor-table.tex" > "$RESULTS/factor.log"
cat "$RESULTS/factor-table.tex"

echo "== Step 2b: randomization test ($DRAWS draws)"
python3 randomization_test.py --input "$CANON/grades-with-pretest.csv" \
    --include "$CANON/completed.csv" -N "$DRAWS" \
    --latex "$RESULTS/randomization-table.tex" > "$RESULTS/randomization.log"
cat "$RESULTS/randomization-table.tex"

echo "== Fingerprint the outputs"
python3 hash_raw_data.py "$CANON/grades-with-pretest.csv" \
    "$CANON/completed.csv" "$CANON/consent-matches.csv" \
    "$RESULTS/factor-table.tex" "$RESULTS/randomization-table.tex" \
    | tee "$RESULTS/output-sha256.txt"
