# Stage 4C-1B 候選更新安全補強（本地待審查）

## 基準與操作界線

- main：`d1a700ffa2c5af42ca1a10ea90877bd3cce7e67a`。
- PR #2／feature/stage4c1-daily-update：`ef61f1fda10f662d441d008bfd3b3de35f7131e1`；實作前以 `git ls-remote` 核對兩分支及 refs/pull/2/head，完全相符。
- 只在 `/workspace/tw-market-scanner-stage4c1b` 隔離 clone 實作。未 commit、push、開 PR、merge、部署、啟 schedule、改 Secrets 或抓取真實行情。
- 原 PR 的 [CI Run #38499865297](https://github.com/0857ken/tw-market-scanner/actions/runs/38499865297) 成功由使用者確認，包含既有測試、建置、Playwright 與每日離線演練。本輪未重新透過 GitHub API 查證；不代表本輪未提交變更已獲遠端 CI 驗證，也不代表正式更新或部署成功。

## 相對原 PR #2 的變更

1. **統一候選入口**：npm 的 data／data:strict／data:candidate 均導向 daily_release，預設不抓行情；直接 run／daily CLI 在任何請求前退出。舊 run 的解析／build 函式仍供既有程式與測試匯入，不能當觀察版更新入口。
2. **取消 baseline 的多檔覆寫**：daily 只讀輸入，必須指定全新 output_dir；所有來源快照與 metadata 留在 staging，完成驗證及寫入後才以同檔案系統 rename 公開整個候選目錄。失敗只有獨立 attempt，沒有部分成功目錄。不允許 output 與 baseline、repo data 或 frontend/public 重疊。
3. **失敗證據隔離**：controlled 的輸出不可覆寫；失敗時刪除 staging 裡的成功 gate／candidate，公開的 failure 目錄不能被打包。重跑需新 run/attempt output，拒絕舊目錄發生在請求前。
4. **完整 ZIP 後才公開名稱**：先在記憶體完成並驗包，再寫入唯一 pending、flush/fsync，最後以獨占 hard-link 公開不可覆寫 ZIP。打包 ZIP 與 receipt 一起放在新目錄，完成後才公開目錄。
5. **本機鎖與 ledger**：改用穩定 flock inode，不 unlink 鎖；程序離開由 kernel 釋放。只有鎖檔但沒有 live lock 不會阻塞。ZIP／ledger 完整保存後才 atomic replace pointer；相同 receipt 的成功重跑是 no-op。既有損壞 ZIP 一律停止並要求明確隔離，不自動刪除或修補。
6. **回復**：CAS、完整舊 ZIP 驗證與舊版 seed/pin 必須吻合。新前端 seed 不能拿來驗舊前端。相同回復可安全重跑；損壞、過時 CAS 或路徑穿越拒絕。
7. **所有 workflows 稽核**：以 PyYAML 6.0.3 結構解析，拒絕 duplicate key／alias、未知檔案、schedule／額外事件、候選 write 權限及部署 environment/action。原 pages-release.yml 整檔 SHA 固定為 `07ec8e9cebcc239d92232663d52bb9f0f872cfa6a4b64b602d4fb317ae00a7ed`，唯一既有正式部署權限保留；這不是宣稱 repo 沒有部署 workflow。
8. **執行政策**：每日設定會被 acquisition、gate、projection、打包、驗包與本機 ledger 載入。profile、scope、凍結策略與 false 權限旗標受到約束；改成 true 不能啟用任何正式權限，只會失敗。品質門檻取自設定，可在安全上限內收緊，不能悄悄放寬。候選政策 SHA 綁定 report／gate／manifest。seed SHA 有設定則強制吻合；null 只允許人工指定 SHA 的離線 rehearsal，不代表已核准正式前端。`sourcePriority` 明列為說明欄位，實際來源優先順序由唯一入口強制 CSV 決定。

## 故障注入證據

測試來源：`tests/test_candidate_safety.py`；只使用 fixture／模擬來源及暫存目錄。

| 注入情境 | 驗證的結果 |
|---|---|
| source-state、quality、market、attempt 各寫入一半後失敗 | baseline 全目錄雜湊不變；無候選目錄；有獨立失敗證據 |
| 新 raw 快照部分寫入，後續讀取失敗 | 擷取提早停止（3 次 mock 呼叫）；錯誤被捕捉；不傳遞損壞候選 |
| KeyboardInterrupt／候選 rename 失敗 | baseline 不變；未公開候選；新嘗試可成功 |
| candidate report 部分寫入 | failure 目錄不含 gate／candidate；舊輸出不可重用，且重用不會發請求 |
| ZIP entry／最終 link／receipt 失敗 | 不公開部分 ZIP 或不完整 package；新嘗試可成功 |
| 子程序完成 pending 寫入後 os._exit(23) | 最終名稱不存在；遺留 pending 無法當成功包；重跑可完成 |
| live flock 競爭、持鎖子程序被 kill | 競爭者停止；鎖檔保留但 kernel lock 釋放，後續可取得 |
| pointer replace 前失敗 | 保留前 pointer；已完整 ZIP/ledger 可供重跑 |
| pointer 已替換後回報錯誤 | 相同 receipt 重跑不改 chain，確認既有完整版本 |
| 截斷新 ZIP、既有損壞 store ZIP | 拒絕；前 pointer／前完整 ZIP 保留，不覆寫損壞檔 |
| 回復的錯誤 seed、stale CAS、損壞舊包 | 拒絕；current pointer 不變；正確舊 seed 可回復原 ZIP 位元組 |
| 設定放寬或權限 true、schedule／workflow 變更 | fail closed；設定 coverage=100 會實際阻擋現有 fixture |

初輪故障注入揭露 raw 快照損壞後例外逃出原 collect 錯誤處理；已將 acquisition 納入整個候選失敗邊界並重測。測試沒有關閉驗證、吞掉錯誤或移除斷言。

## 本輪驗收與證據

最終統計與個別 runner logs 位於 `test-results/stage4c1b/`（忽略路徑）。本報告的結果只代表本地隔離環境。

- Python 離線全套：94 項通過，0 失敗／錯誤。包含故障注入測試；mock HTTP 的通過不等於官方來源實測。
- 前端單元：80 項通過，0 失敗／跳過；HTTP 使用 mock，實際 socket 禁止。
- 一般 Vite build、audit-built、build:rc、audit-rc、daily seed 建置及離線完整打包／驗包／本機 CAS 回復已執行。
- 一般介面 Chromium：17 項通過；固定 RC Chromium：6 項通過。每日候選版 Chromium：7 項通過；全部 30 項均無失敗／跳過／flaky。結果記錄於本輪 acceptance.json 與 browser runner log。
- 瀏覽器只連 localhost；以 host resolver 限制外部解析。失敗刷新、錯誤 SHA 等為瀏覽器本地模擬。
- 未執行會重寫受控 frontend/public/market.json 的根目錄 npm run build；改直接執行 npm run build --prefix frontend。受控資料未改。
- 70 個受保護檔案（全部受控 frontend、data、研究／解析／schema、原觀察版投影、核准／授權政策及正式 Pages workflow）與原 PR SHA 逐位元組一致。
- 以原 PR git archive 的原前端及 seed builder、相同依賴重新 build，6 個固定靜態檔案與 frontend-pin 均與本輪完全一致。每日資料／manifest 的候選政策 metadata 改變是預期差異，不宣稱 ZIP 與原候選相同。
- 舊觀察版公開 data SHA 仍為 `bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9`。
- 對既有正式網站的唯讀 HTTPS 檢查遭代理 403，**未確認線上目前內容**。沒有執行部署／撤站等操作，不能將本地驗證寫成 live HTTPS 驗收。
- 未執行：官方行情抓取、新交易日實測、GitHub Actions dispatch、正式部署／回復、Safari 實機、免費額度遠端檢查。原 CI 成功屬原 PR；本輪變更尚未 push，沒有本輪遠端 CI。

## 安全重現

Python 3.12+、Node 22+；先在虛擬環境安裝 `requirements-dev.txt`，前端用 lockfile 安裝。若預設 npm cache 不可寫，使用新的本地 `--cache`；不可停用 TLS／integrity。

```bash
python -m pip install -r requirements-dev.txt
npm ci --prefix frontend --no-audit --no-fund
python -m scripts.audit_workflows
npm test
npm run build --prefix frontend
node scripts/audit-built.mjs
npm run build:rc
node scripts/audit-rc.mjs
node scripts/build-daily-seed.mjs
python -m scripts.daily-dry-run --output test-results/UNIQUE-REHEARSAL
```

瀏覽器使用既有 Playwright config；本輪使用系統 Chromium，不下載或安裝新瀏覽器。可用 SCANNER_CHROMIUM_PATH 指定本機 executable。三個 suite 必須依序執行，避免共用 4173 port。

候選入口只顯示說明，不發行情請求：`npm run data:candidate -- --help`。未帶 `--fetch-current` 時採用明確標示日期的既有 fixture；資料延遲不能冒稱最新。重跑指定新的 output 路徑；不可刪除前次證據來假裝第一次成功。

## 修改檔案

- CLI／政策／候選：`package.json`、`config/daily-release.json`、`pipeline/daily.py`、`pipeline/daily_release.py`、`pipeline/daily_state.py`、`pipeline/package_daily.py`、`pipeline/run.py`、新增 `pipeline/candidate_io.py`、`pipeline/daily_policy.py`。
- workflows 稽核：`.github/workflows/ci.yml`、`.github/workflows/deploy.yml`、`scripts/audit-rc.mjs`、新增 `scripts/audit_workflows.py`、`requirements-dev.txt`。原正式 pages-release.yml、update-data.yml、package-daily.yml 未改。
- 演練／測試：`scripts/daily-dry-run.py`、`tests/test_daily.py`、`tests/test_daily_release.py`、新增 `tests/test_candidate_safety.py`。
- 說明：`README.md`、`docs/OPERATIONS.md`、`docs/STAGE4C1_OPERATIONS.md`、本報告及新增 `docs/STAGE4C2_INTERFACE_DESIGN.md`。

## 剩餘 P1／P2 與待核准事項

- **P1／4C-2**：尚未實作最後成功正式版本 baseline、正式持久 state、Pages 與 pointer 的跨系統協調。固定 checkout fixture 不能當正式更新基準。
- **P1／4C-2**：尚無部署未知狀態的調和、正式 HTTPS 全檔確認與授權回復流程。不得直接把本機 CAS 接上 schedule。
- **P2**：七日 artifact 保存仍不等於持久保存；既有首次發布 workflow 仍依賴固定 artifact。新版未解決舊產物到期問題。
- **P2**：TPEx 完整／臨時停市／跨年日曆、真實新日全鏈、Safari 實機與通知／額度仍需驗收。
- **P2**：候選目錄 rename 僅保證本機原子可見性，不宣稱所有檔案的斷電持久性；flock 僅適用 Linux 本機，不是跨 runner 鎖。
- **P2**：原有損壞最終 ZIP 採停止／明確隔離政策；孤立 pending 可保留，但沒有自動清理正式儲存的權限。正式長期儲存、完整 candidate/base/run binding 與政策演進介面詳見 4C-2 設計，未當作完成。

本輪到此停在本地待審查。後續 push、CI 或任何正式操作需另外核准。
