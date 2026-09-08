#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MZ="$ROOT/stm32ai-modelzoo-services"

MAMBA="$HOME/STM32N6ai/tools/bin/micromamba"
ENV_MZ="$HOME/STM32N6ai/course13_yolov8_coco80_n6/stm32ai-modelzoo-services/env_mz"
STEDGEAI="$HOME/ST/STEdgeAI/4.0/Utilities/linux/stedgeai"

MODEL="$ROOT/models/st_quantized/yolov8n_256_quant_pc_ii_seg_coco-st.tflite"
PROFILE="$ROOT/configs/n6_neuralart_baseline.json"
POOL="$MZ/application_code/instance_segmentation/STM32N6/Model/my_mpools/stm32n6-app2_STM32N6570-DK.mpool"

test -x "$MAMBA"
test -d "$ENV_MZ"
test -x "$STEDGEAI"
test -s "$MODEL"
test -s "$PROFILE"
test -s "$POOL"

mkdir -p "$ROOT/results/n6_analysis"

RUN="$(mktemp -d \
    "$ROOT/results/n6_analysis/run_$(date +%Y%m%d_%H%M%S)_XXXXXX")"

# 即使分析失敗，也能找到這次的完整紀錄。
printf '%s\n' "$RUN" > "$ROOT/results/n6_analysis/latest_run.txt"

cp "$ROOT/configs/benchmark_n6_seg_local.yaml" "$RUN/"
cp "$PROFILE" "$RUN/"
cp "$POOL" "$RUN/"

sha256sum "$MODEL" > "$RUN/model.sha256"
git -C "$MZ" rev-parse HEAD > "$RUN/modelzoo_commit.txt"
"$STEDGEAI" --version > "$RUN/stedgeai_version.txt" 2>&1

export CUDA_VISIBLE_DEVICES=""
export HYDRA_FULL_ERROR=1
export CLEARML_OFFLINE_MODE=1

# 由模型庫腳本將此設定傳給官方 NPU 編譯器。
export STM32N6_NEURALART_PROFILE="default@$PROFILE"

cd "$MZ/instance_segmentation"

printf '本次分析結果：%s\n' "$RUN"

"$MAMBA" run \
  -p "$ENV_MZ" \
  python stm32ai_main.py \
  --config-path "$ROOT/configs" \
  --config-name benchmark_n6_seg_local \
  "hydra.run.dir=$RUN" \
  "hydra.job.chdir=False" \
  2>&1 | tee "$RUN/console.log"

printf '\n===== 本機分析程序結束 =====\n'
printf '結果位置：%s\n' "$RUN"
printf '尚未建置或燒錄完整的板端應用程式。\n'
