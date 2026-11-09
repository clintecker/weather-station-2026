#ifndef BOARD_CAPS_H
#define BOARD_CAPS_H
/* GENERATED from board.toml by tools/boardgen.py. Do not edit: edit board.toml, then run tools/boardgen.py.
 * What the NUCLEO-WL55JC1 (MB1389) can do, and its radio front end: the generic
 * firmware/board/stm32wl/SubGHz_Phy/Target/radio_board_if.c reads the RF switch, TCXO and PA path here. */

#define BOARD_NAME "nucleo-wl55jc"
#define BOARD_ROLE_TX 1
#define BOARD_ROLE_RX 1
#define BOARD_BENCH_OLED_OK 1
#define BOARD_LED_COUNT 3

/* Feature requirements: a build the board cannot run stops here. */
#if defined(WS_BENCH_OLED) && WS_BENCH_OLED && !BOARD_BENCH_OLED_OK
#error "WS_BENCH_OLED=1 on the nucleo-wl55jc board: "
#endif

/* The radio: the RF switch on PC4, PC5, PC3 (CTRL1..CTRL3), driven by ST's BSP. Truth table (levels in that order):
     off    0  0  0
     rx     1  0  1
     tx_hp  0  1  1
     tx_lp  1  1  1
   */
#define BOARD_RF_SWITCH_BSP 1
#define BOARD_RFO RBI_CONF_RFO_LP_HP /* PA path: lp_hp */
#define BOARD_RFO_LP_MAX_DBM 15
#define BOARD_RFO_HP_MAX_DBM 22
#define BOARD_TCXO 1U
#define BOARD_TCXO_CTRL_VOLTAGE TCXO_CTRL_1_7V
#define BOARD_TCXO_STARTUP_MS ( 1UL )
#define BOARD_DCDC 1U

#endif
