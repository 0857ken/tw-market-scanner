# PR #3 手機優化｜正式發布前 Gate 與回復準備（2026-10-25）

> **結論：UI／Safari UAT 已通過；Production Publish = NO-GO。**
> 此文件僅為發布前審核證據；不是部署指令、批准憑證或排程觸發器。
> 本文件作為獨立文件專用 Draft PR 提交，不更動 PR #2／#3 原始候選、正式網站、每日更新或研究邏輯。

## 1. 固定證據與來源

| 項目 | 事實／識別碼 |
|---|---|
| Repository | `0857ken/tw-market-scanner` |
| 原正式 main 基準 | `d1a700ffa2c5af42ca1a10ea90877bd3cce7e67a` |
| PR #3，手機 UI | Draft，HEAD `f0ea87bdba72569cd2e0ba8f0ebf05e2d6cdb5c3` |
| PR #2，每日更新 | Draft，HEAD `93199de5b76b9db8c3a12ed78c4242967636cf9a` |
| PR #3 CI | Push `39748332666`／PR `39748385578`，均 `completed/success` |
| PR #3 工作成果 | Python 57、Node 78、Chromium 一般 23 + RC 8 = 166；兩份 CI PASS |
| PR #3 原始 candidate artifact | `12413090978`，SHA256 `259a17b10e088a0652f8e9a2684ac632caf06f51c2cc9006c9395bacc972e04e` |
| Preview Repository | `0857ken/tw-market-scanner-pr3-preview`，HEAD `bbf924ed5ef82a7d3e094819fcd96e01a0c29834` |
| Preview deploy | Run `40090224997` 已成功，網址 https://0857ken.github.io/tw-market-scanner-pr3-preview/ |
| 候選行情日／市場資料 | `2026-10-13`；market.json SHA256 `bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9` |
| Safari UAT | 使用者於 2026-10-25 回報六項檢查 6/6 PASS；非第三方設備遠端測試 |
| 正式網站 | https://0857ken.github.io/tw-market-scanner/ （未發布 PR #3） |

GitHub Actions `40090224997` 的 verify job 顯示原始候選包 8 檔逐 byte 驗證通過、未重新 build；deploy job 顯示 Pages 發布成功。發布前仍須對**當下**公開 HTTPS 逐檔再驗證一次，不以舊 logs 取代即時檢查。

## 2. PR #2／#3 交叉變更實際查核

GitHub PR diff 顯示兩分支都修改 `frontend/src/Scanner.jsx`，且在原 main 的以下區域交疊：

1. **約 433–460 行：行情載入與 UI 狀態**。PR #2 導入 `fetchDailyMarket` 與 `VITE_DAILY_FRONTEND_ID` 路徑；PR #3 在相鄰區塊加入搜尋、鍵盤、抽屜與焦點控制。
2. **約 467–523 行：固定版本提示／頁面 JSX**。PR #2 支援每日版本與資料 hash 顯示；PR #3 修改此區域的前端結構／互動。

這是**實際重疊的修訂範圍**，尚未執行兩分支完整三方合併與回歸，不能直接宣稱「有必然 Git conflict」，也不能宣稱「已整合相容」。

後續整合必須另開隔離候選，保留 PR #2 新資料驗證路徑、PR #3 的 Safari 行為；進行兩版本間的三方合併、交叉資料狀態與手機 E2E，再經獨立 owner 審核。不要就地重寫 PR #2／PR #3 的已核准 HEAD。

## 3. 現有發布基礎阻擋

- `.github/workflows/pages-release.yml` 仍是首次 `4b1-rc1` 固定原始 ZIP、舊 artifact `11862513391` 的發布流程。**不可重跑當作 PR #3 上線**；舊 Actions artifact 的到期時間為 2026-10-21 09:17:40 台北時間。
- `.github/workflows/deploy.yml` 只產生候選 artifact，不具正式 Pages 部署權限；`.github/workflows/update-data.yml` 未啟用 schedule。
- Stage 4C-2C 的 GitHub Releases（檢查時 0 個）及 `scanner-release-state` g0（檢查時不存在）尚未正式初始化；Ruleset `25306665` 仍 active。不能假裝 immutable archive／successfulPointer 已存在。
- Stage 4C-2B 留下的 P10 阻擋：舊 `pages-release.yml` 尚未接入單一發布者協調。若將來啟用每日資料更新，必須先解決 writer 互斥與 UNKNOWN 部署對帳。
- 原始 4b1-rc1 ZIP 及可攜閉包已有離線備份證據，**但正式回復仍未依遠端單一成功指標做 clean-room 演練**；不得將「有原始 ZIP」寫成「已有自動 rollback」。
- 預覽站與正式站使用 `0857ken.github.io` 相同 origin（不同 path），可能共用 `localStorage` 關注清單。Safari 已通過測試，不代表資料隔離；手動驗收應用私密瀏覽或備份關注名單。

## 4. 下一次正式發布前的強制 Gate（不得跳過）

- [x] PR #3 固定 SHA，工程 CI 與來源檔案審核。
- [x] 獨立預覽 HTTPS 部署成功。
- [x] Owner iPhone Safari 六項 UAT 通過。
- [ ] 定義且審核**單次人工發布 authority**：精確候選版本、允許的工作流與操作身分、只針對這一次的授權，不可用任意 boolean 或未驗證文字當授權。
- [ ] 複核原始候選 bytes、market SHA 與當下預覽網站兩輪逐檔 HTTPS；再核對正式站仍是核准舊版。
- [ ] 完成原正式站的**持久備份讀回**、精確發布證據、回復演練與遇到 UNKNOWN 狀態的停止條件。
- [ ] 修復／關閉舊發布入口繞過問題，完成 PR #2 與 PR #3 的整合先後決策，避免交錯部署者覆寫成功版。
- [ ] 在隔離候選驗證與 PR #2 同時存在時的版本載入、資料完整性、手機／Safari 操作，不改行情或研究公式。
- [ ] 發布流程／回復流程與權限經獨立審核，使用 GitHub Free 標準資源，額外費用 NT$0；任何權限、成本不明立即停止。
- [ ] Owner **另外明確批准**合併 `main` 與正式 Pages 部署，兩項核准分開記錄。
- [ ] 正式部署後即時兩輪 HTTPS SHA 驗收、使用者 Safari smoke test 與故障回復判定。

## 5. 目前決策與可觀看成果

**Production NO-GO；僅授權文件審查與 Draft PR。** 不 merge main、不觸發正式 Pages、不啟用 daily schedule、不改 PR #2／PR #3、不加 PAT／Secrets、不新建付費服務或擴權。

使用者已能立即查看**真實已上線的 PR #3 獨立預覽成果**：
https://0857ken.github.io/tw-market-scanner-pr3-preview/

正式網站仍為：
https://0857ken.github.io/tw-market-scanner/

此文件完成後的下一關是受控發布機制與 clean-room 回復的工程實作／審核，不是重新做 Safari UAT。
