/* Drives a libFuzzer entry point without libFuzzer: runs every corpus file given on the command
 * line, then -runs=N mutated inputs from a fixed seed (-seed=S), so a failure reproduces exactly.
 * Mutations: bit flips, byte overwrites with interesting values, inserts, deletes, truncation,
 * self-copies of a slice, repeated bytes, and splices of corpus entries. Build with -fsanitize=address,undefined (see Makefile). */
#include <string.h>
#include "fuzz.h"

#define MAX_INPUT 512
#define MAX_SEEDS 64
static uint8_t seeds[MAX_SEEDS][MAX_INPUT];
static size_t seed_len[MAX_SEEDS];
static int n_seeds;
static uint64_t rng = 0x9E3779B97F4A7C15ull;

static uint64_t next(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return rng; }
static size_t below(size_t n) { return n ? (size_t)(next() % n) : 0; }

static int run_file(const char *path)
{
 FILE *f = fopen(path, "rb");
 if (!f) { perror(path); return 1; }
 uint8_t buf[MAX_INPUT]; size_t n = fread(buf, 1, sizeof buf, f); fclose(f);
 LLVMFuzzerTestOneInput(buf, n);
 if (n_seeds < MAX_SEEDS) { memcpy(seeds[n_seeds], buf, n); seed_len[n_seeds++] = n; }
 return 0;
}

static size_t mutate(uint8_t *buf, size_t n)
{
 static const uint8_t special[] = { 0, 1, 0x7f, 0x80, 0xff, '\n', '\r', ' ', '0', '9', 'a', 'f', 'F', 'g', 'W', 'S', 4 };
 int steps = 1 + (int)below(4);
 for (int s = 0; s < steps; s++) {
  switch (below(9)) {
  case 0: if (n) buf[below(n)] ^= (uint8_t)(1u << below(8)); break;
  case 1: if (n) buf[below(n)] = special[below(sizeof special)]; break;
  case 2: if (n) buf[below(n)] = (uint8_t)next(); break;
  case 3: if (n < MAX_INPUT) { size_t at = below(n + 1); memmove(buf + at + 1, buf + at, n - at); buf[at] = special[below(sizeof special)]; n++; } break;
  case 4: if (n) { size_t at = below(n); memmove(buf + at, buf + at + 1, n - at - 1); n--; } break;
  case 5: n = below(n + 1); break;
  case 6: if (n) { /* insert a copy of a slice of the input: grows a hex line without breaking it */
            size_t from = below(n), len = 1 + below(n - from), at = below(n + 1);
            if (n + len > MAX_INPUT) len = MAX_INPUT - n;
            uint8_t tmp[MAX_INPUT]; memcpy(tmp, buf + from, len);
            memmove(buf + at + len, buf + at, n - at); memcpy(buf + at, tmp, len); n += len; } break;
  case 7: if (n && n < MAX_INPUT) { /* repeat one byte up to 16 times */
            size_t at = below(n), len = 1 + below(16);
            if (n + len > MAX_INPUT) len = MAX_INPUT - n;
            memmove(buf + at + len, buf + at, n - at); memset(buf + at, buf[at + len], len); n += len; } break;
  default: if (n_seeds) { /* overwrite part of the input with a corpus entry */
            int k = (int)below((size_t)n_seeds);
            size_t at = below(n + 1), take = below(seed_len[k] + 1);
            if (at + take > MAX_INPUT) take = MAX_INPUT - at;
            memcpy(buf + at, seeds[k], take);
            if (at + take > n) n = at + take; } break;
  }
 }
 return n;
}

int main(int argc, char **argv)
{
 long runs = 0;
 for (int i = 1; i < argc; i++) {
  if (!strncmp(argv[i], "-runs=", 6)) runs = atol(argv[i] + 6);
  else if (!strncmp(argv[i], "-seed=", 6)) rng = strtoull(argv[i] + 6, NULL, 0) | 1u;
  else if (run_file(argv[i])) return 1;
 }
 uint8_t buf[MAX_INPUT];
 for (long r = 0; r < runs; r++) {
  size_t n;
  if (n_seeds && below(8)) { int k = (int)below((size_t)n_seeds); memcpy(buf, seeds[k], seed_len[k]); n = seed_len[k]; }
  else { n = below(MAX_INPUT + 1); for (size_t i = 0; i < n; i++) buf[i] = (uint8_t)next(); }
  n = mutate(buf, n);
  LLVMFuzzerTestOneInput(buf, n);
 }
 printf("fuzz ok: %d corpus files, %ld mutated runs\n", n_seeds, runs);
 return 0;
}
