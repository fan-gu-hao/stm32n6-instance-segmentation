#!/usr/bin/env bash
# 2026-09-09 STM32N6 專案收尾：只保存與提交本機 Git，不執行推送。
set -euo pipefail

ROOT="$HOME/STM32N6ai/course14_yolov8n_seg_n6"
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
export N6_SAVE_SCRIPT="$SELF"

cd "$ROOT"
if [ ! -d .git ] || [ "$(git rev-parse --show-toplevel)" != "$PWD" ]; then
    printf '錯誤：目前不是 course14 專案自己的 Git 根目錄，停止。\n'
    exit 1
fi
if [ -z "$(git config user.name || true)" ] || [ -z "$(git config user.email || true)" ]; then
    printf '錯誤：本機 Git 尚未設定提交姓名或電子郵件，停止。\n'
    exit 1
fi

printf '\n===== 保存今天的程式、設定、修改差異及驗證紀錄 =====\n'
python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

root = Path.cwd()
mz = root / "stm32ai-modelzoo-services"
app = mz / "application_code/instance_segmentation/STM32N6"
snap = root / "results/checkpoints/2026-09-09"
main_rel = "Application/STM32N6570-DK/Src/main.c"
model = root / "models/st_quantized/yolov8n_256_quant_pc_ii_seg_coco-st.tflite"

for p in (mz / ".git", app / ".git", app / main_rel, model):
    if not p.exists():
        raise FileNotFoundError(p)
if "PROJECT_UART_INFERENCE_RESULT" not in (app / main_rel).read_text(encoding="utf-8"):
    raise RuntimeError("目前 main.c 中找不到今天加入的 UART 程式，停止。")

for directory in ("scripts", "configs", "docs", "patches", "requirements"):
    (root / directory).mkdir(exist_ok=True)
snap.mkdir(parents=True, exist_ok=True)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def copy_file(src, dst):
    if not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


# 保存收尾腳本本身，日後可檢查這次提交做過哪些事。
self_path = Path(os.environ["N6_SAVE_SCRIPT"])
dest_script = root / "scripts/save_n6_session_20260909.sh"
if self_path.resolve() != dest_script.resolve():
    copy_file(self_path, dest_script)

# 只記錄官方來源的版本，不對內層儲存庫提交或切換版本。
versions = {
    "session_date": "2026-09-09",
    "modelzoo_repository": "STMicroelectronics/stm32ai-modelzoo-services",
    "modelzoo_commit": git(mz, "rev-parse", "HEAD").decode().strip(),
    "application_repository": "STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation",
    "application_commit": git(app, "rev-parse", "HEAD").decode().strip(),
    "quantized_model": str(model.relative_to(root)),
    "quantized_model_sha256": sha256(model),
}
(snap / "source_versions.json").write_text(
    json.dumps(versions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)

# 最外層忽略官方副本，因此另外保存手動修改的差異。
patch_specs = [
    (mz, "20260909_modelzoo_changes.patch", [
        "common/benchmarking/common_benchmark.py",
        "instance_segmentation/tf/src/utils/gen_h_file.py",
    ]),
    (app, "20260909_application_changes.patch", [
        "Application/STM32N6570-DK/Src",
        "Application/STM32N6570-DK/Inc/app_config.h",
        "Application/STM32N6570-DK/STM32CubeIDE/.cproject",
        "Application/STM32N6570-DK/STM32CubeIDE/.project",
        "Application/STM32N6570-DK/STM32CubeIDE/STM32N657xx.ld",
        "stmaic_STM32N6570-DK.conf",
        "Model/user_neuralart_STM32N6570-DK.json",
        "Model/my_mpools",
    ]),
]
for repo, filename, paths in patch_specs:
    patch = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", *paths)
    (root / "patches" / filename).write_bytes(patch)

# 保存目前實際使用的小型原始碼與設定快照，方便直接閱讀。
for relative in (
    main_rel,
    "Application/STM32N6570-DK/Inc/app_config.h",
    "Application/STM32N6570-DK/STM32CubeIDE/STM32N657xx.ld",
    "Model/user_neuralart_STM32N6570-DK.json",
    "Model/my_mpools/stm32n6-app2_STM32N6570-DK.mpool",
    "stmaic_STM32N6570-DK.conf",
):
    copy_file(app / relative, snap / "application_sources" / relative)
copy_file(root / "pc_webcam_float.py", snap / "extra_scripts/pc_webcam_float.py")

# 保存所有已完成／失敗執行的輕量紀錄，不搬入生成程式或整套執行期。
record_suffixes = {".txt", ".log", ".json", ".yaml", ".yml", ".conf", ".mpool", ".sha256"}
for category in ("n6_analysis", "n6_deployment"):
    for run in sorted((root / "results" / category).glob("run_*")):
        if not run.is_dir():
            continue
        destination = snap / category / run.name
        for p in run.iterdir():
            if p.is_file() and p.suffix in record_suffixes:
                copy_file(p, destination / p.name)
        for pattern in ("**/network_generate_report.txt", "**/network_c_info.json"):
            for p in run.glob(pattern):
                copy_file(p, destination / p.relative_to(run))
for p in sorted((root / "logs").glob("*.log")):
    copy_file(p, snap / "logs" / p.name)

# 模型與韌體本體留在本機；Git 保存其內容指紋。
hash_files = [root / "models/yolov8n-seg.pt", model]
hash_files.extend((root / "models/yolov8n-seg_saved_model").glob("*.tflite"))
for p in (root / "models/yolov8n-seg_saved_model").rglob("*"):
    if p.is_file() and (p.suffix == ".pb" or "variables" in p.parts):
        hash_files.append(p)
for directory in (
    app / "Model/STM32N6570-DK",
    app / "Application/STM32N6570-DK/STM32CubeIDE/ModelZoo",
):
    hash_files.extend(p for p in directory.glob("*")
                      if p.is_file() and p.suffix in {".c", ".h", ".raw", ".bin", ".elf", ".hex"})
(snap / "local_artifacts.sha256").write_text(
    "".join(f"{sha256(p)}  {p.relative_to(root)}\n"
            for p in sorted(set(hash_files)) if p.is_file()), encoding="utf-8"
)

# 這是對話中實際收到的節錄，不是本腳本重新執行的量測。
(snap / "uart_received_excerpt.txt").write_text(
    "# 來源：使用者貼回的 UART 資料；未由本腳本重新測試。\n"
    "FRAME,447,49,1\nDET,0,0,918,4971,6309,9942,7265,1887\nEND,447\n"
    "FRAME,448,49,1\nDET,0,0,918,4971,6118,9942,7456,1909\nEND,448\n"
    "FRAME,449,49,1\nDET,0,0,918,4971,6118,9942,7648,1936\nEND,449\n",
    encoding="utf-8"
)

notes = """# 2026-09-09 收尾：N6 分割模型與 UART 輸出

## 本次已完成
- 原始浮點模型、浮點 TFLite、ST INT8 TFLite 已完成電腦端圖片推論。
- 原始模型與 INT8 模型的電腦攝影機功能已確認。
- ST 逐通道量化、NPU 編譯與正式部署流程已完成。
- Python 設定產生器已修正兩組輸出的辨識，不改模型輸出順序。
- main.c 已加入 FRAME／DET／END 格式的 UART 結果輸出。
- 應用程式更新後，主機已收到連續的物件辨識與遮罩非零計數。

## 基準與限制
- 量化模型 SHA-256：312ea45821140094d6a637d11f2e7daf1c8eb3e9ad5f93b8ed6c595128eaec2e。
- NPU 編譯報告：權重 3,474,865 B；活化值 2,973,760 B（含輸入輸出）。
- 活化值包含 112 KiB 外部 RAM；395 個純硬體、17 個混合、1 個軟體執行階段。
- UART 節錄中的 49 ms 是 stai_network_run() 呼叫耗時，含模型的硬體／混合／軟體階段；不是純 NPU 硬體時間或完整影格延遲。
- UART 目前逐幀同步輸出，會增加整體處理時間；尚未正式量測其成本。
- mask_pixels 是 64×64 遮罩的非零計數，不是完整遮罩資料，也不能直接當成裁切後的物件精確面積。
- 圖片 000000000009.jpg：INT8 比浮點版少一個碗與一張餐桌。小型測試不代表正式準確度評估。
- 模型庫摘要 38.047 M 與 ST Edge AI 主報告 1,019,342,144 MACC 不同，尚未釐清統計範圍，不混用。
- 長時間穩定性、重複冷啟動、逾時恢復與完整效能實驗尚未完成。

## 下次接續
從 A3 分段效能量測開始：影像準備、模型執行、後處理、UART、顯示與整體影格時間。
目前不重新訓練、匯出或量化模型；先建立有明確量測邊界的基準。

## 保存範圍
scripts、configs、docs、patches、環境清單與精選測試結果納入本機 Git。
模型、資料集、生成程式、韌體與虛擬環境仍留在原本硬碟位置，不刪除、不上傳。
這次提交不是整個硬碟的備份；大型產物以來源、版本與雜湊值追溯。
GitHub 等整個專案與測試完成後，再整理發布。
"""
(root / "docs/session_2026-09-09.md").write_text(notes, encoding="utf-8")
readme = root / "README.md"
text = readme.read_text(encoding="utf-8")
marker = "## 2026-09-09 收尾進度"
if marker not in text:
    readme.write_text(text.rstrip() + "\n\n" + marker + "\n\n"
        "已完成 N6 實例分割部署與 UART 結果輸出。今日驗證、限制與接續點見 "
        "[收尾紀錄](docs/session_2026-09-09.md)。\n", encoding="utf-8")

# 先前 *_local.yaml 被排除；現在明確保存三份已知的本機設定。
ignore = root / ".gitignore"
text = ignore.read_text(encoding="utf-8")
marker = "# SESSION_CHECKPOINT_20260909"
if marker not in text:
    ignore.write_text(text.rstrip() + "\n\n" + marker + "\n"
        "/results/n6_analysis/\n/results/n6_deployment/\n"
        "!/configs/coco8_seg_local.yaml\n"
        "!/configs/benchmark_n6_seg_local.yaml\n"
        "!/configs/deployment_n6_seg_local.yaml\n", encoding="utf-8")
print("已保存：", snap)
print("已保存：docs/session_2026-09-09.md 與官方原始碼修改差異。")
PY

# 只讀取目前套件清單，不安裝或更新任何套件。
MAMBA="$HOME/STM32N6ai/tools/bin/micromamba"
ENV_MZ="$HOME/STM32N6ai/course13_yolov8_coco80_n6/stm32ai-modelzoo-services/env_mz"
if [ -x "$MAMBA" ] && [ -d "$ENV_MZ" ]; then
    "$MAMBA" run -p "$ENV_MZ" python -m pip list --format=freeze \
        > requirements/env_mz_packages_20260909.txt
fi

# 不加入被忽略的官方副本、整套生成執行期、模型或韌體。
git add -- .gitignore README.md scripts configs docs patches requirements
for DIR in baseline quantization pc_tflite_check deployment_precheck checkpoints/2026-09-09; do
    if [ -d "results/$DIR" ]; then
        git add -- "results/$DIR"
    fi
done

# 額外檢查暫存區，避免既有的強制加入動作混入大型產物。
python3 - <<'PY'
from pathlib import Path
import subprocess

root = Path.cwd()
entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"]).decode().split("\0")
blocked = {".pt", ".pth", ".onnx", ".tflite", ".pb", ".elf", ".bin", ".hex", ".raw", ".a", ".o"}
for row in filter(None, entries):
    info, name = row.split("\t", 1)
    mode = info.split()[0]
    p = root / name
    if mode == "160000" or name.startswith("stm32ai-modelzoo-services/") or p.suffix.lower() in blocked:
        raise RuntimeError(f"暫存區含不應提交的產物：{name}；停止，不更動既有檔案。")
    if p.is_file() and p.stat().st_size > 25 * 1024 * 1024:
        raise RuntimeError(f"暫存區含超過 25 MiB 的檔案：{name}；停止提交。")
PY

printf '\n===== 本次提交內容摘要 =====\n'
git --no-pager diff --cached --stat

if git diff --cached --quiet; then
    printf '\n沒有新的變更，現有內容已保存。\n'
else
    git commit -m "保存 N6 分割部署、UART 結果輸出與本次驗證紀錄"
fi

printf '\n===== 最新本機提交 =====\n'
git --no-pager log -1 --oneline
printf '\n===== 工作目錄狀態 =====\n'
git status --short
printf '\n本機提交完成；沒有執行 GitHub 登入、建立遠端或推送。\n'
printf '模型、資料集、韌體與虛擬環境仍在原本位置。\n'
printf '下次接續：docs/session_2026-09-09.md\n'
