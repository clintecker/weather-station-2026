# The NUCLEO-WL55JC1's build: its generated MCU and capability variables (gen/board.mk, from board.toml by
# tools/boardgen.py), then the rules every STM32WL board shares (../stm32wl/rules.mk, which lists what a
# project sets). Every NUCLEO project (stage0-node, rangetest, i2cscan, benchlink) includes this file.
ROOT ?= ../..
include $(BOARD_DIR)/gen/board.mk
include $(ROOT)/firmware/board/stm32wl/rules.mk
