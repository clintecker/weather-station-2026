# Outdoor sensor pods (TH, baro, UV): design

Status: reviewed 2026-11-17 (Clint: "likely ok"); one open item, the EEPROM breakout part. From the
conversation with Clint the same day. Builds on the TX card cage
(`hardware/tx-stack-r1/`, design `docs/superpowers/specs/2026-11-09-tx-protoboard-stack-design.md`) and
the module identity design (`docs/firmware-current-design.md` §4.1, §6.7, §6.9).

## Intent

The TX card cage is drawn down to its RJ11 sensor jacks (ports S1-S4: B1 J11-J13, B2 J14). The three
outdoor I2C modules that plug into those jacks exist only as schematic entries (`schematic/model.py`
MOD1-MOD3, "sensor + 24LC32 EEPROM, Perma-Proto 1608"). This design makes them buildable: what each
pod is, where it lives on the mast, how it is sealed, cabled and identified, and the bench sheets
that build it, in the same pipeline and style as the TX cards.

Success: each pod is soldered from the parts on hand plus a short buy list, plugs into any sensor
port on a straight-through cable, is found at boot by its ID EEPROM, and reads outside air
(temperature and humidity, pressure) or open sky (UVA), without water getting to the electronics.

## Goals

- Three pods, one sensor each, each its own module on its own cable and port:
  - **TH**: Adafruit SHT45 with PTFE cap, #6174 (0x44), inside Clint's radiation shield.
  - **Baro**: Adafruit BMP581, #6407 (0x47), outdoors (Clint: the TX box is sealed, not vented).
  - **UV**: Adafruit LTR390, #4831 (0x53), on top of the shield, facing straight up.
- Each pod's electronics on one **Adafruit Perma-Proto Quarter (#1608)**, soldered, carrying:
  the sensor breakout (or, for TH, the lead to it), a **24LC32-class ID EEPROM at 0x50**, and an
  **RJ11 jack: SparkFun BOB-14021 + Amphenol 87180-066LF on a 1x6 header**, the same breakout build
  as the TX cards (tab snapped off, jack pins cut flush).
- Sensor-port pin map, unchanged from the TX (`tx-protoboard-stack-design.md`, RJ11 pin maps):
  pin 2 = 3.3 V, 3 = SDA, 4 = GND, 5 = SCL; pins 1 and 6 unused.
- **One printed PETG box per pod** (Clint), each with its own jack, its own cable gland and a drip
  loop. Swapping or repairing one sensor never opens another pod.
- Bench sheets for the pods drawn from 3D geometry like Sessions 1-5 (`instruction-sheet-style`,
  `draw-breakouts-as-supplied`): every breakout as supplied, every hole named, wires as routed.

## Non-goals

- The EEPROM programming fixture (host tool, `firmware-current-design.md` §6.9 "Programming
  fixture", §13.3). The pods need programmed records before outdoor use, but the tool is a firmware
  task of its own. The pod sheets end with "EEPROM blank, WP strapped as built"; programming is a
  later step.
- A custom PCB, RS-485/RJ45 remote modules (WSMP §13, v2), any MCU on a pod.
- The mast and the pole clamps. The shield's plates and stand stay as Clint printed them; only its top cap
  and its arm are remixed (below, Clint 2026-11-17).
- Calibration coefficients and the siting record (WSMP §15 open items); the design only notes what
  must be recorded.

## Anti-goals

- A connector, solder joint or circuit board inside the shield's measured air, other than the
  SHT45 breakout itself and the four lead joints on its own header pads.
- Any pod whose seal depends on a glued joint that cannot be taken apart.
- A pod that can only be identified by the port it is plugged into: the EEPROM is the identity.
- A UV window that silently changes the reading: the window material is recorded, and its
  transmission becomes a calibration item, never a guess folded into firmware.

## Constraints and facts

- **The shield** is Clint's print, model file `Stevenson_screen_NFS.3mf` (Bambu project; parts named
  "Stevenson screen IQHA with logo"). Its meshes are the reference for every shield dimension; nothing
  on it is measured by hand. Kept locally beside the pod design (licence not known, so not committed:
  see "Left to the builder"). From the meshes:
  - six louver plates, each 100 x 100 x 20 mm (object_79), a closed top cap 100 x 100 x 19.2
    (object_70), plate pitch set by the 15 mm posts;
  - three post columns, diameter about 10 mm, centred 25 mm from the axis, leaving a **clear core
    of diameter 40 mm**;
  - a **sensor stand** (object_68): a strip about 14 x 5 mm, 81 mm tall on a three-legged foot
    (53 x 47), about 8 mm off the axis, zip-tie teardrops up its face;
  - a **base cup** (object_67), diameter about 59, 32.6 tall, with a foot about 19 x 54 that meets
    the **L-bracket arm** (object_72, 58.8 x 124 x 64, holes in its upright plate) and a small pole
    clamp.
  - The 3MF is laid out as printed (parts flat on the bed). The assembled positions (plates on the
    base cup, the stand's orientation to the posts) are derived from the parts' mating features,
    not assumed; the 2026-11-17 fit check assumed the stand on the plate axis and must be redone.
- **SHT45 #6174** board 25.4 x 17.8 mm with its PTFE-capped sensor. The 2026-11-17 fit check put it
  on the stand's inner face with more than 5 mm to every post, but that check assumed the stand on the
  plate axis (above), so the fit is provisional until the assembled-shield check is re-run.
- **Perma-Proto Quarter #1608** (about 44 x 51 mm: take the exact outline and hole grid from
  Adafruit's own file) does not fit the shield's core: the TH pod board lives outside the shield.
- **I2C on a port**: each port's lines are pulled up on the TX side by the mux breakout's 10 k
  (`tx-protoboard-stack-design.md`, cable limit). Every Adafruit breakout on a pod adds its own
  pull-ups. The total per port must stay above the bus's floor and the cable's rise-time limit
  (about 236 pF at 100 kHz with about 5 k): the builder computes the per-pod total and removes
  pull-ups where the breakout allows (cut-trace jumpers), recording which.
- **Cable**: straight-through RJ11/RJ12, round, through a PG-7 gland (3.0-4.3 mm seal) at each end.
  The PG-7 (#762) seals only 3.0-4.3 mm, and common round 6-conductor modular cable is about 4.5 mm,
  so the bulk cable must be bought to an outside diameter of 3.0-4.3 mm (measured, not taken from the
  listing), or that end gets a PG-9 (4.0-6.4 mm). The same limit applies to the TX box's PG-7s.
  A 6P plug (about 12 mm across its corners) cannot pass a gland: the cable goes through both glands
  first and both plugs are crimped after (Clint has 6P crimp plugs; a 6P crimper is needed, see
  `hardware/tx-stack-r1/build/ASSEMBLY.md`). Length per pod is set by the mast layout; any run over
  about 2-3 m needs the port's pull-ups revisited (above).
- **Identity**: every pod carries a programmed 24LC32A record (`firmware-current-design.md` §6.9),
  WP pad strapped so the record is write-protected in service. Each EEPROM shares 0x50 with the
  others only behind the TX mux (one port per channel).
- **TX side**: four sensor ports, three pods. The fourth port (S4, B2 J14) stays spare.
- **Parts status** (`/Users/clint/code/electronics/INVENTORY.md`, review 2026-11-17):
  - On hand or on the 2026-11-09 order: the three sensors (#6174 x2, #6407, #4831), Perma-Proto
    quarters #1608 (10), BOB-14021 (10 + the old panel), 87180-066LF jacks (20), 2-pin headers and
    shunts (100 each, for the WP jumper), RJ12 6P6C crimp plugs (100).
  - **Not in the inventory:** the EEPROM breakouts (Clint says they are in the inventory; no line
    names them, and `docs/current-system.md` records the hub build with no ID EEPROMs at 0x50), a
    6P modular crimper (INVENTORY suggests Klein VDV226-011-SEN), bulk round 6-conductor cable (the
    straight-through cables on hand have plugs fitted, which pass no gland), and enough PG-7 glands
    for three pods on top of the TX box's seven.
- **Cable runs are under 2 m** (Clint, 2026-11-17): the TX side's pull-ups and the per-port total
  above hold; no stronger pull-ups at the pod jacks.
- **Shield remix allowed** (Clint, 2026-11-17): the top cap (object_70) and the L-bracket arm
  (object_72) are reprinted from remixed versions of their meshes: the cap gains screw bosses for the
  UV box, the arm becomes longer (or gains a second arm) with mounting faces for the TH and baro boxes
  beside the base cup. The plates, posts, stand and base cup stay as printed; the base cup may get a
  hole for the TH lead only if no existing opening serves (check the meshes first).

## Approaches considered

**TH pod: where the board goes** (the Perma-Proto quarter cannot enter the shield's 40 mm core).
- **A, chosen (Claude's pick, Clint did not object):** only the SHT45 breakout goes inside, zip-tied
  to the stand's inner face, on a short soldered 4-wire lead down through the base cup to the TH pod
  box on the L-bracket arm, which holds the EEPROM and the jack. The measured air sees one small
  board and a lead; the jack, the solder and the EEPROM are outside it.
- B: a custom round board under 36 mm with everything on it, jack facing down out of the base.
  Rejected: a BOB-14021 and an EEPROM breakout do not fit, and it puts a connector in the airflow.

**Baro pod: where the BMP581 goes** (Clint: the box is not vented).
- **Chosen (Clint): its own outdoor pod box on the arm**, beside the TH pod box, with a sheltered
  downward vent.
- Rejected: venting the TX box and putting the BMP581 inside on S4 (Claude's first pick; Clint chose
  outdoors), and doing both.

**UV pod: where it sits.**
- **Chosen (Clint): on the shield's top cap**, a small pod box screwed to the cap's flat top, its
  window facing straight up, its cable down the outside of the louvers to the arm; the cap is
  reprinted with bosses for it.
- Rejected: on the arm (the shield and the pole shade it part of the day); its own stub mast (one
  more bracket to design for no gain over the cap).

**Housing: one box per pod or one shared box.**
- **Chosen (Clint): one box per pod**, the same printed box family, each with its own jack and
  gland.
- Rejected: one shared box (two jacks and glands in one box, and the baro vent would open the TH
  pod's box too).

## The design (decided)

1. **Pod board, all three pods**: Perma-Proto Quarter; the BOB-14021 jack breakout on a 1x6 header
   built exactly as on the TX cards; the 24LC32 EEPROM breakout soldered on its header; the jack's
   pins 2-5 wired to the board's 3.3 V, SDA, GND, SCL; series and protection parts as on the TX side
   are NOT duplicated on the pod (the TX port already has the PTC, the series resistors and the
   clamps).
2. **TH pod**: SHT45 #6174 on the shield stand, a 4-wire lead (stranded, colours as the TX
   convention: red 3.3 V, black GND, yellow SCL, blue SDA) soldered to its header pads, through the
   base cup, into the TH pod box through a small gland or grommet, to the pod board. Pod box on the
   remixed arm.
3. **Baro pod**: BMP581 #6407 on the pod board; its box on the remixed arm beside the TH box; a downward-facing
   vent port with a baffle (no direct path for rain or spray), and an ePTFE membrane if one is on
   hand.
4. **UV pod**: LTR390 #4831 on the pod board, sensor face up under a UV-transmitting window in the
   box lid (material recorded: PTFE diffuser or UV-grade acrylic/quartz); box screwed to the
   remixed top cap's bosses; cable down the outside of the shield, clipped, to the arm.
5. **EEPROM write-protect**: a 2-pin header and a shunt on each pod board (Clint, 2026-11-17):
   shunt on = protected. Programming means lid off, shunt off, program, shunt back on. The
   sensor-port pin map does not change.
6. **Parts come from the bench** (Clint, 2026-11-17): each bench sensor moves to its pod together
   with its own EEPROM breakout, so its serial and record move with it and no copy-and-invalidate
   step is needed. The pod board is drawn around that EEPROM breakout as supplied (Clint names the
   board; until then it is the Adafruit 24LC32 STEMMA QT breakout, its outline, pull-ups and WP
   jumper read from Adafruit's files). The bench loses these sensors when the pods are built.
   **Open (blocks the pod board layout):** the EEPROM breakout's maker and number, and how many; it is
   not in `INVENTORY.md` (above).
7. **Every pod box**: printed PETG, light colour, UV paint or clear coat outside (as the TX base); a
   lid on an O-ring or gasket held by screws into heat-set inserts (taken apart, never glued); one
   PG-7 gland at the bottom for the port cable; a drip loop below the gland; a mounting face that
   matches the remixed arm's or the remixed cap's bosses.
8. **Cables**: one round straight-through 6-conductor cable per pod, OD 3.0-4.3 mm for the PG-7s,
   crimped after passing the glands at both ends; length from the mast layout (under 2 m). The TH
   pod's lead from the SHT45 to its pod board (about 0.3-0.5 m) counts toward that port's bus length
   and capacitance.
9. **Sheets**: a new session (or one per pod) in `hardware/tx-stack-r1/sheets/`'s pipeline style:
   parts as supplied, each pod board step by step, the TH lead and the shield stand, each box, the
   continuity checks before power, the cable crimp order.
10. **Model and checks**: the pods become placed parts in a layout model like `layout/stack.py`
   (board, breakouts, jack, box), with the same kind of checks (holes, strips, clearances, box fit,
   I2C address and pull-up totals per port, the pin map end to end from pod jack to TX port).

## Left to the builder (calls Claude makes, Clint can override)

- The pod board layout (which holes, which strips, wire routes) and the box geometry, from the parts'
  own drawings and the shield meshes.
- The assembled shield (plate stack, stand orientation, base cup to arm) from the meshes' mating
  features, and a re-run of the fit check on the assembled model.
- Whether the shield file can be committed: its licence is unknown, so keep it out of git (a local
  path in the pod design's sources, with a hash) unless Clint says it is his own work.
- Which breakout pull-ups to remove on each pod, from the per-port total.
- The vent baffle and window details; each cable's length (under 2 m) from where Clint mounts the
  shield on the pole.
- The remixed cap and arm geometry, from the original meshes.
