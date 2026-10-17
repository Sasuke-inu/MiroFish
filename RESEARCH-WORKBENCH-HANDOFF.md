# 接續工作交接

## 最新審查：程式碼審查（2026-10-18）

使用者本輪要求詳細 code review 與逐步修正報告，未要求實作。已核對分支仍為 `codex/workspace-visual-refinement`、HEAD 仍為 `43d30e995ac42fc96a1908520622ba2cde85bec8`，審查開始工作區乾淨。

- 完整報告：[CODE-REVIEW-2026-10-18.md](CODE-REVIEW-2026-10-18.md)。確認 17 項問題（5 項 P1、10 項 P2、2 項 P3），逐項列出位置、條件、證據、最小修正步驟及驗證方式；均尚未修正。
- 高優先問題包括舊工作 API 的來源／操作保護缺口、提前退出仍發正常完成回條、未更新圖譜卻解除報告門檻、生成中刪除造成缺章報告，以及預設 Dockerfile 的依賴複製順序。
- 審查使用原始碼與隔離合成資料；沒有真實模型、付費擷取、live 工作啟停、既有資料庫變更、服務重啟、映像建置、push 或 merge。沒有重跑完整 325 項測試；沒有重新核對現行 3000／3100 服務，下方入口及測試描述保留為 2026-10-03 交付記錄。
- 三個使用任務仍為「待使用者驗收」。保存示範入口目前在程式上仍會走安裝／補寫路徑（報告 R09）；本輪未點擊。隔離代理重現不是使用者實測。

## 最新交付：審查修正實作（2026-10-18）

17 項審查已全部實作，並完成兩輪獨立覆核與其修正；上方審查段的「均尚未修正」已不適用。完整記錄與驗證數字：[IMPLEMENTATION-2026-10-18.md](IMPLEMENTATION-2026-10-18.md)。

- 修正流：6 條 worktree 分支以 --no-ff 逐條合併（R01／R06／R13、R02／R03／R07／R15、R04／R12／R14／R17、R08／R09、R09／R10／R11、R05／R16），加上第一輪覆核修正（c04acd4）與第二輪覆核修正（e44859f）。
- 驗證：後端 647 passed／7 failed／1 skipped（7 項為既有環境依賴的基線失敗，非本次回歸）；前端 341 passed、`npm run build` 成功；Docker 於 746408c 樹（已含全部 17 項修正）真實建置成功。
- 邊界：沒有真實模型、付費服務、live 服務重啟或 push；全部只提交本機。R03 決策：未要求圖譜更新的完成執行保留 completed、graph_ready=false，報告維持不解鎖；訪談閘門另以 graph_update_status=not_requested 放行（746408c）。
- 工作區：6 個修正 worktree 已移除（fix/* 分支保留）；覆核與測試證據在 `D:\Dev\Projects\mirofish-worktrees\_evidence\`（repo 外）。
- 三個使用任務仍為「待使用者驗收」（見下節 2026-10-03 交付）；R09 修正後「開啟保存示範」不再走安裝／補寫路徑。

## 最新交付：主流程收斂（2026-10-03）

本輪開始於 `ec7e524b032a603d822b7a571644c07e00352ecf`，分支仍為 `codex/workspace-visual-refinement`，起始工作區乾淨。只改前端工作台及必要的返回路徑；沒有後端、資料庫、模型、憑證、排程或服務重啟變更。一位實作者、一位唯讀審閱者；審閱提出的導航／狀態問題已修正。

- 使用新版入口：<http://localhost:3000/workbench>。Docker 3100 保留上一版，本輪沒有重建或部署 Docker。
- 第一層由六個分頁改成「總覽／資料／結果」。總覽提供問題、所選模擬、狀態與一個下一步；資料保留來源版本、原文及引用；結果先讀指定保存報告，再進入模擬過程、版本、合格比較與品質資訊。
- 研究清單預設不混入合成示範；「試看示範」「所有任務」為具名次要入口。更新與實驗計畫保留在總覽的「已保存計畫」；管理與匯出仍保留。原六個分頁網址會對應至新位置。
- 設定、舊圖譜與準備／模擬／報告頁的返回連結保留研究及選定模擬／報告。草稿只保存在本機分頁工作階段；不恢復擷取授權或未完成寫入。
- 有保存報告時，即使圖譜未確認仍可閱讀；完整性未核實、部分報告與合成示範分開標示。停止／中斷／未知不自動重送，也不偷偷換成較早成功的模擬。

### 驗證與畫面

最終前端程式快照：本輪提交（提交 ID 以交付訊息及 `git log -1` 為準）；最後測試後只補交接文件。全套前端 **325 passed / 0 failed / 0 skipped**，Vite build 成功。原基線 285 項與各中間批次不能加總。精確來源 hash 與測試輸出保存在忽略的 `deploy/workbench-simplify-final-evidence.json`、`deploy/workbench-simplify-final-tests.json`。

- 實際連接既有本機資料，量得桌面 **1440×900 CSS px**、手機 **390×844 CSS px**；檢查繁中、英文、深／淺色，簡中切換保持可用（既有部分舊文字仍是繁體）。截圖像素不等同 CSS viewport。
- 既有研究：`proj_bca45eb91f02`「本機圖譜驗證：橙子小屋（完成版）」→ 第 2 次模擬 `sim_7bb2afd7b007` → 報告 `report_8040406ad6d3` 第 1 版 → 重新整理，選擇保持不變。這是既有保存內容的閱讀驗證，不是本輪生成。
- 合成示範：研究清單 → 試看示範 → 故事角色互動 → 第 1 次模擬 → 結果 → 引用與假設 → 第一個「定位原文」→ Escape 返回同一結果，焦點回到原按鈕。手機設定往返保持同一研究與模擬。原文定位不代表語意支持已核驗。
- 記錄到的既有研究閱讀／切換／重新整理片段有 **11 個請求，全部 GET，其中 7 個是 `/api/` 請求**；沒有生成／擷取請求。範圍為該片段，不宣稱涵蓋整輪所有瀏覽行為。
- 原生 200% 瀏覽器縮放未驗證；執行中停止控制、錯誤恢復及未知狀態以隔離前端測試驗證，沒有對 live 工作停止或故障注入。沒有真實模型生成或付費擷取驗收。

畫面均在 `deploy/`，為本機證據而非提交內容：

- 改前桌面：`workbench-simplify-before-desktop.jpg`（修改前 3000）；改前手機：`workbench-simplify-before-mobile-docker.jpg`（事後從保留上一版的 3100 擷取，非新版）。
- 改後桌面：`workbench-simplify-after-desktop-dark.jpg`、`workbench-simplify-after-desktop-light.jpg`；手機英文深色：`workbench-simplify-mobile-en-dark.jpg`。
- 保存報告：`workbench-simplify-after-report-desktop.jpg`；引用原文：`workbench-simplify-source-desktop.jpg`。其他帶同前綴的畫面可能是中間快照，不作最終版主畫面。

### 待使用者確認的易用性驗收

1. 從研究清單找到橙子小屋研究，說出目前狀態及下一步。
2. 在「試看示範／故事角色互動」開啟第 1 次模擬的第 1 版保存報告，辨識示範及完整性標示。
3. 從該報告找到引用原文，再返回同一份結果。

代理已操作以上閱讀路徑，但不能替使用者宣稱不再困惑。本輪在交付主流程收斂後停止，不接續下方歷史擴充清單。

## 前一輪交接（歷史，保留追溯）

本輪沿用 `D:\Dev\Projects\mirofish` 的 `codex/workspace-visual-refinement`，開始 HEAD `298a9778f61e7696c2ac6874fba14fc97320ecb2`，開始時乾淨。完整狀態與驗收界線在 `RESEARCH-WORKBENCH-STATUS.md`；每個變更路徑列於 `RESEARCH-WORKBENCH-CHANGES.md`。最終提交 ID 以 `git rev-parse HEAD` 與本輪交付訊息為準。

## 使用入口

- 開發版：<http://localhost:3000/>；工作台：<http://localhost:3000/workbench>。
- Docker 版：<http://localhost:3100/>；設定：`/settings`，任務：`/workbench?view=tasks`，示範：`/workbench?view=demos`。
- 示範為本機合成資料，可查看版本／引用、回放、比較、品質及匯出。新生成仍需明确按鈕、可核對完成屏障和適用授權。
- PDF：`deploy/workbench-contradiction.pdf`。本機測試 JSON／畫面／匯出含本地識別資訊，已被精確忽略，仍留在原位置供檢查。

## 運行、恢復與安全

1. 先檢查 `docker compose -f docker-compose.local.yml ps` 及 `top backend`。目前 backend／Graphiti／frontend 為本 checkout 新映像，Neo4j 未清除或重建資料。
2. 程序不在、heartbeat／擁有者無法核對時，工作標成 interrupted／needs_review；不要手動改成 completed 或盲目 force。保存產物可讀，新的執行使用新身分。
3. namespace recovery 僅核對同一筆圖譜複製交易回條，不啟動模擬；未知寫入結果維持需檢查。不要把原來源 namespace 當恢復目的地。
4. 模型設定只套用新工作；舊 run 的 manifest／來源版本保持固定。聊天模型變更不改本機 embedding 或索引。已有 key 不作管理授權。
5. 工作／證據 SQLite 位於既有 uploads。備份需協調 uploads、Graphiti journal、Neo4j 一致狀態；本輪沒有做完整備份還原演練。不要只搬某一個 SQLite 檔或清除 volumes。
6. 重跑測試沿用隔離容器 `--network none`、暫存 uploads；不要掛入 live 資料做故障注入。開發頁只綁 loopback；不開放 LAN。

## 下個可核對項目

- 使用者明確指定一次真實小旅程的供應商／模型及費用上限後，才進行 LIVE_E2E；記錄來源 hash、run／attempt、Graphiti 完成回條、報告版本及供應商實際用量，不能以 285／534 的隔離測試替代。
- 來源搜尋目前 capability 未實測，停用計畫不會執行；先取得本專案外呼授權再驗證本機 Firecrawl 搜尋與候選採用。
- 原生 200% 縮放、72 列長表格 PDF、完整大圖譜性能及逐物件自動引用仍分開列為未驗收／部分完成。先處理工具能力或具體資料契約，不改名冒充完成。
- 檢查點分支維持 BLOCKED_CAPABILITY，直到平台 DB、代理記憶、隨機狀態與圖譜能共同恢復且父 run 不變。

所有已核對修改只提交本機；沒有 push、merge upstream、公開發佈或新增管理權限。
