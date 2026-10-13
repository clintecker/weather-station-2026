#include "stage0.h"
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
 snprintf(buf,sizeof buf,"4294967295 %s 102",K);
 assert(ws_parse_provision(buf,&id,key,&floor)==0 && id==4294967295u && floor==102);
 snprintf(buf,sizeof buf,"7 %s 4294901759",K);
 assert(ws_parse_provision(buf,&id,key,&floor)==0 && floor==4294901759u);
 const char *bad[]={ "0 %s", "4294967296 %s", "-1 %s", "+1 %s", " 1 %s", "1  %s", "1 %s ", "1 %s 12x",
                     "1 %s -3", "1 %s 4294901760", "1 %s 1 2", "1x %s", "%s", "1" };
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
  snprintf(buf,sizeof buf,bad[i],K);
  assert(ws_parse_provision(buf,&id,key,&floor)!=0);
 }
 assert(ws_parse_provision("1 000102030405060708090a0b0c0d0e0",&id,key,&floor)!=0);   /* 31 hex */
 assert(ws_parse_provision("1 000102030405060708090a0b0c0d0e0f0",&id,key,&floor)!=0); /* 33 hex */
 assert(ws_parse_provision("1 00010203040506070809za0b0c0d0e0f",&id,key,&floor)!=0);  /* non-hex */
 puts("policy ok");
 return 0;
}
