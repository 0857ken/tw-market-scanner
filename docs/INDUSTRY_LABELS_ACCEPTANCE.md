# 產業名稱顯示層改善

基準：PR #8 `bee9f53ef515e837e3ebd160f538f5ea253c22e5`。2026-10-29 核對。

僅替換畫面標籤：產業輪動、族群明細與成分股標題、熱力圖選單與排行、個股抽屜，以及既有週報產業文字。原始 `sector`、`sectorCode`、市場母體、分組鍵、排序鍵與公式完全保留；選單 value 仍是原始產業字串。不修改 parsers、行情、market.json、發布／排程或 observation-only 限制。

## 官方依據

- TWSE 交易資訊使用管理系統手冊，附錄三分類代號表：<https://www.twse.com.tw/docs1/data01/market/public_html/1030722-1030601999-2.pdf>。使用其基礎代碼；舊名稱再依下列更新公告覆核。
- TWSE 2023-05-30 公告，2023-07-03 生效：<https://eshop.twse.com.tw/zh/news/detail/0000000087e9b84901886b8d31700023>。35 綠能環保、36 數位雲端、37 運動休閒、38 居家生活；16 改名觀光餐旅。
- TWSE 分類要點：<https://twse-regulation.twse.com.tw/tw/law/DOC01.aspx?FLCODE=FL007104&FLNO=2>。
- TPEx 官方資訊傳輸手冊分類表：<https://dsp.tpex.org.tw/storage/eb_data/11405/1140500476-1.pdf>。下載文件 SHA256 `784d29bd39a9e5c945cb01f745e83eabaf9198e6b2d7d582d2ec6483874c610a`。
- TPEx 分類更新及 T30 公告：<https://www.tpex.org.tw/storage/eb_data/11203/11200554281.html>、<https://www.tpex.org.tw/storage/eb_data/11204/1120500265.html>。

市場別必須保留：17 在 TWSE 為「金融保險」，TPEx 為「金融業」。既有合併母體仍是一組，只將標籤顯示為「金融業／金融保險（17）」。32 文化創意業、33 農業科技業、80 管理股票僅配置 TPEx；01、09、12、18、19 僅配置 TWSE。TPEx 舊 18／34 不借用上市名稱，保留原碼並標示「分類未確認」。完整映射在 `frontend/src/industry-labels.js`，非數字的既有描述標籤不轉換，未知代碼或市場不猜測。

## 驗證

新增六項 Node 測試覆蓋官方新名稱、跨市場差異、未知／錯誤代碼、原描述、合併群組及輸入不變。五種 Chromium 寬度 320／375／390／430／1440 驗證中文標籤、原始選單值、成分數與成分 ID 不變、市場切換、抽屜、焦點關閉與水平溢位。

本機初步結果：Node 86 通過；RC Chromium 19 通過。最終 CI 與獨立預覽證據隨交付報告提供。本輪沒有執行 iPhone Safari 真機、VoiceOver 或實體鍵盤驗收。

固定行情日期仍為 2026-10-13，RC market.json SHA256 必須維持 `bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9`。新 UI 候選應有自己的 commit、manifest 與前端檔案雜湊，不冒用 PR #8 原始 ZIP 的 SHA。

## Safari 待驗收

用新預覽在 iPhone Safari 確認產業輪動、族群明細及熱力圖選單的長中文名稱可讀；切換上市／上櫃確認 17 的差異；搜尋 2330 並開關抽屜；回歸鍵盤、safe-area、捲動與關注操作。此候選不得取代正式網站。GitHub Pages 同一 owner 的不同路徑共用 origin，建議使用私密瀏覽避免舊快取／關注清單干擾。
