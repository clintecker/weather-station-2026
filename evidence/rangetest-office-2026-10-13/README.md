# Office range test with firmware/rangetest, 2026-10-13 (exploratory, not H01)

Bench tool `firmware/rangetest` (built from ST PingPong): both boards bounce a 16-byte packet about
1.5 times a second at SF7, about 0.8 at SF12. Each packet carries what the sender measured of the
other board's previous packet, so one console logs **both directions**. Buttons on either board change
SF and TX power on both together. Logger: `tools/rangetest_log.py`.

Radio: 915.0 MHz, LoRa 500 kHz, CR 4/5, 16-byte payload. SF and power as stated per run.
TX = board A `003B…` on USB wall power, fixed position. RX = board B `0016…` on the laptop, carried.

## Files

| File | What |
|---|---|
| `rangetest-v1-desk.csv` | First firmware version, desk checks only (16:07–16:14 UTC). No sender-settings columns. |
| `rangetest.csv` | Second firmware version (restart adoption, lost-contact fallback). Desk checks 16:15–16:43, walk 16:43–17:00 UTC. From 16:46:39 timeouts and corrupted packets are logged separately (`rx_timeout`, `rx_error`). `usb` rows mark USB dropouts. |
| `spots.csv` | Mark times and Clint's location notes. |

`up_*` = what RX heard from TX. `down_*` = what TX reported hearing of RX. A `miss` is an RX receive
window with nothing valid, so it includes failures in either direction of the rally.

## Results

**Range (building with thick concrete and metal walls):**

| Setting | Edge |
|---|---|
| SF7 / 0 dBm | Marginal around Farmer's Fridge (about 70 % of round trips) |
| SF12 / 0 dBm | Lost just past the corner beyond Farmer's Fridge (16:48:12) |
| SF12 / +22 dBm | Still connected at the far side of the building, SNR −10 to −17, about half of round trips (16:54) |

**Same spot, same position, only the setting changed:**

| Spot | Setting | Round trips | Up / down RSSI (dBm) | Up / down SNR (dB) |
|---|---|---|---|---|
| Farmer's Fridge | SF7 / 0 dBm | 15/21 (71 %) | −98 | −2 / +1 |
| Farmer's Fridge | SF10 / 0 dBm | 5/8 (62 %) | −97 | 0 / +2 |
| Farmer's Fridge | SF12 / 0 dBm | 21/31 (68 %) | −97 | −3 / −3 |
| Return path (16:49–16:51) | SF12 / +22 dBm | 27/30 (90 %) | −86 / −86 | +3 / +3 |
| Same | SF12 / +14 dBm | ~85 % | −95 | +0.5 |
| Same | SF12 / 0 dBm | 14/28 (50 %) | −99 / −102 | −6.5 / −6 |

## Findings

1. **TX power works on both amplifiers.** +22 dBm (high-power PA) vs 0 dBm at the same spot moved
   the signal about 22 dB once noise is accounted for; +14 dBm landed where expected (−95 vs predicted −94).
2. **Noise floor about −100 dBm at both ends**, roughly 10 dB above the theoretical floor for 500 kHz
   (about −111 dBm). As TX power or distance changed, RSSI stopped falling at about −100 dBm while SNR kept
   falling, so RSSI there is measuring the noise. TX (far from the laptop) saw the same, so the noise is
   not from the laptop next to RX.
3. **Losses do not follow the SF12 sensitivity spec.** At Farmer's Fridge, SF12 delivered no more than
   SF7. Across all SF12 data (294 events), the next round trip succeeded 100 % when the last SNR was
   +4 to +7, 86 % at 0 to +3, about 60–80 % from −1 to −12. SF12's datasheet limit is about −20 dB.
4. **Losses come in clumps:** 67 % of loss streaks were 2+ long, against about 30 % if independent.
5. **Direct sign of in-band interference at 16:54:07:** RSSI rose to −91 dBm while SNR fell to −13 and 3 of
   4 round trips failed. Received power rising while SNR falls means power that is not ours.
6. **Losses split, 16:46–17:00:** mostly timeouts (nothing decoded), with some corrupted packets
   (`rx_error`). At 16:58:53, at SF7 / SNR +5, 2 of 4 losses were corrupted packets.

Working hypothesis, **not confirmed**: bursty in-band interference, for example UHF RFID readers
(902–928 MHz, frequency-hopping, up to +30 dBm EIRP), which are common in access control and automated
fridges. Test: a listen-only noise-floor mode in `firmware/rangetest` carried past Farmer's Fridge.

## USB dropouts reset the boards (bench artifact)

TX restarted at 16:06:52, 16:10:05, 16:20:37 and 16:23:40, and RX at 16:54:35 and 16:54:45, with nobody
pressing reset. Each coincided with that board's USB port vanishing for about 1 s. Reset flags after
clearing them at 16:22 showed the reset pin only, no brown-out. Two further TX restarts (16:22:02,
16:22:18) matched my own debugger sessions and are excluded. Mechanism: when the on-board ST-LINK
re-enumerates, it pulses the target reset. The outdoor node has no ST-LINK, so this matters only for
USB bench runs such as H01: cables must be secured and not touched.

## Limits

- Exploratory, uncontrolled walk: orientation was better than the morning walk (antennas taped up) but
  the laptop was carried and handled.
- Spot locations are Clint's notes, without distances.
- The SNR estimate at SF12 tops out around +4 even at −10 dBm (+12 at SF7). Unexplained, harmless.
- Not H01 evidence.
