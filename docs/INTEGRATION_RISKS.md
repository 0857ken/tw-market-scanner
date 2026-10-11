# 審閱確認的整合缺口 / 高優先事項

## 1. JSON Schema 不相容 — 必須實作 adapter 或統一資料契約

前端 `frontend/src/data.js` 的 `validateMarket()` 需要 `schemaVersion:1`, `mode:live`, `asOf`, `stocks[].symbol`, `stocks[].history[{date,close,volumeShares}]`, `stocks[].institutional[{date,foreignShares,trustShares,dealerShares}]`, `indexHistory`, `creditHistory` 等。

後端 `data-pipeline/scripts/build_dataset.py` 輸出則為 `meta.updated`, `stocks[].sym`, `stocks[].close`, `stocks[].ma20`, `stocks[].inst.{f,t,d}`, `stocks[].margin.{bal,use}`, `taiex`, `breadth`, `instDaily`, `futures`。**沒有 `stocks[].history`，也沒有前端所要求的 `schemaVersion/mode/asOf`。**

不能粗暴把 `mode` 改 live 就冒充已驗證。請重建正確可稽核時間序列、撰寫 schema adapter + fixture + E2E 測試，優先確認兩者對於股數與張數是否重複轉換。

## 2. 資料管線的輸出位置 / 靜態站建置位置

- 後端寫入 `docs/data/market.json`, `docs/data/credit_spread.json`, `docs/data/futures.json`, `docs/data/taiex.json`。
- 前端預期讀取同站 `/market.json` 或 `VITE_MARKET_URL`。
- 必須定義來源快照、轉換、前端 `public/` 或 deploy artifact 間的流水線，保證 JSON 不是過期的、不是跨日期混用，解決 GitHub Pages repository 子路徑和快取問題。

## 3. CI 自動化必須整合而不是單純複製目錄

- 前端 `frontend/.github/workflows/deploy.yml` 在 `main` push 後 build + deploy。
- 後端 `data-pipeline/.github/workflows/update-data.yml` 週一到週五 16:30 / 22:30 台北時間執行，提交資料變更並 `git push`。
- GitHub Actions 必須確認工作目錄 / workflow root / lockfile / Pages 授權、併發更新、失敗時不發布舊資料等。
- `continue-on-error: true` 可以掩蓋抓取失敗；要讓資料品質檢查決定部分可用或中止，不得輸出看似新的混合快照。

## 4. 免費、授權與資料品質

- 官方 TWSE/T86/TAIFEX 來源需再次驗證實際欄位、歷史範圍、授權及速率限制。
- HYG/SHY/SPY 使用 yfinance：**不可假設穩定、授權可轉載或長期免費**；需確認還原權息價和跨時區日期配對，標示可用性與限制。
- 假日、國定假期、停牌、改名、ETF/股票母體、價格調整及歷史樣本不足，要分別處理。選股母體無法覆蓋 TPEx 時不可顯示為「上市櫃全市場」。
- 外資期貨 OI 口徑、幾張、日/夜盤範圍與商品代碼必須核實。
- 盤中量與分點資料若不在來源內，應維持「未接入」，不是推測填值。

## 5. 信用燈號有原始策略矛盾，需請使用者確認原始意圖

原始畫面示意 `0.2540` 顯示 RED，而前端 v2 文件明確為 `<0.25 GREEN / 0.25~<0.35 YELLOW / >=0.35 RED`。不得把原圖的輸出視為已經驗證的策略規則；先列出差異並確認，之後加上單元測試鎖定閾值。

## 6. 研究警示不可過度暗示交易確定性

均線廣度 >70% 或 <30% 是研究門檻，不是普遍必然的反轉；融資使用率高也不能等同必然斷頭。市場體制和期貨 OI 為觀察值，應提供可追溯公式、樣本數與風險描述。回測必須防前視偏誤，處理延遲、交易成本、除息與存活者偏差。

## 7. 尚未完成的驗證

前端已有測試檔與先前靜態檢查記錄，但交接包的本機 npm build/真實瀏覽器視覺驗收 **尚未宣稱通過**；後端的 API 功能聲明來自 Claude 的文字與程式，Work 應重新驗證，不要把前人說法當作測試證據。
