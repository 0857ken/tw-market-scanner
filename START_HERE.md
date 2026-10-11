# 台股市場雷達 3.0 — Work 交接包

## 你看到的是什麼

這份交接包把原有兩份可用來開發的程式放在一起，**尚未完成串接，也未部署**：

- `frontend/`：Vite + React 的市場雷達 v2 展示版，包括明確標示 DEMO 的測試資料、圖表、搜尋、手機版等。
- `data-pipeline/`：Claude 提供的 Python 台股資料管線、GitHub Actions 排程，以及多個 JSON 輸出。來源真實性和執行成功與否要重新以本次工作環境驗證。
- `screenshots/`：原始網站參考畫面兩張。
- `WORK_TASK.md`：貼給 ChatGPT Work 的完整任務指令，也可直接要求 Work 先閱讀本檔。
- `docs/INTEGRATION_RISKS.md`：由程式審閱確認的優先整合問題。

## 最重要的保護規範

1. **新建獨立專案**，建議 `0857ken/tw-market-scanner`。**嚴禁修改** `0857ken/txf-tracker`、main/gh-pages 及其所有 GitHub Actions 或 Secrets。
2. **新增的月費預算為 0 元**：GitHub Free + GitHub Pages + 可用免費額度內的 Actions + 合法免費行情。**任何付費行為都要先取得使用者同意**。
3. 本檔案裡含 DEMO／範例，**不得當成即時真實行情**，不可把缺失值填 0 冒充正常行情。
4. 僅研究與資訊展示；**不得下單、連券商持倉、傳輸憑證**。
5. 先開發分支、測試與 PR，再詢問使用者是否開放公開 GitHub Pages 網站。建立公開 repo 之前要再確認無 Secrets、授權風險和使用者公開意願。

## 注意

`frontend/` 和 `data-pipeline/` 各有自己的 `.github/workflows/`，目前目錄分開只是交接用，不代表放進 GitHub repository 後已可自動運作。Work 需規劃將流程合併至同一個 repo 的根目錄，處理時間與資料一致性、避免 Actions 自動推送形成部署迴圈，再進行端對端驗證。
