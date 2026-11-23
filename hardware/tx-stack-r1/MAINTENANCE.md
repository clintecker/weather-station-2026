# Maintenance: the TX box, the pods and the meters

What to check on the station once it's on the pole, how often, and what reading means you should do something.
"Monthly" checks are done from Home Assistant and the gateway, with no ladder. "Seasonal" means a look at the
pole every three months, and always before winter and before summer. "Yearly" means a dry day with the lid off.
"After a storm" means after high wind, hail, heavy rain or lightning close by.

## The checks

| Part | How often | What to look at | Act when |
|---|---|---|---|
| Pack: Adafruit #353, 1S3P 6600 mAh Li-ion | Monthly | `battery_soc_pct` from sunset to sunrise on a clear night. Write the overnight drop down at commissioning, and compare against nights in the same season | The overnight drop is a third bigger than at commissioning: the cells have lost capacity. Plan a new pack |
| | Monthly | `pack_temp_c` highs and lows | Over 45 C on summer afternoons: check the lid shade is on and its windows are clear. Under 0 C is normal in winter (see `charger_cold_hold` below) |
| | Yearly | Lid off: the pack on its tray | Any swelling, a split wrap or a warm spot: unplug it at PG1 and replace it |
| Pack fuse F5: Littelfuse 021701.6HXP, 1.6 A, in the Schurter 8601.2000 holder | Yearly, or when the pack looks missing | A blown fuse looks like no pack: `battery_soc_pct` goes unavailable and `vbat_mv` on the `CHARGER` line drops, while the panel still runs SYS by day | Find the short first, then fit one of the two spares from the box's bag |
| Glands: 5 PG-7 #762, 2 PG-9 #761 | Seasonal | Caps tight, drip loops still below each gland, the S4 dowel pin in place | A cap turns by hand, or a cable has pulled through |
| | Yearly | Lid off: the seals, and the silicone round the two flat meter cables | A cracked seal, or the silicone has lifted off the cable |
| O-rings: the #905 lid's, and each pod's 1.5 mm NBR cord | Yearly | Lid off: the O-ring sits in its channel all the way round, no flat spots, no cracks. Any water marks inside | `enclosure_rh_pct` stays high for days after rain, or there's a water mark: replace the O-ring and find where it came in |
| Vents: Amphenol LTW VENT-PS1YBK-N8002 (M12, TX box); Gore VE70510 (BARO box, UV crown) | Yearly | The membranes from inside: clean, not torn, the VE70510s still stuck down flat | A torn or lifted vent: replace it. A blocked BARO vent shows as `pressure_hpa` lagging a neighbouring station by more than 1 hPa when the box warms up |
| UV window: JGS1 quartz, 20 x 1 mm, in the UV crown | Seasonal, or when the readings say so | The window from above: dust, pollen, bird droppings, a film. Clean it with water and a soft cloth, then isopropyl alcohol. Never scrape it | The clear-sky noon peak of `uv_index_est` (or `uva_raw`) drops more than 10 % below the clear days just before it, more than the season explains, and jumps back after a wipe. That's dirt. If it doesn't jump back, check for fog inside the crown (the UV breather vent) |
| TH radiation shield | Seasonal | Spider webs, wasp nests, leaves or dirt between the plates, the SHT45 clean | On a sunny calm day `temperature_c` reads more than 1-2 C over a shaded reference thermometer: clean the plates |
| Rain gauge (SEN-15901 bucket) | Seasonal, and after a storm | Leaves and grit in the funnel and the bucket; the gauge still level | No tips through a rain that a neighbour recorded: clear it, then tip the bucket by hand and watch `rain_tips` go up by one |
| Wind cups and vane (SEN-15901) | Seasonal, and after a storm | The cups spin freely and coast to a stop, no grinding; the vane turns freely | `wind_speed_ms` sits at 0 while the trees are moving, or the cups stop dead: check the bearing and the `meter_link` field on `#status` |
| Lid shade: white PETG (`cage/stl/lid-shade.stl`) | Seasonal | Still pressed on, the 14 windows clear (wasps like them), no cracks | Gone, cracked or blocked: refit or reprint before summer |
| Antenna AE1: Taoglas TI.96.A113 and its taped joint | Seasonal | Standing vertical, tip up; the Scotch 23 + 33+ wrap still tight at the coupling nut and the hinge | The tape has split or lifted: unwrap and re-tape |
| | Yearly | The whip's jacket | Chalky, cracked or soft: replace it (Abracon AANE-WH-0039-1 is the fallback) |
| | Monthly | RSSI in the gateway's `receiver.log` against its first month | Down 6 dB or more and staying there, with nothing changed nearby: check the antenna, its tape and the joint for water |
| Bond: Panduit PV14-14R-L lug, 14 AWG green, SatelliteSale SS-GSG9-1 strap | Yearly, and after any lightning close by | A meter from the bulkhead's body to bare pole metal; the lug and the strap for green or white corrosion | Over 1 ohm, or corrosion: clean both to bare metal, Ideal Noalox, retighten, measure again |

## When an alert fires

The gateway's alerts (`docs/runbook-home-assistant.md`, Alerts):

- **`station_stale`**: no fresh reading. Is the receiver alive (see `receiver_silent`)? Is the battery flat
  (`battery_low` before it)? If the RX is fine and the station's gone quiet, look at the box: the antenna, the pack
  fuse, water inside.
- **`battery_low`**: the gauge reads under 20 %, or the node has dropped to CONSERVE or CRITICAL. After a run of dull
  days that's expected. If it happens in good sun, the panel isn't charging: look at `charger_active_input`, the
  panel's face (snow, leaves, bird droppings), the solar lead and the TVS D6 on J2. A shorted D6 shows on the
  `CHARGER` line as `vbus_mv` near 0 and `pg=0` in full sun.
- **`charger_fault`**: the BQ25798 reports an over-voltage, over-current, VSYS or thermal fault, or the firmware has
  held charging off (wrong part, cell count or read-back). Take the lid off and read the `CHARGER` line on the TX
  console.
- **`charger_cold_hold`**: the pack is under about 6 C and the charger has stopped (it stops below about 4 C). That's
  normal on cold nights and mornings. If it lasts through a sunny winter day, the box isn't warming enough: think
  about where the box faces.
- **`receiver_silent`**: the RX board stopped sending `#alive`. Check its USB cable on the gateway Mac and the
  gateway log. Fix this within about 10 hours: the TX journal holds about 10.1 h of one-minute readings (609
  records), and after that it overwrites the oldest.

## The `CHARGER` line

Lid off, USB-C to the Wio-E5 mini on B3, type `CHARGER` on the TX console. These are the fields to read (the full
list is in `firmware/stage0-node/README.md`):

| Field | Good | Act when |
|---|---|---|
| `cells`, `vreg_mv`, `ichg_ma` | `1`, `4200`, `900` | Anything else: the set-up didn't stick. Note `applies` and `resets` and power-cycle once |
| `vac_ovp`, `voc_pct` | `2` (12 V), `4` | Anything else: same as above |
| `ts`, `pack_dc` | `NORMAL`, and `pack_dc` close to the air temperature (0.1 C units) | `none` for `pack_dc`: the thermistor RT1 on J7 is open or shorted |
| `hold` | `none` | `ts-warm`: the pack is over about 42 C (shade). `ts-cold`: under about 4 C. `readback` or `cells`: the set-up failed |
| `fault0`, `fault1` | `0x00` | Anything set: write it down and look it up in TI SLUSDV2C (REG20, REG21) |
| `vbus_mv`, `pg` | in sun, roughly 5000-7000 and `1` | Near 0 and `0` in full sun: the panel, its lead or D6 |
| `vbat_mv` | 3000-4200 | Under 3000, or missing while the pack is plugged in: check F5 |
