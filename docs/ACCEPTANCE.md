# 開發驗收紀錄

驗收日期：2026-10-08（Asia/Taipei），本機分支 `feature/scanner-v3-real-data`。交接 baseline `a112f01` 保留原始程式；最終 commit 由交付包 manifest 記錄。

## 實際通過

| 檢查 | 結果與範圍 |
|---|---|
| Python | 24 項 unittest；ROC／ISO 日期、缺值／NaN、股張、T86 合計、融資限額、TX 三身份、日曆、失敗保留、來源權利、整體整合失敗保留及發布檢查 |
| Node | 22 項；獨立 v2 adapter、真實 fixture、MA／突破暖機、缺日廣度、法人連續性、精確信用排名、DEMO 拒收、16:30 新鮮度 |
| JSON Schema | 使用 jsonschema 4.26.0，Draft 2020-12＋FormatChecker；canonical 與 fixture 均通過；跨欄位限制另由 Python／JS 執行 |
| Build | Vite 6.4.4 production 成功；React 約 142 KB、charts 約 439 KB、app 約 83 KB，單 chunk 低於 500 KB；gzip JS 約 194 KB、CSS 約 6.4 KB |
| Chromium E2E | 10 項；320／375／390／430／1440px，18 個子模組＋首頁，無 root/body 水平溢出或 pageerror |
| 互動與故障 | 搜尋 2330、明細／Escape、自選持久化、表格排序與捲動、503 未接入、刷新失敗留原日期、DEMO 明確選擇／錯格式拒收 |
| 套件 | npm audit 已知漏洞 0；lockfile v3，前端版本 3.0.0 |
| Workflows | 3 個根目錄 YAML 解析成功；精確新 repo、公開限定、標準 ubuntu-latest、更新及發布預設 OFF；未做 GitHub 遠端實跑 |
| 正式子路徑 | production 靜態檔案在 `/tw-market-scanner/` 的本機 HTTP 測試，不是 Vite dev 或公開 Pages |
| 手機截圖 | 繁體中文首頁／信用／資料健康已擷取並人工目視；QA 字型只安裝在測試工具，不增加產品外部字型服務 |

執行環境：Python 3.12.14；Node v24.19.0；npm 11.9.0；Linux headless Chromium 153.0.8010.0，Playwright 1.58.2。網路環境的 Playwright 標準瀏覽器下載未成功，因此本機改用獨立 QA Chromium，並以 `SCANNER_CHROMIUM_PATH` 提供執行路徑；沒有把瀏覽器二進位加進產品套件。遠端 CI 使用標準 Playwright 安裝，仍待 GitHub runner 驗證。

## 真實資料與預期阻擋

最後成功取得價量時間：**2026-10-08T21:52:33+08:00**。來源回傳日仍是 **2026-10-07**，不是產檔日。TWSE 公司 1,089／價量 1,094 行，兩者交集普通股 **1086** 檔；不是上市櫃全市場。指數 5 日，股票只 1 日，均線／突破／體制暖機。

`python3 -m pipeline.run --strict` 實際回傳 **2**：官方來源日期落後，`freshCritical=false`，不是抓取成功就假裝今天。`python3 -m pipeline.release_check` 在期待 2026-10-08 時明確拒絕 2026-10-07 快照；此拒絕是驗收要有的行為，不是網站部署失敗。

TX 最新外資 -79,101／投信 76,268／自營商 -2,253 口；各月合計淨未平倉，非成交口數。融資使用率為今日餘額／次一營業日限額。缺值沒有補 0。

T86 只完成欄位審計／解析測試，公開轉載權未確認，已預設停用，真實明細不入分支。信用價格停用、原燈號 pending，沒有把 .25／.35 凍結成原作者規則。所有回覆需求在 `QUESTIONS_TO_RETURN.md`。

## 尚未驗證與發布狀態

- 沒有實體 iPhone／Safari／WebKit 驗收；已做的是 Chromium 手機尺寸，不宣稱全裝置相容。
- 沒有 GitHub Actions 實跑、長期 API 延遲／限流驗證、Pages CORS／CDN／正式 URL。
- 沒有足夠歷史、還原因子、原 AE／CTA／燈號狀態機或可重現回測。
- GitHub metadata 查詢回傳 404（可能未建立或連線無存取權），未推送／建 repo／開 PR／發布。已準備完整本機分支、PR 草稿與人工發布流程。
- 無付費服務、未修改 txf-tracker、未傳送對外訊息、未連券商／交易憑證。

完整功能差距與費用估算見 `MODULE_STATUS.md`／`SOURCES_AND_COSTS.md`。公開建庫及正式站發布須依交接指令各取得同意。
