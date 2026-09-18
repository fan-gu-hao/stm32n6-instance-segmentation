#ifndef PROJECT_REGION_EVENT_V1
#define PROJECT_REGION_EVENT_V1
#include <math.h>

/* 座標以 10000 表示影像全寬或全高；區域邊界包含在內。 */
#define REGION_X_MIN 2000U
#define REGION_X_MAX 8000U
#define REGION_Y_MIN 2000U
#define REGION_Y_MAX 10000U
#define REGION_ENTER_FRAMES 3U
#define REGION_EXIT_FRAMES 5U
#define REGION_CAPTURE_TIMEOUT_MS 2000U

#if REGION_X_MIN >= REGION_X_MAX || REGION_X_MAX > 10000U || \
    REGION_Y_MIN >= REGION_Y_MAX || REGION_Y_MAX > 10000U || \
    REGION_ENTER_FRAMES == 0 || REGION_EXIT_FRAMES == 0
#error "Invalid region configuration"
#endif

static struct {
  uint32_t occupied, valid, hits, misses, people;
} project_region;

static void Region_Invalidate(void)
{
  project_region.valid = 0;
  project_region.hits = project_region.misses = project_region.people = 0;
  /* 保留最後的占用狀態；資料失效不等於離開。 */
}

static const char *Region_Update(const iseg_pp_out_t *p)
{
  if (!p || (int32_t)p->nb_detect < 0 ||
      p->nb_detect > AI_YOLOV8_SEG_PP_MAX_BOXES_LIMIT ||
      (p->nb_detect && !p->pOutBuff))
  {
    Region_Invalidate();
    return NULL;
  }

  uint32_t people = 0;
  const iseg_pp_outBuffer_t *boxes = p->pOutBuff;
  for (int32_t i = 0; i < (int32_t)p->nb_detect; ++i)
  {
    const iseg_pp_outBuffer_t *b = &boxes[i];
    if (b->class_index != 0) continue;
    if (!isfinite(b->conf)) { Region_Invalidate(); return NULL; }
    if (b->conf < AI_YOLOV8_SEG_PP_CONF_THRESHOLD) continue;
    if (!isfinite(b->x_center) || !isfinite(b->y_center) ||
        !isfinite(b->width) || !isfinite(b->height) ||
        b->width <= 0 || b->height <= 0)
    {
      Region_Invalidate();
      return NULL;
    }

    /* 使用原始預測框的底邊中心，超出影像時不夾回區域。 */
    const float x = b->x_center * 10000.0f;
    const float y = (b->y_center + b->height * 0.5f) * 10000.0f;
    if (x >= REGION_X_MIN && x <= REGION_X_MAX &&
        y >= REGION_Y_MIN && y <= REGION_Y_MAX) ++people;
  }

  project_region.valid = 1;
  project_region.people = people;
  if (people)
  {
    project_region.misses = 0;
    if (project_region.hits < REGION_ENTER_FRAMES) ++project_region.hits;
    if (!project_region.occupied && project_region.hits == REGION_ENTER_FRAMES)
    {
      project_region.occupied = 1;
      return "ENTER";
    }
  }
  else
  {
    project_region.hits = 0;
    if (project_region.misses < REGION_EXIT_FRAMES) ++project_region.misses;
    if (project_region.occupied && project_region.misses == REGION_EXIT_FRAMES)
    {
      project_region.occupied = 0;
      return "EXIT";
    }
  }
  return NULL;
}

static void Region_Draw(void)
{
  if (lcd_bg_area.XSize < 2 || lcd_bg_area.YSize < 2) return;
  uint32_t x0 = lcd_bg_area.X0 + REGION_X_MIN * lcd_bg_area.XSize / 10000U;
  uint32_t x1 = lcd_bg_area.X0 + REGION_X_MAX * lcd_bg_area.XSize / 10000U;
  uint32_t y0 = lcd_bg_area.Y0 + REGION_Y_MIN * lcd_bg_area.YSize / 10000U;
  uint32_t y1 = lcd_bg_area.Y0 + REGION_Y_MAX * lcd_bg_area.YSize / 10000U;
  if (x1 >= lcd_bg_area.X0 + lcd_bg_area.XSize)
    x1 = lcd_bg_area.X0 + lcd_bg_area.XSize - 1;
  if (y1 >= lcd_bg_area.Y0 + lcd_bg_area.YSize)
    y1 = lcd_bg_area.Y0 + lcd_bg_area.YSize - 1;

  const uint32_t pending = project_region.occupied ?
      project_region.misses : project_region.hits;
  const uint32_t color = !project_region.valid ? UTIL_LCD_COLOR_RED :
      pending ? UTIL_LCD_COLOR_YELLOW :
      project_region.occupied ? UTIL_LCD_COLOR_RED : UTIL_LCD_COLOR_GREEN;

  UTIL_LCD_DrawRect(x0, y0, x1 - x0, y1 - y0, color);
  UTIL_LCD_SetTextColor(UTIL_LCD_COLOR_WHITE);
  UTIL_LCD_SetBackColor(0xA0000000);
  if (!project_region.valid)
    UTIL_LCDEx_PrintfAt(0, LINE(3), CENTER_MODE, "ROI: INVALID - reset required");
  else if (pending)
    UTIL_LCDEx_PrintfAt(0, LINE(3), CENTER_MODE, "ROI: %s %lu/%lu",
        project_region.occupied ? "EXIT" : "ENTER", (unsigned long)pending,
        (unsigned long)(project_region.occupied ? REGION_EXIT_FRAMES : REGION_ENTER_FRAMES));
  else
    UTIL_LCDEx_PrintfAt(0, LINE(3), CENTER_MODE, "ROI: %s",
        project_region.occupied ? "OCCUPIED" : "CLEAR");
  UTIL_LCD_SetBackColor(0);
}

static void Region_Fault(const char *reason)
{
  Region_Invalidate();
  printf("EVENT,%lu,INVALID,0\r\nERROR,%lu,%s\r\n",
      (unsigned long)uart_frame_seq, (unsigned long)uart_frame_seq, reason);
  fflush(stdout);
  iseg_pp_out_t empty = {0};
  Display_NetworkOutput(&empty, 0);

  /* 故障時停止處理，等待人工重設；不對未知硬體狀態直接重試。 */
  for (;;) { __WFI(); }
}
#endif
