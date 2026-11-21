# Stage 4C-1 續行驗收：2026-10-20

本輪從遠端 `b64eb7dd4aca690b41059ad7d13eca256c7b09a8` 接續，沿用 `feature/stage4c1-daily-update`／Draft PR #2。未重新開發已完成的 4C-1B／4C-2B，也未把原 Stage 4C-1 需求誤當正式發布授權。

**結果：既有候選程式的回歸、離線同包驗證與回復通過；六來源低負載診斷成功。真正從正式成功 baseline 建立最新交易日候選仍被缺失的遠端 state／Release 阻擋。沒有最新交易日發布、Pages 覆蓋或每日無人值守完成的宣稱。**

## 本輪變更

- README 校正「4C-1B 尚未 push」、「4C-2 僅有設計」及舊官方候選命令。
- OPERATIONS 改為目前已上線的維運說明，移除尚未建庫、market-data overlay、直接設定 variable 或舊 CLI 的過時操作指示。
- STAGE4C1_OPERATIONS 更新現有 baseline-first 架構圖、固定 seed／完整 SHA 追溯、來源優先、停止與修訂機制、重現命令、建議 slot、失敗回報、免費額度及正式發布／回復關卡。
- 新增本報告、[機器可讀驗收](STAGE4C1_REVALIDATION_20261020.json)與[六來源診斷](STAGE4C1_SOURCE_PROBE_20261020.json)。沒有改任何產品程式、workflow、資料、前端、公式或政策。

## 需求對照與驗收範圍

| 要求 | 本輪確認 |
| --- | --- |
| 更新與 Pages 分離 | 候選 update／package 為人工 read-only；既有首次 Pages 入口保留未觸發，正式整合仍是 P0 |
| CSV／OpenAPI 差異 | TWSE 官方當日 CSV 優先，OpenAPI 僅診斷；舊 run／daily CLI 不再可用 |
| 固定前端與完整追溯 | 重用既有 seed／pin，重新驗同包所有 SHA、資料契約、來源及授權，不重新 build 正式站 |
| 冪等、修訂、品質與日期 | 既有回歸覆蓋成功新日、同日不變／修訂、來源延遲、假日／週末、跨日／跨年未知、不同步、日期倒退、覆蓋率、403／429、並發與中斷 |
| 臨時停市／完整 TPEx 日曆 | 尚未正式驗收；採保守停止，不把來源延遲推定為休市 |
| 最新官方資料 | 另准的六來源診斷各一次成功；不輸出市場快照、不形成候選、不繞過 baseline |
| 成功更新測試 | 既有測試以真實較舊 10/8 baseline 與 10/13 fixture 驗有效新交易日；不是 10/20 真實全鏈 |
| 完整 dry-run／回復 | 離線 fixture 10/13；打包、全 SHA、固定前端、CAS 舊版回復與逐 byte 一致通過 |
| 原完整策略 gate | 未修改且實測拒絕 Independent market calendars not verified；信用／T86／未核准長期功能仍禁用 |

## 本機結果

環境：Python 3.12.14、Node 24.19.0；CI 仍固定原 Python 3.12／Node 22，不改版本或 lockfile。

| 檢查 | 結果 |
| --- | --- |
| Python 全套 | 116 通過，447.768 秒，0 failure／error／skip |
| Node 全套 | 80 通過，0 failure／skip |
| 已登錄離線矩陣 | 45 ID PASS；只代表各測試實際斷言，不能關閉下列已知 P1 |
| 一般／RC／daily seed 建置 | 通過 |
| workflow／built／RC audit | 通過 |
| 完整離線打包／CAS／回復 | 通過，productionDeployed=false |
| 本機 Chromium | 官方 Playwright 下載失敗，無可信系統 Chromium；本機未執行，交由既有 CI 跑 17＋6＋7 |
| 受保護程式／政策／workflow | 17 檔與 b64eb7d…逐 byte 一致；所有 tracked 產品檔無修改 |

確切續行 commit 的遠端 CI 結果、job logs 與 artifact 以 [既有 PR #2](https://github.com/0857ken/tw-market-scanner/pull/2) 的該 head checks 及交付紀錄為準。此處記錄本機驗證，不把舊 b64eb7d…的成功 run 當作新 commit 的 CI。

### 離線打包證據

| 欄位 | 本輪本機值 |
| --- | --- |
| fixture 行情日 | 2026-10-13 |
| runId | ci-fixture-local |
| 完整 ZIP SHA256 | 72d1629a6404225865588824c4a22b21aa8effedcf25b5505317fc091a85dad7 |
| 公開資料 SHA256 | e5a8f6fc730814387e2b36db61ca9f92fce53403782b228f070b05af8ad35064 |
| manifest SHA256 | 5bd0b56064a8fbb57c6eac7469eed443c98e141a18f470dc3628368d63682ffb |
| frontend pin SHA256 | 1f24f4de9e88d4c3a6174151526e6a1eb9096a17f397f22613d884d932797dda |
| 逐檔／固定前端／回復 | allHashesVerified、fixedFrontendReused、restoreByteIdentical、atomicCASLedgerAndPreviousBundle 全為 true |
| 權限與結果 | deploymentAuthorized=false、productionDeployed=false、strategyComplete=false |

本機 dry-run 模擬兩個使用相同 fixture、不同 run metadata 的完整站包，不宣稱資料已變成 10/20；真正的新交易日轉換由另列的既有成功新日回歸驗證。CI 自己產生的 ZIP／manifest 可能因 run ID／生成時間不同而有不同 SHA，不能互換。本輪 ZIP 也不是原正式 RC ZIP。

## 官方低負載診斷

2026-10-20 16:03:51～16:04:18（Asia/Taipei），六個已核准最新端點各一次；沒有重試、fallback、歷史日期參數、T86 或信用請求。只保存日期／筆數／SHA／授權 evidence 等 metadata，未保存公司聯絡資料或完整 HTTP body。

| 模組 | 來源日期 | 解析筆數 |
| --- | --- | ---: |
| TWSE 日曆 | 2026-12-25（事件列最大日期，非交易日認證） | 27 |
| TWSE 公司名單 | 2026-10-19 | 1,090 |
| TWSE 當日 CSV | 2026-10-20 | 1,096 |
| TPEx 公司名單 | 2026-10-19 | 893 |
| TPEx 行情 | 2026-10-20 | 891 |
| TPEx 法人 | 2026-10-20 | 761 |

筆數是各來源 parser 的輸出筆數，不是合併普通股母體、有效價格覆蓋率或可發布資格。source metadata SHA、URL、授權依據及各次時間在診斷 JSON；原 data 目錄 inventory 前後相同。

當時尚未到既有同日 EOD 的 16:30 邊界，也沒有可驗正式 baseline，因此 candidateEligibility=NOT_EVALUATED、candidateCreated=false；不因 API 已回當日日期就降低時間或 baseline 門檻。

另外實際執行支援的 verified_baseline preflight：讀 state 遭 404，exit=2、acquisitionCalls=0、fallbackUsed=false、baselineVerified=false、productionUnchanged=true。沒有使用一般 checkout 來補缺口。

## Stage 4C-2 尚待關閉

1. 保留已有的 4C-2A／2B／2C 成果與既有授權，避免重新設保護；核對 orphan／受保護 append 管道與專用初始化 authority，完成原 immutable Release／真 asset IDs index／g0／成功 pointer／乾淨遠端還原。
2. 補完整歷史來源重建、整包封存欄位限制、成功核准證據、Pages artifact 與核准 bytes 綁定、B08 實際採集暫存／closure 中斷驗收。這些本輪不重開發、不以綠燈 CI 誤列通過。
3. 正式 writer 開放前，main 舊更新入口與首次 Pages 入口退役或整合單一預約／fence。當前原碼的遠端 mutators 保持關閉。
4. 精確核准修補 commit／main 合併、新每日 seed／pin、gate 政策、原定 target／slot／deadline、正式發布與回復 scope。完成真實新交易日候選，再依相應授權做一次人工正式全鏈驗收。
5. 完成 API＋兩輪全檔 live＋最後成功 CAS、失敗／UNKNOWN／網站已換但 pointer 未記的 reconcile，及使用舊完整包的正式人工回復驗收。
6. TPEx／跨年／臨時停市與 iPhone Safari、主動過期／漏 slot 回報、共享免費額度與預算驗收。最後另准每日自動更新與 schedule。

建議 18:30 主 slot、19:30／20:30 備援、21:30 截止；細節與不重試類型見維運說明。本輪沒有 schedule、merge、Pages、Release／state 寫入、正式回復、寄信、付費或其他 Repository 操作。
