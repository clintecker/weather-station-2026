#include "stage0.h"
#undef NDEBUG /* the checks below are assert()s: keep them in every build */
#include <assert.h>
#include <string.h>
/* SHT45 reply parsing: conversion, both CRCs, and the raw (uncropped) result; the 0x89 serial reply
   (App/mod_th.c does the bus steps, and the crop after calibration). */
static void reply(uint8_t r[WS_SHT45_REPLY_LEN], uint16_t st, uint16_t srh) {
 r[0]=(uint8_t)(st>>8); r[1]=(uint8_t)st; r[2]=ws_crc8(r,2);
 r[3]=(uint8_t)(srh>>8); r[4]=(uint8_t)srh; r[5]=ws_crc8(r+3,2);
}
int main(void) {
 uint8_t r[WS_SHT45_REPLY_LEN]; int32_t t=0, h=0; uint32_t serial=0;
 reply(r,0x8000,0x8000); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==4250&&h==5650);
 /* Raw and signed: below 0 % and above 100 % reach the caller, which crops after calibration. */
 reply(r,0,0); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==-4500&&h==-600);
 reply(r,0xffff,0xffff); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==13000&&h==11900);
 /* Rounded to nearest, not truncated: raw 20000 is 8.4066 C and 32.147 %RH (datasheet 4.6). */
 reply(r,20000,20000); assert(ws_sht45_parse(r,&t,&h)==0); assert(t==841&&h==3215);
 /* A CRC mismatch in either word is -4 and leaves the outputs untouched. */
 for(int word=0;word<2;word++) {
  reply(r,0x8000,0x8000); r[word?5:2]^=1; t=123; h=456;
  assert(ws_sht45_parse(r,&t,&h)==-4); assert(t==123&&h==456);
 }
 /* The serial reply (command 0x89): two CRC-checked words, high word first. */
 reply(r,0x1234,0xabcd); assert(ws_sht4x_serial_parse(r,&serial)==0); assert(serial==0x1234abcdUL);
 for(int word=0;word<2;word++) {
  reply(r,0x1234,0xabcd); r[word?5:2]^=1; serial=7;
  assert(ws_sht4x_serial_parse(r,&serial)==-4); assert(serial==7);
 }
 return 0;
}
