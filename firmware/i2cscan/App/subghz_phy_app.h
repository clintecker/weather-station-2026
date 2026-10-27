/* i2cscan (weather-station-2026): the board's MX_SubGHz_Phy_Init (board/nucleo-wl55jc) starts the
   application through SubghzApp_Init. This tool does not use the radio. */
#ifndef SUBGHZ_PHY_APP_H
#define SUBGHZ_PHY_APP_H

void SubghzApp_Init(void);

#endif
