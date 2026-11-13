# 公開內容補充紀錄

補入既有程式與實驗證據；原開發專案不變更。來源路徑、大小與 SHA-256 見 [來源清單](source_manifest.json)。

## 串列中斷歷史實驗

保存兩份修補、建置與安裝資訊、部署／還原程式及日誌。主修補包含 4096-byte 環形佇列、512-byte 逐列緩衝、256-byte 重要訊息預留空間與統計介面；採中斷傳送，並非 DMA 傳送。第二份修補加入建置相依來源。

此目錄是歷史實驗封存，不是現行韌體安裝指令。正式 A1 基準使用阻塞式串列；實驗的加速效果與還原原因不由檔名推定。

另補入[可閱讀的 C／H 與兩版安裝工具](uart_it/source_snapshot/README.md)，包含佇列、中斷回呼、應用整合，以及 HAL 相依修復。這五份快照的來源與雜湊另記於[快照來源清單](uart_it/source_snapshot/provenance.json)，不混入先前補檔的原始清單。

## 細部分析與原始證據

A2 補張量分部與代理後端比較；A4 補布局索引與 A/B 原始產碼資料；A5 補首次與重測的完整長測日誌。A5 日誌和兩份串列修補已對照先前 SHA-256，其餘副本建立本次內容指紋。

| 保存檔案 | 位元組 |
| --- | ---: |
| [uart_it/patches/uart_it_v1_20260914_054405_207092.patch](uart_it/patches/uart_it_v1_20260914_054405_207092.patch) | 12444 |
| [uart_it/patches/uart_it_v1_20260914_055728_067784.patch](uart_it/patches/uart_it_v1_20260914_055728_067784.patch) | 893 |
| [uart_it/build_20260914_055733_234190.json](uart_it/build_20260914_055733_234190.json) | 628 |
| [uart_it/install_20260914_054405_207092/manifest.json](uart_it/install_20260914_054405_207092/manifest.json) | 1673 |
| [uart_it/install_20260914_055728_067784/manifest.json](uart_it/install_20260914_055728_067784/manifest.json) | 817 |
| [uart_it/deploy_20260914_060547_683657/deploy_uart_it_v1.py](uart_it/deploy_20260914_060547_683657/deploy_uart_it_v1.py) | 10597 |
| [uart_it/deploy_20260914_060547_683657/deploy.log](uart_it/deploy_20260914_060547_683657/deploy.log) | 19741 |
| [uart_it/deploy_20260914_060547_683657/manifest.json](uart_it/deploy_20260914_060547_683657/manifest.json) | 906 |
| [uart_it/deploy_20260914_060547_683657/sections.txt](uart_it/deploy_20260914_060547_683657/sections.txt) | 3113 |
| [uart_it/rollback_20260914_061621_901943/restore_before_uart_it.py](uart_it/rollback_20260914_061621_901943/restore_before_uart_it.py) | 11723 |
| [uart_it/rollback_20260914_061621_901943/flash.log](uart_it/rollback_20260914_061621_901943/flash.log) | 7786 |
| [uart_it/rollback_20260914_061621_901943/manifest.json](uart_it/rollback_20260914_061621_901943/manifest.json) | 1850 |
| [uart_it/rollback_20260914_061621_901943/install_manifest_0.json](uart_it/rollback_20260914_061621_901943/install_manifest_0.json) | 1673 |
| [uart_it/rollback_20260914_061621_901943/install_manifest_1.json](uart_it/rollback_20260914_061621_901943/install_manifest_1.json) | 817 |
| [a2/tensor_parts.json](a2/tensor_parts.json) | 4866 |
| [a2/pc_backend_check.json](a2/pc_backend_check.json) | 1980 |
| [a4/baseline_profile.json](a4/baseline_profile.json) | 343 |
| [a4/baseline_settings.json](a4/baseline_settings.json) | 754 |
| [a4/firmware_layout.json](a4/firmware_layout.json) | 698 |
| [a4/generation_reports.json](a4/generation_reports.json) | 4157 |
| [a4/A_current/generate.log](a4/A_current/generate.log) | 34855 |
| [a4/A_current/output/network_generate_report.txt](a4/A_current/output/network_generate_report.txt) | 203888 |
| [a4/A_current/output/network_c_info.json](a4/A_current/output/network_c_info.json) | 3871764 |
| [a4/B_npuram6_320k/generate.log](a4/B_npuram6_320k/generate.log) | 35076 |
| [a4/B_npuram6_320k/output/network_generate_report.txt](a4/B_npuram6_320k/output/network_generate_report.txt) | 203928 |
| [a4/B_npuram6_320k/output/network_c_info.json](a4/B_npuram6_320k/output/network_c_info.json) | 3871823 |
| [a5/stability_first_uart.log](a5/stability_first_uart.log) | 2030569 |
| [a5/stability_retest_uart.log](a5/stability_retest_uart.log) | 1562243 |
