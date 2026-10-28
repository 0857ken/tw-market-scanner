# Issue #7 隔離整合及正式發布 Gate

2026-10-28；Production = NO-GO。僅整合實驗，不授權正式發布。

## 固定來源與完整 Git

- main：d1a700ffa2c5af42ca1a10ea90877bd3cce7e67a。
- PR #2：93199de5b76b9db8c3a12ed78c4242967636cf9a。
- PR #3：f0ea87bdba72569cd2e0ba8f0ebf05e2d6cdb5c3。
- PR #6／整合分支起點／新 PR base：3c571518f25aff6463bf58a8d8036bf4a5c03bfc。
- base 分支：feature/ui-heatmap-overview-p1-20261025。
- 整合分支：feature/pr2-pr6-integration-lab-20261026。

Work 重新完整 clone（非 shallow／partial），git fsck --full --strict 通過；真正執行 git merge --no-commit --no-ff，保留雙 parent。沒有以 GitHub 檔案 API 代替本機三方合併。若用既有連接器傳輸 Git objects，必須核對完整 tree、雙 parent、再次 fetch 與 fsck；遠端作者／時間 metadata 可造成 commit SHA 與本地不同，不得冒稱 SHA 相同。

10/26 未完成工作區被維護清除，未推送；10/28 從固定起點重做，不把中斷測試算 PASS。

## 衝突及逐段選擇

只有 frontend/src/Scanner.jsx 一個衝突檔、一個 conflict hunk（固定版本區）。

1. import 及行情 useEffect：保留 PR #2 fetchDailyMarket／VITE_DAILY_FRONTEND_ID 分流；未改 loader、錯誤保留最後已驗證快照及首次 unavailable 行為。
2. 固定版本區：保留 PR #6 展開／收合詳情、第一畫面日期與停用警示、完整 Commit／SHA；每日模式讀取驗證後 observationProfile.version、releaseIntegrity.dataSha256、runId。RC 模式保留編譯時版本及核准 SHA。
3. 未衝突的手機搜尋、visualViewport、safe-area、觸控、body scroll lock、抽屜焦點／Escape、熱力圖100／300／全部、排序篩選與首頁摘要保留 PR #3/#6。
4. data、config、研究公式、授權、observation-only 安全機制未重新設計。PR #2 的 workflows 原樣合入隔離分支，沒有另改 production workflow 或啟 schedule。

## 可重現驗證

執行 npm ci --prefix frontend --no-audit --no-fund；python3 -m scripts.audit_workflows；npm test；npm run build；node scripts/audit-built.mjs；npm run test:e2e；npm run build:rc；npm run test:rc:e2e；node scripts/audit-rc.mjs；node scripts/build-daily-seed.mjs；python3 -m scripts.daily-dry-run；在 frontend 執行 Playwright daily config。

新增 daily-release.spec.js 跨分支回歸：五種寬度320/375/390/430/1440、共用 PR #6 heatmapOverviewCases、來源日期不同時上漲／下跌／平盤全部為 —、manifest／hash 缺失、初始拒絕及刷新保留快照、手機鍵盤／焦點／抽屜、固定時鐘的過期提示與完整驗證身份。

混合日期為明示離線 transport fixture：依既有歷史資料同步來源日期、來源版本、session 及歷史範圍，重新計算測試 manifest hash，走實際 fetchDailyMarket 與 validateMarket；沒有放寬驗證器、正式資料或可信來源。10/26 不完整 fixture 曾被「最新行情版本與來源不一致」正確拒絕；修正測試建構而非產品 gate。

新交易日有效／無效／過期、successfulPointer、來源／SHA、無 baseline 零採集、CAS、UNKNOWN 與回復由保留的 Python 故障測試驗證；fixture 成功不是正式新交易日成功。固定舊行情允許帶明確日期／延遲警示顯示，不表示可發布新交易日。

CI push branches 為 main、feature/**；pull_request 僅 main。本 PR base 是 PR #6 feature，故 PR 事件 CI 不應觸發；沒有觸發不能列 PASS。最終實跑數字、固定 HEAD/tree、候選 hashes 與 Run 以交付證據為準。未執行 iPhone Safari 真機、VoiceOver 或實體鍵盤，不沿用舊 UI UAT 當作新整合驗收。

## 原包與遠端現況

取回 portable-legacy-import.zip SHA256 45a4c959ec14e653c658dd645f165aba14370adb6e89ad69f7a5227f7b3728fe。
四項資產 hash／大小符合既有原包證據，verify_closure 在目前整合程式通過，沒有重新打包原始 site.zip。

| 原資產 | SHA256 |
| --- | --- |
| site.zip | 7621524742b25dfaa7a7216ca5f5b5006719a252966a0554ff7d0416c3262eee |
| acquisition-state.zip | 4f938e7f2d757cb3c1f3de9ea3989be10c63243db12a868f50b8994571d568d0 |
| supporting-material.zip | d8465510a71126ad51b53303c291331608b14034aeee90f060d17c4655b4d994 |
| candidate-receipt.json | 7155108b8ddd5301d38d8855f371e0f76eaa15180214e2984a593025ca262d11 |

10/28 唯讀查詢與 Issue #7 舊文字有差異：Release 426237246（4b1-rc1-original）已 published、immutable:true；四項 asset IDs 為 site 684004647、acquisition 684004677、supporting 684004706、receipt 684004715；metadata digest 符合上述值，但沒有 package-index.json。scanner-release-state matching refs 為空。此 Release 非本輪建立／修改。metadata digest 不等於本輪遠端 asset bytes 下載驗收；原包 bytes 本輪由已保存副本驗證。

## 正式發布阻擋及後續 Gate

1. g0／successfulPointer／獨立可信 authority registry／SuccessRecord／safe append／乾淨遠端還原未完成。Immutable Release 缺 index 的現況須總控另審；不得刪除重建、覆寫資產或關閉 immutability 繞過。
2. 舊 pages-release.yml 綁定首次4b1-rc1及已到期 artifact11862513391，未加入每日單一 writer 預約。不得重跑此入口作 UI-only 或每日發布；需另准精確 workflow 差異，所有可達 Pages mutation 的入口共同受 writer fence/CAS 約束。
3. UI-only 單次發布也會改變正式網站 bytes，必須有精確核准 ZIP／manifest／seed、expectedCurrent、g0 或另經核准的 authority／回復機制；不能以「資料未變」繞過成功指標。此整合測試不是正式 seed 核准。
4. 每日發布須從正式 successfulPointer 取得完整可信 baseline、固定前端 seed/pin、來源日期／授權／品質／SHA gate；不得用 latest Release、checkout fixture、pending 或本輪離線包替代。發布時不得重建前端。
5. 單次 Pages create 前先持久預約、fence／CAS／operation key；成功回覆不是成功認列，還需精確 deployment／artifact／attempt、兩輪 live bytes 與最後成功 state CAS。逾時／失聯／未知狀態一律 UNKNOWN／HALTED，零盲目重送。
6. UNKNOWN 先唯讀核對既有 deployment ID、live 舊／新／混版、state HEAD；未知請求仍在途不得以新 deploy 或 rollback 覆蓋。是否 finalize 或解停須另行精確授權。
7. 回復須核准 prior ZIP／原 seed／政策／完整來源閉包、expectedCurrent；走同一 writer／CAS，新 generation，完整舊 bytes 驗收，不能只回復 market 或退回 pointer。先離線 fault-injection／clean-room，再另准正式演練。
8. 日期與交易日曆（跨年、休市、TPEx）、正式新交易日全鏈、容量／通知、整合後 Safari／VoiceOver／實體鍵盤仍需各自驗收。

成本範圍：只用既有 Work、本地離線測試及 public repository 標準免費 CI，無 larger runner、付費服務、PAT、Secrets 或權限變更；新增月費 NT$0。不是全帳戶帳單稽核。

不得合併、正式部署、初始化 Release/state、啟 schedule、修改原 PR 或其他專案。本文件不解除任何 NO-GO。
