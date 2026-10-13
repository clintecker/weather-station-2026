# G7 part A: reset during flash writes (2026-10-13)

Test for failure-modes.md gap G7 (E2–E6). Tool: `tools/power_cut_test.py --method reset`. In each cycle the tool
waits for the TX board (board A) to boot and records its `#status` line. It then starts `TEST-FLASH-STORM`
(continuous journal, ACK-word and counter-reservation writes), lets it run for a random 0.3–4.0 s, and asserts
NRST through the ST-LINK (openocd). A reset aborts a flash program/erase the way a power cut does (RM0453).
Each boot is checked for:
the counter never going back, the boot epoch strictly increasing, and the self-test passing. At the end the
gateway database is checked for storm records.

## Files

- `cycles.jsonl`: one line per cycle (cycles 0–70, 71 boots). Each line holds the boot lines, parsed `status`,
  `run_s` (storm time before the reset), the `storm` progress lines and `max_ctr_used`.
- `summary.json`: the verdict (PASS). Planned 200 cycles, stopped by Clint after 70. All reset causes `pin`.
  21 boots handled ECC (torn) faults, at most 3 torn slots were burned per boot, and 0 storm rows reached the gateway.
  Unlike the tool's own output it has no `started`/`finished` fields, and its `method` text is descriptive,
  so it appears to have been edited by hand.

## What the files show

- Firmware `db4ceafe9de0-dirty` on every boot. Epoch runs from 25 (cycle 0) to 95 (cycle 70), strictly increasing.
- Mean `run_s` is 2.0 s, consistent with the tool's default 0.3–4.0 s range.

## Open questions

- **Cycle time:** `summary.json` says "~8 s/cycle". The node's own `utc` in the status lines runs from
  1791863763 (03:56:03Z, cycle 0) to 1791864031 (04:00:31Z, cycle 70), which is 268 s for 70 cycles,
  about 3.8 s per cycle. The difference is unexplained. The node clock may not advance normally across resets,
  or the 8 s may include host-side time not reflected in the node clock.
- **Not covered:** true power removal (slow supply decay, brown-out), which is G7 part B, deferred.
  The bench hubs do not really switch VBUS.
