from pathlib import Path
import hashlib
import re
import sys

import hydra
from hydra.core.hydra_config import HydraConfig
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[1]
MZ = ROOT / "stm32ai-modelzoo-services"
sys.path.insert(0, str(MZ))

from instance_segmentation.tf.src.utils.gen_h_file import gen_h_user_file_n6


@hydra.main(version_base=None, config_path=None, config_name=None)
def main(_cfg):
    model = (
        ROOT / "models/st_quantized/"
        "yolov8n_256_quant_pc_ii_seg_coco-st.tflite"
    )
    classes_file = ROOT / "configs/coco80_classes.txt"

    if not model.is_file():
        raise FileNotFoundError(model)

    names = classes_file.read_text(encoding="utf-8").splitlines()

    if len(names) != 80 or names[0] != "person":
        raise ValueError("類別清單不符合目前的八十類模型。")

    before = hashlib.sha256(model.read_bytes()).hexdigest()
    run = Path(HydraConfig.get().runtime.output_dir)

    # 僅提供官方標頭產生函式需要的設定。
    # 此處採官方範例的裁切模式，尚未執行板端影像推論。
    cfg = OmegaConf.create({
        "model": {
            "model_type": "yolov8n_seg",
            "model_path": str(model),
        },
        "dataset": {
            "class_names": names,
        },
        "preprocessing": {
            "resizing": {"aspect_ratio": "crop"},
            "color_mode": "rgb",
        },
        "postprocessing": {
            "confidence_thresh": 0.25,
            "NMS_thresh": 0.5,
            "max_detection_boxes": 10,
        },
        "deployment": {
            "hardware_setup": {"board": "STM32N6570-DK"},
        },
    })

    OmegaConf.save(cfg, str(run / "header_test_config.yaml"))

    # 使用官方函式，不另行手寫 app_config.h。
    gen_h_user_file_n6(
        config=cfg,
        quantized_model_path=str(model),
    )

    header = run / "C_header/app_config.h"
    text = header.read_text(encoding="utf-8")

    expected = {
        "NB_CLASSES": 80,
        "AI_YOLOV8_SEG_PP_TOTAL_BOXES": 1344,
        "AI_YOLOV8_SEG_PP_NB_CLASSES": 80,
        "AI_YOLOV8_SEG_PP_MASK_NB": 32,
        "AI_YOLOV8_SEG_PP_MASK_SIZE": 64,
        "AI_YOLOV8_SEG_ZERO_POINT": 16,
        "AI_YOLOV8_SEG_MASK_ZERO_POINT": -112,
    }

    for name, value in expected.items():
        pattern = (
            r"^#define\s+" + re.escape(name)
            + r"\s+\(([^)]+)\)"
        )
        match = re.search(pattern, text, re.MULTILINE)

        if match is None or int(match.group(1)) != value:
            raise RuntimeError(f"標頭參數不符合本次模型：{name}")

    print("\n===== 產生的分割設定 =====")
    for line in text.splitlines():
        if line.startswith((
            "#define NB_CLASSES",
            "#define AI_YOLOV8_SEG_",
        )):
            print(line)

    after = hashlib.sha256(model.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("模型檔案內容發生變化，停止。")

    print("\n標頭位置：", header)
    print("模型 SHA-256：", after)
    print("通過：官方設定標頭可正確產生，模型內容未修改。")
    print("尚未建置或燒錄完整應用程式。")


if __name__ == "__main__":
    main()
