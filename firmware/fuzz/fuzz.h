#ifndef FUZZ_H
#define FUZZ_H
/* Host fuzz targets for the code that parses input from outside the node: radio replies, the
 * provisioning command and console lines. Each target is a libFuzzer entry point; standalone.c
 * drives the same entry point without libFuzzer (Apple clang does not ship it). README.md here. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
/* The protocol's numbers as docs/protocol-draft5-design.md states them, written out here on
 * purpose instead of taken from ws_frame.h or ws_obs.h: an oracle that reused those headers would
 * share any mistake in them. */
#define SPEC_BYTE0(kind)    (0x50U | (kind))   /* version 5 in the high nibble, kind in the low */
#define SPEC_KIND_MASK      0x0FU
#define SPEC_KIND_MAX       4U
#define SPEC_STATION_MAX    0xFFFFU            /* u16 */
#define SPEC_STATION_AT     1
#define SPEC_STATION_BYTES  2
#define SPEC_COUNTER_AT     3
#define SPEC_COUNTER_BYTES  5
#define SPEC_U32            4
#define SPEC_OBS_FLAGS_AT   16                 /* bit 0: UTC known; bits 1-2: energy state */
#define SPEC_OBS_FLAG_UTC   0x01U
#define SPEC_OBS_ENERGY_SHIFT 1
#define SPEC_OBS_CAL_AT     17
#define SPEC_OBS_BITMAP_AT  18
#define SPEC_OBS_FRAME_MIN  39                 /* 16 overhead + 22 header + a 1-byte field */
#define SPEC_OBS_FRAME_MAX  94                 /* 16 overhead + 78 (every catalog field) */
#define SPEC_DIAG_FRAME_LEN 48                 /* 16 overhead + 32 */
#define SPEC_KEY_HEX_DIGITS 32
#define SPEC_HEX_PER_BYTE   2
#define SPEC_NIBBLE_BITS    4
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);
/* A broken property is a bug: report it and abort, so both drivers keep the input. */
#define FUZZ_CHECK(cond) do { if (!(cond)) { fprintf(stderr, "property failed: %s (%s:%d)\n", #cond, __FILE__, __LINE__); abort(); } } while (0)
#endif
