/* PROVISION arguments as typed on the TX console (ws_parse_provision, firmware/stage0.c).
 * Properties: no memory error; on success the station is 1-65535, the epoch floor is in range,
 * and the 32 key digits at offset (station digits + 1) decode to exactly the key returned. */
#include <ctype.h>
#include <string.h>
#include "fuzz.h"
#include "stage0.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
 char text[300]; uint32_t station, floor; uint8_t key[16];
 if (size >= sizeof text) return 0;
 memcpy(text, data, size); text[size] = 0;  /* the console hands over a NUL-terminated line */
 if (ws_parse_provision(text, &station, key, &floor)) return 0;
 FUZZ_CHECK(station != 0 && station <= 65535U && floor < WS_EPOCH_FLOOR_MAX);   /* draft 5: u16 station */
 size_t digits = strspn(text, "0123456789");
 FUZZ_CHECK(digits >= 1 && text[digits] == ' ');
 for (int i = 0; i < 32; i++) {
  char c = text[digits + 1 + (size_t)i];
  FUZZ_CHECK(isxdigit((unsigned char)c));
  int v = isdigit((unsigned char)c) ? c - '0' : tolower((unsigned char)c) - 'a' + 10;
  FUZZ_CHECK(v == (i % 2 ? key[i / 2] & 15 : key[i / 2] >> 4));
 }
 const char *rest = text + digits + 33;
 FUZZ_CHECK(*rest == 0 || (*rest == ' ' && strspn(rest + 1, "0123456789") == strlen(rest + 1) && rest[1]));
 return 0;
}
