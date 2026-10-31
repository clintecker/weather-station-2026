#ifndef WS_FRAME_H
#define WS_FRAME_H
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
/* Frame envelope, protocol version 6 (docs/protocol-design.md sections 3-4); AES-128-CCM via Mbed TLS.
 * The gateway (ws0/protocol.py) builds the same bytes, checked by tests/test_frame.py. */
/* Version 6: catalog v2 observations and the 64-byte health report (power telemetry design
 * section 4). Byte 0 is 0x61-0x64. The TX and RX roles and the gateway must all match. */
#define WS_FRAME_VERSION 6
#define WS_KIND_OBS 1
#define WS_KIND_ACK 2
#define WS_KIND_NACK 3 /* authentic but permanently rejected */
#define WS_KIND_DIAG 4 /* node health, fire-and-forget */
#define WS_NACK_COLLISION 1
#define WS_NACK_INVALID 2
/* Header: one byte version (high nibble) and kind (low nibble), station u16, counter u40. */
#define WS_VERSION_SHIFT 4
#define WS_KIND_MASK 0x0FU
#define WS_STATION_BYTES 2
#define WS_COUNTER_BYTES 5
#define WS_COUNTER_OFF (1 + WS_STATION_BYTES)   /* everything before it: version, kind, station */
#define WS_HEADER_LEN (WS_COUNTER_OFF + WS_COUNTER_BYTES)
#define WS_KEY_LEN 16            /* AES-128 */
#define WS_KCV_LEN 3             /* key check value (ws_key_check) */
#define WS_TAG_LEN 8             /* CCM M = 8, fixed (section 3.3) */
#define WS_FRAME_OVERHEAD (WS_HEADER_LEN + WS_TAG_LEN)
#define WS_STATION_MAX UINT16_MAX
#define WS_COUNTER_MAX ((1ULL << (WS_COUNTER_BYTES * CHAR_BIT)) - 1U)   /* 2^40 - 1 */
#define WS_REPLY_PLAIN_LEN (3 * 4 + WS_COUNTER_BYTES)   /* ACK/NACK: epoch u32, seq u32, UTC or reason u32, echo u40 */
#define WS_ACK_FRAME_LEN (WS_FRAME_OVERHEAD + WS_REPLY_PLAIN_LEN)
#define WS_FRAME_MAX 255U        /* a LoRa payload */
#define WS_DIAG_PLAIN_LEN 64     /* health report, fixed length (section 4; power telemetry design 6.1) */
#define WS_DIAG_FRAME_LEN (WS_FRAME_OVERHEAD + WS_DIAG_PLAIN_LEN)
#define WS_FRAME_BYTE0(kind) ((uint8_t)((WS_FRAME_VERSION << WS_VERSION_SHIFT) | (kind)))
_Static_assert(WS_HEADER_LEN == 8 && WS_TAG_LEN == 8, "the header and the CCM tag are 8 bytes");
_Static_assert(WS_ACK_FRAME_LEN == 33, "ACK and NACK frames are 33 bytes");
_Static_assert(WS_COUNTER_MAX == 0xFFFFFFFFFFULL, "the counter is 40 bits");
_Static_assert(WS_DIAG_FRAME_LEN == 80, "a health report frame is 80 bytes");

/* Return codes of ws_seal_kind (negative) and ws_open_reply. */
enum {
 WS_FRAME_OK = 0,
 WS_FRAME_EINVAL = -1,   /* bad argument: length, station, counter, kind, or no output buffer */
 WS_FRAME_EHEADER = -2,  /* a reply of another version, kind or station */
 WS_FRAME_EAUTH = -3,    /* the tag does not verify */
 WS_FRAME_ECRYPTO = -4,  /* Mbed TLS failed while sealing */
};
/* Seal one node-to-gateway or gateway-to-node frame. The caller reserves counter durably first;
 * it must never repeat for this key. Returns the frame length (plain_len + WS_FRAME_OVERHEAD), or a negative
 * value, with out zeroized, if: station is 0 or above WS_STATION_MAX, counter is 0 or above
 * WS_COUNTER_MAX (the 5-byte header field would truncate it and repeat a nonce), kind is not 1-4,
 * the frame would exceed out_cap or WS_FRAME_MAX, or the cipher fails. */
int ws_seal_kind(const uint8_t key[WS_KEY_LEN], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t *plain, uint32_t plain_len, uint8_t *out, uint32_t out_cap);
/* Open an ACK (kind 2) or NACK (kind 3). word = UTC for an ACK, the reason for a NACK.
 * 0 on success; nonzero for a wrong length, version, kind or station, or a failed tag. */
int ws_open_reply(const uint8_t key[WS_KEY_LEN], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo);
/* Kind of a frame of this version (1-15), or -1 if it is empty or another version. Inline: the
 * keyless RX bridge uses it without linking the crypto code. */
static inline int ws_frame_kind(const uint8_t *frame, uint32_t len) {
 if(!frame || len<1 || (frame[0]>>WS_VERSION_SHIFT)!=WS_FRAME_VERSION) return -1;
 return frame[0]&WS_KIND_MASK;
}
/* Health report plaintext (kind 4, docs/protocol-design.md section 4; power telemetry design
 * section 6.1). It matches ws0/protocol.py DIAG; tests/test_frame.py checks it byte for byte.
 * The caller clamps the counts (16-bit counts saturate at 0xFFFF) and puts a none code in every
 * slot that its build or phase cannot fill. Members are grouped by width (no padding); the wire
 * order is ws_diag_pack's. */
typedef struct {
 uint32_t epoch, uptime, lost, build;               /* build: first 4 bytes of the release commit */
 uint32_t crash_pc;                                 /* PC of the last crash since power-up; WS_CRASH_PC_NONE = none,
                                                       0xFFFFFFFF = the stacked frame was not trusted */
 uint16_t pending, torn, abandoned, no_ack, rejects;
 uint16_t boots, tx_timeouts, i2c_recoveries;       /* boots since power-up; TX timeouts and I2C recoveries since boot */
 uint16_t vdda_mv;                                  /* MCU supply (VDDA via VREFINT), mV; WS_U16_NONE */
 uint16_t soc;                                      /* gauge SOC, 1/256 %; WS_U16_NONE */
 uint16_t chg_input_mv, chg_batt_mv;                /* charger-reported input and battery voltage, mV; WS_U16_NONE */
 int16_t monitor_temp;                              /* hottest power-monitor die, 0.1 C; WS_I16_NONE */
 int16_t soc_rate;                                  /* gauge SOC rate, 0.1 %/h, + while charging; WS_I16_NONE */
 int16_t chg_input_ma, chg_batt_ma;                 /* charger-reported input and charge current, 1 mA; WS_I16_NONE */
 int16_t chg_temp, pack_temp;                       /* charger die and pack temperature, 0.1 C; WS_I16_NONE */
 uint8_t reset_cause, link, crashes, energy;
 uint8_t charger_status;                            /* WS_CHG_* bits below; WS_CHARGER_NONE = no status */
 uint8_t fitted;                                    /* byte 51: WS_FIT_* bits below, the sources this build has */
 int8_t rssi, snr;                                  /* last authentic ACK as heard; WS_SIGNAL_NONE = none yet */
} ws_diag_t;
#define WS_SIGNAL_NONE INT8_MIN
/* None codes: the slot has no value. The fitted byte (WS_FIT_*) tells why: its bit clear, this build or
 * phase has no source for the slot (not measured); its bit set, the fitted source failed (a fault). */
#define WS_U16_NONE UINT16_MAX
#define WS_I16_NONE INT16_MIN
#define WS_CHARGER_NONE 0xFFU
#define WS_CRASH_PC_NONE 0U
/* Charger status byte (power telemetry design section 6.3). A byte other than WS_CHARGER_NONE with
 * stage 7 is not canonical: the node never sends it. Every active input code (0-3) is canonical. */
#define WS_CHG_POWER_GOOD 0x01U          /* bit 0: input power good */
#define WS_CHG_CHARGING 0x02U            /* bit 1: charging */
#define WS_CHG_FAULT 0x04U               /* bit 2: fault */
#define WS_CHG_STAGE_SHIFT 3
#define WS_CHG_STAGE_MASK 0x38U          /* bits 3-5 */
#define WS_CHG_STAGE_NONE 0U             /* not reported (phase A: the pins cannot tell) */
#define WS_CHG_STAGE_PRECHARGE 1U        /* pre-charge or trickle */
#define WS_CHG_STAGE_CC 2U
#define WS_CHG_STAGE_CV 3U
#define WS_CHG_STAGE_TOPOFF 4U
#define WS_CHG_STAGE_TERMINATED 5U
#define WS_CHG_STAGE_NOT_CHARGING 6U
#define WS_CHG_STAGE_RESERVED 7U         /* not canonical */
#define WS_CHG_INPUT_SHIFT 6
#define WS_CHG_INPUT_MASK 0xC0U          /* bits 6-7: active input */
#define WS_CHG_INPUT_NOT_REPORTED 0U     /* not reported (phases A and B: one VBUS input) */
#define WS_CHG_INPUT_SOLAR 1U            /* VAC1 */
#define WS_CHG_INPUT_USB_C 2U            /* VAC2 */
#define WS_CHG_INPUT_NO_INPUT 3U         /* the charger reports no input: both source rails 0 mA */
#define WS_CHG_STAGE(s) ((uint8_t)(((s) << WS_CHG_STAGE_SHIFT) & WS_CHG_STAGE_MASK))
#define WS_CHG_INPUT(i) ((uint8_t)(((i) << WS_CHG_INPUT_SHIFT) & WS_CHG_INPUT_MASK))
/* Fitted byte (byte 51, power telemetry design section 6.1): bit set = this build has a source for the
 * slots named; a none code in such a slot is then a fault, not "not measured". Bit 7 is reserved and
 * not canonical: ws_diag_pack writes fitted & WS_FIT_DEFINED. */
#define WS_FIT_MCU_SUPPLY 0x01U          /* vdda_mv */
#define WS_FIT_MONITOR_TEMP 0x02U        /* monitor_temp */
#define WS_FIT_GAUGE 0x04U               /* soc, soc_rate */
#define WS_FIT_CHARGER_STATUS 0x08U      /* charger_status bits 0-2: power good, charging, fault */
#define WS_FIT_CHARGER_REGS 0x10U        /* charger_status stage and input, chg_input_mv/ma, chg_batt_mv, chg_temp */
#define WS_FIT_CHARGE_CURRENT 0x20U      /* chg_batt_ma */
#define WS_FIT_PACK_TEMP 0x40U           /* pack_temp */
#define WS_FIT_DEFINED 0x7FU
void ws_diag_pack(const ws_diag_t *d, uint8_t out[WS_DIAG_PLAIN_LEN]);
/* Key check value: first 3 bytes of AES-ECB(key, zero block); safe to display. */
int ws_key_check(const uint8_t key[WS_KEY_LEN], uint8_t out[WS_KCV_LEN]);
/* Zero key material. A plain memset of a buffer that is not read again is a dead store the
   compiler may delete; writes through a volatile pointer are kept. */
static inline void ws_wipe(void *p, size_t n)
{ volatile uint8_t *v = (volatile uint8_t *)p; while (n--) *v++ = 0; }   /* bound: n bytes */
#endif
