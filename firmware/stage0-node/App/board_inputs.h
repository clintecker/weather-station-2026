#ifndef BOARD_INPUTS_H
#define BOARD_INPUTS_H
/* The board inputs of the WSMP local modules (App/board_inputs.c): the cup counter, the vane ADC,
 * the rain gauge interrupt and the charger pins. It defines the board seams of mod_wind.h and
 * mod_power.h. A host harness defines its own. */
void board_inputs_init(void);
#endif
