# Stage 3D 資料授權矩陣

核對日2026-10-13。狀態區分「指定最新資料已開放」「指定歷史取得尚待確認」「資料完整性未驗證」。兩封信均未寄出、未收到本案官方回覆。OGDL第1版涵蓋的資料可保存、加工、再散布並須顯名；問題是精確資料範圍與取得介面的對應，不是要求每次使用已開放資料都另取書面授權。

| 市場／資料 | 取得／保存／加工 | 公開GitHub／網站／JSON下載 | 證據與現況 | 問題編號 |
| --- | --- | --- | --- | --- |
| TWSE最新普通股OHLCV來源 | 指定官方最新介面已核對；本產品目前投影收盤、漲跌與股數 | OGDL範圍內可公開；標機關、日期與版本 | [11549](https://data.gov.tw/dataset/11549)直接列CSV及OpenAPI；本次兩者均10/12 | 已確認最新；歷史另H1–H4 |
| TPEx最新盤後行情 | 已核對最新API，排除非普通股 | 同上，不視為全歷史授權 | [11371](https://data.gov.tw/dataset/11371)／[11370](https://data.gov.tw/dataset/11370) | 已確認最新；歷史另H1–H4 |
| TWSE／TPEx公司名單 | 最新名單可用；投影代號、名稱、產業、股數及日期 | 公開上述欄位；不公開聯絡／個人欄位 | TWSE OpenAPI及[TPEx25036](https://data.gov.tw/dataset/25036)；current-roster-only | E1歷史成員 |
| TWSE300日全市場歷史OHLCV | 未確認指定免費檔與自動取得路徑，不批量抓取 | 私人保存／公開明細／衍生值／下載分開待確認 | 最新11549不直接推定歷史月份參數亦核准 | TWSE H1–H4 |
| TPEx300日全市場歷史OHLCV | 同上，優先年度／一次性檔 | 同上 | [官方FAQ](https://www.tpex.org.tw/zh-tw/about/company/faq.html)確認有歷史查詢，未確認本案批量方式 | TPEx H1–H4 |
| TWSE跨年／臨時休市日曆 | 官方最新日曆已用；300日跨年完整性未驗證 | 已開放指定資料可顯名再用 | [年度表](https://www.twse.com.tw/zh/trading/holiday.html)、OpenAPI holidaySchedule | C1 |
| TPEx跨年／臨時休市日曆 | 有年度表候選，獨立完整日曆尚未載入 | 指定歷史檔／再利用範圍待端點核對 | [年度表](https://www.tpex.org.tw/zh-tw/announce/market/holiday.html)；不借用TWSE宣稱TPEx已驗證 | C1 |
| TWSE下市／停復牌／轉板 | [11543](https://data.gov.tw/en/datasets/11543)下市為OGDL；其他事件全集未驗證 | 下市指定資料可顯名公開，其他另確認 | 下市不等於完整交易資格事件與穩定識別 | E1 |
| TPEx停復牌／下櫃／轉板 | [48665](https://data.gov.tw/dataset/48665)停復牌為OGDL；涵蓋與其他事件未驗證 | 指定48665可顯名公開；其他另確認 | 最新名單消失不擅自當成下櫃或停牌 | E1 |
| TWSE完整公司行動／因子 | 未取得免費完整檔，不用付費商店 | 私人／公開歷史及因子分開待確認 | 參考價不等於總報酬因子；沒有自製正式因子 | A1–A2 |
| TPEx公司行動／因子 | [11633](https://data.gov.tw/dataset/11633)／[11634](https://data.gov.tw/dataset/11634)指定開放事件可用；完整歷史因子未驗證 | 指定參考資料可公開，不稱已完成還原 | 現在adjustedClose全null，核准因子清單空 | A1–A2 |
| TPEx最新法人明細 | [11856](https://data.gov.tw/dataset/11856)已核對OGDL | 可在明確上櫃範圍顯名研究及公開 | 10/12涵蓋787檔；完整既有歷史另確認，不假定零散快照連續 | I1 |
| TWSE T86及衍生訊號 | 未核准、停用 | 不公開 | TPEx授權不能延伸至TWSE | 不在本次詢問範圍 |
| 信用利差資料／核心規則 | 資料授權、作者公式及前日狀態均未齊 | 停用，不發布假燈號或持倉 | 保留189窗口及pending設定；未變更 | 需原作者另提供 |

## 官方聯絡路徑

| 機構 | 建議機構信箱／電話 | 官方證據 | 核實界線 |
| --- | --- | --- | --- |
| TWSE | dataeshop@twse.com.tw；02-8101-3393／3494，請數位資安部轉開放資料授權承辦 | [服務窗口](https://www.twse.com.tw/zh/about/company/service-contact.html)、[Data E-Shop](https://eshop.twse.com.tw/zh/mops/about) | 官方頁公開機構信箱，未寄信或驗證送達；網站頁尾連結實為不法案件檢舉，不作本案詢問入口 |
| TPEx | tpexinfo@tpex.org.tw；02-2366-6106／5976，請轉資訊／開放資料承辦 | [官方商店聯絡資訊](https://eshop.tpex.org.tw/zh/product/list/1)、[資訊業務窗口](https://www.tpex.org.tw/zh-tw/service/data/product/regulation.html) | 官方機構信箱；一般聯絡表單回403，未繞過、未寄信 |

[OGDL第1版](https://data.gov.tw/license) · [TWSE網站條款](https://www.twse.com.tw/zh/terms/use.html) · [TPEx網站條款](https://www.tpex.org.tw/zh-tw/gtsm_disclaimer.html?l=zh-tw)。資料集精確端點與規範是證據範圍；手動CSV、付費資訊商店或第三方抓取程式不能替代許可。

待回覆最優先順序：H1免費一次性全市場檔 → H2自動取得方式 → H3／H4保存及公開權利 → C1／E1完整日期與事件 → A1／A2因子與對帳。回覆經核對後先2–3檔小樣本，再另提300日計畫；本階段不執行回補。
