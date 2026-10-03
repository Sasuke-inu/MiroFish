# 圖譜隔離與模型固定驗證

日期：2026-10-03。以下為本機合成資料驗證，不是付費模型或真實研究資料的驗收。

## 已實作與驗證

- 每份圖譜固定一份模型設定；只有不含憑證的設定指紋持久保存，憑證僅在私人記憶體與本機 Graphiti 請求中使用。更改設定不能改寫已有圖譜的模型。重啟後無法核對相同設定時停止寫入。
- 新模擬使用獨立圖譜，保留 `source_graph_id`、複製作業識別與狀態。複製直接搬移節點、關係和既有向量，不呼叫模型，也不重新計算向量。
- 所有節點及關係取得新 UUID；節點內部關係引用、關係來源／目標及來源片段引用一併重映射。準備資料中的角色 UUID 也跟隨新圖譜。
- 來源含模擬活動、尚未完成的匯入、跨圖譜關係、找不到的內部引用或不支援的型別時拒絕複製。來源用於複製後保存為唯讀，仍有副本引用時不得刪除。
- Neo4j 複製及回條在同一交易完成。SQLite 完成狀態保存失敗時保留需核對狀態；用同一識別核對，不另建重複副本。節點數相同但內容改變也不能冒充未使用的複製結果。
- 模擬背景圖譜更新與停止時的最後一批更新共用同一份模型快照。錯誤紀錄不保存服務回傳的原始憑證內容。
- Graphiti 的 OpenAI 用戶端與上層生成重試均禁止自動重送不確定請求；逾時、HTTP 500 和無效 JSON 的測試皆僅呼叫一次。既有參數相容性處理保留。
- 舊模擬可讀取；缺少獨立圖譜證據時不能直接準備或啟動。`recover_namespace(simulation_id)` 僅供明確核對未完成的複製，不啟動模擬。
- 模擬識別在接觸資料夾前驗證，只允許 1–200 個英數字、底線與連字號。

## 測試證據

最新合跑：**131 passed、1 skipped、1 第三方棄用警告**。跳過項目是需要專用 Neo4j 的整合測試，已另行實測通過。

涵蓋測試檔：

- `test_graphiti_retry_boundary.py`
- `test_updater_model_snapshot.py`
- `test_zep_graph_memory_updater.py`
- `test_graphiti_snapshot_safety.py`
- `test_graphiti_local.py`
- `test_provider_settings.py`
- `test_simulation_namespace.py`
- `test_graphiti_namespace_clone.py`
- `test_simulation_execution_contract.py`

真 Neo4j 測試：`test_graphiti_namespace_clone.py` **12 passed**，包含實際交易的 UUID／引用／向量檢查、完成回條遺失後核對、整筆回滾、內容變更偵測，以及副本寫入不影響原始來源。

測試使用既有 `mirofish-backend:local` 與 `neo4j:5.26-community` 映像。只掛載程式、測試、腳本與 `.env.example`，沒有讀取或掛載真實 `.env`。Neo4j 容器以 `--network none`、無對外連接埠、獨立暫存資料啟動；測試容器只共享其隔離的 loopback。沒有連到現有服務或付費端點。專用容器及暫存卷已清除。

若重跑隔離 Neo4j，需設定可解析的容器名稱，例如 `--hostname clonefixture --add-host clonefixture:127.0.0.1`；否則該映像在無網路下的記錄初始化可能以代碼 3 結束。整合測試只接受 `MIROFISH_CLONE_TEST_NEO4J=bolt://127.0.0.1:7687`。

## 尚未在此子工作驗證

- 真實付費模型與完整多輪生成。
- 使用者介面的新模擬／核對入口；由主要工作整合。
- Zep Cloud 圖譜複製；目前明確拒絕，沒有回退成直接寫入來源。

以上測試數是本次子工作快照；主要工作後續全量測試結果優先。
