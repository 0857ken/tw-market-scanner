# Stage 4A — observation-only Release Candidate

本階段只建候選版、測試及更新 Draft PR #1。沒有 main 合併、Pages 發布、schedule、詢問信寄送、行情下載或付費服務；信用策略和 TWSE T86 不變。

## 發布架構與安全門檻

採固定前端與核准 `market.json` 同包；不使用 `market-data` 分支、跨站資料網址或執行時資料匯入。`npm run build:rc` 先檢查 `config/observation-release.json` 的原始檔 SHA256、正式資料契約、各模組開放授權與凍結限制，再產生最小觀察投影。排除信用、指數、期貨、融資、盤中與券商資料；不改動原始歷史檔。

`pipeline/release_check.py` 完全保留。`pipeline/observation_release.py` 只判定有日期和授權證據的觀察候選資料，不宣稱策略、還原價或日曆完整。策略檢查仍拒絕目前資料。前端 profile 強制停用所有長期訊號，即使未來提供較長歷史，也不會自行解鎖。

前端驗證資料位元組 SHA256（Web Crypto，需 HTTPS 或 localhost）。不符、缺檔、HTTP 失敗均不能覆蓋已載入核准版本；首次失敗保持缺資料。JSON 以 no-store 讀取，沒有 Service Worker、DEMO／匯入入口或外部資料 fallback。CSP connect-src 僅 self；Vite 使用相對路徑、資源內容 hash 與 `.nojekyll`。Meta CSP 不等於 Pages 回應標頭驗證。

RC 不直接複製 public 資料夾，避免納入 `market.example.json` 或其他未核准檔；只加入已驗證投影和 `.nojekyll`，另以資源白名單檢查候選包。手機驗收截圖會等待選單關閉動畫完成。

## 固定資料版本

| 項目 | 候選值 |
|---|---|
| Profile／版本 | observation-only／4a-rc1 |
| 原始核准 input SHA256 | `1c8a9bea32923dc8b03d88958b6297820ba91f8cda729f16aa2b76f2b1e6790f` |
| 同包公開 projection SHA256 | `8a6973bc9d25ea4bce964f35191c40490873ce57df19c20248b77cda4b0145e1` |
| TWSE／TPEx 行情日 | 2026-10-12／2026-10-12 |
| 原始資料產檔時間 | 2026-10-13T12:49:13+08:00；不是行情日 |
| 上市／上櫃普通股 | 1085／893 檔 |
| 同日有效價上市／上櫃／合併 | 1080／868／1948 檔（99.54%／97.20%／98.48%） |
| 未涵蓋 | 5／25 檔，缺價或原因未確認，不推定停牌 |
| 可判定當日漲跌 | 1947 檔；1 檔有價格但無可判定官方漲跌 |
| 價格基礎 | 未還原成交價，經驗證還原價 0 檔 |
| 歷史 | 上市 3 個、上櫃 2 個觀測日，非連續交易日驗證 |
| 最新完整交易日 | 未獨立驗證；不可宣稱最新行情 |

候選版可以明示舊快照和動態日曆日延遲；它不是即時／每日更新站。Stage 4B 必須另外核准確切行情日期與 projection SHA，或先授權人工更新並重新產生、驗收 RC；禁止默認沿用陳舊快照。前端、行情、資料來源 SHA、來源日期和抓取時間列於同包 `release-manifest.json`；manifest 記錄固定 feature commit，而非可漂移 branch 名稱。最終 RC commit SHA 和 Actions run／artifact ID 交付於 PR，避免 commit 自我參照。

## 功能範圍

| 可顯示的觀察功能 | 限制 |
|---|---|
| 普通股盤後價、搜尋、關注名單 | 未還原、依來源日期；關注名單只在本機保存 |
| 上市／上櫃／合併母體 | 不具歷史成員回測資格 |
| 當日漲跌、產業排行、熱力圖 | 缺價不補零；兩市場日期不同時合併漲跌、產業漲跌與熱力圖不提供可比較值 |
| TPEx 法人研究 | 獨立來源日期、只限上櫃；不提供 TWSE／全市場合計或連買訊號 |
| 日期、來源、覆蓋率、固定 SHA | 日曆不足與延遲明示 |

因資料不足停用：MA20/60/120/240、突破、還原價格、歷史回測、盤中量能、完整日曆訊號與法人連續訊號。因規則／授權未核准停用：信用策略、TWSE T86。期貨、融資、海外資料及持股投票不在此觀察版範圍。

## 授權與顯名

沿用 Stage 3D 授權矩陣，並於本階段唯讀核對政府資料平臺：TWSE 當日資料集 [11549](https://data.gov.tw/dataset/11549)、TPEx 當日行情 [11371](https://data.gov.tw/dataset/11371)、TPEx 法人 [11856](https://data.gov.tw/dataset/11856) 與 [OGDL 第1版](https://data.gov.tw/license)。資料來源逐模組顯名及提供官方、授權連結；網站標示非官方站、普通股篩選和統計加工、非投資建議／交易指令。這些證據不能擴張為 300 日歷史批量端點、TWSE T86 或完整公司行動授權。

## 工程驗收與限制

本機：Python 53 項（含 8 項獨立門檻）、Node 78 項、普通版與 RC 正式 build。CI：原 Chromium 17 項，加 RC 5 項；最終 run 結果以 PR 的固定 SHA 證據為準。RC 測試涵蓋 320／390／1440px、真實同包資料、搜尋、關注持續保存、市場切換、TPEx 法人、热力圖個股、產業頁、停用頁、HTTP 503 保留快照與錯誤／舊資料 SHA 拒絕。既有測試涵蓋缺價、兩市場日期不同、休市、跨年、重跑和更新失敗。額外 Node profile 測試確保合併不同日的排行／熱力圖變化無效，長期訊號即使輸入存在也不展示。

RC JS gzip 上限 300 KiB；資料上限與計算效能沿用離線 build audit。實際 Pages CDN、HTTPS、快取與回應標頭須 Stage 4B 才能驗收，不能用本機結果冒充。

目前發布 workflow 只有 contents:read，沒有 pages:write、id-token:write、部署 action 或排程，即使手動執行也只能建候選包。CI 的 candidate ZIP／manifest／截圖保留 7 日／1 日，不是永久備份。首次發行尚無上一個核准「已部署版本」，不虛構可回復網站。

## Stage 4B 單次發布檢查表及回復程序（尚未授權執行）

- [ ] 使用者核准確切 RC commit SHA、資料 SHA、行情日及明示資料延遲；若不接受舊快照，先另行授權更新資料、重新驗收。
- [ ] 確認該 SHA 的 CI 成功、manifest 及 artifact ZIP SHA256；下載保留不可變 bundle 和完整 manifest，超過 7 日到期前保存核准包。
- [ ] 實機 iPhone Safari 驗收或明確核准尚未完成的限制。
- [ ] 另行取得 main 合併、修改發布 workflow、Pages 設定及單次部署授權；Stage 4A 不包含其中任何一項。
- [ ] 新發布 workflow 只接受核准 artifact ID／commit／資料 SHA／ZIP SHA，不跟随最新分支、不抓資料、不重建改動前端。解壓後逐檔驗證 manifest inventory（manifest 自身由 ZIP SHA 保護），核對 code/data/profile。
- [ ] 經人工 environment approval 後以官方 Pages artifact／deploy actions 單次發布；只有發布 job 可取得 pages:write、id-token:write。不得新增 schedule。
- [ ] 部署後檢查 repository 子路徑、JSON SHA、相對 assets、HTTPS、安全政策、快取及手機核心互動；失敗停止，保持原核准版本。
- [ ] 每次新發行前先保留目前核准舊 bundle、ZIP SHA、manifest、部署紀錄及來源版本，不能單獨退資料或只退前端。
- [ ] 有前版時：另經核准選定前一個完整 bundle，驗證所有 SHA 與明示舊行情，再人工一次性重新部署；不可因錯誤讀取自動改用舊版。
- [ ] 首次上線無前版時：如無法安全顯示資料，停止／撤下 Pages 亦須另有授權；不發布 DEMO、不暗中補行情。回復後驗收資料日／延遲、SHA 和資源，記錄原因。

## iPhone Safari 實機待測

本次 Chromium responsive 不等於 Safari／iPhone 實機。待測：HTTPS Web Crypto、JSON hash 和弱網重讀；鍵盤與搜尋遮挡；safe-area／底欄及選單；旋轉、放大字級／200% zoom；SVG 熱力圖觸控；抽屜關閉與捲動恢復；localStorage 在私密模式／限制儲存的行為；背景分頁恢復的延遲標示與過期快取拒絕。沒有在未授權狀態對外發布測試站。
