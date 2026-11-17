# Task 4 report: pod electrical checks

Commit: see `git log` ("hardware: pods-r1 electrical checks P1-P7"), pushed to master. Files: hardware/pods-r1/layout/pod_checks.py, tests/test_pods_checks.py, hardware/pods-r1/run.sh (new step).

## TDD evidence
- RED: tests written first; `python -m unittest tests.test_pods_checks` failed with FileNotFoundError (pod_checks.py absent).
- GREEN: 13 tests OK; `sh hardware/pods-r1/run.sh` passes end to end (note: my first run of the reversed-cable test line was fixed in the test, a sed typo, before implementation behaviour was judged).

## Controller rulings
- (a) `netlist(pod)` is a union-find over strip_of plus wire end holes plus the TH lead's pod-end holes (lead pads are nodes joined to the conductor hole). Declared labels only name the groups. test_no_shorts: no strip with two labels, each of 3V3/GND/SDA/SCL/WP is exactly one group equal to the declared pins. test_open_is_caught drops each wire of each pod in turn (every one is caught); test_short_is_caught adds a GND wire from A2 to A4.
- (b) test_pin_map uses literals {2:3V3,3:SDA,4:GND,5:SCL}, 1 and 6 NC and alone on their strips; JACK_NETS is not read by the test.
- TX port model: loaded read-only with importlib under its own name (imports cleanly; no __pycache__). `PORTS` gives the jack, `PIN_MAPS[jack]` the pin to net map (P2_3V3, P2_JSDA..., normalised to 3V3/SDA/SCL/GND). Mux pull-up: model U4 `pullups_k = 10.0` (stated there, so not taken from the spec).
- cable_map reversed = {i: 7-i} (1<->6, 2<->5, 3<->4); end_to_end(pod, port, cable) returns {tx pin: (pod net, tx net)}; reversed gives ("SCL","3V3") on pin 2.
- test_wp_shunt_protects: on -> 3V3, off -> GND via R1.

## Budget per pod (2 m, 100 pF/m TYPICAL)
Pull-ups: TX mux channel 10 k || sensor breakout 10 k || EEPROM breakout 10 k = 3333 ohm (min 967).
- TH: C 280 pF (200 cable + 30 devices + 50 lead 0.5 m), rise 791 ns
- BARO: C 230 pF, rise 650 ns
- UV: C 230 pF, rise 650 ns
All <= 1000 ns. If a budget fails, `budget_failures` names the breakout (e.g. U1) whose 10 k pull-up pack to remove (tested with extra_k); a rise failure says shorten the cable (removing pull-ups slows it).

## Concerns
- cable_pf_per_m is TBD in sources.py; I used 100 pF/m (top of the typical 50-100 pF/m for PVC 24-28 AWG multi-conductor) as a fallback, printed as TYPICAL in the report. It was not looked up from a datasheet. Measure the bought cable. The TH lead uses the same pF/m.
- Device count = 2 breakouts + the TX mux channel (3 x 10 pF); the TX series 100 ohm resistors and the port clamps' capacitance are not modelled.
- Sensor-side pull-ups behind the level shifters are not counted (only the header-side packs the pod sees), per sources.py.
- Adafruit breakouts have no jumper, so "remove" means cutting/desoldering the pack resistor.
- tx-stack-r1/sources.py had another agent's uncommitted edit; I did not touch it.

## Fix round 1
Important 1: `net_of` (and so `end_to_end`, `cable_faults`, `check_all`, `wp_level`) now reads the pin's net from its copper group in the union-find: the declared name, `SHORT(a+b)` for a mixed group, `OPEN(net)` when that net is split over several groups. New test `test_mutated_pod_fails_end_to_end` drops the J1 SDA wire (end_to_end pin 3 = `("OPEN(SDA)","SDA")`) and adds a jack 3V3-GND wire (pin 2 starts `SHORT(`); both make `cable_faults` non-empty, on all three pods. (Written after the fix, so no separate red run.)
Commands: `.venv/bin/python -m unittest tests.test_pods_checks -v` -> Ran 14 tests, OK; `sh hardware/pods-r1/run.sh` -> "P1-P7: all pass", "every check passes".
