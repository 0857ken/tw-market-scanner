> 正式站已於Stage 4B-2上線，舊文以下為歷史紀錄。每日更新目前仍未啟用；最新架構與限制以 [Stage 4C-1維運說明](STAGE4C1_OPERATIONS.md) 為準。

# 開發、維運與發布

## 本機與分支

分支 `feature/scanner-v3-real-data`，main 保留原始 handoff。尚無 remote、公開 repo、PR、正式 Pages URL。壓縮包有兩分支的 Git bundle，可還原：

```bash
git clone scanner-development.bundle scanner-repo
cd scanner-repo
git switch feature/scanner-v3-real-data
npm run setup
npm test
npm run build
npm run preview
```

也可直接進入壓縮包的 source 目錄執行 npm 命令。preview 目錄為已建置靜態檔案，須用 HTTP 開啟，不能以 file:// 驗收。Python 需要 zoneinfo 的台灣／美國時區資料。

## 資料與錯誤

`python3 -m pipeline.run` 取得官方來源，解析成功才存快照，各模組獨立記錄 asOf、fetchedAt、lastAttemptAt、結果、SHA256、筆數。缺值 null；T86 pending 時不發 HTTP、不讀舊明細。

- HTTP／解析失敗：保留前次成功觀察及日期，source error。
- HTTP 成功但日期落後：保留真值，source stale，不能改今天。
- 無歷史：error／unavailable，不切 DEMO。
- 未知年度日曆：unknown，不猜假日。
- 整體合約／信用匯入失敗：保留前次驗證的行情值與日期，發布明確 error 品質狀態，程式非 0；不讓新壞資料蓋掉舊觀察。

strict 在無真實行情或價量／公司不新鮮時非 0，本次落後為結束碼 2。一般模式保留部分可用的有日期資料。台灣收盤後 16:30 起期待當日；之前期待前交易日；週末／官方假期跳過。前端按現在台灣時間重新判斷落後。

日快照持續累積，整合最多讀最近 300 個模組快照；缺應有交易日插入 null，不壓縮或延用前價。MA20／60／120 需 N 日有效收盤；N 日突破需 N+1 日。股與法人畫面除 1,000 成張；TX 是口。未還原價格不得做含息回測或宣稱原站績效。

## 遠端啟用（尚未執行）

先取得使用者對公開建立 `0857ken/tw-market-scanner` 的同意，確認無 Secret、憑證、聯絡個資及未授權明細，才新建 repo、推送 main baseline 與 feature、開 PR。不可操作 txf-tracker。本次 PR 文字是草稿，不能當作已開。

CI 僅精確 repo 名稱＋公開 repo，執行測試、build、子路徑 E2E。遠端 runner 尚未驗證，成功後再合併。

公開建庫及開發 PR 完成審核後，在此 repo 設非機密 variable `DATA_UPDATES_APPROVED=true`。從 main 執行更新 workflow，驗收 market-data 分支與 quality.json。流程先載入 market-data 舊歷史並合併 main 程式，再取新資料，避免每日重置。只提交 data/；來源 stale／error 仍可保存品質狀態，之後 job 明確失敗，不部署。資料分支保護若阻擋推送，只調整本新 repo，不拿另一專案 Token 繞過。

## 正式網站（另需同意）

公開建庫同意、來源權利、遠端 CI、資料更新與人工驗收完成後，再請使用者核准網站上線。核准後選 Pages Source=GitHub Actions、設定 `PAGES_RELEASE_APPROVED=true`，從 main 人工 dispatch。

發布 overlay market-data 後，用現在台灣交易日重新檢查價量／公司新鮮度與實際使用模組的公開來源政策，才測試及 build。舊 quality.json 的成功值不能單獨通行。未接入／暖機可明示保留；帶未核實授權明細則阻擋。

正式 `VITE_MARKET_URL` 指向獨立 market-data 的 raw JSON，每日品質更新不用重發布；讀取 cache:no-store。子路徑已本機驗證，但 GitHub CORS／CDN、權限、排程、URL 尚未實驗。發布成功後才提供實際可開啟網址，不把預定網址當上線。

## 0 元與回復

只允許公開 repo 的標準 ubuntu-latest，無付費 runner／API、信用卡、券商或交易。移除 DATA_UPDATES_APPROVED 停排程；移除 PAGES_RELEASE_APPROVED 停下次發布，不會自動刪除已有網站。已發布站點要下線需另操作 Pages。

回復用已驗證 commit／PR。資料可由 market-data 來源快照重建，保留原日期與 error；不可補隨機值、填 0、改行情日期或抄回測數字。
