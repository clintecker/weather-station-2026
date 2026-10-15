#include "stage0.h"
#undef NDEBUG /* the checks below are assert()s: keep them in every build */
#include <assert.h>
#include <string.h>
/* SHT45 reply parsing: conversion, RH clamp, and both CRCs (App/sensor.c does the bus steps). */
static void reply(uint8_t r[WS_SHT45_REPLY_LEN], uint16_t st, uint16_t srh) {
 r[0]=(uint8_t)(st>>8); r[1]=(uint8_t)st; r[2]=ws_crc8(r,2);
 r[3]=(uint8_t)(srh>>8); r[4]=(uint8_t)srh; r[5]=ws_crc8(r+3,2);
}
int main(void) {
 uint8_t r[WS_SHT45_REPLY_LEN]; int16_t t=0; uint16_t h=0;
 reply(r,0x8000,0x8000); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==4250&&h==5650);
 reply(r,0,0); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==-4500&&h==0);                 /* RH clamps at 0 */
 reply(r,0xffff,0xffff); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==13000&&h==10000);   /* and at 100 % */
 /* A CRC mismatch in either word is -4 and leaves the outputs untouched. */
 for(int word=0;word<2;word++) {
  reply(r,0x8000,0x8000); r[word?5:2]^=1; t=123; h=456;
  assert(ws_sht45_parse(r,&t,&h)==-4); assert(t==123&&h==456);
 }
 return 0;
}
