# Command-line build of ST's SubGHz_Phy_PingPong (STM32CubeWL v1.6.0) for NUCLEO-WL55JC1.
# Sources/defines/includes mirror STM32CubeIDE/.project + .cproject (Debug config).
#
#   make                      build build/pingpong.elf/.bin
#   make flash SERIAL=<stlink serial>

CUBE      ?= ../../vendor/STM32CubeWL
TOOLCHAIN ?= $(HOME)/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin
PREFIX     = $(TOOLCHAIN)/arm-none-eabi-
CC         = $(PREFIX)gcc
OBJCOPY    = $(PREFIX)objcopy
SIZE       = $(PREFIX)size

BUILD  = build
TARGET = $(BUILD)/pingpong

APP_SRC = $(wildcard Core/Src/*.c) \
          SubGHz_Phy/App/app_subghz_phy.c \
          SubGHz_Phy/App/subghz_phy_app.c \
          SubGHz_Phy/Target/radio_board_if.c \
          startup/syscalls.c startup/sysmem.c

HAL = $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Src/stm32wlxx_hal
CUBE_SRC = $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo_radio.c \
           $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo/stm32wlxx_nucleo.c \
           $(HAL).c $(HAL)_cortex.c $(HAL)_dma.c $(HAL)_dma_ex.c $(HAL)_exti.c \
           $(HAL)_flash.c $(HAL)_flash_ex.c $(HAL)_gpio.c $(HAL)_pwr.c $(HAL)_pwr_ex.c \
           $(HAL)_rcc.c $(HAL)_rcc_ex.c $(HAL)_rtc.c $(HAL)_rtc_ex.c $(HAL)_subghz.c \
           $(HAL)_tim.c $(HAL)_tim_ex.c $(HAL)_uart.c $(HAL)_uart_ex.c \
           $(wildcard $(CUBE)/Middlewares/Third_Party/SubGHz_Phy/radio_driver/*.c) \
           $(CUBE)/Utilities/lpm/tiny_lpm/stm32_lpm.c \
           $(CUBE)/Utilities/misc/stm32_mem.c \
           $(CUBE)/Utilities/misc/stm32_systime.c \
           $(CUBE)/Utilities/misc/stm32_tiny_sscanf.c \
           $(CUBE)/Utilities/misc/stm32_tiny_vsnprintf.c \
           $(CUBE)/Utilities/sequencer/stm32_seq.c \
           $(CUBE)/Utilities/timer/stm32_timer.c \
           $(CUBE)/Utilities/trace/adv_trace/stm32_adv_trace.c

ASM_SRC = startup/startup_stm32wl55jcix.s

INCS = Core/Inc SubGHz_Phy/App SubGHz_Phy/Target \
       $(CUBE)/Drivers/BSP/STM32WLxx_Nucleo \
       $(CUBE)/Drivers/CMSIS/Device/ST/STM32WLxx/Include \
       $(CUBE)/Drivers/CMSIS/Include \
       $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Inc \
       $(CUBE)/Drivers/STM32WLxx_HAL_Driver/Inc/Legacy \
       $(CUBE)/Middlewares/Third_Party/SubGHz_Phy \
       $(CUBE)/Middlewares/Third_Party/SubGHz_Phy/radio_driver \
       $(CUBE)/Utilities/lpm/tiny_lpm $(CUBE)/Utilities/misc \
       $(CUBE)/Utilities/sequencer $(CUBE)/Utilities/timer \
       $(CUBE)/Utilities/trace/adv_trace

DEFS = -DCORE_CM4 -DDEBUG -DSTM32WL55xx -DUSE_HAL_DRIVER

CPU     = -mcpu=cortex-m4 -mthumb -mfloat-abi=soft
CFLAGS  = $(CPU) $(DEFS) $(addprefix -I,$(INCS)) -std=gnu11 -Og -g3 -Wall \
          -ffunction-sections -fdata-sections -MMD -MP
LDFLAGS = $(CPU) -T STM32WL55JCIX_FLASH.ld --specs=nano.specs --specs=nosys.specs \
          -Wl,--gc-sections -Wl,-Map=$(TARGET).map -Wl,--no-warn-rwx-segments \
          -Wl,--start-group -lc -lm -Wl,--end-group

OBJS = $(addprefix $(BUILD)/app/,$(APP_SRC:.c=.o)) \
       $(addprefix $(BUILD)/cube/,$(notdir $(CUBE_SRC:.c=.o))) \
       $(BUILD)/app/startup.o

vpath %.c $(sort $(dir $(CUBE_SRC)))

all: $(TARGET).bin

$(BUILD)/app/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/cube/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/app/startup.o: $(ASM_SRC)
	@mkdir -p $(dir $@)
	$(CC) $(CPU) -x assembler-with-cpp -c $< -o $@

$(TARGET).elf: $(OBJS)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	$(SIZE) $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

flash: $(TARGET).bin
	@test -n "$(SERIAL)" || (echo "usage: make flash SERIAL=<stlink serial>"; exit 1)
	openocd -f interface/stlink.cfg -c "adapter serial $(SERIAL)" -f target/stm32wlx.cfg \
	  -c "reset_config srst_only srst_nogate connect_assert_srst" \
	  -c "program $(TARGET).elf verify reset exit"

clean:
	rm -rf $(BUILD)

-include $(OBJS:.o=.d)

.PHONY: all flash clean
