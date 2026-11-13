# STM32N6 即時實例分割與區域事件偵測

**繁體中文** | [English](README.en.md)

以 STM32N6570-DK 與 YOLOv8n-seg 完成模型匯出、ST INT8 量化、NPU 編譯部署、
後處理介面適配、攝影機與顯示整合、串列通訊、人物區域事件、效能與記憶體實驗及板端驗收。

## 模型與系統流程

模型流程：原始 .pt → ONNX → SavedModel → ST 逐通道 INT8 TFLite → ST Edge AI／Neural-ART → N6 程式、權重與命令資料。
ST 編譯階段另會產生內部 ONNX 與量化資訊；正式量化模型與匯出工具產生的 INT8 檔有明確區分。

正式韌體以單一主迴圈與攝影機中斷回呼運作：擷取 → 同步推論 → 分割後處理 → 區域狀態 → 串列輸出與畫面更新。
模型、驅動與後處理核心保留官方來源，專案中的操作流程、適配修補與新增邏輯逐項列於下方。

## 已完成的實作與實驗

| 範圍 | 工作內容 |
| --- | --- |
| 模型與環境 | 環境與工具版本固定；原始模型與圖片驗證；電腦攝影機驗證；模型格式匯出；ST 逐通道 INT8 量化；量化介面核對；三種模型電腦比較 |
| 編譯與部署 | 後處理輸出對應修正；部署前標頭自動檢查；本機產碼參數修正；NPU 編譯與記憶體配置分析；執行期與建置設定整合；啟動映像對齊與實板部署 |
| 韌體與通訊 | 攝影機與推論主流程；結構化串列輸出；人物區域狀態與顯示；有效性檢查與失效處理；效能量測插樁；串列中斷傳送歷史實驗 |
| A2 正確性驗證 | 固定輸入與板端張量收集；數值與後端差異診斷；共同後處理與最差案例分析；50 張回歸與逐例追查 |
| A3 效能量測 | 完整管線與日誌成本；重複推論與逐區塊分析 |
| A4 記憶體實驗 | 配置基準與韌體布局核對；控制變因產碼與配置比較；兩組實板計時與輸出回歸 |
| A1 來源與重建 | 來源固定與隔離還原；乾淨重建與燒錄讀回 |
| A5 板端驗收 | 冷啟動與受控區域事件；長測異常分析與重新量測；故障注入與正式韌體恢復 |
| 紀錄與交付 | 分階段版本與證據保存 |

每項工作對應的程式、修改與結果見 [完整工作索引](docs/WORK_IMPLEMENTATION_INDEX.md)。
本次補充的歷史程式與原始證據見 [補檔索引](docs/publication_supplement_20261113/README.md)。
已完成的測試與尚未整理成套的操作腳本分別標示；示範影片待補。

流程總覽、模型轉換與介面說明見[工程流程與實作證據](docs/engineering-workflow.md)。

## 驗證成果

| 階段 | 主要結果 | 完整紀錄 |
| --- | --- | --- |
| A1：來源與重建 | 完成來源凍結、乾淨重建、燒錄讀回及隔離目錄還原核對 | [A1 報告](docs/a1_reproducible_20260918/README.md) |
| A2：固定輸入驗證 | 完成四張流程驗證及 50 張回歸；N6 人物精確率 0.870、召回率 0.678 | [A2 報告](docs/a2_validation_20260918/README.md) |
| A3：效能量測 | 固定輸入一般推論平均 48.6066 毫秒；含日誌的攝影機管線約 8.066～10.046 幀／秒 | [A3 報告](docs/a3_performance_20260918/README.md) |
| A4：記憶體配置 | 編譯器回報的實體 RAM 池已用量減少 162.5625 KiB；50 張板端輸出與原 N6 基準逐位元組一致 | [A4 報告](docs/a4_memory_20260918/README.md) |
| A5：板端驗收 | 三次冷啟動、三次進出事件、30 分鐘穩定性重測、模擬擷取逾時及正式韌體恢復通過 | [A5 報告](docs/a5_acceptance_20260919/README.md) |

A2 的 50 張資料包含有人與無人影像各 25 張，共 59 個人物標註。
電腦 INT8 的人物精確率／召回率為 0.872／0.695；
N6 為 0.870／0.678。這是固定小型回歸集的結果，並非標準 COCO mAP。

A3 的固定輸入推論時間與攝影機完整週期採用不同量測範圍；
完整週期包含擷取、推論、後處理、顯示與日誌輸出。

A4 將 npuRAM6 可分配容量從 448 KiB 改為 320 KiB。
A／B 平均推論時間為 48.6079／48.5992 毫秒，差異約 0.02%，
不據此宣稱有明確加速。正式攝影機韌體仍使用原配置，
B 組保留為經過驗證的配置實驗。

## 主要程式碼

| 檔案 | 用途 |
| --- | --- |
| [main.c](firmware/Application/STM32N6570-DK/Src/main.c) | 應用程式主流程、輸出與失效處理整合 |
| [app_camerapipeline.c](firmware/Application/STM32N6570-DK/Src/app_camerapipeline.c) | 攝影機擷取流程 |
| [project_region_event.h](firmware/Application/STM32N6570-DK/Inc/project_region_event.h) | 區域事件邏輯 |
| [app_config.h](firmware/Application/STM32N6570-DK/Inc/app_config.h) | 應用程式設定 |
| [量化設定](configs/yolov8n_seg_int8_int8.yaml) | SavedModel 來源、校正資料、逐通道與 INT8 介面設定 |
| [三模型比較腳本](scripts/check_seg_models_pc.sh) | 原始模型、浮點 TFLite 與 ST INT8 的共同圖片比較 |
| [Model Zoo 修改](tools/model_zoo_overrides/) | 本機產碼與偵測／遮罩輸出對應修補 |
| [部署腳本](scripts/deploy_n6_seg.sh) | 工具與模型檢查、ST-LINK 識別、產碼／建置／封裝／燒錄 |
| [來源對照](docs/PUBLIC_SOURCE_MAP.md) | 發佈副本與原始專案檔案的對應關係 |

firmware/ 是核心程式碼副本。編譯時需搭配固定版本的官方專案、
SDK 與 A1 所列的相依檔案。

## 重建與交付資料

- [來源凍結與重建證據](docs/a1_reproducible_20260918/README.md)
- [固定版本的修補與相依紀錄](patches/a1_source_20260918/)
- [韌體與交付索引](docs/a5_acceptance_20260919/DELIVERY.md)
- [既有操作腳本](scripts/)

目前驗證涵蓋既有開發環境的乾淨重建，以及隔離目錄的來源與相依檔還原核對。
全新電腦的自動環境安裝與完整重建尚未驗證。

## 驗證範圍與限制

- 固定輸入採中央正方形裁切、雙線性縮放至 256×256、RGB；
  攝影機 DCMIPP 的像素一致性尚未另外驗證。
- 電腦 INT8 與 N6 原始輸出存在數值差異，詳見 A2。
  A4 的逐位元組一致，是與原 N6 基準比較。
- A4 的 RAM 數字來自編譯器配置報告，並非整板執行時的記憶體峰值。
- 首次長測的一次序號不連續仍保留在 A5 紀錄中，原因未確定；
  後續從新開機同步的 30 分鐘重測通過。
- 擷取逾時驗證使用軟體故障注入，測試失效提示、清除舊框與停止發布結果。

## 後續雙模型作品

[STM32N6 雙模型語音找物](https://github.com/fan-gu-hao/stm32n6-voice-object-finder)延續本作品的模型部署與視覺整合經驗，增加板上收音、客製 KWS 訓練、INT8 部署、Python／C 比對、快取一致性與 FreeRTOS 雙模型協作。兩個作品的開發流程相互連結，各自保存實際模型版本與驗證結果。

## 第三方來源與授權

- [ST Model Zoo](https://github.com/STMicroelectronics/stm32ai-modelzoo-services)
- [ST STM32N6 實例分割範例](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation)
- [保存的上游授權文件](licenses/)
- [來源與修改對照](docs/PUBLIC_SOURCE_MAP.md)

第三方檔案保留原始著作權與授權資訊。
模型、SDK、執行期函式庫及其他相依檔案，依 A1 紀錄準備。
