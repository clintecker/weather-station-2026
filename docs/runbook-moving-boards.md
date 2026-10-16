# Runbook: moving the boards between gateways

Use this when the TX/RX boards move between machines (for example office ↔ home). Written
2026-10-13; every rule below is tied to code so it can be re-checked.

## The rule that matters

A TX key may only be used with counters that only go up. The AES-CCM nonce is
kind + station ID + the transmission counter (40-bit since draft 5; `header()` in
`firmware/common/ws_frame.c`, `docs/protocol.md` section 2). `PROVISION … [epoch_floor]` raises only the **epoch** (`App/node_store.c`,
`store_epoch_floor`), which keeps observation identities unique. It does not raise the
counter.

What `WIPE ERASE-ALL-NODE-STATE` erases depends on the firmware (`App/node_store.c`, `store_wipe`):

- **Before release `0f456040fe54`:** the key, the counters and the journal. The counter restarted at 1.
- **From `0f456040fe54` on:** the key and the journal only. The counter and the epoch keep
  rising for the life of the board.

| After a WIPE, provision with… | Safe? |
|---|---|
| a **new** key (`ws0 init --hardware` into a new directory) | Yes, always |
| a key whose every use was on this board, with the counter never going back since its first use (no WIPE under firmware older than `0f456040fe54` after that first use; for example the office key `b7142e`, first used after the morning wipe) | Yes: the counter only went up |
| a key used before `0f456040fe54`, or on another board (for example `run-hw`'s) | **No**: can repeat nonces already sent on air |

Prefer a new key: it is never wrong.

A run directory holds the key (`gateway.json`), the observation database and the gateway's own
nonce state. It is git-ignored (`run*/`). Move it only by a private route (AirDrop, USB stick),
never git, chat or email.

## Know which key TX has

```sh
.venv/bin/python -m serial.tools.list_ports -v            # TX = SER=003B00194142500E20353451
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodem<TX> 115200
#   type STATUS; read kcv=… (Ctrl-] quits)
```

Known key check value: office `run-office` (2026-10-13) = `b7142e`. The home `run-hw` value is not recorded in the repo; compute it on the home Mac.
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
