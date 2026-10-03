# 研究工作台變更清單

## 最新交付：主流程收斂（2026-10-03）

比較基準 `ec7e524b032a603d822b7a571644c07e00352ecf`；分支 `codex/workspace-visual-refinement`，起始乾淨。21 個路徑：18 修改、3 新增。只有前端、翻譯、測試、忽略規則及這三份既有交接文件，沒有後端或使用者資料變更。最終提交與精確 diff 以本輪交付 HEAD 對基準的 Git diff 為準。

- `frontend/src/views/WorkbenchView.vue`：既有工作台改為總覽／資料／結果；清單、狀態下一步、所選模擬／報告、來源／結果、草稿與次要入口收斂。
- `frontend/src/utils/workbenchJourney.js`（新增）：可測試的顯示狀態、選擇、命名及舊網址映射；不另建後端生命週期。
- `frontend/src/utils/savedReportMarkdown.js`（新增）、`frontend/src/components/Step4Report.vue`：抽取及共用既有安全報告閱讀格式，保留原解析行為。
- `frontend/src/components/WorkbenchNavigation.vue`：主要導覽只保留研究與偏好／設定，完整任務與示範仍有具名入口。
- `frontend/src/components/RunReplay.vue`：嵌入結果、沿用所選模擬及新分頁位置；跨模擬引用清除不相容報告選擇。
- `frontend/src/components/ReportVersionAction.vue`：新版本操作完成後回到正確研究與報告版本。
- `frontend/src/views/MainView.vue`、`SimulationView.vue`、`SimulationRunView.vue`、`ReportView.vue`：限定本輪的研究返回路徑，保留查詢選擇。
- `frontend/src/api/workbench.js`：復用既有準備狀態讀取與明確停止 API；沒有新增後端 endpoint。
- `frontend/tests/workbench-journey.test.js`（新增）、`frontend/tests/research-workbench.test.js`：三分頁、狀態真實性、選擇／返回／草稿／無開頁副作用回歸。
- `locales/en.json`、`locales/zh-TW.json`、`locales/zh.json`：對應新導覽、狀態、限制文字。
- `.gitignore`：忽略本機 `deploy/workbench-*.jpg` 驗收截圖。
- `RESEARCH-WORKBENCH-HANDOFF.md`、`RESEARCH-WORKBENCH-STATUS.md`、`RESEARCH-WORKBENCH-CHANGES.md`：本輪結果、證據與未驗收事項；前輪記錄保留並標示歷史。

驗證為同一最終前端來源快照的 325 項通過與成功建置。完整範圍、截圖和使用者待確認任務見交接文件。沒有提交憑證、私人設定、資料庫、上傳內容或本機測試輸出。

## 前一輪交付清單（歷史）

日期：2026-10-03。此為本輪工作區交付清單；最終提交身分見交付訊息或 git log。路徑以專案根目錄為基準。

清單由 Git tracked changes 與非忽略 untracked 檔案整理：63 個修改、65 個新增，共 128 個檔案（含本文件）。批次按主要責任歸類，每個路徑只列一次；部分共用檔案支援多個功能。

## 安全與驗證界線

- 未將真實 `.env`、私有 provider 設定、uploads／logs、資料庫或憑證檔列入交付。掃描候選時沒有讀取上述忽略目錄。
- 本機 `deploy/workbench-*.json|png|pdf|txt`、`deploy/p0-*.json` 與 `deploy/print-fixture/` 已忽略，不列為提交候選；產生器和已核對的 Markdown 說明保留。
- 建立本文件前，126 個候選檔合計 2,461,520 bytes，最大 163,143 bytes；没有大型或二進位生成物。8 個憑證樣式命中均為安全回歸測試中的合成／拒絕案例，沒有確認的真實憑證。最後首頁窄修復及本文件使文字大小略增。
- 各批測試數不能相加；最新全套測試、建置與瀏覽器／列印的實際驗收範圍以 `RESEARCH-WORKBENCH-STATUS.md` 及主流程最終證據為準。隔離／合成測試不等於真實模型成功。
- 檢查時兩個其餘子代理均已完成並停止編輯；本子代理只作最後首頁窄修復、其測試和本交付文件，完成後停止。

## 批次 1：持久化工作、明確啟動與安全終止

工作與執行身分持久保存；開頁及輪詢只讀，啟動／準備／建圖由明確操作發起；停止、未知結果與不完整執行不可冒充完成。訪談保留歷史並於送出前核對存活程序。

隔離測試涵蓋重複 claim、程序結束、停止屏障、晚回應、路由切換、訪談與問卷，以及 mounted 無生成副作用。

- `backend/app/api/simulation.py`（修改）
- `backend/app/models/execution.py`（新增）
- `backend/app/models/task.py`（修改）
- `backend/app/services/simulation_ipc.py`（修改）
- `backend/app/services/simulation_manager.py`（修改）
- `backend/app/services/simulation_runner.py`（修改）
- `backend/app/storage.py`（新增）
- `backend/app/utils/atomic.py`（新增）
- `backend/scripts/action_logger.py`（修改）
- `backend/scripts/run_parallel_simulation.py`（修改）
- `backend/scripts/run_reddit_simulation.py`（修改）
- `backend/scripts/run_twitter_simulation.py`（修改）
- `backend/tests/test_execution_persistence.py`（新增）
- `backend/tests/test_interview_availability.py`（新增）
- `backend/tests/test_simulation_execution_contract.py`（新增）
- `backend/tests/test_simulation_prepare_failure.py`（修改）
- `backend/tests/test_simulation_producer_safety.py`（新增）
- `backend/tests/test_storage_pool.py`（新增）
- `frontend/src/App.vue`（修改）
- `frontend/src/api/simulation.js`（修改）
- `frontend/src/components/Step1GraphBuild.vue`（修改）
- `frontend/src/components/Step2EnvSetup.vue`（修改）
- `frontend/src/components/Step3Simulation.vue`（修改）
- `frontend/src/components/Step4Report.vue`（修改）
- `frontend/src/components/Step5Interaction.vue`（修改）
- `frontend/src/views/InteractionView.vue`（修改）
- `frontend/src/views/MainView.vue`（修改）
- `frontend/src/views/ReportView.vue`（修改）
- `frontend/src/views/SimulationRunView.vue`（修改）
- `frontend/src/views/SimulationView.vue`（修改）
- `frontend/tests/interview-readonly.test.js`（新增）
- `frontend/tests/p0-workbench.test.js`（新增）
- `frontend/tests/workflow-quality.test.js`（修改）
- `frontend/tests/workflow.test.js`（修改）

## 批次 2：圖譜隔離、模型固定與具名連線

來源圖譜保存為獨立研究資料；模擬圖譜複製、回條及核對操作不重新生成。分階段模型設定固定，憑證與公開 manifest 分開；未知供應商結果不自動重送。

隔離契約及專用 Neo4j 測試覆蓋交易回滾、身分／版本／憑證邊界與無自動重試；Settings fixtures 覆蓋具名連線和未保存設定。

- `backend/app/api/settings.py`（修改）
- `backend/app/local_graph/namespace_clone.py`（新增）
- `backend/app/local_graph/runtime.py`（修改）
- `backend/app/local_graph/server.py`（修改）
- `backend/app/local_graph/store.py`（修改）
- `backend/app/provider_settings.py`（修改）
- `backend/app/services/oasis_profile_generator.py`（修改）
- `backend/app/services/simulation_config_generator.py`（修改）
- `backend/app/services/zep_graph_memory_updater.py`（修改）
- `backend/app/utils/graphiti_client.py`（修改）
- `backend/app/utils/llm_client.py`（修改）
- `backend/app/utils/openai_chat_compat.py`（修改）
- `backend/tests/test_graphiti_local.py`（修改）
- `backend/tests/test_graphiti_namespace_clone.py`（新增）
- `backend/tests/test_graphiti_retry_boundary.py`（新增）
- `backend/tests/test_graphiti_snapshot_safety.py`（新增）
- `backend/tests/test_namespace_recovery_api.py`（新增）
- `backend/tests/test_preparation_retry_boundary.py`（新增）
- `backend/tests/test_provider_json_envelope.py`（修改）
- `backend/tests/test_provider_profiles.py`（新增）
- `backend/tests/test_provider_settings.py`（修改）
- `backend/tests/test_simulation_namespace.py`（新增）
- `backend/tests/test_unknown_generation_outcome.py`（新增）
- `backend/tests/test_updater_model_snapshot.py`（新增）
- `backend/tests/test_zep_graph_lifecycle.py`（修改）
- `backend/tests/test_zep_report_barrier.py`（修改）
- `backend/tests/test_zep_simulation_barrier.py`（修改）
- `frontend/src/components/StageConnections.vue`（新增）
- `frontend/src/views/SettingsView.vue`（修改）
- `frontend/tests/stage-connections.test.js`（新增）

## 批次 3：研究工作區、來源版本與證據定位

加入同源研究 API、研究清單／封存／複製、來源與 Unicode 引句、版本差異、物件引用及精確事件返回。URL 採計畫→预覽→明確選取納入，納入不再次擷取；分析輸入與原歷史不漂移。

隔離契約涵蓋來源保存、版本／引句定位、跨研究拒絕、輸入 freeze 競態、停用計畫與未知結果；Vue fixtures 驗證真實 API 路由與安全文字呈現。

- `backend/app/__init__.py`（修改）
- `backend/app/api/graph.py`（修改）
- `backend/app/api/workbench.py`（新增）
- `backend/app/models/project.py`（修改）
- `backend/app/services/evidence_store.py`（新增）
- `backend/app/services/research_workbench.py`（新增）
- `backend/app/services/source_importer.py`（修改）
- `backend/tests/test_evidence_store.py`（新增）
- `backend/tests/test_ontology_input_gate.py`（新增）
- `backend/tests/test_research_workbench.py`（新增）
- `backend/tests/test_web_source_adoption.py`（新增）
- `backend/tests/test_workbench_graph_preservation.py`（新增）
- `backend/tests/test_workbench_navigation_plans.py`（新增）
- `frontend/src/api/workbench.js`（新增）
- `frontend/src/components/EventReferenceLink.vue`（新增）
- `frontend/src/components/EvidenceInspector.vue`（新增）
- `frontend/src/components/EvidenceLinks.vue`（新增）
- `frontend/src/components/GraphPanel.vue`（修改）
- `frontend/src/utils/sourceDiff.js`（新增）
- `frontend/src/views/WorkbenchView.vue`（新增）
- `frontend/tests/graph-history-quality.test.js`（修改）
- `frontend/tests/research-workbench.test.js`（新增）
- `frontend/tests/sources.test.js`（修改）

## 批次 4：回放、比較、品質、示範與報告交付

保存事件以穩定身分、分頁及時間點投影供回放／簡報；比較原始計數、文字與宣告引用，不推導語意分數。加入品質分母／樣本限制、三種合成示範、報告版本確認及 HTML／Markdown／JSON 匯出。

測試涵蓋事件缺口／游標、投影時間與範圍、真實計数合計、示範復原、報告版本與失敗拒絕、引用範圍、匯出安全及長文件合成列印來源；不代表真實付費生成通過。

- `backend/app/api/report.py`（修改）
- `backend/app/services/event_store.py`（新增）
- `backend/app/services/quality_evaluation.py`（新增）
- `backend/app/services/report_agent.py`（修改）
- `backend/app/services/report_export.py`（新增）
- `backend/app/services/workbench_demos.py`（新增）
- `backend/tests/benchmark_workbench_events.py`（新增）
- `backend/tests/build_print_fixture.py`（新增）
- `backend/tests/test_demo_recovery.py`（新增）
- `backend/tests/test_quality_evaluation.py`（新增）
- `backend/tests/test_report_outline_fail_closed.py`（新增）
- `backend/tests/test_workbench_events.py`（新增）
- `backend/tests/test_workbench_export_safety.py`（新增）
- `backend/tests/test_workbench_report_comparison.py`（新增）
- `backend/tests/test_workbench_report_safety.py`（新增）
- `frontend/src/components/EventCountComparison.vue`（新增）
- `frontend/src/components/ObservedQuality.vue`（新增）
- `frontend/src/components/ReplayBriefing.vue`（新增）
- `frontend/src/components/ReportComparison.vue`（新增）
- `frontend/src/components/ReportVersionAction.vue`（新增）
- `frontend/src/components/RunReplay.vue`（新增）
- `frontend/src/components/TaskRecordMeta.vue`（新增）

## 批次 5：首頁、歷史語意、三語與可讀性

首頁優先列出繼續研究、保存成果與示範，保留全部原輸入；直接讀取現有任務 API，只顯示進行中的工作與任務入口。保存報告另外顯示執行的真實狀態，stopped／failed／未知不冒充完整成功。新增安全搜尋導航、手機內容優先、對比邊框及單行搜尋按鈕。

前端 fixtures 涵蓋首頁原輸入、GET 失敗重試、任務過濾與不編造百分比、stopped＋completed 舊報告、三語、路由位置、鍵盤操作及淺／深色對比計算。

- `backend/tests/test_simulation_history_pagination.py`（修改）
- `frontend/src/components/HistoryDatabase.vue`（修改）
- `frontend/src/components/HomeResearchOverview.vue`（新增）
- `frontend/src/components/WorkbenchNavigation.vue`（新增）
- `frontend/src/router/index.js`（修改）
- `frontend/src/styles/theme.css`（修改）
- `frontend/src/views/Home.vue`（修改）
- `frontend/tests/fixtures/api.js`（修改）
- `frontend/tests/home-quality.test.js`（修改）
- `frontend/tests/ui-preview.js`（修改）
- `frontend/tests/workbench-contrast.test.js`（新增）
- `locales/en.json`（修改）
- `locales/zh-TW.json`（修改）
- `locales/zh.json`（修改）

## 批次 6：交付紀錄與本機產物排除

保存實作／驗證範圍及本次路徑清單；.gitignore 僅新增本機驗收輸出規則。程式、測試產生器、說明及有用的非敏感驗證紀錄保留。

候選檔案大小、二進位格式、常見憑證樣式與 fixture 命中已唯讀檢查；沒有暫存或提交。

- `.gitignore`（修改）
- `RESEARCH-WORKBENCH-CHANGES.md`（新增）
- `RESEARCH-WORKBENCH-STATUS.md`（新增）
- `deploy/research-workbench-graph-safety-verification.md`（新增）

- `RESEARCH-WORKBENCH-HANDOFF.md`（新增；運行、安全恢復及未驗收項目交接）
