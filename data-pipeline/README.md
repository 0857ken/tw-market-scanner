# 台股掃描器資料管線(免費自動更新)

每日自動抓取官方免費資料,輸出前端可直接讀取的 JSON。

## 資料來源(全部免費、官方)
| 資料 | 來源 | 端點 |
|---|---|---|
| 全市場收盤 | 證交所 OpenAPI | `exchangeReport/STOCK_DAY_ALL` |
| 三大法人買賣超 | 證交所 RWD | `fund/T86` |
| 融資融券餘額 | 證交所 RWD | `marginTrading/MI_MARGN` |
| 加權指數 | 證交所 RWD | `afterTrading/FMTQIK` |
| 期貨三大法人 | 期交所 OpenAPI + 官方下載備援 | 見 `fetch_taifex.py` |
| HYG/SHY/SPY | Yahoo Finance(還原權息價) | yfinance |

## 排程
GitHub Actions 於台北時間 16:30 與 22:30(週一至五)各跑一次,
假日 API 無資料時自動跳過,不會產生錯誤資料。

## 輸出
- `docs/data/market.json` — 前端主資料(個股、廣度、突破、法人、融資)
- `docs/data/credit_spread.json` — 信用利差紅綠燈完整序列
- `docs/data/futures.json` / `taiex.json` — 逐日累積
- `docs/data/raw/` — 每日原始快照(歷史累積的基礎,勿刪)

## 重要限制
證交所 OpenAPI 只提供「最新一天」,歷史靠每日快照累積:
- 跑滿 20 個交易日 → MA20 / 廣度20 可用
- 60 日 → MA60;120 日 → MA120 與 120日突破
累積未滿前對應欄位為 null,前端會顯示「資料累積中」。
