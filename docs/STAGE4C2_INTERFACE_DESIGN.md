# Stage 4C-2 介面與故障設計（尚未實作）

本文件不是啟用許可，也沒有對應正式 state adapter、排程或 Pages 協調程式。4C-1B 的 `productionBaselineVerified:false`、`production:false` 不能升格為正式成功證明。

## 最後成功版本與 baseline

擬議輸入 `load_verified_baseline(expectedPublishedZipSha256)` 必須回傳：

```text
VerifiedBaseline {
  successfulPointer: {generation, deploymentId, publishedZipSha256, receiptSha256,
                     frontendPinSha256, sourceIdentitySha256, sourceRunId, runAttempt},
  completeSiteZip, receipt,
  acquisitionState: {market.json, source-state.json, raw snapshots},
  provenance: {processorCommit, candidatePolicySha256, licensePolicySha256},
  liveVerification: {verifiedAt, everyPublicFileSha256}
}
```

只可讀取 HTTPS 全檔驗證成功的 pointer；不得讀 pending、checkout 內的固定 fixture 或未核准的 market-data。驗證整個 ZIP、receipt、來源快照與公開資料之間的關係。公開 market 已裁切，不能單靠它恢復完整採集歷史；正式儲存必須另外持有對應 acquisition state。資料不足、缺包或政策不相容一律停止，不 fallback。

## 發布前候選契約

擬議 `prepare_candidate(VerifiedBaseline, IntendedSlot, FixedSeed)` 產出不可變 CandidateReceipt，綁定 baseline ZIP/代數、原定 target、source Run ID/attempt、processor SHA、政策 SHA、seed ZIP/pin、candidate data/manifest/ZIP SHA。打包端要獨立核對全部 binding 與 gate，不以單一 `decision:candidate` 字串代替驗收。固定前端 seed 必須是 owner 核准的精確 ZIP，而非相同 frontendId 就視為相同版本。

## 跨系統狀態機

```text
PREPARED -> DEPLOY_REQUESTED -> DEPLOY_CONFIRMED -> LIVE_VERIFIED -> SUCCESS_RECORDED
                     \-> UNKNOWN / FAILED (停止並保留前一成功 pointer)
```

每步使用同一 idempotency key（baseline generation + 原定 target + candidate ZIP SHA）；部署前重新驗 CAS。Pages 與 state 不具分散式原子交易，不能以本機 rename/flock 宣稱解決。部署後逐檔 HTTPS 比 SHA 成功才更新 successful pointer；若已部署但未記 pointer，恢復 worker 必須先查 deployment 與 live hash，不能盲目再部署。CAS 衝突或混版不得推進 pointer。

## 持久保存與回復

保留前後完整正式 ZIP、receipt、各版本 frontend seed/pin、授權/候選政策及 acquisition state，並驗證可恢復。GitHub 七日 artifact 只作診斷。選定正式儲存介面、費用/容量上限、備份與保護規則後另行實作，不在本輪新建 release/state 或其他分支。

擬議 `restore_verified_version(priorReceipt, priorSeed, expectedCurrent, authorization)` 必須重新驗證原完整 ZIP 與原前端，不重新 build。政策有變更時須明確決定是否仍允許舊授權；不為了回復跳過現有授權限制。自動 rollback 未獲授權前預設停止並報告。

## 排程與通知

IntendedSlot 必須保存台灣時區原始交易日，重跑不以實際開始日重算。主 slot／備援 slot、逾時、跨午夜、休市、臨時停市、跨年與去重須測試。403/429、同日修訂、授權或品質異常不得自動重試繞過。GitHub 原生報告亦需核准；不新增 LINE、郵件或付費服務。

## 上線前驗收順序

1. 固定 SHA 的完整 CI、owner 核准 seed 與 gate 門檻。
2. 真實最後成功版本的儲存／baseline 載入／完整回復演練。
3. 同一日多次更新與修訂、日期倒退、相對前版覆蓋率、並行 CAS。
4. Pages 成功、失敗、逾時未知、live 已換但 pointer 未換等故障注入。
5. 取得一次真實新交易日候選的人工全鏈驗收；Safari 實機、免費額度與監測確認。
6. 另行核准正式部署、回復權限與排程後，才能開啟自動更新。
