#!/usr/bin/env python3
"""STM32N6 USART1 中斷傳送安裝器（第一版，HAL 連結修正 1）。

既有區域事件＋A3 版本專用。預設唯讀檢查；--apply --build 套用並建置。
已套用且出現 HAL 缺失符號時：--repair-hal --build。
只處理本機來源與 IDE 登錄，不產生模型、不燒錄、不執行 Git 操作。

傳送政策：單一主迴圈生產者，完整 LF 文字列，4 KiB 有界佇列，
EVENT/ERROR 預留 256 bytes。滿載／過長列整列丟棄，計數於 UART_TX_STATS。
_write 回傳已交給記錄器的長度；這是可丟棄診斷記錄器，不提供送達保證。
所有丟棄與錯誤計數為零，才可用於正常事件／效能驗收。

PROFILE_IT 的 uart_enqueue_ms 與 prev_log_enqueue_ms 為 CPU 排隊耗時。
busy_ms 為 USART1 啟動到完成回呼的累計忙碌區間，含中斷延遲；
queued 包含尚未收到完成回呼的傳送中區段，completed_bytes 以完成區塊累計。
--self-test 使用模擬 HAL 檢查佇列，不能取代板端驗證。
"""
import argparse
from datetime import datetime
import difflib
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

PROJECT_NAME = "STM32N6570-DK_GettingStarted_InstanceSegmentation"

UART_HEADER = r'''#ifndef PROJECT_UART_IT_V1_H
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
'''

UART_SOURCE = r'''#include "project_uart_it.h"
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
'''

TEST_HAL = r'''#ifndef MOCK_HAL_H
#define MOCK_HAL_H
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { void *Instance; struct { uint32_t BaudRate; } Init; } UART_HandleTypeDef;
#define USART1 ((void *)(uintptr_t)1)
#define USART1_IRQn 159
#define __NVIC_PRIO_BITS 4U
#define USE_HAL_UART_REGISTER_CALLBACKS 0U
#define assert_param(x) assert(x)
uint32_t mock_get_primask(void);
void mock_set_primask(uint32_t value);
void mock_enable_sleep(void);
uint32_t mock_get_ipsr(void);
#define __get_PRIMASK() mock_get_primask()
#define __disable_irq() mock_set_primask(1U)
#define __set_PRIMASK(x) mock_set_primask(x)
#define __get_IPSR() mock_get_ipsr()
#define __DMB() do {} while (0)
#define __HAL_RCC_USART1_CLK_SLEEP_ENABLE() mock_enable_sleep()
uint32_t HAL_GetTick(void);
void HAL_NVIC_SetPriority(int irq, uint32_t preempt, uint32_t sub);
void HAL_NVIC_ClearPendingIRQ(int irq);
void HAL_NVIC_EnableIRQ(int irq);
void HAL_NVIC_DisableIRQ(int irq);
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart, const uint8_t *data, uint16_t n);
void HAL_UART_IRQHandler(UART_HandleTypeDef *uart);
#endif
'''

TEST_SOURCE = r'''#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "project_uart_it.c"

static uint32_t tick, primask, ipsr, enabled, sleep_enabled, finish_on_lock;
static HAL_StatusTypeDef forced_status;
static const uint8_t *hw_data;
static uint16_t hw_length;
static unsigned char received[200000];
static size_t received_length;
static UART_HandleTypeDef handle = { .Instance = USART1, .Init = { .BaudRate = 115200 } };

static void Finish(void);
uint32_t mock_get_primask(void) {
  if (finish_on_lock && !primask && hw_length) {
    finish_on_lock = 0;
    Finish();
  }
  return primask;
}
void mock_set_primask(uint32_t x) { primask = x; }
uint32_t mock_get_ipsr(void) { return ipsr; }
void mock_enable_sleep(void) { sleep_enabled = 1; }
uint32_t HAL_GetTick(void) { return tick; }
void HAL_NVIC_SetPriority(int irq, uint32_t p, uint32_t sub) {
  assert(irq == USART1_IRQn && p == 15 && sub == 15);
}
void HAL_NVIC_ClearPendingIRQ(int irq) { assert(irq == USART1_IRQn); }
void HAL_NVIC_EnableIRQ(int irq) { assert(irq == USART1_IRQn); enabled = 1; }
void HAL_NVIC_DisableIRQ(int irq) { assert(irq == USART1_IRQn); enabled = 0; }
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart, const uint8_t *data, uint16_t n) {
  assert(uart == &handle);
  if (forced_status != HAL_OK) return forced_status;
  assert(!hw_length && n > 0);
  hw_data = data; hw_length = n;
  return HAL_OK;
}
void HAL_UART_IRQHandler(UART_HandleTypeDef *uart) {
  assert(uart == &handle && hw_length);
  assert(received_length + hw_length <= sizeof(received));
  memcpy(received + received_length, hw_data, hw_length);
  received_length += hw_length;
  hw_length = 0;
  HAL_UART_TxCpltCallback(uart);
}
static void Finish(void) {
  assert(enabled && !primask);
  tick += 1;
  ipsr = 1;
  USART1_IRQHandler();
  ipsr = 0;
}
static void Drain(void) { unsigned guard = 0; while (hw_length) { assert(++guard < 10000); Finish(); } }
static void Reset(void) {
  tx_head = tx_tail = active_length = 0;
  busy_open = busy_started = busy_accumulated = 0;
  line_used = discard_line = last_report = 0;
  uart_port = NULL;
  counters = (ProjectUartStats){0};
  tick = primask = ipsr = enabled = sleep_enabled = finish_on_lock = 0;
  forced_status = HAL_OK; hw_length = 0; hw_data = NULL; received_length = 0;
  memset(received, 0, sizeof(received));
  ProjectUart_Init(&handle);
  assert(enabled && sleep_enabled);
}
static void Write(const char *s) { assert(ProjectUart_Write(s, (int)strlen(s)) == (int)strlen(s)); }
static void Expect(const char *s) { assert(received_length == strlen(s)); assert(!memcmp(received, s, strlen(s))); }

int main(void) {
  Reset();
  char text[] = "EVENT,1,ENTER,1\r\n";
  Write(text); memset(text, 'X', sizeof(text) - 1);
  assert(received_length == 0); /* 模擬 HAL 保存指標，尚未消費來源記憶體。 */
  Write("PROFILE_IT,2\r\n"); Drain();
  Expect("EVENT,1,ENTER,1\r\nPROFILE_IT,2\r\n");

  Reset();
  Write("EV"); Write("ENT,3,EX"); assert(hw_length == 0);
  Write("IT,0\r\nFRAME,4,49,0\r\nEND,4\r\n"); Drain();
  Expect("EVENT,3,EXIT,0\r\nFRAME,4,49,0\r\nEND,4\r\n");

  Reset();
  char line[512]; memset(line, 'A', sizeof(line)); line[511] = '\n';
  for (int i = 0; i < 7; i++) assert(ProjectUart_Write(line, sizeof(line)) == sizeof(line));
  assert(Queued() == 3584);
  assert(ProjectUart_Write(line, sizeof(line)) == sizeof(line));
  assert(counters.dropped_lines == 1 && counters.critical_drops == 0);
  Write("EVENT,8,ENTER,1\r\n");
  assert(counters.critical_drops == 0);
  Drain();
  assert(received_length == 3584 + strlen("EVENT,8,ENTER,1\r\n"));
  assert(!memcmp(received + 3584, "EVENT,8,ENTER,1\r\n", strlen("EVENT,8,ENTER,1\r\n")));

  Reset();
  char critical[256]; memset(critical, 'B', sizeof(critical));
  memcpy(critical, "EVENT,", 6); critical[255] = '\n';
  for (int i = 0; i < 16; i++) ProjectUart_Write(critical, sizeof(critical));
  assert(counters.dropped_lines == 1 && counters.critical_drops == 1);
  Drain(); assert(received_length == 3840);

  Reset();
  char oversized[600]; memset(oversized, 'Q', sizeof(oversized));
  memcpy(oversized, "EVENT,", 6); oversized[599] = '\n';
  ProjectUart_Write(oversized, sizeof(oversized));
  Write("EVENT,9,EXIT,0\r\n"); Drain();
  Expect("EVENT,9,EXIT,0\r\n");
  assert(counters.oversize_lines == 1 && counters.critical_drops == 1);

  Reset();
  /* 多次跨尾端、文字分段、在發布新 head 前收到舊傳送完成中斷。 */
  char expected[160000]; size_t expected_length = 0;
  for (unsigned i = 0; i < 1000; ++i) {
    char row[100]; int n = snprintf(row, sizeof(row), "DET,%u,0,918,4971,6309,9942,7265,1887\r\n", i);
    memcpy(expected + expected_length, row, (size_t)n); expected_length += (size_t)n;
    if (i % 3 == 0 && hw_length) finish_on_lock = 1;
    ProjectUart_Write(row, 3);
    ProjectUart_Write(row + 3, n - 3);
    if (i % 4 == 0) Drain();
  }
  Drain(); assert(received_length == expected_length);
  assert(!memcmp(received, expected, expected_length));
  assert(counters.dropped_lines == 0 && counters.completed_bytes == expected_length);

  Reset();
  primask = 1; Write("EVENT,1,ENTER,1\n"); assert(primask == 1);
  primask = 0; Drain();
  ipsr = 1; assert(ProjectUart_Write("x\n", 2) == -1); ipsr = 0;
  assert(counters.context_rejects == 1);

  Reset();
  forced_status = HAL_BUSY; Write("EVENT,2,ENTER,1\n");
  assert(counters.start_errors == 1 && counters.fault && !enabled);
  assert(ProjectUart_Write("x\n", 2) == -1);

  Reset(); Write("EVENT,2,ENTER,1\n");
  HAL_UART_ErrorCallback(&handle);
  assert(counters.hal_errors == 1 && counters.fault && !enabled);

  Reset(); tick = UINT32_MAX - 2U; Write("x\n");
  tick = 4; Drain();
  ProjectUartStats s; ProjectUart_GetStats(&s);
  assert(s.busy_ms == 8 && s.queued == 0);

  Reset(); ProjectUart_Announce(); Drain();
  assert(strstr((char *)received, "UART_TX_CONFIG,IT,115200,4096,512,256\r\n"));
  tick = 1000; ProjectUart_Service(); Drain();
  assert(strstr((char *)received, "UART_TX_STATS,"));
  size_t previous_length = received_length;
  ProjectUart_Service(); Drain(); assert(received_length == previous_length);
  puts("PASS: delayed consumption, fragmented lines, overflow reserve, event overflow,");
  puts("      oversize recovery, wraparound/order, completion interleaving, IRQ context,");
  puts("      mask restoration, HAL errors, tick rollover, status reporting.");
  return 0;
}
'''

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mask_c(text):
    # 保留長度與換行，使括號掃描不受字串／註解中的括號干擾。
    token = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    return re.sub(token, lambda m: re.sub(r'[^\n]', ' ', m.group()), text)


def function_span(text, name, return_type):
    masked = mask_c(text)
    matches = list(re.finditer(
        rf'\b{re.escape(return_type)}\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{', masked))
    require(len(matches) == 1, f"找不到唯一函式定義：{name}")
    match = matches[0]
    depth = 1
    for index in range(match.end(), len(masked)):
        if masked[index] == '{': depth += 1
        elif masked[index] == '}': depth -= 1
        if depth == 0:
            return match.start(), index + 1
    raise RuntimeError(f"函式括號不完整：{name}")


def once(text, old, new):
    require(text.count(old) == 1, "找不到唯一修改位置：" + old[:100])
    return text.replace(old, new, 1)


def paths(repo):
    app = repo / 'stm32ai-modelzoo-services/application_code/instance_segmentation/STM32N6'
    board = app / 'Application/STM32N6570-DK'
    return app, board, board / 'STM32CubeIDE'


def ide_link_path(ide, link):
    uri = link.findtext('locationURI') or link.findtext('location') or ''
    match = re.fullmatch(r'PARENT-(\d+)-PROJECT_LOC/(.+)', uri)
    if match:
        parent = ide
        for _ in range(int(match[1])):
            parent = parent.parent
        return (parent / match[2]).resolve()
    if uri.startswith('PROJECT_LOC/'):
        return (ide / uri[len('PROJECT_LOC/'):]).resolve()
    require(Path(uri).is_absolute(), '無法解析官方 HAL 的 IDE 連結：' + uri)
    return Path(uri).resolve()


def prepare_hal_dependencies(repo, project_text):
    """補齊 HAL_UART_IRQHandler 的連結相依；不設定 DMA 硬體。"""
    app, board, ide = paths(repo)
    hal_src = app / 'STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver/Src'
    conf_path = board / 'Inc/stm32n6xx_hal_conf.h'
    conf_original = conf_path.read_bytes()
    conf = conf_original.decode()
    active = mask_c(conf)
    require(re.search(r'^\s*#\s*define\s+HAL_UART_MODULE_ENABLED\b', active, re.M),
            'HAL_UART_MODULE_ENABLED 未啟用，與目前專案不同。')
    if not re.search(r'^\s*#\s*define\s+HAL_DMA_MODULE_ENABLED\b', active, re.M):
        # 僅啟用官方驅動的編譯入口；沒有呼叫 HAL_DMA_Init 或 UART DMA API。
        uart_define = re.search(r'^\s*#\s*define\s+HAL_UART_MODULE_ENABLED[^\r\n]*', active, re.M)
        line_end = uart_define.end()
        newline = '\r\n' if '\r\n' in conf else '\n'
        conf = (conf[:line_end] + newline +
                '#define HAL_DMA_MODULE_ENABLED /* UART IRQ link dependency */' + conf[line_end:])

    root = ET.fromstring(project_text)
    require(root.findtext('name') == PROJECT_NAME, 'IDE 專案名稱與目前已知專案不同。')
    links = root.findall('./linkedResources/link')
    uart_name = 'stm32n6xx_hal_uart.c'
    uart_links = [x for x in links if (x.findtext('name') or '').endswith('/' + uart_name)]
    require(len(uart_links) == 1 and uart_links[0].findtext('type') == '1',
            '找不到唯一官方 UART 驅動檔案連結。')
    template = uart_links[0]
    require(ide_link_path(ide, template) == (hal_src / uart_name).resolve(),
            '官方 UART 驅動連結未指向本專案既有 SDK。')
    blocks = [m.group() for m in re.finditer(r'<link>\s*[\s\S]*?</link>', project_text)
              if ET.fromstring(m.group()).findtext('name') == template.findtext('name')]
    require(len(blocks) == 1, '無法定位官方 UART 驅動的 XML 區塊。')

    configs = [x for x in ET.parse(ide / '.cproject').getroot().findall('.//configuration')
               if x.get('name') == 'ModelZoo']
    require(len(configs) == 1, '找不到唯一 ModelZoo 組態。')
    entries = configs[0].findall('./sourceEntries/entry')
    root_entries = [x for x in entries if x.get('name') == '']
    require(len(root_entries) == 1, 'ModelZoo 原始碼納入方式已改變。')
    dependencies = {
        'stm32n6xx_hal_dma.c': (('HAL_DMA_Abort', 'HAL_StatusTypeDef'),
                              ('HAL_DMA_Abort_IT', 'HAL_StatusTypeDef')),
        'stm32n6xx_hal_uart_ex.c': (('HAL_UARTEx_WakeupCallback', 'void'),
                                  ('HAL_UARTEx_TxFifoEmptyCallback', 'void'),
                                  ('HAL_UARTEx_RxFifoFullCallback', 'void')),
    }
    new_blocks = []
    for filename, functions in dependencies.items():
        source = hal_src / filename
        require(source.is_file(), '既有 SDK 缺少相依來源檔：' + str(source))
        source_text = source.read_text()
        for symbol, return_type in functions:
            function_span(source_text, symbol, return_type)
        candidates = [x for x in links if (x.findtext('name') or '').endswith('/' + filename)]
        require(len(candidates) <= 1, 'IDE 重複登錄 HAL 來源：' + filename)
        link = candidates[0] if candidates else ET.fromstring(blocks[0].replace(uart_name, filename))
        require(link.findtext('type') == '1' and ide_link_path(ide, link) == source.resolve(),
                'HAL 相依來源的既有 IDE 連結不同：' + filename)
        name = link.findtext('name')
        for exclude in root_entries[0].get('excluding', '').split('|'):
            exclude = exclude.rstrip('/')
            if exclude:
                require(not (name == exclude or name.startswith(exclude + '/') or
                             fnmatch.fnmatchcase(name, exclude)),
                        'ModelZoo 已排除此 HAL 來源，請核對既有設定：' + name)
        for item in configs[0].findall('.//fileInfo'):
            require(not (item.get('resourcePath') == name and item.get('exclude') == 'true'),
                    'ModelZoo fileInfo 已排除此 HAL 來源：' + name)
        if not candidates:
            new_blocks.append('\t\t' + blocks[0].replace(uart_name, filename) + '\n')
    if new_blocks:
        close = re.search(r'(?m)^[ \t]*</linkedResources>', project_text)
        require(close is not None, '無法定位 IDE linkedResources 結尾。')
        project_text = project_text[:close.start()] + ''.join(new_blocks) + project_text[close.start():]
        ET.fromstring(project_text)
    return project_text, conf_original, conf.encode()


def repair_hal(repo):
    verify_applied(repo)
    _, board, ide = paths(repo)
    project = ide / '.project'
    conf_path = board / 'Inc/stm32n6xx_hal_conf.h'
    before_project = project.read_bytes()
    changed_project, before_conf, changed_conf = prepare_hal_dependencies(repo, before_project.decode())
    originals, changes = {}, {}
    for path, before, after in ((project, before_project, changed_project.encode()),
                               (conf_path, before_conf, changed_conf)):
        if before != after:
            originals[path], changes[path] = before, after
    script = repo / 'scripts/install_uart_it_v1.py'
    script_data = Path(__file__).read_bytes()
    if not script.exists() or script.read_bytes() != script_data:
        if script.exists():
            previous = script.read_bytes()
            require(sha(previous) == '00d5731c56ae11678facc41c5203c24b039996d697d8899d7f24ac9388924e46',
                    '專案內安裝器與先前交付版本不同，保留其修改並停止。')
            originals[script] = previous
        changes[script] = script_data
    if changes:
        print('HAL 連結修復，預計修改：')
        for path in changes: print(' ', path.relative_to(repo))
        apply_changes(repo, originals, changes)
    else:
        print('HAL 相依來源已完整登錄，沒有重複修改。')
    print('已核對：HAL DMA 核心、UART 擴充來源與五個缺失函式的定義。')


def prepare(repo):
    app, board, ide = paths(repo)
    main = board / 'Src/main.c'
    header = board / 'Inc/project_uart_it.h'
    source = board / 'Src/project_uart_it.c'
    project = ide / '.project'
    cproject = ide / '.cproject'
    hal_root = app / 'STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver'
    for p in (main, project, cproject, board / 'Inc/project_region_event.h',
              board / 'Inc/stm32n6xx_hal_conf.h', hal_root / 'Inc/stm32n6xx_hal_rcc.h',
              hal_root / 'Src/stm32n6xx_hal_uart.c'):
        require(p.is_file(), f"缺少現有專案檔案：{p}")
    require(not source.exists() and not header.exists(),
            "中斷傳送模組已存在，避免重複套用；已套用版本可直接使用 --build。")
    originals = {p: p.read_bytes() for p in (main, project)}
    main_text = originals[main].decode('utf-8')
    project_text = originals[project].decode('utf-8')
    require('PROJECT_A3_PROFILE_V1' in main_text and 'project_region_event.h' in main_text,
            "主程式不是目前的 A3＋區域事件版本。")
    require('project_uart_it.h' not in main_text and 'PROFILE_IT,' not in main_text,
            "主程式已有中斷傳送整合標記。")

    conf = (board / 'Inc/stm32n6xx_hal_conf.h').read_text()
    require(re.search(r'^\s*#\s*define\s+USE_HAL_UART_REGISTER_CALLBACKS\s+0U?\b', conf, re.M),
            "UART 回呼設定已改變；本版需要 USE_HAL_UART_REGISTER_CALLBACKS = 0U。")
    for p in sorted((board / 'Src').glob('*.c')):
        masked = mask_c(p.read_text(errors='replace'))
        for symbol in ('USART1_IRQHandler', 'HAL_UART_TxCpltCallback', 'HAL_UART_ErrorCallback'):
            require(not re.search(rf'\b{symbol}\s*\([^;{{}}]*\)\s*\{{', masked),
                    f"{p.name} 已定義 {symbol}，保留既有內容並停止。")
    rcc = (hal_root / 'Inc/stm32n6xx_hal_rcc.h').read_text()
    require('__HAL_RCC_USART1_CLK_SLEEP_ENABLE' in rcc,
            "目前 HAL 找不到 USART1 睡眠時脈巨集。")
    hal_uart = (hal_root / 'Src/stm32n6xx_hal_uart.c').read_text()
    first, last = function_span(hal_uart, 'UART_EndTransmit_IT', 'void')
    finish = mask_c(hal_uart[first:last])
    ready = re.search(r'\bgState\s*=\s*HAL_UART_STATE_READY\s*;', finish)
    callback = finish.find('HAL_UART_TxCpltCallback')
    require(ready is not None and callback > ready.end(),
            "目前 HAL 的傳送完成順序與本版預期不同：需在回呼前先恢復 READY。")

    root = ET.fromstring(project_text)
    require(root.findtext('name') == PROJECT_NAME, "IDE 專案名稱與目前已知專案不同。")
    links = root.findall('./linkedResources/link')
    main_links = [x for x in links if x.findtext('name') == 'Application/main.c']
    require(len(main_links) == 1, "缺少唯一的 Application/main.c 編譯連結。")
    old_uri = main_links[0].findtext('locationURI')
    require(main_links[0].findtext('type') == '1' and old_uri == 'PARENT-1-PROJECT_LOC/Src/main.c',
            "主程式的 IDE 連結方式已改變。")
    require(not any(x.findtext('name') == 'Application/project_uart_it.c' for x in links),
            "IDE 已登錄中斷傳送模組。")
    configs = ET.parse(cproject).getroot().findall('.//configuration')
    configs = [x for x in configs if x.get('name') == 'ModelZoo']
    require(len(configs) == 1, "找不到唯一 ModelZoo 組態。")
    entries = configs[0].findall('./sourceEntries/entry')
    require(any(x.get('name') == '' for x in entries), "ModelZoo 原始碼納入方式已改變。")
    for entry in entries:
        for exclude in entry.get('excluding', '').split('|'):
            require(exclude not in ('Application', 'Application/*', 'Application/project_uart_it.c'),
                    "ModelZoo 排除了新增模組所屬的 Application 路徑。")

    first, last = function_span(main_text, '_write', 'int')
    old_write = main_text[first:last]
    require(re.search(r'\bHAL_UART_Transmit\s*\(', mask_c(old_write)),
            "現有 _write 已不是同步 UART 版本。")
    replacement = '''int _write(int file, char *ptr, int len)
{
  if ((file != STDOUT_FILENO) && (file != STDERR_FILENO)) {
    errno = EBADF;
    return -1;
  }
  return ProjectUart_Write(ptr, len);
}'''
    changed = main_text[:first] + replacement + main_text[last:]
    changed = once(changed, '#include "main.h"',
                   '#include "main.h"\n#include "project_uart_it.h"\n#include <errno.h>')
    changed = once(changed, '  CONSOLE_Config();',
                   '  CONSOLE_Config();\n  ProjectUart_Init(&huart1);')
    changed = once(changed, '  printf("REGION_CONFIG,',
                   '  ProjectUart_Announce();\n  printf("REGION_CONFIG,')
    changed = once(changed, 'PROFILE_HEADER,frame,', 'PROFILE_IT_HEADER,frame,')
    changed = once(changed, 'region_ms,uart_ms,display_ms,',
                   'region_ms,uart_enqueue_ms,display_ms,')
    changed = once(changed, 'prev_cycle_ms,prev_log_ms,warmup',
                   'prev_cycle_ms,prev_log_enqueue_ms,warmup')
    changed = once(changed, 'printf("PROFILE,%lu', 'printf("PROFILE_IT,%lu')
    changed = once(changed, '    prev_log_ms = HAL_GetTick() - log_start;',
                   '    ProjectUart_Service();\n    prev_log_ms = HAL_GetTick() - log_start;')

    new_link = '''\t\t<link>
\t\t\t<name>Application/project_uart_it.c</name>
\t\t\t<type>1</type>
\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/project_uart_it.c</locationURI>
\t\t</link>
'''
    close = re.search(r'(?m)^[ \t]*</linkedResources>', project_text)
    require(close is not None, "無法定位 IDE linkedResources 結尾。")
    new_project = project_text[:close.start()] + new_link + project_text[close.start():]
    ET.fromstring(new_project)
    new_project, conf_original, new_conf = prepare_hal_dependencies(repo, new_project)
    script_copy = repo / 'scripts/install_uart_it_v1.py'
    script_data = Path(__file__).read_bytes()
    require(not script_copy.exists() or script_copy.read_bytes() == script_data,
            f"{script_copy} 已有不同內容，保留既有檔案並停止。")
    changes = {
        main: changed.encode(), header: UART_HEADER.encode(), source: UART_SOURCE.encode(),
        project: new_project.encode(), script_copy: script_data,
    }
    conf_path = board / 'Inc/stm32n6xx_hal_conf.h'
    if new_conf != conf_original:
        originals[conf_path] = conf_original
        changes[conf_path] = new_conf
    if script_copy.exists():
        originals[script_copy] = script_copy.read_bytes()
    return originals, changes


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def apply_changes(repo, originals, changes):
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output = repo / 'results/uart_it' / ('install_' + stamp)
    output.mkdir(parents=True, exist_ok=False)
    records, diff = [], []
    for path, after in changes.items():
        relative = path.relative_to(repo)
        before = originals.get(path)
        require(path.read_bytes() == before if before is not None else not path.exists(),
                f"套用前檔案內容改變：{path}")
        if before is not None:
            backup = output / 'before' / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        record = {'path': str(relative), 'before_sha256': sha(before) if before is not None else None,
                  'after_sha256': sha(after), 'created': before is None}
        records.append(record)
        # 安裝器本身另以完整原始檔保存；差異檔記錄實際韌體與 IDE 變更。
        if relative.as_posix() != 'scripts/install_uart_it_v1.py':
            label = relative.as_posix()
            diff.extend(difflib.unified_diff(
                (before or b'').decode().splitlines(True), after.decode().splitlines(True),
                fromfile='a/' + label if before is not None else '/dev/null', tofile='b/' + label))
    patch = repo / 'patches' / ('uart_it_v1_' + stamp + '.patch')
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(''.join(diff))
    record = {'version': 'uart_it_v1_hal_fix1', 'repo': str(repo), 'files': records,
              'patch': str(patch.relative_to(repo)), 'status': 'prepared'}
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    applied = []
    try:
        for path, data in changes.items():
            before = originals.get(path)
            require(path.read_bytes() == before if before is not None else not path.exists(),
                    f"檔案內容在套用期間改變：{path}")
            atomic_write(path, data)
            applied.append(path)
    except BaseException:
        for path in reversed(applied):
            # 僅回復本安裝器剛寫入且未再改變的內容。
            if path.read_bytes() == changes[path]:
                if path in originals: atomic_write(path, originals[path])
                else: path.unlink()
        record['status'] = 'rolled_back'
        manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
        raise
    record['status'] = 'applied'
    manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print('修改已套用。備份與版本紀錄：', output)
    print('修改差異：', patch)
    return output


def verify_applied(repo):
    _, board, ide = paths(repo)
    require((board / 'Src/project_uart_it.c').read_text() == UART_SOURCE,
            '中斷傳送來源與本安裝器不同。')
    require((board / 'Inc/project_uart_it.h').read_text() == UART_HEADER,
            '中斷傳送標頭與本安裝器不同。')
    main = (board / 'Src/main.c').read_text()
    for marker in ('ProjectUart_Init(&huart1)', 'ProjectUart_Service();',
                   'return ProjectUart_Write(ptr, len);', 'PROFILE_IT_HEADER,'):
        require(marker in main, '主程式缺少整合標記：' + marker)
    require('Application/project_uart_it.c' in (ide / '.project').read_text(),
            'IDE 未登錄新增來源。')


def build_firmware(repo):
    verify_applied(repo)
    app, board, ide = paths(repo)
    project_text = (ide / '.project').read_text()
    expected_project, before_conf, expected_conf = prepare_hal_dependencies(repo, project_text)
    require(expected_project == project_text and before_conf == expected_conf,
            '尚未補齊 HAL 相依來源，請用此修正版執行 --repair-hal --build。')
    cubeide = Path('/opt/st/stm32cubeide_2.2.0/stm32cubeide')
    toolbin = Path('/opt/st/stm32cubeide_2.2.0/plugins/'
                   'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
                   '14.3.rel1.linux64_1.0.100.202602081740/tools/bin')
    nm = toolbin / 'arm-none-eabi-nm'
    for tool in (cubeide, nm): require(tool.is_file(), f'找不到既有工具：{tool}')
    # 使用獨立工作區，讓 IDE 首次匯入更新後的 .project 連結。
    workspace = Path.home() / '.cache/stm32n6_course14_uart_it_halfix1_cubeide'
    workspace.mkdir(parents=True, exist_ok=True)
    log = repo / 'logs' / ('build_uart_it_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [str(cubeide), '--launcher.suppressErrors', '-nosplash',
               '-application', 'org.eclipse.cdt.managedbuilder.core.headlessbuild',
               '-data', str(workspace), '-import', str(ide), '-no-indexer',
               '-printErrorMarkers', '-build', PROJECT_NAME + '/ModelZoo']
    print('\n使用已確認的 ModelZoo 建置命令：\n' + shlex.join(command), flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors='replace')
    try:
        with log.open('w') as stream:
            for line in process.stdout:
                print(line, end='', flush=True)
                stream.write(line)
        status = process.wait()
    except BaseException:
        process.terminate()
        process.wait(timeout=30)
        raise
    require(status == 0, f'建置失敗（結束碼 {status}）；保留修改與日誌：{log}')
    require(re.search(r'Build Finished\.\s+0 errors', log.read_text()) is not None,
            f'未確認零錯誤的建置完成訊息，請保留日誌檢查：{log}')
    elf = ide / 'ModelZoo' / (PROJECT_NAME + '.elf')
    require(elf.is_file(), '建置後未找到 ELF。')
    data = elf.read_bytes()
    for marker in (b'UART_TX_CONFIG,IT', b'PROFILE_IT_HEADER,', b'PROFILE_IT,', b'EVENT,'):
        require(marker in data, 'ELF 缺少新版本標記：' + marker.decode())
    symbols = subprocess.check_output([str(nm), '-S', '--defined-only', str(elf)], text=True)
    for name in ('USART1_IRQHandler', 'HAL_UART_TxCpltCallback', 'HAL_UART_ErrorCallback',
                 'ProjectUart_Write', 'ProjectUart_Service'):
        require(re.search(rf'^\S+\s+\S+\s+T\s+{name}$', symbols, re.M),
                f'ELF 缺少強符號 {name}；中斷模組可能沒有納入建置。')
    for name in ('HAL_UART_IRQHandler', 'HAL_DMA_Abort', 'HAL_DMA_Abort_IT',
                 'HAL_UARTEx_WakeupCallback', 'HAL_UARTEx_TxFifoEmptyCallback',
                 'HAL_UARTEx_RxFifoFullCallback'):
        require(re.search(rf'^\S+\s+\S+\s+[TW]\s+{name}$', symbols, re.M),
                'ELF 缺少官方 HAL 中斷相依函式：' + name)
    ring = re.search(r'^(\S+)\s+(\S+)\s+[bB]\s+uart_tx_ring$', symbols, re.M)
    require(ring is not None, 'ELF 找不到 UART 環形緩衝區。')
    address, length = (int(x, 16) for x in ring.groups())
    require(length == 4096 and 0x34000000 <= address and address + length <= 0x34100000,
            'UART 環形緩衝區未配置在預期的應用程式 SRAM1。')
    verify_applied(repo)
    record = {'elf': str(elf), 'elf_sha256': sha(data), 'log': str(log),
              'uart_ring_address': hex(address), 'uart_ring_bytes': length,
              'strong_irq_and_callbacks': True, 'hal_irq_dependencies_verified': True,
              'installer_revision': 'uart_it_v1_hal_fix1', 'flashed': False}
    result = repo / 'results/uart_it' / ('build_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print('\n中斷處理函式、回呼與新量測格式檢查通過。')
    print(f'UART 環形緩衝區：0x{address:08X}，{length} bytes；另有 512-byte 組列緩衝區及控制資料。')
    print('ELF：', elf)
    print('SHA-256：', sha(data))
    print('建置紀錄：', result)
    print('本步完成建置，尚未燒錄。')


def self_test():
    compiler = shutil.which('gcc') or shutil.which('cc')
    require(compiler is not None, '主機自我測試需要本機 C 編譯器（gcc 或 cc）。')
    with tempfile.TemporaryDirectory(prefix='uart_it_test_') as directory:
        root = Path(directory)
        for name, text in [('project_uart_it.h', UART_HEADER), ('project_uart_it.c', UART_SOURCE),
                           ('stm32n6xx_hal.h', TEST_HAL), ('test_uart_it.c', TEST_SOURCE)]:
            (root / name).write_text(text)
        binary = root / 'test_uart_it'
        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(root), str(root / 'test_uart_it.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('以上為主機模擬測試；真實 HAL、中斷與攝影機同時運作仍需板端驗證。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path,
                        default=Path.home() / 'STM32N6ai/course14_yolov8n_seg_n6')
    parser.add_argument('--apply', action='store_true', help='備份後套用修改')
    parser.add_argument('--build', action='store_true', help='使用既有 ModelZoo 組態建置並核對 ELF')
    parser.add_argument('--repair-hal', action='store_true', help='對已套用版本備份並補齊官方 HAL 來源登錄')
    parser.add_argument('--self-test', action='store_true', help='使用主機模擬 HAL 驗證佇列邏輯')
    args = parser.parse_args()
    require(not (args.apply and args.repair_hal), '--apply 與 --repair-hal 請擇一使用。')
    repo = args.repo.expanduser().resolve()
    if args.self_test:
        self_test()
        if not args.apply and not args.build and not args.repair_hal: return
    if args.repair_hal:
        repair_hal(repo)
    elif args.apply or not args.build:
        originals, changes = prepare(repo)
        print('檢查通過，預計修改：')
        for path in changes: print(' ', path.relative_to(repo))
        if not args.apply:
            print('唯讀檢查完成；套用並建置使用 --apply --build。')
            return
        apply_changes(repo, originals, changes)
    if args.build: build_firmware(repo)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ET.ParseError, subprocess.CalledProcessError) as error:
        raise SystemExit('停止：' + str(error))
