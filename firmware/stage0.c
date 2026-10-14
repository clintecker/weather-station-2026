#include "stage0.h"
#include <string.h>
/* Sensirion polynomial 0x31, initial FF, no final XOR. */
uint8_t ws_crc8(const uint8_t *data, size_t count) {
 uint8_t crc=0xff;
 for(size_t i=0;i<count;i++) {
  crc^=data[i];
  for(unsigned bit=0;bit<8;bit++) crc=(uint8_t)((crc&0x80)?(crc<<1)^0x31:crc<<1);
 }
 return crc;
}
int ws_sht45_read(const ws_i2c *bus,int16_t *centi_c,uint16_t *centi_rh) {
 const uint8_t command=0xfd; uint8_t bytes[6];
 if(!bus||!bus->write||!bus->read||!bus->delay_ms||!centi_c||!centi_rh) return -1;
 /* Callbacks use the 7-bit address; STM32 HAL glue shifts it when needed. */
 if(bus->write(bus->context,0x44,&command,1)) return -2;
 bus->delay_ms(bus->context,10); /* High precision, heater OFF. */
 if(bus->read(bus->context,0x44,bytes,6)) return -3;
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
void ws_th_add(ws_th_window *w,int valid,int16_t t,uint16_t h) {
 if(!valid||t<-4000||t>12500||w->n>=255) return;
 if(h>10000) h=10000;
 if(!w->n||t<w->t_min) w->t_min=t;
 if(!w->n||t>w->t_max) w->t_max=t;
 if(!w->n||h<w->h_min) w->h_min=h;
 if(!w->n||h>w->h_max) w->h_max=h;
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
int ws_i2c_recover(const ws_i2c_pins *p) {
 const uint32_t half=5;                      /* 5 us half period = 100 kHz */
 p->set_sda(p->context,1); p->set_scl(p->context,1); p->wait_us(p->context,half);
 for(int i=0;i<9 && !p->read_sda(p->context);i++) {
  p->set_scl(p->context,0); p->wait_us(p->context,half);
  p->set_scl(p->context,1); p->wait_us(p->context,half);
 }
 int held=!p->read_sda(p->context);
 p->set_scl(p->context,0); p->wait_us(p->context,half);   /* STOP */
 p->set_sda(p->context,0); p->wait_us(p->context,half);
 p->set_scl(p->context,1); p->wait_us(p->context,half);
 p->set_sda(p->context,1); p->wait_us(p->context,half);
 return held?-1:0;
}
int ws_link_may_send(int energy,int probing,int32_t secs_until_probe) {
 if(energy>=3) return 0;
 if(!probing||energy<=1) return 1;
 return secs_until_probe<=0;
}
static int parse_u32(const char **s,uint32_t *out) {
 uint64_t v=0; const char *p=*s;
 if(*p<'0'||*p>'9') return -1;
 for(;*p>='0'&&*p<='9';p++) { v=v*10+(uint64_t)(*p-'0'); if(v>0xFFFFFFFFULL) return -1; }
 *out=(uint32_t)v; *s=p; return 0;
}
static int hex_nibble(char c) {
 if(c>='0'&&c<='9') return c-'0';
 if(c>='a'&&c<='f') return c-'a'+10;
 if(c>='A'&&c<='F') return c-'A'+10;
 return -1;
}
int ws_parse_provision(const char *args,uint32_t *station,uint8_t key[16],uint32_t *epoch_floor) {
 const char *p=args; uint32_t floor=0;
 if(!p||parse_u32(&p,station)||*station==0||*station>65535U||*p++!=' ') return -1;
 for(int i=0;i<16;i++) {
  int hi=hex_nibble(p[0]), lo=hi<0?-1:hex_nibble(p[1]);
  if(lo<0) return -1;
  key[i]=(uint8_t)(hi<<4|lo); p+=2;
 }
 if(*p==' ') { p++; if(parse_u32(&p,&floor)||floor>=WS_EPOCH_FLOOR_MAX) return -1; }
 if(*p!=0) return -1;
 *epoch_floor=floor; return 0;
}
void ws_failrun_note(ws_failrun *r,int ok) {
 if(ok) r->n=0;
 else if(r->n<0xFFFFFFFFu) r->n++;
}
int ws_failrun_tripped(const ws_failrun *r,uint32_t limit) { return r->n>limit; }
