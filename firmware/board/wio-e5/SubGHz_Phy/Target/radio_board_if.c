/**
  ******************************************************************************
  * @file    radio_board_if.c
  * @brief   The interface between the SubGHz_Phy middleware and the Seeed LoRa-E5 module (Wio-E5 mini)
  ******************************************************************************
  * weather-station-2026 (issue #35): ST's CubeMX template (../../../nucleo-wl55jc/SubGHz_Phy/Target), with
  * its "user to provide its board code" branch written for this module. No BSP: USE_BSP_DRIVER is not
  * defined (Core/Inc/platform.h).
  *
  * The RF switch: two GPIOs, PA4 (CTRL1) and PA5 (CTRL2), push-pull. The truth table is Seeed's own STM32CubeWL
  * port, https://github.com/Seeed-Studio/LoRaWan-E5-Node at commit 163c05379b1805dd8f2c061d4557a69985acc953,
  * Drivers/BSP/STM32WLxx_LoRa_E5_mini/stm32wlxx_LoRa_E5_mini_radio.c, BSP_RADIO_ConfigRFSwitch (lines 99-136),
  * with the pins from stm32wlxx_LoRa_E5_mini_radio.h lines 84-92 (CTRL1 = GPIOA pin 4, CTRL2 = GPIOA pin 5):
  *
  *   state     PA4  PA5   Seeed's comment
  *   OFF        0    0    "Turn off switch"                      (lines 103-108)
  *   RX         1    0    "Turns On in Rx Mode the RF Switch"    (lines 110-115)
  *   RFO_LP     1    1    "Turns On in Tx Low Power"             (lines 117-122; not wired on this module)
  *   RFO_HP     0    1    "Turns On in Tx High Power"            (lines 124-129)
  *
  * Zephyr agrees on RX and TX: dts/arm/seeed_studio/lora-e5.dtsi (commit 0235217d) names PA4
  * tx-enable-gpios and PA5 rx-enable-gpios, both GPIO_ACTIVE_LOW: RX = PA4 high, PA5 low; TX = PA4 low,
  * PA5 high. They differ on OFF: Zephyr leaves both enables inactive (both high, Seeed's RFO_LP code),
  * Seeed drives both low. This file follows Seeed's BSP, which its own firmware runs with; OFF is
  * UNVERIFIED on the hardware (the bench check: RX and TX work, and the sleep current with OFF).
  *
  * The rest, from the same BSP file and Zephyr's: a TCXO (BSP_RADIO_IsTCXO, RADIO_CONF_TCXO_SUPPORTED;
  * Zephyr hse-tcxo, dio3-tcxo-voltage 1.7 V: radio_conf.h), the SMPS fitted (BSP_RADIO_IsDCDC,
  * RADIO_CONF_DCDC_SUPPORTED), the TX path RFO_HP only (BSP_RADIO_GetTxConfig returns RADIO_CONF_RFO_HP;
  * Zephyr power-amplifier-output = "rfo-hp", rfo-hp-max-power = <22>).
  ******************************************************************************
  */
#include "radio_board_if.h"

#define RFO_LP_MAX_DBM 15   /* not wired on this module; ST's template value */
#define RFO_HP_MAX_DBM 22   /* Zephyr rfo-hp-max-power */

int32_t RBI_Init(void)
{
  GPIO_InitTypeDef gpio = { 0 };
  RF_SW_GPIO_CLK_ENABLE();
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  gpio.Pin = RF_SW_CTRL1_PIN;
  HAL_GPIO_Init(RF_SW_CTRL1_GPIO_PORT, &gpio);
  gpio.Pin = RF_SW_CTRL2_PIN;
  HAL_GPIO_Init(RF_SW_CTRL2_GPIO_PORT, &gpio);
  return RBI_ConfigRFSwitch(RBI_SWITCH_OFF);
}

int32_t RBI_DeInit(void)
{
  (void)RBI_ConfigRFSwitch(RBI_SWITCH_OFF);
  HAL_GPIO_DeInit(RF_SW_CTRL1_GPIO_PORT, RF_SW_CTRL1_PIN);
  HAL_GPIO_DeInit(RF_SW_CTRL2_GPIO_PORT, RF_SW_CTRL2_PIN);
  return 0;
}

static void rf_switch(GPIO_PinState ctrl1, GPIO_PinState ctrl2)
{
  HAL_GPIO_WritePin(RF_SW_CTRL1_GPIO_PORT, RF_SW_CTRL1_PIN, ctrl1);
  HAL_GPIO_WritePin(RF_SW_CTRL2_GPIO_PORT, RF_SW_CTRL2_PIN, ctrl2);
}

int32_t RBI_ConfigRFSwitch(RBI_Switch_TypeDef Config)
{
  switch (Config)
  {
    case RBI_SWITCH_OFF:    rf_switch(GPIO_PIN_RESET, GPIO_PIN_RESET); break;
    case RBI_SWITCH_RX:     rf_switch(GPIO_PIN_SET, GPIO_PIN_RESET); break;
    case RBI_SWITCH_RFO_LP: rf_switch(GPIO_PIN_SET, GPIO_PIN_SET); break;     /* never asked: RBI_CONF_RFO_HP */
    case RBI_SWITCH_RFO_HP: rf_switch(GPIO_PIN_RESET, GPIO_PIN_SET); break;
    default: break;
  }
  return 0;
}

int32_t RBI_GetTxConfig(void) { return RBI_CONF_RFO; }

int32_t RBI_IsTCXO(void) { return IS_TCXO_SUPPORTED; }

int32_t RBI_IsDCDC(void) { return IS_DCDC_SUPPORTED; }

int32_t RBI_GetRFOMaxPowerConfig(RBI_RFOMaxPowerConfig_TypeDef Config)
{
  return Config == RBI_RFO_LP_MAXPOWER ? RFO_LP_MAX_DBM : RFO_HP_MAX_DBM;
}
