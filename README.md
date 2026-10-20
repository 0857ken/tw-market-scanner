# 台股掃描器 3.0

> 2026-10-20 維運文件校正：沿用 Draft PR #2 與已完成的 Stage 4C-1B／4C-2B；正式站仍為 `4b1-rc1`。最新證據見 [Stage 4C-1 續行驗收](docs/STAGE4C1_REVALIDATION_20261020.md)。

Stage 4C-2B 已有 [持久版本／安全發布的離線實作](docs/STAGE4C2B_IMPLEMENTATION.md)，依 [4C-2A 規格](docs/STAGE4C2A_ARCHITECTURE_AND_CODEX_SPEC.md) 延伸。4C-2C 已設定 state 專用 ruleset，Release immutability 曾於 10/17 設定；原始 Release、scanner-release-state、g0／successfulPointer 與正式寫入能力仍未初始化／驗收。唯一支援的候選 CLI 是 `pipeline.verified_baseline`，缺 state 即停止；不得用 checkout fixture 作正式 baseline。

正式盤後觀察站：**https://0857ken.github.io/tw-market-scanner/**。Stage 4B-2 已合併 PR #1，使用核准固定版本 `4b1-rc1` 首次發布（Run `38496725153`）。正式快照的 TWSE／TPEx 行情日均為 **2026-10-13**，不是即時行情；TWSE 名單為10/12、29檔缺有效價格、交易日曆部分驗證、Safari 實機尚待驗收。正式版未啟用長期均線、突破、還原價格、回測、信用利差或 TWSE T86。

Stage 4C-1 建立每日更新候選架構與非正式 dry-run：**沒有 schedule、没有正式網站更新權限、不寫 market-data、不合併 main**。獨立 React／Vite 前端與 Python 盤後資料管線；不讀取或修改 `txf-tracker`。目前母體為1,085檔上市、893檔上櫃普通股，有效價格1,949檔（98.53%）。來源日期與抓取時間分開顯示，延遲不補假資料。

見 [Stage 4C-1 維運、架構與驗收](docs/STAGE4C1_OPERATIONS.md)。

**Stage 4C-1B 已提交並通過既有 CI：** `db5e1f41…` 的 Push／PR 各 204 項；後續 `b64eb7d…` 已有 4C-2B 離線實作，Push／PR 各 226 項。沿用 [Draft PR #2](https://github.com/0857ken/tw-market-scanner/pull/2)，未合併。[4C-1B 說明](docs/STAGE4C1B_REVIEW.md) 的「待審查／尚未 push」為提交前歷史紀錄；離線 PASS 不等於正式初始化或發布完成。

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
npm run data:candidate -- --help  # 唯一候選入口；舊 data/data:strict 是相同入口別名
npm run build         # 驗證資料後同步前端，不會自動發布
```

瀏覽器測試：先 `npm exec --prefix frontend -- playwright install chromium`，再 `npm run test:e2e`。Linux 可能需要 Playwright 系統相依套件。測試使用實際擷取的官方 fixture，不會每次向金融網站發請求。

## 資料與限制

- `schemaVersion: 2`；缺值使用 `null`，不補 0。`mode: live` 表示實際來源快照，**不表示即時行情或最新交易日**。
- 上市僅觀測到 4 日、上櫃 3 日行情；MA20／60／120／240、均線廣度及 N 日突破維持缺資料／暖機。300 日回補尚未完成，沒有捏造歷史。
- 股價尚未還原除權息與分割，只供未還原價格研究；沒有驗證過的回測績效。母體是目前公司名單，非歷史時點母體。
- TWSE T86 公開轉載授權未核實，不抓取、不載入、不公開明細。TPEx 開放授權法人快照可獨立研究，但不能冒充完整上市櫃法人資料，連續訊號仍須足夠歷史。
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

**額外月費目標 NT$0；本次付費項目為零。** 正式 Pages 已上線；每日自動更新仍關閉，僅允許指定公開 repo 的標準 Ubuntu runner；公開建庫及正式網站發布各需使用者明確核准。

## Stage 3B（2026-10-12）

上市／上櫃／合併普通股母體與雙價格欄位已整合，預設經驗證還原價；目前還原價為空、歷史仍不足。未還原突破會受完整事件／交易日驗證門檻保護。詳見 [Stage 3B 稽核、授權、覆蓋率與限制](docs/STAGE3B_AUDIT.md)。此階段未合併或部署，未啟用排程。

## 歷史 Stage 3C：單次人工更新驗收

新增當日行情、漲跌家數、產業有效樣本與熱力圖；沒有完整均線窗口時不產生突破訊號。同日快照不重寫，來源修訂／錯誤先保留最後有效資料。

歷史曾使用 `pipeline.daily --twse-current-csv`；目前 run／daily 的直接 CLI 已停用，`pipeline.daily_release --fetch-current` 也不再是官方候選入口。**只使用 `pipeline.verified_baseline`／`npm run data:candidate`**，先驗精確 successfulPointer、封存閉包與當下 live；缺 state 在金融請求前停止。必要參數與離線演練見 [維運說明](docs/STAGE4C1_OPERATIONS.md)。

[品質報表](data/quality.json) · [更新及CSV來源證據](data/stage3c-update-manifest.json) · [離線重播證據](data/stage3c-replay-evidence.json) · [TWSE詢問信草稿](docs/TWSE_LICENSE_INQUIRY_DRAFT.md) · [TPEx詢問信草稿](docs/TPEX_LICENSE_INQUIRY_DRAFT.md)。兩封信未寄出，歷史批量及價格還原尚未核准。

## 歷史 Stage 3D：盤後觀察版上線準備

[驗收報告](docs/STAGE3D_AUDIT.md) · [正式上線檢查表與Stage 4流程](docs/OBSERVATION_RELEASE_CHECKLIST.md) · [授權矩陣／官方聯絡窗口](docs/DATA_LICENSE_MATRIX.md)。本階段未發布網站、未合併或寄信。

首頁詳細來源／研究限制可展開；資料重新讀取省略憑證、15秒逾時，僅允許本站／GitHub原始資料URL或匯入JSON。打包保留CSP與相對Pages路徑，CI提供一天的手機截圖 artifact。正式 CDN／HTTPS 已有 Stage 4B-2 與後續原版逐檔核對證據；iPhone Safari 實機及完整日曆仍待驗收。每日候選前端需要自己的固定 seed 核准，不能直接替換原站 JSON。
