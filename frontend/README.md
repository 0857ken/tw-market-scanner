# 市場雷達 · 台股掃描器 v2

由原始 React 單檔展示稿改造成手機優先、資料來源明確的 Vite + React 前端專案，附有 npm 建置設定。

**重要：預設所有行情是固定隨機種子產生的虛構測試資料**。日期刻意固定於 2026-06-30，不得作為交易依據。接入自己的正式資料後才是使用者匯入模式；不代表本網站有即時行情授權。

## 最快啟動

```sh
npm install
npm run dev
# 瀏覽器開 http://localhost:5173
npm test
npm run build
```

正式部署 GitHub Pages：將整個資料夾上傳一個**獨立儲存庫**，Settings → Pages → Source 選 GitHub Actions；內含 `.github/workflows/deploy.yml` 在推送 main 時可建置發佈。Vite `base: './'` 可在 GitHub Pages 專案路徑下正常載入相對資源。建議先確認 repo 不與 txf-tracker 混用。

## 真實資料接入：schemaVersion 1

網站啟動時會先嘗試讀取同站 `market.json`（例如將檔案放在 `public/market.json` 後重新執行 build），也可在建置時指定 `VITE_MARKET_URL=https://.../market.json`。若未設定或不存在，**只顯示明確標示的 DEMO**；若設定了 URL 而讀取失敗，會顯示錯誤。你也可以點選網站右上角「接入資料」，貼上可公開讀取、跨域允許 CORS 的 HTTPS JSON 網址，或直接上傳 `.json` 檔案。此版**不假設**你之前 Claude 製作的 `market.json` 已符合這個格式，需要先對欄位。如果你把 `tw-scanner-data.zip` 和既有 `market.json` 上傳給 ChatGPT，可以精確替你寫 adapter。

正式資料欄位（詳見 `public/market.example.json`，該檔刻意標記 `mode: example`，**不能**冒充正式行情匯入）:

```json
{
  "schemaVersion": 1,
  "mode": "live",
  "asOf": "2026-10-08",
  "source": "TWSE / TAIFEX / 公開授權資料",
  "universe": "上市普通股 XXX 檔，排除 ETF、權證、缺值",
  "indexHistory": [{"date": "2026-10-08", "close": 0}],
  "stocks": [{
    "symbol": "2330", "name": "台積電", "sector": "半導體",
    "marketCapM": 0,
    "history": [{"date": "2026-10-08", "close": 0, "volumeShares": 0}],
    "institutional": [{"date": "2026-10-08", "foreignShares": 0, "trustShares": 0, "dealerShares": 0}],
    "margin": {"balanceShares": 0, "usagePct": 0},
    "intraday": {"asOf": "2026-10-08T11:00:00+08:00", "cumulativeVolumeShares": 0}
  }],
  "futures": [{"date": "2026-10-08", "foreign": 0, "trust": 0, "dealer": 0}],
  "creditHistory": [{"date": "2026-10-08", "hyg": 80, "shy": 82, "spy": 600}]
}
```

**注意：範例中的 0、80、82、600 都是欄位示意，不是真實行情。** 最好提供完整 240 日以上交易歷史；計算 MA20 / MA60 / MA120，N 日高點突破需要至少 N+1 個有效交易日，信用壓力燈號需要 **189 日以上** HYG、SHY 的**還原權息價**。API 若回傳美國市場未還原價，必須在後端先正確調整。

所有股票成交量、法人買賣超與融資餘額一律使用 **股數**（`volumeShares`, `foreignShares` 等），畫面用股數/1000 顯示為張。`marketCapM` 使用**百萬元**作為熱力圖市值權重（可略）。`futures` 每欄單位**口**，僅放口徑相同、商品相同（例如台股期 TX）的淨未平倉。資料缺漏可以省略該選用欄位，UI 會標「—」或「尚未接入」。不可填 0 冒充缺值。

可額外擴充：`usStocks`（陣列，屬性 `symbol,name,sector,marketCapM,change`）、`overnight`（陣列，`name,change`）、`branches`（合法取得的券商分點資料）。美股與分點尚未接線則顯示空白，不會偷偷生成虛構即時報價。

### 不同 API 的對應 / 風險

| 功能 | 建議資料源 | 注意事項 |
|---|---|---|
| 上市股票日收盤量價 | TWSE STOCK_DAY_ALL，歷史逐日保存 | API 是當日快照；上櫃須補 TPEx。除權息、分割的均線價格需一致處理 |
| 三大法人個股 | TWSE T86 | 官方欄位單位為**股**，不要直接當張，也不要隨意當「億元」 |
| 期貨法人 | TAIFEX 各期貨契約法人明細 OpenAPI | 篩選契約、市場別、正確未平倉口徑，不要混入選擇權或不同商品 |
| 融資 | TWSE / TPEx 官方融資統計 | 餘額 ≠ 使用率；須另有融資限額或可用使用率資料 |
| HYG / SHY / SPY | 有合法使用權的還原權息資料 | 本應用不包含任何美股報價抓取金鑰或免費資料授權保證 |
| 分點 | 有授權的券商分點資料 | **T86 不等於券商分點** |
| 盤中爆量 | 有 timestamp 的盤中成交量資料 | STOCK_DAY_ALL 不能提供可靠的盤中即時累積量 |
| 市場廣度 | 全部有效母體的每日價格快照 | 各均線分母排除歷史不足、停牌當日無價股票 |

本範例只包含前端讀取適配；**沒有宣稱完成正式資料自動排程管線**。GitHub Actions 部署 workflow 只做前端靜態站發佈，不抓市場行情。完整管線仍須以 Claude 提供的資料 zip 實際整合、測試端點及行程時區。

## 這次修正的重點

- 把信用燈號規則收斂成單一 `creditLight()`：`<0.25` 綠、`0.25~<0.35` 黃、`>=0.35` 紅。參數集中在 `src/logic.js`；原截圖 0.2540 顯示 RED 與原程式閾值不一致，這版依程式閾值統一為 YELLOW。
- 每個模組用同一份計算後資料；儀表板與明細不再各算一套定義。
- 法人買賣超以 **股數除以 1,000** 呈現張數，移除錯誤的「約當億元」。
- 年化波動率用去均值的樣本標準差，避免把漂移誤算進波動。
- 產業週報用過去 5 日報酬，而非把當日漲跌當作整週。
- 信用利差歷史回放使燈號、數值、圖表同步。
- 移除預設虛構群眾投票（改成本機自行記錄）。券商分點、美股市場、盤前固定國際市場數字等缺來源時標為未接入。
- 手機優先：固定底部捷徑、可收合側欄、卡片排序、個股研究抽屜、個股搜尋、關注名單（僅本機），表格不再撐破螢幕。
- 明確區分 DEMO、使用者匯入、資料日期、資料來源，沒有假裝即時行情或交易功能。

## 下一階段的優先項

1. 上傳 Claude 做的 `tw-scanner-data.zip` + `market.json` 範例，將資料管線真實輸出轉成 schemaVersion 1。
2. 驗證上市/上櫃/ETF 成分、價格還原口徑、假日與漏日、法人欄位和 T86 變更，建立每日資料品質報告。
3. 歷史重建 MA20/MA120（或從今天開始累積），處理成分股存活者偏差與除權息。
4. 若考慮回測，另開獨立模組，加入合理成交價、訊號時間、交易成本、股息、滑價與樣本外驗證，不能把圖表當績效。

## 安全

不讀券商帳戶、庫存、憑證，也**不自動下單**。個人關注名單存在 localStorage；上傳的 JSON 只在網頁內存處理。不要把 API token、pfx、券商登入憑證放在網頁或公開 repository。

**本次交付驗證限制**：源碼已通過 JavaScript/JSX 語法解析、9 項邏輯單元測試與 17 個頁面／組件的模擬掛載檢查。但此次執行環境無法解析 npm registry DNS，因此未能下載 Vite / React / Recharts 依賴，也未能在真實瀏覽器完成 `npm run build`／畫面實測。第一次於你的電腦或 GitHub Actions 建置時應檢查 build log，修正相容性問題後才部署正式站。
