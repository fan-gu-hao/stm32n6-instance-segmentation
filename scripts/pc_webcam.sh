#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MAMBA="${MAMBA:-$HOME/STM32N6ai/tools/bin/micromamba}"
ENV_EXPORT="${ENV_EXPORT:-$HOME/STM32N6ai/course13_yolov8_coco80_n6/env_export}"
CAMERA="${1:-0}"

cd "$ROOT"

test -x "$MAMBA"
test -d "$ENV_EXPORT"
test -s models/yolov8n-seg.pt

export YOLO_AUTOINSTALL=false

exec "$MAMBA" run \
  -p "$ENV_EXPORT" \
  yolo segment predict \
  model=models/yolov8n-seg.pt \
  source="$CAMERA" \
  imgsz=256 \
  conf=0.25 \
  iou=0.5 \
  device=cpu \
  show=True \
  save=False
