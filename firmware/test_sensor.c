#include "stage0.h"
#include <assert.h>
#include <string.h>
/* Fake I2C verifies command, address, delay, CRC handling and transport failure. */
static int mode=0;
static int write_sensor(void *ctx,uint8_t address,const uint8_t *data,size_t n) {
 (void)ctx; assert(address==0x44&&n==1&&data[0]==0xfd); return mode==2?-1:0;
}
static int read_sensor(void *ctx,uint8_t address,uint8_t *data,size_t n) {
 (void)ctx; assert(address==0x44&&n==6);
 uint8_t reply[6]={0x80,0,0,0x80,0,0};
 reply[2]=ws_crc8(reply,2); reply[5]=ws_crc8(reply+3,2);
 if(mode==1) reply[5]^=1;
 memcpy(data,reply,6); return mode==3?-1:0;
}
static void delay_sensor(void *ctx,uint32_t ms) {(void)ctx;assert(ms>=10);}
int main(void) {
 ws_i2c bus={0,write_sensor,read_sensor,delay_sensor}; int16_t t=0; uint16_t h=0;
 assert(ws_sht45_read(&bus,&t,&h)==0); assert(t==4250&&h==5650);
 for(mode=1;mode<=3;mode++) {
  t=123; h=456; assert(ws_sht45_read(&bus,&t,&h)!=0); assert(t==123&&h==456);
 }
 return 0;
}
