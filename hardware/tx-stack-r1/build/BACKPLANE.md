# Backplane: build sheet

`layout/drawings.py` writes this sheet. The drawing is `drawings/backplane.svg`.

The backplane is a BusBoard PAD3U padboard (160.02 x 100.08 mm, 38 x 62 holes on 0.1 in). It has a separate plated pad per hole and no strips. You use 31 of its rows at the plated end, each the full 38 holes. Both faces have pads. This sheet calls the face the sockets go on the component side (the front, toward the cards), and the face with the bus wires the copper side (toward the back wall). The lines run up and down in the box.

Nothing on the board connects unless a wire does. On lines 1-18 a bare bus wire on the copper side, soldered at every used pad, carries bus line n for every card (every socket is 1x30). Lines 19-23 and 26 carry B4's power pins (the battery path, its senses and SYS) down to short leads to the charger and the pack. The charger's own ground lead (J3 GND, SYS's return) lands on line 12, the bus ground.

## 1. Cut

1. Take one PAD3U and find the end with the two large plated mounting holes. The other end has two small plain holes. Count 31 rows in from the mounting-hole end. They become lines 30 (next to the mounting holes) down to 0, each the full 38 holes. Seen from the face that becomes the front (the face the sockets go on), the mounting-hole end is the right edge. Keep the PAD3U's own right, top and bottom edges, with no cut there.
2. There are no holes to drill, because the base has no screw posts (enclosure 4). The cards in the sockets hold the board. Leave both mounting holes as they are: the right corner post's slot holds that edge.
3. Score both faces midway between line 0 and the next row out (never through the holes) and snap. That's the only cut. Sand the edge flat. Aim for 1.27 mm from line 0's hole centres, about 0.8 mm from the near side of the 0.94 mm holes. If the edge ends more than about 1.78 mm from those centres, it won't go fully into the left wall's groove. Cut a little short and it still seats under the groove roof.
4. Check the right edge. It should be 2.83 mm beyond the mounting holes' centres (5.48 from line 30's) [TBD-MEASURE: the scan cuts that end off]. For the fit, it must be no more than 6.13 past line 30's centres.
5. Meter any two neighbouring pads. They read open, because the board has no strips.

## 2. Sockets (one per card; pin n on line n) and their key plugs

| Socket | Card | Hole along the lines | Key plug (line, hole) | Colour dot |
|---|---|---|---|---|
| XB1 generic female strip, cut to 1x30 | socket for B1 (PORTS A); key plug in contact 27 | 27 | contact 27: line 27, hole 27 | blue |
| XB2 generic female strip, cut to 1x30 | socket for B2 (PORTS B + METERS); key plug in contact 28 | 19 | contact 28: line 28, hole 19 | green |
| XB3 generic female strip, cut to 1x30 | socket for B3 (CORE); key plug in contact 29 | 35 | contact 29: line 29, hole 35 | yellow |
| XB4 generic female strip, cut to 1x30 | socket for B4 (POWER); key plug in contact 30 | 13 | contact 30: line 30, hole 13 | red |

Fit each socket square to the board, because a card pin bent sideways won't go in. Solder one end pin, check the socket, then solder the rest. Every socket is 1x30 (lines 1-30). It takes its card's 29 header pins, and the key plug (below) in the 30th contact. Solder all 30 tails, each in its own pad.

On lines 19-30 only B4's contacts on lines 19-23 and 26 meet a bus wire. Every other contact there is soldered to its own pad and nothing else (an isolated pad):

- XB4 (hole 13) lines 24-25, 27-30
- XB2 (hole 19) lines 19-30
- XB1 (hole 27) lines 19-30
- XB3 (hole 35) lines 19-30

Cut each socket from a longer strip. Pull the contact one past the end and cut through that empty position, so you lose one position at each cut. File the cut face flat.

**Key plugs (the slot keys).** The four sockets are the same, so each one gets a key plug that only its own card clears: XB4 (for B4) in contact 30, XB2 (for B2) in contact 28, XB1 (for B1) in contact 27, XB3 (for B3) in contact 29. Each card has that same pin pulled from its header (see its build sheet). Every other card still has that pin, so it stubs on the plug and can't seat. For example, B3 in B4's slot would put the battery on the Wio-E5.

Make each plug from the generic male header stock. Pull one pin out of the plastic. Push its long end into the socket contact from the front until it bottoms. Cut it flush with the socket mouth and file the cut end flat, so nothing stands proud of the mouth.

Only the contact's grip holds the plug. Never solder it, and solder nothing else to that contact's pad. It stays an isolated pad, with no bus wire and no lead. After fitting, try each card in each wrong socket by hand, off the base. Each one must stop at the mouth.

**Colour dots.** Put a paint-pen or sticker dot beside each socket on the front face, and one on the base beside its card slot. Use the same colour as the dot on that card's front edge: B1 blue, B2 green, B3 yellow, B4 red.

## 3. Pins and parts on the front (the charger's I2C, the sense resistors)

| Part | Pin | Line, hole | Bus line |
|---|---|---|---|
| XJ1 (charger I2C pins (lead to EVM J8)) | ground | 2, 11 | ground |
| XJ1 (charger I2C pins (lead to EVM J8)) | clock | 7, 11 | I2C clock (SCL) |
| XJ1 (charger I2C pins (lead to EVM J8)) | data | 10, 11 | I2C data (SDA) |
| R7 (charger sense 100 ohm, lying on the front, junction to a lone pad) | 1 | 21, 7 | battery + junction (backplane lines 21-22) |
| R7 (charger sense 100 ohm, lying on the front, junction to a lone pad) | 2 | 24, 7 | charger battery sense (BATP) |
| R8 (gauge sense 100 ohm, lying on the front (on a slant), junction to line 23) | 1 | 22, 8 | battery + junction (backplane lines 21-22) |
| R8 (gauge sense 100 ohm, lying on the front (on a slant), junction to line 23) | 2 | 23, 11 | fuel gauge cell sense (VBAT) |

R7 and R8 lie flat on the front, with R8 on a slant and its legs bent to the span. R7's free leg (line 24, hole 7) also takes the charger sense lead on the copper side.

### Leads to the charger and the pack (copper side, short)

| From | To the backplane | What |
|---|---|---|
| F5 lead + | line 21, hole 6 | pack + (after the fuse F5) to the junction, 24 AWG stranded, red with a black band |
| U1 battery + (J5 BATTERY) | line 19, hole 6 | charger battery + (J5 BATTERY) to lines 19-20, 24 AWG stranded, red with a black band |
| U1 system out (J3 SYS) | line 26, hole 6 | charger system output (J3 SYS) to line 26 (B4 pin 26, the regulator in), 24 AWG stranded, red with a black band |
| U1 system ground (J3 GND) | line 12, hole 11 | charger system ground (J3 GND) to line 12 (the bus ground, SYS's return), 24 AWG stranded, black |
| U1 battery sense (J5 SNS_BATP) | R7's free leg (line 24, hole 7) | charger battery sense (J5 SNS_BATP) from R7's free leg, 24 AWG stranded, white with a red band |

Cut each lead to the length in section 5 and trim it to fit. Leave a service loop, because the EVM slides out on these leads.

The ground lead (J3 GND to line 12) is SYS's return. The regulator's load and the radio's transmit peaks come back mainly on it, so they don't depend on the I2C lead's J8 pin 1. J8 pin 1 is tied to the same ground on the EVM and still carries a small parallel share. Run the ground lead beside the SYS lead from J3 and on to line 12 above the mux.

## 4. Bus wires (copper side)

Use bare 22 AWG solid copper: the Adafruit 1311 hook-up wire on hand, stripped (0.64 mm). Lay each wire straight along its line over the pads and tack it at the first and last hole. Then solder it at every hole listed. Cut length: the span plus 10 mm.

Most of those holes already hold a socket pin, an XJ1 pin, a resistor leg or a section-3 lead. The others take the section-5 leads: hole 5 on lines 19, 20, 21 and 22, hole 10 on lines 3, 4, 8, 9, 13, 14, 17 and 18, hole 14 on line 15, hole 15 on line 1, hole 16 on line 2, hole 17 on line 7, hole 18 on line 10 and hole 38 on lines 2 and 12. Fit those leads before the bus wires, or leave those holes open and solder them in section 5.

| Line | Bus line | From hole | To hole | Cut | Soldered at holes |
|---|---|---|---|---|---|
| 1 | 3.3 V supply | 13 | 35 | 70 mm | 13, 15, 19, 27, 35 |
| 2 | ground | 11 | 38 | 80 mm | 11, 13, 16, 19, 27, 35, 38 |
| 3 | sensor port 1 data (SDA) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 4 | sensor port 1 clock (SCL) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 5 | cups (wind speed) pulse | 13 | 35 | 70 mm | 13, 19, 27, 35 |
| 6 | vane (wind direction) voltage | 13 | 35 | 70 mm | 13, 19, 27, 35 |
| 7 | I2C clock (SCL) | 11 | 35 | 75 mm | 11, 13, 17, 19, 27, 35 |
| 8 | sensor port 2 data (SDA) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 9 | sensor port 2 clock (SCL) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 10 | I2C data (SDA) | 11 | 35 | 75 mm | 11, 13, 18, 19, 27, 35 |
| 11 | rain gauge pulse | 13 | 35 | 70 mm | 13, 19, 27, 35 |
| 12 | ground | 11 | 38 | 80 mm | 11, 13, 19, 27, 35, 38 |
| 13 | sensor port 3 data (SDA) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 14 | sensor port 3 clock (SCL) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 15 | mux reset | 13 | 35 | 70 mm | 13, 14, 19, 27, 35 |
| 16 | spare bus line (for the charger interrupt) | 13 | 35 | 70 mm | 13, 19, 27, 35 |
| 17 | sensor port 4 data (SDA) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 18 | sensor port 4 clock (SCL) | 10 | 35 | 75 mm | 10, 13, 19, 27, 35 |
| 19 | charger battery + (after the shunt) | 5 | 13 | 35 mm | 5, 6, 13 |
| 20 | charger battery + (after the shunt) | 5 | 13 | 35 mm | 5, 13 |
| 21 | battery + junction (backplane lines 21-22) | 5 | 13 | 35 mm | 5, 6, 7, 13 |
| 22 | battery + junction (backplane lines 21-22) | 5 | 13 | 35 mm | 5, 8, 13 |
| 23 | fuel gauge cell sense (VBAT) | 11 | 13 | 20 mm | 11, 13 |
| 26 | charger system output (SYS) | 6 | 13 | 30 mm | 6, 13 |

## 5. Leads on the copper side

| From | To | Length | Line | What |
|---|---|---|---|---|
| PG1 lead - | U1 battery - (J5 GND) | 150 mm, trim to fit | battery - (charger ground) | pack - to charger battery - (J5 GND), 24 AWG stranded, black |
| U4 VIN | backplane line 1 hole 15 | 80 mm | 3.3 V supply | mux VCC header lead to its line's bus wire |
| U4 GND | backplane line 2 hole 16 | 90 mm | ground | mux GND header lead to its line's bus wire |
| U4 SCL | backplane line 7 hole 17 | 85 mm | I2C clock (SCL) | mux SCL header lead to its line's bus wire |
| U4 SDA | backplane line 10 hole 18 | 85 mm | I2C data (SDA) | mux SDA header lead to its line's bus wire |
| U4 RESET | backplane line 15 hole 14 | 55 mm | mux reset | mux RST header lead to its line's bus wire |
| U4 CH0 SDA | backplane line 3 hole 10 | 30 mm of cable | sensor port 1 data (SDA) | QT cable #4209 in mux channel 0, pin end cut off: its blue SDA into hole 10 |
| U4 CH0 SCL | backplane line 4 hole 10 | 30 mm of cable | sensor port 1 clock (SCL) | QT cable #4209 in mux channel 0, pin end cut off: its yellow SCL into hole 10 |
| U4 CH1 SDA | backplane line 8 hole 10 | 25 mm of cable | sensor port 2 data (SDA) | QT cable #4209 in mux channel 1, pin end cut off: its blue SDA into hole 10 |
| U4 CH1 SCL | backplane line 9 hole 10 | 25 mm of cable | sensor port 2 clock (SCL) | QT cable #4209 in mux channel 1, pin end cut off: its yellow SCL into hole 10 |
| U4 CH2 SDA | backplane line 13 hole 10 | 30 mm of cable | sensor port 3 data (SDA) | QT cable #4209 in mux channel 2, pin end cut off: its blue SDA into hole 10 |
| U4 CH2 SCL | backplane line 14 hole 10 | 30 mm of cable | sensor port 3 clock (SCL) | QT cable #4209 in mux channel 2, pin end cut off: its yellow SCL into hole 10 |
| U4 CH3 SDA | backplane line 17 hole 10 | 30 mm of cable | sensor port 4 data (SDA) | QT cable #4209 in mux channel 3, pin end cut off: its blue SDA into hole 10 |
| U4 CH3 SCL | backplane line 18 hole 10 | 30 mm of cable | sensor port 4 clock (SCL) | QT cable #4209 in mux channel 3, pin end cut off: its yellow SCL into hole 10 |
| backplane line 2 hole 38 | backplane line 12 hole 38 | 40 mm | ground | the two bus ground lines joined |
| backplane line 19 hole 5 | backplane line 20 hole 5 | 20 mm | charger battery + (after the shunt) | lines 19 and 20 joined (charger battery +, two pins) |
| backplane line 21 hole 5 | backplane line 22 hole 5 | 20 mm | battery + junction (backplane lines 21-22) | lines 21 and 22 joined (battery + junction, two pins) |
| PG1 lead + | F5 lead from PG1 | PG1's red lead cut to 30 mm, then F5's own holder lead | pack + lead (before the fuse) | PG1's red lead spliced to the pack fuse F5's holder lead, within 30 mm of PG1's socket |
| F5 lead + | backplane line 21 hole 6 | 100 mm, trim to fit | battery + junction (backplane lines 21-22) | pack + (after the fuse F5) to the junction, 24 AWG stranded, red with a black band |
| U1 battery + (J5 BATTERY) | backplane line 19 hole 6 | 100 mm, trim to fit | charger battery + (after the shunt) | charger battery + (J5 BATTERY) to lines 19-20, 24 AWG stranded, red with a black band |
| U1 system out (J3 SYS) | backplane line 26 hole 6 | 100 mm, trim to fit | charger system output (SYS) | charger system output (J3 SYS) to line 26 (B4 pin 26, the regulator in), 24 AWG stranded, red with a black band |
| U1 system ground (J3 GND) | backplane line 12 hole 11 | 100 mm, trim to fit | ground | charger system ground (J3 GND) to line 12 (the bus ground, SYS's return), 24 AWG stranded, black |
| R7 2 | U1 battery sense (J5 SNS_BATP) | 100 mm, trim to fit | charger battery sense (BATP) | charger battery sense (J5 SNS_BATP) from R7's free leg, 24 AWG stranded, white with a red band |

The mux is an Adafruit #5626. Bridge A0 for address 0x71 and set its Vlogic switch SW1 to V+. It sits on a foam pad on the copper side over holes 2-9, below the B4 socket. That keeps it clear of the bus wires, which start at hole 10 or above. Its 5-hole header (VIN, GND, SCL, SDA, RST, at the far end from its upstream QT port) takes five leads to the main bus lines. Channels 0-3 reach sensor ports 1-4 through four Adafruit #4209 QT cables, one plugged into each channel's QT port. Its upstream port and channels 4-7 stay empty, and the sensors take power from their own card ports.

VIN, GND, SCL, SDA and RST are 22 AWG solid insulated hook-up (Adafruit 1311), stripped 3 mm, soldered in from the top face with the tails trimmed flush on the back. Channels 0-3 are the QT ports along the long edge on the same side as the header's VIN end (CONN1, CONN2, CONN5, CONN6; Adafruit's board file, `layout/muxleads.py`). Cut each #4209 cable's male-pin end off at the length in the table, measured from the back of the plug. Strip 3 mm off its blue (SDA) and yellow (SCL) wires. Cut its red (V+) and black (GND) wires off about 3 mm from the plug and tape them; the mux's ground comes through its header lead. Nothing else is soldered to the mux. Stick the back face to the foam, the channel 0-3 edge toward hole 10, and plug the four cables in. The foam goes in the middle, no thicker than 1 mm, so the mux clears the floor. Each cable wire goes into its hole 10. Each header lead rises off the header, runs up past hole 13 on its own line (RST over the mux's top, left of the header; VIN straight up; GND, SCL and SDA past the mux's end), drops onto its own row between the B4 and B2 sockets (holes 14-18, the table) and runs along it to its line, so no lead crosses another (`layout/muxleads.py`, layout check L7). Every one goes in from the copper side and is soldered on the front; the bus wire's joint on the copper side takes it too.

## 6. Fit it in the base (`cage/backplane-mount-spec.md`)

1. With the copper side back and the mux behind it, tilt the board. Push its factory right edge into the right corner post's slot, to the slot's end (Xb 92.30). Its left edge is then clear of the left wall's face. Lower the left side onto the pads, copper face down.
2. Slide it left, flat on the pads, until its left edge is in the left wall's groove and the rail below it (about 2.84 mm). The right edge stays 3.66 mm into the slot. The mux moves with it and clears the pads.
3. There are no screws, because enclosure 4 has no screw posts. The board lies on the support pads under s20.2, s28.16, s24.31. Once the cards are plugged into its sockets, they hold it in place. Until then it's loose, so fit the cards straight after. It comes out the same way, after every card is out.

## 7. Hole by hole

This table has every pad with anything soldered in it. Every other pad stays bare.

| Line | Hole | What is in it | Bus wire |
|---|---|---|---|
| 1 | 13 | XB4 bus 1 | line 1 |
| 1 | 15 | lead to U4 VIN | line 1 |
| 1 | 19 | XB2 bus 1 | line 1 |
| 1 | 27 | XB1 bus 1 | line 1 |
| 1 | 35 | XB3 bus 1 | line 1 |
| 2 | 11 | XJ1 ground | line 2 |
| 2 | 13 | XB4 bus 2 | line 2 |
| 2 | 16 | lead to U4 GND | line 2 |
| 2 | 19 | XB2 bus 2 | line 2 |
| 2 | 27 | XB1 bus 2 | line 2 |
| 2 | 35 | XB3 bus 2 | line 2 |
| 2 | 38 | lead to backplane line 12 hole 38 | line 2 |
| 3 | 10 | lead to U4 CH0 SDA | line 3 |
| 3 | 13 | XB4 bus 3 | line 3 |
| 3 | 19 | XB2 bus 3 | line 3 |
| 3 | 27 | XB1 bus 3 | line 3 |
| 3 | 35 | XB3 bus 3 | line 3 |
| 4 | 10 | lead to U4 CH0 SCL | line 4 |
| 4 | 13 | XB4 bus 4 | line 4 |
| 4 | 19 | XB2 bus 4 | line 4 |
| 4 | 27 | XB1 bus 4 | line 4 |
| 4 | 35 | XB3 bus 4 | line 4 |
| 5 | 13 | XB4 bus 5 | line 5 |
| 5 | 19 | XB2 bus 5 | line 5 |
| 5 | 27 | XB1 bus 5 | line 5 |
| 5 | 35 | XB3 bus 5 | line 5 |
| 6 | 13 | XB4 bus 6 | line 6 |
| 6 | 19 | XB2 bus 6 | line 6 |
| 6 | 27 | XB1 bus 6 | line 6 |
| 6 | 35 | XB3 bus 6 | line 6 |
| 7 | 11 | XJ1 clock | line 7 |
| 7 | 13 | XB4 bus 7 | line 7 |
| 7 | 17 | lead to U4 SCL | line 7 |
| 7 | 19 | XB2 bus 7 | line 7 |
| 7 | 27 | XB1 bus 7 | line 7 |
| 7 | 35 | XB3 bus 7 | line 7 |
| 8 | 10 | lead to U4 CH1 SDA | line 8 |
| 8 | 13 | XB4 bus 8 | line 8 |
| 8 | 19 | XB2 bus 8 | line 8 |
| 8 | 27 | XB1 bus 8 | line 8 |
| 8 | 35 | XB3 bus 8 | line 8 |
| 9 | 10 | lead to U4 CH1 SCL | line 9 |
| 9 | 13 | XB4 bus 9 | line 9 |
| 9 | 19 | XB2 bus 9 | line 9 |
| 9 | 27 | XB1 bus 9 | line 9 |
| 9 | 35 | XB3 bus 9 | line 9 |
| 10 | 11 | XJ1 data | line 10 |
| 10 | 13 | XB4 bus 10 | line 10 |
| 10 | 18 | lead to U4 SDA | line 10 |
| 10 | 19 | XB2 bus 10 | line 10 |
| 10 | 27 | XB1 bus 10 | line 10 |
| 10 | 35 | XB3 bus 10 | line 10 |
| 11 | 13 | XB4 bus 11 | line 11 |
| 11 | 19 | XB2 bus 11 | line 11 |
| 11 | 27 | XB1 bus 11 | line 11 |
| 11 | 35 | XB3 bus 11 | line 11 |
| 12 | 11 | lead to U1 system ground (J3 GND) | line 12 |
| 12 | 13 | XB4 bus 12 | line 12 |
| 12 | 19 | XB2 bus 12 | line 12 |
| 12 | 27 | XB1 bus 12 | line 12 |
| 12 | 35 | XB3 bus 12 | line 12 |
| 12 | 38 | lead to backplane line 2 hole 38 | line 12 |
| 13 | 10 | lead to U4 CH2 SDA | line 13 |
| 13 | 13 | XB4 bus 13 | line 13 |
| 13 | 19 | XB2 bus 13 | line 13 |
| 13 | 27 | XB1 bus 13 | line 13 |
| 13 | 35 | XB3 bus 13 | line 13 |
| 14 | 10 | lead to U4 CH2 SCL | line 14 |
| 14 | 13 | XB4 bus 14 | line 14 |
| 14 | 19 | XB2 bus 14 | line 14 |
| 14 | 27 | XB1 bus 14 | line 14 |
| 14 | 35 | XB3 bus 14 | line 14 |
| 15 | 13 | XB4 bus 15 | line 15 |
| 15 | 14 | lead to U4 RESET | line 15 |
| 15 | 19 | XB2 bus 15 | line 15 |
| 15 | 27 | XB1 bus 15 | line 15 |
| 15 | 35 | XB3 bus 15 | line 15 |
| 16 | 13 | XB4 bus 16 | line 16 |
| 16 | 19 | XB2 bus 16 | line 16 |
| 16 | 27 | XB1 bus 16 | line 16 |
| 16 | 35 | XB3 bus 16 | line 16 |
| 17 | 10 | lead to U4 CH3 SDA | line 17 |
| 17 | 13 | XB4 bus 17 | line 17 |
| 17 | 19 | XB2 bus 17 | line 17 |
| 17 | 27 | XB1 bus 17 | line 17 |
| 17 | 35 | XB3 bus 17 | line 17 |
| 18 | 10 | lead to U4 CH3 SCL | line 18 |
| 18 | 13 | XB4 bus 18 | line 18 |
| 18 | 19 | XB2 bus 18 | line 18 |
| 18 | 27 | XB1 bus 18 | line 18 |
| 18 | 35 | XB3 bus 18 | line 18 |
| 19 | 5 | lead to backplane line 20 hole 5 | line 19 |
| 19 | 6 | lead to U1 battery + (J5 BATTERY) | line 19 |
| 19 | 13 | XB4 power 19 | line 19 |
| 19 | 19 | XB2 spare 19 | - (isolated pad) |
| 19 | 27 | XB1 spare 19 | - (isolated pad) |
| 19 | 35 | XB3 spare 19 | - (isolated pad) |
| 20 | 5 | lead to backplane line 19 hole 5 | line 20 |
| 20 | 13 | XB4 power 20 | line 20 |
| 20 | 19 | XB2 spare 20 | - (isolated pad) |
| 20 | 27 | XB1 spare 20 | - (isolated pad) |
| 20 | 35 | XB3 local 20 (+3V3) | - (isolated pad) |
| 21 | 5 | lead to backplane line 22 hole 5 | line 21 |
| 21 | 6 | lead to F5 lead + | line 21 |
| 21 | 7 | R7 1 | line 21 |
| 21 | 13 | XB4 power 21 | line 21 |
| 21 | 19 | XB2 spare 21 | - (isolated pad) |
| 21 | 27 | XB1 spare 21 | - (isolated pad) |
| 21 | 35 | XB3 local 21 (SWDIO) | - (isolated pad) |
| 22 | 5 | lead to backplane line 21 hole 5 | line 22 |
| 22 | 8 | R8 1 | line 22 |
| 22 | 13 | XB4 power 22 | line 22 |
| 22 | 19 | XB2 spare 22 | - (isolated pad) |
| 22 | 27 | XB1 spare 22 | - (isolated pad) |
| 22 | 35 | XB3 local 22 (SWCLK) | - (isolated pad) |
| 23 | 11 | R8 2 | line 23 |
| 23 | 13 | XB4 power 23 | line 23 |
| 23 | 19 | XB2 spare 23 | - (isolated pad) |
| 23 | 27 | XB1 spare 23 | - (isolated pad) |
| 23 | 35 | XB3 local 23 (NRST) | - (isolated pad) |
| 24 | 7 | R7 2 | - |
| 24 | 13 | XB4 local 24 (+3V3) | - (isolated pad) |
| 24 | 19 | XB2 spare 24 | - (isolated pad) |
| 24 | 27 | XB1 spare 24 | - (isolated pad) |
| 24 | 35 | XB3 local 24 (GND) | - (isolated pad) |
| 25 | 13 | XB4 local 25 (GND) | - (isolated pad) |
| 25 | 19 | XB2 spare 25 | - (isolated pad) |
| 25 | 27 | XB1 spare 25 | - (isolated pad) |
| 25 | 35 | XB3 spare 25 | - (isolated pad) |
| 26 | 6 | lead to U1 system out (J3 SYS) | line 26 |
| 26 | 13 | XB4 power 26 | line 26 |
| 26 | 19 | XB2 spare 26 | - (isolated pad) |
| 26 | 27 | XB1 spare 26 | - (isolated pad) |
| 26 | 35 | XB3 local 26 (MUX_RST) | - (isolated pad) |
| 27 | 13 | XB4 spare 27 | - (isolated pad) |
| 27 | 19 | XB2 spare 27 | - (isolated pad) |
| 27 | 27 | XB1 key plug 27 | - (isolated pad) |
| 27 | 35 | XB3 spare 27 | - (isolated pad) |
| 28 | 13 | XB4 spare 28 | - (isolated pad) |
| 28 | 19 | XB2 key plug 28 | - (isolated pad) |
| 28 | 27 | XB1 spare 28 | - (isolated pad) |
| 28 | 35 | XB3 spare 28 | - (isolated pad) |
| 29 | 13 | XB4 spare 29 | - (isolated pad) |
| 29 | 19 | XB2 spare 29 | - (isolated pad) |
| 29 | 27 | XB1 spare 29 | - (isolated pad) |
| 29 | 35 | XB3 key plug 29 | - (isolated pad) |
| 30 | 13 | XB4 key plug 30 | - (isolated pad) |
| 30 | 19 | XB2 spare 30 | - (isolated pad) |
| 30 | 27 | XB1 spare 30 | - (isolated pad) |
| 30 | 35 | XB3 spare 30 | - (isolated pad) |

## Before power

- Each bus line to its neighbours: open, except 19-20 and 21-22, which are closed (joined at hole 5), and 22-23, which reads about 100 ohm through R8. Line 2 to line 12: closed (both ground, joined at hole 38).
- 3.3 V supply (line 1) to ground (line 2): open.
- Lines 19-30: each B4 contact on lines 19-23 and 26 beeps to its line's bus wire (19 to 20, 21 to 22). Every other contact on lines 19-30 (the isolated pads, the key plugs' included) beeps to nothing: not its line's wire, not its neighbours.
- The charger ground lead's EVM end (J3 GND) beeps to line 12 and line 2.
- Each bus wire: continuity from its first to its last soldered hole.
