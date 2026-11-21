# 開發、維運與發布

更新：2026-10-20。Repository：0857ken/tw-market-scanner。正式站：https://0857ken.github.io/tw-market-scanner/ 。

## 目前狀態

正式觀察版 `4b1-rc1` 已於 Stage 4B-2 發布，Pages Run 38496725153；正式 TWSE／TPEx 行情日仍為 2026-10-13。不要重新建庫、首次上線或假設 main 仍是原始 handoff。

開發沿用 `feature/stage4c1-daily-update` 與 Draft PR #2，4C-1B 候選架構與 4C-2B 離線協調已有成果，尚未合併 main。4C-2C 已有 state 專用保護；原始 Release、state 分支、g0／successfulPointer 與乾淨遠端還原尚未完成。沒有啟用每日 schedule。

[本輪驗收](STAGE4C1_REVALIDATION_20261020.md) · [每日維運、架構與回復](STAGE4C1_OPERATIONS.md) · [4C-2B 離線實作](STAGE4C2B_IMPLEMENTATION.md) · [4C-2A 規格](STAGE4C2A_ARCHITECTURE_AND_CODEX_SPEC.md)。

## 本機驗證

Python 3.12+、Node 22+。只使用既有 requirements／lockfile：

```bash
npm run setup
npm test
npm run build
node scripts/audit-built.mjs
npm run preview
```

在 `http://127.0.0.1:4173/tw-market-scanner/` 驗收。測試使用離線 fixture，不抓金融 API。三組瀏覽器測試及完整候選 dry-run 見每日維運說明；Chromium 不能代替 iPhone Safari。

## 官方更新入口

```bash
npm run data:candidate -- --help
```

此命令對應 `pipeline.verified_baseline`。必填精確成功 ZIP／generation、原定 target／slot／deadline、run／attempt 與全新 output。缺 state／來源閉包／live 對應即停止。舊 run／daily CLI 與 daily_release 直接抓取都不是替代入口；不要設 `DATA_UPDATES_APPROVED=true` 或用 checkout／market-data 冒充正式 baseline。

另准的低負載來源診斷只保存必要 metadata，不賦予候選或發布資格。403／429／來源異常停止，不換來源、Token 或日期參數繞過。

## 發布與回復

正式站目前使用原完整 ZIP；每日前端尚待 seed 核准。未來流程：成功 pointer → 封存閉包／live → 隔離採集／gate → 固定 seed 打包／receipt → 不可變封存與單一預約 → 一次 Pages create → API 與兩輪全檔 HTTPS → 成功 CAS。

舊 `pages-release.yml` 尚未接入單一協調器，main 也尚有舊人工更新入口；實際 variable 值未核實。這些是正式 daily writer 開放前的阻擋，不能依舊說明重跑首次發布。

正式回復須有該操作的精確授權，使用原完整舊 ZIP、其 seed／receipt／來源閉包，經同協調器產生新 generation 並重驗 live。不重新 build、不只換 pointer。逾時、失聯、UNKNOWN、混版或網站已換但 pointer 未記，停止並唯讀 reconcile，不自動重送或回復。

## 費用與限制

額外月費目標 NT$0；只用公開 repo 的標準 Ubuntu runner，不新增付費來源／雲端／larger runner。artifact 僅供短期診斷，正式備份須保留必要完整舊版與閉包。啟用前核對帳號共享儲存與預算，不自動加購、GC 歷史或縮減必要來源。

不得修改 txf-tracker、寄出詢問信、建立 PAT／Secrets、批量回補 300 日或解鎖信用／TWSE T86／未驗證長期訊號。完整策略 `release_check` 保持嚴格；observation-only 不代表完整策略通過。
