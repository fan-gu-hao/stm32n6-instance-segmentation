# 完整工作、程式與證據索引

本索引涵蓋模型處理、工具修正、韌體整合、歷史實驗與驗證。補檔沿用既有資料，沒有重新執行硬體測試。

## 模型與環境

### 環境與工具版本固定

保存模型匯出、ST 量化與部署環境套件版本，區分各環境用途。既有腳本使用原開發環境路徑。

程式／證據：[requirements](../requirements)。

### 原始模型與圖片驗證

確認 YOLOv8n-seg 模型類型、80 類與框／遮罩輸出，完成電腦端靜態圖片功能檢查。

程式／證據：[pc_baseline.md](pc_baseline.md)。

### 電腦攝影機驗證

完成原始模型與 INT8 模型攝影機功能確認；原始模型入口腳本已公開，其他操作保留於歷史紀錄。

程式／證據：[pc_webcam.sh](../scripts/pc_webcam.sh)、[session_2026-09-09.md](session_2026-09-09.md)。

### 模型格式匯出

從 .pt 經 ONNX、onnx2tf 轉成 SavedModel，並產生浮點與 INT8 TFLite；核對輸入輸出介面與遮罩布局。

程式／證據：[03_export_seg.log](../results/checkpoints/2026-09-09/logs/03_export_seg.log)、[pc_baseline.md](pc_baseline.md)。

### ST 逐通道 INT8 量化

另從 SavedModel 執行 ST 逐通道量化，使用 COCO8-seg 的四張校正影像；此 ST TFLite 為正式部署基準，與匯出工具產生的 INT8 檔區分。

程式／證據：[yolov8n_seg_int8_int8.yaml](../configs/yolov8n_seg_int8_int8.yaml)、[04_st_quantization_seg.log](../results/checkpoints/2026-09-09/logs/04_st_quantization_seg.log)。

### 量化介面核對

核對張量形狀、資料型別、比例、零點及逐通道量化資訊。TFLite 輸入為 INT8，N6 產碼介面指定 UINT8／NHWC。

程式／證據：[interface_check.txt](../results/quantization/interface_check.txt)、[model.sha256](../results/quantization/model.sha256)。

### 三種模型電腦比較

以一致的推論參數比較原始模型、浮點 TFLite 與 ST INT8，保存圖片、模型雜湊、參數、日誌與視覺結果；後續 A2 再建立固定像素數值驗證。

程式／證據：[check_seg_models_pc.sh](../scripts/check_seg_models_pc.sh)、[run_20260909_010330_KzpJuw](../results/pc_tflite_check/run_20260909_010330_KzpJuw)。

## 編譯與部署

### 後處理輸出對應修正

修改 gen_h_file.py，依張量形狀辨識偵測與遮罩原型，檢查型別、類別／係數數量及官方排序條件，修正產生設定時的對應。

程式／證據：[modelzoo_seg_output_mapping.patch](../patches/modelzoo_seg_output_mapping.patch)、[gen_h_file.py](../tools/model_zoo_overrides/instance_segmentation/tf/src/utils/gen_h_file.py)。

### 部署前標頭自動檢查

檢查產生設定中的 80 類、1344 候選、32 遮罩係數、64×64 原型與量化零點，並核對模型雜湊未改變。

程式／證據：[check_n6_seg_header.py](../scripts/check_n6_seg_header.py)、[header_20260909_014108_3e0IWp](../results/deployment_precheck/header_20260909_014108_3e0IWp)。

### 本機產碼參數修正

修改 common_benchmark.py，傳入指定 Neural-ART 配置、記憶體池與輸入輸出格式，處理命令參數引號。此階段是本機產碼與配置分析。

程式／證據：[modelzoo_n6_local_benchmark.patch](../patches/modelzoo_n6_local_benchmark.patch)、[n6_benchmark_local.sh](../scripts/n6_benchmark_local.sh)、[n6_neuralart_baseline.json](../configs/n6_neuralart_baseline.json)。

### NPU 編譯與記憶體配置分析

ST Edge AI 接收量化 TFLite，內部產生另一份 ONNX 與量化 JSON，再由 Neural-ART 產生模型程式、權重、命令資料與介面；保存配置報告。

程式／證據：[network_generate_report.txt](../results/checkpoints/2026-09-09/n6_deployment/run_20260909_020310_zj69FR/generated/network_generate_report.txt)。

### 執行期與建置設定整合

對齊產碼與 NetworkRuntime1201_CM55_GCC.a；ModelZoo 組態配置命令資料與後處理暫存的區段，核對連結配置與相依檔。

程式／證據：[.cproject](../firmware/Application/STM32N6570-DK/STM32CubeIDE/.cproject)、[STM32N657xx.ld](../firmware/Application/STM32N6570-DK/STM32CubeIDE/STM32N657xx.ld)、[dependencies.json](../patches/a1_source_20260918/dependencies.json)。

### 啟動映像對齊與實板部署

修正映像產生命令的 -of 0x80000000 與 -align；確認唯一 ST-LINK 目標，執行產碼、建置與燒錄並保存紀錄。此修補是標頭與對齊處理。

程式／證據：[instance_segmentation_signing_alignment.patch](../patches/instance_segmentation_signing_alignment.patch)、[deploy_n6_seg.sh](../scripts/deploy_n6_seg.sh)、[deployment_n6_seg_local.yaml](../configs/deployment_n6_seg_local.yaml)。

## 韌體與通訊

### 攝影機與推論主流程

整合顯示持續擷取、模型單次擷取、同步推論、後處理、顯示與快取維護。正式應用使用單一主迴圈與中斷回呼。

程式／證據：[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)、[app_camerapipeline.c](../firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c)。

### 結構化串列輸出

新增 FRAME／DET／END，輸出類別、信心、框座標與遮罩非零像素數；以整數縮放表示信心與座標，事件與量測使用共同影格序號。

程式／證據：[uart_inference_result.patch](../patches/uart_inference_result.patch)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 人物區域狀態與顯示

以人物框底邊中心判斷區域，連續三幀有人觸發 ENTER、五幀無人觸發 EXIT；整合區域框、狀態與進出計數顯示。

程式／證據：[project_region_event.h](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 有效性檢查與失效處理

檢查物件數、指標、座標與信心等資料；擷取逾時或推論／後處理異常時回報 INVALID／ERROR、清除舊框、顯示失效並停止發布偵測，等待人工重設。

程式／證據：[project_region_event.h](../firmware/Application/STM32N6570-DK/Inc/project_region_event.h)、[region_event.patch](a3_performance_20260918/instrumentation/region_event.patch)。

### 效能量測插樁

加入擷取完成時間／序號，分段量測 ISP、擷取、輸入處理、推論、後處理、區域判定、串列、顯示及快取；處理暖機、前一週期與日誌自身成本。

程式／證據：[a3_profile.patch](a3_performance_20260918/instrumentation/a3_profile.patch)、[main.c](../firmware/Application/STM32N6570-DK/Src/main.c)。

### 串列中斷傳送歷史實驗

保存環形佇列、完整列提交、重要訊息預留空間與統計介面修補，以及建置相依修補、部署與還原程式和紀錄。正式 A1 版本仍使用阻塞傳送；現有證據不宣稱此實驗有量測到加速。

程式／證據：[uart_it](publication_supplement_20261113/uart_it)。

## A2 正確性驗證

### 固定輸入與板端張量收集

建立中央裁切、256×256 RGB 固定像素及 UINT8／INT8／FLOAT32 對應；讀回權重核對，使用官方驗證韌體收集四張及後續 50 張原始輸出。

程式／證據：[a2_validation_20260918](a2_validation_20260918/README.md)、[n6_reference.json](a2_validation_20260918/regression50/n6_reference.json)。

### 數值與後端差異診斷

比較一致率、LSB 誤差、餘弦相似度與相對 L2；分開分析框座標、類別分數、遮罩係數，另停用預設代理後端比較。

程式／證據：[numerical_comparison.json](a2_validation_20260918/fixed4/numerical_comparison.json)、[tensor_parts.json](publication_supplement_20261113/a2/tensor_parts.json)、[pc_backend_check.json](publication_supplement_20261113/a2/pc_backend_check.json)。

### 共同後處理與最差案例分析

使用固定 Ultralytics 版本、共用信心／NMS 設定及一對一配對比較框與遮罩；加入浮點參照、裁切後標註與餐桌遮罩最差案例視覺化。

程式／證據：[postprocess_config.json](a2_validation_20260918/fixed4/postprocess_config.json)、[object_mask_comparison.json](a2_validation_20260918/fixed4/object_mask_comparison.json)、[float_int8_comparison.json](a2_validation_20260918/fixed4/float_int8_comparison.json)、[annotation_comparison.json](a2_validation_20260918/fixed4/annotation_comparison.json)、[worst_mask.png](a2_validation_20260918/fixed4/worst_mask.png)。

### 50 張回歸與逐例追查

依影像編號與雜湊排除 COCO8 重疊，選有人／無人各 25 張、共 59 個人物標註；比對三組結果、重跑參考影像，定位誤檢與漏檢差異。

程式／證據：[inputs_manifest.json](a2_validation_20260918/regression50/inputs_manifest.json)、[evaluation.json](a2_validation_20260918/regression50/evaluation.json)、[person_difference_review.json](a2_validation_20260918/regression50/person_difference_review.json)。

## A3 效能量測

### 完整管線與日誌成本

分析無人／有人各 1000 個完整週期，分列擷取、推論、後處理、串列、顯示與量測日誌成本。

程式／證據：[pipeline](a3_performance_20260918/pipeline)、[a3_performance_20260918](a3_performance_20260918/README.md)。

### 重複推論與逐區塊分析

排除兩次暖機，量測三組各十次一般模式及三次逐區塊模式；35 次輸出核對，分析 58 個區塊，保存時鐘與官方計時來源。

程式／證據：[repeat](a3_performance_20260918/validation/repeat)、[analysis.json](a3_performance_20260918/analysis.json)。

## A4 記憶體實驗

### 配置基準與韌體布局核對

比對 A2 模型產碼、尋找相符的原始報告，檢查攝影機與驗證韌體區段及堆疊相關配置，保存來源定位紀錄。

程式／證據：[baseline_settings.json](publication_supplement_20261113/a4/baseline_settings.json)、[firmware_layout.json](publication_supplement_20261113/a4/firmware_layout.json)、[generation_reports.json](publication_supplement_20261113/a4/generation_reports.json)。

### 控制變因產碼與配置比較

將 npuRAM6 可用容量由 448 改為 320 KiB，其餘設定固定；分別產碼，核對權重並比較實體池已用量，排除合併虛擬池的重複計算。

程式／證據：[comparison_plan.json](a4_memory_20260918/comparison_plan.json)、[memory_comparison.json](a4_memory_20260918/memory_comparison.json)、[A_current](publication_supplement_20261113/a4/A_current)、[B_npuram6_320k](publication_supplement_20261113/a4/B_npuram6_320k)。

### 兩組實板計時與輸出回歸

分別建置、載入與重複計時；A 組四張固定輸入核對，B 組 50 張原始輸出與原 N6 基準逐位元組相同。正式攝影機仍採原配置。

程式／證據：[A](a4_memory_20260918/A)、[B](a4_memory_20260918/B)、[a4_memory_20260918](a4_memory_20260918/README.md)。

## A1 來源與重建

### 來源固定與隔離還原

固定兩個官方基底版本，保存修改、新增與刪除清單及三份二進位相依資訊；隔離還原並核對 100 份來源與相依檔。

程式／證據：[a1_source_20260918](../patches/a1_source_20260918)、[replay_verification.json](a1_reproducible_20260918/replay_verification.json)。

### 乾淨重建與燒錄讀回

在既有環境乾淨重建，核對來源、ELF 區段及模型命令資料；準備應用映像，讀回權重／命令，燒錄後逐位元組核對並確認重新供電運作。

程式／證據：[a1_reproducible_20260918](a1_reproducible_20260918/README.md)、[rebuild_report.json](a1_reproducible_20260918/rebuild_report.json)、[flash_manifest.json](a1_reproducible_20260918/flash_manifest.json)。

## A5 板端驗收

### 冷啟動與受控區域事件

完成三次完整冷啟動、從重設後首筆序號同步，以及依提示進行的三次人物進入／離開事件檢查與畫面更新確認。

程式／證據：[cold_boots.json](a5_acceptance_20260919/cold_boots.json)、[region_reset.json](a5_acceptance_20260919/region_reset.json)。

### 長測異常分析與重新量測

保留首次長測的序號不連續與原失敗判定，分析截斷列及連續區段；新開機同步後重測通過，板端週期合計 1800.016 秒、18077 個完整影格。

程式／證據：[sequence_review.json](a5_acceptance_20260919/sequence_review.json)、[stability_retest.json](a5_acceptance_20260919/stability_retest.json)、[a5](publication_supplement_20261113/a5)。

### 故障注入與正式韌體恢復

在隔離副本第 50 幀模擬擷取完成通知逾時，確認失效回報、清除舊框及停止發布；觀察至少十秒，再還原正式映像、讀回核對並確認畫面與偵測。

程式／證據：[capture_fault.patch](a5_acceptance_20260919/capture_fault.patch)、[capture_fault.json](a5_acceptance_20260919/capture_fault.json)、[restore_observation.json](a5_acceptance_20260919/restore_observation.json)。

## 紀錄與交付

### 分階段版本與證據保存

保存操作腳本、設定、來源修改、工具版本、模型與產物雜湊，按 A1～A5 分階段提交，建立來源與交付索引並公開發布。

程式／證據：[save_n6_session_20260909.sh](../scripts/save_n6_session_20260909.sh)、[PUBLIC_SOURCE_MAP.md](PUBLIC_SOURCE_MAP.md)、[DELIVERY.md](a5_acceptance_20260919/DELIVERY.md)。

## 官方核心與專案修改的關係

模型、驅動與分割核心沿用官方；本專案完成模型流程操作、介面適配、部署修補、通訊、事件、量測與驗收。

後處理來源：[官方封裝](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation/blob/b99b83fe4fcd66c9fa11b6f6528bf9215dc55ab2/Middlewares/ai-postprocessing-wrapper/app_postprocess_iseg_yolo_v8_ui.c)、[分割核心](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation/blob/b99b83fe4fcd66c9fa11b6f6528bf9215dc55ab2/Middlewares/stm32-vision-models-postprocessing/lib_vision_models_pp/Src/iseg_pp_yolov8.c)。

## 程式保存狀態與重現範圍

六份既有操作腳本位於 [scripts](../scripts/)。本次另外封存串列中斷實驗的部署與還原程式；它們保持歷史內容，沒有在本次整理中重新執行。

原始模型匯出、ST 量化及 A1～A5 各項臨時終端測試程式，尚未找到成套保存的原始腳本。相關設定、方法、日誌與結果分別列於上文；不能將現有證據包稱為完整可直接重跑的測試工具包。後續若重建操作入口，須標明為整理版本及其實測狀態。

完整模型、原始張量、SDK、函式庫及可燒錄映像仍依原有雜湊與相依索引追溯，本儲存庫未提供完整離線建置套件。

## 結果判讀邊界

- A1 的乾淨重建在既有環境完成；隔離還原只核對來源與相依檔，未在該目錄建置。
- A2 比較原始張量與共用電腦後處理，沒有證明攝影機像素或板端 C 後處理逐像素等價；50 張為部署回歸集。
- A3 模型執行時間與攝影機完整週期分開，含硬體／混合／軟體模型區塊。
- A4 統計編譯配置的實體池已用量；微小計時差異不當作明確加速，B 配置未成為正式攝影機韌體。
- A5 首次長測異常根因仍未確定；重測通過與軟體逾時注入依各自條件解讀。
- 串列中斷實驗有來源與部署／還原紀錄，現有清單沒有獨立的效能比較結果；不宣稱它是正式版的傳輸方式。
