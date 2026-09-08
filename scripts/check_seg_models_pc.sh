#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAMBA="$HOME/STM32N6ai/tools/bin/micromamba"
ENV_EXPORT="$HOME/STM32N6ai/course13_yolov8_coco80_n6/env_export"

cd "$ROOT"

PT_MODEL="models/yolov8n-seg.pt"
FLOAT_MODEL="models/yolov8n-seg_saved_model/yolov8n-seg_float32.tflite"
INT8_MODEL="models/st_quantized/yolov8n_256_quant_pc_ii_seg_coco-st.tflite"

DATA_CONFIG="configs/coco8_seg_local.yaml"
SOURCE="datasets/coco8-seg/images/train"

for FILE in "$PT_MODEL" "$FLOAT_MODEL" "$INT8_MODEL" "$DATA_CONFIG"; do
    if [ ! -s "$FILE" ]; then
        printf '缺少必要檔案：%s\n' "$FILE"
        exit 1
    fi
done

if [ ! -d "$SOURCE" ]; then
    printf '找不到測試圖片目錄：%s\n' "$SOURCE"
    exit 1
fi

export YOLO_AUTOINSTALL=false
export CUDA_VISIBLE_DEVICES=""

mkdir -p "$ROOT/results/pc_tflite_check"

RUN="$(mktemp -d \
    "$ROOT/results/pc_tflite_check/run_$(date +%Y%m%d_%H%M%S)_XXXXXX")"

# 保存本次使用的模型與圖片指紋。
sha256sum "$PT_MODEL" "$FLOAT_MODEL" "$INT8_MODEL" \
    > "$RUN/models.sha256"

find "$SOURCE" -maxdepth 1 -type f -name '*.jpg' -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum \
    > "$RUN/images.sha256"

# 三份模型使用相同的前處理與後處理設定。
COMMON=(
    "data=$DATA_CONFIG"
    "source=$SOURCE"
    "imgsz=256"
    "batch=1"
    "rect=False"
    "conf=0.25"
    "iou=0.5"
    "max_det=10"
    "retina_masks=False"
    "device=cpu"
    "show=False"
    "save=True"
    "project=$RUN"
)

printf '%s\n' "${COMMON[@]}" > "$RUN/predict_arguments.txt"

for TAG in pt_float tflite_float st_int8; do
    case "$TAG" in
        pt_float)     MODEL="$PT_MODEL" ;;
        tflite_float) MODEL="$FLOAT_MODEL" ;;
        st_int8)      MODEL="$INT8_MODEL" ;;
    esac

    printf '\n===== 開始測試：%s =====\n' "$TAG"
    printf '模型：%s\n' "$MODEL"

    "$MAMBA" run \
        -p "$ENV_EXPORT" \
        yolo segment predict \
        "model=$MODEL" \
        "${COMMON[@]}" \
        "name=$TAG" \
        2>&1 | tee "$RUN/${TAG}.log"
done

printf '%s\n' "$RUN" \
    > "$ROOT/results/pc_tflite_check/latest_run.txt"

printf '\n===== 三份模型的圖片推論已執行完成 =====\n'
printf '結果目錄：%s\n' "$RUN"
printf '尚需檢查三份結果圖片，不代表準確度驗證已通過。\n'
