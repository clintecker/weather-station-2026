# wsmp_ident: the verdict for a module on a port

In v1 a port number is a place. It doesn't tell you the module type. When the station finds a module
on an I2C port, it reads the module record from the board's ID EEPROM. It may also read the sensor's
own serial. Then it decides: admit the module, quarantine it, or, for a duplicate, check the module
that holds its serial or type first.

`docs/firmware-current-design.md` section 6.7 sets that decision out as an ordered table. This file is
that table as one pure function, `wsmp_identify`, plus the serial rules it needs.

The function does no I/O. The station does that part today. `firmware/stage0-node/App/port_id.c` reads
the record and the sensor serial. It tries a failed record read 3 times in all (the first try plus 2
retries), back to back, before it gives `NO_RECORD` (READ). A record with a CRC failure gets read once
more. `firmware/stage0-node/App/wsmp_host.c` runs the verdict and the holder check that a duplicate
asks for, and it keeps the port states.

This document is the source. `tools/tangle.py` generates `wsmp_ident.c` from the code chunks below.
The header `wsmp_ident.h` is a plain file.

```sh
python3 tools/tangle.py firmware/common/wsmp_ident.lit.md            # write wsmp_ident.c
python3 tools/tangle.py --check firmware/common/wsmp_ident.lit.md    # committed .c == tangle
```

## 1. Guarantees

| Property | Guarantee | Checked by |
|---|---|---|
| Order | the first step of the table that applies decides, the same for every serial source | `tests/test_wsmp_record.py` `Verdict` |
| Serial | the serial comes from the record (namespace 0x01) only when the record is valid, of the probed type and bound to the live sensor; otherwise from the sensor (0x02), else the port (0x00) | `test_step_1_read_failure_takes_the_sensor_or_port_serial`, `test_step_3b_sensor_changed` |
| Record CRC | `record_crc` is the record's CRC only with status 0 (applied); 0 for `NO_RECORD`, `SENSOR_CHANGED`, `CAL_REJECTED` and a quarantine | `test_step_3c_cal_rejected_keeps_the_record_serial_with_crc_0` |
| Duplicates | a serial duplicate is found before a type duplicate, whatever the port order; only a holding module on another port counts | `test_step_4_clone_wins_over_type_duplicate`, `test_only_holding_modules_on_other_ports_count` |
| Flags | `id_flags` is the serial source in bits 0–1 and the record status in bits 4–7 | every `Verdict` test |

## 2. The serial namespaces

The serial's top byte names its source, so serials from different sources never collide (section 6.7,
"Namespaces"). The station-bound fallback is today's `WSMP_LOCAL_SERIAL(port, type)`
(`stage0-node/App/wsmp_local.h`), and its value already has a zero top byte. A sensor serial carries the module type, so an SHT45's serial
can never equal another part's.

```c {#serials}
#define PORT_SERIAL_BASE  0x575300000000ULL   /* "WS" above the port and type: WSMP_LOCAL_SERIAL */
#define PORT_SHIFT        8U
#define NAMESPACE_SHIFT   56U
#define SENSOR_TYPE_SHIFT 40U

uint64_t wsmp_port_serial(uint8_t port, uint16_t type)
{
  return PORT_SERIAL_BASE | (uint64_t)port << PORT_SHIFT | type;
}

uint64_t wsmp_sensor_serial(uint16_t type, uint32_t sensor_serial)
{
  return (uint64_t)WSMP_SRC_SENSOR << NAMESPACE_SHIFT | (uint64_t)type << SENSOR_TYPE_SHIFT | sensor_serial;
}
```

## 3. The verdict order

| Step | Verdict | When | Result |
|---|---|---|---|
| 1 | `NO_RECORD` (READ) | the record could not be read | step 4 with the sensor or port serial, no calibration |
| 2 | `NO_RECORD` (BLANK, NO_MAGIC, VERSION, MALFORMED, CRC) | the record fails checks 2–6 (`wsmp_record_parse`) | as step 1 |
| 3a | `TYPE_CONFLICT` | a valid record of another module type than the probed part | quarantined; stop |
| 3b | `SENSOR_CHANGED` | a valid record whose sensor bind differs from the live sensor | the sensor (or port) serial, no calibration |
| 3c | `CAL_REJECTED` | a valid record that fails only check 7 (`wsmp_cal_check`) | the record's serial, no calibration |
| 4 | duplicate serial | the serial equals that of a holding module on another port | check the holder |
| 5 | duplicate type | the module type is held on another port (one per type in v1) | check the holder |
| 6 | admit | otherwise | the serial, its flags and, for status 0, the record's calibration |

Without a usable record, the serial comes from the sensor if the part has one, else from the port.
That order is the same everywhere (section 6.7, "Serial rules").

```c {#fallback}
static void fallback_serial(const wsmp_observed *o, wsmp_verdict *v)
{
  v->source = o->has_sensor_serial ? (uint8_t)WSMP_SRC_SENSOR : (uint8_t)WSMP_SRC_PORT;
  v->serial = o->has_sensor_serial ? wsmp_sensor_serial(o->probed_type, o->sensor_serial)
                                   : wsmp_port_serial(o->port, o->probed_type);
}
```

A bind of kind 1 matches only a sensor serial that was read and is equal. If a record binds a sensor
whose serial couldn't be read, nothing can confirm the bind. So it counts as changed, and its
calibration never goes onto a sensor it may not belong to.

The station never asks for that verdict, though. A sensor serial that fails its 3 tries leaves the identification incomplete, and the station
decides no verdict from it (`App/port_id.c`, firmware-current-design.md section 6.7, step 3b). So on
the station `SENSOR_CHANGED` means a serial that was read and differs. The rule here just keeps the
function safe on its own.

```c {#bind}
static int bind_matches(const wsmp_record *r, const wsmp_observed *o)
{
  return r->bind_kind == WSMP_BIND_NONE || (o->has_sensor_serial && o->sensor_serial == r->bind_value);
}
```

Steps 1 to 3c decide the record status and the serial. A quarantine stops there, and the function
returns 0. Every other outcome goes on to the duplicate steps. The parsed record stays in the verdict, so the
station can apply its calibration when the status is 0.

```c {#record-steps}
static int record_steps(const wsmp_observed *o, wsmp_verdict *v)
{
  v->status = o->read_ok ? wsmp_record_parse(o->record, &v->record) : (uint8_t)WSMP_REC_READ;
  if (v->status != WSMP_REC_APPLIED)
  {
    fallback_serial(o, v);   /* steps 1 and 2 */
    return 1;
  }
  v->source = WSMP_SRC_RECORD;
  v->serial = v->record.serial;
  if (v->record.type != o->probed_type) return 0;   /* step 3a */
  if (!bind_matches(&v->record, o))
  {
    v->status = WSMP_REC_SENSOR_CHANGED;   /* step 3b */
    fallback_serial(o, v);
    return 1;
  }
  v->status = wsmp_cal_check(&v->record);   /* step 3c */
  if (v->status == WSMP_REC_APPLIED) v->record_crc = v->record.crc;
  return 1;
}
```

Steps 4 and 5 look for a holder. That's a module on another port in the Admitted, Active or Suspect
state. With a non-zero serial the search goes by serial, else by type. A serial is never 0 because
every namespace has a non-zero part, so the two searches can't mix.

```c {#holder}
static const wsmp_port_held *holder(const wsmp_port_held *held, unsigned n, uint8_t port, uint64_t serial, uint16_t type)
{
  for (unsigned i = 0; i < n; i++)
  {
    const wsmp_port_held *h = &held[i];
    if (!h->holding || h->port == port) continue;
    if (serial != 0 ? h->serial == serial : h->type == type) return h;
  }
  return NULL;
}
```

A quarantined module isn't admitted, so its serial, source and flags go nowhere. The console's
`MODULES` line shows only the verdict (`type_conflict`) for that port. The verdict itself still
carries the record's serial, source "record", status 0 and no record CRC.

```c {#identify}
void wsmp_identify(const wsmp_observed *o, const wsmp_port_held *held, unsigned n, wsmp_verdict *v)
{
  memset(v, 0, sizeof *v);
  int go_on = record_steps(o, v);
  v->id_flags = wsmp_id_flags(v->source, v->status);
  if (!go_on)
  {
    v->verdict = WSMP_V_TYPE_CONFLICT;
    return;
  }
  const wsmp_port_held *h = holder(held, n, o->port, v->serial, 0);   /* step 4 */
  if (h != NULL)
  {
    v->verdict = WSMP_V_DUP_SERIAL;
    v->holder_port = h->port;
    return;
  }
  h = holder(held, n, o->port, 0, o->probed_type);   /* step 5 */
  v->verdict = h != NULL ? (uint8_t)WSMP_V_DUP_TYPE : (uint8_t)WSMP_V_ADMIT;   /* or step 6 */
  v->holder_port = h != NULL ? h->port : 0U;
}
```

## 4. The file

```c {#wsmp_ident.c}
#include "wsmp_ident.h"
#include <string.h>
#include "wsmp_cal.h"

<<serials>>

<<fallback>>

<<bind>>

<<record-steps>>

<<holder>>

<<identify>>
```
