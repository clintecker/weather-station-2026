# Bench range test for NUCLEO-WL55JC1, built from ST's SubGHz_Phy_PingPong (STM32CubeWL v1.6.0).
# Board code, linker script (110 KB application region) and build rules: ../board/nucleo-wl55jc.
#
#   make                      build build/rangetest.elf/.bin
#   make flash SERIAL=<stlink serial>

BOARD  = ../board/nucleo-wl55jc
BUILD  = build
TARGET = $(BUILD)/rangetest

APP_SRC = $(BOARD_CORE_SRC) \
          $(BOARD_APP_SRC) \
          SubGHz_Phy/App/subghz_phy_app.c \
          App/rt_proto.c \
          $(BOARD_RADIO_SRC) \
          $(BOARD_SYS_SRC)

PROJ_INCS = Core/Inc App SubGHz_Phy/App
DEFS      = -DDEBUG -DVERBOSE_LEVEL=VLEVEL_M -DLOW_POWER_DISABLE=0
OPT       = -Og

# Our own C (the range-test protocol) builds with the strict warning set and -Werror.
STRICT_SRC = App/rt_proto.c

include $(BOARD)/board.mk
