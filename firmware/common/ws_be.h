#ifndef WS_BE_H
#define WS_BE_H
#include <stdint.h>
/* Big-endian (network order) integers, the byte order of every frame, plaintext and journal record
 * field. The fixed-width forms are written so GCC turns them into one load or store plus a byte
 * swap; the n-byte forms serve the catalog's 1-4 byte fields (ws_put_be) and the 5-byte counter
 * (the 64-bit pair, n <= 8), kept apart so 32-bit callers need no 64-bit shifts. */
static inline void ws_put_be16(uint8_t *p, uint16_t v)
{
 p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v;
}
static inline void ws_put_be32(uint8_t *p, uint32_t v)
{
 p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static inline uint32_t ws_get_be32(const uint8_t *p)
{
 return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
static inline void ws_put_be(uint8_t *p, uint32_t v, unsigned n) /* n <= 4 */
{
 for (unsigned k = 0; k < n; k++) p[k] = (uint8_t)(v >> (8U * (n - 1U - k)));
}
static inline void ws_put_be64(uint8_t *p, uint64_t v, unsigned n) /* n <= 8 */
{
 for (unsigned k = 0; k < n; k++) p[k] = (uint8_t)(v >> (8U * (n - 1U - k)));
}
static inline uint64_t ws_get_be64(const uint8_t *p, unsigned n) /* n <= 8 */
{
 uint64_t v = 0;
 for (unsigned k = 0; k < n; k++) v = v << 8 | p[k];
 return v;
}
/* Cursor forms: each reads or writes the field at p and returns p just past it (p = ws_write_be32(p,
 * v)), so a record's layout is the order of the calls, as in ws0/protocol.py's struct formats, and
 * no offset is written out. One level of indirection (docs/power-of-ten.md rule 9). */
static inline uint8_t *ws_write_u8(uint8_t *p, uint8_t v) { *p = v; return p + sizeof v; }
static inline uint8_t *ws_write_be16(uint8_t *p, uint16_t v) { ws_put_be16(p, v); return p + sizeof v; }
static inline uint8_t *ws_write_be32(uint8_t *p, uint32_t v) { ws_put_be32(p, v); return p + sizeof v; }
static inline uint8_t *ws_write_be(uint8_t *p, uint64_t v, unsigned n) { ws_put_be64(p, v, n); return p + n; }   /* n <= 8 */
static inline const uint8_t *ws_read_be32(const uint8_t *p, uint32_t *v) { *v = ws_get_be32(p); return p + sizeof *v; }
static inline const uint8_t *ws_read_be(const uint8_t *p, uint64_t *v, unsigned n) { *v = ws_get_be64(p, n); return p + n; }   /* n <= 8 */
#endif
