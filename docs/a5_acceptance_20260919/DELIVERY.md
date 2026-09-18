# 交付索引

正式韌體 SHA-256：63d5086cdbe8637e7470cc294252f3218d7784e2a56e6e92aafba4c8e9dc55a2

| 項目 | 路徑 |
| --- | --- |
| 來源固定與重建 | [A1 報告](../a1_reproducible_20260918/README.md) |
| 模型正確性 | [A2 報告](../a2_validation_20260918/README.md) |
| 效能量測 | [A3 報告](../a3_performance_20260918/README.md) |
| 記憶體配置比較 | [A4 報告](../a4_memory_20260918/README.md) |
| 開機及運行驗收 | [A5 報告](README.md) |
| 原始碼版本與修補 | [來源鎖定清單](../../patches/a1_source_20260918/source_lock.json) |
| 模型、權重及執行期函式庫 | [相依檔案清單](../../patches/a1_source_20260918/dependencies.json) |
| 正式燒錄映像的大小與雜湊 | [映像清單](../../results/a1_freeze/run_20260918_190900/rebuild_20260918_191804/flash_20260918_192610/manifest.json) |

| 燒錄項目 | 檔案 | 位址 |
| --- | --- | --- |
| 開機程式 | stm32ai-modelzoo-services/application_code/instance_segmentation/STM32N6/FSBL/ai_fsbl.hex | 使用 HEX 內的位址 |
| 正式應用程式 | [app_signed.bin](../../results/a1_freeze/run_20260918_190900/rebuild_20260918_191804/flash_20260918_192610/app_signed.bin) | 0x70100000 |
| 模型權重 | [weights_reference.bin](../../results/a1_freeze/run_20260918_190900/rebuild_20260918_191804/flash_20260918_192610/weights_reference.bin) | 0x70380000 |
| 模型命令 | [ecblob_reference.bin](../../results/a1_freeze/run_20260918_190900/rebuild_20260918_191804/flash_20260918_192610/ecblob_reference.bin) | 0x71380000 |

正式版本沿用 A1；A4 的 B 配置是實驗結果，故障注入映像不是交付版本。
已驗證來源還原核對與現有環境重建；未另測試全新電腦上的完整重建。
results 內的原始日誌、二進位檔及相依檔案副本仍須保留，本次未全部加入 Git。
示範影片與 GitHub 發布由使用者安排日後完成。
