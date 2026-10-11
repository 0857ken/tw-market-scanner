# PR 草稿（尚未建立）

Title: feat: 台股掃描器 3.0 手機版、官方盤後資料與品質管線

原前端與管線格式不相容，缺資料時容易以 DEMO 或不完整欄位掩蓋。此分支建立 schemaVersion 2、獨立 Python／JS 驗證、官方 TWSE／TAIFEX 盤後串接，手機首頁明示日期、缺值、暖機、落後與失敗。首次載入 2026-10-07 的 1,086 檔普通股，非即時。

改善 320–430px 導覽、44px 操作區、表格捲動、搜尋、排序、自選及明細。信用原始規則、T86 轉載授權未核實而停用；未還原價、1 日個股歷史及缺少來源的限制明示。無未授權 T86 明細、Secret、公司聯絡個資。

根目錄整合 CI、market-data 更新及人工 Pages 發布，發布重新查當下交易日與權利。更新／發布預設關閉，只用本公開 repo 標準免費 runner。未修改 txf-tracker，未正式部署。

Validation: 24 Python、22 Node、JSON Schema 2020-12 日期格式驗證、Vite production build、10 Chromium E2E（詳見 docs/ACCEPTANCE.md）。npm audit 無已知漏洞；實體 iPhone／Safari、GitHub runner／Pages 及長期排程待驗。
