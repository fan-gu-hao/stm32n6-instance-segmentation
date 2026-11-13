#include "project_uart_it.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#if USE_HAL_UART_REGISTER_CALLBACKS != 0U
#error "This module uses the HAL weak UART callbacks (registration must be disabled)."
#endif

_Static_assert((PROJECT_UART_TX_CAPACITY & (PROJECT_UART_TX_CAPACITY - 1U)) == 0U,
               "UART queue capacity must be a power of two");
_Static_assert(PROJECT_UART_TX_CAPACITY <= 65536U, "HAL TX length is uint16_t");
_Static_assert(PROJECT_UART_TX_LINE_MAX + PROJECT_UART_TX_RESERVE < PROJECT_UART_TX_CAPACITY,
               "UART queue cannot hold a normal line and the critical reserve");

/* 一格保留用於區分空／滿。包括傳送中區段，直到完成中斷後才釋放。
 * 一般 .bss，配置於應用程式 SRAM；CPU 寫入、CPU 中斷讀取，未使用 DMA。
 */
static uint8_t uart_tx_ring[PROJECT_UART_TX_CAPACITY];
static char uart_line[PROJECT_UART_TX_LINE_MAX];
static uint32_t line_used, discard_line, last_report;
static UART_HandleTypeDef *uart_port;
static volatile uint32_t tx_head, tx_tail, active_length;
static volatile uint32_t busy_open, busy_started, busy_accumulated;
static volatile ProjectUartStats counters;

static uint32_t Lock(void)
{
  uint32_t saved = __get_PRIMASK();
  __disable_irq();
  __DMB();
  return saved;
}

static void Unlock(uint32_t saved)
{
  __DMB();
  __set_PRIMASK(saved);
}

static uint32_t Queued(void)
{
  return (tx_head - tx_tail) & (PROJECT_UART_TX_CAPACITY - 1U);
}

static void CloseBusy(void)
{
  if (busy_open) {
    busy_accumulated += HAL_GetTick() - busy_started;
    busy_open = 0U;
  }
}

/* 呼叫端需持有極短的臨界區，或已在本 UART 中斷內。
 * 此處不複製文字、不格式化、不等待硬體完成。
 */
static void StartNext(void)
{
  if (active_length || counters.fault) return;
  uint32_t length = Queued();
  if (!length) { CloseBusy(); return; }
  uint32_t contiguous = PROJECT_UART_TX_CAPACITY - tx_tail;
  if (length > contiguous) length = contiguous;

  active_length = length;
  if (!busy_open) {
    busy_started = HAL_GetTick();
    busy_open = 1U;
  }
  HAL_StatusTypeDef status = HAL_UART_Transmit_IT(
      uart_port, &uart_tx_ring[tx_tail], (uint16_t)length);
  if (status != HAL_OK) {
    /* 不忙等 HAL_BUSY，也不把同一段資料重複交給其他傳送者。 */
    active_length = 0U;
    counters.start_errors++;
    counters.fault = 1U;
    CloseBusy();
    HAL_NVIC_DisableIRQ(USART1_IRQn);
  }
}

static int CriticalLine(const char *data, uint32_t length)
{
  return length >= 6U &&
      (!memcmp(data, "EVENT,", 6U) || !memcmp(data, "ERROR,", 6U));
}

static void Dropped(int critical)
{
  counters.dropped_lines++;
  if (critical) counters.critical_drops++;
}

static int QueueLine(const char *data, uint32_t length, int critical)
{
  /* 單一主程式生產者；中斷只會釋放空間，故此快照可以保守估計可用空間。 */
  uint32_t head = tx_head;
  uint32_t free_space = PROJECT_UART_TX_CAPACITY - 1U - Queued();
  uint32_t reserve = critical ? 0U : PROJECT_UART_TX_RESERVE;
  if (counters.fault || length > PROJECT_UART_TX_LINE_MAX ||
      free_space < length + reserve) {
    Dropped(critical);
    return 0;
  }
  uint32_t first = PROJECT_UART_TX_CAPACITY - head;
  if (first > length) first = length;
  /* 複製期間保留中斷；尚未發布 head，傳送者不會看到未完成的資料。 */
  memcpy(&uart_tx_ring[head], data, first);
  memcpy(uart_tx_ring, data + first, length - first);

  uint32_t saved = Lock();
  if (counters.fault) {
    Unlock(saved);
    Dropped(critical);
    return 0;
  }
  __DMB();
  tx_head = (head + length) & (PROJECT_UART_TX_CAPACITY - 1U);
  uint32_t used = Queued();
  if (used > counters.high_water) counters.high_water = used;
  StartNext();
  Unlock(saved);
  return counters.fault == 0U;
}

void ProjectUart_Init(UART_HandleTypeDef *uart)
{
  /* 綁定既有 USART1；不重新初始化 GPIO、鮑率或 UART。 */
  assert_param(uart != NULL);
  assert_param(uart->Instance == USART1);
  assert_param(uart_port == NULL);
  uart_port = uart;
  __HAL_RCC_USART1_CLK_SLEEP_ENABLE();
  uint32_t lowest = (1U << __NVIC_PRIO_BITS) - 1U;
  HAL_NVIC_SetPriority(USART1_IRQn, lowest, lowest);
  HAL_NVIC_ClearPendingIRQ(USART1_IRQn);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

int ProjectUart_Write(const char *data, int length)
{
  if (length < 0 || (length && !data)) { errno = EINVAL; return -1; }
  if (!length) return 0;
  if (__get_IPSR() != 0U) {
    uint32_t saved = Lock();
    counters.context_rejects++;
    Unlock(saved);
    errno = EPERM;
    return -1;
  }
  if (!uart_port || counters.fault) { errno = EIO; return -1; }

  for (int i = 0; i < length; ++i) {
    char c = data[i];
    if (discard_line || line_used == sizeof(uart_line)) {
      discard_line = 1U;
      if (c == '\n') {
        counters.oversize_lines++;
        Dropped(CriticalLine(uart_line, line_used));
        discard_line = line_used = 0U;
      }
      continue;
    }
    uart_line[line_used++] = c;
    if (c == '\n') {
      (void)QueueLine(uart_line, line_used, CriticalLine(uart_line, line_used));
      line_used = 0U;
    }
  }
  return length;
}

void USART1_IRQHandler(void)
{
  counters.irq_calls++;
  if (uart_port && !counters.fault) HAL_UART_IRQHandler(uart_port);
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart != uart_port || counters.fault || !active_length) return;
  /* HAL 在此回呼前，已將傳送狀態改為 READY。 */
  tx_tail = (tx_tail + active_length) & (PROJECT_UART_TX_CAPACITY - 1U);
  counters.completed_bytes += active_length;
  active_length = 0U;
  StartNext();
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if (uart != uart_port) return;
  counters.hal_errors++;
  counters.fault = 1U;
  CloseBusy();
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  /* 傳輸故障保留計數，等待人工重設；不在中斷中 printf 或重試。 */
}

void ProjectUart_GetStats(ProjectUartStats *stats)
{
  uint32_t saved = Lock();
  *stats = counters;
  stats->queued = Queued();
  stats->busy_ms = busy_accumulated +
      (busy_open ? HAL_GetTick() - busy_started : 0U);
  Unlock(saved);
}

void ProjectUart_Announce(void)
{
  /* 先把既有 stdio 啟動文字排入佇列，維持訊息順序。 */
  fflush(stdout);
  char text[128];
  int n = snprintf(text, sizeof(text), "UART_TX_CONFIG,IT,%lu,%u,%u,%u\r\n",
      (unsigned long)uart_port->Init.BaudRate, PROJECT_UART_TX_CAPACITY,
      PROJECT_UART_TX_LINE_MAX, PROJECT_UART_TX_RESERVE);
  if (n > 0 && (size_t)n < sizeof(text)) (void)ProjectUart_Write(text, n);
  static const char header[] =
      "UART_TX_STATS_HEADER,queued,high_water,dropped_lines,critical_drops,"
      "oversize_lines,start_errors,hal_errors,context_rejects,completed_bytes,"
      "irq_calls,busy_ms,fault\r\n";
  (void)ProjectUart_Write(header, (int)(sizeof(header) - 1U));
}

void ProjectUart_Service(void)
{
  uint32_t now = HAL_GetTick();
  if (now - last_report < 1000U || counters.fault) return;
  last_report = now;
  ProjectUartStats s;
  ProjectUart_GetStats(&s);
  char text[256];
  int n = snprintf(text, sizeof(text),
      "UART_TX_STATS,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu\r\n",
      (unsigned long)s.queued, (unsigned long)s.high_water,
      (unsigned long)s.dropped_lines, (unsigned long)s.critical_drops,
      (unsigned long)s.oversize_lines, (unsigned long)s.start_errors,
      (unsigned long)s.hal_errors, (unsigned long)s.context_rejects,
      (unsigned long)s.completed_bytes, (unsigned long)s.irq_calls,
      (unsigned long)s.busy_ms, (unsigned long)s.fault);
  if (n > 0 && (size_t)n < sizeof(text)) (void)QueueLine(text, (uint32_t)n, 0);
}
