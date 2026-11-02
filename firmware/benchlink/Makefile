# Bench telemetry link for NUCLEO-WL55JC1 (README.md): ROLE=tx sends the bench's power and air readings
# every 5 s over plain LoRa; ROLE=rx prints every packet. A test tool, not the station protocol.
# Flashing writes only the application region: the node's key and journal (pages 55..127) survive.
#
#   make ROLE=tx|rx                    build build/<role>/benchlink-<role>.elf/.bin
#   make ROLE=tx|rx flash SERIAL=<stlink serial>

ROLE  ?= tx
BOARD  = ../board/nucleo-wl55jc
BUILD  = build/$(ROLE)
TARGET = $(BUILD)/benchlink-$(ROLE)

APP_SRC = $(BOARD_CORE_SRC) \
          $(BOARD_APP_SRC) \
          App/benchlink.c \
          App/bl_guard.c \
          App/bl_pkt.c \
          ../stage0-node/App/fault.c \
          ../i2cscan/App/bench_regs.c \
          ../common/power_regs.c \
          $(BOARD_RADIO_SRC) \
          $(BOARD_SYS_SRC)

IT_SRC    = Core/Src/stm32wlxx_it.c
HAL_EXTRA = i2c i2c_ex adc adc_ex iwdg
PROJ_INCS = Core/Inc App ../i2cscan/App ../common   # bench_regs.h, power_regs.h
EXTRA_INCS = ../stage0-node/App   # fault.h only; searched after everything else
DEFS      = -DDEBUG -DVERBOSE_LEVEL=VLEVEL_M -DBL_ROLE_$(ROLE)
OPT       = -Og

STRICT_SRC = App/benchlink.c App/bl_guard.c App/bl_pkt.c ../i2cscan/App/bench_regs.c ../common/power_regs.c

include $(BOARD)/board.mk
