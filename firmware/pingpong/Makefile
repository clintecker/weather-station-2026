# Command-line build of ST's SubGHz_Phy_PingPong (STM32CubeWL v1.6.0) for NUCLEO-WL55JC1.
# Board code, linker script (64 KB application region) and build rules: ../board/nucleo-wl55jc.
#
#   make                      build build/pingpong.elf/.bin
#   make flash SERIAL=<stlink serial>

BOARD  = ../board/nucleo-wl55jc
BUILD  = build
TARGET = $(BUILD)/pingpong

APP_SRC = $(BOARD_CORE_SRC) \
          SubGHz_Phy/App/app_subghz_phy.c \
          SubGHz_Phy/App/subghz_phy_app.c \
          $(BOARD_RADIO_SRC) \
          $(BOARD_SYS_SRC)

PROJ_INCS = Core/Inc SubGHz_Phy/App
DEFS      = -DDEBUG -DVERBOSE_LEVEL=VLEVEL_M -DLOW_POWER_DISABLE=0
OPT       = -Og

include $(BOARD)/board.mk
