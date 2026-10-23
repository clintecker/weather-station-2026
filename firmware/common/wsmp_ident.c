/* GENERATED from wsmp_ident.lit.md by tools/tangle.py: do not edit. Edit the document, then run
 * tools/tangle.py firmware/common/wsmp_ident.lit.md (tests/test_tangle.py checks this file). */
#include "wsmp_ident.h"
#include <string.h>
#include "wsmp_cal.h"

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

static void fallback_serial(const wsmp_observed *o, wsmp_verdict *v)
{
  v->source = o->has_sensor_serial ? (uint8_t)WSMP_SRC_SENSOR : (uint8_t)WSMP_SRC_PORT;
  v->serial = o->has_sensor_serial ? wsmp_sensor_serial(o->probed_type, o->sensor_serial)
                                   : wsmp_port_serial(o->port, o->probed_type);
}

static int bind_matches(const wsmp_record *r, const wsmp_observed *o)
{
  return r->bind_kind == WSMP_BIND_NONE || (o->has_sensor_serial && o->sensor_serial == r->bind_value);
}

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
