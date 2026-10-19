/* GENERATED from firmware/common/wsmp_registry.toml by tools/wsmp_registry.py. Do not edit. */
#ifndef WSMP_REGISTRY_H
#define WSMP_REGISTRY_H
#include <stddef.h>
#include <stdint.h>

#define WSMP_REGISTRY_VERSION 1

#define WSMP_Q_AIR_TEMPERATURE 1
#define WSMP_Q_RELATIVE_HUMIDITY 2
#define WSMP_Q_STATION_PRESSURE 3
#define WSMP_Q_WIND_SPEED 4
#define WSMP_Q_WIND_GUST 5
#define WSMP_Q_WIND_FROM_DIRECTION 6
#define WSMP_Q_RAIN_TIPS 7
#define WSMP_Q_UVA_COUNTS 8
#define WSMP_Q_BATTERY_VOLTAGE 9
#define WSMP_Q_BATTERY_CURRENT 10
#define WSMP_Q_ENERGY_IN 11
#define WSMP_Q_ENERGY_OUT 12
#define WSMP_Q_CHARGE_IN 13
#define WSMP_Q_CHARGE_OUT 14
#define WSMP_Q_STATE_OF_CHARGE 15
#define WSMP_Q_CHARGER_STATE 16
#define WSMP_Q_ANEMOMETER_PULSES 17

#define WSMP_U_CEL 1
#define WSMP_U_PERCENT 2
#define WSMP_U_HPA 3
#define WSMP_U_M_PER_S 4
#define WSMP_U_DEG 5
#define WSMP_U_TIP 6
#define WSMP_U_COUNT 7
#define WSMP_U_VOLT 8
#define WSMP_U_AMPERE 9
#define WSMP_U_WATT_HOUR 10
#define WSMP_U_AMPERE_HOUR 11
#define WSMP_U_STATE 12
#define WSMP_U_PULSE 13

#define WSMP_K_POINT 1
#define WSMP_K_MEAN 2
#define WSMP_K_MIN 3
#define WSMP_K_MAX 4
#define WSMP_K_SUM 5
#define WSMP_K_COUNTER 6
#define WSMP_K_GUST 7
#define WSMP_K_VEC_EAST 8
#define WSMP_K_VEC_NORTH 9
#define WSMP_K_STATE 10

#define WSMP_T_AIR_TH 1
#define WSMP_T_PRESSURE 2
#define WSMP_T_UVA 3
#define WSMP_T_ENCL_TH 4
#define WSMP_T_POWER 5
#define WSMP_T_WIND 6
#define WSMP_T_RAIN 7

#define WSMP_RC_MINUTE 0
#define WSMP_RC_HEALTH 1
#define WSMP_KIND_MAX 10U

#define WSMP_POWER_STATE_OFF 0
#define WSMP_POWER_STATE_CHARGING 1
#define WSMP_POWER_STATE_DONE 2
#define WSMP_POWER_STATE_FAULT 3
#define WSMP_WIND_UMS_PER_HZ 666980UL
#define WSMP_WIND_GUST_MS 3000UL
#define WSMP_RAIN_NM_PER_TIP 279400UL

typedef struct { uint16_t quantity; uint8_t kind; } wsmp_type_ch;
typedef struct { uint16_t type; uint8_t schema, channels, report_class; wsmp_type_ch ch[8]; } wsmp_type_entry;

/* The canonical unit of a quantity (WSMP-G3), 0 for an unknown quantity. */
static const uint8_t wsmp_unit_of[18] = { 0, 1, 2, 3, 4, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 2, 12, 13 };
static inline uint8_t wsmp_canonical_unit(uint16_t quantity)
{
  return quantity < sizeof wsmp_unit_of ? wsmp_unit_of[quantity] : 0U;
}

#define WSMP_TYPE_COUNT 7U
static const wsmp_type_entry wsmp_types[WSMP_TYPE_COUNT] = {
  { 1, 1, 2, WSMP_RC_MINUTE, { { 1, 2 }, { 2, 2 } } },
  { 2, 1, 1, WSMP_RC_MINUTE, { { 3, 2 } } },
  { 3, 1, 1, WSMP_RC_MINUTE, { { 8, 2 } } },
  { 4, 1, 2, WSMP_RC_MINUTE, { { 1, 2 }, { 2, 2 } } },
  { 5, 1, 7, WSMP_RC_HEALTH, { { 9, 2 }, { 11, 6 }, { 12, 6 }, { 13, 6 }, { 14, 6 }, { 15, 1 }, { 16, 10 } } },
  { 6, 1, 4, WSMP_RC_MINUTE, { { 17, 6 }, { 5, 7 }, { 6, 8 }, { 6, 9 } } },
  { 7, 1, 1, WSMP_RC_MINUTE, { { 7, 6 } } },
};
/* The registry entry of a module type, NULL for an unknown type. */
static inline const wsmp_type_entry *wsmp_type(uint16_t type)
{
  for (size_t i = 0; i < WSMP_TYPE_COUNT; i++)   /* bound: WSMP_TYPE_COUNT entries */
    if (wsmp_types[i].type == type) return &wsmp_types[i];
  return NULL;
}

#endif
