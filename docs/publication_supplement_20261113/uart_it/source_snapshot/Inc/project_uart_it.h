#ifndef PROJECT_UART_IT_V1_H
#define PROJECT_UART_IT_V1_H

#include "stm32n6xx_hal.h"

#define PROJECT_UART_TX_CAPACITY 4096U
#define PROJECT_UART_TX_LINE_MAX 512U
#define PROJECT_UART_TX_RESERVE 256U

typedef struct {
  uint32_t queued, high_water, dropped_lines, critical_drops;
  uint32_t oversize_lines, start_errors, hal_errors, context_rejects;
  uint32_t completed_bytes, irq_calls, busy_ms, fault;
} ProjectUartStats;

/* 僅供單一主迴圈使用；不支援從中斷或多個工作執行緒呼叫輸出。 */
void ProjectUart_Init(UART_HandleTypeDef *uart);
/* 逐列診斷介面：文字複製到內部儲存，遇到 LF 才提交完整列。
 * 回傳長度表示文字已交給記錄器，不表示已送達電腦。
 * 滿載或過長的列整列丟棄，並反映在統計計數。
 * EVENT/ERROR 可使用預留空間，仍須檢查 critical_drops。
 */
int ProjectUart_Write(const char *data, int length);
void ProjectUart_GetStats(ProjectUartStats *stats);
void ProjectUart_Announce(void);
void ProjectUart_Service(void);

#endif
