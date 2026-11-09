# GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
# The NUCLEO-WL55JC1 (MB1389): what firmware/board/stm32wl/rules.mk and the project Makefiles take
# from the board.
ifndef BOARD_GEN_MK
BOARD_GEN_MK := 1
BOARD_NAME          := nucleo-wl55jc
BOARD_ROLES         := tx rx
BOARD_BENCH_OLED_OK := 1
BOARD_BENCH_OLED_WHY := 
BOARD_FLASH         := onboard-stlink
MCU_DEF  = STM32WL55xx
ASM_SRC  = $(BOARD_DIR)/startup/startup_stm32wl55jcix.s
LDSCRIPT = $(BOARD_DIR)/STM32WL55JCIX_FLASH.ld
BSP_SRC  = $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo_radio.c $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo.c
BSP_INC  = $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo
endif
