# Bench I2C tool for NUCLEO-WL55JC1: lists what answers on I2C2 and prints the INA228 and MAX17048
# readings once a second (README.md). Board code, linker script (110 KB application region) and build
# rules: ../board/nucleo-wl55jc. Flashing writes only the application region: the node's key and
# journal (pages 55..127) survive, and flashing the node back restores it.
#
#   make                      build build/i2cscan.elf/.bin
#   make flash SERIAL=<stlink serial>

BOARD  = ../board/nucleo-wl55jc
BUILD  = build
TARGET = $(BUILD)/i2cscan

APP_SRC = $(BOARD_CORE_SRC) \
          $(BOARD_APP_SRC) \
          App/i2cscan.c \
          App/bench_regs.c \
          $(BOARD_RADIO_SRC) \
          $(BOARD_SYS_SRC)

HAL_EXTRA = i2c i2c_ex
PROJ_INCS = Core/Inc App
DEFS      = -DDEBUG -DVERBOSE_LEVEL=VLEVEL_M
OPT       = -Og

# Our own C builds with the strict warning set and -Werror.
STRICT_SRC = App/i2cscan.c App/bench_regs.c

include $(BOARD)/board.mk
