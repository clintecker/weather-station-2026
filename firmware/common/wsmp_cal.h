#ifndef WSMP_CAL_H
#define WSMP_CAL_H
/* Module record calibration (docs/firmware-current-design.md section
 * 6.9; firmware/common/wsmp_cal.lit.md): check 7 against the frozen table of record major 1, the
 * entry for a channel, v' = ws_div_round(v x gain, 10^6) + offset in int64, and the crop and range
 * check of a port module's channel. Portable C: no HAL, no heap, no state. */
#include <stdint.h>
#include "wsmp.h"

#define WSMP_CAL_UNITY 1000000L   /* a gain of 1, in ppm */

/* Check 7, strict at any minor: WSMP_REC_APPLIED, or WSMP_REC_CAL_REJECTED for a used entry whose
   quantity is not in the table, whose (quantity, kind) matches no channel of the module type (kind 0:
   any channel of the quantity), whose revision is 0, or whose offset or gain is outside the table's
   bounds, or for two entries with the same (quantity, kind). r passed wsmp_record_parse. */
uint8_t wsmp_cal_check(const wsmp_record *r);
/* The entry for a channel (quantity, kind) of an applied record: (quantity, kind) wins over
   (quantity, 0). NULL: the channel is reported uncorrected, calibration revision 0. */
const wsmp_cal_entry *wsmp_cal_find(const wsmp_record *r, uint16_t quantity, uint8_t kind);
/* raw x gain / 10^6, rounded half up, plus the offset; raw itself for e NULL. e passed check 7. */
int64_t wsmp_cal_apply(const wsmp_cal_entry *e, int32_t raw);
/* Crop v into the quantity's physical range: *out is v, or the physical limit for a v within the crop
   margin. Returns WSMP_QUAL_GOOD, or WSMP_QUAL_SUSPECT beyond the margin (keep it out of the window
   sum). A quantity outside the table has no crop: only the int32 range. */
uint8_t wsmp_cal_crop(uint16_t quantity, int64_t v, int32_t *out);
/* One sample of a port-module channel, in the spec's order: raw, calibration (applied is NULL unless
   the record status is WSMP_REC_APPLIED), then the crop. Returns the sample's quality as wsmp_cal_crop. */
uint8_t wsmp_cal_sample(const wsmp_record *applied, uint16_t quantity, uint8_t kind, int32_t raw, int32_t *out);
#endif
