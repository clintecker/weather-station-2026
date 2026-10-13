# Office range test with firmware/rangetest, 2026-10-13 (exploratory, not H01)

Bench tool `firmware/rangetest` (built from ST PingPong): both boards bounce a 16-byte packet about
1.6 times a second at SF7 and about 0.8 at SF12. Each packet carries what the sender measured of the
other board's previous packet, so one console logs **both directions**. Buttons on either board change
SF and TX power on both boards together. Logger: `tools/rangetest_log.py`.

Radio: 915.0 MHz, LoRa 500 kHz, CR 4/5, 16-byte payload. SF and power as stated per run.
TX = board A `003B…` on USB wall power, fixed position. RX = board B `0016…` on the laptop, carried.
The CSVs are the RX board's console.

**Every number below is printed by `analyze.py`** (stdlib only):
`python3 evidence/rangetest-office-2026-10-13/analyze.py`.

## Files

| File | What |
|---|---|
| `rangetest-v1-desk.csv` | First firmware version, desk checks only (16:06:57–16:15:02 UTC). No peer-settings columns. |
| `rangetest.csv` | Second firmware version (restart adoption, lost-contact fallback). Desk checks 16:15–16:43, walk 16:43–17:00 UTC. From 16:46:39 each failed window also gets an annotation row, `rx_timeout` (nothing decoded) or `rx_error` (corrupted packet), just before its `miss` row. |
| `spots.csv` | Mark times and Clint's location notes. |
| `analyze.py` | Recomputes every number in this README from the CSVs. |

`up_*` = what RX heard from TX. `down_*` = what TX reported hearing of RX. `usb` rows are written each
time the logger opens the port: a `disconnected` row followed by `connected` is a USB dropout
(16:54:35, 16:54:45). A `connected` row on its own is the logger starting or restarting
(16:43:37, 16:46:39, 16:56:31).

## Definitions

- **Event:** one RX receive window, meaning one `rx` row (round trip succeeded) or one `miss` row (nothing
  valid heard, so the failure could be in either direction). `rx_timeout`/`rx_error` rows annotate a `miss`
  and are not counted again.
- **Segment:** consecutive events with the same RX setting (SF, power). A segment is cut at every
  `mark` and `usb` row, so segments run from one switch (or mark) to the next. Nothing is hand-picked.
- **Loss streak:** consecutive `miss` events inside one segment.
- **Signal estimate:** RSSI minus the noise share implied by SNR, `S = RSSI − 10·log10(1 + 10^(−SNR/10))`.
- **Walk statistics** (findings 3 and 4) use the walk from 16:43:37 up to the first RX USB dropout at 16:54:35.745.
  After that dropout the boards were on different settings (see below), so those misses are not radio loss.

## Results

**Range (building with thick concrete and metal walls):**

| Setting | Edge |
|---|---|
| SF7 / 0 dBm | Marginal at Farmer's Fridge: 19/25 round trips (76 %) |
| SF12 / 0 dBm | Lost just past the corner beyond Farmer's Fridge. After mark 3 (16:47:44), 4/21 round trips (19 %); last packet 16:48:08.9; boards fell back to SF7/0 at 16:48:37 |
| SF12 / +22 dBm | 16:52:09–16:54:35 (walking out, spot not marked): 58/86 (67 %). In the last 35 s before the RX dropout (16:54:00–16:54:35): 11/19 (58 %), up SNR −9 to −19 dB |

**The "furthest side of the building" mark (16:55:11) has no SF12/+22 data.** The RX board restarted
at 16:54:35 and 16:54:45 (USB dropouts). This firmware's restart and fallback setting is SF7/0 dBm, and
every later `rx` row is SF7/0. The TX setting during that time was not logged. No packet was decoded
from 16:54:42 until 16:57:49 (SF7/0, RSSI −100), which includes the mark at 16:55:11. That gap shows
a settings mismatch and then SF7/0 being out of range. It is not an SF12/+22 range limit.

**Same spot, only the setting changed.** Farmer's Fridge stop, from the SF7 switch (16:45:05.250) to the logger
restart (16:46:39.634). Mark 2 (16:45:46) fell inside the SF10 span:

| Setting | Round trips | Up / down RSSI (dBm, median) | Up / down SNR (dB, median) |
|---|---|---|---|
| SF7 / 0 dBm | 19/25 (76 %) | −98 / −100 | −2 / −1 |
| SF10 / 0 dBm | 5/8 (62 %) | −97 / −99 | 0 / +2 |
| SF12 / 0 dBm | 21/29 (72 %) | −97 / −99 | −3 / −3 |

**Return path (spot not noted), consecutive segments:**

| Segment | Setting | Round trips | Up / down RSSI (dBm) | Up / down SNR (dB) | Signal estimate (dBm) |
|---|---|---|---|---|---|
| 16:49:09–16:49:52 | SF12 / +22 dBm | 30/33 (91 %) | −86 / −86 | +3 / +3 | −88.3 |
| 16:49:53–16:51:08 | SF12 / 0 dBm | 22/43 (51 %) | −99 / −102 | −7 / −6 | −106.8 |
| 16:51:09–16:52:08 | SF12 / +14 dBm | 34/42 (81 %) | −94 / −95 | +1 / +2 | −96.1 |

## Findings

1. **TX power works on both amplifiers.** Going from +22 dBm (high-power PA) to 0 dBm at the return-path spot
   lowered the signal estimate by 18.5 dB (−88.3 to −106.8 dBm), against 22 dB nominal. The +14 dBm
   segment landed where expected: median RSSI −94 against −94 predicted (−86 − 8), signal estimate
   −96.1 against −96.3 predicted.
2. **Noise floor about −100 dBm at both ends.** Median RSSI of packets received below the noise
   (SNR ≤ −5 dB) was −99 dBm at RX and −102 dBm at TX. That is roughly 10 dB above the expected receiver
   floor: thermal floor −117 dBm at 500 kHz plus about 6 dB noise figure ≈ −111 dBm. RSSI stopped falling
   at about −100 dBm while SNR kept falling, so RSSI there is measuring the noise. TX, far from the laptop,
   saw the same, so the noise does not come from the laptop next to RX.
3. **Losses do not follow the SF12 sensitivity spec.** At Farmer's Fridge, SF12 delivered no more than
   SF7 (72 % vs 76 %). Across all SF12 events on the walk (357 events; 246 `rx` events followed by another
   event in the same segment), the next round trip succeeded 37/37 (100 %) when the last up SNR was +4 to
   +7. It succeeded 63/74 (85 %) at 0 to +3 and 82/116 (71 %) at −1 to −12 (14/19 below −12). SF12's
   datasheet demodulation limit is about −20 dB.
4. **Losses come in clumps.** 34 of 61 loss streaks (56 %) were 2 or more long. With independent losses at
   the observed rate (p = 0.31) the expected share is 31 %.
5. **Direct sign of in-band interference at 16:54:03.9:** a packet arrived at RSSI −91 dBm with SNR −13,
   while neighbouring packets were at −98 to −100 dBm. The next three windows failed (timeout, corrupted,
   timeout). Received power rising while SNR falls means power that is not ours.
6. **How losses split from 16:46:39 to 17:00:** 146 timeouts (nothing decoded) and 26 corrupted packets
   (`rx_error`). Between 16:58:39 and 16:58:53 (SF7, decoded packets at SNR −3 to +9), 2 of the
   5 losses were corrupted packets.

Working hypothesis, **not confirmed**: bursty in-band interference, for example UHF RFID readers
(902–928 MHz, frequency-hopping, up to +30 dBm EIRP), which are common in access control and automated
fridges. Test: a listen-only noise-floor mode in `firmware/rangetest` carried past Farmer's Fridge.

## Board restarts (sequence resets in the logs)

`ping seq=` drops when the sender restarts. All resets found by `analyze.py`:

| Time (first packet after) | Last heard before | Classification |
|---|---|---|
| 16:07:25 (v1) | 16:07:17, seq 34 | Unknown (not in the original notes) |
| 16:09:44 (v1) | 16:09:37, seq 205 | Unknown; follows mark 3 at 16:09:40 |
| 16:10:06 (v1) | 16:10:02, seq 27 | TX restart with USB dropout (16:10:05) |
| 16:21:08 | 16:20:36, seq 471 | TX restart with USB dropout (16:20:37); boards met again after the RX fell back at 16:21:07 (first packet seq 5) |
| 16:22:06 | 16:21:59, seq 84 | Debugger session (16:22:02), excluded |
| 16:22:22 | 16:22:15, seq 14 | Debugger session (16:22:18), excluded |
| 16:23:46 | 16:23:40, seq 121 | TX restart with USB dropout (16:23:40) |
| 16:43:38 | 16:38:52, seq 807 | Unknown: happened while the logger was stopped (16:38:52–16:43:37) |
| 17:00:35 | 17:00:13, seq 682 | Unknown: after the walk |

An earlier TX restart at 16:06:52 happened before the first logged row. The RX restarted at 16:54:35 and
16:54:45 (`usb` dropout rows). After that, seq continued from the TX (533 at 16:57:49), so the TX did not
restart.

**Mechanism for the USB-dropout restarts (bench artifact).** Each listed restart with a USB dropout coincided with
that board's USB port vanishing for about 1 s, with nobody pressing reset. Reset flags read after being cleared at
16:22 showed the reset pin only, no brown-out. When the on-board ST-LINK re-enumerates, it pulses the
target reset. The outdoor node has no ST-LINK, so this matters only for USB bench runs such as H01:
cables must be secured and not touched. The TX-side dropout times and reset flags come from the session
console, not from these CSVs (which are the RX console).

## Limits

- Exploratory, uncontrolled walk. Orientation was better than in the morning walk (antennas taped up), but
  the laptop was carried and handled.
- Spot locations are Clint's notes, without distances.
- At strong signal (RSSI above −40 dBm) the SNR estimate has a median of +4 at SF12 (maximum +9), against +12 at SF7.
  Unexplained, harmless.
- Not H01 evidence.
