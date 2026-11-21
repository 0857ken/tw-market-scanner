# Stage 4C-2B：持久版本與安全發布的離線實作

主要規格為同目錄 STAGE4C2A_ARCHITECTURE_AND_CODEX_SPEC.md；從 db5e1f41b2637856bd3d48cfa49d0f314a6e9808 增量延伸既有 Draft PR #2。本期只完成離線介接、格式、協調與故障驗證；沒有初始化遠端 Releases／scanner-release-state、Pages、main、schedule、Secrets 或其他 repo。

## 實作與界線

| 規格 | 實作 | 說明 |
| --- | --- | --- |
| T1 | acquisition_state.py、daily_release.py | 成功 candidate 在 temporary directory 清除前輸出自足 acquisition-state.zip；包含所有已核准解析快照、完整內部 market／source-state、必要品質 metadata 與 inventory；失敗不公開半包。 |
| T2 | publication_contract.py、candidate_package.py | Receipt v2、完整 policy／parser／schema／code／slot／baseline／run attempt／seed／site／來源綁定。雜湊圖無自我依賴。保留原 false 權限，不把候選當正式成功。 |
| T3 | verified_baseline.py | 固定 state head → successfulPointer → SuccessRecord 鏈 → 精確 Release／asset ID → 完整閉包 → 原 projection 重現 → 重新全檔 live 核對；不存在就停止。 |
| T4 | release_archive.py、github_transport.py | filesystem 模型與 GitHub REST adapter；精確 ID、讀回、starter／digest／immutability／容量驗證；沒有 latest 選版或 clobber。 |
| T5 | persistent_state.py | 真實本機 bare Git 與 GitHub Git Database adapter；唯一 parent＝讀取 H、non-force ref update；state／事件／成功證據同一 tree／commit。 |
| T6 | publication_coordinator.py | PREPARED、先持久 dispatch intent、create 一次、記 ID、status、兩輪 live、最後 CAS。失敗／UNKNOWN 保留舊成功 pointer 及預約，不自動 rebase 或重送。 |
| T7 | pages_transport.py | Fake Pages 與未啟用的 GitHub create／exact-ID status 契約；不混用 Run／artifact／Pages IDs；保留 raw status，未知值停止。 |
| T8 | live_verification.py | manifest 前後夾讀、所有公開檔兩輪 SHA、同源 HTTPS、受限 redirect／大小／時間；.nojekyll 只作明確控制檔例外。 |
| T9 | reconcile_publication.py | 唯讀事故與回復計畫。離線單次回復經同 coordinator，保留原 receipt，產生 g+1／rollbackOf，不能只換 pointer 假裝網站已回復。 |
| T10 | test_publication.py、publication_tests.py | 真實兩 process Git 競爭、每個 state transition 前後與 Release mutation 前後中斷、API lost response、完整還原、機器可讀矩陣；原有測試保留。 |

GitHub mutator 現在固定於第一個 mutation 前拒絕。CLI 旗標、環境變數、JSON 權限或離線 approval 均不能啟用它。下一階段須對精確 authority／受保護 ref／environment 接線另行審核；本期不假裝已具備正式寫入能力。OfflineApproval 只適用所有 backend 都是 offline 的測試環境；重啟 coordinator 不繼承發布所有權，只能 reconcile，不能恢復就再送 create。

## 每日入口的實際變更

- update-data.yml 不再直接用 checkout data 做官方候選基準，改呼叫 verified_baseline CLI。必填精確 expected ZIP／generation、原定 target／slot／deadline、實際 Run／attempt；先完成 pointer／archive／live 驗證，才可能進入六來源採集。遠端 state 尚未初始化時，它會安全失敗，不抓金融來源。
- package-daily.yml 指定 source run 的精確 attempt，保留原 repo／workflow／code／成功狀態檢查。打包前重新載入同 successful baseline；有 head／generation 變化就拒絕。產出 v2 receipt、acquisition／support 包，但沒有 Release／state／Pages 寫入權限。
- 舊 package() 不帶 VerifiedBaseline 的呼叫只保留離線 rehearsal 相容性，仍為 deploymentAuthorized:false；無法通過 v2 協調器的正式候選要求。
- CI 仍為 contents:read，沒有新 workflow 或事件，沒有新增部署 action；只增加矩陣輸出，逾時由 10 調至 15 分鐘以容納故障整合測試。

所有 workflows 仍受原結構化 audit 約束，pages-release.yml 保持原始 SHA。它目前仍是舊首次發布入口，尚未納入新預約；P10 的正式多入口整合必須於 4C-2D 退役或接入後才可關閉。本期只驗證新真實 transport 保持關閉，不能宣稱已解決正式 writer 繞過問題。

## 原包保全與資料證據

原始 artifact 11862513391／Run 38494657009：413,691 bytes，ZIP SHA256 為 7621524742b25dfaa7a7216ca5f5b5006719a252966a0554ff7d0416c3262eee。原核准程式為 82b1749a2626ce30d6196a101577b8bb09273c31；公開 market SHA 為 bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9。

scripts/preserve_original_rc.py 只讀取原 ZIP 與該原 commit 的候選採集材料，不執行下載程式、不重建網站。它先驗原 manifest 全部 8 檔，再證明原觀察版 projection 位元組相同，並產出本地完整 legacy import closure／可攜包／original-rc-proof.json。原版 code inventory 逐一與現在凍結公式／parser／schema 比較；不相同即停止。

Legacy frontend inventory 標示 derived-at-import，沒有捏造當年不存在的 daily seed 核准。原 manifest 作為 original-receipt.json 原 bytes 保存。原來源只有解析快照與 response digest，明列 responseBodyArchived:false；快照 JSON 檔案 SHA 與原 response digest 分欄，不宣稱保存原 HTTP body。

輸入閉包保存現有合法的 index／margin／futures 等解析依賴，不新增該等來源請求、不重新啟用公開功能。信用、TWSE T86、未核准 history／還原資料拒絕。公司名單 parsed rows 僅允許既有公開欄位，聯絡欄位會阻擋；未知依賴不靜默排除。全部既有 raw snapshots 保留，不 prune 舊歷史。

GitHub Actions artifact 到期不再是原 ZIP 的唯一保全邊界；交付保全副本與可攜閉包。這仍不是遠端 immutable Release 已建立的證明。正式 g0 還必須取得當下 live 逐檔證據、原 Pages 精確部署證據、ruleset／token append 相容及 owner 匯入核准。

## 驗收與重現

```bash
python3 -m pip install -r requirements-dev.txt
npm ci --prefix frontend --no-audit --no-fund
python3 -m scripts.audit_workflows
npm test
npm run build --prefix frontend
node scripts/audit-built.mjs
npm run test:e2e
npm run build:rc
npm run test:rc:e2e
node scripts/audit-rc.mjs
node scripts/build-daily-seed.mjs
python3 -m scripts.daily-dry-run --output test-results/UNIQUE-4C2B-REHEARSAL
cd frontend
node node_modules/@playwright/test/cli.js test --config playwright.daily.config.js
```

npm test 執行所有原 Python 測試及新增測試，再執行原 Node 全套；輸出 test-results/stage4c2b-matrix.json。矩陣按規格 B/A/C/P/L/R/G/W 共 45 個情境列離線斷言證據，另外分列真實遠端初始化、Pages、回復、P10 正式入口與 Safari 的 BLOCKED／NOT_AUTHORIZED，不能合併計為正式 PASS。

本地環境 Python 3.12／Node 24；CI 固定 Python 3.12／Node 22。若本地瀏覽器下載受到環境限制，不更換不可信二進位或降低測試；由既有 GitHub CI 執行相同三組 Chromium。結果依實際 run／log 回報，不把未跑項目列為成功。

保全程式的唯讀使用方式（輸出路徑必須全新）：

```bash
python3 -m scripts.preserve_original_rc ORIGINAL-APPROVED.zip --output NEW-EVIDENCE-DIRECTORY
```

## 4C-2C 遠端初始化程序（等待獨立授權）

1. 固定本期核准 commit，重新驗證原 ZIP、可攜閉包、每個 policy／seed／receipt SHA 與 input closure。取原 Pages 精確部署證據；完整 live HTTPS 兩輪與原包一致，任一缺口停止。
2. 檢視並核准 repository immutability 與 scanner-release-state 規則：禁止 force／delete、線性 append、沒有可執行 workflow、不是 Pages source。核實既有 GITHUB_TOKEN 在保護規則下可 append；不自行加 PAT／Secrets 或削弱 main。
3. 對精確初始化程式與獨立 authority 接線審核；不是翻轉 daily-release.json 的三個 false 旗標，也不是讓任意 CLI confirmation 字串授權。
4. 只匯入原網站 ZIP／acquisition／support／receipt：建立 Draft Release、逐資產讀回、產生含真實 asset IDs 的 index、讀回、凍結並核對 immutable:true。任何 starter／不一致停止；不刪除重傳。
5. 以核准的 orphan bootstrap 建立 state g0，pointer／SuccessRecord／live evidence／receipt／index／approval 同一個 commit。genesis 不呼叫 Pages、不稱作新發布。
6. 在全新、無 checkout data／cache 的目錄只靠 successfulPointer 與 Release 還原，核對原公開投影、policy／seed 與當前站點。讀回 state head 與資產 SHA，交付完整證據。
7. 到此停止。舊 Pages 入口整合、新 daily seed、首次受控 Pages、Safari、正式人工回復及 schedule 分別按 4C-2D／2E／4C-3 另行核准。

## 剩餘風險

- 本期沒有真實 immutable Release、state CAS 或 Pages API 能力驗收；filesystem 模型不是 GitHub 平台 immutability 證書。
- 原首次 workflow 的 bypass 路徑未改，初始化與發布權限仍未接線；不得直接開 schedule。
- GitHub 帳號／repo 管理者刪除風險仍在，同平台兩種保存不等於獨立災難備份；可攜閉包用於人工備份與核對。
- 大型 state 初次讀取、GitHub secondary rate limits、長期資料增長及帳號共享儲存需實測；超容量停止，不自動 GC／截斷或付費。
- TPEx／跨年／臨時停市日曆、真實新交易日、Safari、主動通知仍未驗收；本期不啟用這些能力。
