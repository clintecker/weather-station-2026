"""Run-time blocking check from GCC call graphs (-fcallgraph-info=su): no busy-waits at run time.

    python3 tools/blocking_report.py firmware/stage0-node/build/tx [--toolchain DIR]

The firmware must be interrupt/event driven: after boot, nothing may busy-wait or block for
milliseconds. This reads the same *.ci call graphs and address-taken analysis as stack_report.py and
checks every function a run-time root can reach against the wait-primitive tables below.

Run-time roots (everything that can run after boot):
- every interrupt handler (*_IRQHandler, *_Handler; Reset_Handler is boot);
- every linked address-taken function (sequencer tasks, timer callbacks, radio callbacks, driver
  tables, the console line handler): a call through a pointer can reach any of them, so all are
  roots (the same conservative rule as stack_report.py), except a function whose address is taken
  only in a constant driver table (DRIVER_TABLES, e.g. the SubGHz_Phy `Radio` struct) and whose
  slot no compiled source mentions;
- the body of main()'s forever loop (MAIN_LOOP).
Boot code is what main reaches by direct calls and no run-time root reaches: waits there are
allowed and listed as boot waits.

Wait primitives (tables below, each entry with its reason and source):
- BANNED: ms-scale or unbounded waits. Reachable at run time (outside TEST_ONLY): FAIL.
- ALLOWED: hardware stalls/handshakes with a stated worst-case bound. Reported, not a failure.
- CLOCKS: the time sources a timeout or delay loop polls. Every run-time function that calls one
  directly must be classified (BANNED, ALLOWED or TIMESTAMP); an unclassified one FAILS. This is
  how a new hidden wait (a new HAL timeout loop, a hand-written delay) is caught.
- TEST_ONLY: deliberate hang/crash bench commands. Waits reachable only through them are reported
  as test-only, not failures.
Traversal stops at a BANNED function (its internals are its own business) and continues through
ALLOWED and TIMESTAMP ones (a banned call inside an allowed one is still found).

Limits: only calls are visible. A register-poll loop written inline (`while (!(REG & FLAG));`)
calls nothing and is not seen, nor is a counter-bounded loop in a static function GCC inlined into
its caller; the ALLOWED table therefore names the public functions that contain such loops, and new
inline polls must be found in review. Prebuilt library code (newlib, libgcc) has no call graph and
is assumed not to wait.

Exit status 1 if a BANNED function is reachable at run time outside TEST_ONLY paths, or an
unclassified clock caller is reachable at run time.
"""
import argparse
import re
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_report  # noqa: E402  (tools/ is scripts, not a package)

DEFAULT_TOOLCHAIN = stack_report.DEFAULT_TOOLCHAIN
INDIRECT = stack_report.INDIRECT

HAL = 'vendor/STM32CubeWL/Drivers/STM32WLxx_HAL_Driver/Src'
BOARD = 'firmware/board/nucleo-wl55jc'
RADIO = 'vendor/STM32CubeWL/Middlewares/Third_Party/SubGHz_Phy/radio_driver'

# Keys are function names, or 'file.c:name' for a static function (matched on the file's basename).
# GCC clones (name.isra.0, name.constprop.0, name.part.0) match their base name.

# Time sources a wait loop polls. Their direct callers must be classified.
CLOCKS = {
    'HAL_GetTick': f'HAL timeout/delay clock; {BOARD}/Core/Src/sys_app.c reads it from the RTC '
                   '(TIMER_IF_GetTimerValue) once the timer server runs, 0 before that.',
    'UTIL_TIMER_GetCurrentTime': 'timer-server clock (TimerGetCurrentTime in SubGHz_Phy).',
    'UTIL_TIMER_GetElapsedTime': 'timer-server elapsed time (TimerGetElapsedTime in SubGHz_Phy).',
}

# Ms-scale or unbounded waits: never at run time.
BANNED = {
    'HAL_Delay': f'{BOARD}/Core/Src/sys_app.c: TIMER_IF_DelayMs(Delay), a busy-wait of Delay ms.',
    'TIMER_IF_DelayMs': f'{BOARD}/Core/Src/timer_if.c: spins on the RTC sub-second counter '
                        'until delay ms have passed.',
    'HAL_I2C_Master_Transmit': f'{HAL}/stm32wlxx_hal_i2c.c: polls TXIS/STOPF per byte, each with a '
                               'caller timeout in ms on HAL_GetTick; a whole transfer at 100 kHz is ~0.1 ms/byte '
                               'and a stretched or stuck bus waits the full timeout.',
    'HAL_I2C_Master_Receive': f'{HAL}/stm32wlxx_hal_i2c.c: polls RXNE/STOPF per byte (as Transmit).',
    'HAL_I2C_Mem_Write': f'{HAL}/stm32wlxx_hal_i2c.c: blocking polled transfer (as Master_Transmit).',
    'HAL_I2C_Mem_Read': f'{HAL}/stm32wlxx_hal_i2c.c: blocking polled transfer (as Master_Receive).',
    'HAL_I2C_IsDeviceReady': f'{HAL}/stm32wlxx_hal_i2c.c: up to Trials polled address cycles, each '
                             'waiting up to the caller timeout (ms) for ACK/NACK and STOPF.',
    'HAL_I2C_Slave_Transmit': f'{HAL}/stm32wlxx_hal_i2c.c: waits for a master for up to the timeout.',
    'HAL_I2C_Slave_Receive': f'{HAL}/stm32wlxx_hal_i2c.c: waits for a master for up to the timeout.',
    'HAL_UART_Transmit': f'{HAL}/stm32wlxx_hal_uart.c: polls TXE per byte; 87 us/byte at 115200 baud, '
                         'so a console line blocks for ms.',
    'HAL_UART_Receive': f'{HAL}/stm32wlxx_hal_uart.c: waits for host input up to the timeout.',
    'HAL_UARTEx_ReceiveToIdle': f'{HAL}/stm32wlxx_hal_uart_ex.c: waits for host input up to the timeout.',
    'vcom_Trace': f'{BOARD}/Core/Src/usart_if.c: HAL_UART_Transmit(..., 1000), a blocking console write '
                  '(the DMA path vcom_Trace_DMA is the run-time one).',
    'HAL_SPI_Transmit': f'{HAL}/stm32wlxx_hal_spi.c: polled transfer with a ms timeout.',
    'HAL_SPI_Receive': f'{HAL}/stm32wlxx_hal_spi.c: polled transfer with a ms timeout.',
    'HAL_SPI_TransmitReceive': f'{HAL}/stm32wlxx_hal_spi.c: polled transfer with a ms timeout.',
    'HAL_DMA_PollForTransfer': f'{HAL}/stm32wlxx_hal_dma.c: polls a DMA transfer to completion.',
    'HAL_ADC_PollForConversion': f'{HAL}/stm32wlxx_hal_adc.c: polls a conversion with a ms timeout.',
    'HAL_RTC_PollForAlarmAEvent': f'{HAL}/stm32wlxx_hal_rtc.c: waits for the alarm itself (seconds+).',
    'HAL_RTCEx_PollForAlarmBEvent': f'{HAL}/stm32wlxx_hal_rtc_ex.c: waits for the alarm itself.',
    'HAL_RTCEx_PollForWakeUpTimerEvent': f'{HAL}/stm32wlxx_hal_rtc_ex.c: waits for the wake-up timer.',
    'HAL_RTCEx_PollForTimeStampEvent': f'{HAL}/stm32wlxx_hal_rtc_ex.c: waits for an external event.',
    'HAL_RTCEx_PollForTamperEvent': f'{HAL}/stm32wlxx_hal_rtc_ex.c: waits for an external event.',
    'UTIL_SEQ_WaitEvt': 'Utilities/sequencer/stm32_seq.c: blocks the calling task until an event '
                        'arrives (nests the sequencer).',
    'RadioIsChannelFree': f'{RADIO}/radio.c: HAL_Delay(wake-up time) then spins on RSSI for '
                          'maxCarrierSenseTime ms.',
    'RFW_PollRxBytes': f'{RADIO}/radio_fw.c: spins on the RX buffer pointer for bytes*8 bit times '
                       '(UTIL_TIMER clock), ms at FSK rates.',
}

# Hardware stalls/handshakes allowed at run time: (worst-case bound, why and source).
ALLOWED = {
    # Flash (single bank: the CPU stalls on flash fetches while it programs/erases anyway).
    'FLASH_WaitForLastOperation': (
        'page erase 22.0 ms typ / 24.5 ms max; 64-bit program ~82-91 us (DS13293 flash memory '
        'characteristics, tERASE/tPROG); HAL timeout 1 s (FLASH_TIMEOUT_VALUE)',
        f'{HAL}/stm32wlxx_hal_flash.c: polls FLASH_SR.BSY on HAL_GetTick. Code runs from the same '
        'flash bank, so the core stalls on fetches for the operation whether it polls or not.'),
    'HAL_FLASH_Program': (
        '2 x FLASH_WaitForLastOperation; one 64-bit program ~91 us max (DS13293)',
        f'{HAL}/stm32wlxx_hal_flash.c: waits before and after the double-word write.'),
    'HAL_FLASHEx_Erase': (
        '24.5 ms max per 2 KB page (DS13293 tERASE); callers erase one page at a time',
        f'{HAL}/stm32wlxx_hal_flash_ex.c: FLASH_WaitForLastOperation per page.'),
    # SUBGHZ radio: BUSY-line and SPI byte handshakes, counter-bounded loops (no HAL_GetTick).
    'SUBGHZ_WaitOnBusy': (
        'radio BUSY: tens of us per command, up to ~3.5 ms on wake-up from sleep with calibration '
        '(RM0461 sub-GHz radio BUSY timing); hard cap: loop counter 100 * (SystemCoreClock*24>>20) '
        '= 109,863 iterations at 48 MHz, ST-sized to ~100 ms',
        f'{HAL}/stm32wlxx_hal_subghz.c: polls PWR_SR2.RFBUSYS, counter-bounded.'),
    'SUBGHZ_CheckDeviceReady': (
        'as SUBGHZ_WaitOnBusy (NSS pulse to wake the radio, then the BUSY wait)',
        f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'SUBGHZSPI_Transmit': (
        'one SPI byte: 8 bits at 48 MHz/4 = 0.67 us; cap: loop counter 100 * (SystemCoreClock*28>>19) '
        '= 256,347 iterations, ~100 ms',
        f'{HAL}/stm32wlxx_hal_subghz.c: polls SPI TXE then RXNE, counter-bounded.'),
    'SUBGHZSPI_Receive': (
        'as SUBGHZSPI_Transmit (one byte, 0.67 us)', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_ExecSetCmd': (
        'BUSY wait + n SPI bytes (<= 0.67 us each) + BUSY wait; see SUBGHZ_WaitOnBusy',
        f'{HAL}/stm32wlxx_hal_subghz.c (listed because the static waits may be inlined).'),
    'HAL_SUBGHZ_ExecGetCmd': ('as HAL_SUBGHZ_ExecSetCmd', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_WriteRegisters': ('as HAL_SUBGHZ_ExecSetCmd', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_ReadRegisters': ('as HAL_SUBGHZ_ExecSetCmd', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_WriteBuffer': ('as HAL_SUBGHZ_ExecSetCmd (<= 255 bytes: 170 us)', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_ReadBuffer': ('as HAL_SUBGHZ_ExecSetCmd (<= 255 bytes: 170 us)', f'{HAL}/stm32wlxx_hal_subghz.c.'),
    'HAL_SUBGHZ_Init': (
        'RF reset release: loop counter 100 * (SystemCoreClock*28>>19), ~100 ms cap; the reset '
        'itself takes a few radio clock cycles',
        f'{HAL}/stm32wlxx_hal_subghz.c: polls RCC_CSR.RFRSTF, counter-bounded.'),
    # RTC sub-second double read (GetTimerTicks, static inline, inlined into these).
    'TIMER_IF_GetTimerValue': (
        '2-3 reads (< 1 us): SSR changes at most once per RTC tick (30.5 us at 32.768 kHz), '
        'so two consecutive reads agree on the 2nd or 3rd try',
        f'{BOARD}/Core/Src/timer_if.c GetTimerTicks: re-reads RTC_SSR until two reads agree.'),
    'TIMER_IF_GetTimerElapsedTime': ('as TIMER_IF_GetTimerValue', f'{BOARD}/Core/Src/timer_if.c.'),
    'TIMER_IF_SetTimerContext': ('as TIMER_IF_GetTimerValue', f'{BOARD}/Core/Src/timer_if.c.'),
    'TIMER_IF_GetTime': ('as TIMER_IF_GetTimerValue', f'{BOARD}/Core/Src/timer_if.c.'),
    'TIMER_IF_StartTimer': ('as TIMER_IF_GetTimerValue', f'{BOARD}/Core/Src/timer_if.c.'),
    # RTC init handshakes (TIMER_IF_Init is in the timer driver table, so counted as run time).
    'RTC_EnterInitMode': (
        'INITF within ~2 RTCCLK cycles = 61 us at 32.768 kHz (RM0461 RTC initialization); HAL '
        'timeout 1 s (RTC_TIMEOUT_VALUE), which never expires before the timer server runs',
        f'{HAL}/stm32wlxx_hal_rtc.c: polls RTC_ICSR.INITF on HAL_GetTick.'),
    'HAL_RTC_WaitForSynchro': (
        'RSF after the next shadow-register copy, <= 2 RTCCLK cycles = 61 us (RM0461 RTC '
        'register synchronization); HAL timeout 1 s',
        f'{HAL}/stm32wlxx_hal_rtc.c: polls RTC_ICSR.RSF on HAL_GetTick.'),
    # ADC enable handshake (App/board_inputs.c, the board ADC sequence of vane, ISET, charger input and
    # VREFINT: HAL_ADC_Start_IT from board_vane_mv and board_power_adc, about once a second each).
    # The sequence adds no other wait: its channels are configured once at init (the VREFINT path
    # needs no stabilisation loop; only the temperature sensor's has one) and it completes by interrupt.
    'ADC_Enable': (
        'ADRDY a few ADC clock cycles after ADEN (RM0453 ADC enable sequence); the HAL bounds it with '
        'ADC_ENABLE_TIMEOUT = 2 ms. The ADC stays enabled between conversions (no auto power-off), so '
        'later calls find it ready and return at once',
        f'{HAL}/stm32wlxx_hal_adc.c: polls ADC_FLAG_RDY on HAL_GetTick, at most ADC_ENABLE_TIMEOUT.'),
    # ADC offset calibration (App/board_inputs.c, the board ADC sequence: once, at the modules' start).
    'HAL_ADCEx_Calibration_Start': (
        '8 calibrations of about 82 ADC clock cycles each, about 60 us at 12 MHz (RM0453 ADC '
        'calibration); each wait is bounded by ADC_CALIBRATION_TIMEOUT = 178,176 loop passes, and the '
        'final disable by ADC_DISABLE_TIMEOUT = 2 ms. Runs once at init',
        f'{HAL}/stm32wlxx_hal_adc_ex.c: counts loop passes, then polls ADEN on HAL_GetTick.'),
    'ADC_Disable': (
        'ADDIS clears ADEN within a few ADC clock cycles (RM0453 ADC disable sequence); the HAL bounds it '
        'with ADC_DISABLE_TIMEOUT = 2 ms. Only reached from the calibration at init',
        f'{HAL}/stm32wlxx_hal_adc.c: polls ADEN on HAL_GetTick, at most ADC_DISABLE_TIMEOUT.'),
    # UART enable handshakes (vcom_Resume runs after every STOP2 wake-up; vcom_Init is a driver slot).
    'UART_WaitOnFlagUntilTimeout': (
        'only reached through UART_CheckIdleState / HAL_UARTEx_StopModeWakeUpSourceConfig here: '
        'TEACK/REACK follow TE/RE within a few USART kernel clock cycles (RM0461 USART); the HAL '
        'timeout (HAL_UART_TIMEOUT_VALUE = 0x1FFFFFF ms, 9.3 h) is no bound',
        f'{HAL}/stm32wlxx_hal_uart.c: polls one ISR flag on HAL_GetTick. A blocking transfer that '
        'uses it is BANNED separately (HAL_UART_Transmit/Receive).'),
    'UART_CheckIdleState': (
        'TEACK + REACK: a few USART kernel clock cycles (RM0461 USART)',
        f'{HAL}/stm32wlxx_hal_uart.c (from HAL_UART_Init).'),
    'HAL_UARTEx_StopModeWakeUpSourceConfig': (
        'REACK after re-enabling the USART: a few kernel clock cycles (RM0461 USART)',
        f'{HAL}/stm32wlxx_hal_uart_ex.c.'),
    'vcom_ReceiveInit': (
        'NOT counter-bounded: inline while(ISR.BUSY) lasts one character (87 us at 115200 baud) '
        'per character the host sends back-to-back, then while(!ISR.REACK) a few kernel clocks; '
        'a host streaming without a gap stalls it for the stream; the IWDG is the backstop',
        f'{BOARD}/Core/Src/usart_if.c (inline register polls, invisible to the call graph). Reached '
        'only through the UTIL_ADV_TRACE driver table (UTIL_ADV_TRACE_StartRxProcess at boot).'),
    # Boot clock and watchdog set-up. HAL_GetTick returns 0 until UTIL_TIMER_Init (sys_app.c), so the
    # HAL timeouts of the RCC waits in SystemClock_Config cannot expire: the hardware is the bound.
    'HAL_RCC_OscConfig': (
        'LSE start-up, ~2 s typ with the low drive used here (DS13293 LSE oscillator tSU(LSE)); MSI '
        'ready in us. No effective timeout (HAL_GetTick is 0 this early) and the IWDG is not running '
        'yet: a dead 32 kHz crystal hangs boot',
        f'{HAL}/stm32wlxx_hal_rcc.c: polls LSERDY/MSIRDY on HAL_GetTick (LSE_STARTUP_TIMEOUT 5 s).'),
    'HAL_RCC_ClockConfig': (
        'SYSCLK switch to MSI 48 MHz and prescaler updates: a few clock cycles (RM0461 RCC)',
        f'{HAL}/stm32wlxx_hal_rcc.c: polls RCC_CFGR SWS/PREF flags on HAL_GetTick.'),
    'RCC_SetFlashLatencyFromMSIRange': (
        'FLASH_ACR.LATENCY read-back: a few cycles',
        f'{HAL}/stm32wlxx_hal_rcc.c: polls the latency read-back on HAL_GetTick.'),
    'HAL_IWDG_Init': (
        'IWDG prescaler/reload update in the LSI domain, a few LSI cycles; HAL timeout 6 x 256 LSI '
        'cycles + LSI start-up, ~48 ms',
        f'{HAL}/stm32wlxx_hal_iwdg.c: polls IWDG_SR PVU/RVU/WVU on HAL_GetTick.'),
}

# Clock callers that only read the time (a timestamp or a deadline for a timer/radio call): no loop.
# None in stage0-node now: both roles read the time only through App/clock.c (SysTimeGetMcuTime, not
# a CLOCKS source), and the ACK window is a UTIL_TIMER. The entries this table held (app_rx.c
# on_rx_done ... SubghzApp_Init, app_tx.c handle) dated from HAL_GetTick timestamps and no longer
# matched any clock call (2026-10-15 refactor, checked with the table emptied). A new entry needs a
# real clock call to classify.
TIMESTAMP = {}

# Deliberate hang/crash bench commands.
TEST_ONLY = {
    'fault_test': 'TEST-FAULT console command: prints, waits for the UART, then faults on purpose.',
    'test_hang': 'TEST-HANG console command: stops the main loop so the watchdog must reset.',
}

# The body of main()'s while(1): runs forever after boot.
MAIN_LOOP = {
    'MX_SubGHz_Phy_Process': f'{BOARD}/Core/Src/main.c calls it in its while (1) loop (runs the sequencer).',
}

# Constant driver tables: {section holding the table: (object name, {function: slot member})}, from
# {RADIO}/radio.c `const struct Radio_s Radio` and radio.h. A function whose address is taken ONLY in
# such a table (checked from the relocations) runs only when code reads its slot, so it is not
# treated as a root. Instead the compiled sources (every file in the make .d dependency lists) are
# scanned: `Radio.Slot(...)` inside a function becomes a direct call edge from that function. Any
# other use (the slot stored or passed, a mention outside a function such as in a macro, a caller
# with no call graph, or the object used other than as `Radio.Slot`) makes the function a root.
DRIVER_TABLES = {
    '.rodata.Radio': ('Radio', {
        'RadioInit': 'Init', 'RadioGetStatus': 'GetStatus', 'RadioSetModem': 'SetModem',
        'RadioSetChannel': 'SetChannel', 'RadioIsChannelFree': 'IsChannelFree', 'RadioRandom': 'Random',
        'RadioSetRxConfig': 'SetRxConfig', 'RadioSetTxConfig': 'SetTxConfig',
        'RadioCheckRfFrequency': 'CheckRfFrequency', 'RadioTimeOnAir': 'TimeOnAir', 'RadioSend': 'Send',
        'RadioSleep': 'Sleep', 'RadioStandby': 'Standby', 'RadioRx': 'Rx', 'RadioStartCad': 'StartCad',
        'RadioSetTxContinuousWave': 'SetTxContinuousWave', 'RadioRssi': 'Rssi', 'RadioWrite': 'Write',
        'RadioRead': 'Read', 'RadioWriteRegisters': 'WriteRegisters', 'RadioReadRegisters': 'ReadRegisters',
        'RadioSetMaxPayloadLength': 'SetMaxPayloadLength', 'RadioSetPublicNetwork': 'SetPublicNetwork',
        'RadioGetWakeupTime': 'GetWakeupTime', 'RadioIrqProcess': 'IrqProcess', 'RadioRxBoosted': 'RxBoosted',
        'RadioSetRxDutyCycle': 'SetRxDutyCycle', 'RadioTxPrbs': 'TxPrbs', 'RadioTxCw': 'TxCw',
        'RadioSetRxGenericConfig': 'RadioSetRxGenericConfig', 'RadioSetTxGenericConfig': 'RadioSetTxGenericConfig',
        'RFW_TransmitLongPacket': 'TransmitLongPacket', 'RFW_ReceiveLongPacket': 'ReceiveLongPacket',
        'RadioLrFhssSetCfg': 'LrFhssSetCfg', 'RadioLrFhssGetTimeOnAirInMs': 'LrFhssGetTimeOnAirInMs',
    }),
}

BOOT_ENTRY = {'main', 'Reset_Handler'}
CLONE = re.compile(r'\.(?:isra|constprop|part|cold|lto_priv)\.\d+.*$')


def short(title):
    return title.split(':')[-1]


# Only defined nodes (with a frame size); a declaration's label points at a header.
NODE_FILE = re.compile(r'node: \{ title: "([^"]+)" label: "[^"\\]*\\n([^":\\]+):\d+:\d+\\n\d+ bytes')
ORIGIN = {}   # title -> basename of the file defining it (a global's title names no file)


def origins(build):
    """Each defined function's source file basename, from the .ci node labels."""
    out = {}
    for ci in stack_report.build_files(build, '.ci'):
        for title, path in NODE_FILE.findall(ci.read_text(errors='replace')):
            out.setdefault(title, Path(path).name)
    return out


def keys(title):
    """Table keys that name this call-graph node: 'name', its clone base, and 'file.c:name'."""
    name = short(title)
    base = CLONE.sub('', name)
    out = [name, base]
    f = Path(title.rsplit(':', 1)[0]).name if ':' in title else ORIGIN.get(title)
    if f:
        out += [f'{f}:{name}', f'{f}:{base}']
    return out


def lookup(table, title):
    for k in keys(title):
        if k in table:
            return k
    return None


def compiled_sources(build):
    """Every source and header compiled into this build, from the make .d files (paths relative to
    the compiler's working directory, recovered from the .o target path)."""
    out = set()
    for d in stack_report.build_files(build, '.d'):
        rule = d.read_text(errors='replace').replace('\\\n', ' ').split('\n', 1)[0]
        target, _, deps = rule.partition(': ')
        base = d.with_suffix('.o')
        for _ in Path(target.strip()).parts:
            base = base.parent
        for dep in deps.split():
            path = Path(dep) if Path(dep).is_absolute() else base/dep
            if path.exists():
                out.add(path.resolve())
    return sorted(out)


C_NOISE = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
FUNC_HEAD = re.compile(r'(\w+)\s*\([^{};]*\)\s*$')


def strip_c(text):
    """C text with comments and string/char literals blanked (offsets and line numbers kept)."""
    return C_NOISE.sub(lambda m: re.sub(r'[^\n]', ' ', m[0]), text)


def function_spans(code):
    """[(start, end, name)] of the top-level brace blocks that are function bodies."""
    spans, depth, head_from, start = [], 0, 0, 0
    for i, ch in enumerate(code):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}' and depth:
            depth -= 1
            if depth == 0:
                head = re.sub(r'__attribute__\s*\(\(.*?\)\)', ' ', code[head_from:start], flags=re.S)
                m = FUNC_HEAD.search(head)
                if m:
                    spans.append((start, i, m[1]))
                head_from = i + 1
        elif ch == ';' and depth == 0:
            head_from = i + 1
    return spans


EDGE_SITE = re.compile(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)" label: "([^"]+):(\d+):\d+"')


def compile_base(build):
    """The compiler's working directory (the .d targets are relative to it), or None."""
    for d in stack_report.build_files(build, '.d'):
        target = d.read_text(errors='replace').split(':', 1)[0].strip()
        base = d.with_suffix('.o')
        for _ in Path(target).parts:
            base = base.parent
        return base
    return None


def call_sites(build):
    """{(caller title, callee as written in the .ci): [(source path, line)]} from the edge labels.
    After inlining, a call site still names the source line, so the function written around it is
    known even when that function no longer exists in the graph."""
    base, sites = compile_base(build), {}
    for ci in stack_report.build_files(build, '.ci'):
        for src, dst, path, line in EDGE_SITE.findall(ci.read_text(errors='replace')):
            p = Path(path)
            p = p if p.is_absolute() or base is None else base/p
            sites.setdefault((src, dst), []).append((p, int(line)))
    return sites


_SPANS = {}


def enclosing_function(path, line):
    """Name of the C function whose body contains this source line, or None."""
    if path not in _SPANS:
        try:
            code = strip_c(Path(path).read_text(errors='replace'))
        except OSError:
            code = ''
        line_of = lambda at: code.count('\n', 0, at) + 1
        _SPANS[path] = [(line_of(s), line_of(e), name) for s, e, name in function_spans(code)]
    return next((name for s, e, name in _SPANS[path] if s <= line <= e), None)


def slot_uses(build, wanted):
    """Scan the compiled sources for the slots of `wanted` ({function: (object, slot)}).
    Returns ({function: {(caller name, caller file basename, line)}} for `Object.Slot(` calls inside
    a function, {function: reason} for any use that must make the function a root)."""
    calls, escaped, by_slot = {}, {}, {}
    for f, key in wanted.items():
        by_slot.setdefault(key, []).append(f)
    for obj in sorted({obj for obj, _ in by_slot}):
        use = re.compile(rf'\b{obj}\b(\s*(?:\.|->)\s*(\w+)(\s*\()?)?')
        for src in compiled_sources(build):
            code = strip_c(src.read_text(errors='replace'))
            if not re.search(rf'\b{obj}\b', code):
                continue
            spans = function_spans(code)
            for m in use.finditer(code):
                caller = next((name for s, e, name in spans if s < m.start() < e), None)
                where = f'{src.name}:{code.count(chr(10), 0, m.start()) + 1}'
                if not m[1]:
                    # `struct Radio_s Radio` (its definition or extern declaration) is not a use.
                    if not re.search(r'\bstruct\s+\w+\s*$', code[max(0, m.start() - 80):m.start()]):
                        for (o, _slot), fs in by_slot.items():
                            for f in fs if o == obj else ():
                                escaped.setdefault(f, f'{obj} used as an object at {where}')
                    continue
                for f in by_slot.get((obj, m[2]), ()):
                    if m[3] and caller:
                        line = code.count('\n', 0, m.start(2)) + 1
                        calls.setdefault(f, set()).add((caller, src.name, line))
                    else:
                        how = 'stored or passed' if caller else 'outside a function'
                        escaped.setdefault(f, f'{obj}.{m[2]} {how} at {where}')
    return calls, escaped


def table_slot(name, sections):
    """(object, slot) if this function's address is taken only in a DRIVER_TABLES table, else None."""
    for section, (obj, table) in DRIVER_TABLES.items():
        if name in table and sections and set(sections) <= {section}:
            return obj, table[name]
    return None


def analyse(build, toolchain=DEFAULT_TOOLCHAIN, taken=None):
    """`taken`: {function: sections taking its address} (default: from the objects and .elf); a plain
    set of names means 'taken somewhere else than a driver table'."""
    frames, _kinds, edges, defined_in = stack_report.load(build)
    ORIGIN.clear()
    ORIGIN.update(origins(build))
    if taken is None:
        linked = stack_report.linked_functions(build, toolchain)
        taken = {n: s for n, s in stack_report.address_references(build, toolchain).items() if n in linked}
    elif not isinstance(taken, dict):
        taken = {n: {'.text'} for n in taken}
    titles = set(frames)
    wanted = {n: slot for n, s in taken.items() if (slot := table_slot(n, s))}
    slot_calls, escaped = slot_uses(build, wanted)
    sites = call_sites(build)
    # The graph nodes holding each indirect call site (a function inlined into another keeps its
    # source line in the .ci label).
    indirect_at = {}
    for (src, dst), where in sites.items():
        if dst == INDIRECT:
            for p, line in where:
                indirect_at.setdefault((p.name, line), set()).add(src)
    # A slot call becomes a direct edge from the node(s) that contain it: the function written around
    # it, and any node its indirect call site was inlined into. A call that cannot be placed in the
    # graph makes the slot's function a root instead.
    extra = {}
    for f, callers in sorted(slot_calls.items()):
        targets = [t for t in titles if short(t) == f]
        for name, file, line in sorted(callers):
            found = {t for t in titles if short(t) == name and f'{file}:{name}' in keys(t)}
            found |= indirect_at.get((file, line), set()) & titles
            if not found:
                escaped.setdefault(f, f'called from {file}:{name} (line {line}), which has no call graph')
            for c in found:
                extra.setdefault(c, set()).update(targets)
    table_funcs = {n for n in wanted if n not in escaped}
    via_slot = {n: sorted({name for name, _, _ in slot_calls.get(n, ())}) for n in table_funcs}

    def callees_raw(f):
        """(callee title, callee as written in the .ci or None for a slot edge)."""
        for t in sorted(edges.get(f, ())):
            if t == INDIRECT:
                continue
            for c in stack_report.resolve(t, frames, defined_in) or [t]:
                yield c, t
        for c in sorted(extra.get(f, ())):
            yield c, None

    def callees(f):
        return [c for c, _ in callees_raw(f)]

    def written_in(f, raw):
        """[(file basename, function written around the call, line)] for each site of this edge.
        Differs from f when GCC inlined the written function into f."""
        return [(p.name, enclosing_function(p, line), line) for p, line in sites.get((f, raw), ())]

    in_table = lambda table, file, name: name is not None and (name in table or f'{file}:{name}' in table)

    def test_edge(f, raw):
        """Every site of this call is written inside a TEST_ONLY function (inlined into f)."""
        w = written_in(f, raw) if raw else []
        return bool(w) and all(in_table(TEST_ONLY, file, name) for file, name, _ in w)

    def unclassified_clock_sites(f):
        """Clock calls in f not covered by a table entry for f or for the function written around
        the call (so a classified function stays classified after GCC inlines it elsewhere)."""
        if lookup(CLOCKS, f) or lookup(TIMESTAMP, f) or lookup(ALLOWED, f) or lookup(BANNED, f):
            return []
        bad = []
        for c, raw in callees_raw(f):
            if not lookup(CLOCKS, c):
                continue
            w = written_in(f, raw) if raw else []
            tables = (TIMESTAMP, ALLOWED, BANNED, TEST_ONLY)
            bad += [f'{short(c)} at {file}:{line} in {name}' for file, name, line in w
                    if not any(in_table(t, file, name) for t in tables)]
            if not w:
                bad.append(short(c))
        return bad

    is_root_name = lambda t: short(t) not in BOOT_ENTRY
    irq = sorted(t for t in titles if short(t).endswith(('_IRQHandler', '_Handler')) and is_root_name(t))
    callbacks = sorted(t for t in titles if short(t) in taken and t not in irq and is_root_name(t)
                       and short(t) not in table_funcs)
    loop = sorted(t for t in titles if lookup(MAIN_LOOP, t))
    roots = list(dict.fromkeys(irq + callbacks + loop))
    # A call through a pointer reaches only address-taken functions, which are all roots: the run-time
    # set below is closed under pointer calls by construction.

    test = lambda t: lookup(TEST_ONLY, t) is not None
    test_calls = []   # (run-time caller, TEST_ONLY function written around the call, callee)

    def walk(starts, blocked, run_time=False):
        """BFS over direct calls. Returns {node: parent}; does not enter `blocked` nodes and does not
        descend below BANNED ones. At run time, a call written inside an inlined TEST_ONLY function
        is not followed but recorded in test_calls."""
        parent = {s: None for s in starts}
        q = deque(starts)
        while q:
            f = q.popleft()
            if lookup(BANNED, f):
                continue
            for c, raw in callees_raw(f):
                if run_time and test_edge(f, raw):
                    test_calls.append((f, written_in(f, raw)[0][1], c))
                    continue
                if c not in parent and not blocked(c):
                    parent[c] = f
                    q.append(c)
        return parent

    def path(parent, f, prefix=None):
        out = []
        while f is not None:
            out.append(short(f))
            start, f = f, parent[f]
        return (prefix or {}).get(start, '') + ' > '.join(reversed(out))

    def hits(parent):
        """(banned, allowed, unclassified clock callers) among the reached nodes."""
        banned, allowed, unclassified = {}, {}, {}
        for f in parent:
            if (k := lookup(BANNED, f)):
                banned.setdefault(k, f)
            elif (k := lookup(ALLOWED, f)):
                allowed.setdefault(k, f)
            elif (bad := unclassified_clock_sites(f)):
                unclassified[f] = bad
        return banned, allowed, unclassified

    run = walk([r for r in roots if not test(r)], test, run_time=True)
    run_calls = {}
    for p in run:
        for c, raw in callees_raw(p):
            if not test_edge(p, raw):
                run_calls.setdefault(c, set()).add(short(p))
    callers = lambda f: sorted(run_calls.get(f, ()))
    rb, ra, ru = hits(run)

    # Test-only: TEST_ONLY functions that are roots or that run-time code calls (directly, or inlined
    # into the caller), and what they reach.
    test_starts = [r for r in roots if test(r)]
    test_starts += sorted({c for f in run for c in callees(f) if test(c) and c not in run})
    commands = [short(t) if t in roots else
                path(run, next(f for f in run if t in set(callees(f)))) + ' > ' + short(t) for t in test_starts]
    prefix = {}
    for f, name, c in test_calls:
        commands.append(f'{path(run, f)} > {name} (inlined)')
        if c not in run and c not in test_starts:
            test_starts.append(c)
            prefix[c] = f'{path(run, f)} > {name} (inlined) > '
    tparent = walk(test_starts, lambda t: t in run)
    tb, ta, tu = hits(tparent)

    # Boot: main by direct calls, minus everything that also runs at run time.
    mains = [t for t in titles if short(t) == 'main']
    bparent = walk(mains, lambda t: test(t) or t in run)
    bb, ba, bu = hits(bparent)

    return dict(
        irq=irq, callbacks=callbacks, loop=loop, via_slot=via_slot, escaped=escaped,
        run=[(k, path(run, f), callers(f)) for k, f in sorted(rb.items())],
        allowed=[(k, path(run, f)) for k, f in sorted(ra.items())],
        unclassified=[(short(f), path(run, f), ru[f]) for f in sorted(ru)],
        boot=[(k, path(bparent, f), 'BANNED') for k, f in sorted(bb.items())]
        + [(k, path(bparent, f), 'ALLOWED') for k, f in sorted(ba.items())]
        + [(short(f), path(bparent, f), 'unclassified clock caller') for f in sorted(bu)],
        test=[(k, path(tparent, f, prefix), 'BANNED') for k, f in sorted(tb.items())]
        + [(k, path(tparent, f, prefix), 'ALLOWED') for k, f in sorted(ta.items())]
        + [(short(f), path(tparent, f, prefix), 'unclassified clock caller') for f in sorted(tu)],
        test_commands=sorted(set(commands)),
        failed=bool(rb or ru),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('build')
    ap.add_argument('--toolchain', default=DEFAULT_TOOLCHAIN, help='directory with arm-none-eabi-nm/objdump')
    a = ap.parse_args(argv)
    r = analyse(a.build, a.toolchain)
    print(f"run-time roots: {len(r['irq']) + len(r['callbacks']) + len(r['loop'])} "
          f"({len(r['irq'])} interrupt handlers, {len(r['callbacks'])} address-taken functions, "
          f"{len(r['loop'])} main loop)")
    called = sorted(f for f, c in r['via_slot'].items() if c)
    if called:
        print('driver-table functions followed as direct calls from their slot callers (not roots): '
              + ', '.join(f'{f} (from {", ".join(r["via_slot"][f])})' for f in called))
    never = sorted(f for f, c in r['via_slot'].items() if not c)
    if never:
        print('driver-table functions whose slot nothing reads (not roots): ' + ', '.join(never))
    for f, why in sorted(r['escaped'].items()):
        print(f'driver-table function kept as a root: {f}: {why}')
    if r['test_commands']:
        print('TEST_ONLY bench commands reachable: ' + '; '.join(r['test_commands']))
    print('\nBANNED waits reachable at run time:' + ('' if r['run'] else ' none'))
    for k, p, callers in r['run']:
        print(f'  FAIL {k}: {BANNED[k]}\n       path: {p}\n       called at run time from: {", ".join(callers)}')
    print('\nunclassified clock callers reachable at run time:' + ('' if r['unclassified'] else ' none'))
    for name, p, where in r['unclassified']:
        print(f'  FAIL {name} calls a clock and is in no table: {"; ".join(where)}\n       path: {p}')
    print('\nallowed hardware waits reachable at run time:' + ('' if r['allowed'] else ' none'))
    for k, p in r['allowed']:
        print(f'  {k}: {ALLOWED[k][0]}\n       path: {p}')
    print('\nboot waits (main only, allowed):' + ('' if r['boot'] else ' none'))
    for k, p, kind in r['boot']:
        print(f'  {kind} {k}\n       path: {p}')
    print('\ntest-only waits (TEST_ONLY bench commands, allowed):' + ('' if r['test'] else ' none'))
    for k, p, kind in r['test']:
        print(f'  {kind} {k}\n       path: {p}')
    print('\nresult: ' + ('FAIL: the firmware can block at run time' if r['failed'] else
                          'OK: no banned or unclassified wait is reachable at run time'))
    return 1 if r['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
