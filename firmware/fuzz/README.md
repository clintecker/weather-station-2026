# Fuzzing the node's input parsers

These targets cover the code that reads input from outside the node: radio replies and console
lines. They feed it malformed input under AddressSanitizer and UndefinedBehaviorSanitizer, and
check properties that must hold for every input.

| Target | Code under test | Properties beyond "no memory error" |
|---|---|---|
| `reply` | The draft-5 envelope (`firmware/common/ws_frame.c`): `ws_open_reply` on any bytes from the air, and `ws_seal_kind` with fuzzer-chosen station, counter, kind and plaintext, biased to the 16-bit and 40-bit limits | Nothing opens except the two genuine self-test frames (`corpus/reply/`); out-of-range values are refused with the output wiped, never truncated into the header (that would repeat a nonce); accepted frames carry exactly the spec's header, and ACK/NACKs open again to the same values |
| `provision` | `ws_parse_provision` (`firmware/stage0.c`): `PROVISION` arguments | On success: station 1–65,535 (the draft-5 header holds 2 bytes), epoch floor in range, the key equals the 32 hex digits typed, only digits after the optional space |
| `console` | `ws_line_feed`, `ws_hex_decode`, `ws_host_reply_ok`, `ws_air_frame_ok` (`firmware/common/ws_console.c`), then `ws_parse_provision`: a raw UART byte stream as either board receives it | Lines are 1–256 bytes with no `\n`/`\r`; the line buffer is cleared after each line; a hex decode is exactly half the line; only a 33-byte version-5 ACK/NACK passes the RX downstream check, and only valid observation and health-report lengths the upstream one |
| `obs` | `ws_obs_encode` (`firmware/common/ws_obs.c`): arbitrary records, codes biased to edges, INVALID and CALM | The encoder accepts exactly the records an independent copy of the spec's catalog accepts; accepted records have the spec's length, header and big-endian fields |

The boards run the same functions (`App/console.c`, `App/app_rx.c`, `App/app_tx.c`).

## Run

```sh
make -C firmware/fuzz check                 # any cc with ASan/UBSan: corpus + 200,000 mutated inputs per target
make -C firmware/fuzz check RUNS=5000000 SEED=7
make -C firmware/fuzz libfuzzer             # coverage-guided; needs clang with libFuzzer (Linux, Homebrew llvm)
firmware/fuzz/build/libfuzzer-console build/new-corpus firmware/fuzz/corpus/console -max_total_time=600
```

`tests/test_fuzz.py` runs the standalone drivers (20,000 mutated inputs each; `WS_FUZZ_RUNS` raises
that) on every test run. CI also runs each libFuzzer target for 60 s on Linux.

The standalone driver (`standalone.c`) exists because Apple clang does not ship libFuzzer. It is
not coverage-guided: it mutates the corpus from a fixed seed, so a failure reproduces with the
same `-seed`. Two planted bugs checked that the harness works. Removing the length bound in
`ws_hex_decode` gave an ASan stack overflow within 200,000 inputs for each of three seeds. Making
`ws_open_reply` skip the tag check broke the `reply` property at once.

Draft 5 (2026-10-14), also checked with planted bugs:
- Removing the 2^40 counter check from `ws_seal_kind` broke the `reply` property within 200,000 inputs.
- A range check off by one in `ws_obs.c` broke the `obs` property. The first version of `obs` missed it,
  because its oracle called the encoder's own range check. It now keeps its own copy of the spec's ranges.

When checking a planted bug, delete the built target first: macOS ships GNU Make 3.81, whose
timestamps have 1-second resolution, so an edit in the same second as the last build is not rebuilt.

Checked 2026-10-13: Ubuntu 24.04, clang 18.1.3. libFuzzer ran 20 s per target, about 36 million
inputs in all, with no findings. The standalone drivers pass under Apple clang 17 and GCC.

## Add a target

Write `fuzz_<name>.c` with `LLVMFuzzerTestOneInput`, use `FUZZ_CHECK` for properties, add
`SRC_<name>` and the name to `TARGETS` in the `Makefile`, put seeds in `corpus/<name>/`, and add a
test method to `tests/test_fuzz.py`.
