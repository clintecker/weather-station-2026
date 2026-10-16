# Common build for every NUCLEO-WL55JC1 project (stage0-node, rangetest).
#
# The board directory holds the ST CubeMX/CubeIDE template code all projects share: Core/ (HAL init,
# UART, RTC, low power), startup/, SubGHz_Phy/Target/ and the linker script (64 KB application
# region: pages 55..127 hold the node key and journal, see firmware/stage0-node/App/flash_layout.h).
#
# A project Makefile sets these, then includes this file last:
#   BOARD      path to this directory (../board/nucleo-wl55jc)
#   TARGET     output path without extension (e.g. $(BUILD)/rangetest)
#   BUILD      build directory; every object lands in $(BUILD)/app or $(BUILD)/cube
#   APP_SRC    the project's C sources in link order; use $(BOARD_CORE_SRC), $(BOARD_SYS_SRC) and
#              $(BOARD_RADIO_SRC) for the shared ones
#   IT_SRC     optional: the project's own stm32wlxx_it.c in place of the board's stock one
#   HAL_EXTRA  optional: extra HAL modules (e.g. i2c iwdg), compiled after the common ones
#   CUBE_EXTRA optional: further vendor sources, linked after the common ones
#   PROJ_INCS  the project's include directories (searched before the board's)
#   EXTRA_INCS optional: include directories searched after the vendor ones
#   DEFS       the project's -D flags (VERBOSE_LEVEL / LOW_POWER_DISABLE override Core/Inc/sys_conf.h)
#   OPT        optimisation level (-Os, -Og)
#   STRICT_SRC optional: sources built with the strict warning set and -Werror (ANALYZE=1 adds
#              -fanalyzer); ST-generated and vendor code is never in it
#   FLASH_BUDGET_PCT optional: fail the link when code + data exceed this % of APP_FLASH_BYTES
#   NO_HEAP    optional: 1 fails the link if the heap allocator (malloc, free, ... or _sbrk) is linked in
#   CLEAN_DIR  optional: what `make clean` removes (default $(BUILD))
#   USAGE_ARGS optional: extra arguments shown in the `make flash` usage line
#
# Pinned inputs: tools/fetch-vendor.sh (STM32CubeWL v1.6.0 + submodules, Mbed TLS 3.6.6)
# and xPack arm-none-eabi-gcc 15.2.1-1.1.

ROOT      ?= ../..
CUBE      ?= $(ROOT)/vendor/STM32CubeWL
TOOLCHAIN ?= $(HOME)/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin
PREFIX     = $(TOOLCHAIN)/arm-none-eabi-
CC         = $(PREFIX)gcc
OBJCOPY    = $(PREFIX)objcopy
NM         = $(PREFIX)nm
SIZE       = $(PREFIX)size
CLEAN_DIR ?= $(BUILD)

.DEFAULT_GOAL := all

# Shared sources. Core/Src keeps the glob order the projects have always linked in; a project's own
# stm32wlxx_it.c takes the stock one's place in that order.
IT_SRC         ?= $(BOARD)/Core/Src/stm32wlxx_it.c
BOARD_CORE_SRC  = $(patsubst $(BOARD)/Core/Src/stm32wlxx_it.c,$(IT_SRC),$(wildcard $(BOARD)/Core/Src/*.c))
BOARD_SYS_SRC   = $(BOARD)/startup/syscalls.c $(BOARD)/startup/sysmem.c
BOARD_RADIO_SRC = $(BOARD)/SubGHz_Phy/Target/radio_board_if.c
# MX_SubGHz_Phy_Init/Process, which hand over to the project's SubGHz app.
BOARD_APP_SRC   = $(BOARD)/SubGHz_Phy/App/app_subghz_phy.c
ASM_SRC         = $(BOARD)/startup/startup_stm32wl55jcix.s

HAL = $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Src/stm32wlxx_hal
CUBE_SRC = $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo_radio.c \
           $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo.c \
           $(HAL).c $(HAL)_cortex.c $(HAL)_dma.c $(HAL)_dma_ex.c $(HAL)_exti.c \
           $(HAL)_flash.c $(HAL)_flash_ex.c $(HAL)_gpio.c $(HAL)_pwr.c $(HAL)_pwr_ex.c \
           $(HAL)_rcc.c $(HAL)_rcc_ex.c $(HAL)_rtc.c $(HAL)_rtc_ex.c $(HAL)_subghz.c \
           $(HAL)_tim.c $(HAL)_tim_ex.c $(HAL)_uart.c $(HAL)_uart_ex.c \
           $(addprefix $(HAL)_,$(addsuffix .c,$(HAL_EXTRA))) \
           $(wildcard $(CUBE)/Middlewares/Third_Party/SubGHz_Phy/radio_driver/*.c) \
           $(CUBE)/Utilities/lpm/tiny_lpm/stm32_lpm.c \
           $(CUBE)/Utilities/misc/stm32_mem.c \
           $(CUBE)/Utilities/misc/stm32_systime.c \
           $(CUBE)/Utilities/misc/stm32_tiny_sscanf.c \
           $(CUBE)/Utilities/misc/stm32_tiny_vsnprintf.c \
           $(CUBE)/Utilities/sequencer/stm32_seq.c \
           $(CUBE)/Utilities/timer/stm32_timer.c \
           $(CUBE)/Utilities/trace/adv_trace/stm32_adv_trace.c \
           $(CUBE_EXTRA)

INCS = $(PROJ_INCS) $(BOARD)/Core/Inc $(BOARD)/SubGHz_Phy/App $(BOARD)/SubGHz_Phy/Target \
       $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo \
       $(CUBE)/Drivers/CMSIS/Device/ST/STM32WLxx/Include \
       $(CUBE)/Drivers/CMSIS/Include \
       $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Inc \
       $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Inc/Legacy \
       $(CUBE)/Middlewares/Third_Party/SubGHz_Phy \
       $(CUBE)/Middlewares/Third_Party/SubGHz_Phy/radio_driver \
       $(CUBE)/Utilities/lpm/tiny_lpm $(CUBE)/Utilities/misc \
       $(CUBE)/Utilities/sequencer $(CUBE)/Utilities/timer \
       $(CUBE)/Utilities/trace/adv_trace \
       $(EXTRA_INCS)

CPU     = -mcpu=cortex-m4 -mthumb -mfloat-abi=soft
CFLAGS  = $(CPU) -DCORE_CM4 -DSTM32WL55xx -DUSE_HAL_DRIVER $(DEFS) $(addprefix -I,$(INCS)) \
          -std=gnu11 $(OPT) -g3 -Wall -ffunction-sections -fdata-sections -MMD -MP -fcallgraph-info=su
LDFLAGS = $(CPU) -T $(BOARD)/STM32WL55JCIX_FLASH.ld --specs=nano.specs --specs=nosys.specs \
          -Wl,--gc-sections -Wl,-Map=$(TARGET).map -Wl,--no-warn-rwx-segments \
          -Wl,--start-group -lc -lm -Wl,--end-group

# Objects are flat per kind: $(BUILD)/app/<name>.o for project and board sources,
# $(BUILD)/cube/<name>.o for vendor sources. Basenames must therefore be unique within each kind.
APP_OBJS  = $(addprefix $(BUILD)/app/,$(notdir $(APP_SRC:.c=.o)))
CUBE_OBJS = $(addprefix $(BUILD)/cube/,$(notdir $(CUBE_SRC:.c=.o)))
OBJS      = $(APP_OBJS) $(CUBE_OBJS) $(BUILD)/app/startup.o

ifneq ($(words $(sort $(notdir $(APP_SRC)) startup.c)),$(words $(APP_SRC) startup.c))
$(error duplicate source basenames in APP_SRC: $(APP_SRC))
endif
ifneq ($(words $(sort $(notdir $(CUBE_SRC)))),$(words $(CUBE_SRC)))
$(error duplicate source basenames in CUBE_SRC)
endif

# Strict warnings for our own C. These flags do not change the generated code. The second and third
# lines came with docs/power-of-ten.md (rule 10): ISO C (-Wpedantic, on top of gnu11's extensions), the
# console formats (sys_app.h gives APP_PRINTF a format check), declarations, and no function frame
# above 512 B (-Wstack-usage; tools/stack_report.py bounds whole call chains).
STRICT = -Wextra -Wshadow -Wconversion -Wsign-conversion -Wcast-qual -Wstrict-prototypes \
         -Wmissing-prototypes -Wundef -Wdouble-promotion -Wformat=2 -Wnull-dereference \
         -Wpedantic -Wformat-signedness -Wformat-overflow=2 -Wformat-truncation=2 -Wvla -Walloca -Wcast-align \
         -Wpointer-arith -Wredundant-decls -Wold-style-definition -Wmissing-declarations -Wwrite-strings \
         -Wjump-misses-init -Wlogical-op -Wduplicated-cond -Wduplicated-branches -Wswitch-default \
         -Wfloat-equal -Wunused-macros -Wstack-usage=512 -Werror
ifeq ($(ANALYZE),1)
STRICT += -fanalyzer
endif
STRICT_OBJS = $(addprefix $(BUILD)/app/,$(notdir $(STRICT_SRC:.c=.o)))
$(STRICT_OBJS): CFLAGS += $(STRICT)

all: $(TARGET).bin

# -MMD tracks headers, not flags: rewrite flags.txt when the compile flags change (a new
# FW_VERSION after a commit, a different DEFS) so every object rebuilds, and relink when the
# linker script or a makefile changes. Otherwise `make` without `clean` kept an old version string.
FLAGS_FILE := $(BUILD)/flags.txt
ifeq ($(filter clean,$(MAKECMDGOALS)),)
$(shell mkdir -p $(BUILD) && printf '%s\n' '$(CFLAGS) $(LDFLAGS)' | cmp -s - $(FLAGS_FILE) || printf '%s\n' '$(CFLAGS) $(LDFLAGS)' > $(FLAGS_FILE))
endif
$(OBJS): $(FLAGS_FILE)

# One explicit rule per source (no vpath), so a project file can never be shadowed by a board or
# vendor file of the same name.
define BOARD_COMPILE_RULE
$(1): $(2)
	@mkdir -p $$(dir $$@)
	$$(CC) $$(CFLAGS) -c $$< -o $$@
endef
$(foreach s,$(APP_SRC),$(eval $(call BOARD_COMPILE_RULE,$(BUILD)/app/$(notdir $(s:.c=.o)),$(s))))
$(foreach s,$(CUBE_SRC),$(eval $(call BOARD_COMPILE_RULE,$(BUILD)/cube/$(notdir $(s:.c=.o)),$(s))))

$(BUILD)/app/startup.o: $(ASM_SRC)
	@mkdir -p $(dir $@)
	$(CC) $(CPU) -x assembler-with-cpp -c $< -o $@

APP_FLASH_BYTES ?= 112640

$(TARGET).elf: $(OBJS) $(BOARD)/STM32WL55JCIX_FLASH.ld $(MAKEFILE_LIST)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SIZE) $@
ifneq ($(FLASH_BUDGET_PCT),)
	@$(SIZE) $@ | awk -v lim=$(APP_FLASH_BYTES) -v pct=$(FLASH_BUDGET_PCT) 'NR==2 { used=$$1+$$2; \
	  printf "flash budget: %d of %d B (%.1f%%, limit %d%%)\n", used, lim, 100*used/lim, pct; \
	  if (used*100 > lim*pct) { print "error: over the flash budget, see docs/firmware-budget.md"; exit 1 } }'
endif
ifeq ($(NO_HEAP),1)
	@$(NM) $@ > $@.nm && ! grep -E ' [TtWw] (_?(malloc|calloc|realloc|free)|_(malloc|calloc|realloc|free)_r|_sbrk)$$' $@.nm \
	  || { rm -f $@.nm; echo "error: the heap allocator is linked in, or nm failed (docs/power-of-ten.md, rule 3)"; exit 1; }
	@rm -f $@.nm
	@echo "no heap: no allocator linked"
endif

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	shasum -a 256 $@

flash: $(TARGET).bin
	@test -n "$(SERIAL)" || (echo "usage: make $(strip $(USAGE_ARGS) flash) SERIAL=<stlink serial>"; exit 1)
	openocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \
	  -c "reset_config srst_only srst_nogate connect_assert_srst" \
	  -c "program $(TARGET).elf verify reset exit"

# Worst-case stack bound from the GCC call graphs (-fcallgraph-info=su); fails if it exceeds the
# stack the linker reserves (_Min_Stack_Size). See tools/stack_report.py and docs/firmware-budget.md.
stack: $(TARGET).elf
	python3 $(ROOT)/tools/stack_report.py $(BUILD) --toolchain $(TOOLCHAIN)

# No busy-wait or blocking call reachable at run time (interrupts, tasks, callbacks, main loop); boot
# and TEST_ONLY waits are listed. See tools/blocking_report.py and docs/firmware-budget.md.
waits: $(TARGET).elf
	python3 $(ROOT)/tools/blocking_report.py $(BUILD) --toolchain $(TOOLCHAIN)

clean:
	rm -rf $(CLEAN_DIR)

-include $(OBJS:.o=.d)

# A failed check after the link (flash budget, no heap) must not leave an .elf the next make trusts.
.DELETE_ON_ERROR:

.PHONY: all flash clean stack waits
