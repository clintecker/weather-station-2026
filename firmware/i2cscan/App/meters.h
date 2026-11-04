/* The weather meter inputs for the bench tool (meters.c): the node's pins (stage0-node/App/board_inputs.c),
 * read without the node's link probe or minute windows, so each spin, turn and tip shows within a second. */
#ifndef METERS_H
#define METERS_H

#include <stdint.h>

void meters_init(void);

uint16_t meters_cups(void);    /* LPTIM1 on PB5: cup pulses since start, 16 bits, wraps */
uint32_t meters_tips(void);    /* EXTI4 on PB4: rain tips since start, 100 ms lockout as the node */
/* 1 with the vane (PB2, ADC1_IN4) in ratio mV, as the node reads it; 0 if the ADC failed. Blocking, ~1 ms. */
int meters_vane_mv(uint16_t *mv);

#endif
