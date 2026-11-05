# Bench prototype firmware for the NUCLEO-WL55JC1, two roles from one tree.
#
#   make ROLE=tx                         sensor node  -> build/tx/stage0-tx.{elf,bin}
#   make ROLE=rx                         USB receiver -> build/rx/stage0-rx.{elf,bin}
#   make ROLE=tx flash SERIAL=<stlink>   program one board (see docs/hardware for serials)
#   make ROLE=tx stack                   worst-case stack bound vs the linker's reservation
#   make ROLE=tx ANALYZE=1               add GCC's static analyzer to our own C (used by CI)
#   make ROLE=tx WS_BENCH_OLED=1         the bench build with the OLED -> build/tx-oled/stage0-tx.{elf,bin}
#   make ROLE=tx WS_POWER_PROFILE=2      a power telemetry profile (App/power_config.h; default: its own)
#   make field-check                     build ROLE=tx without the OLED (build/tx-fieldcheck); fail if any display
#                                        code is linked
# WS_BENCH_OLED and WS_POWER_PROFILE are not remembered: pass them to `flash` as to the build (the flash usage
# line and the budget line name them).
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
# Firmware build ID in the health report, DIAG (docs/protocol.md): the first 8 hex digits of
# FW_VERSION, or 0 ("not identified") if they are not 8 lowercase hex digits (e.g. "unknown" or a
# tag name) or the tree is dirty: a build with uncommitted changes (a measured constant edited into
# App/power_config.h, say) must not report the ID of the commit it differs from (power spec 8.6).
FW_BUILD_ID := $(or $(shell printf '%s\n' '$(FW_VERSION)' | grep -v -e '-dirty$$' | cut -c1-8 | grep -E '^[0-9a-f]{8}$$' | sed 's/^/0x/'),0)

ifeq ($(filter $(ROLE),tx rx),)
$(error ROLE must be tx or rx)
endif

# The bench OLED (App/oled_dma.h; docs/superpowers/specs/2026-11-04-node-oled-and-e2e-design.md):
# WS_BENCH_OLED=1 builds the display into the TX, 0 (the field build, the default) leaves it out with
# its pins. The bench build has its own directory, so neither build ever links the other's objects
# (flags.txt in board.mk would rebuild them all anyway when the flags differ).
WS_BENCH_OLED ?= 0
ifeq ($(filter $(WS_BENCH_OLED),0 1),)
$(error WS_BENCH_OLED must be 0 or 1)
endif
ifeq ($(ROLE)$(WS_BENCH_OLED),rx1)
$(error WS_BENCH_OLED=1 is for ROLE=tx: the receiver has no display)
endif
OLED_SUFFIX = $(if $(filter 1,$(WS_BENCH_OLED)),-oled)
# The power telemetry profile (App/power_config.h): empty keeps the header's default.
WS_POWER_PROFILE ?=

BUILD      = build/$(ROLE)$(OLED_SUFFIX)
TARGET     = $(BUILD)/stage0-$(ROLE)
# `make clean` removes both roles (build/), or only the BUILD given on the command line.
CLEAN_DIR  = $(patsubst %/$(ROLE)$(OLED_SUFFIX),%,$(BUILD))
# What the flash usage line and the budget line name: the role and the flags that change the image.
USAGE_ARGS = ROLE=$(ROLE) $(if $(filter 1,$(WS_BENCH_OLED)),WS_BENCH_OLED=1) $(if $(WS_POWER_PROFILE),WS_POWER_PROFILE=$(WS_POWER_PROFILE))
BUDGET_LABEL = $(ROLE)$(if $(WS_POWER_PROFILE),$(comma) profile $(WS_POWER_PROFILE))$(if $(filter 1,$(WS_BENCH_OLED)),$(comma) bench OLED)
comma := ,

IT_SRC  = Core/Src/stm32wlxx_it.c
APP_SRC = $(BOARD_CORE_SRC) $(BOARD_SYS_SRC) \
          $(BOARD_APP_SRC) App/radio_cfg.c App/console.c App/leds.c App/watchdog.c App/stackmon.c App/busymon.c App/fault.c App/clock.c App/events.c App/bench.c App/app_$(ROLE).c \
          $(ROOT)/firmware/common/ws_console.c $(ROOT)/firmware/common/ws_check.c \
          $(BOARD_RADIO_SRC)
ifeq ($(ROLE),tx)
APP_SRC += App/tx_exchange.c App/tx_policy.c App/tx_time.c App/tx_console.c App/selftest.c \
           App/node_store.c App/flash_stm32wl.c App/i2c_bus.c App/board_inputs.c App/wsmp_local.c App/port_id.c App/wsmp_host.c \
           App/wsmp_catalog_map.c App/mod_th.c App/mod_mean.c App/mod_reg.c App/mod_power.c App/power_acq.c App/mod_wind.c \
           App/mod_rain.c $(ROOT)/firmware/common/power_regs.c $(ROOT)/firmware/common/wsmp.c $(ROOT)/firmware/common/wsmp_cal.c \
           $(ROOT)/firmware/common/wsmp_ident.c $(ROOT)/firmware/stage0.c \
           $(ROOT)/firmware/common/ws_frame.c $(ROOT)/firmware/common/ws_obs.c $(ROOT)/firmware/common/ws_policy.c
endif
# The display: the driver, its application (the step, the view, the scheduler), the screens, then the
# shared frame buffer, drawing and font (firmware/common).
ifeq ($(WS_BENCH_OLED),1)
APP_SRC += App/oled_dma.c App/oled_app.c App/oled_view.c App/scr_sched.c App/scr_view.c App/scr_calc.c App/scr_home.c \
           App/scr_detail.c App/scr_interludes.c App/scr_rain.c App/scr_silly.c App/scr_art.c App/scr_font.c App/scr_kana.c \
           $(ROOT)/firmware/common/oled_fb.c $(ROOT)/firmware/common/oled_draw.c $(ROOT)/firmware/common/font5x7.c
endif

HAL_EXTRA = i2c i2c_ex iwdg adc adc_ex lptim
ifeq ($(ROLE),tx)
CUBE_EXTRA = $(addprefix $(MBEDTLS)/library/,aes.c ccm.c block_cipher.c platform_util.c constant_time.c)
endif

PROJ_INCS  = App Core/Inc $(ROOT)/firmware $(ROOT)/firmware/common
EXTRA_INCS = $(MBEDTLS)/include

DEFS = -DWS_ROLE_$(ROLE) -DWS_FW_VERSION=\"$(FW_VERSION)\" -DWS_FW_BUILD_ID=$(FW_BUILD_ID)UL -DMBEDTLS_CONFIG_FILE=\"ws_mbedtls_config.h\"
ifeq ($(WS_BENCH_OLED),1)
DEFS += -DWS_BENCH_OLED=1
endif
ifneq ($(WS_POWER_PROFILE),)
DEFS += -DWS_POWER_PROFILE=$(WS_POWER_PROFILE)
endif
OPT  = -Os
# GCC 15 turns the bitwise CRC loops (node_store.c crc16, stage0.c ws_crc8) into 768 B of lookup
# tables; they run a few times a minute, so keep them as loops (same values, tests/test_stage0.py).
$(BUILD)/app/node_store.o $(BUILD)/app/stage0.o: CFLAGS += -fno-optimize-crc

# Our own C (not ST-generated Core/, not vendor, not the board code) builds with board.mk's strict
# warning set and -Werror. ANALYZE=1 adds -fanalyzer (used by CI).
STRICT_SRC = $(filter App/%.c $(ROOT)/firmware/%.c,$(APP_SRC))

# Code-space budget (docs/firmware-budget.md): fail when code + initialized data exceed
# FLASH_BUDGET_PCT of the 190 KB application region (pages 0-94), well before the linker's hard
# limit, so growth is noticed while there is still room to plan.
FLASH_BUDGET_PCT ?= 90
# No dynamic allocation (docs/power-of-ten.md, rule 3): the link fails if malloc & co. are linked in.
NO_HEAP = 1

include $(BOARD)/board.mk

# The field build links no display code (design, "Field builds"): build ROLE=tx with WS_BENCH_OLED=0
# (and the default power profile) in its own directory, so it never replaces a build in build/tx, and
# fail on any symbol of the driver, the screens or the display library.
FIELD_CHECK = build/tx-fieldcheck
field-check:
	$(MAKE) ROLE=tx WS_BENCH_OLED=0 WS_POWER_PROFILE= BUILD=$(FIELD_CHECK)
	@$(NM) $(FIELD_CHECK)/stage0-tx.elf > $(FIELD_CHECK)/field-check.nm || { echo "error: nm failed"; exit 1; }
	@if grep -E ' [A-Za-z] (oled_|scr_|ssd1325_|font5x7)' $(FIELD_CHECK)/field-check.nm; then \
	  rm -f $(FIELD_CHECK)/field-check.nm; echo "error: the field build links display code (WS_BENCH_OLED=0)"; exit 1; fi
	@rm -f $(FIELD_CHECK)/field-check.nm
	@echo "field build: no display symbols"

.PHONY: field-check
