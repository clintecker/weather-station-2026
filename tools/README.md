# Tools

Run from the repository root with the project virtualenv (`.venv/bin/python`). Boards are found by ST-LINK serial
number where the tool supports it, because `/dev/cu.usbmodem*` names change between USB sockets and machines.

| File | Purpose | Usage | More |
|---|---|---|---|
| `fetch-vendor.sh` | Clone pinned STM32CubeWL v1.6.0 and its submodules (HAL, CMSIS, BSP, SubGHz_Phy, Mbed TLS) into `vendor/`. Re-running verifies the pinned commits. Needed for firmware builds and for 7 C-vs-Python crypto tests. | `sh tools/fetch-vendor.sh` | `docs/CONTEXT-PACK.md` §5 |
| `status.py` | Print the gateway's `/v1/status` JSON without echoing the API token. | `.venv/bin/python tools/status.py --directory run-office` (default `run-demo`) | `README.md` |
| `h01_report.py` | H01 scorer: the verdict for a time window, computed from a gateway database (opened read-only). With `--output`, writes `report.json` and `report.md` to a new directory. | `.venv/bin/python tools/h01_report.py --db run-office/observations.sqlite3 --station station-01 --start 2026-10-15T00:00:00Z --hours 24 --output evidence/h01-2026-10-15` (`--db` defaults to `run-hw/observations.sqlite3`) | `docs/H01-checklist.md` |
| `power_cut_test.py` | G7 test of the TX flash state: start `TEST-FLASH-STORM`, then cut power (`--method power`, uhubctl) or pulse NRST (`--method reset`). Each boot is checked for counter and epoch monotonicity. `--check` does one cut to verify that the hub really removes VBUS. | `.venv/bin/python tools/power_cut_test.py --method reset --serial-number 003B00194142500E20353451 --cycles 200 --gateway-db run-office/observations.sqlite3 --output evidence/power-cut-<date>` | `docs/failure-modes.md` G7; `evidence/g7-reset-during-write-2026-10-13/` |
| `rangetest_log.py` | Log a `firmware/rangetest` board's console (both link directions, settings, spot marks) to CSV. Reconnects after USB dropouts. | `.venv/bin/python tools/rangetest_log.py 0016001E4142500E20353451 evidence/<run>/rangetest.csv` | `firmware/rangetest/README.md` |
| `nucleo/at.py` | Send AT commands to a board running ST's factory Concentrator firmware (console 9600 8N1). | `python3 tools/nucleo/at.py /dev/cu.usbmodemXXXX "AT+VER=?"` | `docs/hardware/nucleo-wl55jc-bringup.md` |
| `nucleo/trace-swd-disable.tcl` | OpenOCD script: a watchpoint on `GPIOA_MODER` writes, used to find where the factory firmware disables SWD. The script runs `init` itself. | `openocd -f interface/stlink.cfg -f target/stm32wlx.cfg -f tools/nucleo/trace-swd-disable.tcl` | `docs/hardware/nucleo-wl55jc-bringup.md` (SWD) |
| `deploy/macos/install.sh` | Install, remove or inspect the launchd agent `com.clintecker.weatherstation.gateway`. The agent runs `ws0 serve --serial-number <RX>`, restarts if it exits, and logs to `<state-dir>/serve.out`. | `tools/deploy/macos/install.sh install [state-dir] [rx-stlink-serial]` \| `uninstall` \| `status` (defaults: `run-hw`, `0016001E4142500E20353451`) | `docs/CONTEXT-PACK.md` §4 |
| `deploy/macos/com.clintecker.weatherstation.gateway.plist.in` | launchd template filled in by `install.sh` (`@REPO@`, `@STATE@`, `@RX_SERIAL@`). | Not run directly | |
| `deploy/linux/ws0-gateway.service` | systemd unit for an always-on Linux gateway. | Copy to `/etc/systemd/system/`, set `User` and paths, then `systemctl daemon-reload && systemctl enable --now ws0-gateway` | `firmware/stage0-node/README.md` |
