#include "stage0.h"
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
static void put(uint8_t *out,uint64_t v,size_t n) {
 for(size_t i=0;i<n;i++) out[n-1-i]=(uint8_t)(v>>(8*i));
}
void ws_pack_observation(uint8_t out[24],uint32_t epoch,uint32_t seq,uint64_t utc,
 int16_t t,uint16_t rh,uint8_t valid,uint8_t timed) {
 put(out,epoch,4); put(out+4,seq,4); put(out+8,timed?utc:0,8);
 put(out+16,valid?(uint16_t)t:0,2); put(out+18,valid?rh:0,2);
 out[20]=valid?1:0; out[21]=timed?1:0; out[22]=0; out[23]=0;
}
