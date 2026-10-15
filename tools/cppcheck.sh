#!/bin/sh
# Cppcheck over our firmware C (CI host job; run locally the same way): a second static analyser next
# to GCC's -fanalyzer (Power of Ten rule 10, docs/power-of-ten.md). Any finding fails. Vendor code,
# ST-generated board files and the host test programs are out of scope.
# Needs cppcheck from requirements-dev.txt (the pinned cppcheck wheel: Cppcheck 2.22.0).
# Findings we accept are suppressed inline, next to the code, each with its reason
# (/* cppcheck-suppress <id> ; why */): ST's callback signatures, which we cannot make const.
set -eu
cd "$(dirname "$0")/.."
cppcheck --version
cppcheck --std=c11 --enable=warning,style,performance,portability --check-level=exhaustive --inline-suppr \
  --error-exitcode=1 --quiet --suppress=missingIncludeSystem --suppress=missingInclude --suppress=unusedFunction \
  -I firmware/common -I firmware/stage0-node/App -I firmware \
  -DWS_FW_VERSION='"cppcheck"' -DWS_FW_BUILD_ID=0UL \
  --template='{file}:{line}: {severity} {id}: {message}' \
  firmware/stage0-node/App firmware/common firmware/stage0.c
echo "cppcheck: OK (no findings)"
