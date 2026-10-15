#include "stage0.h"
#include <string.h>
#include "common/ws_console.h"   /* ws_hex_nibble */
/* Sensirion polynomial 0x31, initial FF, no final XOR. */
uint8_t ws_crc8(const uint8_t *data, size_t count) {
 uint8_t crc=0xff;
 for(size_t i=0;i<count;i++) {
  crc^=data[i];
  for(unsigned bit=0;bit<8;bit++) crc=(uint8_t)((crc&0x80)?(crc<<1)^0x31:crc<<1);
 }
 return crc;
}
int ws_sht45_parse(const uint8_t bytes[WS_SHT45_REPLY_LEN],int16_t *centi_c,uint16_t *centi_rh) {
 if(ws_crc8(bytes,2)!=bytes[2]||ws_crc8(bytes+3,2)!=bytes[5]) return -4;
 uint32_t rt=((uint32_t)bytes[0]<<8)|bytes[1], rh=((uint32_t)bytes[3]<<8)|bytes[4];
 int32_t t=-4500+(int32_t)((17500*rt+32767)/65535);
 int32_t h=-600+(int32_t)((12500*rh+32767)/65535);
 if(h<0) h=0;
 if(h>10000) h=10000;
 *centi_c=(int16_t)t; *centi_rh=(uint16_t)h;
 return 0; /* Outputs are unchanged on failure; caller must emit invalid flags. */
}
/* Explicit packing avoids structure padding and alignment assumptions. */
void ws_th_reset(ws_th_window *w) { memset(w,0,sizeof *w); }
static void th_extrema(ws_th_window *w,int16_t t,uint16_t h) {
 if(!w->n) { w->t_min=w->t_max=t; w->h_min=w->h_max=h; return; }
 if(t<w->t_min) w->t_min=t;
 if(t>w->t_max) w->t_max=t;
 if(h<w->h_min) w->h_min=h;
 if(h>w->h_max) w->h_max=h;
}
void ws_th_add(ws_th_window *w,int valid,int16_t t,uint16_t h) {
 if(!valid||t<-4000||t>12500||w->n>=255) return;
 if(h>10000) h=10000;
 th_extrema(w,t,h);
 w->t_sum+=t; w->h_sum+=h; w->n++;
}
/* floor((2*sum + n) / (2n)): round half up, also for negative sums (C division truncates, and
 * den > 0, so a negative inexact quotient is one too high). 32-bit arithmetic: ws_th_add counts at
 * most 255 samples of -4000..12500 (T) or 0..10000 (RH), so |2*sum + n| stays far below 2^31. */
_Static_assert(2LL*255*12500+255 < INT32_MAX && 2LL*255*-4000 > INT32_MIN,"T/RH window sums fit 32-bit mean arithmetic");
static int32_t mean_half_up(int32_t sum,uint8_t n) {
 int32_t num=2*sum+n, den=2*(int32_t)n, q=num/den;
 if(num%den!=0&&num<0) q--;
 return q;
}
int ws_th_mean_t(const ws_th_window *w,int16_t *t) { if(!w->n) return 0; *t=(int16_t)mean_half_up(w->t_sum,w->n); return 1; }
int ws_th_mean_h(const ws_th_window *w,uint16_t *h) { if(!w->n) return 0; *h=(uint16_t)mean_half_up(w->h_sum,w->n); return 1; }
/* One step per half period of 100 kHz SCL; the caller waits >= WS_I2C_HALF_US between steps. */
enum { REC_CHECK, REC_HIGH, REC_STOP_SDA_LOW, REC_STOP_SCL_HIGH, REC_STOP_SDA_HIGH, REC_DONE };
void ws_i2c_recover_begin(ws_i2c_rec *s,const ws_i2c_pins *p) {
 s->phase=REC_CHECK; s->pulses=0; s->held=0;
 p->set_sda(p->context,1); p->set_scl(p->context,1);
}
int ws_i2c_recover_step(ws_i2c_rec *s,const ws_i2c_pins *p) {
 switch(s->phase) {
  case REC_CHECK:
   if(s->pulses<9&&!p->read_sda(p->context)) { p->set_scl(p->context,0); s->phase=REC_HIGH; return 1; }
   s->held=!p->read_sda(p->context);
   p->set_scl(p->context,0); s->phase=REC_STOP_SDA_LOW; return 1;   /* STOP */
  case REC_HIGH: p->set_scl(p->context,1); s->pulses++; s->phase=REC_CHECK; return 1;
  case REC_STOP_SDA_LOW: p->set_sda(p->context,0); s->phase=REC_STOP_SCL_HIGH; return 1;
  case REC_STOP_SCL_HIGH: p->set_scl(p->context,1); s->phase=REC_STOP_SDA_HIGH; return 1;
  case REC_STOP_SDA_HIGH: p->set_sda(p->context,1); s->phase=REC_DONE; return 1;
  default: return s->held?-1:0;
 }
}
int ws_i2c_recover(const ws_i2c_pins *p) {
 ws_i2c_rec s;
 ws_i2c_recover_begin(&s,p); p->wait_us(p->context,WS_I2C_HALF_US);
 for(int k=0;k<WS_I2C_RECOVER_STEPS;k++) {
  int rc=ws_i2c_recover_step(&s,p);
  if(rc<=0) return rc;
  p->wait_us(p->context,WS_I2C_HALF_US);
 }
 return -1; /* not reached: the sequence ends within WS_I2C_RECOVER_STEPS steps */
}
int ws_link_may_send(int energy,int probing,int32_t secs_until_probe) {
 if(energy>=3) return 0;
 if(!probing||energy<=1) return 1;
 return secs_until_probe<=0;
}
/* Each parser returns the text just past what it read, or NULL if the text does not parse (one level
   of indirection: no pointer to the cursor, docs/power-of-ten.md rule 9). */
static const char *parse_u32(const char *p,uint32_t *out) {
 uint64_t v=0;
 if(*p<'0'||*p>'9') return NULL;
 /* bound: the NUL-terminated console line (WS_LINE_MAX); any 11th significant digit overflows */
 for(;*p>='0'&&*p<='9';p++) { v=v*10+(uint64_t)(*p-'0'); if(v>0xFFFFFFFFULL) return NULL; }
 *out=(uint32_t)v; return p;
}
/* 32 hex digits (either case); a NUL ends the parse before the byte after it is read. */
static const char *parse_key(const char *p,uint8_t key[16]) {
 for(int i=0;i<16;i++,p+=2) {
  int hi=ws_hex_nibble(p[0]), lo=hi<0?-1:ws_hex_nibble(p[1]);
  if(lo<0) return NULL;
  key[i]=(uint8_t)(hi<<4|lo);
 }
 return p;
}
/* The optional " <epoch_floor>"; 0 (no floor) if absent. */
static const char *parse_floor(const char *p,uint32_t *floor) {
 *floor=0;
 if(*p!=' ') return p;
 p=parse_u32(p+1,floor);
 return p&&*floor<WS_EPOCH_FLOOR_MAX?p:NULL;
}
int ws_parse_provision(const char *args,uint32_t *station,uint8_t key[16],uint32_t *epoch_floor) {
 uint32_t floor;
 const char *p=args?parse_u32(args,station):NULL;
 if(!p||*station==0||*station>65535U||*p++!=' ') return -1;
 p=parse_key(p,key);
 if(p) p=parse_floor(p,&floor);
 if(!p||*p!=0) return -1;
 *epoch_floor=floor; return 0;
}
void ws_failrun_note(ws_failrun *r,int ok) {
 if(ok) r->n=0;
 else if(r->n<0xFFFFFFFFu) r->n++;
}
int ws_failrun_tripped(const ws_failrun *r,uint32_t limit) { return r->n>limit; }
