# G13 bench outage: link back-off and backlog drain (2026-10-13)

`tx-console.log` is a 26-line TX console excerpt (03:42:22Z–03:53:23Z, boot epoch 13). It was committed with `db4ceaf`
(G13: link back-off and airtime-capped backlog drain). The link was silent from the start of the excerpt
until a probe was answered at 03:52:22Z. Every reading is `valid=0`, because no sensor was attached.

What the log shows:
- **Minutes 1–3 (seq 1–3):** one frame per minute, no ACK (`#ack none`).
- **03:44:24:** `#link probing: 3 silent minutes; next probe in 120 s`. Readings keep being journaled (`pending` rises).
- **Probes:** at 03:47:24 (unanswered, `next probe in 240 s`) and at 03:52:22 (answered). The minutes between probes have
  no `#ack` line: journal-only. Both probes ran about 1 minute later than announced (due 03:46:24 and 03:51:24).
  failure-modes.md G13 records this as fixed during the test.
- **03:52:22:** `#link linked after 4 silent minutes`, then the backlog drains oldest first. At 03:53:22–23 the
  live seq 12 plus backlog seq 1–5 were ACKed, so 5 backlog items in that minute. `pending` went 11 → 5.
  `lost=0` throughout.

The excerpt ends with 5 still pending. The rest of the drain is not in this file.
