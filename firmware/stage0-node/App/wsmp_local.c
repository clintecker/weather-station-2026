/* The station's local WSMP modules (wsmp_local.h): each operation is a switch on the port. Ports
 * without a driver yet answer "absent" and give an empty snapshot. */
#define WS_CHECK_FILE 14
#include "wsmp_local.h"
#include <string.h>
#include "i2c_bus.h"
#include "mod_reg.h"
#include "mod_th.h"
#include "ws_check.h"

void local_init(uint32_t boot_id)
{
  mod_th_init(boot_id);
  mod_reg_init(boot_id);
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
}

int local_probe_result(enum wsmp_port p, uint16_t *seq)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  *seq = 0;
  if (u != TH_COUNT) return mod_th_probe(u, seq);
  return r != REG_COUNT ? mod_reg_probe(r, seq) : 0;
}

void local_identity(enum wsmp_port p, uint8_t id[WSMP_IDENTITY_LEN], uint8_t desc[WSMP_DESC_BLOCK_LEN])
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  memset(id, 0, WSMP_IDENTITY_LEN); memset(desc, 0, WSMP_DESC_BLOCK_LEN);
  if (u != TH_COUNT) mod_th_identity(u, id, desc);
  if (r != REG_COUNT) mod_reg_identity(r, id, desc);
}

void local_latch(enum wsmp_port p, uint16_t token, uint32_t utc, uint32_t now_ms)
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  (void)utc;   /* the mean windows need only the station's clock */
  if (u != TH_COUNT) mod_th_latch(u, token, now_ms);
  if (r != REG_COUNT) mod_reg_latch(r, token, now_ms);
}

void local_snapshot(enum wsmp_port p, uint8_t snap[WSMP_SNAPSHOT_LEN])
{
  enum th_unit u = th_unit(p);
  enum reg_unit r = reg_unit(p);
  memset(snap, 0, WSMP_SNAPSHOT_LEN);
  if (u != TH_COUNT) mod_th_snapshot(u, snap);
  if (r != REG_COUNT) mod_reg_snapshot(r, snap);
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
    default: (void)WS_CHECK(0); break;   /* no module submits on the other clients yet */
  }
}
