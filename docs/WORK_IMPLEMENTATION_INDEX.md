# 完整工作與程式索引

本索引以「環境建立 → 原始模型 → 匯出與量化 → 介面修正 → NPU 產碼 → 韌體整合與實板部署」為主軸。先列出從模型到開發板的 17 個開發步驟，再列應用功能、歷史實驗與交付材料；A1～A5 測試放在最後。

## 從模型到實板的 17 個開發步驟

### 1. 確立專案目標與完成條件

- 在 STM32N6570-DK 上使用 YOLOv8n-seg 辨識物件類別、位置與每個物件的分割遮罩。
- 串接攝影機擷取、板端推論、分割後處理、螢幕顯示與結構化串列結果。
- 加入人物區域事件，保存模型流程、工具修補、韌體修改與後續驗收紀錄。

程式：[應用程式主流程](../firmware/Application/STM32N6570-DK/Src/main.c)、[工程流程](engineering-workflow.md)。

### 2. 準備電腦、開發板與周邊設備

- 準備 Ubuntu 開發電腦、STM32N6570-DK、攝影機與螢幕。
- 確認供電、ST-LINK 除錯與虛擬串列連線，使用裝置序號選定目標開發板。
- 區分開發模式與外部快閃記憶體啟動模式，建立燒錄、讀回與串列監看流程。

程式：[部署腳本](../scripts/deploy_n6_seg.sh)、[部署設定](../configs/deployment_n6_seg_local.yaml)、[攝影機流程](../firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c)。

### 3. 準備並固定開發工具

- 使用 STM32CubeIDE、Arm 交叉編譯器、STM32CubeProgrammer 與開發板外部記憶體載入器。
- 準備 ST Edge AI、Neural-ART、映像標頭與對齊工具，以及官方模型驗證程式。
- 保存實際工具版本與來源版本，供產碼、建置與重新部署核對。

程式：[工具與來源版本](../results/checkpoints/2026-09-09/source_versions.json)、[工具版本與重建紀錄](a1_reproducible_20260918/README.md)。

### 4. 建立模型處理與部署環境

- 使用微型環境管理工具（micromamba），沿用前期偵測專案的匯出環境與模型工具庫環境。
- 區分電腦推論、模型匯出、ST 量化、部署與板端驗證的執行環境。
- 保存套件清單；既有操作腳本保留原開發環境路徑，標明對前期環境的相依關係。

程式：[requirements](../requirements)、[匯出環境](../requirements/env_export_packages.txt)、[模型工具庫環境](../requirements/env_mz_packages_20260909.txt)。

### 5. 取得官方來源並整理專案結構

- 固定 ST 模型工具庫與 N6 實例分割應用程式的官方基底版本。
- 區分主專案、模型工具庫與巢狀應用程式，分別保存官方來源、專案修改與新增檔案。
- 依模型、設定、腳本、修補、結果與文件整理目錄，以獨立執行目錄及雜湊追溯版本。

程式：[來源鎖定清單](../patches/a1_source_20260918/source_lock.json)、[公開來源對照](PUBLIC_SOURCE_MAP.md)、[階段保存腳本](../scripts/save_n6_session_20260909.sh)。

### 6. 建立原始模型的電腦端基準

- 取得預訓練 YOLOv8n-seg，確認模型任務、80 個類別、偵測框與分割遮罩。
- 以固定圖片進行原始模型推論，保存物件數、結果圖與日誌。
- 使用電腦攝影機確認即時實例分割功能；此階段建立功能基準，數值與準確性比較另於後續完成。

程式：[pc_baseline.md](pc_baseline.md)、[pc_webcam.sh](../scripts/pc_webcam.sh)、[原始模型推論日誌](../results/checkpoints/2026-09-09/logs/02_pc_float_segmentation.log)。

### 7. 匯出原始模型並完成第一段 ONNX 轉換

- 固定 256×256 輸入，將原始 PyTorch 模型匯出為 ONNX。
- 記錄 ONNX、算子集與模型簡化工具版本，再以 onnx2tf 轉成 TensorFlow SavedModel。
- 保存匯出器產生的浮點及 INT8 TFLite、各階段產物與完整日誌。

程式：[03_export_seg.log](../results/checkpoints/2026-09-09/logs/03_export_seg.log)、[匯出介面紀錄](pc_baseline.md)。

### 8. 檢查浮點模型的輸入與輸出

- 確認 SavedModel 輸入為一張 256×256 RGB 浮點影像。
- 確認偵測張量 1×116×1344，對應 4 個框座標、80 個類別分數與 32 個遮罩係數。
- 確認遮罩原型 1×64×64×32，分別檢查不同格式的輸出中繼資料，不以字典列印順序推定 TFLite 輸出順序。

程式：[浮點輸入輸出紀錄](pc_baseline.md)。

### 9. 建立 ST 逐通道整數量化流程

- 以 SavedModel 為 ST 量化來源，使用 COCO8-seg 的四張校正影像與固定前處理設定。
- 執行逐通道量化（Per-channel Quantization），指定有號 8 位元（INT8）輸入與輸出。
- 將 ST 量化模型選為正式部署基準，與匯出器產生的其他 INT8 檔分開保存，記錄模型雜湊。

程式：[yolov8n_seg_int8_int8.yaml](../configs/yolov8n_seg_int8_int8.yaml)、[04_st_quantization_seg.log](../results/checkpoints/2026-09-09/logs/04_st_quantization_seg.log)。

### 10. 核對量化模型的介面與像素轉換

- 核對張量名稱、形狀、型別、尺度、零點及逐通道量化資訊。
- 確認 TFLite 輸入為 INT8，尺度約 1/255、零點 −128；辨識遮罩原型與偵測兩組輸出。
- 區分模型 INT8 介面與 N6 產碼的 UINT8、通道置後（NHWC）入口，建立攝影機 RGB888 像素的對應。

程式：[interface_check.txt](../results/quantization/interface_check.txt)、[model.sha256](../results/quantization/model.sha256)。

### 11. 比較三種模型的電腦端功能

- 使用共同圖片、輸入尺寸與推論參數，比較原始模型、浮點 TFLite 與 ST INT8。
- 保存物件數、類別、信心、框、遮罩與視覺結果，追查量化後新增或消失的物件。
- 完成 INT8 電腦攝影機功能確認；固定像素與原始張量的跨平台比較由後續 A2 處理。

程式：[check_seg_models_pc.sh](../scripts/check_seg_models_pc.sh)、[run_20260909_010330_KzpJuw](../results/pc_tflite_check/run_20260909_010330_KzpJuw)、[session_2026-09-09.md](session_2026-09-09.md)。

### 12. 修改模型工具庫的後處理介面產生流程

- 修正 gen_h_file.py，依三維與四維張量形狀辨識偵測與遮罩原型，對應正確的尺度與零點。
- 檢查 INT8 型別、類別數、遮罩係數、原型尺寸與官方轉接層的大小排序要求。
- 產生正確的板端設定標頭，保留模型輸出順序，以及官方非極大值抑制與遮罩重建核心。

程式：[modelzoo_seg_output_mapping.patch](../patches/modelzoo_seg_output_mapping.patch)、[gen_h_file.py](../tools/model_zoo_overrides/instance_segmentation/tf/src/utils/gen_h_file.py)。

### 13. 建立部署前的設定自動檢查

- 核對產生設定中的 80 類、1344 候選、32 個遮罩係數、64×64 原型與量化零點。
- 確認模型雜湊未改變，讓設定與實際模型保持一致。
- 不符合預期時停止後續部署，保存標頭檢查結果。

程式：[check_n6_seg_header.py](../scripts/check_n6_seg_header.py)、[header_20260909_014108_3e0IWp](../results/deployment_precheck/header_20260909_014108_3e0IWp)。

### 14. 修正本機模型產碼參數

- 修改 common_benchmark.py，傳入指定 Neural-ART 設定檔、記憶體池與輸入輸出格式。
- 明確指定 UINT8 輸入、INT8 輸出與 NHWC 排列，處理命令參數的引號。
- 保存本機產碼與配置分析方法，實板執行時間另外由 A3 量測。

程式：[modelzoo_n6_local_benchmark.patch](../patches/modelzoo_n6_local_benchmark.patch)、[n6_benchmark_local.sh](../scripts/n6_benchmark_local.sh)、[n6_neuralart_baseline.json](../configs/n6_neuralart_baseline.json)。

### 15. 執行第二段 ONNX 轉換與 N6 模型編譯

- ST Edge AI 接收正式 ST INT8 TFLite，產生內部 ONNX 與量化 JSON，再交由 Neural-ART 編譯。
- 依記憶體池及編譯選項產生模型程式、介面、權重與執行命令資料。
- 分析硬體、混合及軟體執行階段與權重、活化值、外部記憶體配置，保存完整產碼報告。

程式：[network_generate_report.txt](../results/checkpoints/2026-09-09/n6_deployment/run_20260909_020310_zj69FR/generated/network_generate_report.txt)、[編譯分析](../results/checkpoints/2026-09-09/n6_analysis/run_20260909_012357_bvINEg/)。

### 16. 整合推論執行期與韌體建置設定

- 對齊模型產碼、Cortex-M55 執行期標頭與 NetworkRuntime1201_CM55_GCC.a。
- 調整 ModelZoo 組態的包含與連結路徑，將模型命令資料與後處理工作區配置至指定區段。
- 核對內部 RAM、外部 RAM、快閃記憶體與相依檔，讓生成模型能與官方應用程式連結。

程式：[.cproject](../firmware/Application/STM32N6570-DK/STM32CubeIDE/.cproject)、[STM32N657xx.ld](../firmware/Application/STM32N6570-DK/STM32CubeIDE/STM32N657xx.ld)、[dependencies.json](../patches/a1_source_20260918/dependencies.json)。

### 17. 完成映像封裝修正與第一次板端部署

- 產生可執行檔與記憶體配置檔，修正映像標頭與對齊參數（-of 0x80000000、-align）。
- 核對開機程式、應用程式、權重與命令資料的配置，辨識唯一 ST-LINK 目標並透過 SWD 與外部載入器燒錄。
- 從外部快閃記憶體啟動，確認攝影機、框與遮罩畫面，保存產碼、建置與部署紀錄。

程式：[instance_segmentation_signing_alignment.patch](../patches/instance_segmentation_signing_alignment.patch)、[deploy_n6_seg.sh](../scripts/deploy_n6_seg.sh)、[deployment_n6_seg_local.yaml](../configs/deployment_n6_seg_local.yaml)。

## 韌體與通訊

### 攝影機與推論主流程

整合顯示持續擷取、模型單次擷取、同步推論、後處理、顯示與快取維護。正式應用使用單一主迴圈與中斷回呼。

程式：[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)、[app_camerapipeline.c](../firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c)。

### 結構化串列輸出

新增 FRAME／DET／END，輸出類別、信心、框座標與遮罩非零像素數；以整數縮放表示信心與座標，事件與量測使用共同影格序號。

程式：[uart_inference_result.patch](../patches/uart_inference_result.patch)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 人物區域狀態與顯示

以人物框底邊中心判斷區域，連續三幀有人觸發 ENTER、五幀無人觸發 EXIT；整合區域框、狀態與進出計數顯示。

程式：[project_region_event.h](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 有效性檢查與失效處理

檢查物件數、指標、座標與信心等資料；擷取逾時或推論／後處理異常時回報 INVALID／ERROR、清除舊框、顯示失效並停止發布偵測，等待人工重設。

程式：[project_region_event.h](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[region_event.patch](a3_performance_20260918/instrumentation/region_event.patch)。

### 效能量測插樁

加入擷取完成時間／序號，分段量測 ISP、擷取、輸入處理、推論、後處理、區域判定、串列、顯示及快取；處理暖機、前一週期與日誌自身成本。

程式：[a3_profile.patch](a3_performance_20260918/instrumentation/a3_profile.patch)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 串列中斷傳送歷史實驗

保存環形佇列、完整列提交、重要訊息預留空間與統計介面修補，以及建置相依修補、部署與還原程式和紀錄。正式 A1 版本仍使用阻塞傳送；現有紀錄未包含此實驗的獨立加速量測。

程式：[uart_it](publication_supplement_20261113/uart_it)。

## 紀錄與交付

### 分階段版本與程式保存

保存操作腳本、設定、來源修改、工具版本、模型與產物雜湊，按 A1～A5 分階段提交，建立來源與交付索引並公開發布。

程式：[save_n6_session_20260909.sh](../scripts/save_n6_session_20260909.sh)、[PUBLIC_SOURCE_MAP.md](PUBLIC_SOURCE_MAP.md)、[DELIVERY.md](a5_acceptance_20260919/DELIVERY.md)。

## 官方核心與專案修改的關係

模型、驅動與分割核心沿用官方；本專案完成模型流程操作、介面適配、部署修補、通訊、事件、量測與驗收。

後處理來源：[官方封裝](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation/blob/b99b83fe4fcd66c9fa11b6f6528bf9215dc55ab2/Middlewares/ai-postprocessing-wrapper/app_postprocess_iseg_yolo_v8_ui.c)、[分割核心](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation/blob/b99b83fe4fcd66c9fa11b6f6528bf9215dc55ab2/Middlewares/stm32-vision-models-postprocessing/lib_vision_models_pp/Src/iseg_pp_yolov8.c)。

## 程式保存狀態與重現範圍

六份既有操作腳本位於 [scripts](../scripts/)。本次另外封存串列中斷實驗的部署與還原程式；它們保持歷史內容，沒有在本次整理中重新執行。

原始模型匯出、ST 量化及 A1～A5 各項臨時終端測試程式，尚未找到成套保存的原始腳本。相關設定、方法、日誌與結果分別列於上文；不能將現有資料包稱為完整可直接重跑的測試工具包。後續若重建操作入口，須標明為整理版本及其實測狀態。

完整模型、原始張量、SDK、函式庫及可燒錄映像仍依原有雜湊與相依索引追溯，本儲存庫未提供完整離線建置套件。

## 後續測試與結果

以下保留固定輸入、效能、記憶體、來源重建與板端驗收的詳細索引；本次文件整理沒有重新執行硬體測試。

## A2 正確性驗證

### 固定輸入與板端張量收集

建立中央裁切、256×256 RGB 固定像素及 UINT8／INT8／FLOAT32 對應；讀回權重核對，使用官方驗證韌體收集四張及後續 50 張原始輸出。

程式：[a2_validation_20260918](a2_validation_20260918/README.md)、[n6_reference.json](a2_validation_20260918/regression50/n6_reference.json)。

### 數值與後端差異診斷

比較一致率、LSB 誤差、餘弦相似度與相對 L2；分開分析框座標、類別分數、遮罩係數，另停用預設代理後端比較。

程式：[numerical_comparison.json](a2_validation_20260918/fixed4/numerical_comparison.json)、[tensor_parts.json](publication_supplement_20261113/a2/tensor_parts.json)、[pc_backend_check.json](publication_supplement_20261113/a2/pc_backend_check.json)。

### 共同後處理與最差案例分析

使用固定 Ultralytics 版本、共用信心／NMS 設定及一對一配對比較框與遮罩；加入浮點參照、裁切後標註與餐桌遮罩最差案例視覺化。

程式：[postprocess_config.json](a2_validation_20260918/fixed4/postprocess_config.json)、[object_mask_comparison.json](a2_validation_20260918/fixed4/object_mask_comparison.json)、[float_int8_comparison.json](a2_validation_20260918/fixed4/float_int8_comparison.json)、[annotation_comparison.json](a2_validation_20260918/fixed4/annotation_comparison.json)、[worst_mask.png](a2_validation_20260918/fixed4/worst_mask.png)。

### 50 張回歸與逐例追查

依影像編號與雜湊排除 COCO8 重疊，選有人／無人各 25 張、共 59 個人物標註；比對三組結果、重跑參考影像，定位誤檢與漏檢差異。

程式：[inputs_manifest.json](a2_validation_20260918/regression50/inputs_manifest.json)、[evaluation.json](a2_validation_20260918/regression50/evaluation.json)、[person_difference_review.json](a2_validation_20260918/regression50/person_difference_review.json)。

## A3 效能量測

### 完整管線與日誌成本

分析無人／有人各 1000 個完整週期，分列擷取、推論、後處理、串列、顯示與量測日誌成本。

程式：[pipeline](a3_performance_20260918/pipeline)、[a3_performance_20260918](a3_performance_20260918/README.md)。

### 重複推論與逐區塊分析

排除兩次暖機，量測三組各十次一般模式及三次逐區塊模式；35 次輸出核對，分析 58 個區塊，保存時鐘與官方計時來源。

程式：[repeat](a3_performance_20260918/validation/repeat)、[analysis.json](a3_performance_20260918/analysis.json)。

## A4 記憶體實驗

### 配置基準與韌體布局核對

比對 A2 模型產碼、尋找相符的原始報告，檢查攝影機與驗證韌體區段及堆疊相關配置，保存來源定位紀錄。

程式：[baseline_settings.json](publication_supplement_20261113/a4/baseline_settings.json)、[firmware_layout.json](publication_supplement_20261113/a4/firmware_layout.json)、[generation_reports.json](publication_supplement_20261113/a4/generation_reports.json)。

### 控制變因產碼與配置比較

將 npuRAM6 可用容量由 448 改為 320 KiB，其餘設定固定；分別產碼，核對權重並比較實體池已用量，排除合併虛擬池的重複計算。

程式：[comparison_plan.json](a4_memory_20260918/comparison_plan.json)、[memory_comparison.json](a4_memory_20260918/memory_comparison.json)、[A_current](publication_supplement_20261113/a4/A_current)、[B_npuram6_320k](publication_supplement_20261113/a4/B_npuram6_320k)。

### 兩組實板計時與輸出回歸

分別建置、載入與重複計時；A 組四張固定輸入核對，B 組 50 張原始輸出與原 N6 基準逐位元組相同。正式攝影機仍採原配置。

程式：[A](a4_memory_20260918/A)、[B](a4_memory_20260918/B)、[a4_memory_20260918](a4_memory_20260918/README.md)。

## A1 來源與重建

### 來源固定與隔離還原

固定兩個官方基底版本，保存修改、新增與刪除清單及三份二進位相依資訊；隔離還原並核對 100 份來源與相依檔。

程式：[a1_source_20260918](../patches/a1_source_20260918)、[replay_verification.json](a1_reproducible_20260918/replay_verification.json)。

### 乾淨重建與燒錄讀回

在既有環境乾淨重建，核對來源、ELF 區段及模型命令資料；準備應用映像，讀回權重／命令，燒錄後逐位元組核對並確認重新供電運作。

程式：[a1_reproducible_20260918](a1_reproducible_20260918/README.md)、[rebuild_report.json](a1_reproducible_20260918/rebuild_report.json)、[flash_manifest.json](a1_reproducible_20260918/flash_manifest.json)。

## A5 板端驗收

### 冷啟動與受控區域事件

完成三次完整冷啟動、從重設後首筆序號同步，以及依提示進行的三次人物進入／離開事件檢查與畫面更新確認。

程式：[cold_boots.json](a5_acceptance_20260919/cold_boots.json)、[region_reset.json](a5_acceptance_20260919/region_reset.json)。

### 長測異常分析與重新量測

保留首次長測的序號不連續與原失敗判定，分析截斷列及連續區段；新開機同步後重測通過，板端週期合計 1800.016 秒、18077 個完整影格。

程式：[sequence_review.json](a5_acceptance_20260919/sequence_review.json)、[stability_retest.json](a5_acceptance_20260919/stability_retest.json)、[a5](publication_supplement_20261113/a5)。

### 故障注入與正式韌體恢復

在隔離副本第 50 幀模擬擷取完成通知逾時，確認失效回報、清除舊框及停止發布；觀察至少十秒，再還原正式映像、讀回核對並確認畫面與偵測。

程式：[capture_fault.patch](a5_acceptance_20260919/capture_fault.patch)、[capture_fault.json](a5_acceptance_20260919/capture_fault.json)、[restore_observation.json](a5_acceptance_20260919/restore_observation.json)。

## 結果判讀邊界

- A1 的乾淨重建在既有環境完成；隔離還原只核對來源與相依檔，未在該目錄建置。
- A2 比較原始張量與共用電腦後處理，沒有證明攝影機像素或板端 C 後處理逐像素等價；50 張為部署回歸集。
- A3 模型執行時間與攝影機完整週期分開，含硬體／混合／軟體模型區塊。
- A4 統計編譯配置的實體池已用量；微小計時差異不當作明確加速，B 配置未成為正式攝影機韌體。
- A5 首次長測異常根因仍未確定；重測通過與軟體逾時注入依各自條件解讀。
- 串列中斷實驗有來源與部署／還原紀錄，現有清單沒有獨立的效能比較結果；不宣稱它是正式版的傳輸方式。
