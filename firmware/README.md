# NUCLEO-WL55JC1 firmware groundwork

`stage0.c` and `stage0.h` provide portable SHT45 acquisition and packet serialization.
They compile with warnings-as-errors in the host tests. **No ARM target build,
flash image, board programming or radio transmission has been performed.**

## Existing hardware target

Two ST NUCLEO-WL55JC1 boards: sensor transmitter and powered USB receiver.
SHT45 PTFE breakout: Adafruit 6174, superseding the starter's older 5665 suggestion.
The supplied development boards, their antennas and USB data cables are the Stage-0
platform; custom boards and printed fixtures are not required to validate this link.

## Required target integration, in order

1. Pin a STM32CubeWL release **and exact Git commit/submodules**, the Arm GNU toolchain
   and ST programming tools. Use the vendor's matching NUCLEO-WL55JC single-core
   direct-radio example as the board/RF basis. No vendor revision is falsely marked
   pinned in this package; selection and an actual target build remain open.
2. Confirm actual board revision and sensor header mapping against UM2592 and generated
   GPIO/I2C configuration. The C callback contract uses a 7-bit I2C address (0x44);
   shift for STM32 HAL APIs that expect an 8-bit address. Use the breakout's short local
   I2C connection at 3.3 V. No guessed pin numbers are an assembly instruction.
3. Wire the I2C callbacks to bounded HAL reads/writes; run one high-precision heater-off
   measurement/minute. CRC or bus failure emits explicit invalid readings. Test unplug,
   stuck-bus recovery and restart before radio integration.
4. Add maintained-library AES-CCM with 16-byte tag and verify against a host-generated
   known-answer frame. Do not write custom AES. Implement wired key provisioning and
   durable unique transmission nonce state. The host allocator is not an MCU flash driver.
5. Implement a journal that survives planned power interruptions and retains observations
   until authenticated host ACK. Reserve a boot epoch before sampling. Agree the Stage-0
   outage/storage capacity and exact storage BOM before this integration; the final
   30-day/16 MB H11 target is not satisfied by this host simulation.
6. Implement the receiver's bounded hex serial framing and ACK return path, authenticated
   time sync, and RF receive windows. Keep current observations ahead of bounded backfill.
7. Validate RF region/channel, bandwidth/spreading factor, power, antenna configuration
   and airtime for the US configuration before transmitting. Do not equate arbitrary
   915 MHz settings with a qualified regional configuration.
8. Build both targets, record binary hashes, flash via ST-LINK, then run the H01 checklist.

## Current measurement preparation

UM2592 documents JP1/I_SoC and separate measurement arrangements involving JP2/I_RF,
JP5/I_SYS and associated bridges. Verify the board revision and manual before changing
jumpers/bridges. USB input power includes debugger/development-board overhead; it is
not a measurement of the final station's pack power. Record supply boundary and
jumper/debugger settings with traces. Normal USB power is appropriate for Stage 0.

References:
- https://github.com/STMicroelectronics/STM32CubeWL
- https://www.st.com/en/evaluation-tools/nucleo-wl55jc.html
- https://www.st.com/resource/en/user_manual/um2592-stm32wl-nucleo64-board-mb1389-stmicroelectronics.pdf
- https://sensirion.com/resource/datasheet/sht4x
- https://www.adafruit.com/product/6174
