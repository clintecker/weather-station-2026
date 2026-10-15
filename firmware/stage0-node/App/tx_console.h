#ifndef TX_CONSOLE_H
#define TX_CONSOLE_H
#include <stdint.h>
/* TX console (firmware/stage0-node/README.md, "Console"): STATUS, KAT,
 * PROVISION <station_id> <32 hex key> [epoch_floor], WIPE ERASE-ALL-NODE-STATE, TEST-FLASH-STORM,
 * and the bench commands of App/bench.h. Every line this board prints starts with '#'. */
#define STORM_EPOCH 0xFFFFFFFFUL   /* TEST-FLASH-STORM records; the boot scrub drops any left pending */
void tx_console_init(void);   /* the console, the reboot timer and the storm task */
void tx_status(void);         /* #status, #counts and #timing */
#endif
