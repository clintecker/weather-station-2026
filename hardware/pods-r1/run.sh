#!/bin/sh
# Check everything that exists so far in hardware/pods-r1. Exits non-zero on the first failed step.
# Later tasks append their own steps (layout checks, CAD) below.
set -e
cd "$(dirname "$0")"
echo "== dimension table in README.md"
python3 sources.py --check
echo "== pods-r1: every check passes"
