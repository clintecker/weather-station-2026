#!/bin/sh
# The CI gates (.github/workflows/ci.yml), run locally from the repository root; one line per gate.
# Not here: the libFuzzer step (it needs a clang with libFuzzer; CI runs it). Added here: a 1M-run
# standalone fuzz of every target and the Power of Ten rule 1 grep. Works on macOS and Linux.
# Usage: tools/gates.sh   (exit status 0 only if every gate passes)
R=$(cd "$(dirname "$0")/.." && pwd); cd "$R" || exit 1
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export PATH="${WS_GATES_PATH:+$WS_GATES_PATH:}$R/.venv/bin:$PATH" WS_REQUIRE_VENDOR=1 WS_REQUIRE_CC=1   # as CI: a skip fails
# Tools CI installs from requirements-dev.txt: if the virtualenv lacks one, run the pinned version through uvx.
mkdir -p "$T/bin"; export PATH="$PATH:$T/bin"
for tool in lizard cppcheck; do
  command -v "$tool" >/dev/null && continue
  pin=$(grep -i "^$tool==" requirements-dev.txt | awk '{print $1}')
  printf '#!/bin/sh\nexec uvx --from %s %s "$@"\n' "$pin" "$tool" > "$T/bin/$tool"; chmod +x "$T/bin/$tool"
done
fails=0
gate() { name=$1; shift; if out=$("$@" 2>&1); then echo "PASS  $name"; else echo "FAIL  $name"; echo "$out" | tail -25; fails=$((fails + 1)); fi; }
gate "ruff" ruff check
gate "code shape (lizard, jscpd, loop bounds, tangle, registry)" tools/code_shape.sh
gate "cppcheck" tools/cppcheck.sh
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }   # Linux, macOS
twice() {
  cd firmware/stage0-node || return 1
  for pass in 1 2; do make clean >/dev/null; make ROLE=rx -j8 >/dev/null || return 1; make ROLE=tx -j8 > "$T/tx.log" || { cat "$T/tx.log"; return 1; }
    sha256 build/rx/stage0-rx.bin build/tx/stage0-tx.bin > "$T/bin-$pass.sha256"; done
  grep "flash budget" "$T/tx.log"; diff "$T/bin-1.sha256" "$T/bin-2.sha256"
}
gate "two clean builds, identical .bin (budget, no heap)" twice
gate "bench firmware (rangetest)" make -C firmware/rangetest BUILD=build/ci -j8
gate "bench firmware (i2cscan)" make -C firmware/i2cscan BUILD=build/ci -j8
bl() { make -C firmware/benchlink ROLE=tx BUILD=build/ci-tx -j8 && make -C firmware/benchlink ROLE=rx BUILD=build/ci-rx -j8; }
gate "bench firmware (benchlink)" bl
an() { cd firmware/stage0-node && make ROLE=rx ANALYZE=1 BUILD=build/analyze-rx -j8 && make ROLE=tx ANALYZE=1 BUILD=build/analyze-tx -j8; }
gate "gcc -fanalyzer" an
st() { cd firmware/stage0-node && make ROLE=rx BUILD=build/analyze-rx stack && make ROLE=tx BUILD=build/analyze-tx stack; }
gate "stack bound" st
wt() { cd firmware/stage0-node && make ROLE=rx BUILD=build/analyze-rx waits && make ROLE=tx BUILD=build/analyze-tx waits; }
gate "no blocking waits" wt
gate "unit tests (with firmware C)" python -m unittest discover -s tests
fz() {
  n=$(make -s --no-print-directory -C firmware/fuzz targets | wc -w | tr -d ' ')
  rm -rf firmware/fuzz/build && make -C firmware/fuzz check RUNS=1000000 | grep -c "fuzz ok" | grep -qx "$n"
}
gate "fuzz (standalone, 1M runs per target)" fz
p10() { ! grep -rnE "\bgoto\b|\bsetjmp\b|\blongjmp\b" firmware/stage0-node/App firmware/common firmware/stage0.c firmware/stage0.h; }
gate "Power of Ten rule 1 (no goto/setjmp in scope)" p10
[ "$fails" -eq 0 ]
