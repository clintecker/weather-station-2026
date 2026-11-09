# The Seeed Wio-E5 mini (LoRa-E5 module, STM32WLE5JC: the single-core WL55, the same Cortex-M4, 256 KB
# flash, 64 KB RAM and sub-GHz radio). Issue #35; README.md here has the pin map, the wiring and the steps.
#
# This file names the MCU and its board code, then includes the NUCLEO's board.mk, which holds the
# shared rules (the variables a project sets are listed there). What differs from the NUCLEO:
#   - STM32WLE5xx and its startup file (vendor/STM32CubeWL, CMSIS templates), no CM0+;
#   - no ST board support package: SubGHz_Phy/Target/radio_board_if.c drives the RF switch itself;
#   - the linker script STM32WLE5JCIX_FLASH.ld, the NUCLEO's layout unchanged (190 KB application region,
#     pages 95..127 for the node key and journal);
#   - Core/: USART1 on PB6/PB7 (the mini's own USB-UART, its USB-C) for the console, the one user LED
#     (PB5, active low), no buttons, no probe pins; Core/Inc/board_pins.h for the station's pins.
# There is no debug probe on the mini: flash and unlock go through the NUCLEO's ST-LINK as an external
# probe over SWD (README.md). The first flash of a new board needs `unlock` once (RDP level 1 to 0).

MCU_DEF  = STM32WLE5xx
ASM_SRC  = $(BOARD_DIR)/startup/startup_stm32wle5xx.s
LDSCRIPT = $(BOARD_DIR)/STM32WLE5JCIX_FLASH.ld
BSP_SRC  =
BSP_INC  =

include $(BOARD_DIR)/../nucleo-wl55jc/board.mk

# Seeed ships the module with its AT firmware under read-out protection level 1. Regressing it to level 0
# mass-erases the flash (the AT firmware with it); after that `flash` works. OpenOCD 0.12.0's manual
# (Flash Commands, stm32l4x driver, which target/stm32wlx.cfg uses for bank 0): "stm32l4x unlock num:
# Unlocks the entire stm32 device", and "To apply the protection change immediately, use 'stm32l4x
# option_load'", which "will cause a system reset of the device". To be confirmed on the first board.
unlock:
	@test -n "$(SERIAL)" || (echo "usage: make BOARD=wio-e5 unlock SERIAL=<NUCLEO ST-LINK serial>"; exit 1)
	openocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \
	  -c "reset_config srst_only srst_nogate connect_assert_srst" \
	  -c "init" -c "reset halt" -c "stm32l4x unlock 0" -c "stm32l4x option_load 0" -c "shutdown"

.PHONY: unlock
