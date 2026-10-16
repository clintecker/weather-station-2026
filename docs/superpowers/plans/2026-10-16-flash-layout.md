# Flash Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the firmware region from 64 KB to 110 KB and give a full station a 24-hour journal, with the node-state pages at the top of flash.

**Architecture:** `App/flash_layout.h` defines the node-state pages from the top of flash down: provisioning 127, meta log 125–126, journal 55–124. One constant, `WS_FIRMWARE_PAGES` (55), sets the firmware region; the linker script and `board.mk` must agree with it, and a test checks that. `node_store` keeps its format; only its page guards and compile-time checks change. The boards need a destructive migration, because the old counter pages fall inside the new firmware region.

**Tech Stack:** C (arm-none-eabi-gcc 15.2.1, host cc), GNU ld linker script, Make, Python unittest, the literate source `node_store.lit.md` with `tools/tangle.py`.

**Spec:** `docs/superpowers/specs/2026-10-16-sixteen-stations-design.md`, section 6.1 (sub-project 1 of section 10).

## Global Constraints

- Page map (STM32WL55JC, 128 pages of 2 KB): firmware pages 0–54 (110 KB, 112,640 B); journal pages 55–124 (70 pages); meta log A page 125, B page 126; provisioning page 127.
- A full station (widest catalog, 78-byte plaintext, 96-byte slots, 21 per page) retains at least 1,440 records: (70 − 1) × 21 = 1,449.
- `node_store.lit.md` is the source of `node_store.c`. Edit the document, then run `python3 tools/tangle.py firmware/stage0-node/App/node_store.lit.md`.
- The flash budget guard stays at 90 % of the firmware region.
- Greenfield: no migration code. Boards are wiped and re-provisioned with a new key.
- No destructive board action (WIPE, re-provisioning, archiving a run directory) without Clint's explicit OK. Clint runs WIPE.
- Never re-provision a board with a key it used before the migration.
- Never commit keys, tokens or run databases (`run*/` is git-ignored).

## Review Focus

1. **Stale state after flashing.** The new journal and meta pages (55–126) hold old journal pages from the previous layout, with the same slot size. An unprovisioned board must not send them, and WIPE must erase them before provisioning. Task 3 makes WIPE a required migration step, before `PROVISION`.
2. **Counter loss means a new key.** The old meta log (pages 33–34) is now firmware, so the counter restarts at 1. Re-using the old key would repeat nonces. Task 3 provisions from a fresh gateway state directory, which generates a new key.
3. **Guard boundaries.** `prog64` and `erase_page` must refuse page 54 (the last firmware page) and accept page 55 and page 127. Task 1 Step 4 pins pages 55 and 127 through the flash model's erase counts, and the model's zero-violation rule catches any access below page 55.
4. **Shrunken host geometries.** The host sweeps build a 3-page journal. With a top-down layout, that journal starts at page 122, and the sweeps must still wrap. Task 1 runs the existing sweeps unchanged.
5. **Other images on the shared linker script.** `firmware/rangetest` uses the same `STM32WL55JCIX_FLASH.ld`. It must still build, and must stay below page 55. Task 1 builds it.

---

### Task 1: The layout in code

**Files:**
- Modify: `firmware/stage0-node/App/flash_layout.h`
- Modify: `firmware/board/nucleo-wl55jc/STM32WL55JCIX_FLASH.ld:52` (FLASH LENGTH and its comment)
- Modify: `firmware/board/nucleo-wl55jc/board.mk:5,145` (comment; `APP_FLASH_BYTES`)
- Modify: `firmware/stage0-node/Makefile:64-66` (budget comment)
- Modify: `firmware/sim_flash.h:13-22` (model range)
- Modify: `firmware/stage0-node/App/node_store.lit.md` (chunks `write-guards`, `geometry-checks`; prose tables that state page numbers, section 2), then regenerate `node_store.c`
- Modify: `firmware/test_store.c` (`checks()`: guard edges)
- Create: `tests/test_flash_layout.py`

**Interfaces:**
- Produces, in `flash_layout.h`:
  - `WS_FIRMWARE_PAGES` = 55U
  - `WS_FIRMWARE_BYTES` = `WS_FIRMWARE_PAGES * WS_PAGE_SIZE` (112,640)
  - `WS_CONFIG_PAGE` = `WS_FLASH_PAGES - 1U` (127)
  - `WS_META_PAGE_B` = 126U and `WS_META_PAGE_A` = 125U (as `WS_CONFIG_PAGE - 1U`, `- 2U`)
  - `WS_JOURNAL_PAGES` = 70U (default; host tests may still override it)
  - `WS_JOURNAL_FIRST` = `WS_META_PAGE_A - WS_JOURNAL_PAGES` (55 by default, 122 with 3 pages)
  - `WS_STATE_FIRST` = `WS_JOURNAL_FIRST`: the lowest node-state page
  - `_Static_assert(WS_JOURNAL_FIRST >= WS_FIRMWARE_PAGES, ...)` replaces "the journal runs to the last flash page".
- Produces, in `sim_flash.h`: `SIM_FIRST_PAGE` = `WS_STATE_FIRST`, `SIM_PAGES` = `WS_FLASH_PAGES - WS_STATE_FIRST`.
- Produces, in `node_store`: `STORE_PAGE_FIRST` = `WS_STATE_FIRST` and `STORE_PAGE_END` = `WS_FLASH_PAGES`. The guards accept `[STORE_PAGE_FIRST, STORE_PAGE_END)`.
- Produces, in `node_store`'s geometry checks:
  - order `WS_JOURNAL_FIRST + WS_JOURNAL_PAGES == WS_META_PAGE_A < WS_META_PAGE_B < WS_CONFIG_PAGE`;
  - `(uint64_t)WS_STATE_FIRST * WS_PAGE_SIZE >= WS_FIRMWARE_BYTES`;
  - 24 hours for the widest build: `(WS_JOURNAL_PAGES - 1U) * JOURNAL_SLOTS_PER_PAGE >= 1440U` when `WS_JOURNAL_PAGES` has its default (guard it with the same `#ifndef` the header uses, so the 3-page host sweeps still compile).

- [ ] **Step 1: Write the failing layout test** — `tests/test_flash_layout.py`, class `FlashLayout`:
  - `test_firmware_region_agrees_everywhere`: compile a tiny host program that includes `flash_layout.h` and prints `WS_FIRMWARE_BYTES WS_JOURNAL_FIRST WS_JOURNAL_PAGES WS_META_PAGE_A WS_META_PAGE_B WS_CONFIG_PAGE` (use `tests/toolchain.py`'s `CC_STRICT` and `ROOT`). Assert they are `112640 55 70 125 126 127`. Parse `LENGTH = (\d+)K` on the FLASH line of the linker script and assert `110`. Parse `APP_FLASH_BYTES \?= (\d+)` in `board.mk` and assert `112640`.
  - `test_a_full_station_keeps_24_hours`: compile with `-DWS_NODE_FIELDS=WS_FIELDS_DEFINED` (the widest catalog, as the `wide` geometry in `tests/test_store_powercut.py` builds it) and print `JOURNAL_SLOTS_PER_PAGE`. Assert that `(WS_JOURNAL_PAGES - 1) * slots >= 1440`, and that slots is 21.

- [ ] **Step 2: Run it and see it fail**

  Run: `.venv/bin/python -m unittest tests.test_flash_layout -v`
  Expected: FAIL. The values are `65536 35 93 33 34 32`, and LENGTH is 64.

- [ ] **Step 3: Implement the layout.** Edit `flash_layout.h` to the Interfaces values, with its header comment stating the page map. Set the linker FLASH `LENGTH = 110K` and comment that pages 55–127 hold node state. Set `APP_FLASH_BYTES ?= 112640`, and update the board.mk and Makefile comments. Set the `sim_flash.h` range. In `node_store.lit.md`, change the `write-guards` and `geometry-checks` chunks to the Interfaces rules, and update the section 2 page-map table and the prose that names pages 32, 33–34 and 35–127. Regenerate `node_store.c` with tangle.

- [ ] **Step 4: Pin the state-range edges.** The guards are static, so pin the edges through the flash model. In `firmware/test_store.c`'s functional summary line, add `config_erases=%u`: the count `S.page_erases[WS_CONFIG_PAGE - SIM_FIRST_PAGE]`, next to the existing `journal0_erases`. `sim_flash` already counts any access outside `[SIM_FIRST_PAGE, SIM_FIRST_PAGE + SIM_PAGES)` as a violation, and the sweeps already require zero. In `tests/test_store_powercut.py`, in the functional test that reads `journal0_erases`, assert `config_erases >= 1` (the workload runs WIPE, which erases page 127 last), `journal0_erases >= 1` (page 55 by default) and `sim_violation` absent.

- [ ] **Step 5: Run the layout test, the store sweeps and the builds**

  Run: `.venv/bin/python -m unittest tests.test_flash_layout tests.test_store_powercut tests.test_tangle tests.test_tx_machine -v`
  Expected: all PASS. The sweeps cover all three geometries: `full` (now 70 pages), `small` (3 pages, starting at page 122) and `wide`.

  Run: `make -C firmware/stage0-node ROLE=tx -j8 && make -C firmware/stage0-node ROLE=rx -j8 && make -C firmware/rangetest BUILD=build/ci -j8`
  Expected: all link. The budget lines read `of 112640 B`: TX about 51.7 %, RX about 30.9 %.

- [ ] **Step 6: Run every gate**

  Run: the CI gate list (`tools/code_shape.sh`, `tools/cppcheck.sh`, `make ... ANALYZE=1`, `make ... stack`, `make ... waits`, the full unittest discover, `make -C firmware/fuzz check`)
  Expected: all PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add firmware tests/test_flash_layout.py
  git commit -m "Flash layout: firmware 110 KB, 70-page journal (24 h for a full station), node state at the top"
  ```

### Task 2: Documents that state the page map

**Files:**
- Modify: `docs/firmware-budget.md` (the summary table, the flash-map diagram, "the linker script limits the firmware to pages 0–31")
- Modify: `docs/protocol-stack.md:233-238` (page table, "a firmware update programs only pages 0–31")
- Modify: `docs/lora-firmware-update-study.md:71` (flash map now)
- Modify: `docs/power-of-ten.md:195` (guard range)
- Modify: `firmware/stage0-node/README.md:41,344-354` (survival note, map diagram, table)
- Modify: `firmware/rangetest/README.md:52-53`
- Modify: `docs/failure-modes.md` (the open issue "Code space for the final station": move its result into the code-space row and close it)

**Interfaces:**
- Consumes: the page map from Task 1's Interfaces.

- [ ] **Step 1: Find every stale page reference**

  Run: `git grep -nE "pages 0[-–]31|page 32|pages 33[-–]34|pages 35[-–]127|32[-–]127|64 KB" -- ':!vendor' ':!evidence' ':!firmware/stage0-node/RELEASES.md' ':!docs/firmware-review-2026-10-13.md'`
  Expected: the lines listed under Files, and nothing in code.

- [ ] **Step 2: Rewrite each one to the new map.** Firmware pages 0–54 (110 KB); journal 55–124 (70 pages: 24.2 h for a full station, 41.4 h for temperature and humidity); meta 125–126; provisioning 127. In the Mermaid flash maps, keep the diagram type and change only the numbers and addresses: page 55 is at 0x0801B800, page 125 at 0x0803E800, page 127 at 0x0803F800. Budget figures come from Task 1 Step 5's build output.

- [ ] **Step 3: Check the diagrams and the grep**

  Run: `node <scratchpad>/mmdcheck/check.mjs docs/firmware-budget.md firmware/stage0-node/README.md` and re-run Step 1's grep.
  Expected: `0 failed`, and the grep finds nothing outside dated records.

- [ ] **Step 4: Commit**

  ```bash
  git add docs firmware/stage0-node/README.md firmware/rangetest/README.md
  git commit -m "Docs: the new flash map (firmware 110 KB, journal 55-124, state at the top)"
  ```

### Task 3: Release and board migration

Every step that changes a board or the gateway state needs Clint's explicit OK first. Clint runs WIPE.

**Files:**
- Modify: `docs/runbook-moving-boards.md` (add "Changing the flash layout")
- Modify: `firmware/stage0-node/RELEASES.md` (the new release entry)

**Interfaces:**
- Consumes: Task 1's build, and `ws0 init`, `ws0 provision-node` and `ws0 serve` as they exist today.

- [ ] **Step 1: Write the runbook section** "Changing the flash layout" in `docs/runbook-moving-boards.md`, as a numbered procedure:
  1. Stop the gateway.
  2. Archive the old run directory.
  3. Flash RX, then TX.
  4. Clint runs `WIPE ERASE-ALL-NODE-STATE` on TX. It erases the journal pages (old journal data) and the provisioning page.
  5. `ws0 init --hardware --directory run-<new>`, which makes a new key.
  6. `ws0 provision-node --directory run-<new> --serial <TX port>`.
  7. `ws0 serve` on the new directory.

  State why: the old counter pages are now firmware, so the counter restarts. Re-using a key would repeat nonces.

- [ ] **Step 2: Cut the release.** Follow "How to cut a release" in `RELEASES.md` (clean tree, `tools/fetch-vendor.sh`, two clean builds with identical `.bin` hashes). Expected: identical hashes, TX budget about 51.7 % of 112,640 B.

- [ ] **Step 3: Ask Clint for the OK to migrate the boards.** Name the run directory to archive (`run-d6`), the new one, and say that the old key is retired.

- [ ] **Step 4: Migrate**, after the OK: Step 1's procedure, with Clint running WIPE.
  Expected:
  - TX `STATUS` shows `provisioned=1` with a new `kcv`, `epoch=1`, a counter near 1 and `kat=pass`;
  - RX `#boot` shows the new `fw=`;
  - the gateway stores epoch 1 seq 0, 1, 2 as valid;
  - no `counter-regression` lines appear.

- [ ] **Step 5: Record the release** in `RELEASES.md`: hashes, budget, stack, migration record, bench check.

- [ ] **Step 6: Commit and push**

  ```bash
  git add docs/runbook-moving-boards.md firmware/stage0-node/RELEASES.md
  git commit -m "Release <id>: flash layout (firmware 110 KB, 24 h journal); boards migrated with a new key"
  git push origin master
  ```
