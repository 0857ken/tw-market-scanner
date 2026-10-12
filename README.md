# 台股掃描器 3.0

獨立 React／Vite 前端與 Python 盤後資料管線，預定儲存庫為 `0857ken/tw-market-scanner`。不讀取或修改 `txf-tracker`。本交付是本機開發分支；尚未建立公開儲存庫、推送 PR 或發布網站。

目前載入 **2026-10-07 的 1,086 檔 TWSE 上市普通股**，使用官方公司名單篩選，排除 ETF、權證與上櫃。加權指數、TX 法人淨未平倉與融資各有獨立資料日。2026-10-08 盤後再次取得的官方來源仍停留在前一日，畫面及品質報告因此標示資料落後。

## 執行

需要 Python 3.12+、Node.js 22+ 與 npm。核心資料管線只使用 Python 標準函式庫，不需要 API Key 或付費服務。

```bash
npm run setup
npm test
npm run build
npm run preview
```

開啟 `http://127.0.0.1:4173/tw-market-scanner/`。這是本機預覽，並非公開網址。開發模式使用 `npm run dev`，依終端顯示的 localhost 網址開啟。

```bash
npm run data           # 取得官方盤後資料，允許有日期的過期快照
npm run data:strict    # 關鍵來源落後或失敗時結束碼非 0
npm run build         # 驗證資料後同步前端，不會自動發布
```

瀏覽器測試：先 `npm exec --prefix frontend -- playwright install chromium`，再 `npm run test:e2e`。Linux 可能需要 Playwright 系統相依套件。測試使用實際擷取的官方 fixture，不會每次向金融網站發請求。

## 資料與限制

- `schemaVersion: 2`；缺值使用 `null`，不補 0。`mode: live` 表示實際來源快照，**不表示即時行情或最新交易日**。
- 個股目前只有 1 個價量交易日、指數有 5 日。MA20／60／120、均線廣度、N 日突破、20 日市場體制維持暖機；沒有捏造歷史。
- 股價尚未還原除權息與分割，只供未還原價格研究；沒有驗證過的回測績效。母體是目前公司名單，非歷史時點母體。
- T86 解析與股／張單位測試已完成，但公開轉載授權未核實，預設不抓取、不載入、不公開明細。法人排名及連續買賣超維持未接入。
- HYG／SHY／SPY 預設停用；信用燈號依原始截圖還原，規則仍待確認，不採用 v2 的 0.25／0.35 作為原始規則。請將 [回覆清單](docs/QUESTIONS_TO_RETURN.md) 交給原作者。
- 美股熱力圖、盤中量、券商分點、盤前國際市場尚未接入。持股水位是本機個人記錄，自選股存在同瀏覽器，不是群眾投票或券商持倉。
- DEMO 必須在接入資料視窗中明確選擇；載入失敗預設未接入，刷新失敗保留先前觀察日期與錯誤提示。

## 結構

| 路徑 | 用途 |
|---|---|
| `frontend/` | 手機 UI、獨立 JS adapter、研究公式、單元與瀏覽器測試 |
| `pipeline/` | 官方 HTTP、單位與日期解析、歷史快照、品質與發布檢查 |
| `data/market.json` | 真實來源的整合快照 |
| `data/raw/` | 必要欄位的逐日標準化快照與原始 HTTP 回應 SHA256；無公司負責人聯絡資料 |
| `data/quality.json`、`data/runs/` | 品質與歷次來源／錯誤狀態 |
| `config/` | 待確認信用規則、逐來源授權政策 |
| `schemas/market-v2.schema.json` | JSON Schema 2020-12；跨欄位及日期順序另由 Python／JS 驗證 |
| `.github/workflows/` | CI、資料更新、人工核准後的 Pages 發布 |

閱讀 [模組狀態](docs/MODULE_STATUS.md)、[來源與費用](docs/SOURCES_AND_COSTS.md)、[維運與部署](docs/OPERATIONS.md)、[驗收紀錄](docs/ACCEPTANCE.md)、[PR 草稿](docs/PR_DESCRIPTION.md)。

`START_HERE.md`、`WORK_TASK.md`、`docs/INTEGRATION_RISKS.md` 是原始交接指令。原 `data-pipeline/` 與巢狀 workflows 已在此分支整合移除；原始版本仍保存在 Git baseline。以本 README 與驗收紀錄判斷現在狀態。

**額外月費目標 NT$0；本次付費項目為零。** 自動更新與 Pages 預設關閉，僅允許指定公開 repo 的標準 Ubuntu runner；公開建庫及正式網站發布各需使用者明確核准。

## Stage 3B（2026-10-12）

上市／上櫃／合併普通股母體與雙價格欄位已整合，預設經驗證還原價；目前還原價為空、歷史仍不足。未還原突破會受完整事件／交易日驗證門檻保護。詳見 [Stage 3B 稽核、授權、覆蓋率與限制](docs/STAGE3B_AUDIT.md)。此階段未合併或部署，未啟用排程。
