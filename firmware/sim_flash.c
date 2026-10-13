/* Host RAM model of STM32WL55 flash with power-cut injection; see sim_flash.h. */
#include "sim_flash.h"
#include <stdio.h>
#include <string.h>

#define ERASED UINT64_MAX

void sim_flash_reset(sim_flash *s) {
 uint8_t *kinds = s->kinds; uint64_t cap = s->kinds_cap; void (*hook)(void) = s->on_fault;
 memset(s, 0, sizeof *s);
 memset(s->mem, 0xFF, sizeof s->mem);
 s->cut_at = SIM_NEVER; s->fail_at = SIM_NEVER;
 s->kinds = kinds; s->kinds_cap = cap; s->on_fault = hook;
}

int sim_flash_variants(int kind) { return kind == SIM_OP_PROG ? SIM_PROG_VARIANTS : SIM_ERASE_VARIANTS; }

static void violation(sim_flash *s, const char *what, uint32_t a) {
 s->violations++;
 snprintf(s->last_violation, sizeof s->last_violation, "%s at 0x%08lx (op %llu)", what,
          (unsigned long)a, (unsigned long long)s->ops);
}

/* Maps an absolute address to the double-word it names; NULL (and a violation) when outside
   the modelled pages or not 8-byte aligned. */
static int locate(sim_flash *s, uint32_t addr, uint32_t *pg, uint32_t *dw) {
 uint32_t lo = WS_PAGE_ADDR(SIM_FIRST_PAGE), hi = WS_PAGE_ADDR(SIM_FIRST_PAGE + SIM_PAGES);
 if (addr < lo || addr >= hi || (addr & 7U)) { violation(s, "bad address", addr); return -1; }
 *pg = (addr - lo) / WS_PAGE_SIZE; *dw = (addr - lo) % WS_PAGE_SIZE / 8U;
 return 0;
}

static uint32_t rnd(uint32_t *x) { *x ^= *x << 13; *x ^= *x >> 17; *x ^= *x << 5; return *x; }

/* Counts the op; returns 1 when it must fail without effect, longjmps on a cut (after the
   caller-specific damage has been applied by 'cut'), 0 to proceed normally. */
static int begin_op(sim_flash *s, int kind) {
 uint64_t n = s->ops++;
 if (s->kinds && n < s->kinds_cap) s->kinds[n] = (uint8_t)kind;
 if (n != s->fail_at && n != s->cut_at) return 0;
 if (s->on_fault) s->on_fault();
 return n == s->fail_at ? 1 : 2;
}

/* What an interrupted erase of page index p leaves behind (SIM_ERASE_* variant v). */
static void partial_erase(sim_flash *s, uint32_t p, int v) {
 uint32_t x = s->seed * 2654435761U + 0x9E3779B9U + (uint32_t)v;
 for (uint32_t i = 0; i < SIM_DW_PER_PAGE; i++) {
  uint32_t r = rnd(&x) >> 8;
  int erase = v == SIM_ERASE_ALL || ((v == SIM_ERASE_RANDOM_A || v == SIM_ERASE_RANDOM_B) && (r & 1)) ||
              (v == SIM_ERASE_RANDOM_ECC && r % 3 == 0);
  if (erase) { s->mem[p][i] = ERASED; s->ecc[p][i] = 0; }
  else if (v == SIM_ERASE_RANDOM_ECC && r % 3 == 1 && s->mem[p][i] != ERASED) s->ecc[p][i] = 1;
 }
}

int sim_flash_read64(void *ctx, uint32_t addr, uint64_t *out) {
 sim_flash *s = ctx; uint32_t pg, dw;
 if (locate(s, addr, &pg, &dw)) { *out = 0; return -1; }
 if (s->ecc[pg][dw]) { s->ecc_reads++; *out = 0; return -1; }
 *out = s->mem[pg][dw];
 return 0;
}

int sim_flash_prog64(void *ctx, uint32_t addr, uint64_t value) {
 sim_flash *s = ctx; uint32_t pg, dw; int b = begin_op(s, SIM_OP_PROG);
 if (locate(s, addr, &pg, &dw)) return -1;
 int overwrite = s->mem[pg][dw] != ERASED || s->ecc[pg][dw];
 if (overwrite && value) { violation(s, "program over non-erased double-word", addr); return -1; }
 if (b == 1) {
  if (s->fail_variant == SIM_FAIL_DAMAGED) { s->mem[pg][dw] = value | 0x5555555555555555ULL; s->ecc[pg][dw] = 1; }
  return -1;
 }
 if (b == 2) {
  s->cut_kind = SIM_OP_PROG; s->cut_addr = addr;
  if (s->cut_variant == SIM_PROG_NEW) { s->mem[pg][dw] = value; s->ecc[pg][dw] = 0; }
  else if (s->cut_variant == SIM_PROG_TORN) { s->mem[pg][dw] = value | 0x5555555555555555ULL; s->ecc[pg][dw] = 1; }
  longjmp(*s->cut_jump, 1);
 }
 if (overwrite) { s->zero_overwrites++; s->ecc[pg][dw] = 0; }
 s->mem[pg][dw] = value; s->progs++;
 return 0;
}

int sim_flash_erase(void *ctx, uint32_t page) {
 sim_flash *s = ctx; int b = begin_op(s, SIM_OP_ERASE);
 if (page < SIM_FIRST_PAGE || page >= SIM_FIRST_PAGE + SIM_PAGES) { violation(s, "bad page", page); return -1; }
 uint32_t p = page - SIM_FIRST_PAGE;
 if (b == 1) {
  if (s->fail_variant == SIM_FAIL_DAMAGED) partial_erase(s, p, SIM_ERASE_RANDOM_ECC);
  return -1;
 }
 if (b == 2) {
  s->cut_kind = SIM_OP_ERASE; s->cut_addr = page;
  partial_erase(s, p, s->cut_variant);
  longjmp(*s->cut_jump, 1);
 }
 memset(s->mem[p], 0xFF, sizeof s->mem[p]); memset(s->ecc[p], 0, sizeof s->ecc[p]);
 s->erases++; s->page_erases[p]++;
 return 0;
}
