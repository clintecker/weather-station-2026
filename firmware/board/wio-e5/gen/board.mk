# GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
# The Seeed Wio-E5 mini (LoRa-E5, STM32WLE5JC): what firmware/board/stm32wl/rules.mk and the project Makefiles take
# from the board.
ifndef BOARD_GEN_MK
BOARD_GEN_MK := 1
BOARD_NAME          := wio-e5
BOARD_ROLES         := tx
BOARD_BENCH_OLED_OK := 0
BOARD_BENCH_OLED_WHY := the OLED's SPI1 pins PA4 and PA5 drive the module's RF switch
BOARD_FLASH         := nucleo-stlink-swd
MCU_DEF  = STM32WLE5xx
ASM_SRC  = $(BOARD_DIR)/startup/startup_stm32wle5xx.s
LDSCRIPT = $(BOARD_DIR)/STM32WLE5JCIX_FLASH.ld
BSP_SRC  =
BSP_INC  =

# RDP level 1 to 0 (mass-erases the flash): OpenOCD's stm32l4x driver, which target/stm32wlx.cfg uses
# for bank 0. "stm32l4x option_load" applies it at once (a system reset).
unlock:
	@test -n "$(SERIAL)" || (echo "usage: make BOARD=wio-e5 unlock SERIAL=<ST-LINK serial>"; exit 1)
	openocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \
	  -c "reset_config srst_only srst_nogate connect_assert_srst" \
	  -c "init" -c "reset halt" -c "stm32l4x unlock 0" -c "stm32l4x option_load 0" -c "shutdown"
.PHONY: unlock
endif
