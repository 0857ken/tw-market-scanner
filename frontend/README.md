# 台股掃描器 3.0 前端

請先閱讀 [根目錄 README](../README.md)。正式資料契約為 schemaVersion 2，資料管線與前端已整合。

從根目錄執行 `npm run setup`、`npm test`、`npm run build`、`npm run preview`。直接在本目錄 build 不會同步新的 `data/market.json`，因此以根目錄命令為準。

所有 workflows 位於 repo 根目錄，推送 main 不會直接發布 Pages。預設讀取同站相對路徑 `market.json`；核准發布時可設定 `VITE_MARKET_URL` 讀取獨立 `market-data` 分支。

載入失敗顯示未接入，不自動切 DEMO。DEMO 只能手動啟用且保持虛構標示。信用規則尚未確認，不使用舊版固定門檻冒充原始截圖規則。
