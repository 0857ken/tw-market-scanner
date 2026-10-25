# Issue #5：手機熱力圖與首頁資訊層級驗收

基準：PR #3 `feature/ui-mobile-safari-polish-20261020`，固定 HEAD `f0ea87bdba72569cd2e0ba8f0ebf05e2d6cdb5c3`，tree `944099a9493554207e5d48ab5df00a1aee980fd7`。開始前已唯讀核對遠端一致。

候選：`feature/ui-heatmap-overview-p1-20261025`，Draft PR base 必須是上述 PR #3 分支。最終 HEAD、tree、PR URL、CI run 與 ZIP SHA256 由同批交付的驗收包 REPORT.md 記錄，避免文件自我引用 commit／ZIP hash。

## 實作及邊界

- 台股熱力圖在寬度 ≤750px 預設市值排序前 100 檔；桌面預設全部。可選 100／300／全部。尚未自行選擇時跟隨視窗大小；明確選擇後，旋轉／resize、產業及母體切換均保留選擇。離開頁面重新進入則依目前 viewport 使用預設值。
- 市值／漲跌幅只控制排序與入選，明確標註「非面積」。漲跌幅採原本的由高至低排序。先對全部符合產業條件、有可判定漲跌的股票檢查市值；只要任一股票缺失或市值無效，整組等權，即使該股不在前 100 檔也不會改採市值。
- 保留 `size: useCap ? marketCapM : 1`、既有 Recharts Treemap 及原市值資料，不修改市值推導或研究公式。紅漲／綠跌／平盤圖例、目前顯示 N／符合條件 M、目前市場全母體分母分開標示。
- 方塊寬高均 ≥24 CSS px 才可點擊／鍵盤開啟抽屜；較小方塊只供觀察，不擴大重疊命中區。可透過原股票搜尋與原前 25 檔排行操作。抽屜關閉後焦點返回原方塊。24px 為本階段最低命中區，iPhone 真機仍需評估易用性。
- 首頁優先展示當日漲跌與同日價格覆蓋率，完整分母保留。官方行情日期、落後／日期待核對、非即時、缺價及停用警示保持展開可見。完整 commit、資料 SHA、manifest、原研究覆蓋與日曆資訊仍可由原生 details／資料健康查閱。
- 保留原配色、Safari Visual Viewport、safe-area、搜尋鍵盤、抽屜焦點循環、背景鎖定及捲動還原。沒有改 `logic.js`、`research.js`、`data.js`、`observation.js`、資料、config、workflow、lockfile 或部署設定。

## 檔案

| 檔案 | 內容 |
| --- | --- |
| frontend/src/Scanner.jsx | 熱力圖入選與顯示控制、可存取標籤、最小命中區、摘要及可展開版本資訊 |
| frontend/src/style.css | 摘要卡片、圖例、窄螢幕排列與焦點樣式 |
| frontend/e2e/heatmap-overview-cases.js | 一般與 observation-only 共用 P1 瀏覽器案例；一般版另含缺市值測試 |
| frontend/e2e/scanner.spec.js | 納入 P1 案例；既有手機熱力圖數量斷言改為前 100 |
| frontend/e2e/observation-rc.spec.js | 納入 P1 案例；既有 RC 驗證不刪除 |
| docs/UI_HEATMAP_OVERVIEW_P1_ACCEPTANCE.md | 本驗收文件 |

## 驗證方法

在 320／375／390／430／1440 × 844px 使用相同核准資料、本機字型及 Chromium 154.0.8037.57。Node 24.19.0、Python 3.12.14、Playwright 1.58.2。只用既有 `SCANNER_CHROMIUM_PATH=/usr/bin/chromium`、`SCANNER_CHROMIUM_ARGS='["--disable-dev-shm-usage"]'`，未更動專案依賴或 CI 設定。

```sh
npm test
npm run build
node scripts/audit-built.mjs
npm run test:e2e
npm run build:rc
npm run test:rc:e2e
node scripts/audit-rc.mjs
```

新增案例檢查精確股票集合、100／300／全部、市值／漲跌幅排序、產業及 TPEx 篩選、分母、resize 預設／手動選擇、抽屜點擊與鍵盤焦點返回、小方塊無操作、圖例、日期警示、完整摘要位於第一屏、完整 SHA 可用鍵盤展開、無 root/body 橫向溢位。一般版以僅存在記憶體的測試副本模擬入選範圍外缺市值，驗證整組等權且無價格股票排除；沒有寫入行情資料。RC 不繞過核准資料 SHA 驗證。

首輪新增案例因產業選單缺少精確可存取標籤而逾時（原 23 項通過），中止後續新增案例，補標籤後重新完整測試；失敗截圖與 log 一併保留，沒有 retries／skip。第二輪 29 項通過，等權測試原先誤以為所有方塊像素面積應相同，忽略 Recharts 尾列分配餘量；改以獨立全等市值 fixture 比對完整幾何，並加上全缺市值情境，未更改 Treemap 演算法。初次本地 build 遇 sandbox 子程序 EPERM，以允許的執行權限重跑後通過，不改 build 腳本。

最終本地測試及 CI 實際數量、結果以驗收包 logs／REPORT.md 為準。既有 CI `pull_request.branches: [main]` 不會對此 stacked PR 自動產生第二份 PR 事件 run；不改 workflow、不暫改 base、不重跑成功 CI 偽裝雙 CI。push 的 `feature/**` CI 仍應實跑並讀回結果；未跑的 PR 事件 CI 不稱通過。

## 畫面與資料保全

驗收包包含五種 viewport、首頁／熱力圖、修改前／後、視窗截圖／完整頁面，共 40 PNG，及 compare.html。截圖固定時間為 2026-10-25 16:00 Asia/Taipei；熱力圖視窗截圖捲至圖表可見位置，完整頁面保存控制與警示。基準與候選皆由同一 PR #3 HEAD 衍生；候選正式 commit 後重建固定 HEAD 的 RC。

行情日維持 2026-10-13；RC `market.json` SHA256 必須為 `bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9`。未修改既有 PR #2/#3/#4、main、正式 Pages、舊預覽或其他 repo。未新增服務、付費資源、PAT、Secrets、schedule、Release 或 state。

## Work 下一階段

本次不部署候選，也不正式發布、不合併。Work 應核對最終 HEAD／tree、CI、ZIP 內容 SHA，再建立獨立 HTTPS 候選預覽；保留原 PR #3 預覽。驗收項目包括 iPhone Safari 直橫向、手動 300／全部後旋轉、產業與母體切換、實體鍵盤／VoiceOver、真實軟體鍵盤、地址列收合、safe-area、方塊點擊及焦點返回。既有 PR #3 Safari 驗收不代表本次新 UI 已經真機驗收；本次沒有 iPhone 真機，不宣稱 Safari 已通過。
