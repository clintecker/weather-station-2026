/* The station's local WSMP modules (wsmp_local.h): each operation is a switch on the port. Ports
 * without a driver yet answer "absent" and give an empty snapshot. */
#define WS_CHECK_FILE 14
#include "wsmp_local.h"
#include <string.h>
#include "i2c_bus.h"
#include "mod_power.h"
#include "mod_rain.h"
#include "mod_reg.h"
#include "mod_th.h"
#include "mod_wind.h"
#include "port_id.h"
#include "ws_check.h"

typedef struct { uint64_t serial; uint16_t id_flags, caps; uint8_t set; } port_ident;
static port_ident ident_of[P_COUNT];
static uint32_t epoch;

void local_pack_identity(enum wsmp_port p, uint16_t type, uint8_t channels, uint32_t boot_id,
                         const uint8_t desc[WSMP_DESC_BLOCK_LEN], uint8_t id[WSMP_IDENTITY_LEN])
{
  const port_ident *a = &ident_of[p];
  const wsmp_identity ident = { .type = type, .schema = 1, .channels = channels, .fw_major = 1, .fw_minor = 0,
                                .serial = a->set ? a->serial : WSMP_LOCAL_SERIAL(p, type), .boot_id = boot_id,
                                .caps = a->caps, .id_flags = a->id_flags,
                                .desc_digest = wsmp_crc32c(desc, WSMP_DESC_BLOCK_LEN) };
  wsmp_pack_identity(&ident, id);
}

void local_set_identity(enum wsmp_port p, uint64_t serial, uint16_t id_flags, uint16_t caps)
{
  ident_of[p] = (port_ident){ .serial = serial, .id_flags = id_flags, .caps = caps, .set = 1 };
}

uint32_t local_boot_epoch(void) { return epoch; }

void local_init(uint32_t boot_id, uint32_t now_ms)
{
  epoch = boot_id;
  memset(ident_of, 0, sizeof ident_of);
  port_id_init();
  mod_th_init(boot_id, now_ms);
  mod_reg_init(boot_id, now_ms);
  mod_power_init(boot_id, now_ms);
  mod_wind_init(boot_id, now_ms);
  mod_rain_init(boot_id, 0, now_ms);   /* the application applies the stored setting (store_rain_enabled) */
  i2c_bus_init();
}

/* The temperature and humidity unit of a port, or TH_COUNT for another port. */
static enum th_unit th_unit(enum wsmp_port p)
{
  if (p == P_AIR_TH) return TH_AIR;
  if (p == P_ENCL_TH) return TH_ENCL;
  return TH_COUNT;
}

/* The register unit of a port, or REG_COUNT for another port. */
static enum reg_unit reg_unit(enum wsmp_port p)
{
  if (p == P_PRESSURE) return REG_PRESSURE;
  if (p == P_UVA) return REG_UVA;
  return REG_COUNT;
}

void local_tick(enum wsmp_port p, uint32_t now_ms)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  if (u != TH_COUNT) mod_th_tick(u, now_ms);
  if (r != REG_COUNT) mod_reg_tick(r, now_ms);
  if (p == P_POWER) mod_power_tick(now_ms);
  if (p == P_WIND) mod_wind_tick(now_ms);
  if (p == P_RAIN) mod_rain_tick(now_ms);
}

int local_probe_result(enum wsmp_port p, uint16_t *seq)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  *seq = 0;
  if (u != TH_COUNT) return mod_th_probe(u, seq);
  if (p == P_POWER) return mod_power_probe(seq);
  if (p == P_WIND) return mod_wind_probe(seq);
  if (p == P_RAIN) return mod_rain_probe(seq);
  return r != REG_COUNT ? mod_reg_probe(r, seq) : 0;
}

void local_identity(enum wsmp_port p, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  memset(id, 0, WSMP_IDENTITY_LEN); memset(desc, 0, WSMP_DESC_BLOCK_LEN);
  if (u != TH_COUNT) mod_th_identity(u, id, desc);
  if (r != REG_COUNT) mod_reg_identity(r, id, desc);
  if (p == P_POWER) mod_power_identity(id, desc);
  if (p == P_WIND) mod_wind_identity(id, desc);
  if (p == P_RAIN) mod_rain_identity(id, desc);
}

void local_bind(enum wsmp_port p, const wsmp_record *applied, uint32_t boot_id, uint32_t now_ms)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  if (u != TH_COUNT) mod_th_bind(u, applied, boot_id, now_ms);
  if (r != REG_COUNT) mod_reg_bind(r, applied, boot_id, now_ms);
}

void local_hold(enum wsmp_port p, int on)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  if (u != TH_COUNT) mod_th_hold(u, on);
  if (r != REG_COUNT) mod_reg_hold(r, on);
}

int local_idle(enum wsmp_port p)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  if (u != TH_COUNT) return mod_th_idle(u);
  return r != REG_COUNT ? mod_reg_idle(r) : 1;
}

int local_has_sensor_serial(enum wsmp_port p) { return p == P_AIR_TH; }

void local_id_check(enum wsmp_port p)
{
  enum reg_unit r = reg_unit(p);
  if (p == P_AIR_TH) mod_th_serial_request(TH_AIR);
  if (r != REG_COUNT) mod_reg_id_check(r);
}

int local_id_result(enum wsmp_port p, uint32_t *serial)
{
  enum reg_unit r = reg_unit(p);
  *serial = 0;
  if (p == P_AIR_TH) return mod_th_serial_result(TH_AIR, serial);
  return r != REG_COUNT ? mod_reg_id_result(r) : I2C_EID;
}

uint16_t local_type(enum wsmp_port p)
{
  static const uint16_t type[P_COUNT] = { 0, WSMP_T_AIR_TH, WSMP_T_PRESSURE, WSMP_T_UVA, WSMP_T_ENCL_TH,
                                          WSMP_T_POWER, WSMP_T_WIND, WSMP_T_RAIN };
  return type[p];
}

void local_latch(enum wsmp_port p, uint16_t token, uint32_t utc, uint32_t now_ms)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  (void)utc;   /* the mean windows need only the station's clock */
  if (u != TH_COUNT) mod_th_latch(u, token, now_ms);
  if (r != REG_COUNT) mod_reg_latch(r, token, now_ms);
  if (p == P_POWER) mod_power_latch(token, now_ms);
  if (p == P_WIND) mod_wind_latch(token, now_ms);
  if (p == P_RAIN) mod_rain_latch(token, now_ms);
}

void local_snapshot(enum wsmp_port p, uint8_t snap[WSMP_SNAPSHOT_LEN])
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  memset(snap, 0, WSMP_SNAPSHOT_LEN);
  if (u != TH_COUNT) mod_th_snapshot(u, snap);
  if (r != REG_COUNT) mod_reg_snapshot(r, snap);
  if (p == P_POWER) mod_power_snapshot(snap);
  if (p == P_WIND) mod_wind_snapshot(snap);
  if (p == P_RAIN) mod_rain_snapshot(snap);
}

/* The completion of a bus transfer (i2c_bus.h): to the module that owns the client. */
void i2c_bus_done(enum i2c_client c, int rc)
{
  switch (c)
  {
    case I2C_C_SHT45: mod_th_i2c_done(TH_AIR, rc); break;
    case I2C_C_SHTC3: mod_th_i2c_done(TH_ENCL, rc); break;
    case I2C_C_BMP581: mod_reg_i2c_done(REG_PRESSURE, rc); break;
    case I2C_C_LTR390: mod_reg_i2c_done(REG_UVA, rc); break;
    case I2C_C_INA228: case I2C_C_MAX17048: mod_power_i2c_done(rc); break;
    case I2C_C_REC_AIR: port_id_i2c_done(P_AIR_TH, rc); break;
    case I2C_C_REC_PRESSURE: port_id_i2c_done(P_PRESSURE, rc); break;
    case I2C_C_REC_UVA: port_id_i2c_done(P_UVA, rc); break;
    default: (void)WS_CHECK(0); break;   /* no module submits on the other clients yet */
  }
}
