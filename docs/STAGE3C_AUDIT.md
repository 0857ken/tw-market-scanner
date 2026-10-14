# Stage 3C：每日行情更新驗收與歷史資料授權調查

2026-10-12，Asia/Taipei。僅 `0857ken/tw-market-scanner` feature 分支及 Draft PR #1。單次受控更新、資料品質修補與工程驗收；沒有合併、Pages、schedule、付費、T86、信用規則變更或txf-tracker操作。

## 最近有效資料與更新結果

本次先在隔離資料副本執行六個已核准的最新官方API（公司名單兩個、行情兩個、TWSE日曆及TPEx法人），開始時間23:12:38。TWSE OpenAPI回傳10/8、TPEx行情10/12，系統保留真實日期，未以重新產檔冒充行情更新。

進一步核對政府資料集11549**直接連結**的當日CSV：`https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data`，23:20:46取得10/12行情。此為無日期參數的最新開放資料，不是手動歷史CSV頁面的抓取。以本次已下載位元組重新驗證、整合；沒有再發出行情請求。新增 `--twse-current-csv` 明確選項，後續經授權的人工更新可選用此介面。預設OpenAPI若退回較舊日期，會拒絕降版而保留最後資料；不悄悄覆蓋10/12。

本次資料取得為6次成功API回應加1次成功CSV檢查；另有一次網頁查核工具嘗試預覽該CSV，因不支援text/csv未能解析。沒有歷史日期迴圈、300日批量下載或付費服務。完整URL、SHA256、首次快照時間與最近嘗試時間在 `data/stage3c-update-manifest.json`；原始六API结果及CSV交叉核對亦分開保留。

| 行情日均為10/12 | TWSE上市 | TPEx上櫃 | 合併 |
| --- | ---: | ---: | ---: |
| 普通股母體 | 1,085 | 893 | 1,978 |
| 有效未還原收盤價 | 1,080 | 868 | 1,948 |
| 原價覆蓋率 | 99.54% | 97.20% | 98.48% |
| 行情列缺漏 | 2 | 6 | 8 |
| 有列但缺價、原因未確認 | 3 | 19 | 22 |
| 未能判定原因合計 | 5 | 25 | 30 |
| 經事件證實停牌 | 0 | 0 | 0 |
| 漲／跌／平 | 538／451／91 | 330／466／71 | 868／917／162 |
| 可判定漲跌 | 1,080 | 867 | 1,947 |
| 已觀測行情日 | 3 | 2 | 不相加 |
| 經驗證還原價 | 0 | 0 | 0 |

上櫃有1檔收盤有效、官方漲跌價差無法解析為有效數值，排除漲跌分母，不補0或改用不連續前價。缺价原因未確認的30檔不稱為停牌或零成交。母體仍是最新公司名單：TWSE名單日10/11、TPEx名單日10/12，並非已驗證完整歷史母體。TPEx法人10/12涵蓋787檔普通股，僅供上櫃獨立研究。

TWSE保留10/7、10/8、10/12；TPEx保留10/8、10/12。MA20／60／120／240與突破仍未具備完整窗口，不能產生相關買賣訊號。TPEx完整獨立交易日曆尚未核准，日期品質保留unknown；TWSE行情日期符合已載入日曆。`freshCritical=false`，不將「成功收到今日資料」當成所有來源皆完整驗收。

## 更新保護與重跑

`python -m pipeline.daily --data-dir <隔離副本> --twse-current-csv` 是本階段人工驗證入口；沒有排程或Git／部署副作用。一次最多六個選定來源，不接信用、TWSE T86、margin歷史參數、付費來源。未加CSV選項時使用原OpenAPI，兩者均禁止歷史日期參數。

- 先在暫存副本收集，檢查來源與前後端資料契約，再將新快照納入；`market.json`最後以原子替換寫入。
- 來源錯誤、空表、日期倒退或同日數值修訂會中止此次整合；market、raw與source-state保留原位元組。失敗只另寫attempt報告。這是驗證／來源失敗保護，不宣稱多個檔案在磁碟故障或程序遭強制終止下具有資料庫式完整交易性。
- 同來源同日期、正規化內容相同時不重寫raw檔，保留首次快照SHA與fetchedAt，另記最近嘗試及回應摘要。內容異動不靜默更正，需審閱官方修訂。
- 假日收到前一交易日快照，保留其日期。拒絕週末價格、TWSE已知休市日价格與16:30前同日盤後價。TPEx未有完整日曆時不借用TWSE日曆宣稱已驗證；目前僅能作週末及來源日期檢查。
- 本次實際資料離線正規化重播兩次，17個raw快照數目及內容完全相同；模擬網路失敗後market位元組保持一致，證據見 `data/stage3c-replay-evidence.json`。重播沒有對官方再發請求。
- 品質報表分別提供有效價、缺列、缺價、原因未知、確定停牌、漲跌可判定分母、來源版本。市場日期不同時合併漲跌欄位為null，不能把兩天相加。

## 實際可用功能

搜尋、盤後收盤／股數、當日漲跌、熱力圖及產業平均使用當日有效原價，不依賴300日。各市場單獨顯示自己的asOf；合併視角要求同日才提供合併漲跌。產業表同時顯示母體檔數與有效樣本；熱力圖不以缺值當0。來源卡顯示快照首次抓取、最近檢查、資料日期及SHA摘要。

突破頁分開計算「具完整窗口家數」與「套用搜尋／量比後家數」，區分0檔符合條件和0檔足夠資料。即使輸入包含301筆原價，缺完整日曆／公司事件／還原驗證仍不能產生突破。TPEx連續法人訊號亦不把零散快照當成連續交易日；當日法人排名可以獨立顯示。

## 歷史授權證據與缺口

查核日2026-10-12。下表是本案證據界線，不是法律確定判決；「未確認」不代表來源不存在或一律禁止。

| 項目 | TWSE | TPEx | 本次結論 |
| --- | --- | --- | --- |
| 最新個股行情 | [11549](https://data.gov.tw/dataset/11549)，含OHLCV欄位、OGDL、免費、官方CSV及OpenAPI | [11371](https://data.gov.tw/dataset/11371)／[11370](https://data.gov.tw/dataset/11370)，最新行情、OGDL、免費 | 可依已開放資料的條款保存、加工、顯名再散布；本案採已核對最新介面 |
| 約300日個股OHLCV | [歷史月查詢](https://www.twse.com.tw/zh/trading/historical/stock-day.html)存在；尚未確認指定自動歷史端點與11549授權範圍對應 | [官方FAQ](https://www.tpex.org.tw/zh-tw/about/company/faq.html)說明下櫃股票仍可按年月查行情；未明列本案歷史批量與再散布授權 | 最新端點可用不等於歷史參數已核准；不批量抓取 |
| 日曆 | OpenAPI holidaySchedule及[年度表](https://www.twse.com.tw/zh/trading/holiday.html) | [年度表](https://www.tpex.org.tw/zh-tw/announce/market/holiday.html)、[115年公告](https://www.tpex.org.tw/storage/eb_data/11411/11400754581.html) | 有官方候選，仍須跨年度及臨時休市完整性驗證；TPEx未直接借用TWSE |
| 下市／停復牌／轉板 | [11543終止上市](https://data.gov.tw/en/datasets/11543)明列OGDL免費；[暫停交易查詢](https://www.twse.com.tw/zh/trading/historical/twtawu.html)可見 | [48665歷史停復牌](https://data.gov.tw/dataset/48665)明列OGDL免費；[終止上櫃查詢](https://www.tpex.org.tw/zh-tw/mainboard/listed/delisted.html)存在 | 新找到TWSE下市的明確資料集證據，但非完整轉板／臨時停牌歷史；本次未匯入事件全集 |
| 公司行動／還原 | [資訊商店公司行為](https://eshop.twse.com.tw/zh/category/sub/22)存在分內／外部使用的收費商品，未訂購 | [11633](https://data.gov.tw/dataset/11633)計算結果及[11634](https://data.gov.tw/dataset/11634)預告為OGDL；非完整歷史總報酬因子 | 沒有取得可直接核准的完整免費歷史因子與独立對帳證據 |
| 法人 | T86停用 | [11856](https://data.gov.tw/dataset/11856)開放授權最新明細 | 只發布TPEx範圍，未取得或發布TWSE T86 |

[OGDL第1版](https://data.gov.tw/license)允許對其授權範圍內資料重製、散布、公開傳輸與加工，並要求顯名；已適用者不必再逐次取得書面許可。仍須識別「哪個資料與取得方式已開放」，不能把網站所有內容視為同一授權。

[TWSE網站條款](https://www.twse.com.tw/zh/terms/use.html)對未經同意之自動下載設有限制，並為已授權政府開放資料保留例外。[TPEx網站條款](https://www.tpex.org.tw/zh-tw/gtsm_disclaimer.html?l=zh-tw)搜尋可讀內容亦有政府開放資料例外；本次直接頁面讀取回403，沒有規避限制。兩者的付費資訊商店不等於本案免費開放資料授權；未訂購，NT$0。

未取得官方針對本案300日批量、保存／公開Git歷史／JSON下載範圍的書面確認。已備妥 [TWSE詢問信](TWSE_LICENSE_INQUIRY_DRAFT.md) 與 [TPEx詢問信](TPEX_LICENSE_INQUIRY_DRAFT.md)，**均未寄出**，聯絡姓名／Email保留待填。

## 還原方法與下一個資料驗收關卡

rawClose與adjustedClose繼續獨立；正式還原欄位全null，版本核准清單保持空。因子工具只會將生效日晚於價格日的已核准乘數向前套用，不會由參考價自行宣告為總報酬。總報酬須另明定股息再投資、增減資、分割、有效日及修订版本。

收到精確端點／檔案授權後，先提出2–3檔、少量日期的樣本，涵蓋普通日、公司行動及缺價／停復牌；逐項比對官方OHLCV、股數單位、事件因子、原價／還原價和日期。只有對帳通過才提出300日正式回補方案；本階段不執行。

## Recharts棄用與遷移成本

鎖定版本仍為2.15.4，CI的npm棄用提示表示1.x／2.x分支不再積極維護。這是維護風險，不等同已證實可利用漏洞；本階段未做完整相依弱點稽核或改動lockfile。

依[官方3.0遷移指南](https://github.com/recharts/recharts/wiki/3.0-migration-guide)，React18及Node22符合最低要求。程式未使用Customized／CategoricalChartState或activeIndex等明顯移除API。主要成本是驗證Tooltip／Legend層次、雙Y軸的排序與CartesianGrid axisId、自訂Treemap格子、無資料／null及手機尺寸。信用圖表有ind／spy雙軸，升級時須特別保持視覺與凍結計算一致。估計為中等工作量、適合獨立PR；不是只改版本號即可驗收。本次保留已通過測試的現有圖表。

## 測試、安全與停止点

本地Python 44、Node 70與正式建置通過；新增重跑、同日修訂、日期倒退、來源失敗保留、休市、跨年、日期不一致、缺價與無效突破測試。Chromium新增390px真實整合資料驗收，合計15個；GitHub最新CI結果、commit與run連結記在Draft PR #1。實體iPhone Safari未測。

新增raw公司快照僅公司代號、名稱、產業、股數與日期白名單，無個人聯絡欄位。安全檢查涵蓋變更文字與追蹤路徑、常見GitHub/OpenAI/AWS憑證及私鑰格式、資料鏡像、TWSE institutional為空、creditHistory為空與信用核心設定不變。是限定範圍掃描，不宣稱完整資安認證。既有workflows未增加schedule、未啟動Pages；CI仍是公開repo標準runner。完成PR與CI後停止。
