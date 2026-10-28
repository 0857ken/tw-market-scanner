# 台股掃描器 Stage 4C-2A：正式版本持久狀態與安全發布架構
版本：設計提案 v1.0｜研究日：2026-10-17（Asia/Taipei）
Repository：0857ken/tw-market-scanner
基準：Draft PR #2，commit db5e1f41b2637856bd3d48cfa49d0f314a6e9808

**本文件只交付研究與下一階段規格，不是實作、合併、遠端儲存初始化、Pages 發布、回復或排程的授權。** 本輪未修改 repository、PR、main、正式網站、Secrets 或設定；未觸發 workflow、抓取金融來源、建立 Release／state 分支或使用付費資源。

## 1. 建議決策

採用「**GitHub Releases 保存完整、不可變的版本檔案；獨立 scanner-release-state 分支保存小型狀態與稽核紀錄**」。

- Releases 保存每個版本的完整網站 ZIP、完整可恢復採集狀態 ZIP、候選 receipt、固定前端種子／pin／政策與檔案索引。
- state 分支保存唯一 successfulPointer、發布中的 transaction、停止狀態及逐次成功／失敗證據。不要把每日 ZIP 或原始資料整包 commit 到 Git。
- 每日 baseline 只從 successfulPointer 指定的精確版本讀取，驗證完整關係並重新核對線上檔案；不讀 latest Release、pending、checkout fixture 或不存在的 market-data。
- Pages 與 state 沒有跨系統原子交易。使用持久發布預約、Git 分支 CAS、單一發布者、冪等識別及人工處理 UNKNOWN，管理這個缺口。
- 異常後預設停止。不自動 rollback、不因逾時重送 Pages，不把指標改回舊值冒充網站已回復。
- 新每日 manifest 前端必須一次性核准精確 seed ZIP；之後行情發布重用相同 HTML／JS／CSS 位元組，不從 main 重建。

建議先核准「離線 adapter 與故障測試」實作。遠端 Release／state 初始化、固定前端遷移、一次 Pages 發布、人工回復演練、未來排程，各自另設核准界線。

## 2. 已核對的現況與可重用成果

### 2.1 遠端事實

| 項目 | 本輪讀取結果 |
| --- | --- |
| PR #2 | open、Draft、未合併 |
| PR head | db5e1f41b2637856bd3d48cfa49d0f314a6e9808，與指定 commit 一致 |
| main | d1a700ffa2c5af42ca1a10ea90877bd3cce7e67a |
| Repository | public；API size 約 2,688 KiB，這是 repository 統計，不是逐檔工作樹大小 |
| 分支 | main、feature/scanner-v3-real-data、feature/stage4c1-daily-update；沒有 market-data 或正式 state 分支 |
| Releases | 查詢結果為空 |
| 分支保護 | branches 回傳 protected:false；rulesets 查詢為空。不能稱現況已有保護 |
| Push CI | Run 38938248745，completed／success，固定上述 head |
| PR CI | Run 38938256502，completed／success，attempt 1，固定上述 head |
| 本輪 CI 日誌核對 | PR Run test job 117099092251：Python 94、Node 80、Chromium 17＋6＋7，共 204 項通過；建置與 workflow audit 步驟亦成功 |
| 原首次正式 Pages | Run 38496725153 的 verify、deploy、acceptance 三個 job 均 success |
| 原正式 ZIP | Artifact 11862513391、Run 38494657009；413,691 bytes，expired:false |
| 原正式 ZIP SHA-256 | 7621524742b25dfaa7a7216ca5f5b5006719a252966a0554ff7d0416c3262eee |
| 原正式公開資料 SHA-256 | bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9 |
| 原正式 ZIP 到期 | 2026-10-21 01:17:40 UTC，即台灣 10/21 09:17:40 |
| 原核准程式版本 | 82b1749a2626ce30d6196a101577b8bb09273c31，正式資料日期 2026-10-13 |

本輪核對的是 GitHub metadata、固定 SHA 的程式與既有 CI 日誌，沒有重跑測試或部署。正式站逐檔即時 SHA 未在本輪完成：公開 manifest 的研究工具讀取未成功，因此不能宣稱「今天仍逐檔與原 ZIP 相同」。此項必須在未來 bootstrap／發布前實際執行。

原始 Artifact 到期是具體初始化風險；本輪沒有下載移存或延長期限。若下一階段開始時已到期，須取得可信的原 ZIP 副本並比對既有核准 SHA，不得重新 build 取代它。

### 2.2 程式對照：延伸既有流程，不重寫

| 現有檔案／能力 | 可直接重用 | 4C-2 必補的邊界 |
| --- | --- | --- |
| docs/STAGE4C2_INTERFACE_DESIGN.md | VerifiedBaseline、候選 binding、發布狀態機、人工回復原則 | 本文件將其具體化為儲存／CAS／故障契約 |
| pipeline/daily.py | 唯讀 baseline、隔離採集、六個已核准最新來源、來源日期與品質邏輯 | 輸入須由正式 baseline loader 提供，不能繼續以 checkout data 當正式起點 |
| pipeline/daily_release.py | gate、project、來源關係檢查、固定前端 bundle 與逐檔驗包 | controlled() 的完整 updated-data 位於 TemporaryDirectory；目前只公開 gate／candidate-market／report／attempt，完整採集狀態未輸出，離開函式後消失 |
| pipeline/package_daily.py | 獨立打包、精確 seed ZIP SHA、拒絕 failure／no-op、靜態資源重用 | 加入 baseline generation、run attempt、完整採集狀態與新版 receipt binding |
| pipeline/daily_state.py | 本機 immutable ZIP／ledger、flock／CAS／restore 演練 | 不是遠端 state adapter；restore() 只換本機 pointer，沒有 Pages 操作 |
| pipeline/daily_policy.py、config/daily-release.json | 候選權限預設關閉、門檻與政策 SHA | 不可翻轉候選旗標來授予正式權限；正式權限須外加獨立、經審核的發布控制 |
| frontend/src/observation.js | 新每日 manifest loader 的同源／資料 SHA／停用功能核對 | 每日 loader 尚未正式部署；frontendId 相同不代表 seed bytes 核准 |
| scripts/audit_workflows.py | 全 workflows、permissions、禁止 schedule／舊路徑等稽核 | 未來若加 workflow，必須精確新增允許清單與負向測試，不能放寬成任意寫權限 |
| tests/test_candidate_safety.py、tests/test_daily_release.py | 資料寫入中斷、ZIP、local CAS、跨 seed restore、來源／品質與 workflow 測試 | 增加遠端 CAS、Releases 完整性與 Pages UNKNOWN 情境，保留既有測試 |
| .github/workflows/update-data.yml | 人工隔離採集、contents:read、8 分鐘 | 沒有正式 baseline loader／持久來源輸出 |
| .github/workflows/package-daily.yml | 人工打包、contents:read＋actions:read、核對來源 Run 與 SHA | 依賴短期 artifacts，沒有正式協調器 |
| .github/workflows/pages-release.yml | 原 ZIP 驗證、Pages、逐檔 HTTPS、正式瀏覽器驗收可供參考 | 仍是一次性 4b1 發布；獨立 concurrency group，沒有 state CAS，不可直接當每日發布入口 |

**兩個不可混淆的資料層：**

1. 公開 market.json 是觀察版投影，部分欄位被清除或移除；不等於可恢復全部採集狀態。未假設它已裁切股票 history 天數。
2. data/raw/*.json 實際保存解析後的 rows、日期、URL 及來源回應 digest，不是原始 HTTP response bytes。不能拿檔內 sha256 當該 JSON 檔案自身的 SHA。

## 3. 保存方案比較與平台限制

查證日期：2026-10-17。下列平台限制來自 GitHub 官方文件；工程預算另外標示，並非平台保證。

| 方案 | 完整 ZIP／來源狀態 | 成功指標與競爭控制 | 成本與限制 | 維護評估 |
| --- | --- | --- | --- | --- |
| 只用 GitHub Releases | 適合大型檔案；可開啟 immutable releases | latest／Release 標籤不表示部署成功；欠缺適合的小型 CAS 狀態 | 每 Release 至多 1,000 assets、單檔小於 2 GiB；文件未設 Release 總大小／頻寬上限；不是無限保存 SLA | 需另外補指標與交易紀錄，不單獨採用 |
| 只用獨立 state 分支 | 小型 JSON 適合；完整 ZIP 每日 commit 會累積不可回收 Git 歷史 | 一個 ref 原子推進，適合 CAS | Git 單檔一般超過 50 MiB 警告、超過 100 MiB 阻擋；大型歷史 clone／維護成本上升 | 不適合當每日二進位資料庫 |
| **Releases＋小型 state 分支** | **完整版本在 Releases，依精確 asset ID／SHA 讀取** | **單一 state commit 原子更新 pointer＋transaction** | **利用現有 public repo；不需另購雲端／LFS；仍受平台政策與 API 限制** | **兩個元件，但責任清楚；建議採用** |
| Actions artifacts／cache | 適合短期診斷／交接，不適合持久 baseline | 無正式成功交易指標；cache 可能淘汰 | 現有 artifacts 1／7 日；public artifact retention 可設定 1～90 日；Free 表列 artifact 500 MB，與 Packages 共用，不能當 Release 額度 | 不採用為正式唯一儲存 |
| Git LFS／外部 object storage | 技術上可行 | 仍需 CAS／協調器 | 額外額度、憑證、政策與可能費用；本階段不啟用 | 目前沒有足夠利益，不採用 |

GitHub Pages 公開站可使用 Free：網站成品上限 1 GB、每月頻寬 soft limit 100 GB、部署超過 10 分鐘逾時。每小時 10 builds soft limit 不適用自訂 Actions 發布，但這不免除其他平台限流。

公開 repo 的標準 GitHub-hosted runner 為免費使用範圍；larger runner 即使 public repo 也會計費。500 MB 是 Free 的 Actions／Packages 相關儲存表列額度，**不是 Releases 的總容量上限**。本設計只用標準 ubuntu runner，不增加付費設定，也不假設其他專案的共用額度為零。

immutable Release 保護 assets 與 tag；標題、說明與 latest 標記仍可改，整個 Release 仍存在管理者刪除風險。必須由核准後的初始化流程啟用並實際核對 immutable:true，不能只靠命名規則宣稱不可變。它只保護啟用後的新 Releases。

### 3.1 容量測量與估算

本輪固定 commit 的 Git tree 未壓縮檔案大小：

| 項目 | 實測 bytes | 約 MiB | 解讀 |
| --- | ---: | ---: | --- |
| 原正式網站 ZIP | 413,691 | 0.395 | 真實已部署版本的壓縮大小，不是新每日 seed 的大小 |
| PR 工作樹 data/ | 5,903,064 | 5.630 | 含完整 market、解析後快照及少量其他證據；未製作新 ZIP |
| 其中 data/raw/ | 2,243,717 | 2.140 | 含目前已累積的各來源日期檔 |
| frontend/public/market.json | 3,562,233 | 3.397 | 工作樹檔案；不是以此認定當前線上資料 SHA |
| PR CI dry-run artifact | 2,276,629 | 2.171 | 內含演練／證據，不等於單一正式 ZIP |
| PR CI RC artifact | 413,771 | 0.395 | 候選固定 RC，不是原正式 ZIP |
| PR CI browser artifact | 4,200,211 | 4.006 | retention 1 日 |

容量公式：

- N 個保留成功版本，網站 ZIP 為 S_i，採集狀態 ZIP 為 A_i，seed／政策／receipt 為 M_i，總儲存約為 Σ(S_i＋A_i＋M_i)。
- 若僅以原網站大小示意，250 個交易日約 98.6 MiB；完整來源狀態與歷史會使總量明顯更大。
- 規劃情境：每版合計 2／10／50 MiB，250 版分別約 0.49／2.44／12.21 GiB。這是容量情境，**不是實測採集包大小預測**。
- 完整來源歷史會增長，每日重存全量可能呈二次累積：若 A_i＝A_0＋i×d，全年採集包總量＝N×A_0＋d×N×(N＋1)/2。不得用第一天 A_0 乘 250 宣稱全年固定。
- run.snapshots() 雖只讀最後 300 個快照，現有程式沒有因此自動刪除 data/raw 舊檔；不得直接新增 prune，以免改變研究／成員歷史語意。

建議第一版保存「自足、無 delta chain 的完整採集包」，降低回復依賴；先量測 10 次真實成功版本再修正估算。以下是**提議的工程保守預算，須核准後才生效**：

| 預算／保留規則 | 建議 |
| --- | --- |
| 網站 ZIP | 保留既有驗證器 16 MiB ZIP／12 MiB 展開上限，不為容納增長自動放寬 |
| 採集狀態 ZIP | 新格式初始上限 64 MiB ZIP／256 MiB 展開／10,000 entries；超限停止，不截斷資料 |
| 專案 Releases 合計 | 1 GiB 提醒；預估下一版將超過 5 GiB 時停止新增封存與發布，人工處理；這是自設預算，不是 GitHub 配額 |
| state 小檔 | state.json ≤64 KiB；單事件／成功證據 ≤256 KiB；累計達 100 MiB 時人工檢視，不自動 rewrite history |
| artifacts | 診斷 7 日、瀏覽器截圖 1 日、Pages 交接 1 日；專案暫存預算 100 MiB，並檢查帳號共用量 |
| 保留最低集合 | genesis、current、previous、所有 unresolved transaction 的完整包與各自 seed／政策，不受年齡清除 |
| 歷史建議 | 最近 90 個成功版本＋最近 12 個月的每月末成功版本；其餘僅能在人工核准、驗包／回復演練後整版移除 |
| 刪除 | 不做自動 GC；immutable release 不可逐 asset 修補，若未來准許移除，須按整版依賴閉包辦理 |
| 增長處理 | 若自足包超預算，另開變更評估 snapshot 內容定址去重或更長期冷存；本輪不先引入複雜 delta／跨包鏈 |

所有成功版本的小型 receipt／索引摘要與 generation 鏈長期留在 state。若歷史完整包依核准保留政策刪除，須記為 retired、註明不再可完整回復；不能繼續把該版本列為可回復。

維護工時預算：初始化盤點／原包匯入約 1～2 小時人工核對、每月約 10～20 分鐘查看容量與回復可用性、每季一次離線還原演練。這是規劃估算，不含異常修復工時。

## 4. 建議資料模型與保存內容

### 4.1 三個可信度層次

1. **CandidateReceipt**：只證明候選通過既有資料／ZIP gate，不能證明部署成功。
2. **ArchivedPackage**：Release 已完整上傳、讀回驗 SHA 並凍結，表示版本材料可恢復，仍不能當 successful。
3. **SuccessRecord**：精確 Pages 部署成功＋線上驗證＋最終 CAS 成功，才可被 successfulPointer 指向。

候選內既有 productionBaselineVerified:false、deploymentAuthorized:false、production:false 不得改為 true 冒充正式證據。正式成功證據由新的外部 SuccessRecord 提供；保留既有候選驗證器與政策的「不能授權正式發布」語意。

### 4.2 每個不可變 Release

建議唯一 tag：scanner-archive-<targetDate>-r<sourceRunId>-a<attempt>-<siteZipSha前12位>。永不覆寫同 tag；Release published 只表示「封存已凍結」，網站是否成功仍只看 state。不要使用 latest 或 prerelease 作成功判定。

| Asset | 必要內容 |
| --- | --- |
| site.zip | 要部署的完整 ZIP 原 bytes；包含 index、JS／CSS、market、manifest、.nojekyll；禁止重新 build 或重新壓縮替代既有核准 ZIP |
| acquisition-state.zip | 對應版本的完整可讀採集目錄：內部 market.json、source-state.json、實際計算依賴的解析後 raw snapshots、必要品質／來源 metadata、inventory |
| supporting-material.zip | 該版精確 frontend seed ZIP／pin、candidate／license／observation 政策原 bytes、來源顯名與授權證據、processor commit／檔案雜湊 |
| candidate-receipt.json | v2 完整候選契約；舊格式 receipt 原 bytes 的 SHA 與內容另附，不竄改舊 receipt |
| package-index.json | 前四項的 name／asset ID／bytes／SHA-256、repository ID、Release ID、格式版本與完整性狀態；自身 SHA／asset ID 由 state 外部記錄 |

雜湊依賴必須無循環：site／acquisition／support → candidate receipt → package index → state。package index 不含自身 hash，ZIP 內 inventory 不含該 ZIP 自身 hash。

先建立 Draft Release，上傳前四項、讀回比 SHA，再產生／上傳索引、再讀回；最後凍結 Release。不使用 GitHub 自動生成的 source-code zipball 代替 site.zip。上傳回應不確定時按精確 Release／asset ID 查詢：同 bytes 可視為既有結果；空 starter／不一致 asset 停止並隔離，不能刪除後 clobber 核准資產。

成功後的 deployment／live 證據留在 state 的新檔與 SuccessRecord，不向已凍結 Release 補檔。復原包依賴的 seed 每版自帶，避免舊版本因最新 seed 改變而失效。

### 4.3 採集狀態與來源快照規則

- inventory 對每個檔案列相對路徑、實際 bytes、檔案 SHA、module、日期、來源 URL、原來源 response digest、schema／parser／license policy。
- parsedSnapshotFileSha256 是快照 JSON bytes 的 SHA；responseSha256 沿用原取得時的來源回應 digest；二者不可互換。
- 現有舊來源沒有原始 HTTP body，須標 responseBodyArchived:false，不能補造 body 或稱已驗證原 HTTP bytes。
- 本期必要材料是可恢復的解析後來源快照；不額外要求保存未篩選的原始公司 API body。原始公司資料可能包含聯絡／個人欄位，不能因封存而擴大公開範圍。
- Release／state 都是 public。先做 input closure 盤點：必需且已核准的資料完整保存；非依賴資料僅可在證明不影響投影／歷史後排除；無權公開的依賴會阻擋初始化，不能藏進 Draft 當私有儲存。
- 新採集仍限既有六來源；tpexEvents 等既有必要歷史依賴可唯讀保存，但不新增來源請求。T86、信用、還原價、付費或歷史批量來源不能藉封存開啟。
- 每個採集包可獨立恢復，不靠前一 ZIP、最新 checkout 或過期 artifact。
- 所有 ZIP 禁絕 traversal、symlink、重複 entry、不允許檔案、異常展開大小；網站包沿用既有規則，採集包另定嚴格格式。

### 4.4 CandidateReceipt v2 必要欄位

| 欄位群 | 必須綁定 |
| --- | --- |
| identity | schemaVersion、repository ID／name、environment、profile、operation kind |
| baseline | successful generation、published ZIP SHA、candidate receipt SHA、acquisition ZIP SHA、讀取時 state commit SHA |
| intended slot | Asia/Taipei 原定交易日、原始 event／slot／deadline、實際開始時間；備援共用同一 target |
| provenance | source Run ID＋runAttempt、成功 upstream run／workflow path／code SHA、processorCommit |
| policies | candidatePolicySha256、licensePolicySha256、observationPolicySha256、input schema／parser版本 |
| fixed frontend | 精確 seed ZIP SHA、frontendPinSha256、static file hash inventory，不能只檢查 frontendId |
| output | candidate internal market SHA、公開 market SHA、sourceIdentitySha256、manifest SHA、完整 site ZIP SHA、採集包與support包 SHA |
| gate | decision、各市場實際日期、coverage／roster、停用功能、來源集合與來源 identity、no-op／revision判定 |
| authority | candidate 本身沒有發布或回復權限；獨立 approval reference 僅由協調器驗證 |

sourceIdentitySha256 沿用既有 identity() 定義；如果要改定義須升 schema，不同含義不能共用舊欄位名。runAttempt 不可省略或默認為目前最新 attempt。

### 4.5 state 分支

scanner-release-state 為未來人工核准初始化的 orphan 分支，只放資料 JSON／說明，不能含可執行 workflow 或成為 Pages source。

| 路徑 | 角色 |
| --- | --- |
| state.json | 唯一原子快照：schemaVersion、stateRevision、control、successfulPointer、activeTransaction |
| transactions/<key>/<sequence>.json | 不覆寫的階段事件、前事件 SHA、操作鍵、fence、時間、錯誤 |
| successes/g<generation>.json | 不覆寫的 SuccessRecord、前代指標與成功證據 |
| receipts/<digest>.json、indexes/<digest>.json | 成功版本的完整小型 receipt／package index 副本，長期保存以免隨歷史大包退役而失去追溯 |
| live-evidence/<digest>.json | 小型逐檔 HTTPS 證據與 API 狀態摘要 |
| approvals/<digest>.json | 已明確核准的操作／seed／政策範圍與到期條件，排除 Tokens |
| retired/<digest>.json | 未來人工核准移除完整版本包的稽核紀錄 |

state.json 欄位語意：

- stateRevision：每次遠端狀態轉換遞增。
- successfulPointer.generation：僅新增成功版本／成功人工回復時遞增；不因失敗回退。
- successfulPointer：publishedZipSha256、receiptSha256、acquisitionZipSha256、packageIndexSha256、Release／asset IDs、frontendPinSha256、seed ZIP SHA、sourceIdentitySha256、sourceRunId／runAttempt、deploymentId、successRecordSha256、前代 pointer。
- receiptSha256 明確指 candidate-receipt.json；successRecordSha256 另指部署後成功證據，避免兩種 receipt 混用。
- control：halted、原因、觸發操作、未決事故。正式發布／rollback／schedule 權限預設關閉，不能由每日資料輸入授權。
- activeTransaction：operation key、PREPARED 等 phase、baseline generation／ZIP、候選 ZIP、run／attempt、fence、deploymentId（可 null）、archive refs。
- state commit SHA 是外部讀取結果，不塞入該 commit 內自我雜湊。

Git 歷史不是獨立數位簽章。保護 ruleset、固定 workflow、token 權限、SHA 鏈與 immutable Release 共同形成信任邊界；管理者刪 repo／改規則仍屬剩餘風險。

## 5. 最後成功 baseline 載入與初始遷移

### 5.1 load_verified_baseline 契約

沿用介面文件的名稱，建議明確參數為 expectedPublishedZipSha256、expectedGeneration 與 policy context；回傳原介面 VerifiedBaseline，另附 stateHeadCommit、完整封存定位與 input inventory。

必須依序：

1. 讀 scanner-release-state 的 ref 得到固定 H，再從 H 讀 state.json；不能一檔用 branch、另一檔用更新後 branch。
2. 核對 schema、控制狀態、successfulPointer 與 SuccessRecord／generation 鏈；缺 state 或缺 success 就停止。
3. 存在未決 activeTransaction 時，診斷可讀舊成功包，但不得建立新的每日發布；UNKNOWN／halted 一律拒絕正式工作。
4. expected ZIP／generation 不一致即停止，不尋找「差不多的」版本。
5. 按 repository ID、精確 Release／asset ID 下載 index、receipt、site、acquisition、support；核對 immutable、asset state、size、每個檔案 SHA。
6. 安全解包、完整核對 inventory、來源日期／URL／解析快照／source-state／內部 market／公開投影之間關係。
7. 重用該版原 processor／投影契約核對公開結果；有時間欄位須使用記錄的 effective time，不能用今天重算而改 bytes。舊政策驗證與目前授權相容性分開。
8. 用該版前端 pin 驗證整包；legacy 版走明確 legacy adapter，不能硬套新版 manifest。
9. 重新以 HTTPS 驗證當前站點的每個可公開檔案與 pointer 指定版本一致，保存證據；資料太舊可顯示 stale，但不把 stale 當新交易日成功。
10. 驗證目前授權／候選政策相容；有政策變更須人工審核。不能用「舊版曾成功」跳過目前禁止條件。
11. 將只讀 baseline materialize 給現有 run_daily()／controlled()；任何輸出在全新隔離目錄。對 input 做前後 hash inventory 檢查。

**絕不 fallback：** main/data、PR fixture、market-data、latest Release、pending 包、只有公開 market 的資料、重新抓當日資料來冒充歷史 baseline。

### 5.2 legacy genesis 匯入

現有正式站沒有新式成功指標，因此不能直接呼叫正式更新器。未來需一次明確核准的「只匯入、零部署」程序：

1. 取得原完整 ZIP，核對上述 76215247… SHA、原 CI／artifact／Pages run。
2. 取原核准版本 82b1749a… 的採集材料，盤點完整 input closure；**checkout 只是一份候選證據**，不是天然可信正式 baseline。
3. 以原投影／manifest／source identities 與時間契約驗證其對應公開 ZIP；不能以今天的 data/ 或新行情替代。
4. 為原前端建立 legacy static inventory 與版本化 legacy receipt；沒有原本不存在的 daily frontend-pin，不捏造「當時已核准」的紀錄。
5. 逐檔即時 HTTPS 核對。若站點與原 ZIP 不一致／來源材料不足，停止匯入並交人工調查。
6. 取得具體匯入核准後，建立 immutable 封存與 state genesis。保留原 4b1 公開 ZIP bytes，記為 g0；這不是一次新的 Pages 發布。
7. 記明舊來源僅有解析快照與 response digest 的證據等級；任何缺口需 owner 明確接受或補證，不可自動降標準。

新的 daily frontend seed 為另一個核准事件。先保存目前 4b1 可回復材料，再核准新 seed、pin 與候選，之後才可能進行首次新前端發布。第一次新版本成功後，g0 才成為可實際回復的前一正式版本。

## 6. 跨系統 CAS、發布預約與權限

### 6.1 遠端 CAS 的具體作法

GitHub Git ref PATCH 沒有 expected_sha 參數；不能把「先 GET 再 force PATCH」當原子 CAS。

選用以下方法：

1. 讀取 state ref＝H。
2. 新建 state tree，所有新事件與 state.json 放入**同一個** tree。
3. 建立新 commit C，**唯一 parent 必須精確等於 H**。
4. PATCH 該 ref 到 C，force:false。若另一 worker 已由 H 推進到不同 child，C 不是目前 ref 的 fast-forward，伺服器拒絕。
5. 寫後讀回 ref；若連線逾時，先查目前 ref／歷史是否已包含 C，不能直接再建另一份成功紀錄。
6. 成功 generation／ZIP、activeTransaction／fence 必須同時符合應用層前置條件。衝突不得自動 rebase 舊候選；部署前衝突停止，部署後衝突進 UNKNOWN。

成立條件：state 線性、禁止 force push／刪除／任意 merge；所有寫者遵守同一 adapter。這是由 Git fast-forward 與單父 commit 組合而來的設計推論，必須用兩個並行 worker 的整合測試驗證，不只 mock 一個 expected_sha。若兩個請求剛好提交完全相同的 C，應辨識為同一結果的冪等成功，不產生兩筆紀錄。

### 6.2 發布預約與 operation key

operationKey＝SHA-256(canonical(repositoryId、environment、operation kind、baseline generation、baseline ZIP SHA、intended targetDate、candidate ZIP SHA))。

- 同一 transaction 的 rerun／resume 使用同 key。run ID／attempt 是來源 binding，不用來繞過同一 operation 的去重。
- 不同 ZIP 在同日仍須經既有 revision gate，不能以換 run／key 接受修訂。
- PREPARED 必須先用 CAS 持久化 activeTransaction，才有權送 Pages。
- activeTransaction 使用單調遞增 fence；只允許該 operation／fence 推進。最後一刻再查 state、成功版本、停止旗標與線上 baseline。
- 不以 TTL／lease 到期自動釋放發布預約。時間過了不代表 Pages 沒有收到請求。
- all Pages writers 必須共用 scanner-pages-production 的 concurrency group、cancel-in-progress:false，並遵守 state 預約。
- 現有 pages-release.yml 的首次發佈路徑必須在未來經核准退役或納入同一協調器；只把新 workflow 設同名 group 而保留舊入口繞過 state，仍不合格。
- GitHub concurrency 不保證 FIFO，也不是持久佇列；排隊取消／延遲要以 intended slot 與 state 判斷，不能藉此宣稱 exactly once。

### 6.3 發布 API 與 ID

正式 transport 不能只回傳 page_url；必須取得 Pages 建立回應的 deployment id，盡快持久記錄，才進入輪詢。通用 Deployments ID、Pages deployment ID、Actions Run ID、artifact ID 各自保存，不互換。

建議薄 transport 使用官方 Pages create／status API 與官方 Actions OIDC 流程。create 只送一次；不能沿用一般 HTTP helper 對不確定 POST 自動 retry。pages_build_version 使用 transaction 的唯一識別（例如 operation key 的 40 位 hex），真實 processor／workflow SHA 另存；官方欄位允許 unique build string。不能因每天 code SHA 相同就把 SHA 當部署唯一鍵，也不能預設回傳 id 必定等於 build version。

現有 deploy-pages action.yml 只公開 page_url output，未能直接提供此持久 ID 契約；如採用 wrapper／受控 action 變體，需固定其精確 action commit，審核 API、OIDC、取消及重試行為。實際 API 能力驗證只可在未來另准許的隔離環境進行，不為驗證而部署目前正式站。

### 6.4 權限拆分提案

| Job／元件 | 最低權限提案 | 限制 |
| --- | --- | --- |
| PR CI／離線測試 | contents:read | 無 Pages／state／Release 寫入 |
| acquisition／package | contents:read；必要時 actions:read | 不執行 artifact 內程式、不改 main |
| archive／prepare | contents:write；必要時 actions:read | 僅核准的 Release 與 state 路徑；不具 Pages 權限 |
| publish transport | pages:write、id-token:write、actions:read；為即時記錄部署 ID，限此 job 加 contents:write | 這個組合是窄範圍必要例外；只跑受信任固定程式，不 npm install／build／執行下載內容 |
| live verifier | contents:read、pages:read、actions:read | 只讀 API／HTTPS |
| success recorder | contents:write、pages:read、actions:read | 再核對證據後 CAS；無 Pages POST 權限 |
| reconcile report | contents:read、pages:read、actions:read | 預設只產生人工處置報告 |
| manual restore | 僅在單次核准後交給同 publish coordinator | 禁用獨立繞過鎖的 deploy 路徑 |

GITHUB_TOKEN 的 contents:write 是 repository scope，不是僅能寫 state 分支。需要 main／其他分支保護、固定 ref／environment、最小 job 範圍與 workflow audit；不能聲稱 token 原生只能寫 state。

免費公開 repo 可用 branch／tag rulesets；先設禁止 state force push／刪除與線性歷史，再驗證核准寫者能正常 append。不可直接要求每次 state 更新都走 PR 而又假設 GITHUB_TOKEN 能 bypass；若既有 token 與規則不相容，停止遠端初始化，提交具體保護方案，不自行加 PAT／Secrets 或放寬 main 保護。

## 7. 發布狀態機與每種故障的處置

正常路徑：

PREPARED → DEPLOY_REQUESTED → DEPLOY_CONFIRMED → LIVE_VERIFIED → SUCCESS_RECORDED

封存已完成才可 PREPARED；每一步保存相同 key、baseline generation、candidate ZIP、fence。successfulPointer 只在最後一個 CAS 中更動，並同時寫 SuccessRecord、前代資訊與清除 activeTransaction。

| 情境／狀態 | successfulPointer | 下一步／停止條件 |
| --- | --- | --- |
| archive／receipt／來源驗證失敗 | 不動 | 尚未送 Pages，保留 failure 證據；禁止出現可用候選索引 |
| PREPARED，尚未送出 | 不動 | 送出前再驗 CAS／fence／live；worker 中斷時不得靠猜測已／未送出 |
| DEPLOY_REQUESTED | 不動 | 先持久記 dispatch intent，再做一次 POST；記錄 response id 後查精確 Pages status |
| Pages status＝succeed | 不動 | 僅進 DEPLOY_CONFIRMED；不能直接成功 |
| 明確 terminal failure，且舊站全檔仍一致 | 不動 | FAILED_SAFE；設停止／保留紀錄；人工確認後才能釋放發布預約或准許下一次 |
| failure 但站點不一致／讀不到 | 不動 | UNKNOWN／HALTED；failure 不證明網站沒換 |
| workflow timeout／取消／runner 消失 | 不動 | UNKNOWN；不能假設 cancel 已終止平台部署，不自動重送或 rollback |
| POST 已可能送出，但 response／deployment ID 遺失 | 不動 | UNKNOWN；按既有 operation／artifact／run 證據查核，無法唯一辨識就人工處理 |
| API 404／新 status 字串／403／429／斷線 | 不動 | UNKNOWN 或明確拒絕；停止；404 不代表「從未部署」 |
| API succeed，HTTPS 仍舊／混版 | 不動 | 有限唯讀驗證後 HALTED；不接受單個首頁／manifest 成功 |
| API succeed＋線上所有檔案符合候選 | 最後 CAS 前仍不動 | LIVE_VERIFIED；記證據後再重新驗一次 state／API／live 再 finalize |
| 網站已換，成功 pointer 尚未寫入就中斷 | 保留前版，active 未解決 | 人工啟動 reconcile；若完整證據與版本唯一對應，可提出 finalize-existing-no-deploy 計畫，經核准後只補記，不能再部署 |
| final CAS conflict | 不動或已有別的核准紀錄 | HALTED；不可把舊候選 rebase 到新 baseline |
| final CAS response 遺失 | 查 state 再判定 | 若同 key／SuccessRecord 已完成，回報已有成功；不新增 generation、不再部署 |
| successful pointer 已新，但 live 被外部改版 | 不回退指標 | HALTED；記漂移，人工選擇承認、修復或回復 |
| GitHub state 不可寫 | 不動；active 預約仍會阻擋 | 當次立即停止；不得只因本機顯示完成就當正式成功 |

Pages API 有自己的 status 值，例如 succeed；adapter 必須保留 raw status，按固定版本允許清單正規化為 pending／success／failure／unknown。未識別字串 fail closed，不能使用「不是 failed 就 success」。

### 7.1 逾時與有限查核預算

提議未來 publish job timeout 15 分鐘，transport 自己在 9 分鐘內停止輪詢，留時間記 UNKNOWN；不得沿用目前 8 分鐘 job 卻套 10 分鐘 action 預設。Pages 平台仍可能在 10 分鐘自行逾時，worker 提早超時不能推定平台終止。

- Pages status：GET 每 10 秒起、上限 30 秒，總 wall-clock 最多 9 分鐘、最多 40 次；任一不確定結果不重送 create。
- live verification：另有最多 4 分鐘 deadline，至少兩輪完整驗證，間隔約 15 秒；每 request 最多 15 秒，總請求量受檔案 inventory 限制。
- GitHub 403／429：停止本 worker，保存 retry-after／rate-limit reset 供人工判讀；不換 token／endpoint 繞過。
- 金融來源 403／429 保持原先終止政策；與 GitHub 狀態 GET 分開，不引入無限重試。
- 每次完整發布預估 GitHub API <100 requests，遠低於 GITHUB_TOKEN 一般每 repo 每小時 1,000 的 primary rate limit；其他 workflow 共用與 secondary limit 仍需處理。

以上為下一階段規格，沒有在本輪新增計時或排程。

## 8. 線上驗證的明確定義

每輪驗證依序讀 manifest M1 → index／所有 JS／CSS／market 等檔案 → manifest M2；M1 與 M2 的 bytes／SHA 均須等於 ZIP 內 manifest，所有檔案均與 ZIP inventory 相同。兩輪皆成功才可 LIVE_VERIFIED。

- HTTPS 同源、固定專案 base path；禁止跨 origin redirect、目錄 traversal 或用別站回應代替。
- 使用 no-cache／no-store 與唯一 query 避免快取誤判；以解碼傳輸後的 response body 核對原檔 bytes。
- 保存 URL path、狀態、SHA、bytes、時間與必要 cache headers；不保存 Authorization、Cookie／Set-Cookie 等敏感資料。
- .nojekyll 是平台控制檔，不是可公開驗證檔：在 ZIP 與上傳內容驗證，線上清單明確記排除理由，不強求 HTTP 200。
- HTTP 200／首頁顯示新日期／workflow success／單一 manifest 正確都不足以成功。
- 即使 manifest 與 market 同時錯成另一版，與核准 ZIP 的預期 SHA 不一致也須拒絕。
- 逐檔驗證是觀測時點與測試視角的證據，不保證世界各 CDN 節點永久一致；固定 reader 的 SHA 驗證讓遇到混版的使用者拒絕錯版資料並保留錯誤提示。
- 每次 baseline 載入與 finalize 前重新比對，降低驗證後遭外部發布的窗口；可靠性仍依賴單一發布者，不宣稱分散式原子性。
- finalize 使用的最後一輪完整 live 證據建議不得早於 60 秒，且持久 activeTransaction／fence 仍相同；超時重做唯讀驗證，不重新部署。
- 第一次新 seed 上線另要求完整 Chromium／iPhone Safari 驗收；每日資料更新則保留載入、搜尋、上市櫃切換、熱力圖等離線 smoke，不每日重建前端。

## 9. 故障停止、人工確認與完整版本回復

### 9.1 預設事故程序

1. 保留最後成功 pointer、前後完整 ZIP、來源狀態、receipt、operation、deployment／run／attempt 證據。
2. 持久化 halted 或保留未解 activeTransaction；下一個 worker 一開始即停止，不能以重新 dispatch 清除事故。
3. 產生唯讀 incident report：已知 API 狀態、實際 live matches previous／candidate／mixed／unknown、缺失證據與可採取的具體選項。
4. 如果 state API 故障無法記 halted，原 activeTransaction 仍為封鎖依據；若完全未有預約，不得曾送 Pages。
5. GitHub summary／artifact 為診斷輸出，不等於主動通知。未獲核准不新增 LINE／email／issue comment；沒有獨立監測前，不能保證停機後使用者立刻收到提醒。

### 9.2 人工可選操作

| 操作 | 前置核對 | 會不會部署 |
| --- | --- | --- |
| abandon-pre-deploy | 明確證明尚未開始 Pages、原 worker 已終止、舊站仍一致 | 不會 |
| close-failed-safe | 精確部署已 terminal、無在途寫者、舊站兩輪完整相同 | 不會 |
| finalize-existing-no-deploy | Pages succeed、live＝候選全檔、archive／來源／核准完整、預期 state／fence 相符 | 不會；只補記真正完成版本 |
| restore-verified-version | 下面的完整回復規則、單次 owner 核准 | **會**；因此必須獨立核准 |
| accept-external-change | 另做完整匯入與來源驗證 | 不可直接手改 pointer 承認未知站點 |

reconcile 預設唯讀，只提出可審核計畫；不會自動 finalize、清鎖、重送、回復或解停。

### 9.3 restore_verified_version 契約

輸入：priorReceipt、priorSeed、expectedCurrent（state head＋generation＋ZIP＋active fence）、單次 authorization。

- 核准內容需綁定 operation、目標完整 ZIP SHA、目標 seed／receipt SHA、預期當前 state／觀測 live、理由、有效期限與操作者；普通確認字串不能自行構成權限。
- 先確認所有舊 worker 已終止，已知 Pages 部署 terminal，沒有不確定的在途請求；UNKNOWN 未釐清時不能用另一個部署覆蓋它。
- 使用目標版本原完整 ZIP、原 seed／pin／政策與來源包，不重新 build、不只換 market／JSON。
- 歷史 CandidateReceipt 的原 baseline binding 保留；另建 restore operation envelope 綁定本次 expectedCurrent 與核准，不修改舊 receipt 來假裝它出自新的 baseline。
- 驗證當前授權相容性：若原版本含目前禁止公開內容，回復要停止，除非 owner 對具體政策變更另有明確核准且有合法依據。
- 回復也經同一 archive／CAS／單一發布協調器、Pages API、兩輪全檔 HTTPS 與 finalize；禁止直接呼叫本機 daily_state.restore() 充作網站回復。
- 成功回復產生新的 generation g+1，指向舊 ZIP，保存 rollbackOf／原先 generation；不把 generation 倒退，也不 rewrite 成功歷史。
- 回復時 pointer 可成功移到舊資料日期，須明確記 operation=manual-restore；之後每日採集仍從這個真實成功版本出發。
- 回復失敗／逾時仍 HALTED，不無限切換版本，不撤站。

本階段與下一個離線實作階段均沒有自動回復權限。

## 10. 固定前端、公式與正式網站的保護

| 保護對象 | 必須成立的規則 |
| --- | --- |
| 研究／策略公式 | pipeline/research.py、pipeline/release_check.py、frontend/src/logic.js／research.js 及相關 schema／凍結範圍，以核准 commit 檔案 SHA inventory 驗證；本功能不得修改公式／放寬 gate |
| 固定前端 | 核准精確 seed ZIP＋pin＋static inventory；每日 package 中 HTML／JS／CSS 全部 bytes 相同；變更一 byte 即拒絕 |
| 每日允許差異 | market.json、release-manifest.json；receipt、來源包與 state 在網站外保存 |
| 權限旗標 | config/daily-release.json 的三個授權旗標維持 false；正式控制另設且預設拒絕 |
| main 與舊正式站 | 研究／離線階段沒有寫入；現有首次 release workflow 不觸發；正式整合需明確核准 |
| 資料範圍 | observation-only、未還原價；MA／突破／信用／T86／還原價／回測／intraday／連續法人訊號仍停用 |
| 來源／門檻 | 沿用 95% 最低覆蓋、最多下降 2 百分點、母體變動最多 5%、名單最多 7 日及同日修訂待審規則；不藉儲存功能調參 |
| 供應鏈 | 固定批准 code SHA／dependency lock／第三方 action commit；持有寫權限 job 不執行候選包內程式 |
| 手動入口 | 不能提供不帶 expectedCurrent／seed／receipt 的直接 deploy 或「force publish」捷徑 |

不能宣稱固定 source code 就等於固定 frontend binary；保護核心是實際部署 ZIP 的靜態 bytes。公式原始檔 hash 則用來限制未來資料 processor 的行為變更。

## 11. 風險清單與關閉條件

| ID／優先 | 風險 | 控制與關閉條件 |
| --- | --- | --- |
| R01／P0 | 來源暫存成功後消失，無法建立下一日 baseline | 在 temporary directory 清除前輸出完整自足採集包；故障注入驗證其與 receipt 同一世代 |
| R02／P0 | 原正式 ZIP 10/21 09:17 到期 | 獨立核准後依原 SHA 移存；到期後只能用可信原副本，不能重建冒充 |
| R03／P0 | Genesis 來源材料與已部署包不對應 | 原版 projection／source identity／全檔 HTTPS 全鏈驗證，不足就停止 |
| R04／P0 | Pages 已變但 pointer 沒變 | 持久 activeTransaction、UNKNOWN 封鎖、人工 reconcile；零盲目重送 |
| R05／P0 | 舊 pages-release 與新入口互相覆蓋 | 所有 Pages writers 經同 coordinator；核准整合前不能新增正式每日發布 |
| R06／P0 | branch／Release 只有慣例，沒有保護 | 初始化前驗 ruleset／immutable；保護與現有 GITHUB_TOKEN 相容，不加未准許 Secrets |
| R07／P0 | 狀態寫入後 lost response／CAS 衝突造成重複成功 | 一父 commit＋non-force、key／generation／fence；讀回已完成結果；並行測試 |
| R08／P1 | 完整來源包公開了未核准資料／個人欄位 | input closure＋來源政策；只保留核准解析快照，不擴大原始公司 API body 公開 |
| R09／P1 | 歷史增長／全量重複保存／Git 膨脹 | 大檔不進 state；實測壓縮量、1／5 GiB 自設預算、人工保留政策 |
| R10／P1 | 同日修訂、日曆不足、來源延遲被當新行情 | 保留既有 gate；完成 TWSE／TPEx、跨年／臨時停市規格後才考慮 schedule |
| R11／P1 | 新前端未核准或每日 rebuild 偷換 UI | seed ZIP 精確核准＋靜態 bytes 比對；新 seed 一次性 Safari 驗收 |
| R12／P1 | 政策變更導致舊包不能回復 | 原政策保存＋當前授權相容審核；不能自動 bypass |
| R13／P1 | workflow／artifact／deployment 紀錄到期 | 成功必要證據在 state／Release 長期保存，URL 只是補充，不是唯一證據 |
| R14／P1 | 監測未啟用，故障後無人知道 | 顯示既有行情日期，事故 report；主動監測／原生通知另行核准 |
| R15／P2 | GitHub 帳號／repo／管理者刪除，兩儲存層一起消失 | 同平台不算獨立備份；另提人工下載可攜匯出，未核准不自動複製到其他服務 |

P0 為正式上線前阻擋項；不表示本輪有執行上線。容量、Safari、日曆與通知未驗證前不能宣稱已完成無人值守能力。

## 12. 分階段實作與核准邊界

| 階段提案 | 工作 | 可以驗收的成果 | 禁止跨越 |
| --- | --- | --- | --- |
| 4C-2B-1 離線契約 | 完整採集出口、receipt v2、archive／state／Pages interfaces、legacy importer plan | 完整 fixtures、自足包／hash 驗證、baseline loader；預設無網路／遠端寫入 | 不建遠端 Release／state，不部署，不改 main／Secrets／schedule |
| 4C-2B-2 故障協調 | Git CAS adapter、狀態機、只讀 reconcile、mock Pages transport | 並行 CAS、每個中斷點、unknown／lost response／rollback plan tests | 不因測試增加正式寫權限或進行真實 Pages |
| 4C-2C 儲存初始化 | 另行核准 ruleset／Release immutability、genesis 原包移存、state 初始化 | 從持久保存完整載入真實 g0；零 Pages 寫入 | GitHub Release 凍結本身也是遠端寫入，不能由離線任務順便完成 |
| 4C-2D 首次受控發布 | 另核准新 seed／固定 frontend、真實新交易日候選、單次 Pages 與整合 workflow | 部署 API／live／SuccessRecord 完整閉環；Safari 實機 | 仍不啟 schedule，不授權自動回復 |
| 4C-2E 人工回復演練 | 明確指定版本及 expectedCurrent，核准單次回復 | 原完整 ZIP／原 seed、g+1、全檔一致、來源狀態可用 | 不推廣為自動 rollback |
| 4C-3 自動化評估 | 另審交易日曆、slots／延遲／節流、容量與通知 | schedule 啟用提案、人工成功一輪、無人值守監測證據 | 未再核准前 schedule 仍關閉 |

現有 18:30 主 slot、19:30／20:30 備援、21:30 後不補發布等僅保留原提案，不在本期啟用或更動。原定 target 必須跨午夜保留，與實際開始日期分開。

## 13. 可直接交給下一階段 Codex 的任務規格

以下任務**僅在使用者核准對應階段後開始**。本輪到此設計文件即停止。

### 13.1 固定起點與作業規則

- Repository：0857ken/tw-market-scanner；先重讀 PR #2 最新 head。預期起點 db5e1f41b2637856bd3d48cfa49d0f314a6e9808。
- 若 head 有變，先做增量差異核對，不 reset／force push，不用過時檔案覆蓋。以既有 feature／Draft PR 作延伸；遠端 commit／push／PR 更新仍依當次核准範圍。
- 必讀 docs/STAGE4C2_INTERFACE_DESIGN.md、docs/STAGE4C1_OPERATIONS.md、docs/STAGE4C1B_REVIEW.md、現有政策、candidate／package／state、全部 workflows 與測試。
- 預設只實作 4C-2B-1／2 的離線模式。不得 merge、main 寫入、Pages、schedule、Secrets、付費、GitHub Release 發布或正式 state 初始化。
- 不新增金融來源測試請求；fixtures 用於邏輯驗證，清楚標示不是新交易日正式成功。
- 保留原候選 false 權限旗標及既有 204 個回歸項目的行為；不更動研究公式／UI。不得「為通過測試」弱化 workflow audit。

### 13.2 增量模組與責任

以下為建議新名稱，可依 repo 慣例微調，但責任契約不可刪除：

| 任務 | 建議位置 | 必要交付 |
| --- | --- | --- |
| T1 採集狀態出口 | 延伸 pipeline/daily_release.py、package_daily.py | success candidate 輸出完整可恢復 state／inventory；失敗不公開半包；baseline 全檔不變；不重寫 run_daily |
| T2 格式與純驗證 | pipeline/publication_contract.py | receipt v2／package index／SuccessRecord／legacy schema；安全解包；hash graph 無循環 |
| T3 baseline loader | pipeline/verified_baseline.py | load_verified_baseline；legacy g0 importer 的唯讀 plan；只從 verified success 取 input |
| T4 持久 archive 介面 | pipeline/release_archive.py | fake／filesystem backend＋未啟用的 GitHub transport；精確 asset IDs／SHA，不用 latest；write capability 預設拒絕 |
| T5 state adapter | pipeline/persistent_state.py | StateStore.read／cas_transition；Git 單父 child＋non-force；atomic transaction＋pointer；與 local daily_state 演練名稱／範圍區分 |
| T6 協調器 | pipeline/publication_coordinator.py | prepare／record_request／record_status／verify／finalize；operation／fence／停止邏輯；無自動 rollback |
| T7 Pages transport | pipeline/pages_transport.py | Fake Pages；read-only status；預設拒絕真實 create；未來 create 一次＋即時 persist callback 的契約 |
| T8 live verifier | pipeline/live_verification.py | manifest 前後夾讀、全檔兩輪、受限 HTTPS、證據輸出、.nojekyll 明確排除 |
| T9 人工處置 | pipeline/reconcile_publication.py | 預設唯讀 report／restore plan；列 expectedCurrent／缺證，不清鎖不部署 |
| T10 回歸與文件 | tests、docs、必要 CI 測試入口 | 測試矩陣、failure evidence、容量實測格式、操作手冊、未完成／未授權清單 |

production transport 即使已寫入原始碼，也必須在無 capability／非核准 ref 時於**任何 mutation 前**拒絕；旗標或 CLI 字串不能自行構成授權。若要加入有寫權限的 workflow，必須另行取得 4C-2D 對精確 workflow 差異的核准。

### 13.3 函式介面契約

- load_verified_baseline(expectedPublishedZipSha256, expectedGeneration, policyContext) → VerifiedBaseline。
- prepare_candidate(VerifiedBaseline, IntendedSlot, FixedSeed) → CandidateReceiptV2＋完整 candidate closure；no-op 與 revision 不產生可發布 receipt。
- archive_candidate(CandidateClosure, archiveCapability) → ImmutableArchiveRef；未給能力必須在遠端寫入前拒絕。
- cas_transition(expectedStateHead, expectedGeneration, operationKey, fence, transition) → 新 state head；衝突必須顯式回報。
- prepare_publication(VerifiedBaseline, ImmutableArchiveRef, approval) → 持久 PREPARED transaction。
- request_pages_once(transaction, publishCapability, persistDeploymentId) → 精確 PagesDeploymentRef 或 UNKNOWN；不可自動 retry create。
- observe_pages(transaction) → pending／confirmed／failed／unknown＋raw status。
- verify_live(transaction) → LiveEvidence，不更新 successfulPointer。
- finalize_success(transaction, evidence, expectedCurrent) → 新 generation／SuccessRecord；原子寫入，無 Pages POST。
- reconcile(transaction) → 唯讀 ResolutionPlan。
- restore_verified_version(priorReceipt, priorSeed, expectedCurrent, authorization) → 經相同協調器的新 operation；沒有授權只產生 plan。

CLI 預設 dry-run／read-only，mutable operation 不得因缺參數而採用 latest／目前日期／最新 seed 或目前 state，必須要求精確 expectedCurrent。

## 14. 具體測試與驗收矩陣

既有 204 項是本輪核對的現況，不是未來可以刪減的最低數字。新增測試應驗證實際危險行為與不可變量，不以大量重複 implementation 的單元測試灌數。

| ID | 測試情境 | 必須觀察到的結果 |
| --- | --- | --- |
| B01 | 沒有 state／success／來源包／receipt／seed | baseline loader 停止；零金融請求、零 publish、零 fallback |
| B02 | latest Release 較新但 pointer 還在舊版 | 只讀 pointer；不能使用未成功版本 |
| B03 | receipt／ZIP／快照／source-state 任一 SHA 錯 | 全鏈拒絕，舊 pointer 與 baseline inventory 完全不變 |
| B04 | run ID 相同但 attempt 不同／processor SHA 不同 | 拒絕跨 attempt／workflow／code 混用 |
| B05 | 獨立全新目錄，只有封存包、無 checkout data／cache | 可恢復原 input closure，公開投影與原版相同；不能偷偷讀本機 fixture |
| B06 | legacy ZIP 正確但來源無法對應 | 只產生阻擋報告，無 genesis 寫入／部署 |
| B07 | parsed JSON file SHA 與 response digest 混用 | schema／驗證拒絕；不宣稱保存不存在的 HTTP body |
| B08 | 來源狀態寫到一半或 temporary directory 清除時中斷 | 無半成品成功出口；成功出口可完整獨立恢復 |
| A01 | Release asset 只有部分上傳／starter／digest 不符 | 不產生可用 ImmutableArchiveRef；不動 pointer |
| A02 | 同名 asset 已存在但 bytes 不同 | 不 overwrite／delete-and-replace，停止並隔離 |
| A03 | Release immutable:false 或 tag／ID 不一致 | 拒絕正式封存引用 |
| A04 | ZIP traversal、symlink、duplicate、zip bomb、超限 | 在解包／寫出前拒絕，不逃逸暫存目錄 |
| A05 | 移除 unapproved 原始聯絡欄位後導致 input closure 缺失 | 阻擋；不能靜默宣稱仍可重現 |
| C01 | 兩個不同 operation 同時由同一 H 產生不同 single-parent child | 遠端模型／本機 bare Git 實證僅一個 fast-forward 成功，另一個衝突；完全相同 C 則另驗冪等 |
| C02 | force:false、parent 不等於讀取 H、試圖 merge／rewind | adapter 拒絕；不能換成 force 重試 |
| C03 | CAS 寫成功但 response 遺失 | 讀回辨識相同 commit／key；不新增第二筆 success／generation |
| C04 | 已有 activeTransaction 或 control.halted | 新 publish 零 POST；過 lease 時間也不自動解鎖 |
| C05 | 準備後另一 worker 改 state／成功版本 | 部署前拒絕舊 candidate；部署後進 UNKNOWN |
| P01 | 正常 Pages succeed＋全檔兩輪符合 | 每 operation create 恰一次；只有最後 CAS 更新 pointer，generation＋1 |
| P02 | create 明確拒絕，live＝舊版 | FAILED_SAFE，舊 pointer 保留，人工解停前零再發布 |
| P03 | create timeout／5xx／response lost／ID lost | UNKNOWN；create 呼叫次數不因 resume 增加 |
| P04 | workflow 取消／job timeout／runner killed | active 預約保留、成功指標不動、下一 worker 被封鎖 |
| P05 | status 404／403／429／未知字串 | 不映射為成功或未部署，不盲重送／繞過 |
| P06 | API succeed 但 live＝舊版／混版／404 | 不更新 pointer，有限驗證後 HALTED |
| P07 | live 換到候選後，寫 success 前 crash | 新 worker 只出 reconcile plan；未核准不 deploy／finalize |
| P08 | 已記 success 後 crash／相同 operation rerun | 回傳既有 success，不重送、不再增 generation |
| P09 | success CAS conflict | 不自動 rebase／改 expectedCurrent；HALTED |
| P10 | 原 pages-release 入口與每日入口同時觸發 | 只有遵守同預約的單一 writer 可達 POST；舊繞過路徑測試必須失敗 |
| L01 | manifest 在取檔前後改版 | 夾讀拒絕，舊指標不動 |
| L02 | manifest／market 一起換錯另一版 | 與 candidate ZIP SHA inventory 不符而拒絕 |
| L03 | JS／CSS／index 任一 byte 改變，frontendId 相同 | 拒絕，不能只信 ID |
| L04 | 跨源 redirect、TLS 錯誤、超時、異常大小 | 拒絕，不降低 HTTPS 或忽略 hash |
| L05 | .nojekyll 線上不提供 | 僅按明確控制檔例外處理；其餘公開檔必驗，不能概括 skip missing |
| R01 | 無 authorization／過期／expectedCurrent 不符 | restore 只出 plan 或拒絕，零 Pages POST／pointer mutation |
| R02 | 舊 seed 與最新 seed 不同 | 必須用舊 seed；相同 ID／最新 pin 不可替代 |
| R03 | 舊包損壞／現政策禁止／來源缺失 | 拒絕 restore，不能降 gate |
| R04 | 已核准 restore 成功 | 原 ZIP bytes、原 UI／資料全檔相同，新 generation＋1，保留 rollbackOf |
| R05 | UNKNOWN 尚有在途 deployment，要求回復 | 停止，不以新 deploy 蓋過未知請求 |
| G01 | 同日相同／同日修訂／日期倒退／市場不一致 | 原 gate 行為保留：no-op／待審／停止，無重複成功 |
| G02 | 延遲跨午夜、週末、已知／未知休市、臨時停市、新年度 | 原 target 不變；無日曆證據不猜，保留前成功 |
| G03 | 低覆蓋／名單異常／來源 403／429／授權變更 | 沿用既有停止；不 fallback、不換 source 繞過 |
| G04 | 超儲存預算／未知剩餘容量 | 按明確容量策略停封存／發布，不啟用付費或截斷歷史 |
| W01 | 嘗試在 PR 加 schedule／Pages write／內容寫權限 | workflow audit 拒絕；原首次核准 workflow 僅允許既有例外 |
| W02 | 下載包含 executable／workflow／新公式 | 不執行；inventory／固定 code hash 阻擋 |
| W03 | 任一離線測試 | mutation spy 證明零真實 GitHub／Pages／金融 endpoint mutation；無 Secrets 需求 |

### 14.1 驗收層級

**離線實作完成：**

- 固定 commit 的原 Python／Node／三組 Chromium 回歸全過，新增矩陣全過，沒有以 skip 掩蓋 P0。
- Git CAS 競爭以兩個獨立 process／bare Git 實證，不只函式 mock。
- 在每個狀態轉換「前／後」及外部 API「送出前／已接受但失去回應」注入中斷。
- 每次故障都比對 successfulPointer、完整 baseline inventory、create 次數、generation 與 active fence。
- 產出可機器讀的 matrix report，區分 PASS、BLOCKED、NOT_AUTHORIZED；真實 Pages／Safari 沒跑不能列 PASS。
- 不新建／修改正式儲存、部署與排程。

**儲存初始化完成（另准）：**

- 原 ZIP SHA 與即時全檔 HTTPS 對應，legacy 採集閉包已證明，immutable archive 可下載驗證。
- 全新無 cache 目錄僅靠持久版本恢復成功，g0／seed／政策可讀；正式網站完全未部署。
- ruleset／GITHUB_TOKEN append 相容，force／delete 拒絕證據；若不能驗證，列 BLOCKED。

**單次正式發布完成（另准）：**

- 真實新交易日資料，原定 target、來源與 gate 完整；核准精確 seed／code／receipt／ZIP。
- Pages API 成功＋兩輪全公開檔 SHA＋單一 SuccessRecord／generation。
- 網站日期／搜尋／上市櫃／產業／熱力圖／自選持久化／手機 safe-area，含 iPhone Safari 實機。
- 透過最後成功 pointer 重新讀出新採集 baseline，獨立新目錄可恢復。
- schedule／自動 rollback 仍關閉。

未通過以上層級，交付只能稱「離線實作」或「儲存初始化」，不能稱每日無人值守已完成。

## 15. 研究來源與證據連結

### Repository 證據（固定版本）

- [Draft PR #2](https://github.com/0857ken/tw-market-scanner/pull/2)
- [指定 commit](https://github.com/0857ken/tw-market-scanner/commit/db5e1f41b2637856bd3d48cfa49d0f314a6e9808)
- [原介面文件](https://github.com/0857ken/tw-market-scanner/blob/db5e1f41b2637856bd3d48cfa49d0f314a6e9808/docs/STAGE4C2_INTERFACE_DESIGN.md)
- [運作說明](https://github.com/0857ken/tw-market-scanner/blob/db5e1f41b2637856bd3d48cfa49d0f314a6e9808/docs/STAGE4C1_OPERATIONS.md)
- [candidate／bundle 實作](https://github.com/0857ken/tw-market-scanner/blob/db5e1f41b2637856bd3d48cfa49d0f314a6e9808/pipeline/daily_release.py)
- [本機 state 演練](https://github.com/0857ken/tw-market-scanner/blob/db5e1f41b2637856bd3d48cfa49d0f314a6e9808/pipeline/daily_state.py)
- [首次 Pages workflow](https://github.com/0857ken/tw-market-scanner/blob/db5e1f41b2637856bd3d48cfa49d0f314a6e9808/.github/workflows/pages-release.yml)
- [Push CI](https://github.com/0857ken/tw-market-scanner/actions/runs/38938248745)
- [PR CI](https://github.com/0857ken/tw-market-scanner/actions/runs/38938256502)
- [原正式 Pages Run](https://github.com/0857ken/tw-market-scanner/actions/runs/38496725153)
- [原正式 ZIP 所屬 CI](https://github.com/0857ken/tw-market-scanner/actions/runs/38494657009)

### GitHub 官方文件（2026-10-17 查證）

| 主題 | 官方連結 | 本文件用途 |
| --- | --- | --- |
| Release assets 限制 | [官方文件](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) | 1,000 assets／小於 2 GiB／總量與頻寬說明 |
| Immutable releases | [官方文件](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases) | tag／asset 保護與限制 |
| 啟用 immutability | [官方文件](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes) | 設定僅對未來 Releases 生效 |
| Actions billing | [官方文件](https://docs.github.com/en/billing/concepts/product-billing/github-actions) | 標準 public runner 免費、Free 儲存與 larger runner 區別 |
| Pages limits | [官方文件](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) | 成品／頻寬／部署 timeout |
| Git references API | [官方文件](https://docs.github.com/en/rest/git/refs) | force:false fast-forward；沒有 expected_sha body 參數 |
| Git database guide | [官方文件](https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database) | 以讀取 commit 為 parent 建立新 commit |
| Pages REST API | [官方文件](https://docs.github.com/en/rest/pages/pages) | create 的 artifact／build version／OIDC、精確部署 ID／status |
| Rulesets | [官方文件](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) | public Free 可用 branch／tag 規則；bypass 不等同自動可用 |
| Release asset API | [官方文件](https://docs.github.com/en/rest/releases/assets) | asset digest、starter、同名衝突 |
| REST rate limits | [官方文件](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) | GITHUB_TOKEN 1,000／小時／repo、403／429 |
| Artifact／run retention | [官方文件](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization) | public 1～90 日，不能視為永久證據 |
| Git 大檔限制 | [官方文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) | 50 MiB 警告、100 MiB 阻擋與 Git 歷史維護成本 |
| 官方 deploy-pages action | [官方文件](https://github.com/actions/deploy-pages/blob/main/action.yml) | page_url output、預設 timeout／取消行為；實作仍須固定精確版本 |

平台文件描述的是限制與能力；本文件的容量門檻、保留期、兩輪驗證、CAS 組合與階段命名是設計建議。任何費用、權限、真實 source／Pages 能力於實作核准前均需重新確認當時現況。

---

**本次交付到設計為止。等待使用者核准下一個具體階段後，才開始程式修改或遠端操作。**
