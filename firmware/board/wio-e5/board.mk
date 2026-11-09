# The Seeed Wio-E5 mini's build (issue #35; README.md here has the pin map, the wiring and the steps): its
# generated MCU and capability variables and the `unlock` rule (gen/board.mk, from board.toml by
# tools/boardgen.py), then the rules every STM32WL board shares (../stm32wl/rules.mk).
# There is no debug probe on the mini: flash and unlock go through the NUCLEO's ST-LINK as an external
# probe over SWD (README.md). The first flash of a new board needs `unlock` once (RDP level 1 to 0).
ROOT ?= ../..
include $(BOARD_DIR)/gen/board.mk
include $(ROOT)/firmware/board/stm32wl/rules.mk
