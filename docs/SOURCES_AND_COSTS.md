# 來源、授權與費用審計

查核日期：2026-10-08。未開通或購買付費 API、雲服務、券商接口或新訂閱。

## 官方資料

| 模組 | 來源／日期／單位 | 公開依據與處理 |
|---|---|---|
| 公司名單 | TWSE `opendata/t187ap03_L`，2026-10-07，1,089 個四碼公司 | [TWSE OpenAPI](https://openapi.twse.com.tw/v1/swagger.json) 的 license 指向政府開放授權；僅存名稱、產業、股數、代碼、日期 |
| 日價量 | TWSE `exchangeReport/STOCK_DAY_ALL`，2026-10-07，成交量股／收盤價元 | [資料集 11549](https://data.gov.tw/dataset/11549)、TWSE OpenAPI；與公司名單交集 1,086 檔，未還原價 |
| 指數 | TWSE `MI_INDEX`／`FMTQIK`，2026-10-07，5 個真實日期 | 同 TWSE OpenAPI；精確選發行量加權股價指數 |
| 日曆 | TWSE `holidaySchedule`，2026 年 27 項、至 2026-12-25 | 同 TWSE OpenAPI；開始／最後交易日是事件，不當休市 |
| 融資 | TWSE `rwd/zh/marginTrading/MI_MARGN`，2026-10-07，1,067 行 | [資料集 11680](https://data.gov.tw/en/datasets/11680) 列同名集中市場資料、欄位、免費及 OGDL；交易單位 ×1,000 成股，分母是次一營業日限額 |
| TX OI | TAIFEX `MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate`，2026-10-07 | [資料集 11596](https://data.gov.tw/dataset/11596) 免費、OGDL、契約／日期／身份／淨未平倉；外資 -79,101、投信 76,268、自營商 -2,253 口 |

[政府資料開放授權條款第 1 版](https://data.gov.tw/license)。保留來源、日期與加工公式；不把資料完整、服務穩定或授權永續當成保證。`config/source-publication.json` 記錄逐來源依據，不能取代第三方資料權利的審核。

每個 HTTP 最多 2 次、15 秒 timeout、20 MB 上限，只允許官方 HTTPS，不使用憑證。標準化日快照僅保留必要欄位；`sha256` 是原始 HTTP 位元組摘要，不能以標準化 JSON 重算並期待相同。尚無明確服務水準／速率保證；低頻盤後請求遇到封鎖會報錯，不轉付費 API。

## 未接入／待核實

T86 實際欄位與合計已用官方回應核對，但 [TWSE 使用條款](https://www.twse.com.tw/zh/terms/use.html) 對自動取得及轉載有限制，例外是已授權政府資料平台的資料。[開放建議 137032](https://data.gov.tw/suggests/137032)、[44238](https://data.gov.tw/suggests/44238) 是建議頁，不能當 T86 已開放證明。目前預設不抓取、不讀舊明細、不公開；先前欄位審計的 T86 明細不進開發分支。須取得確切開放資料集、書面許可或合法免費替代才變更政策，不購買網路資訊商店商品。

[yfinance 官方說明](https://ranaroussi.github.io/yfinance/) 指向個人用途，不能推論公開轉載許可。預設無 yfinance 相依、抓取或 HYG／SHY／SPY 報價。`--credit-file` 要求來源、授權 URL、轉載權宣告與同日配對還原權息價；這是輸入條件，仍需審核。來源政策 pending 時，發布檢查會拒絕帶有信用明細的快照。

TPEx、S&P 500、盤中量、分點、盤前國際、歷史調整因子尚缺。零費用途徑是累積已授權官方快照，等待原作者提供有授權的歷史／公式；未用模擬填補。

## 月費 NT$0

| 項目 | 本次新增費用 | 條件 |
|---|---|---|
| 本機開發／測試 | NT$0 | 已執行，未買服務 |
| GitHub 公開 repo | NT$0 | 尚待公開建立同意 |
| GitHub Pages | NT$0 設計 | [官方文件](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages)：GitHub Free 公開 repo；不加購私人 Pages、網域或主機 |
| GitHub Actions | NT$0 設計 | [官方計費](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)：公開 repo 標準 runner 免費；workflow 拒絕 private，無 larger runner |
| 行情 API | NT$0 | 上述免費開放來源，pending 模組停用 |

更新預設關閉。核准後平日台灣 17:40／22:40，按 22 個平日為 44 次／月。每次估 2–4 分鐘，約 **88–176 runner 分鐘／月**；8 分鐘 job timeout 的保守上限 **352 分鐘／月**，不含人為重跑、CI、發布。這是估計，沒有遠端帳單或排程成功證據。

CI 每次上限 10 分鐘，網站人工 dispatch，更新只寫 market-data，避免推送觸發 CI／發布迴圈。CI 不保存大型測試 artifact，Pages artifact 留 1 日。需監看 GitHub 儲存、流量、政策限制；若要求付費即停止並回報，不自行付費。
