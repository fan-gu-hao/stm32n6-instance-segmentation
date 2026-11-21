# 完整工程流程與程式

本作品以 STM32N6570-DK 建立 MCU 級的即時實例分割系統。開發主軸是從 YOLOv8n-seg 原始權重出發，完成電腦環境、模型匯出、ST 逐通道 INT8 量化、模型工具庫介面修正、Neural-ART 產碼、執行期整合與實板部署，再加入串列結果與人物區域事件。

本頁依 17 個開發步驟整理模型到開發板的過程；A1～A5 的後續測試集中於最後。更細的程式與歷史實驗入口見[完整工作與程式索引](WORK_IMPLEMENTATION_INDEX.md)。

## 從模型到實板：17 個開發步驟

| 步驟 | 實際工作 | 程式 |
| --- | --- | --- |
| **1. 確立專案目標與完成條件** | 在開發板完成 80 類物件的框與個別遮罩；串接攝影機、推論、後處理、螢幕、串列資料與人物區域事件 | [主程式](../firmware/Application/STM32N6570-DK/Src/main.c)、[區域事件](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h) |
| **2. 準備電腦、開發板與周邊設備** | 準備 Ubuntu、STM32N6570-DK、攝影機與 LCD；核對供電、ST-LINK、串列裝置與目標序號，區分開發及快閃記憶體啟動模式 | [部署腳本](../scripts/deploy_n6_seg.sh)、[部署設定](../configs/deployment_n6_seg_local.yaml) |
| **3. 準備並固定開發工具** | 固定 STM32CubeIDE、Arm 編譯器、STM32CubeProgrammer、外部載入器、映像封裝工具、ST Edge AI、Neural-ART 與官方驗證工具 | [來源版本](../results/checkpoints/2026-09-09/source_versions.json)、[工具版本](a1_reproducible_20260918/README.md) |
| **4. 建立模型處理與部署環境** | 以 micromamba 區分匯出與模型工具庫環境，沿用前期專案的相依套件並保存清單 | [匯出環境](../requirements/env_export_packages.txt)、[模型工具庫環境](../requirements/env_mz_packages_20260909.txt) |
| **5. 取得官方來源並整理專案結構** | 固定官方基底與巢狀應用程式，分開模型、設定、腳本、修補與結果，以獨立工作目錄及雜湊追溯 | [來源鎖定](../patches/a1_source_20260918/source_lock.json)、[來源對照](PUBLIC_SOURCE_MAP.md) |
| **6. 建立原始模型的電腦端基準** | 核對 YOLOv8n-seg 任務與 80 類別，保存原始模型圖片推論及電腦攝影機分割結果 | [浮點推論日誌](../results/checkpoints/2026-09-09/logs/02_pc_float_segmentation.log)、[攝影機腳本](../scripts/pc_webcam.sh) |
| **7. 匯出原始模型並完成第一段 ONNX 轉換** | 固定 256×256 輸入，由 PyTorch 匯出 ONNX，再經 onnx2tf 建立 SavedModel 與 TFLite，保存版本及完整日誌 | [完整匯出日誌](../results/checkpoints/2026-09-09/logs/03_export_seg.log) |
| **8. 檢查浮點模型的輸入與輸出** | 核對 RGB 浮點輸入、1×116×1344 偵測資料及 1×64×64×32 遮罩原型；分別讀取各格式的中繼資料 | [浮點介面](pc_baseline.md) |
| **9. 建立 ST 逐通道整數量化流程** | 用 SavedModel 與四張 COCO8-seg 校正圖產生逐通道 INT8 模型；明確選定正式部署檔並保存雜湊 | [量化設定](../configs/yolov8n_seg_int8_int8.yaml)、[成功量化日誌](../results/checkpoints/2026-09-09/logs/04_st_quantization_seg.log) |
| **10. 核對量化模型的介面與像素轉換** | 檢查形狀、型別、尺度、零點與兩組輸出；對應 TFLite INT8 介面和 N6 UINT8／NHWC 輸入 | [介面檢查紀錄](../results/quantization/interface_check.txt) |
| **11. 比較三種模型的電腦端功能** | 以共同圖片及推論參數比較原始模型、浮點 TFLite、ST INT8，保存框、遮罩、物件差異與結果圖，確認 INT8 攝影機功能 | [比對腳本](../scripts/check_seg_models_pc.sh)、[結果](../results/pc_tflite_check/run_20260909_010330_KzpJuw/)、[階段摘要](session_2026-09-09.md) |
| **12. 修改模型工具庫的後處理介面產生流程** | 依三維／四維張量辨識偵測與遮罩，修正尺度、零點及產生標頭的對應，檢查類別數、係數、型別與大小排序 | [輸出對應補丁](../patches/modelzoo_seg_output_mapping.patch)、[修改後的產生器](../tools/model_zoo_overrides/instance_segmentation/tf/src/utils/gen_h_file.py) |
| **13. 建立部署前的設定自動檢查** | 檢查 80 類、1344 候選、32 個遮罩係數、64×64 原型及零點，並核對模型雜湊，異常時停止部署 | [標頭檢查](../scripts/check_n6_seg_header.py) |
| **14. 修正本機模型產碼參數** | 修正 Neural-ART 設定檔、記憶體池、UINT8 輸入、INT8 輸出、通道排列與命令引號的傳遞 | [本機分析補丁](../patches/modelzoo_n6_local_benchmark.patch)、[分析腳本](../scripts/n6_benchmark_local.sh)、[設定](../configs/n6_neuralart_baseline.json) |
| **15. 執行第二段 ONNX 轉換與 N6 模型編譯** | ST Edge AI 將正式 TFLite 轉為內部 ONNX 與量化描述，再由 Neural-ART 產生程式、權重與命令，分析執行階段及記憶體 | [分析輸出](../results/checkpoints/2026-09-09/n6_analysis/run_20260909_012357_bvINEg/)、[產碼報告](../results/checkpoints/2026-09-09/n6_deployment/run_20260909_020310_zj69FR/generated/network_generate_report.txt) |
| **16. 整合推論執行期與韌體建置設定** | 對齊 M55 執行期標頭／函式庫，調整 ModelZoo 組態與連結配置，安排模型命令資料和後處理工作區 | [建置組態](../firmware/Application/STM32N6570-DK/STM32CubeIDE/.cproject)、[連結腳本](../firmware/Application/STM32N6570-DK/STM32CubeIDE/STM32N657xx.ld)、[相依檔案](../patches/a1_source_20260918/dependencies.json) |
| **17. 完成映像封裝修正與第一次板端部署** | 產生 ELF／配置檔，修正映像標頭及對齊；經 SWD、外部載入器燒錄開機程式、應用與模型資料，確認獨立啟動及分割畫面 | [部署腳本](../scripts/deploy_n6_seg.sh)、[簽章工具參數補丁](../patches/instance_segmentation_signing_alignment.patch)、[成功部署紀錄](../results/checkpoints/2026-09-09/n6_deployment/run_20260909_020310_zj69FR/) |

## 模型轉換與兩段 ONNX 的分工

原始 yolov8n-seg.pt → 第一段 ONNX → onnx2tf → TensorFlow SavedModel → ST 逐通道 INT8 TFLite → ST Edge AI 內部 ONNX 與量化描述 → Neural-ART → N6 模型程式、權重與執行命令 → 韌體整合。

2026-09-09 保存的匯出日誌明確記錄：

- Ultralytics 8.3.157、ONNX 1.16.1、算子集（opset）19、onnxslim 0.1.96。
- ONNX 成功輸出為 models/yolov8n-seg.onnx。
- onnx2tf 1.26.3 與 TensorFlow 2.18.0 完成 SavedModel／TFLite 匯出。
- ST 量化另由已保存的設定與量化日誌確認成功；這份模型與匯出器同時產生的其他 TFLite 檔案分別保存。

原始匯出命令的所有參數未逐字保存，不影響上述實際轉換階段已有成功日誌可查。量化校正使用四張 COCO8-Seg 影像；品質另以電腦比對及 A2 回歸檢視，不能把這四張資料當成完整精度評估。

第一段 ONNX 用於原始模型轉成 TensorFlow 格式。第二段由 ST 編譯工具產生，包含面向 N6 產碼的模型表示與量化描述。SavedModel 亦會由匯出流程產生浮點與其他 INT8 TFLite；正式部署採另外執行 ST 量化所得到的模型。

## 模型介面與後處理修改

量化模型本身的輸入為 INT8，尺度約為 1/255、零點 -128。N6 產碼入口設定為 UINT8、通道置後，讓攝影機 RGB888 像素接入；兩者是不同層的介面設定。

| 輸出 | 張量形狀 | 用途 |
| --- | --- | --- |
| 偵測資料 | 1×116×1344 | 4 個框座標＋80 個類別分數＋32 個遮罩係數 |
| 遮罩原型 | 1×64×64×32 | 供每個物件的遮罩重建使用 |

實際 TFLite 列出的順序是遮罩原型在前、偵測資料在後。修改後的 gen_h_file.py 依三維／四維張量判斷角色，核對 INT8 型別、類別數與遮罩係數、正方形原型、官方板端轉接層的大小排序要求，再用正確的中繼資料產生標頭。這項修改沒有重排模型本體輸出。

後處理的移植與介面修補是本專案的工程工作；NMS 與遮罩重建核心保留 ST 上游實作。兩者的來源與貢獻可以同時清楚呈現。

## 產碼、執行期與映像配置

- 初期編譯報告記錄權重 3,474,865 位元組、活化值 2,973,760 位元組，包含 112 KiB 外部 RAM；分類為 395 個硬體、17 個混合、1 個軟體階段。
- `common_benchmark.py` 修正指定模型配置、記憶體池與輸入輸出參數的傳遞；`n6_benchmark_local.sh` 在此負責本機產碼與配置分析。
- ModelZoo 組態使用 `NetworkRuntime1201_CM55_GCC.a`，搭配相符標頭與連結路徑；命令資料與後處理工作區分別使用指定快閃記憶體及外部 RAM 區段。
- 映像產生流程修正 `-of 0x80000000` 與 `-align`，處理映像標頭及對齊，接續開發板燒錄與啟動。
- 正式交付的應用程式、權重與模型命令資料分別位於 `0x70100000`、`0x70380000`、`0x71380000`；第一階段開機程式使用 HEX 內的位址。

## 板端應用與新增功能

| 範圍 | 實作 | 程式 |
| --- | --- | --- |
| 攝影機與推論 | 單一主迴圈搭配攝影機中斷回呼；整合顯示連續擷取、模型單次擷取、同步推論、分割後處理與快取維護 | [主程式](../firmware/Application/STM32N6570-DK/Src/main.c)、[攝影機管線](../firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c) |
| 結構化串列輸出 | 使用共同影格序號輸出 FRAME／DET／END，包含類別、信心、框座標與遮罩非零計數 | [UART 補丁](../patches/uart_inference_result.patch)、[收到的資料節錄](../results/checkpoints/2026-09-09/uart_received_excerpt.txt) |
| 人物區域事件 | 以人物框底邊中心判斷區域；連續三幀確認進入、五幀確認離開，更新區域狀態與事件 | [區域事件程式](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[修改補丁](a3_performance_20260918/instrumentation/region_event.patch) |
| 資料失效處理 | 擷取逾時或推論／後處理異常時回報失效、清除舊框並停止發布結果，等待人工重設 | [主程式](../firmware/Application/STM32N6570-DK/Src/main.c)、[區域事件程式](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h) |
| 分段量測 | 插入擷取、推論、後處理、串列、顯示及完整週期量測，記錄暖機與日誌成本 | [計時補丁](a3_performance_20260918/instrumentation/a3_profile.patch) |
| 串列中斷歷史實驗 | 實作環形佇列、整列提交、重要訊息預留空間與中斷回呼，保存部署及還原紀錄；正式版維持阻塞傳送 | [歷史程式](publication_supplement_20261113/uart_it) |

## 來源保存、交付與開發延續

操作腳本、模型設定、工具修補、核心程式與結果分別保存，並建立[來源對照](PUBLIC_SOURCE_MAP.md)、[來源固定材料](../patches/a1_source_20260918/)與[交付索引](a5_acceptance_20260919/DELIVERY.md)。

前期 COCO 80 類偵測專案建立模型工具環境，本專案沿用該環境再完成實例分割。[部署腳本](../scripts/deploy_n6_seg.sh)仍可直接看到 course13_yolov8_coco80_n6/stm32ai-modelzoo-services/env_mz 的相依關係。後續[雙模型語音找物作品](https://github.com/fan-gu-hao/stm32n6-voice-object-finder)延續視覺部署與板端整合經驗，再加入自行訓練的關鍵字辨識、音訊管線及 FreeRTOS 排程。

不同階段的實作都保留在各自來源與紀錄中；後續定版選用不同模型檔案，不會抹去先前完成的匯出、量化和修補工作。

## 後續測試與結果

上述模型與板端整合完成後，再進行固定輸入比較、效能量測、記憶體配置實驗、來源重建與可靠性驗收。完整方法及原始結果保留在各階段文件。

| 階段 | 方法與主要結果 | 程式 |
| --- | --- | --- |
| **A2：固定輸入與量化差異** | 同一份像素建立 FP32／INT8／UINT8 輸入，讀回 N6 原始輸出，透過共同後處理比較框、遮罩與標註；50 張資料有 59 個人物標註，電腦 INT8 與 N6 配對框／遮罩平均 IoU 為 0.961／0.959 | [四張初驗及 50 張回歸](a2_validation_20260918/README.md) |
| **A3：分段效能與瓶頸** | 分開統計攝影機完整週期與固定輸入推論；一般推論平均 48.6066 毫秒，並分析 58 個量測區塊 | [A3 報告](a3_performance_20260918/README.md)、[計時補丁](a3_performance_20260918/instrumentation/a3_profile.patch) |
| **A4：記憶體配置實驗** | 調整 npuRAM6 配額並重新產碼，B 配置的實體 RAM 池已用量減少 162.5625 KiB；50 張輸出與既有 N6 基準逐位元組一致 | [A4 報告](a4_memory_20260918/README.md)、[A/B 記憶體比較](a4_memory_20260918/memory_comparison.json) |
| **A1：可追溯重建** | 固定官方基底、修補、新增來源與二進位相依，完成既有環境乾淨重建、燒錄讀回及隔離目錄來源還原核對 | [A1 報告](a1_reproducible_20260918/README.md)、[來源固定材料](../patches/a1_source_20260918/) |
| **A5：可靠性與錯誤路徑** | 完成冷啟動、區域進出、長測複驗、模擬擷取逾時、失效提示與正式韌體恢復；保留首次長測異常與後續通過結果 | [A5 報告](a5_acceptance_20260919/README.md)、[故障注入補丁](a5_acceptance_20260919/capture_fault.patch) |

### 結果範圍與版本界線

- A2 使用固定回歸集及共同電腦後處理；攝影機像素路徑與板端 C 後處理逐像素等價不在本組測試範圍內。
- 編譯報告的硬體／混合／軟體階段數，與 A3 的 58 個量測區塊屬於不同統計層級；模型呼叫時間也與攝影機完整週期分開。
- A4 的 RAM 數字來自編譯器配置報告，微小時間差不作為明確加速；B 是配置實驗，正式攝影機仍使用 A1 的原配置。
- A1 在既有環境完成乾淨重建；隔離目錄只完成來源及相依檔還原核對，沒有在該目錄建置。全新電腦的完整重建尚未驗證。
- A5 首次長測的序號不連續根因未確定；後續重新同步開機的長測通過。故障處理以軟體注入擷取逾時驗證。
- 原始臨時終端程式尚未全部整理成可直接重跑的操作套件，保存範圍見[完整工作與程式索引](WORK_IMPLEMENTATION_INDEX.md)。

2026-09-09 的收尾文件是階段快照，其中當時尚未完成的項目，應接續閱讀後來的 A1～A5；本頁把各階段連在一起。跨作品比較時，依各自模型雜湊與紀錄判定版本，不將本作品的測試數字套用為後續雙模型作品的結果。
