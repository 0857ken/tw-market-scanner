# Stage 4B-1 — 最新行情更新與最終 RC 驗收

只核准一次受控最新官方資料更新、feature 開發、Draft PR 與候選驗收。不合併 main、不發布 Pages、不啟用 schedule、不抓 300 日歷史、不寄信、不付費、不改 txf-tracker；信用、TWSE T86 與未驗證歷史訊號仍凍結。

## 更新與來源核對

2026-10-14 02:28:36 台北時間在隔離的 data 副本執行一次 `pipeline.daily --twse-current-csv`，只含六個已核准最新來源；另外一次 TWSE OpenAPI 最新價量核對。既有 JSON 介面最多兩次有界重試，CSV與額外OpenAPI核對各最多一次，沒有歷史日期參數，未重跑更新。來源全部成功後才將四個新增快照、來源狀態、品質及完整 market.json 加入 feature。

**行情日上市與上櫃均 2026-10-13。** TWSE 當日 CSV 更新至10/13；TWSE OpenAPI仍是10/12，無法做同日對帳，不能把不同日價格差當成同日錯誤。採政府資料集11549明列的當日CSV，不混合不同日期。TWSE 最新公司名單仍為10/12，保留日期；TPEx公司名單與法人均10/13。

完整URL、版本SHA、來源日與抓取時間：`data/daily-attempt.json`、`data/stage4b1-update-review.json`、`data/quality.json`。產檔及最近檢查時間不是行情日，快照相同時仍保留首次抓取時間。

| 10/13 盤後資料 | TWSE 上市 | TPEx 上櫃 | 合併 |
|---|---:|---:|---:|
| 普通股母體 | 1085 | 893 | 1978 |
| 有效價格 | 1081 | 868 | 1949 |
| 覆蓋率 | 99.63% | 97.20% | 98.53% |
| 缺行情列 | 2 | 6 | 8 |
| 有列但缺有效價格／原因不明 | 2 | 19 | 21 |
| 未涵蓋有效價格 | 4 | 25 | 29 |
| 可判定官方漲跌 | 1081 | 867 | 1948 |
| 上漲／下跌／平盤 | 269／730／82 | 175／609／83 | 444／1339／165 |
| 已觀測價格日 | 4 | 3 | 不相加 |
| 最新公司名單日 | 10/12 | 10/13 | 不同日 |

29檔缺價不擅稱停牌。另1檔上櫃有價格但官方漲跌不能判定。TPEx法人773檔，120檔沒有當日法人列，不補零；只限上櫃，不冒充完整上市櫃法人。所有經驗證還原價仍null。上市名單日落後行情日：新增／轉板母體須人工核對，不能宣稱全市場當日成員已獨立完整驗證。

## 固定版本與安全檢查

- RC version：`4b1-rc1`，profile `observation-only`。
- 原始完整 market.json input SHA256：`0d63dfce2e572ef21ee51a759d5ba0ce36859d5b74936068b06f465a5f7e9411`。
- 同包公開投影 market.json SHA256：`bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9`。
- 完整 commit、RC ZIP SHA、Actions run、保存文件識別和最終驗收結果交付於 PR及保全附件，避免commit自我參照。
- 前端版本不再硬編碼4a-rc1；顯示manifest相同版本，新增普通股名單日期／落後提示。既有年月日、日曆不足、來源、延遲、缺價、停用功能和完整SHA追溯保留。
- 核准資料與前端同包；不依賴market-data；沒有DEMO、資料匯入／外部fallback、未授權TWSE法人、信用或長期買賣訊號。
- `release_check.py`／信用核心及資料授权種類未變；完整策略仍拒絕。觀察候選pass不等於策略資料完整或部署授權。
- `pipeline.verify_rc`只讀ZIP，不解壓、不取外部資料、不部署：核對外部核准ZIP SHA、commit、資料SHA、日期、manifest逐檔SHA、資源白名單、路徑／重複項／symlink／大小、資料契約及凍結限制。拒絕錯誤hash、額外範例或路徑、被改動資源；成功仍回傳publicationAuthorized=false。
- 常見token／私鑰模式掃描、公開公司欄位白名單、來源授權、資源白名單與前後端契約再次核對；不是完整滲透或漏洞稽核。Recharts 2.15.4棄用仍是已知風險，沒有升級或改動核心圖表。

授權證據：TWSE [11549](https://data.gov.tw/dataset/11549)、TPEx行情 [11371](https://data.gov.tw/dataset/11371)、TPEx法人 [11856](https://data.gov.tw/dataset/11856)，平台仍明列免費／OGDL第1版；其他已核准來源沿用`config/source-publication.json`及`docs/DATA_LICENSE_MATRIX.md`。沒有擴張為歷史批量下載、總報酬調整或TWSE T86授權。

## 驗收

預期執行：Python57（含新ZIP驗證4項）、Node78、Chromium17+6、普通正式build／RCbuild、效能與發布資源檢查。最終成功紀錄以固定SHA的Actions log及PR為準，未通過前不宣布完成。RC涵蓋320／390／1440px、實際同包資料、版本和公司名單日期、搜尋、關注持續保存、市場切換、熱力圖個股、產業展開、TPEx法人、缺價不使用前日價冒充、失敗保留快照／SHA拒絕與停用頁。

iPhone Safari實機仍待測；Chromium尺寸模擬不當作實機驗收。正式Pages HTTPS／CDN／MIME／回應安全標頭與公網快取只能待另行授權上線後驗證。

## 永久交付檔案

完整RC ZIP保存為獨立交付檔，不只留短期Actions artifact。另保存manifest、逐檔SHA清單、外部ZIP SHA、候選核准請求（所有合併／部署／排程權限均false）、本檢查表及離線驗證結果，打包為驗收附件。來源程式和原始已核准快照保留於immutable feature commit；未保存或上傳任何Secrets或未授權資料。

Stage4A既有commit／資料SHA保留，並另保存舊RC以利日後核准回復；舊版本保全不等於授權以舊資料正式部署。首次發行仍沒有已部署的正式前版。

## Stage 4B-2 單次部署檢查表（全部待另行授權）

- [ ] 使用者核准最終feature commit、`4b1-rc1`、10/13行情、公司名單日期差異、資料SHA、RC ZIP SHA和手機實機待辦；經過新交易日後再次確認接受延遲，不默認資料永遠最新。
- [ ] 確認固定SHA的CI全成功，下載長期保存RC ZIP與附件；先核對ZIP SHA，再執行`python -m pipeline.verify_rc <ZIP> --zip-sha256 <核准ZIP摘要> --commit <核准commit> --data-sha256 bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9 --as-of 2026-10-13`。
- [ ] 獲得明確Stage4B-2授權後，才核對PR仍Draft／未合併與main未變，核准需要的PR狀態／合併操作；main合併不得重新暗中換掉核准bundle。建置SHA屬feature，merge SHA另外記錄。
- [ ] 另審核單次Pages發布workflow／設定；目前workflow沒有Pages權限或發布job，不會因合併自動部署。
- [ ] 發布job僅接受核准ZIP與摘要／資料日期，來源由已保存bundle提供，不跟随移動分支、不抓資料、不重建不同前端、不啟用排程。只在人工核准發布job給予pages:write／id-token:write。
- [ ] ZIP驗證後只將site資源用官方Pages actions發布一次；驗收子路徑、JSON摘要、assets、來源／日期／缺價警示、HTTPS、CSP與手機核心互動。
- [ ] 若核准摘要、日期或資源有任何不符：在發布前停止，保留最後有效核准包，不換用DEMO或其他行情。
- [ ] 發布job失敗：停止後續步驟，若有既有站不改其核准版本；沒有既有正式版時不擅建替代站。
- [ ] 發布後驗收失敗：向使用者回報，再依明確核准回復整個同包或撤下；回復也明示舊日期，不只回前端／資料其中一半。Stage4A舊RC只能經另核准才作觀察版回復候選，不是假裝曾部署的正式版。
- [ ] 完成單次發布／必要回復後停止；沒有schedule、300日歷史、寄信、付費服務或策略解鎖授權。
