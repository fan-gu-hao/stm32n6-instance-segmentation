# STM32N6 即時實例分割與區域事件偵測

在 STM32N6570-DK 上執行 YOLOv8n-seg，整合攝影機擷取、
實例分割、螢幕顯示、串列輸出，以及人物進入／離開區域事件。

已完成 A1～A5 的驗證與紀錄。示範影片將於後續補上。

## 本專案實作範圍

沿用官方模型、驅動、推論執行期與後處理，主要工作包括：

- 整合攝影機、模型推論、顯示與串列通訊（UART）。
- 輸出 FRAME、DET、END、EVENT、ERROR 與 PROFILE 紀錄。
- 整合人物區域事件，以及擷取逾時時的失效處理。
- 建立固定輸入比對、分階段計時、記憶體配置實驗與板端驗收。
- 保存來源修改、相依檔案雜湊與可追溯的測試證據。

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
| [Model Zoo 修改](tools/model_zoo_overrides/) | 部署與產生設定檔的相關修改 |
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

## 第三方來源與授權

- [ST Model Zoo](https://github.com/STMicroelectronics/stm32ai-modelzoo-services)
- [ST STM32N6 實例分割範例](https://github.com/STMicroelectronics/STM32N6-GettingStarted-InstanceSegmentation)
- [保存的上游授權文件](licenses/)
- [來源與修改對照](docs/PUBLIC_SOURCE_MAP.md)

第三方檔案保留原始著作權與授權資訊。
模型、SDK、執行期函式庫及其他相依檔案，依 A1 紀錄準備。
