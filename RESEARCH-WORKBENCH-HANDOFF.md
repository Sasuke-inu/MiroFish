# 接續工作交接

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
