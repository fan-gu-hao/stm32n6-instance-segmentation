# 完整工程流程與實作證據

本作品從 YOLOv8n-seg 原始權重開始，完成模型匯出、ONNX 中間轉換、逐通道 INT8 量化、電腦比對、模型庫修補、N6 部署、應用功能及 A1～A5 工程驗證。上游提供模型架構、預訓練權重與基礎函式庫；本專案保存實際執行的轉換流程、修改與驗證結果。

## 開發延續

前期 COCO 80 類偵測專案建立模型工具環境，本專案沿用該環境再完成實例分割。[部署腳本](../scripts/deploy_n6_seg.sh)仍可直接看到 course13_yolov8_coco80_n6/stm32ai-modelzoo-services/env_mz 的相依關係。後續[雙模型語音找物作品](https://github.com/fan-gu-hao/stm32n6-voice-object-finder)延續視覺部署與板端整合經驗，再加入自行訓練的關鍵字辨識、音訊管線及 FreeRTOS 排程。

不同階段的實作都保留在各自來源與證據中；後續定版選用不同模型檔案，不會抹去先前完成的匯出、量化和修補工作。

## 逐步工作與閱讀入口

| 階段 | 實際工作 | 程式、設定或執行證據 |
| --- | --- | --- |
| 1. 環境固定 | 保存匯出與模型庫環境、工具版本、模型雜湊 | [匯出環境](../requirements/env_export_packages.txt)、[模型庫環境](../requirements/env_mz_packages_20260909.txt)、[來源版本](../results/checkpoints/2026-09-09/source_versions.json) |
| 2. 浮點基準 | 使用原始分割模型進行電腦圖片與攝影機推論 | [浮點推論日誌](../results/checkpoints/2026-09-09/logs/02_pc_float_segmentation.log)、[攝影機腳本](../scripts/pc_webcam.sh) |
| 3. 模型匯出 | 原始 PyTorch 模型匯出 ONNX，再由 onnx2tf 建立 TensorFlow SavedModel 與 TFLite | [完整匯出日誌](../results/checkpoints/2026-09-09/logs/03_export_seg.log) |
| 4. 量化 | 用 ST 量化工具與 COCO8-Seg 校正影像產生逐通道 INT8 模型 | [量化設定](../configs/yolov8n_seg_int8_int8.yaml)、[成功量化日誌](../results/checkpoints/2026-09-09/logs/04_st_quantization_seg.log) |
| 5. 模型介面核對 | 檢查輸入輸出型別、形狀、量化尺度、零點及兩組輸出順序 | [介面檢查紀錄](../results/quantization/interface_check.txt) |
| 6. 三模型比較 | 在相同四張影像上比較原始模型、浮點 TFLite、ST INT8，保存結果圖與參數 | [比對腳本](../scripts/check_seg_models_pc.sh)、[結果](../results/pc_tflite_check/run_20260909_010330_KzpJuw/) |
| 7. 模型庫本機產碼修補 | 補上 Neural-ART 設定檔、UINT8 輸入、INT8 輸出與通道順序參數 | [本機分析補丁](../patches/modelzoo_n6_local_benchmark.patch)、[分析腳本](../scripts/n6_benchmark_local.sh)、[設定](../configs/n6_neuralart_baseline.json) |
| 8. 後處理介面適配 | 依張量形狀辨識偵測資料與遮罩原型，驗證類別數、遮罩係數、型別及大小排序 | [輸出對應補丁](../patches/modelzoo_seg_output_mapping.patch)、[修改後的產生器](../tools/model_zoo_overrides/instance_segmentation/tf/src/utils/gen_h_file.py)、[標頭檢查](../scripts/check_n6_seg_header.py) |
| 9. NPU 分析 | 檢查硬體、混合及軟體執行階段與權重、活化值配置 | [分析輸出](../results/checkpoints/2026-09-09/n6_analysis/run_20260909_012357_bvINEg/)、[階段摘要](session_2026-09-09.md) |
| 10. 部署與映像封裝 | 固定部署參數、辨識 ST-LINK、核對 SWD 連線、產碼建置，修正映像標頭及對齊參數並燒錄 | [部署腳本](../scripts/deploy_n6_seg.sh)、[部署設定](../configs/deployment_n6_seg_local.yaml)、[簽章工具參數補丁](../patches/instance_segmentation_signing_alignment.patch)、[成功部署紀錄](../results/checkpoints/2026-09-09/n6_deployment/run_20260909_020310_zj69FR/) |
| 11. 應用與通訊 | 整合攝影機、LCD、推論結果；輸出 FRAME／DET／END 與遮罩非零計數 | [主程式](../firmware/Application/STM32N6570-DK/Src/main.c)、[UART 補丁](../patches/uart_inference_result.patch)、[收到的資料節錄](../results/checkpoints/2026-09-09/uart_received_excerpt.txt) |
| 12. 區域事件 | 人物進入／離開區域的狀態判定與事件輸出 | [區域事件程式](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[修改補丁](a3_performance_20260918/instrumentation/region_event.patch) |
| 13. 固定輸入與量化差異 | 同一份像素建立 FP32／INT8／UINT8 輸入；讀回 N6 原始輸出，共同後處理，比較框、遮罩及人物標註 | [A2：四張初驗及 50 張回歸](a2_validation_20260918/README.md) |
| 14. 分段效能與瓶頸 | 計時擷取、推論、後處理、UART、顯示及完整週期；固定輸入與逐執行區塊量測 | [A3 報告](a3_performance_20260918/README.md)、[計時補丁](a3_performance_20260918/instrumentation/a3_profile.patch) |
| 15. 記憶體配置實驗 | 調整 npuRAM6 配額、重新產碼，比較記憶體與時間，並做輸出回歸 | [A4 報告](a4_memory_20260918/README.md)、[A/B 記憶體比較](a4_memory_20260918/memory_comparison.json) |
| 16. 可追溯重建 | 固定官方基底、修改補丁、新增來源、二進位相依及雜湊；乾淨重建與讀回核對 | [A1 報告](a1_reproducible_20260918/README.md)、[來源固定材料](../patches/a1_source_20260918/) |
| 17. 可靠性與錯誤路徑 | 冷啟動、區域進出、長測複驗、模擬擷取逾時、失效提示與正式韌體恢復 | [A5 報告](a5_acceptance_20260919/README.md)、[故障注入補丁](a5_acceptance_20260919/capture_fault.patch) |
| 18. 交付保存 | 將程式、設定、補丁、結果與來源對應整理成公開作品 | [來源對照](PUBLIC_SOURCE_MAP.md)、[交付索引](a5_acceptance_20260919/DELIVERY.md) |

## 已確認的模型轉換順序

原始 yolov8n-seg.pt → ONNX → onnx2tf → TensorFlow SavedModel／TFLite → ST 逐通道 INT8 TFLite → ST Edge AI／Neural-ART → N6 模型程式、權重與執行指令 → 韌體整合。

2026-09-09 保存的匯出日誌明確記錄：

- Ultralytics 8.3.157、ONNX 1.16.1、算子集（opset）19、onnxslim 0.1.96。
- ONNX 成功輸出為 models/yolov8n-seg.onnx。
- onnx2tf 1.26.3 與 TensorFlow 2.18.0 完成 SavedModel／TFLite 匯出。
- ST 量化另由已保存的設定與量化日誌確認成功；這份模型與匯出器同時產生的其他 TFLite 檔案分別保存。

原始匯出命令的所有參數未逐字保存，不影響上述實際轉換階段已有成功日誌可查。量化校正使用四張 COCO8-Seg 影像；品質另以電腦比對及 A2 回歸檢視，不能把這四張資料當成完整精度評估。

## 模型介面與後處理修改

量化模型本身的輸入為 INT8，尺度約為 1/255、零點 -128。N6 產碼入口設定為 UINT8、通道置後，讓攝影機 RGB888 像素接入；兩者是不同層的介面設定。

| 輸出 | 張量形狀 | 用途 |
| --- | --- | --- |
| 偵測資料 | 1×116×1344 | 4 個框座標＋80 個類別分數＋32 個遮罩係數 |
| 遮罩原型 | 1×64×64×32 | 供每個物件的遮罩重建使用 |

實際 TFLite 列出的順序是遮罩原型在前、偵測資料在後。修改後的 gen_h_file.py 依三維／四維張量判斷角色，核對 INT8 型別、類別數與遮罩係數、正方形原型、官方板端轉接層的大小排序要求，再用正確的中繼資料產生標頭。這項修改沒有重排模型本體輸出。

後處理的移植與介面修補是本專案的工程工作；NMS 與遮罩重建核心保留 ST 上游實作。兩者的來源與貢獻可以同時清楚呈現。

## 分析結果與版本界線

- 初期 NPU 分析記錄權重 3,474,865 bytes、活化值 2,973,760 bytes，含 112 KiB 外部 RAM；分類為 395 個硬體、17 個混合、1 個軟體階段。這組編譯統計與 A3 的 58 個量測區塊是不同統計層級。
- A2 的 50 張人物資料有 59 個標註；電腦 INT8 與 N6 配對框平均 IoU 0.961、遮罩 IoU 0.959，完整數值和評估條件見報告。
- A3 固定輸入的一般推論平均 48.6066 ms；攝影機完整週期另外計入傳輸、後處理與顯示。
- A4 B 配置的實體 RAM 配置已用量減少 162.5625 KiB，50 張輸出與既有 N6 基準逐位元組一致。正式攝影機版維持 A1 配置。
- A5 保存首次長測異常與後續通過的複驗，保留當時實際狀態。

2026-09-09 的收尾文件是階段快照，其中當時尚未完成的項目，應接續閱讀後來的 A1～A5；本頁把各階段連在一起。跨作品比較時，請以各自模型雜湊與證據判定版本，不將課程 14 的測試數字套用為雙模型作品的結果。
