# Office range walk, 2026-10-13 (exploratory, not H01)

Firmware a07f498273f7 on both boards. Radio: 915.0 MHz, BW 500 kHz, SF7, CR 4/5, **0 dBm** (bench settings).
TX re-provisioned with a fresh office key (KCV b7142e, taken from the `provision-node` output, which is not in these logs. Run directory `run-office/`, not committed).

## Setup

- TX: on USB wall power, fixed position in the office.
- RX: on the gateway laptop, carried by Clint (`ws0 serve`, receiver.log RSSI/SNR per frame).
- **Both boards hung loose from their USB cables: antenna orientation was uncontrolled.** The antennas were confirmed screwed on.
- No SHT45 attached: every reading is `sensor_fault` (expected).

## Results

| UTC | Position (RX relative to TX) | Uplink RSSI (dBm) | SNR (dB) | Delivery |
|---|---|---|---|---|
| 15:37–15:42 | Same room, ~30–50 ft (9–15 m), line of sight | −61 to −78 | +6 to +13 | all ACKed |
| 15:43 | Next to TX (~1 ft) | −64 | +13 | ACKed |
| 15:44–15:46 | End of hallway | −83 to −97 | +6 to +11 | all ACKed |
| 15:47–15:48 | A few hundred feet away in the building; old warehouse, thick concrete and metal walls | none | none | 2 minutes lost link |
| 15:49 | Returning | −81 to −84 | +11 to +12 | 2 missed + current reading delivered together |
| 15:50–15:51 | Near TX | −63 to −65 | +8 to +13 | ACKed |

- **No reading was lost.** The walk (15:37:14–15:51:14) covers session 2, sequences 0–14. All 15 are in the gateway database (`run-office/observations.sqlite3`, not committed) with their original sample times. Seq 0 was sampled at boot before time sync, so it has a gateway-reconstructed time. The two readings taken during the dropout (seq 10, 11) were held in the TX journal and delivered at 15:49:14 together with seq 12.
- **Latency:** seq 10 committed 121.6 s after sampling, over the H01 120 s limit; seq 11 at 61.8 s. A 2-minute dropout therefore costs H01 on-time readings even with zero loss.
- One TX boot health (diag) frame at 15:37:14 arrived at −58 dBm with SNR −2 dB, while the observation just before it had SNR +13 dB. Possible in-band interference at the office; single sample, unconfirmed.

## Limits of this evidence

- Uncontrolled antenna orientation (polarization mismatch and pattern nulls, plus body shadowing from carrying the laptop) explains the ~40 dB shortfall at 1 ft versus the bench (−20 dBm at 30 cm) and the 10–15 dB swings at a single spot. Absolute RSSI values and the dropout distance are **not** a range figure.
- 0 dBm / SF7 is the weakest configuration. The deployment policy allows up to +22 dBm and SF9–SF12 (`docs/failure-modes.md`).
- Downlink RSSI (ACK at TX) was not captured: the TX console was not connected.

## Next time

Fix both boards with antennas vertical (TX taped to a non-metal object; RX taped to the laptop lid, antenna above it), keep the body out of the path, stay 3+ minutes per spot, and connect a TX console if downlink RSSI is wanted.

Files: `receiver-excerpt.log`: receiver lines 15:30–15:51 UTC, frame headers only (ciphertext and ACK bodies removed).
