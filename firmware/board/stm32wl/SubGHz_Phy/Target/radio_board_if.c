/**
  ******************************************************************************
  * @file    radio_board_if.c
  * @brief   The interface between the SubGHz_Phy middleware and the board's radio front end
  ******************************************************************************
  * weather-station-2026 (issue #36): one file for every STM32WL board, driven by the board's generated
  * gen/board_caps.h (board.toml [radio]; tools/boardgen.py). It replaces ST's CubeMX template
  * (Copyright (c) 2021 STMicroelectronics, licensed under the terms in the LICENSE file of STM32CubeWL),
  * which each board used to copy and edit. Two drivers, by board.toml [radio] driver:
  *
  *   "st-bsp"  ST's BSP does it all (the NUCLEO-WL55JC1: Drivers/BSP/STM32WLxx_Nucleo, USE_BSP_DRIVER in
  *             its Core/Inc/platform.h): the template's BSP branch, unchanged. board.toml still holds the
  *             BSP's truth table, which tests/test_boardgen.py checks against the BSP source.
  *   "gpio"    this file drives the RF switch: BOARD_RF_SW_* name its pins, the rf_switch() parameters and
  *             body, and each state's levels (the truth table); BOARD_RFO the PA path, BOARD_TCXO and
  *             BOARD_DCDC (radio_board_if.h), BOARD_RFO_*_MAX_DBM the RFO limits.
  * The TCXO voltage and start-up go to the radio driver through radio_conf.h.
  ******************************************************************************
  */
#include "radio_board_if.h"

#if BOARD_RF_SWITCH_BSP

int32_t RBI_Init(void)
{
  return BSP_RADIO_Init();
}

int32_t RBI_DeInit(void)
{
  return BSP_RADIO_DeInit();
}

int32_t RBI_ConfigRFSwitch(RBI_Switch_TypeDef Config)
{
  return BSP_RADIO_ConfigRFSwitch((BSP_RADIO_Switch_TypeDef) Config);
}

int32_t RBI_GetTxConfig(void)
{
  return BSP_RADIO_GetTxConfig();
}

int32_t RBI_IsTCXO(void)
{
  return BSP_RADIO_IsTCXO();
}

int32_t RBI_IsDCDC(void)
{
  return BSP_RADIO_IsDCDC();
}

int32_t RBI_GetRFOMaxPowerConfig(RBI_RFOMaxPowerConfig_TypeDef Config)
{
  return BSP_RADIO_GetRFOMaxPowerConfig((BSP_RADIO_RFOMaxPowerConfig_TypeDef) Config);
}

#else

int32_t RBI_Init(void)
{
  GPIO_InitTypeDef gpio = { 0 };
  BOARD_RF_SW_CLK_ENABLE();
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  BOARD_RF_SW_PINS_INIT(&gpio);
  return RBI_ConfigRFSwitch(RBI_SWITCH_OFF);
}

int32_t RBI_DeInit(void)
{
  (void)RBI_ConfigRFSwitch(RBI_SWITCH_OFF);
  BOARD_RF_SW_PINS_DEINIT();
  return 0;
}

static void rf_switch(BOARD_RF_SW_PARAMS)
{
  BOARD_RF_SW_WRITE();
}

int32_t RBI_ConfigRFSwitch(RBI_Switch_TypeDef Config)
{
  switch (Config)
  {
    case RBI_SWITCH_OFF:    rf_switch(BOARD_RF_SW_OFF); break;
    case RBI_SWITCH_RX:     rf_switch(BOARD_RF_SW_RX); break;
    case RBI_SWITCH_RFO_LP: rf_switch(BOARD_RF_SW_TX_LP); break;
    case RBI_SWITCH_RFO_HP: rf_switch(BOARD_RF_SW_TX_HP); break;
    default: break;
  }
  return 0;
}

int32_t RBI_GetTxConfig(void) { return RBI_CONF_RFO; }

int32_t RBI_IsTCXO(void) { return IS_TCXO_SUPPORTED; }

int32_t RBI_IsDCDC(void) { return IS_DCDC_SUPPORTED; }

int32_t RBI_GetRFOMaxPowerConfig(RBI_RFOMaxPowerConfig_TypeDef Config)
{
  return Config == RBI_RFO_LP_MAXPOWER ? BOARD_RFO_LP_MAX_DBM : BOARD_RFO_HP_MAX_DBM;
}

#endif
