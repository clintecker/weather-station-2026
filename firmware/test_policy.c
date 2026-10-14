#include "stage0.h"
#undef NDEBUG /* the checks below are assert()s: keep them in every build */
#include <assert.h>
#include <stdio.h>
/* Host tests for the I2C stuck-bus recovery waveform and the per-minute link gate. */

/* Open-drain bus model: a line is high only if nobody pulls it low. The "sensor" holds SDA low
   until it has seen hold_clocks rising SCL edges (it finishes the byte it was sending). */
static int scl_drive=1, sda_drive=1, hold_clocks, scl_rises, stops, bad_starts, prev_scl=1, prev_sda=1;
static int line_sda(void) { return sda_drive && !(hold_clocks > scl_rises); }
static void observe(void) {
 int scl=scl_drive, sda=line_sda();
 if(scl && prev_scl) {                       /* SDA changed while SCL stayed high */
  if(!prev_sda && sda) stops++;
  if(prev_sda && !sda) bad_starts++;
 }
 if(scl && !prev_scl) scl_rises++;
 prev_scl=scl; prev_sda=line_sda();
}
static void set_scl(void *c,int level) { (void)c; scl_drive=level; observe(); }
static void set_sda(void *c,int level) { (void)c; sda_drive=level; observe(); }
static int read_sda(void *c) { (void)c; return line_sda(); }
static void wait_us(void *c,uint32_t us) { (void)c; (void)us; }

static void run_recovery(int hold) {
 scl_drive=1; sda_drive=1; scl_rises=0; stops=0; bad_starts=0; hold_clocks=hold;
 prev_scl=1; prev_sda=line_sda();
 ws_i2c_pins pins={0,set_scl,set_sda,read_sda,wait_us};
 int rc=ws_i2c_recover(&pins);
 assert(bad_starts==0);                      /* never an accidental START */
 if(hold>9) { assert(rc==-1); return; }      /* a device that never lets go is reported */
 assert(rc==0);
 assert(stops==1);                           /* exactly one real STOP: SDA rises while SCL is high */
 assert(scl_drive==1 && line_sda()==1);      /* bus left idle */
}

int main(void) {
 for(int hold=0; hold<=9; hold++) run_recovery(hold);   /* free bus and stuck for 1..9 clocks */
 run_recovery(12);                                       /* stuck beyond 9 clocks */

 /* Link gate (docs/radio-energy-policy.md §6): energy 0 SURPLUS, 1 NORMAL, 2 CONSERVE, 3 CRITICAL. */
 for(int e=0;e<=1;e++) {                     /* healthy energy: probing still sends every minute */
  assert(ws_link_may_send(e,0,500)==1);
  assert(ws_link_may_send(e,1,500)==1);
  assert(ws_link_may_send(e,1,-5)==1);
 }
 assert(ws_link_may_send(2,0,500)==1);       /* CONSERVE, linked: the energy gate decides elsewhere */
 assert(ws_link_may_send(2,1,500)==0);       /* CONSERVE, probing: wait for the back-off */
 assert(ws_link_may_send(2,1,0)==1);
 assert(ws_link_may_send(2,1,-1)==1);
 assert(ws_link_may_send(3,0,0)==0);         /* CRITICAL never transmits */
 assert(ws_link_may_send(3,1,-1)==0);
 /* PROVISION argument parser: exact fields, digits only, no overflow, floor below the ceiling. */
 const char *K="000102030405060708090a0b0c0d0e0f";
 char buf[160]; uint32_t id, floor; uint8_t key[16];
 snprintf(buf,sizeof buf,"1 %s",K);
 assert(ws_parse_provision(buf,&id,key,&floor)==0 && id==1 && floor==0 && key[0]==0 && key[15]==15);
 snprintf(buf,sizeof buf,"65535 %s 102",K);
 assert(ws_parse_provision(buf,&id,key,&floor)==0 && id==65535u && floor==102);  /* draft 5: station is u16 */
 snprintf(buf,sizeof buf,"7 %s 4294901759",K);
 assert(ws_parse_provision(buf,&id,key,&floor)==0 && floor==4294901759u);
 const char *bad[]={ "0 %s", "65536 %s", "4294967295 %s", "4294967296 %s", "-1 %s", "+1 %s", " 1 %s", "1  %s", "1 %s ", "1 %s 12x",
                     "1 %s -3", "1 %s 4294901760", "1 %s 1 2", "1x %s", "%s", "1" };
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
  snprintf(buf,sizeof buf,bad[i],K);
  assert(ws_parse_provision(buf,&id,key,&floor)!=0);
 }
 assert(ws_parse_provision("1 000102030405060708090a0b0c0d0e0",&id,key,&floor)!=0);   /* 31 hex */
 assert(ws_parse_provision("1 000102030405060708090a0b0c0d0e0f0",&id,key,&floor)!=0); /* 33 hex */
 assert(ws_parse_provision("1 00010203040506070809za0b0c0d0e0f",&id,key,&floor)!=0);  /* non-hex */
 /* Consecutive-failure run (TX health, review P7): only uninterrupted failures trip it. */
 ws_failrun fr={0};
 for(int i=0;i<10;i++) { ws_failrun_note(&fr,0); assert(!ws_failrun_tripped(&fr,10)); }
 ws_failrun_note(&fr,0); assert(ws_failrun_tripped(&fr,10));           /* 11th failure in a row */
 ws_failrun_note(&fr,1); assert(!ws_failrun_tripped(&fr,10) && fr.n==0); /* any success resets */
 for(unsigned i=0;i<1000;i++) ws_failrun_note(&fr,0);
 assert(fr.n==1000);                                                     /* no overflow trouble */
 fr.n=0xFFFFFFFFu; ws_failrun_note(&fr,0); assert(fr.n==0xFFFFFFFFu);  /* saturates */

 /* Radio silence check (RX relisten, review P6): wrap-safe over the 32-bit ms tick. */
 assert(!ws_silent_for(1000,1000,300000));
 assert(!ws_silent_for(300999,1000,300000));
 assert(ws_silent_for(301001,1000,300000));
 assert(!ws_silent_for(0x00000100u,0xFFFFFF00u,300000));   /* 512 ms across the wrap */
 assert(ws_silent_for(0x00050000u,0xFFFFFF00u,300000));    /* ~328 s across the wrap */
 /* Stack high-water scan (run-time stack monitor): the deepest word no longer holding the paint. */
 uint32_t ram[64];
 for(int i=0;i<64;i++) ram[i]=WS_STACK_PAINT;
 assert(ws_stack_peak(ram, ram+64)==0);                     /* nothing used */
 ram[50]=1;                                                 /* deepest touched word, index 50 */
 assert(ws_stack_peak(ram, ram+64)==(64-50)*4);
 ram[10]=WS_STACK_PAINT+1;
 assert(ws_stack_peak(ram, ram+64)==(64-10)*4);
 ram[0]=0;
 assert(ws_stack_peak(ram, ram+64)==64*4);                  /* reached the bottom: overflow suspect */
 /* 15-s T/RH window: mean rounds half up (also below zero), extrema, out-of-range samples skipped. */
 { ws_th_window w; int16_t t; uint16_t h;
   ws_th_reset(&w); assert(!ws_th_mean_t(&w,&t) && !ws_th_mean_h(&w,&h));
   ws_th_add(&w,1,-1234,4567); ws_th_add(&w,1,-1235,4568);           /* mean -1234.5 -> -1234 (half up) */
   assert(ws_th_mean_t(&w,&t) && t==-1234 && ws_th_mean_h(&w,&h) && h==4568); /* 4567.5 -> 4568 */
   ws_th_add(&w,0,9999,9999);                                          /* sensor fault: not counted */
   ws_th_add(&w,1,-4001,5000); ws_th_add(&w,1,12501,5000);              /* outside -40..125 C: not counted */
   ws_th_add(&w,1,2000,11900);                                         /* RH clamps to 100.00 % */
   assert(w.n==3 && w.t_min==-1235 && w.t_max==2000 && w.h_min==4567 && w.h_max==10000);
   assert(ws_th_mean_t(&w,&t) && t==-156);                             /* (-1234-1235+2000)/3 = -156.33 -> -156 */
   ws_th_reset(&w); ws_th_add(&w,1,1,0); ws_th_add(&w,1,2,0);           /* 1.5 -> 2 */
   assert(ws_th_mean_t(&w,&t) && t==2);
   ws_th_reset(&w); ws_th_add(&w,1,-1,0); ws_th_add(&w,1,-2,0);         /* -1.5 -> -1 (toward +inf) */
   assert(ws_th_mean_t(&w,&t) && t==-1);
   for(int i=0;i<300;i++) ws_th_add(&w,1,12500,10000);                  /* saturates at 255 samples */
   assert(w.n==255 && ws_th_mean_t(&w,&t)); }
 puts("policy ok");
 return 0;
}
