# Stage 4C-2C 前置 P1 補強（2026-10-20）

從既有 Draft PR #2 的 f15cee49230bc16a2be9c76917e2a1ceb92b974e 增量處理；保留原四資產 bytes、公式、政策、前端與全部 workflows。此變更不啟用正式 mutator、Pages、回復或 schedule。

## 五項補強

1. **完整採集重建**：acquisition_validation.replay 只把來源 metadata 與記錄的 generatedAt 當輸入，以封存內解析快照重新呼叫原有 build／integrate，逐欄比對完整內部 market。原 market 的 stocks／history 不作重建 seed。涵蓋缺價／缺列、全歷史、法人、指數、融資、期貨與成員／事件等既有輸出，不修改公式。
2. **整包欄位限制**：market 的非來源欄位由完整重建比對約束；來源 metadata、source-state、quality、daily-attempt、inventory、receipt／projection 額外限制欄位。解析快照列不允許 dict／list 型的隱藏巢狀資料。這是結構與來源控制，不宣稱能辨認任何文字欄位內的敏感語意。
3. **成功核准證據**：每代 SuccessRecord 必須有實際 approval bytes、正確 SHA、來源類別、ZIP／receipt／seed／原 processor 與 publisher code、expected state、有效時間與前代綁定。offline-test 只可用於兩個 offline backends；真實 owner-reviewed 證據必須再符合由受信任呼叫端提供的獨立 registry，不能從 state 自行宣告可信。尚未接好 registry 的正式讀取會安全停止。
4. **Pages artifact bytes**：唯讀檢查精確 artifact ID、repo／非 fork、workflow、head SHA、run attempt 與產生時間；重新計算外層 ZIP SHA，再驗內部 artifact.tar 的每個檔案 bytes 與核准 site.zip 一致，拒絕額外檔、重複、link／traversal。dispatch 前再讀回，SuccessRecord 持久保存 proof 與 SHA。舊版本 processor 與執行回復的 publisher 可分別核准，不必重建舊網站。
5. **B08 真正中斷**：子程序在 pack 前、ZIP 暫存寫入後／link 前、候選目錄公開前／後直接 os._exit。公開前不得有半包；公開後及正常完成須能在 writer 已退出後獨立還原，baseline inventory 不變。舊僅檢查 unpack 的方法移除 B08 標記。

原遠端 mutator 閘門及離線 authority 的限制保留。新 Pages bytes 契約以記憶體 client／合成 artifact 驗證，不是假稱已呼叫真實 Pages。正式多入口、一次發布、Safari、日曆與排程仍未驗收。

同一包驗證過程把固定 parser／policy 檔案雜湊讀取移到逐快照迴圈外；每次驗包仍重新讀取，沒有跨包或跨政策的驗證快取，也沒有減少逐檔檢查。

## 原版本保全

portable-legacy-import(2).zip 已成功讀取並重算 SHA：

`45a4c959ec14e653c658dd645f165aba14370adb6e89ad69f7a5227f7b3728fe`

四資產 SHA 與 10/17 核准紀錄完全一致；以新完整來源重建驗證器驗原 closure 通過，沒有重新打包或覆寫舊 receipt／網站。原始 HTTP body 未保存，仍明列 responseBodyArchived=false。

## 驗收

- 新增 P1 定向測試首次 5/5 通過；Node 80/80，workflow audit 通過。
- 舊 transport wire 測試補上 bytes proof 契約；wire 與完整舊版回復定向 2/2 通過。
- 本機 Python 完整回歸 121 項，745.284 秒，0 failure/error/skip；45 ID 矩陣全部 PASS。其後追加的純 g0 builder 與最後核准／欄位補強，由最新 6 項 P1 定向測試重驗（46.411 秒）全過。遠端固定 SHA CI 應包含 122 項 Python，不以此前 226 項代替，也不把重跑相加為不同測試。
- 本機未因這些修補取得 Pages／正式回復權限；真實 acquisition／發布不屬本輪 P1 測試。

## 初始化承接

既有 Stage 4C-2C 初始化授權與官方網頁操作授權保留。10/20 已重新讀回 state ruleset 25306665：active，精確 state ref，禁止 delete／non-fast-forward、要求 linear history、無 bypass；官方 Release 編輯頁顯示 immutability 已啟用。

本輪 Git clone 與精確 HEAD 讀取已成功，原包下載也已恢復；這些不是遠端寫入／受保護 append 成功的證明。現有通用 create_commit 仍必填 parent，不能拿它建立 orphan。

若採既有 Git transport 初始化，須使用獨立 bare repository 的空 parent root；不能從 main 建普通分支。先建立只含說明的 pending bootstrap root，再以單 parent／非 force append 留下管道驗證；此時沒有 state.json／success pointer，更新器必須保持安全停止。保護下 append 成功後，才進行核准的原版本封存及同 commit 的完整 g0。bootstrap commits 不代表正式版本，g0 所在分支的祖先 root 必須確實無 parent。

封存固定 tag／原 processor commit，四資產逐一讀回後生成真實 Release／asset IDs 的 package-index；凍結前後都驗包。g0 同 commit 保存 pointer、SuccessRecord、live、approval、receipt、index，不呼叫 Pages。乾淨遠端還原的可信 authority registry 必須由此次人工初始化核准資料獨立給定，不能由下載的 state 自行組成；將精確 registry digest 留在交付證據，未來自動 workflow 另行核准接線。

任何權限拒絕、資產不一致或未知狀態停止；不加 PAT／Secrets、不擷取其他憑證、不弱化 ruleset、不翻轉 production／rollback／schedule 旗標。
