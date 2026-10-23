/* Host stand-in for the STM32WL HAL: what the TX modules and App/i2c_bus.c use. The I2C, GPIO and NVIC
   functions are implemented by firmware/host/i2c_sim.c. */
#ifndef HOST_STM32WLXX_HAL_H
#define HOST_STM32WLXX_HAL_H
#include <stddef.h>
#include "stm32wlxx.h"
uint32_t HAL_GetTick(void);

typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { I2C2_EV_IRQn = 32, I2C2_ER_IRQn = 33 } IRQn_Type;
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t pre, uint32_t sub);
void HAL_NVIC_EnableIRQ(IRQn_Type irq);
void HAL_NVIC_DisableIRQ(IRQn_Type irq);
void HAL_NVIC_ClearPendingIRQ(IRQn_Type irq);

typedef struct { int unused; } GPIO_TypeDef;
extern GPIO_TypeDef host_gpioa;
#define GPIOA (&host_gpioa)
#define GPIO_PIN_9  (1U << 9)
#define GPIO_PIN_11 (1U << 11)
#define GPIO_PIN_12 (1U << 12)
typedef enum { GPIO_PIN_RESET, GPIO_PIN_SET } GPIO_PinState;
enum { GPIO_MODE_AF_OD = 1, GPIO_MODE_OUTPUT_OD = 2, GPIO_MODE_OUTPUT_PP = 3, GPIO_NOPULL = 0, GPIO_PULLUP = 1,
       GPIO_SPEED_FREQ_LOW = 0, GPIO_AF4_I2C2 = 4 };
typedef struct { uint32_t Pin, Mode, Pull, Speed, Alternate; } GPIO_InitTypeDef;
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *init);
void HAL_GPIO_DeInit(GPIO_TypeDef *port, uint32_t pins);
void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint32_t pins, GPIO_PinState state);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint32_t pin);

enum { RCC_PERIPHCLK_I2C2 = 1, RCC_I2C2CLKSOURCE_PCLK1 = 0 };
typedef struct { uint32_t PeriphClockSelection, I2c2ClockSelection; } RCC_PeriphCLKInitTypeDef;
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *clk);
#define __HAL_RCC_GPIOA_CLK_ENABLE() ((void)0)
#define __HAL_RCC_I2C2_CLK_ENABLE() ((void)0)
#define __HAL_RCC_I2C2_CLK_DISABLE() ((void)0)

typedef struct { int unused; } I2C_TypeDef;
extern I2C_TypeDef host_i2c2;
#define I2C2 (&host_i2c2)
enum { I2C_ADDRESSINGMODE_7BIT = 1, I2C_DUALADDRESS_DISABLE = 0, I2C_GENERALCALL_DISABLE = 0, I2C_NOSTRETCH_DISABLE = 0,
       I2C_ANALOGFILTER_ENABLE = 0 };
typedef struct { uint32_t Timing, OwnAddress1, AddressingMode, DualAddressMode, GeneralCallMode, NoStretchMode; } I2C_InitTypeDef;
typedef struct __I2C_HandleTypeDef {
  I2C_TypeDef *Instance; I2C_InitTypeDef Init;
  HAL_StatusTypeDef (*XferISR)(struct __I2C_HandleTypeDef *hi2c, uint32_t flags, uint32_t sources);
  volatile uint32_t ErrorCode;
} I2C_HandleTypeDef;
#define HAL_I2C_ERROR_BERR 0x00000001U
#define HAL_I2C_ERROR_AF   0x00000004U
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef *hi2c);
HAL_StatusTypeDef HAL_I2C_DeInit(I2C_HandleTypeDef *hi2c);
HAL_StatusTypeDef HAL_I2CEx_ConfigAnalogFilter(I2C_HandleTypeDef *hi2c, uint32_t filter);
HAL_StatusTypeDef HAL_I2C_Master_Transmit_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size);
HAL_StatusTypeDef HAL_I2C_Master_Receive_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint8_t *data, uint16_t size);
#define I2C_MEMADD_SIZE_8BIT 1U
#define I2C_MEMADD_SIZE_16BIT 2U
HAL_StatusTypeDef HAL_I2C_Mem_Read_IT(I2C_HandleTypeDef *hi2c, uint16_t addr, uint16_t mem, uint16_t mem_size, uint8_t *data, uint16_t size);
void HAL_I2C_EV_IRQHandler(I2C_HandleTypeDef *hi2c);
void HAL_I2C_ER_IRQHandler(I2C_HandleTypeDef *hi2c);
void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c);
void HAL_I2C_MspDeInit(I2C_HandleTypeDef *hi2c);
void HAL_I2C_MasterTxCpltCallback(I2C_HandleTypeDef *hi2c);
void HAL_I2C_MasterRxCpltCallback(I2C_HandleTypeDef *hi2c);
void HAL_I2C_MemRxCpltCallback(I2C_HandleTypeDef *hi2c);
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c);
#endif
