/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    subghz_phy_app.c
  * @author  MCD Application Team
  * @brief   Application of the SubGHz_Phy Middleware
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2021 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "platform.h"
#include "sys_app.h"
#include "subghz_phy_app.h"
#include "radio.h"

/* USER CODE BEGIN Includes */
#include "stm32_timer.h"
#include "stm32_seq.h"
#include "utilities_def.h"
#include "app_version.h"
#include "subghz_phy_version.h"
#include "rt_proto.h"
/* USER CODE END Includes */

/* External variables ---------------------------------------------------------*/
/* USER CODE BEGIN EV */

/* USER CODE END EV */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef enum
{
  RX,
  RX_TIMEOUT,
  RX_ERROR,
  TX,
  TX_TIMEOUT,
} States_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
/* Configurations */
/*Timeout*/
#define RX_TIMEOUT_VALUE              3000
#define TX_TIMEOUT_VALUE              3000
/*Size of the payload to be sent*/
/* Size must be greater of equal the PING and PONG*/
#define MAX_APP_BUFFER_SIZE          255
#if (PAYLOAD_LEN > MAX_APP_BUFFER_SIZE)
#error PAYLOAD_LEN must be less or equal than MAX_APP_BUFFER_SIZE
#endif /* (PAYLOAD_LEN > MAX_APP_BUFFER_SIZE) */
/* wait for remote to be in Rx, before sending a Tx frame*/
#define RX_TIME_MARGIN                200
/* Afc bandwidth in Hz */
#define FSK_AFC_BANDWIDTH             83333
/* LED blink Period*/
#define LED_PERIOD_MS                 200
/* weather-station-2026: extra time a board holds the "ball" (blue LED on) before returning it.
   rangetest: short, so each board hears about 1.5 packets/s at SF7. Must stay well under
   RX_TIMEOUT_VALUE. */
#define BALL_HOLD_MS                  100
/* rangetest: ignore button bounce within this window */
#define BUTTON_DEBOUNCE_MS            250
/* rangetest: green LED blink half-period for button feedback */
#define BLINK_MS                      150

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* Radio events function pointer */
static RadioEvents_t RadioEvents;

/* USER CODE BEGIN PV */
/*Ping Pong FSM states */
static States_t State = RX;
/* App Rx Buffer*/
static uint8_t BufferRx[MAX_APP_BUFFER_SIZE];
/* App Tx Buffer*/
static uint8_t BufferTx[MAX_APP_BUFFER_SIZE];
/* Last  Received Buffer Size*/
uint16_t RxBufferSize = 0;
/* Last  Received packer Rssi*/
int8_t RssiValue = 0;
/* Last  Received packer SNR (in Lora modulation)*/
int8_t SnrValue = 0;
/* Led Timers objects*/
static UTIL_TIMER_Object_t timerLed;
/* device state. Master: true, Slave: false*/
bool isMaster = true;
/* random delay to make sure 2 devices will sync*/
/* the closest the random delays are, the longer it will
   take for the devices to sync when started simultaneously*/
static int32_t random_delay;

/* rangetest: settings handshake, sequence numbers, what I last measured from the peer */
static rt_state_t rt;
static uint16_t txSeq;
static int16_t lastRssi = RT_NO_RSSI;
static int8_t lastSnr;
/* rangetest: buttons (set in the EXTI interrupt, consumed by Buttons_Process) */
static volatile uint8_t buttonsPressed;
static UTIL_TIMER_Time_t buttonLastMs[3];
static uint16_t markCount;
static UTIL_TIMER_Object_t timerBlink;
static uint8_t blinkLeft;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/*!
 * @brief Function to be executed on Radio Tx Done event
 */
static void OnTxDone(void);

/**
  * @brief Function to be executed on Radio Rx Done event
  * @param  payload ptr of buffer received
  * @param  size buffer size
  * @param  rssi
  * @param  LoraSnr_FskCfo
  */
static void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t LoraSnr_FskCfo);

/**
  * @brief Function executed on Radio Tx Timeout event
  */
static void OnTxTimeout(void);

/**
  * @brief Function executed on Radio Rx Timeout event
  */
static void OnRxTimeout(void);

/**
  * @brief Function executed on Radio Rx Error event
  */
static void OnRxError(void);

/* USER CODE BEGIN PFP */
/**
  * @brief  Function executed on when led timer elapses
  * @param  context ptr of LED context
  */
static void OnledEvent(void *context);

/**
  * @brief  weather-station-2026: blue LED (LD1) shows which board holds the ball
  */
static void CatchBall(void);

/**
  * @brief PingPong state machine implementation
  */
static void PingPong_Process(void);

/**
  * @brief rangetest: build a PING or PONG for the current settings and send it
  */
static void RadioSend(uint8_t type);

/**
  * @brief rangetest: button presses, run from the sequencer (never inside the interrupt)
  */
static void Buttons_Process(void);

/**
  * @brief rangetest: blink the green LED n times without blocking the radio
  */
static void Blink(uint8_t n);
static void OnBlinkEvent(void *context);

/**
  * @brief rangetest: log the effect of a handshake event, if any
  */
static void LogEvents(int ev);

/**
  * @brief PingPong RX configure and process
  */
static void RadioRx(void);

/* USER CODE END PFP */

/* Exported functions ---------------------------------------------------------*/
void SubghzApp_Init(void)
{
  /* USER CODE BEGIN SubghzApp_Init_1 */

  APP_LOG(TS_OFF, VLEVEL_M, "\n\rRANGETEST (weather-station-2026, from ST PING PONG)\n\r");
  APP_LOG(TS_OFF, VLEVEL_M, "B1 = mark spot, B2 = TX power down (22/14/10/0 dBm), B3 = SF down (12/10/9/7); both wrap to the top. Boot and ~30 s without contact = SF12 / +22 dBm.\n\r");
  /* Get SubGHY_Phy APP version*/
  APP_LOG(TS_OFF, VLEVEL_M, "APPLICATION_VERSION: V%X.%X.%X\r\n",
          (uint8_t)(APP_VERSION_MAIN),
          (uint8_t)(APP_VERSION_SUB1),
          (uint8_t)(APP_VERSION_SUB2));

  /* Get MW SubGhz_Phy info */
  APP_LOG(TS_OFF, VLEVEL_M, "MW_RADIO_VERSION:    V%X.%X.%X\r\n",
          (uint8_t)(SUBGHZ_PHY_VERSION_MAIN),
          (uint8_t)(SUBGHZ_PHY_VERSION_SUB1),
          (uint8_t)(SUBGHZ_PHY_VERSION_SUB2));

  /* Led Timers*/
  UTIL_TIMER_Create(&timerLed, LED_PERIOD_MS, UTIL_TIMER_ONESHOT, OnledEvent, NULL);
  UTIL_TIMER_Start(&timerLed);

  /* rangetest: settings start at the bench default on every boot */
  rt_init(&rt);
  UTIL_TIMER_Create(&timerBlink, BLINK_MS, UTIL_TIMER_ONESHOT, OnBlinkEvent, NULL);
  UTIL_SEQ_RegTask((1 << CFG_SEQ_Task_Buttons), UTIL_SEQ_RFU, Buttons_Process);
  /* gpio.c already configures the button pins as falling-edge EXTI; enable their interrupts */
  HAL_NVIC_SetPriority(EXTI0_IRQn, 15, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  HAL_NVIC_SetPriority(EXTI1_IRQn, 15, 0);
  HAL_NVIC_EnableIRQ(EXTI1_IRQn);
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, 15, 0);
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
  /* USER CODE END SubghzApp_Init_1 */

  /* Radio initialization */
  RadioEvents.TxDone = OnTxDone;
  RadioEvents.RxDone = OnRxDone;
  RadioEvents.TxTimeout = OnTxTimeout;
  RadioEvents.RxTimeout = OnRxTimeout;
  RadioEvents.RxError = OnRxError;

  Radio.Init(&RadioEvents);

  /* USER CODE BEGIN SubghzApp_Init_2 */
  /*calculate random delay for synchronization*/
  random_delay = (Radio.Random()) >> 22; /*10bits random e.g. from 0 to 1023 ms*/

  /* Radio Set frequency */
  Radio.SetChannel(RF_FREQUENCY);

  /* Radio configuration */
#if ((USE_MODEM_LORA == 1) && (USE_MODEM_FSK == 0))
  APP_LOG(TS_OFF, VLEVEL_M, "---------------\n\r");
  APP_LOG(TS_OFF, VLEVEL_M, "LORA_MODULATION\n\r");
  APP_LOG(TS_OFF, VLEVEL_M, "LORA_BW=%d kHz\n\r", (1 << LORA_BANDWIDTH) * 125);
  APP_LOG(TS_OFF, VLEVEL_M, "#rt cfg sf=%d pwr=%d boot\n\r", rt_cur_sf(&rt), rt_cur_pwr(&rt));
#elif ((USE_MODEM_LORA == 0) && (USE_MODEM_FSK == 1))
  APP_LOG(TS_OFF, VLEVEL_M, "---------------\n\r");
  APP_LOG(TS_OFF, VLEVEL_M, "FSK_MODULATION\n\r");
  APP_LOG(TS_OFF, VLEVEL_M, "FSK_BW=%d Hz\n\r", FSK_BANDWIDTH);
  APP_LOG(TS_OFF, VLEVEL_M, "FSK_DR=%d bits/s\n\r", FSK_DATARATE);
#else
#error "Please define a modulation in the subghz_phy_app.h file."
#endif /* USE_MODEM_LORA | USE_MODEM_FSK */

  /*fills tx buffer*/
  memset(BufferTx, 0x0, MAX_APP_BUFFER_SIZE);

  APP_LOG(TS_ON, VLEVEL_L, "rand=%d\n\r", random_delay);

  /*register task to to be run in while(1) after Radio IT*/
  UTIL_SEQ_RegTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), UTIL_SEQ_RFU, PingPong_Process);

  /*starts first process */
  HAL_Delay(RX_TIMEOUT_VALUE + random_delay);
  RadioRx();
  /* USER CODE END SubghzApp_Init_2 */
}

/* USER CODE BEGIN EF */

/* USER CODE END EF */

/* Private functions ---------------------------------------------------------*/
static void OnTxDone(void)
{
  /* USER CODE BEGIN OnTxDone */
  APP_LOG(TS_ON, VLEVEL_L, "OnTxDone\n\r");
  /* ball has left this board */
  HAL_GPIO_WritePin(LED1_GPIO_Port, LED1_Pin, GPIO_PIN_RESET); /* LED_BLUE */
  /* Update the State of the FSM*/
  State = TX;
  /* Run PingPong process in background*/
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), CFG_SEQ_Prio_0);
  /* USER CODE END OnTxDone */
}

static void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t LoraSnr_FskCfo)
{
  /* USER CODE BEGIN OnRxDone */
  APP_LOG(TS_ON, VLEVEL_L, "OnRxDone\n\r");
#if ((USE_MODEM_LORA == 1) && (USE_MODEM_FSK == 0))
  APP_LOG(TS_ON, VLEVEL_L, "RssiValue=%d dBm, SnrValue=%ddB\n\r", rssi, LoraSnr_FskCfo);
  /* Record payload Signal to noise ratio in Lora*/
  SnrValue = LoraSnr_FskCfo;
#endif /* USE_MODEM_LORA | USE_MODEM_FSK */
#if ((USE_MODEM_LORA == 0) && (USE_MODEM_FSK == 1))
  APP_LOG(TS_ON, VLEVEL_L, "RssiValue=%d dBm, Cfo=%dkHz\n\r", rssi, LoraSnr_FskCfo);
  SnrValue = 0; /*not applicable in GFSK*/
#endif /* USE_MODEM_LORA | USE_MODEM_FSK */
  /* Update the State of the FSM*/
  State = RX;
  /* Clear BufferRx*/
  memset(BufferRx, 0, MAX_APP_BUFFER_SIZE);
  /* Record payload size*/
  RxBufferSize = size;
  if (RxBufferSize <= MAX_APP_BUFFER_SIZE)
  {
    memcpy(BufferRx, payload, RxBufferSize);
  }
  /* Record Received Signal Strength*/
  RssiValue = rssi;
  /* Record payload content*/
  APP_LOG(TS_ON, VLEVEL_H, "payload. size=%d \n\r", size);
  for (int32_t i = 0; i < PAYLOAD_LEN; i++)
  {
    APP_LOG(TS_OFF, VLEVEL_H, "%02X", BufferRx[i]);
    if (i % 16 == 15)
    {
      APP_LOG(TS_OFF, VLEVEL_H, "\n\r");
    }
  }
  APP_LOG(TS_OFF, VLEVEL_H, "\n\r");
  /* Run PingPong process in background*/
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), CFG_SEQ_Prio_0);
  /* USER CODE END OnRxDone */
}

static void OnTxTimeout(void)
{
  /* USER CODE BEGIN OnTxTimeout */
  APP_LOG(TS_ON, VLEVEL_L, "OnTxTimeout\n\r");
  /* Update the State of the FSM*/
  State = TX_TIMEOUT;
  /* Run PingPong process in background*/
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), CFG_SEQ_Prio_0);
  /* USER CODE END OnTxTimeout */
}

static void OnRxTimeout(void)
{
  /* USER CODE BEGIN OnRxTimeout */
  APP_LOG(TS_ON, VLEVEL_L, "OnRxTimeout\n\r");
  /* Update the State of the FSM*/
  State = RX_TIMEOUT;
  /* Run PingPong process in background*/
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), CFG_SEQ_Prio_0);
  /* USER CODE END OnRxTimeout */
}

static void OnRxError(void)
{
  /* USER CODE BEGIN OnRxError */
  APP_LOG(TS_ON, VLEVEL_L, "OnRxError\n\r");
  /* Update the State of the FSM*/
  State = RX_ERROR;
  /* Run PingPong process in background*/
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_SubGHz_Phy_App_Process), CFG_SEQ_Prio_0);
  /* USER CODE END OnRxError */
}

/* USER CODE BEGIN PrFD */
static void RadioSend(uint8_t type)
{
  rt_build(&rt, type, txSeq++, lastRssi, lastSnr, BufferTx);
#if ((USE_MODEM_LORA == 1) && (USE_MODEM_FSK == 0))
  Radio.Sleep();
  Radio.SetChannel(RF_FREQUENCY);
  Radio.SetTxConfig(MODEM_LORA, (int8_t)rt_cur_pwr(&rt), 0, LORA_BANDWIDTH,
                    (uint32_t)rt_cur_sf(&rt), LORA_CODINGRATE,
                    LORA_PREAMBLE_LENGTH, LORA_FIX_LENGTH_PAYLOAD_ON,
                    true, 0, 0, LORA_IQ_INVERSION_ON, TX_TIMEOUT_VALUE);
  Radio.SetMaxPayloadLength(MODEM_LORA, MAX_APP_BUFFER_SIZE);
#elif ((USE_MODEM_LORA == 0) && (USE_MODEM_FSK == 1))
  Radio.SetTxConfig(MODEM_FSK, TX_OUTPUT_POWER, FSK_FDEV, 0,
                    FSK_DATARATE, 0,
                    FSK_PREAMBLE_LENGTH, FSK_FIX_LENGTH_PAYLOAD_ON,
                    true, 0, 0, 0, TX_TIMEOUT_VALUE);
  Radio.SetMaxPayloadLength(MODEM_FSK, MAX_APP_BUFFER_SIZE);
#else
#error "Please define a modulation in the subghz_phy_app.h file."
#endif /* USE_MODEM_LORA | USE_MODEM_FSK */

  Radio.Send(BufferTx, PAYLOAD_LEN);
}

static void RadioRx(void)
{
#if ((USE_MODEM_LORA == 1) && (USE_MODEM_FSK == 0))
  Radio.Sleep();
  Radio.SetChannel(RF_FREQUENCY);
  Radio.SetRxConfig(MODEM_LORA, LORA_BANDWIDTH, (uint32_t)rt_cur_sf(&rt),
                    LORA_CODINGRATE, 0, LORA_PREAMBLE_LENGTH,
                    LORA_SYMBOL_TIMEOUT, LORA_FIX_LENGTH_PAYLOAD_ON,
                    0, true, 0, 0, LORA_IQ_INVERSION_ON, true);
  if (LORA_FIX_LENGTH_PAYLOAD_ON == true)
  {
    Radio.SetMaxPayloadLength(MODEM_LORA, PAYLOAD_LEN);
  }
  else
  {
    Radio.SetMaxPayloadLength(MODEM_LORA, MAX_APP_BUFFER_SIZE);
  }
#elif ((USE_MODEM_LORA == 0) && (USE_MODEM_FSK == 1))
  Radio.SetRxConfig(MODEM_FSK, FSK_BANDWIDTH, FSK_DATARATE,
                    0, FSK_AFC_BANDWIDTH, FSK_PREAMBLE_LENGTH,
                    0, FSK_FIX_LENGTH_PAYLOAD_ON, 0, true,
                    0, 0, false, true);
  if (LORA_FIX_LENGTH_PAYLOAD_ON == true)
  {
    Radio.SetMaxPayloadLength(MODEM_FSK, PAYLOAD_LEN);
  }
  else
  {
    Radio.SetMaxPayloadLength(MODEM_FSK, MAX_APP_BUFFER_SIZE);
  }
#else
#error "Please define a modulation in the subghz_phy_app.h file."
#endif /* USE_MODEM_LORA | USE_MODEM_FSK */

  Radio.Rx(RX_TIMEOUT_VALUE);
}

static void PingPong_Process(void)
{
  rt_rx_t info;
  int ev;
  bool gotPing = false, gotPong = false;

  Radio.Sleep();

  switch (State)
  {
    case RX:
      if (RxBufferSize > 0)
      {
        ev = rt_on_rx(&rt, BufferRx, RxBufferSize, &info);
        if (ev >= 0)
        {
          /* uplink = what I heard now; downlink = what the peer heard of my last packet */
          APP_LOG(TS_ON, VLEVEL_L, "#rt rx %s seq=%u rssi=%d snr=%d peer_rssi=%d peer_snr=%d sf=%d pwr=%d "
                  "peer_sf=%d peer_pwr=%d\n\r",
                  info.type == RT_PING ? "ping" : "pong", info.seq, RssiValue, SnrValue,
                  info.peer_rssi, info.peer_snr, rt_cur_sf(&rt), rt_cur_pwr(&rt),
                  rt_info_sf(&info), rt_info_pwr(&info));
          lastRssi = RssiValue;
          lastSnr = SnrValue;
          LogEvents(ev);
          gotPing = info.type == RT_PING;
          gotPong = info.type == RT_PONG;
        }
      }
      if (isMaster == true)
      {
        if (gotPong)
        {
          CatchBall();
          /* Add delay between RX and TX */
          HAL_Delay(Radio.GetWakeupTime() + RX_TIME_MARGIN + BALL_HOLD_MS);
          APP_LOG(TS_ON, VLEVEL_L, "Master Tx start\n\r");
          RadioSend(RT_PING);
        }
        else if (gotPing)
        {
          /* A master already exists then become a slave */
          isMaster = false;
          APP_LOG(TS_ON, VLEVEL_L, "Slave Rx start\n\r");
          RadioRx();
        }
        else /* valid reception but not a rangetest packet */
        {
          APP_LOG(TS_ON, VLEVEL_L, "Master Rx start\n\r");
          RadioRx();
        }
      }
      else
      {
        if (gotPing)
        {
          CatchBall();
          /* Add delay between RX and TX */
          HAL_Delay(Radio.GetWakeupTime() + RX_TIME_MARGIN + BALL_HOLD_MS);
          APP_LOG(TS_ON, VLEVEL_L, "Slave  Tx start\n\r");
          RadioSend(RT_PONG);
        }
        else /* valid reception but not a PING as expected */
        {
          /* Set device as master and start again */
          isMaster = true;
          APP_LOG(TS_ON, VLEVEL_L, "Master Rx start\n\r");
          RadioRx();
        }
      }
      break;
    case TX:
      /* an ack has left the antenna: this is when the acknowledging board switches */
      LogEvents(rt_on_tx_done(&rt));
      APP_LOG(TS_ON, VLEVEL_L, "Rx start\n\r");
      RadioRx();
      break;
    case RX_TIMEOUT:
    case RX_ERROR:
      APP_LOG(TS_ON, VLEVEL_L, "#rt miss sf=%d pwr=%d\n\r", rt_cur_sf(&rt), rt_cur_pwr(&rt));
      LogEvents(rt_on_miss(&rt));
      if (isMaster == true)
      {
        /* Send the next PING frame */
        /* Add delay between RX and TX*/
        /* add random_delay to force sync between boards after some trials*/
        HAL_Delay(Radio.GetWakeupTime() + RX_TIME_MARGIN + random_delay);
        APP_LOG(TS_ON, VLEVEL_L, "Master Tx start\n\r");
        RadioSend(RT_PING);
      }
      else
      {
        APP_LOG(TS_ON, VLEVEL_L, "Slave Rx start\n\r");
        RadioRx();
      }
      break;
    case TX_TIMEOUT:
      APP_LOG(TS_ON, VLEVEL_L, "Slave Rx start\n\r");
      RadioRx();
      break;
    default:
      break;
  }
}

static void LogEvents(int ev)
{
  /* In the order rt_on_rx applies them; each line names the settings that event refers to. */
  static const struct { int bit; const char *name; } events[] = {
    { RT_EV_ADOPTED, "adopted" }, { RT_EV_COMMIT, "commit" }, { RT_EV_SWITCHED, "switched" },
    { RT_EV_ROLLBACK, "rollback" }, { RT_EV_FALLBACK, "fallback" } };
  for (unsigned i = 0; i < sizeof events / sizeof events[0]; i++)
  {
    if (!(ev & events[i].bit)) continue;
    rt_cfg_t c = rt_event_cfg(&rt, ev, events[i].bit);
    APP_LOG(TS_ON, VLEVEL_L, "#rt cfg sf=%d pwr=%d %s\n\r", rt_sf_of(c), rt_pwr_of(c), events[i].name);
  }
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
  uint8_t idx = GPIO_Pin == BUT1_Pin ? 0 : GPIO_Pin == BUT2_Pin ? 1 : GPIO_Pin == BUT3_Pin ? 2 : 3;
  UTIL_TIMER_Time_t now = UTIL_TIMER_GetCurrentTime();

  if (idx > 2 || now - buttonLastMs[idx] < BUTTON_DEBOUNCE_MS)
    return;
  buttonLastMs[idx] = now;
  buttonsPressed |= (uint8_t)(1 << idx);
  UTIL_SEQ_SetTask((1 << CFG_SEQ_Task_Buttons), CFG_SEQ_Prio_0);
}

static void Buttons_Process(void)
{
  uint8_t pressed;

  UTILS_ENTER_CRITICAL_SECTION();
  pressed = buttonsPressed;
  buttonsPressed = 0;
  UTILS_EXIT_CRITICAL_SECTION();

  if (pressed & 1)
  {
    markCount++;
    APP_LOG(TS_ON, VLEVEL_L, "#rt mark %u\n\r", markCount);
    Blink(1);
  }
  if (pressed & 2)
  {
    rt_press_pwr(&rt);
    APP_LOG(TS_ON, VLEVEL_L, "#rt propose sf=%d pwr=%d\n\r", rt_sf_of(rt.prop), rt_pwr_of(rt.prop));
    Blink((uint8_t)(rt.prop.pwr + 1));
  }
  if (pressed & 4)
  {
    rt_press_sf(&rt);
    APP_LOG(TS_ON, VLEVEL_L, "#rt propose sf=%d pwr=%d\n\r", rt_sf_of(rt.prop), rt_pwr_of(rt.prop));
    Blink((uint8_t)(rt.prop.sf + 1));
  }
}

static void Blink(uint8_t n)
{
  UTIL_TIMER_Stop(&timerBlink);
  HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, GPIO_PIN_SET); /* LED_GREEN */
  blinkLeft = (uint8_t)(n * 2 - 1);
  UTIL_TIMER_Start(&timerBlink);
}

static void OnBlinkEvent(void *context)
{
  HAL_GPIO_TogglePin(LED2_GPIO_Port, LED2_Pin); /* LED_GREEN */
  if (--blinkLeft > 0)
    UTIL_TIMER_Start(&timerBlink);
  else
    HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, GPIO_PIN_RESET);
}

static void OnledEvent(void *context)
{
  HAL_GPIO_TogglePin(LED2_GPIO_Port, LED2_Pin); /* LED_GREEN */
  HAL_GPIO_TogglePin(LED3_GPIO_Port, LED3_Pin); /* LED_RED */
  UTIL_TIMER_Start(&timerLed);
}

static void CatchBall(void)
{
  /* linked: stop the red/green "searching" blink */
  UTIL_TIMER_Stop(&timerLed);
  HAL_GPIO_WritePin(LED2_GPIO_Port, LED2_Pin, GPIO_PIN_RESET); /* LED_GREEN */
  HAL_GPIO_WritePin(LED3_GPIO_Port, LED3_Pin, GPIO_PIN_RESET); /* LED_RED */
  /* this board has the ball until OnTxDone */
  HAL_GPIO_WritePin(LED1_GPIO_Port, LED1_Pin, GPIO_PIN_SET); /* LED_BLUE */
}

/* USER CODE END PrFD */
