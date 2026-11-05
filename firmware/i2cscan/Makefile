# Bench I2C tool for NUCLEO-WL55JC1: lists what answers on I2C2 and prints the INA228 and MAX17048
# readings once a second (README.md). Board code, linker script (190 KB application region) and build
# rules: ../board/nucleo-wl55jc. Flashing writes only the application region: the node's key and
# journal (pages 95..127) survive, and flashing the node back restores it.
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
          ../common/power_regs.c \
          App/bench_screen.c \
          App/meters.c \
          App/oled.c \
          ../common/oled_fb.c \
          ../common/oled_draw.c \
          ../common/font5x7.c \
          $(BOARD_RADIO_SRC) \
          $(BOARD_SYS_SRC)

HAL_EXTRA = i2c i2c_ex adc adc_ex lptim
PROJ_INCS = Core/Inc App ../common   # power_regs.h, oled_fb.h: shared with the node (and benchlink)
DEFS      = -DDEBUG -DVERBOSE_LEVEL=VLEVEL_M
OPT       = -Og

# Our own C builds with the strict warning set and -Werror.
STRICT_SRC = App/i2cscan.c App/meters.c App/bench_regs.c ../common/power_regs.c App/bench_screen.c App/oled.c ../common/oled_fb.c ../common/oled_draw.c ../common/font5x7.c

include $(BOARD)/board.mk
