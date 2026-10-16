# app_tx: TX node boot, sampling and the minute report

`app_tx.c` boots the TX node and runs its sampling. It reads the SHT45 every 15 s and builds one
observation per minute from four samples. It journals the observation in flash and hands it to the
radio exchange (`tx_exchange.c`). It also decides whether the watchdog may be refreshed.

This document is the source. `tools/tangle.py` generates `app_tx.c` from the code chunks below. The
generated file is committed, so the build, the static analysers and the host tests read ordinary C.
Edit this file, then regenerate and check:

```sh
python3 tools/tangle.py firmware/stage0-node/App/app_tx.lit.md                           # write app_tx.c
python3 tools/tangle.py --check firmware/stage0-node/App/app_tx.lit.md                   # committed .c == tangle
python3 tools/tangle.py --weave /tmp/app_tx.html firmware/stage0-node/App/app_tx.lit.md  # render
```

A chunk is a fenced ` ```c {#name} ` block. A line `<<name>>` inside a chunk includes chunk `name`.
Chunks appear in reading order. The root chunk (section 7) puts them in C order.

## 1. Behaviour

| Behaviour | Checked by (`tests/test_tx_machine.py`) |
|---|---|
| Samples at 0, 15, 30 and 45 s after boot. The minute's report follows the 4th sample | `test_minute_exchange_then_health_report_after_a_gap` |
| Flash is never written while the radio transmits or receives | every test: `node()` asserts `h_flash_ops_during_radio() == 0` |
| A reading made during an exchange is held in RAM and journaled when the radio goes idle | `test_a_reading_made_during_an_exchange_is_journaled_when_the_radio_goes_idle` |
| At most `HELD_MAX` (2) readings are held. A third drops the oldest and counts it in `held_lost` | `test_held_readings_keep_the_newest_when_more_minutes_wait` |
| An exchange that outlasts its bound stops the radio, journals the held readings and fails the watchdog check from then on | `test_a_radio_that_never_finishes_trips_the_exchange_bound` |
| More than `TX_FAIL_LIMIT` (10) transmit failures in a row fail the watchdog check. One success clears the run | `test_transmit_failures_in_a_row_trip_the_watchdog_and_a_tx_done_clears_them` |
| Sampling stopped by a command (reboot, `TEST-FLASH-STORM`) keeps the watchdog check healthy | `test_commanded_reboot_comes_from_a_timer_and_stops_sampling`, `test_flash_storm_stops_sampling_and_exchanges` |
| A sensor fault sends every T/RH field as INVALID. A measurement still running at the next sample counts as a missed sample (`rc=-1`) | `test_sensor_failure_and_a_measurement_that_never_ends` |
| A sequence number is used once, even when its journal write fails | none (code only: `minute_report`) |
| A boot that fails in storage or the epoch reservation resets after 10 min. An unprovisioned board or a failed self-test does not reset | none (code only: `boot_ready`, `boot_retry`) |

The generated file opens with a summary:

```c {#abstract}
/* Stage-0 TX: one SHT45 observation per minute, journaled in flash before transmission and
 * retained until an authenticated host ACK (or a NACK / strike-limit abandon). Each minute sends
 * the live observation first, then older pending ones as the energy and link policy allows
 * (docs/radio-energy-policy.md); each frame gets a fresh durably reserved counter and one ACK
 * receive window. This file is boot and the sampling glue; the other TX modules are listed in
 * App/tx_node.h. */
```

## 2. Boot

### Order of operations

`SubghzApp_Init` runs once at startup. It does every step that does not depend on stored state
first, then `boot_ready`, then starts sampling:

```text
1. stackmon_paint, busymon_init, leds_init, exchange_init     stack paint, busy monitor, LEDs, radio
2. register the sample task (sample_timed), tx_console_init    the console works on every later path
3. node.boot_s = clock_s(); policy_init; watchdog_start        uptime origin. The IWDG runs from here
4. node.kat_ok = selftest_kat(); print #boot; fault_report     self-test result, reset cause, radio settings
5. boot_ready()                                                fails: return, the node does not sample
6. sensor_init; node.running = 1; last_sample_s = clock_s()    the watchdog expects progress from here
7. tx_status; start the 15-s periodic timer; post the sample task at once (the first sample is at 0 s)
```

The watchdog starts at step 3, before storage is read. Before step 6 `node.running` is 0, so
`watchdog_healthy` returns 1 (section 6). A node that fails `boot_ready` therefore stays up with the
console available and is not reset by the watchdog.

### State

`node` is this boot's identity and run state (`tx_node_t`, `tx_node.h`). Only this file writes it.
The other TX modules read it through `node_state()`. `node_selftest` is the `KAT` console command.
It runs the self-test again and stores the result in `node.kat_ok`. It does not start sampling on a
node whose boot stopped at a failed self-test.

```c {#node-state}
/* This boot's identity and run state: written only here; the other TX modules read it through
   node_state() (docs/power-of-ten.md, rule 6). */
static tx_node_t node;
const tx_node_t *node_state(void) { return &node; }
uint32_t node_uptime_s(void) { return clock_s() - node.boot_s; }
int node_selftest(void) { node.kat_ok = selftest_kat(); return node.kat_ok; }
```

### boot_ready

`boot_ready` returns 1 when the node may sample and transmit. Each check that fails turns the red
LED on, prints one line, and returns 0:

| Step | Call | On failure |
|---|---|---|
| 1 | `store_meta_init`, then `store_journal_init` | `#error store-init`, `boot_retry` |
| 2 | `store_journal_scrub(STORM_EPOCH)` | none. A nonzero count prints `#storm-scrub dropped=N` |
| 3 | `exchange_load_identity` (station and key) | `tx_status`, `#unprovisioned: send PROVISION <station_id> <key>` |
| 4 | `time_restore` | none |
| 5 | `node.kat_ok` (from boot step 4) | `tx_status`, `#error self-test failed; not transmitting` |
| 6 | `store_next_epoch(&node.boot_epoch)` | `#error epoch-reserve`, `boot_retry` |

Step 2 acknowledges the records that the bench `TEST-FLASH-STORM` load wrote under `STORM_EPOCH`
and that a power cut left pending (`tx_console.h`). Step 6 reserves the epoch durably before the
first sample, so the observation identity (epoch, sequence) never repeats.

```c {#boot-ready}
/* Storage, key, self-test and a durable epoch: 1 if the node may sample and transmit. */
static int boot_ready(void)
{
  if (store_meta_init() || store_journal_init()) { led_set(LED_RED, 1); APP_PRINTF("#error store-init\n"); boot_retry(); return 0; }
  uint32_t scrubbed = store_journal_scrub(STORM_EPOCH);
  if (scrubbed) APP_PRINTF("#storm-scrub dropped=%u (test slots a power cut left pending)\n", (unsigned)scrubbed);
  if (!exchange_load_identity()) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#unprovisioned: send PROVISION <station_id> <key>\n"); return 0; }
  time_restore();
  if (!node.kat_ok) { led_set(LED_RED, 1); tx_status(); APP_PRINTF("#error self-test failed; not transmitting\n"); return 0; }
  /* Durable epoch before the first sample: observation identities never repeat. */
  if (store_next_epoch(&node.boot_epoch)) { led_set(LED_RED, 1); APP_PRINTF("#error epoch-reserve\n"); boot_retry(); return 0; }
  return 1;
}
```

### Boot retry

A storage failure at boot may be transient. `boot_retry` arms a one-shot timer of `BOOT_RETRY_MS`
(10 minutes) whose callback calls `NVIC_SystemReset`. It prints `#boot-retry: reset in 600 s`. It
does nothing when the self-test failed. An unprovisioned board never calls it. Both cases need an
operator, and a reset does not change them.

```c {#boot-retry-delay}
/* A storage failure at boot may be transient: retry once by a reset after 10 minutes. */
#define BOOT_RETRY_MS       (10UL * CLOCK_MS_PER_MIN)
```

```c {#boot-retry}
static void on_boot_retry(void *ctx) { (void)ctx; NVIC_SystemReset(); }

/* Never for an unprovisioned board or a failed self-test: those need an operator, not a reset. */
static void boot_retry(void)
{
  if (!node.kat_ok) return;
  APP_PRINTF("#boot-retry: reset in %u s\n", (unsigned)(BOOT_RETRY_MS / CLOCK_MS_PER_S));
  (void)UTIL_TIMER_Create(&boot_retry_timer, BOOT_RETRY_MS, UTIL_TIMER_ONESHOT, on_boot_retry, NULL);
  (void)UTIL_TIMER_Start(&boot_retry_timer);
}
```

### Entry point

```c {#init}
void SubghzApp_Init(void)
{
  stackmon_paint();
  busymon_init();
  leds_init();
  exchange_init();
  UTIL_SEQ_RegTask(1U << CFG_SEQ_Task_Sample, UTIL_SEQ_RFU, sample_timed);
  tx_console_init();

  node.boot_s = clock_s();
  policy_init();
  watchdog_start();
  node.kat_ok = selftest_kat();
  APP_PRINTF("#boot role=tx fw=%s reset=%s kat=%s freq=%u bw=%u sf=%u power=%d\n", WS_FW_VERSION,
             watchdog_reset_cause(), node.kat_ok ? "pass" : "FAIL", (unsigned)WS_RF_FREQUENCY_HZ, (unsigned)WS_LORA_BANDWIDTH, (unsigned)WS_LORA_SF, WS_TX_POWER_DBM);
  fault_report();
  if (!boot_ready()) return;
  sensor_init();
  node.running = 1;
  last_sample_s = clock_s();
  tx_status();
  (void)UTIL_TIMER_Create(&sample_timer, SAMPLE_PERIOD_MS, UTIL_TIMER_PERIODIC, on_sample_timer, NULL);
  (void)UTIL_TIMER_Start(&sample_timer);
  UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0);
}
```

## 3. Sampling

### The sample timer

The timer period is `SAMPLE_PERIOD_MS` (15 000 ms). Every `SAMPLES_PER_REPORT`-th (4th) sample
closes the minute.

```c {#sample-constants}
#define SAMPLE_PERIOD_MS    15000U  /* one T/RH sample; every SAMPLES_PER_REPORT-th builds the minute (PRD 9) */
#define SAMPLES_PER_REPORT  4U
```

```c {#timers}
static UTIL_TIMER_Object_t sample_timer, boot_retry_timer;
static uint32_t last_sample_s;   /* watchdog progress evidence */
```

`on_sample_timer` runs in the timer interrupt and only posts the sample task. `sample` runs from the
sequencer. It records `last_sample_s`, the progress evidence for the watchdog check, and starts one
measurement. `sensor_start` returns at once. The result arrives later in `sensor_done`, about 11 ms
after the start, or 15–100 ms after a bus failure (`sensor.h`). If the previous measurement has not
finished, `sensor_start` returns -1 and `sample` reports a missed sample through
`sensor_done(-1, 0, 0)`. `BUSYMON_TASK(sample)` defines `sample_timed`, the timed wrapper that
`SubghzApp_Init` registers.

```c {#sample-timer}
/* Every 15 s: start a measurement; sensor_done() gets its result from the sensor task ~10 ms later. */
static void sample(void)
{
  last_sample_s = clock_s();
  if (sensor_start()) sensor_done(-1, 0, 0);   /* the previous one never finished: a missed sample */
}
BUSYMON_TASK(sample)

static void on_sample_timer(void *ctx) { (void)ctx; UTIL_SEQ_SetTask(1U << CFG_SEQ_Task_Sample, CFG_SEQ_Prio_0); }
```

### The T/RH window

`th_window` collects the minute's samples (`ws_th_window`, `firmware/stage0.c`). `th_ticks` counts
sample results since the last report. `sensor_reported` makes the first result after boot print one
`#sensor` line. `stuck` is set by the watchdog check when an exchange outlasts its bound (section 6).

```c {#window-state}
/* The minute's 15-s samples (PRD section 9: coverage, mean and extrema). */
static ws_th_window th_window;
static unsigned th_ticks;
static int sensor_reported;   /* the first reading after boot is printed as #sensor */
static int stuck;             /* the exchange outlasted its worst case: the watchdog is resetting the board */
```

`ws_th_add` keeps the window's count, sums, minimum and maximum:

| Input | Effect |
|---|---|
| `src != 0` (sensor fault or missed sample) | ignored |
| temperature outside `WS_TEMP_MIN_CENTI`..`WS_TEMP_MAX_CENTI` (-40.00..125.00 °C) | ignored |
| RH above `WS_RH_MAX_CENTI` (100.00 %) | clamped to 100.00 % |
| 255 samples already counted | ignored |

`ws_th_mean_t` and `ws_th_mean_h` round the mean half up and return 0 for an empty window.

### sensor_done

`sensor.c` calls `sensor_done` once per measurement. It does the following:

1. Return at once if sampling stopped (`node.running == 0`) or the radio is stuck. This drops a
   measurement that finishes after `sampling_stop` or after the watchdog check aborted an exchange.
2. On the first result after boot, print `#sensor ok t=... rh=...` or `#sensor fault rc=...`.
3. Add the sample to the window.
4. On the 4th result, reset `th_ticks` and call `minute_report` with this result's code.

```c {#sensor-done}
void sensor_done(int src, int16_t t, uint16_t h)
{
  if (!node.running || stuck) return;   /* a measurement that finishes after sampling stopped (reboot, storm, stuck radio) */
  if (!sensor_reported)
  {
    sensor_reported = 1;
    if (src) { APP_PRINTF("#sensor fault rc=%d (see sensor.h for codes)\n", src); }
    else { APP_PRINTF("#sensor ok t=%d rh=%u\n", t, h); }
  }
  ws_th_add(&th_window, src == 0, t, h);
  if (++th_ticks < SAMPLES_PER_REPORT) return;   /* the minute's report follows its last sample */
  th_ticks = 0;
  minute_report(src);
}
```

## 4. The minute report

### Order of operations

`minute_report` runs from `sensor_done` on the minute's 4th sample:

```text
1. minute_encode           means, extrema, time; encode into plain[]; reset the window
2. busy = exchange_busy()  is the previous minute's exchange still running?
3. journal_or_hold         busy: hold plain[] in RAM. Idle: append it to the journal
4. sample_line             print #sample
5. node.next_seq++         the sequence number is used even if step 3 failed
6. busy: print #busy and return
7. minute_send             the live record (NULL if step 3 failed) and the allowed backlog
```

`busymon` times step 3 as `report.journal` and step 7 as `report.send`. Step 3 can start a new
journal page, which erases flash for about 22 ms.

```c {#minute-report}
/* The minute's report: journaled and sent as the policy allows, or held while the previous
   minute's exchange is still running (the radio is transmitting or listening: no flash write). */
static void minute_report(int src)
{
  uint8_t plain[WS_OBS_PLAIN_MAX] = { 0 }; jref_t live; minute_t m;
  int encoded = WS_CHECK(minute_encode(&m, plain));   /* our own codes always encode */
  int busy = exchange_busy();
  bm_span s = busymon_begin();
  int rc = journal_or_hold(plain, encoded, busy, &live);   /* a journal page start erases 22 ms */
  busymon_step_end(s, "report.journal");
  sample_line(&m, src, rc, busy);
  node.next_seq++; /* identity is never reused, even if the journal write failed */
  if (busy) { APP_PRINTF("#busy previous exchange still running; reading held until it ends\n"); return; }
  s = busymon_begin();
  minute_send(rc ? NULL : &live);
  busymon_step_end(s, "report.send");
}
```

### Encoding

`minute_encode` fills a `minute_t` and encodes the observation into `WS_OBS_PLAIN_MAX` bytes:

| Field | Source |
|---|---|
| `valid` | both means exist, so at least one sample was valid |
| `t`, `h` | the window's means (0 when not valid) |
| `utc` | `time_utc()`: 0 while the time is unknown |
| `uptime` | `node_uptime_s()`: always sent. The gateway reconstructs time from it |
| `epoch`, `seq` | `node.boot_epoch`, `node.next_seq` |
| `energy` | `energy_state()` |
| `bitmap` | `WS_NODE_FIELDS`, the build's field set (`node_fields.h`) |
| `samples` | the window's count, for `#sample` |

A minute that is not valid increments `node.sensor_faults`. The function resets the window before it
returns, so the next minute starts empty. It returns 1 only if the encoder wrote exactly
`WS_OBS_PLAIN_MAX` bytes. `minute_report` wraps the result in `WS_CHECK`, because the codes come from
this file and always encode.

The `ws_obs_t` is `static`: `minute_encode` runs only from the sequencer and is never re-entered,
and its call chain is the deepest one that `tools/stack_report.py` counts.

```c {#minute-encode}
/* The minute's observation, from its samples. */
typedef struct { int valid; int16_t t; uint16_t h; uint32_t utc, uptime; unsigned samples; } minute_t;

/* Build and encode the minute's observation into plain (WS_OBS_PLAIN_MAX bytes); 0 if it did not
   encode. Starts the next minute's window. */
static int minute_encode(minute_t *m, uint8_t *plain)
{
  m->t = 0; m->h = 0;
  m->valid = ws_th_mean_t(&th_window, &m->t) && ws_th_mean_h(&th_window, &m->h);
  m->utc = time_utc();
  m->uptime = node_uptime_s(); /* always sent: the gateway reconstructs time from it */
  if (!m->valid) node.sensor_faults++;
  /* static: this runs only from the sequencer, never re-entered, and it is on the deepest callback
     chain, which tools/stack_report.py counts four times (a 104-byte record cost ~416 B). */
  static ws_obs_t o;
  o = (ws_obs_t){ .epoch = node.boot_epoch, .seq = node.next_seq, .utc = m->utc, .uptime = m->uptime,
                  .energy = (uint8_t)energy_state(), .bitmap = WS_NODE_FIELDS };
  obs_codes(&o, m->valid, m->t, m->h);
  m->samples = th_window.n;
  ws_th_reset(&th_window);
  return ws_obs_encode(&o, plain, WS_OBS_PLAIN_MAX) == (int)WS_OBS_PLAIN_MAX;
}
```

`obs_codes` sets the T/RH codes. `WS_FI_TH_SAMPLES` is the window's count, clamped to
`WS_TH_SAMPLES_MAX` (60). Without a valid sample every T/RH field gets its INVALID code
(`ws_obs_invalid`). No field is left out. With valid samples the mean, minimum and maximum go through
`ws_code_temp_centi` and `ws_code_rh_centi`. The summary fields reach the frame only if the build's
bitmap includes them (`WS_F_TH_SUMMARY` in `node_fields.h`).

```c {#obs-codes}
/* Draft-5 observation (docs/protocol-draft5-design.md 5): out-of-range temperature is INVALID,
   RH is clamped (ws_code_*); a sensor fault sends every field as INVALID, never leaves it out.
   The summary fields are used only if the build's bitmap includes them (WS_F_TH_SUMMARY in
   node_fields.h). */
static void obs_codes(ws_obs_t *o, int valid, int16_t t, uint16_t h)
{
  static const uint8_t th_fields[] = { WS_FI_TEMPERATURE_C, WS_FI_HUMIDITY_PCT, WS_FI_TEMPERATURE_MIN_C,
                                       WS_FI_TEMPERATURE_MAX_C, WS_FI_HUMIDITY_MIN_PCT, WS_FI_HUMIDITY_MAX_PCT };
  o->code[WS_FI_TH_SAMPLES] = th_window.n > WS_TH_SAMPLES_MAX ? WS_TH_SAMPLES_MAX : th_window.n;
  if (!valid)
  {
    for (unsigned i = 0; i < sizeof th_fields; i++) o->code[th_fields[i]] = ws_obs_invalid(th_fields[i]);
    return;
  }
  o->code[WS_FI_TEMPERATURE_C] = ws_code_temp_centi(t);
  o->code[WS_FI_HUMIDITY_PCT] = ws_code_rh_centi(h);
  o->code[WS_FI_TEMPERATURE_MIN_C] = ws_code_temp_centi(th_window.t_min);
  o->code[WS_FI_TEMPERATURE_MAX_C] = ws_code_temp_centi(th_window.t_max);
  o->code[WS_FI_HUMIDITY_MIN_PCT] = ws_code_rh_centi(th_window.h_min);
  o->code[WS_FI_HUMIDITY_MAX_PCT] = ws_code_rh_centi(th_window.h_max);
}
```

### Journal or hold

`journal_or_hold` writes flash only when the radio is idle. It returns 0 when the reading was
journaled or held, `REC_ENOTENCODED` (-100, outside the `STORE_E*` range) when it did not encode, and
the `STORE_E*` code of a failed append otherwise. It updates the journal failure run
(`node.journal_fails`) for every case except a held reading. `held_flush` counts that append when it
happens.

| Encoded | Radio busy | Action | Return | `journal_fails` |
|---|---|---|---|---|
| yes | no | `store_journal_append` into `*live` | the append's code | success or failure |
| yes | yes | `hold` | 0 | unchanged |
| no | no | none | `REC_ENOTENCODED` | failure |
| no | yes | none | `REC_ENOTENCODED` | failure |

```c {#journal-or-hold}
/* Journal the encoded reading now, or hold it while the radio is busy (a held reading's append
   is counted when the radio goes idle). 0: journaled or held; else the error (REC_ENOTENCODED or a STORE_E* code). */
#define REC_ENOTENCODED (-100)   /* outside the STORE_E* range */
static int journal_or_hold(const uint8_t *plain, int encoded, int busy, jref_t *live)
{
  int rc = encoded ? 0 : REC_ENOTENCODED;
  if (!rc && busy) hold(plain);
  else if (!rc) rc = store_journal_append(plain, live);
  if (rc || !busy) ws_failrun_note(&node.journal_fails, rc == 0);
  return rc;
}
```

### The #sample line

`sample_line` prints one line per minute:

```text
#sample epoch=E seq=S uptime=U valid=0|1 rc=SRC n=SAMPLES t=T rh=H time=synchronized|unknown utc=UTC journal=ok|held|ERROR pending=P lost=L
```

`rc` is the 4th sample's sensor code. `t` and `rh` are 0 when the minute is not valid. `pending` and
`lost` come from `store_journal_pending` and `store_journal_lost`.

```c {#sample-line}
static void sample_line(const minute_t *m, int src, int rc, int busy)
{
  APP_PRINTF("#sample epoch=%u seq=%u uptime=%u valid=%d rc=%d n=%u t=%d rh=%u time=%s utc=%u journal=%s pending=%u lost=%u\n",
             (unsigned)node.boot_epoch, (unsigned)node.next_seq, (unsigned)m->uptime, m->valid, src, m->samples,
             m->valid ? m->t : 0, m->valid ? m->h : 0U, m->utc ? "synchronized" : "unknown", (unsigned)m->utc,
             rc ? "ERROR" : busy ? "held" : "ok", (unsigned)store_journal_pending(), (unsigned)store_journal_lost());
}
```

### Sending

`minute_send` asks the policy what this minute may send (`policy_minute_backlog`,
`docs/radio-energy-policy.md`). A return of -1 sends nothing, and the reading stays journaled. Any
other value starts the exchange with the live record and that many backlog records. `live` is NULL
when the journal append failed, and the exchange then sends backlog only. The policy counts a minute
that may send as the last send, so `minute_send` asks it only when no exchange is running.

```c {#minute-send}
/* What this minute may send, if anything: the live reading (NULL if its journal append failed)
   and the backlog the policy allows. A refused minute's reading stays journaled. */
static void minute_send(const jref_t *live)
{
  if (exchange_busy()) return;   /* the reading is held (journal_or_hold); ask the policy only for a minute that sends */
  int backlog = policy_minute_backlog();
  if (backlog >= 0) exchange_start(live, (unsigned)backlog);
}
```

## 5. Held readings

### Why a reading waits

Flash is written only with the radio idle (`docs/firmware-event-model.md`). A journal append can
erase a page, and the CPU stalls during a flash erase. A minute that ends while the previous
minute's exchange still runs therefore keeps its encoded reading in `held[]`. `tx_exchange.c` calls
`held_flush` the moment the radio goes idle, before anything else runs. The next minute sends the
journaled reading as backlog.

### HELD_MAX

A normal exchange ends well within its minute. Only a hung radio keeps it busy longer. Then the
watchdog resets the board:

| Term | Value | Source |
|---|---|---|
| exchange bound | `(frames + 1) × (3000 + 2000 + 50) ms / 1000 + 5 s`: 116 s with 21 frames | `tx_exchange.c` `exchange_start` |
| watchdog check period | 1 s | `watchdog.c` `CHECK_PERIOD_MS` |
| IWDG timeout | 8 s (4000 counts at 500 Hz) | `watchdog.c` `IWDG_RELOAD` |

21 frames is `MAX_QUEUE`, the live record and 20 backlog records. Minute reports come 60 s and
120 s after the exchange starts. So at most `HELD_MAX` (2) readings wait. If one more comes anyway,
`hold` drops the oldest, prints `#error held-lost seq=...`, increments `node.held_lost` and keeps the
newest.

A reset loses what is held. Those sequence numbers are never sent, and the gateway sees the gap. The
watchdog check avoids this for a hung radio: it calls `exchange_abort`, which stops the radio and
calls `held_flush` before the check starts to fail (section 6).

```c {#held-buffer}
/* Readings a minute produced while the previous minute's exchange was still running. Flash is only
 * written with the radio idle (docs/firmware-event-model.md), so such a reading waits here, encoded,
 * and held_flush() journals it the moment the radio goes idle, before anything else runs; the next
 * minute sends it as backlog. A normal exchange ends well within its minute; only a hung radio
 * keeps it busy longer, and then the watchdog resets the board once the exchange outlasts its bound
 * (at most 116 s, with 21 frames) plus the IWDG's ~8 s, so at most HELD_MAX minutes can be waiting.
 * Should one more come anyway, the oldest held reading is dropped and counted (held_lost) and the
 * newest kept. A reset loses what is held: those sequence numbers are never sent, so the gateway
 * sees the gap. */
#define HELD_MAX 2U
```

```c {#held-storage}
static uint8_t held[HELD_MAX][WS_OBS_PLAIN_MAX];
static unsigned held_n;
```

### hold and held_flush

`held_count` returns `held_n`. `hold` makes room before it adds, so `held_n` never exceeds
`HELD_MAX`. If it does, `WS_CHECK` records the failure and `held_count` clamps it.

```c {#hold}
/* hold() makes room before it adds, so held_n never exceeds HELD_MAX; a count that did is clamped. */
static unsigned held_count(void)
{
  if (!WS_CHECK(held_n <= HELD_MAX)) held_n = HELD_MAX;
  return held_n;
}

static void hold(const uint8_t *plain)
{
  if (held_count() == HELD_MAX)
  {
    node.held_lost++;
    APP_PRINTF("#error held-lost seq=%u (a newer reading replaced it; held_lost=%u)\n", (unsigned)ws_obs_seq(held[0]),
               (unsigned)node.held_lost);
    memmove(held[0], held[1], (HELD_MAX - 1U) * sizeof held[0]);
    held_n--;
  }
  memcpy(held[held_n++], plain, sizeof held[0]);
}
```

`held_flush` appends every held reading, oldest first. Each append updates `node.journal_fails` and
prints `#held journaled seq=S rc=RC pending=P`. It then empties the buffer. A reading whose append
fails is not kept. Its `#held` line shows the nonzero `rc`.

```c {#held-flush}
void held_flush(void)
{
  jref_t r;
  for (unsigned i = 0, n = held_count(); i < n; i++)
  {
    int rc = store_journal_append(held[i], &r);
    ws_failrun_note(&node.journal_fails, rc == 0);
    APP_PRINTF("#held journaled seq=%u rc=%d pending=%u\n", (unsigned)ws_obs_seq(held[i]), rc, (unsigned)store_journal_pending());
  }
  held_n = 0;
}
```

## 6. Watchdog health

### Constants

`TX_FAIL_LIMIT` is the longest failure run that still counts as healthy. `ws_failrun_tripped` is
true when the run exceeds it, so the 11th failure in a row trips it. A reset re-runs `Radio.Init`.
A minute that the policy chose not to send does not touch either run.

```c {#fail-limit}
/* A TX that keeps failing must not look healthy. Above this many failures in a row,
 * of journal appends (journal_fails) or of transmissions (exchange_counts()->air), the watchdog
 * resets the board (which re-runs Radio.Init). Minutes the policy chose not to send never count. */
#define TX_FAIL_LIMIT       10U
```

`SAMPLING_STALL_S` (150 s) is 10 sample periods without a call to `sample`.

```c {#stall}
#define SAMPLING_STALL_S 150U   /* 10 sample periods without a sample: the sampler stopped */
```

### watchdog_healthy

`watchdog.c` calls `watchdog_healthy` every second and refreshes the IWDG only when it returns 1.
After 8 s without a refresh the IWDG resets the board. The checks run in this order. The first that
matches decides:

| Check | Result | Notes |
|---|---|---|
| `stuck` | 0 | set by the exchange-overdue check below, never cleared |
| `node.running == 0` | 1 | not sampling by design: boot stopped, commanded reboot pending, flash storm |
| `now - last_sample_s > SAMPLING_STALL_S` | 0 | the sampler stopped |
| `exchange_overdue(now)` | 0 | see below |
| `node.journal_fails` run > `TX_FAIL_LIMIT` | 0 | prints `#watchdog N journal failures in a row` |
| `exchange_counts()->air` run > `TX_FAIL_LIMIT` | 0 | prints `#watchdog N transmit failures in a row` |
| otherwise | 1 | |

`exchange_overdue` is true when an exchange is busy for longer than its bound (section 5). The check
then does the following, in this order:

1. Set `stuck`. From now on `sensor_done` ignores results and every check returns 0.
2. Stop the sample timer.
3. Call `exchange_abort`: stop the gap and ACK timers, put the radio in standby, mark the exchange
   idle, then `held_flush`. The held readings are journaled with the radio idle.
4. Print `#watchdog radio exchange stuck; radio stopped, held readings journaled, resetting` and
   return 0.

The IWDG resets the board within 8 s. The reset loses no reading.

```c {#watchdog-healthy}
/* Watchdog health: real progress, not just a running main loop. */
int watchdog_healthy(void)
{
  uint32_t now = clock_s();
  if (stuck) return 0;
  if (!node.running) return 1;                             /* not sampling by design */
  if (now - last_sample_s > SAMPLING_STALL_S) return 0;       /* sampling stopped */
  if (exchange_overdue(now))                                  /* radio exchange stuck */
  {
    /* Stop sampling and the radio, journal any held reading with the radio idle, then let the
       watchdog reset the board: the reset loses no reading. */
    stuck = 1;
    (void)UTIL_TIMER_Stop(&sample_timer);
    exchange_abort();
    APP_PRINTF("#watchdog radio exchange stuck; radio stopped, held readings journaled, resetting\n");
    return 0;
  }
  if (ws_failrun_tripped(&node.journal_fails, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u journal failures in a row\n", (unsigned)node.journal_fails.n); return 0; }
  const ws_failrun *air = &exchange_counts()->air;
  if (ws_failrun_tripped(air, TX_FAIL_LIMIT))
  { APP_PRINTF("#watchdog %u transmit failures in a row\n", (unsigned)air->n); return 0; }
  return 1;
}
```

### sampling_stop

The console calls `sampling_stop` for a commanded reboot and for `TEST-FLASH-STORM`. It clears
`node.running` and stops the sample timer. The watchdog check then stops expecting samples, and a
measurement already in flight is dropped by `sensor_done`.

```c {#sampling-stop}
void sampling_stop(void)
{
  node.running = 0;
  (void)UTIL_TIMER_Stop(&sample_timer);
}
```

## 7. The file

The generated file keeps the C order: the includes, the constants, the state, then each function
before its first caller.

```c {#app_tx.c}
<<abstract>>
#define WS_CHECK_FILE 1
#include <string.h>
#include "busymon.h"
#include "clock.h"
#include "fault.h"
#include "leds.h"
#include "node_store.h"
#include "radio_cfg.h"
#include "selftest.h"
#include "sensor.h"
#include "stackmon.h"
#include "stage0.h"
#include "stm32_seq.h"
#include "stm32_timer.h"
#include "stm32wlxx_hal.h"
#include "subghz_phy_app.h"
#include "sys_app.h"
#include "tx_console.h"
#include "tx_exchange.h"
#include "tx_node.h"
#include "tx_policy.h"
#include "tx_time.h"
#include "utilities_def.h"
#include "watchdog.h"
#include "ws_be.h"
#include "ws_check.h"
#include "ws_obs.h"

<<sample-constants>>
<<fail-limit>>
<<boot-retry-delay>>

<<timers>>
<<node-state>>

<<window-state>>

<<sampling-stop>>

<<obs-codes>>

<<held-buffer>>
<<stall>>
<<held-storage>>


<<hold>>

<<held-flush>>

<<minute-send>>

<<minute-encode>>

<<journal-or-hold>>

<<sample-line>>

<<minute-report>>

<<sensor-done>>

<<sample-timer>>

<<watchdog-healthy>>

<<boot-retry>>

<<boot-ready>>

<<init>>
```

## 8. Tests

`tests/test_tx_machine.py` builds `app_tx.c` with the other TX modules and the real `node_store.c`
into a host library. `firmware/host/tx_harness.c` simulates the clock, the timers, the sequencer, the
radio, the SHT45 and the flash. Every test checks at its end that no flash operation happened while
the radio was busy, that no running timer was started again, and that no `WS_CHECK` failed.

| Test | What it checks in this file |
|---|---|
| `test_minute_exchange_then_health_report_after_a_gap` | `#boot` and `#sensor ok`, then the first minute's frame |
| `test_a_reading_made_during_an_exchange_is_journaled_when_the_radio_goes_idle` | `journal=held`, the `#busy` line, `#held journaled` after the exchange ends, then the reading sent as backlog |
| `test_held_readings_keep_the_newest_when_more_minutes_wait` | two held readings, a third drops the oldest (`held_lost=1`), the rest journaled oldest first |
| `test_a_radio_that_never_finishes_trips_the_exchange_bound` | the exchange bound to the second, standby radio, held readings journaled, no sampling until the reset |
| `test_transmit_failures_in_a_row_trip_the_watchdog_and_a_tx_done_clears_them` | healthy for 10 failures, unhealthy at the 11th, healthy again after one transmission |
| `test_commanded_reboot_comes_from_a_timer_and_stops_sampling` | no sensor start after `sampling_stop` |
| `test_flash_storm_stops_sampling_and_exchanges` | no `#sample` and a healthy watchdog check while sampling is stopped |
| `test_sensor_failure_and_a_measurement_that_never_ends` | `#sensor fault rc=-2`, `valid=0 rc=-1 n=0` for missed samples |
| `test_three_hours_of_mixed_link_keep_every_invariant` | a healthy watchdog check at every step and a `#sample` every minute |

`tests/test_sensor_machine.py` checks the driver side of `sensor_done`: one call per measurement
with the documented code, and a start while busy refused at once
(`test_a_start_while_busy_is_refused_at_once`). `firmware/test_policy.c`, run by
`tests/test_stage0.py`, checks `ws_failrun` (trips at the 11th failure, resets on success,
saturates) and the T/RH window means (round half up).

No host test covers the boot failure paths (`#error store-init`, `#unprovisioned`, `#error self-test
failed`, `#error epoch-reserve`, `#boot-retry`) or `SAMPLING_STALL_S`.

```sh
.venv/bin/python -m unittest tests.test_tx_machine tests.test_sensor_machine tests.test_stage0 tests.test_tangle
```
