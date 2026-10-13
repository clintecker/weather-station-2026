# Stage-0 NUCLEO-WL55JC1 firmware, two roles from one tree.
#
#   make ROLE=tx                         sensor node  -> build/tx/stage0-tx.{elf,bin}
#   make ROLE=rx                         USB receiver -> build/rx/stage0-rx.{elf,bin}
#   make ROLE=tx flash SERIAL=<stlink>   program one board (see docs/hardware for serials)
#
# Pinned inputs: tools/fetch-vendor.sh (STM32CubeWL v1.6.0 + submodules, Mbed TLS 3.6.6)
# and xPack arm-none-eabi-gcc 15.2.1-1.1.

ROLE      ?= tx
ROOT       = ../..
CUBE      ?= $(ROOT)/vendor/STM32CubeWL
TOOLCHAIN ?= $(HOME)/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin
PREFIX     = $(TOOLCHAIN)/arm-none-eabi-
CC         = $(PREFIX)gcc
OBJCOPY    = $(PREFIX)objcopy
SIZE       = $(PREFIX)size
MBEDTLS    = $(CUBE)/Middlewares/Third_Party/mbed-crypto
FW_VERSION:= $(shell git describe --always --dirty --abbrev=12 2>/dev/null || echo unknown)

ifeq ($(filter $(ROLE),tx rx),)
$(error ROLE must be tx or rx)
endif

BUILD  = build/$(ROLE)
TARGET = $(BUILD)/stage0-$(ROLE)

APP_SRC = $(wildcard Core/Src/*.c) startup/syscalls.c startup/sysmem.c \
          App/app_subghz_phy.c App/radio_cfg.c App/console.c App/leds.c App/watchdog.c App/app_$(ROLE).c \
          SubGHz_Phy/Target/radio_board_if.c
ifeq ($(ROLE),tx)
APP_SRC += App/node_store.c App/sensor.c $(ROOT)/firmware/stage0.c $(ROOT)/firmware/common/ws_frame.c
endif

HAL = $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Src/stm32wlxx_hal
CUBE_SRC = $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo_radio.c \
           $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo.c \
           $(HAL).c $(HAL)_cortex.c $(HAL)_dma.c $(HAL)_dma_ex.c $(HAL)_exti.c \
           $(HAL)_flash.c $(HAL)_flash_ex.c $(HAL)_gpio.c $(HAL)_pwr.c $(HAL)_pwr_ex.c \
           $(HAL)_rcc.c $(HAL)_rcc_ex.c $(HAL)_rtc.c $(HAL)_rtc_ex.c $(HAL)_subghz.c \
           $(HAL)_tim.c $(HAL)_tim_ex.c $(HAL)_uart.c $(HAL)_uart_ex.c \
           $(HAL)_i2c.c $(HAL)_i2c_ex.c $(HAL)_iwdg.c \
           $(wildcard $(CUBE)/Middlewares/Third_Party/SubGHz_Phy/radio_driver/*.c) \
           $(CUBE)/Utilities/lpm/tiny_lpm/stm32_lpm.c \
           $(CUBE)/Utilities/misc/stm32_mem.c \
           $(CUBE)/Utilities/misc/stm32_systime.c \
           $(CUBE)/Utilities/misc/stm32_tiny_sscanf.c \
           $(CUBE)/Utilities/misc/stm32_tiny_vsnprintf.c \
           $(CUBE)/Utilities/sequencer/stm32_seq.c \
           $(CUBE)/Utilities/timer/stm32_timer.c \
           $(CUBE)/Utilities/trace/adv_trace/stm32_adv_trace.c
ifeq ($(ROLE),tx)
CUBE_SRC += $(addprefix $(MBEDTLS)/library/,aes.c ccm.c cipher.c cipher_wrap.c platform_util.c constant_time.c)
endif

ASM_SRC = startup/startup_stm32wl55jcix.s

INCS = App Core/Inc SubGHz_Phy/Target $(ROOT)/firmware $(ROOT)/firmware/common \
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
       $(MBEDTLS)/include

DEFS = -DCORE_CM4 -DSTM32WL55xx -DUSE_HAL_DRIVER -DWS_ROLE_$(ROLE) \
       -DWS_FW_VERSION=\"$(FW_VERSION)\" -DMBEDTLS_CONFIG_FILE=\"ws_mbedtls_config.h\"

CPU     = -mcpu=cortex-m4 -mthumb -mfloat-abi=soft
CFLAGS  = $(CPU) $(DEFS) $(addprefix -I,$(INCS)) -std=gnu11 -Os -g3 -Wall \
          -ffunction-sections -fdata-sections -MMD -MP
LDFLAGS = $(CPU) -T STM32WL55JCIX_FLASH.ld --specs=nano.specs --specs=nosys.specs \
          -Wl,--gc-sections -Wl,-Map=$(TARGET).map -Wl,--no-warn-rwx-segments \
          -Wl,--start-group -lc -lm -Wl,--end-group

OBJS = $(addprefix $(BUILD)/app/,$(notdir $(APP_SRC:.c=.o))) \
       $(addprefix $(BUILD)/cube/,$(notdir $(CUBE_SRC:.c=.o))) \
       $(BUILD)/app/startup.o

vpath %.c $(sort $(dir $(APP_SRC) $(CUBE_SRC)))

all: $(TARGET).bin

$(BUILD)/app/%.o $(BUILD)/cube/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/app/startup.o: $(ASM_SRC)
	@mkdir -p $(dir $@)
	$(CC) $(CPU) -x assembler-with-cpp -c $< -o $@

# Code-space budget (docs/firmware-budget.md): fail when code + initialized data exceed
# FLASH_BUDGET_PCT of the 64 KB application region (pages 0-31), well before the linker's hard
# limit, so growth is noticed while there is still room to plan.
APP_FLASH_BYTES  ?= 65536
FLASH_BUDGET_PCT ?= 90

$(TARGET).elf: $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SIZE) $@
	@$(SIZE) $@ | awk -v lim=$(APP_FLASH_BYTES) -v pct=$(FLASH_BUDGET_PCT) 'NR==2 { used=$$1+$$2; \
	  printf "flash budget: %d of %d B (%.1f%%, limit %d%%)\n", used, lim, 100*used/lim, pct; \
	  if (used*100 > lim*pct) { print "error: over the flash budget, see docs/firmware-budget.md"; exit 1 } }'

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	shasum -a 256 $@

flash: $(TARGET).bin
	@test -n "$(SERIAL)" || (echo "usage: make ROLE=$(ROLE) flash SERIAL=<stlink serial>"; exit 1)
	openocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \
	  -c "reset_config srst_only srst_nogate connect_assert_srst" \
	  -c "program $(TARGET).elf verify reset exit"

clean:
	rm -rf build

-include $(OBJS:.o=.d)

.PHONY: all flash clean
