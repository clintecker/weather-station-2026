# Stage-0 NUCLEO-WL55JC1 firmware, two roles from one tree.
#
#   make ROLE=tx                         sensor node  -> build/tx/stage0-tx.{elf,bin}
#   make ROLE=rx                         USB receiver -> build/rx/stage0-rx.{elf,bin}
#   make ROLE=tx flash SERIAL=<stlink>   program one board (see docs/hardware for serials)
#   make ROLE=tx stack                   worst-case stack bound vs the linker's reservation
#   make ROLE=tx ANALYZE=1               add GCC's static analyzer to our own C (used by CI)
#
# The board code (Core/, startup/, SubGHz_Phy/Target/, linker script) and the common build rules
# live in ../board/nucleo-wl55jc (board.mk). This project keeps its own Core/Src/stm32wlxx_it.c
# (flash ECC NMI hook, HardFault record) and Core/Inc/utilities_def.h (sequencer tasks).
# Pinned inputs: tools/fetch-vendor.sh (STM32CubeWL v1.6.0 + submodules, Mbed TLS 3.6.6)
# and xPack arm-none-eabi-gcc 15.2.1-1.1.

ROLE      ?= tx
ROOT       = ../..
BOARD      = ../board/nucleo-wl55jc
# CUBE comes from board.mk (expanded when used).
MBEDTLS    = $(CUBE)/Middlewares/Third_Party/mbed-crypto
FW_VERSION:= $(shell git describe --always --dirty --abbrev=12 2>/dev/null || echo unknown)
# DIAG firmware build ID (docs/protocol.md): the first 8 hex digits of FW_VERSION, 0 if they are not
# 8 lowercase hex digits (e.g. "unknown" or a tag name).
FW_BUILD_ID := $(or $(shell printf '%s\n' '$(FW_VERSION)' | cut -c1-8 | grep -E '^[0-9a-f]{8}$$' | sed 's/^/0x/'),0)

ifeq ($(filter $(ROLE),tx rx),)
$(error ROLE must be tx or rx)
endif

BUILD      = build/$(ROLE)
TARGET     = $(BUILD)/stage0-$(ROLE)
# `make clean` removes both roles (build/), or only the BUILD given on the command line.
CLEAN_DIR  = $(patsubst %/$(ROLE),%,$(BUILD))
USAGE_ARGS = ROLE=$(ROLE)

IT_SRC  = Core/Src/stm32wlxx_it.c
APP_SRC = $(BOARD_CORE_SRC) $(BOARD_SYS_SRC) \
          $(BOARD_APP_SRC) App/radio_cfg.c App/console.c App/leds.c App/watchdog.c App/stackmon.c App/fault.c App/app_$(ROLE).c \
          $(ROOT)/firmware/common/ws_console.c \
          $(BOARD_RADIO_SRC)
ifeq ($(ROLE),tx)
APP_SRC += App/node_store.c App/flash_stm32wl.c App/sensor.c $(ROOT)/firmware/stage0.c $(ROOT)/firmware/common/ws_frame.c $(ROOT)/firmware/common/ws_obs.c
endif

HAL_EXTRA = i2c i2c_ex iwdg
ifeq ($(ROLE),tx)
CUBE_EXTRA = $(addprefix $(MBEDTLS)/library/,aes.c ccm.c block_cipher.c platform_util.c constant_time.c)
endif

PROJ_INCS  = App Core/Inc $(ROOT)/firmware $(ROOT)/firmware/common
EXTRA_INCS = $(MBEDTLS)/include

DEFS = -DWS_ROLE_$(ROLE) -DWS_FW_VERSION=\"$(FW_VERSION)\" -DWS_FW_BUILD_ID=$(FW_BUILD_ID)UL -DMBEDTLS_CONFIG_FILE=\"ws_mbedtls_config.h\"
OPT  = -Os
# GCC 15 turns the bitwise CRC loops (node_store.c crc16, stage0.c ws_crc8) into 768 B of lookup
# tables; they run a few times a minute, so keep them as loops (same values, tests/test_stage0.py).
$(BUILD)/app/node_store.o $(BUILD)/app/stage0.o: CFLAGS += -fno-optimize-crc

# Our own C (not ST-generated Core/, not vendor, not the board code) builds with board.mk's strict
# warning set and -Werror. ANALYZE=1 adds -fanalyzer (used by CI).
STRICT_SRC = $(filter App/%.c $(ROOT)/firmware/%.c,$(APP_SRC))

# Code-space budget (docs/firmware-budget.md): fail when code + initialized data exceed
# FLASH_BUDGET_PCT of the 64 KB application region (pages 0-31), well before the linker's hard
# limit, so growth is noticed while there is still room to plan.
FLASH_BUDGET_PCT ?= 90

include $(BOARD)/board.mk
