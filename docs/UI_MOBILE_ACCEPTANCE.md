# 手機相容性與互動改善驗收

本次僅調整既有前端互動，沿用原配色、頁面架構與研究功能。基準為 main `d1a700ffa2c5af42ca1a10ea90877bd3cce7e67a`；獨立分支為 `feature/ui-mobile-safari-polish-20261020`。PR #2 與 `feature/stage4c1-daily-update` 不在本次修改範圍。

## 修改範圍

| 檔案 | 行為 |
| --- | --- |
| `frontend/src/Scanner.jsx` | 搜尋收起鍵盤、保留結果、Enter 選取及方向鍵操作；Visual Viewport 配合；抽屜焦點循環、背景 inert、固定背景並還原捲動；避免抽屜拖曳誤關閉 |
| `frontend/src/style.css` | 搜尋及重要圖示按鈕至少 44×44 CSS px；手機輸入 16px；安全區、動態高度、抽屜獨立捲動與固定關閉列；長字及窄螢幕邊界 |
| `frontend/index.html` | 只在 viewport 加入 `viewport-fit=cover`，使既有與新增 safe-area inset 生效 |
| `frontend/e2e/scanner.spec.js` | 四種手機尺寸的觸控、搜尋、焦點、抽屜、捲動與模擬鍵盤縮小視窗測試 |
| `frontend/e2e/observation-rc.spec.js` | 固定 observation-only 候選的尺寸增加 375、430px |
| `docs/UI_MOBILE_ACCEPTANCE.md` | 驗收證據與 Safari 待辦 |

未修改資料、公式、policy、授權、停用策略、Actions、每日更新、Release、state 或部署。信用策略、TWSE T86、未核准歷史資料繼續停用；沒有執行資料抓取、發布或 schedule。

## 驗證方式

從修改前 main 建立本地 observation-only build，在任何前端修改前，保存 320／375／390／430×844 的首頁、搜尋及抽屜共 12 張畫面。修改後以相同資料、字型、瀏覽器和尺寸再保存 12 張。這些是本地候選預覽，並非正式站部署截圖；本地 manifest 的基準 commit 不代表修改已正式發布。

原先四種尺寸首頁的 root/body 均未溢位；不能把這點描述成此次才修復。改善前清除搜尋約 19×22px、抽屜關閉 36×44px。新增檢查涵蓋長查詢、搜尋結果、抽屜及既有所有頁面邊界；寬表格仍在原本的表格容器內橫向捲動。

本地使用 Python 3.12、Node 24、Playwright 1.58.2 與 Chromium 153.0.8010.0（正常安全設定，僅額外 `--disable-dev-shm-usage`）。因官方瀏覽器下載遭截斷，本地 Chromium 從隔離的 `@sparticuz/chromium@153.0.0` 取得，未新增專案依賴、修改 lockfile 或測試設定。既有 GitHub CI 仍使用 Node 22 與 Playwright 安裝的 Chromium。

命令：

```sh
npm test
npm run build
node scripts/audit-built.mjs
npm run test:e2e
npm run build:rc
npm run test:rc:e2e
node scripts/audit-rc.mjs
```

本地 Chromium 透過既有 `SCANNER_CHROMIUM_PATH`、`SCANNER_CHROMIUM_ARGS` 設定指定，未更改 CI。Visual Viewport 測試控制 viewport height 後發出 resize，以確認應用程式反應；不等於真實 iOS 軟體鍵盤測試。

## 結果

本地 Python 57 項、Node 78 項通過；正式 Build、built audit、observation-only Build 與 RC audit 通過，RC Chromium 8 項通過。一般 Chromium 完整重驗 23 項通過，合計 166 項，沒有 skip 或自動重試。GitHub CI 由新 Draft PR 的 Checks 與交付報告提供精確 run URL；不重跑成功紀錄。

首輪一般 Chromium 為 22 通過、1 失敗：首次 fixture 載入在同時建置的本機超過預設 5 秒。保留原失敗證據，將載入日期等待明訂為 15 秒後完整重驗，沒有增加 retries 或略過測試。

四種尺寸的清除搜尋均由 19×22px 改為 44×44px，抽屜關閉由 36×44px 改為 44×44px；root/body 寬度均等於視窗寬度。正式行情候選仍為 2026-10-13，`market.json` SHA256 必須維持 `bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9`。RC build 與稽核通過僅代表本地可驗證，不構成合併或發布授權。

## Safari 真機待辦

尚未執行 WebKit 或 iPhone Safari 真機驗收，Chromium 手機模擬不能代替。

- 在支援 `inert`、Visual Viewport 與動態 viewport 單位的 iOS Safari，記錄機型與 iOS 版本。
- 直向／橫向、瀏海與 Home indicator 安全區；地址列展開收合後導覽、關閉鈕與內容保持可用。
- 中文注音／拼音候選輸入、搜尋鍵送出、收起鍵盤、結果選取及清除，確認不誤選、不自動放大或被鍵盤遮蔽。
- 抽屜長內容手勢、邊緣回彈、關閉鈕固定位置、背景鎖定及原位置還原。
- VoiceOver 與外接鍵盤的焦點循環、Escape、關閉後返回觸發位置；文字放大與顯示縮放。
- 所有資料日期、缺漏／延遲、來源及停用提示仍可閱讀。驗收前不得宣稱 Safari 真機通過，不得合併或發布。
