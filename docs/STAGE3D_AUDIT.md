# Stage 3D：盤後觀察版上線準備與歷史授權確認

2026-10-13，Asia/Taipei。既有feature分支及Draft PR #1，未合併。**盤後觀察功能已完成本階段工程預備驗收；正式網站未發布。** 300日歷史、還原與完整交易日曆仍有缺口，完整策略發布門檻未解除。

交付：[正式上線檢查表](OBSERVATION_RELEASE_CHECKLIST.md)、[授權矩陣／官方窗口](DATA_LICENSE_MATRIX.md)、[TWSE詢問信](TWSE_LICENSE_INQUIRY_DRAFT.md)、[TPEx詢問信](TPEX_LICENSE_INQUIRY_DRAFT.md)。兩封信改為逐項表格，**均未寄出、未收到本案官方回覆**。

## 受控最新資料更新

12:49:13在隔離data副本人工執行一次 `pipeline.daily --twse-current-csv`，六個最新開放資料來源：TWSE日曆、兩市場公司名單、TWSE當日CSV、TPEx行情與TPEx法人。另單次核對TWSE OpenAPI，12:51:39開始、12:52:05完成，解析出的日期也是10/12。沒有歷史日期參數、T86或付費來源。來源URL、SHA256、首次快照時間、最近嘗試與原始結果見 `data/stage3d-update-manifest.json`。

此次CSV與TPEx同日重跑均保留既有raw檔；只有TWSE公司名單新增10/12版本。source.fetchedAt保留首次快照取得的管線時間，lastAttemptAt是本次更新開始時間，不能把兩者改成行情日。今日尚未完成盤後，未產生10/13行情或假交易日。

| 最新有效行情均10/12 | TWSE上市 | TPEx上櫃 | 合併 |
| --- | ---: | ---: | ---: |
| 普通股母體 | 1,085 | 893 | 1,978 |
| 有效未還原收盤價 | 1,080 | 868 | 1,948 |
| 覆蓋率 | 99.54% | 97.20% | 98.48% |
| 缺行情列 | 2 | 6 | 8 |
| 有列缺價、原因未確認 | 3 | 19 | 22 |
| 缺價／未知原因合計 | 5 | 25 | 30 |
| 上漲／下跌／平盤 | 538／451／91 | 330／466／71 | 868／917／162 |
| 漲跌可判定家數 | 1,080 | 867 | 1,947 |
| 已觀測行情日 | 3 | 2 | 不相加 |
| 經驗證還原價／MA240／突破240可用家數 | 0／0／0 | 0／0／0 | 0／0／0 |

公司名單日現在兩市場均10/12，仍是current-roster-only。TPEx法人10/12涵蓋787檔普通股，只有上櫃研究；不存在上市T86或完整合併法人訊號。上櫃1檔收盤有效但漲跌價差不可判定，不補成平盤。缺價30檔不擅自說成停牌。TPEx日曆仍unknown，freshCritical=false；不宣稱所有來源及長期資料都完整。

這是單次受控取用與既有離線重跑驗證，沒有多日正式上線可用率或SLA。Stage3C所見OpenAPI延遲在本次已追上10/12，但仍保留CSV選項及降版防護。

## 修補與前後端契約

- 更新失敗保留market／raw／source-state；日期倒退、同日內容修訂、空表與盤後時間未完成會拒絕更新。假日保留最後真正交易日，跨年缺日曆保持未知；兩市場異日不相加漲跌。
- 來源與市場metadata的日期必須一致；各市場SHA要完整合法。最新有價列的sourceVersion須與該市場來源版本吻合，不能偽造最新來源或自行核准日曆／還原／信用規則。Python及Node新增3組共用拒絕案例，現為13組研究契約案例，另保留原22組契約。
- 手機首頁保留母體、日期、每日漲跌與缺漏，詳細來源／更新時間／停用原因可展開。搜尋、切換、關注、產業排行、熱力圖及TPEx法人沿用同一已驗證資料；研究均線與突破仍停用。視覺核對另修正熱力圖：不以沒有股票資料的父層畫色塊，保留所有有值的小格；點選或鍵盤可開啟對應個股，CI核對有值股票與格數一致。
- HTTP讀取使用no-store及scanner_check時間參數、omit credentials、15秒逾時；失敗保留已載入資料。URL僅本站或無憑證的raw.githubusercontent.com，其他資料可用本機JSON匯入並驗契約。
- 頁面顯名為臺灣證券交易所、證券櫃檯買賣中心及臺灣期貨交易所，並說明普通股篩選／研究加工及OGDL第1版。完整來源與版本仍可在資料健康查看。

## Pages路徑、快取與安全

正式打包以相對base `./`輸出；preview在`/tw-market-scanner/`測試，增加`.nojekyll`。新Chromium測試**不攔截market.json**，讀取真實打包資料並檢查資源、搜尋、切換、產業、熱力圖與上櫃法人，另驗證異日與更新失敗保留最後版本。既有手機／桌面尺寸與18個模組測試保留。

CSP meta限制腳本同站、connect同站與GitHub raw、object禁用、base-uri同站、form提交禁用；React行內樣式明確保留unsafe-inline以保持圖表。無外部JavaScript、追蹤或Service Worker快取。Vite僅本機開發模式移除此meta以支援HMR，正式打包保留並檢查。referrer policy為no-referrer。

[GitHub官方HTTPS說明](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)支持公開repo的Pages與HTTPS，但**本次未設定或發布**。本地preview的no-store標頭不代表Pages的CDN；正式Cache-Control／MIME／CORS與實機仍須Stage4驗收。時間參數加no-store不能保證所有CDN立刻刷新，所以資料日期與版本始終顯示。

依[MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors)，frame-ancestors不支援meta；沒有假設meta等同X-Frame-Options或HSTS。沒有自訂域名、付費CDN或額外服務。

現有deploy workflow仍需main、PAGES_RELEASE_APPROVED、market-data資料分支及嚴格release_check。後者目前會拒絕未驗證的完整市場日曆，**不能直接按現況一鍵上線**。本階段未放寬該門檻；Stage4應獨立驗收只顯示有限盤後觀察功能的profile，並明確決定同包快照或market-data方式。詳見部署流程清單。

## 效能、CI與手機驗收

本地正式快照約2.95MB，gzip約193KB；全部JavaScript gzip約199KB。本地這次計算上市／上櫃／合併約95／51／205ms，具硬體差異；不是手機或公網載入速度。`scripts/audit-built.mjs`只做離線讀取，門檻為快照<8MiB、JS gzip<300KiB、單次計算<2秒，並查相對資源、安全meta與停用訊號。最新實測由CI的stage3d-build-audit.json記錄，不只依本地數字。

本地Python45、Node76及build通過；Chromium預定17個，包括新增真實打包／手機及異日失敗防護。最新實際CI數量與SUCCESS結果、commit、run放在Draft PR #1。CI加入官方upload-artifact@v7.0.2，只保存PNG和兩份驗收JSON一天，用標準公開repo runner；沒有每日schedule或部署步驟。

Chromium涵蓋320／375／390／430／1440px，不等於真實iPhone Safari或Android Chrome。實機、文字放大、弱網路與正式HTTPS快取尚未完成。截圖供本階段視覺核對，完整未測事項在清單。

Recharts2.15.4棄用提示保留，未修改依賴版本／lockfile。Stage3C已有3.0遷移成本報告，本次驗證現有圖表而非冒然升級。

## 授權確認與尚待回覆

最新TWSE11549與TPEx11371／11856等資料集明列OGDL／免費，屬指定最新介面的已確認證據。300日全市場OHLCV、自動取得方法、私人保存加工、公開Git版本／網站／下載，各自以H1–H4詢問，優先免費一次性年度或全市場檔。跨年／臨時休市C1、停復牌／轉板E1、公司行動與價格／總報酬因子A1–A2亦獨立詢問。

官方窗口已核對：TWSE機構信箱dataeshop@twse.com.tw、TPEx機構信箱tpexinfo@tpex.org.tw與機構服務電話。未寄信、未測送達；「未收到回覆」不稱為信已寄出等待回覆。官方證據及403限制記在授權矩陣，不推定手動CSV就是批量授權。

沒有取得合法完整歷史檔或核准因子，調整資料仍null。下一步由使用者審閱並另授權寄信；收到精確檔案／端點及權利證據後，先2–3檔小樣本對帳，再另提300日方案。

## 安全與停止點

檢查變更文字／追蹤路徑、常見GitHub/OpenAI/AWS憑證／私鑰格式、公司名單白名單、TWSE institutional空、信用history空、還原null與前後端鏡像。信用設定與核心計算函式未改，T86、因子、策略日曆仍未自核准。這是限定範圍檢查，不宣稱完整弱點掃描或滲透測試。

未操作txf-tracker、main合併、Pages設定或發布、每日排程、信件寄送、歷史批量或付費來源。CI只增加驗收與短期artifact；原發布與資料排程門檻不變。額外月費NT$0。完成最新CI與PR後停止，等待Stage4明確授權。
