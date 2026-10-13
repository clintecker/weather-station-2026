# Runbook: moving the boards between gateways

Use this when the TX/RX boards move between machines (for example office ↔ home). Written
2026-10-13; every rule below is tied to code so it can be re-checked.

## The rule that matters

A TX key may only be used with counters that only go up. The AES-CCM nonce is
kind + station ID + the 64-bit transmission counter (`firmware/common/ws_frame.c:15`,
`docs/protocol.md`). `WIPE ERASE-ALL-NODE-STATE` erases the key, counters and journal, so the
counter restarts at 1 (`App/node_store.h`: `store_wipe`; observed `ctr=1` after the 2026-10-13
wipe). `PROVISION … [epoch_floor]` raises only the **epoch** (`App/node_store.c`,
`store_epoch_floor`), which keeps observation identities unique (gap G5). It does not raise the
counter.

| After a WIPE, provision with… | Safe? |
|---|---|
| a **new** key (`ws0 init --hardware` into a new directory) | Yes |
| a key TX has used before (for example `run-hw`'s) | **No**: repeats nonces already sent on air |

A run directory holds the key (`gateway.json`), the observation database and the gateway's own
nonce state. It is git-ignored (`run*/`). Move it only by a private route (AirDrop, USB stick),
never git, chat or email.

## Know which key TX has

```sh
.venv/bin/python -m serial.tools.list_ports -v            # TX = SER=003B00194142500E20353451
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodem<TX> 115200
#   type STATUS; read kcv=… (Ctrl-] quits)
```

Known key check values: home `run-hw` = `bf886a`; office `run-office` (2026-10-13) = `b7142e`.
The gateway's key check value is `key_check()` of `gateway.json`'s key (`ws0/__main__.py`).

## Options when the boards move

**A. Move the gateway with the key (no re-provisioning).** Run the gateway on the machine that
holds the matching run directory, wherever the boards are:

```sh
.venv/bin/python -m ws0 serve --directory run-office --serial-number 0016001E4142500E20353451
# or keep it running unattended (LaunchAgent; replaces any existing one):
tools/deploy/macos/install.sh install run-office 0016001E4142500E20353451
```

**B. Copy the run directory to the other machine** (private route), then point that machine's
gateway at it: `tools/deploy/macos/install.sh install <copied-dir> 0016001E4142500E20353451`.
Stop any other gateway for the same RX first: only one process can hold RX's port, and a gateway
with the wrong key rejects every frame.

**C. New key.** `ws0 init --hardware --station station-01 --station-id 1 --directory run-<new>`,
then `WIPE ERASE-ALL-NODE-STATE` on TX, then
`ws0 provision-node --directory run-<new> --serial /dev/cu.usbmodem<TX>`. Readings start a new
history in the new directory.

## Checks after any move

- `STATUS` on TX shows `provisioned=1` and the expected `kcv`.
- The gateway log shows frames accepted, none rejected: `tools/status.py --directory <dir>`
  (`accepted_this_process` rises, `rejected_this_process` stays 0).
- Green LED after each blue flash on TX (ACK received).

## Bench notes

- A USB dropout of about 1 s makes the ST-LINK reset its board (seen on both boards,
  `docs/hardware/nucleo-wl55jc-bringup.md`, "Office session"). Seat cables firmly; for long runs
  avoid touching them.
- Port names (`/dev/cu.usbmodem…`) follow the USB socket, not the board. Always identify boards
  by ST-LINK serial number.
