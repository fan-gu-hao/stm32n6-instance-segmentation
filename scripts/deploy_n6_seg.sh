#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MZ="$ROOT/stm32ai-modelzoo-services"

MAMBA="$HOME/STM32N6ai/tools/bin/micromamba"
ENV_MZ="$HOME/STM32N6ai/course13_yolov8_coco80_n6/stm32ai-modelzoo-services/env_mz"

MODEL="$ROOT/models/st_quantized/yolov8n_256_quant_pc_ii_seg_coco-st.tflite"
CONFIG="$ROOT/configs/deployment_n6_seg_local.yaml"

export STM32_AI_EXE="$HOME/ST/STEdgeAI/4.0/Utilities/linux/stedgeai"
export STM32_CUBE_IDE_EXE="/opt/st/stm32cubeide_2.2.0/stm32cubeide"

export STM32_CUBE_PROG_EXE="/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI"
export STM32_SIGNINGTOOL_CLI="/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_SigningTool_CLI"

export PATH="$(dirname "$STM32_CUBE_PROG_EXE"):$(dirname "$STM32_CUBE_IDE_EXE"):$PATH"

export CUDA_VISIBLE_DEVICES=""
export HYDRA_FULL_ERROR=1
export CLEARML_OFFLINE_MODE=1

cd "$ROOT"

test -x "$MAMBA"
test -d "$ENV_MZ"
test -s "$MODEL"
test -s "$CONFIG"

mkdir -p "$ROOT/results/n6_deployment"

RUN="$(mktemp -d \
    "$ROOT/results/n6_deployment/run_$(date +%Y%m%d_%H%M%S)_XXXXXX")"

# 失敗時也能找到這次紀錄。
printf '%s\n' "$RUN" > "$ROOT/results/n6_deployment/latest_run.txt"

cp "$CONFIG" "$RUN/deployment_requested.yaml"

sha256sum "$MODEL" > "$RUN/model.sha256"

git -C "$MZ" rev-parse HEAD > "$RUN/modelzoo_commit.txt"

cp \
  "$MZ/application_code/instance_segmentation/STM32N6/stmaic_STM32N6570-DK.conf" \
  "$RUN/"

printf '\n===== 尋找 ST-LINK =====\n'

"$STM32_CUBE_PROG_EXE" -l stlink \
  2>&1 | tee "$RUN/stlink_list.log"

mapfile -t SERIALS < <(
    awk -F':' '
      /ST-LINK SN/ {
        sn=$2
        gsub(/[[:space:]\r]/, "", sn)
        if (sn != "") print sn
      }
    ' "$RUN/stlink_list.log" \
    | sort -u
)

if [ "${#SERIALS[@]}" -ne 1 ]; then
    printf '預期只有一個 ST-LINK，實際找到 %s 個，停止。\n' \
      "${#SERIALS[@]}"
    printf '請保留 stlink_list.log，不繼續燒錄。\n'
    exit 1
fi

SERIAL="${SERIALS[0]}"
printf '%s\n' "$SERIAL" > "$RUN/stlink_serial.txt"

printf '\n===== 測試目標板 SWD 連線 =====\n'

"$STM32_CUBE_PROG_EXE" \
  -c port=SWD mode=HOTPLUG "sn=$SERIAL" \
  2>&1 | tee "$RUN/connection.log"

printf '\n===== 開始模型庫正式部署 =====\n'
printf '目標 ST-LINK：%s\n' "$SERIAL"
printf '結果目錄：%s\n' "$RUN"

# 相對 C 專案路徑以這個工作目錄為基準。
cd "$MZ/instance_segmentation"

"$MAMBA" run \
  -p "$ENV_MZ" \
  python -u stm32ai_main.py \
  --config-path "$ROOT/configs" \
  --config-name deployment_n6_seg_local \
  "hydra.run.dir=$RUN" \
  "hydra.job.chdir=False" \
  "++deployment.hardware_setup.stlink_serial_number='${SERIAL}'" \
  2>&1 | tee "$RUN/console.log"

printf '\n===== 模型庫部署命令已正常結束 =====\n'
printf '結果目錄：%s\n' "$RUN"
printf '請確認完整燒錄紀錄，再切換正常開機模式。\n'
