# MiroFish 研究工作台：實作與驗證紀錄

## 最新範圍：簡化既有主流程（2026-10-03）

本輪依使用者最新的「簡化介面與主操作流程，不再擴大功能」執行；起始 HEAD `ec7e524b032a603d822b7a571644c07e00352ecf`，工作區乾淨，分支 `codex/workspace-visual-refinement`。下方 Phase 0 及 coverage matrix 屬前一輪歷史，沒有把其模型、測試或服務更新宣稱為本輪重新驗證。

- 已完成：研究清單與示範分離、三個第一層入口、真實狀態的下一步、選定模擬／報告版本固定、來源原文與結果往返、相關舊頁及設定返回、草稿保留。能力位置與可重現操作見 `RESEARCH-WORKBENCH-HANDOFF.md` 最新段落。
- 本輪測試快照：最終提交中的前端來源（測試後僅補文件）；**325 passed / 0 failed / 0 skipped**，建置成功。前端狀態映射及元件測試涵蓋無來源、未分析、準備不足、就緒、執行中、完成屏障、部分保存報告、停止／中斷／未知、示範、深連結與無開頁生成副作用。不與基線或中間結果加總。
- 實際閱讀驗證：既有資料的指定模擬／報告、示範引用原文、重新整理、設定往返、Escape 焦點恢復；實測 viewport 1440×900／390×844 CSS px，繁中／英文及深／淺色；簡中切換相容。
- 未完成驗收：原生 200% 瀏覽器縮放、使用者三項易用性任務。停止與錯誤狀態只在隔離測試驗證，沒有操作 live 執行中的工作。沒有進行真實模型生成、搜尋或擷取。
- 開發入口 3000 已載入新版；3100 Docker 維持歷史版本。無後端修改、服務重啟、新服務、資料／歷史刪除、管理授權、憑證搬移或外部推送。

## 前一輪實作紀錄（歷史）

需求來源：使用者於 2026-10-03 明確指定接續實作的 `MiroFish_Research_Workbench_Codex_Prompt_zh-TW.md`，已完整讀取。此檔為主進度與 coverage matrix；未驗證項目不列為完成。

## Phase 0：本機基線

- Checkout：`D:\Dev\Projects\mirofish`；分支 `codex/workspace-visual-refinement`；開始 HEAD `298a9778f61e7696c2ac6874fba14fc97320ecb2`；開始時 working tree 乾淨。
- Remote：`https://github.com/666ghj/MiroFish.git`。沒有重新 clone、fetch／merge 上游或推送。
- Compose：`mirofish-local`；開發前端 3000、Docker 前端 3100、後端 5001；四個服務均 healthy。此結果僅為服務健康。
- Backend 映像 `e4399f28…`；Graphiti 映像 `b1ca5f19…`；兩者身分不同，後續以當前 checkout 掛載的隔離測試為程式驗證依據。
- 資料掛載：`backend/uploads`、`backend/logs`；named volumes `models`、`cache`、`graphiti-state`、`neo4j-data`、`neo4j-logs`。Graphiti 的設定掛載為唯讀。既有備份說明要求 uploads、Graphiti journal 與 Neo4j 一起保存；未宣稱已有一致快照或完成還原演練。
- 僅讀既有執行狀態摘要：2 筆 completed、2 筆 stopped。未開啟可能啟動生成的頁面，未讀取或搬移管理憑證。
- 基準實测：2026-10-03 12:57–12:58 Australia/Sydney，前端 **146 passed**、Vite build exit 0；後端在 network=none、未掛載 live uploads 的容器測試 **261 passed**，exit 0。
- 證據：`deploy/workbench-baseline-frontend-command.json`、`workbench-baseline-frontend.json`、`workbench-baseline-backend-command.json` 與同名前後端日誌。附件歷史 370／88 模型數／上游 SHA 不作現況證據。

## 本輪狀態（2026-10-03）

以下更新涵蓋 Phase 0 之後的實作批次。`VERIFIED（隔離契約）` 只表示使用暫存資料、模擬供應商或專用容器通過相應測試，不代表付費模型、真實搜尋或完整使用者旅程已通過。各批測試有重疊，數量不可相加。

最終分層驗收見本文件末尾「交付驗收」。Phase 0 的 HEAD、測試數量和映像是開始時快照；各批測試不可相加，也不代替真實模型驗收。

## Coverage matrix（隨實作更新）

| 需求 | 本機入口／程式證據 | 本輪狀態 | 缺口與下一動作 |
|---|---|---|---|
| 現有暖灰／炭黑／琥珀、三語、響應式介面 | Home、theme.css、studio.css、WorkbenchView；保留既有旅程路徑 | VERIFIED（測試及已列畫面範圍） | 最終前端 285 passed；390／768／1440、繁中／英文、淺／深／系統模式已有實際操作；原生 200% 瀏覽器縮放尚未驗證 |
| 開頁不生成、設定不停止工作 | Step2／Step3／Step4、SimulationView、ReportView 改為讀取保存狀態與明確動作 | VERIFIED（前端契約） | mounted 不 prepare／start／force-regenerate；刷新、返回、設定往返與舊圖譜已實際操作；生成旅程仍受授權限制 |
| 執行防重複、終止與完成屏障 | RunStore、TaskManager、simulation API／runner、report API | VERIFIED（隔離契約） | 交易式 claim、不可覆寫身分、停止不算完成、全平台回條與圖譜完成後才可正式報告；LIVE_E2E 另列 |
| 工作持久化與重啟 | storage.py 共用 SQLite、擁有者身分與 heartbeat、原子 JSON 保存 | VERIFIED（隔離契約） | 孤兒／無法核對工作標示 interrupted／needs_review，不自動重送；live 閒置服務已重建並恢復 healthy；進行中故障只在隔離測試注入 |
| 訪談結束後的唯讀歷史 | Step5Interaction、interview/history、三種 interview API、runner producer 核對 | VERIFIED（前端／後端隔離契約）／PARTIAL（本機歷史頁手動驗收） | 開頁只讀；新訪談與問卷在送出前重查 producer＋run/attempt heartbeat；程序已結束、重啟或本 worker 無法核對時停用，但保存歷史仍可讀。未宣稱能在 producer 結束後恢復訪談 |
| 原來源圖譜保留與 run 隔離 | namespace_clone、Graphiti runtime/store、simulation_manager | VERIFIED（隔離契約＋專用 Neo4j） | 新 UUID／邊／向量映射、交易回條、來源唯讀、故障不回退寫來源；Zep Cloud clone 為 BLOCKED_CAPABILITY |
| 模型固定與憑證邊界 | graph-scoped private snapshot、prepare／simulation／report stage snapshot、subprocess environment | VERIFIED（隔離契約） | 模型設定與憑證指紋固定；圖譜重啟不能核對則拒絕寫入；API、DB、公開 manifest 不保存完整 key |
| 明確核對圖譜複製 | POST simulation/{id}/recover-namespace、UI 核對按鈕 | VERIFIED（隔離 API 契約）／PARTIAL（故障 recovery 按鈕未在 live 資料觸發） | 只核對同一複製作業；不得 prepare／start，不宣稱任意輪次檢查點恢復 |
| 未知生成結果與重試 | Graphiti retry boundary、LLMClient、profile/config generator、CAMEL scripts | VERIFIED（已列隔離批次） | 未知 timeout／無效 JSON 不自動重送；純本地 JSON 修復不額外呼叫模型；報告大綱例外分支的最後修復見下方 P0 記錄 |
| 分析輸入不可漂移 | ProjectManager.input_mutation_lock、save_source、generate_ontology、frozen_input.json | VERIFIED（隔離 thread＋spawn process） | 來源材料化與 ontology claim/freeze 共用 OS 檔案鎖；生成前釋放，後來來源不改原 bytes／版本；模型在 claim 前固定並保存去 key 快照 |
| 來源版本、引句與證據 Inspector | EvidenceStore、上傳／Firecrawl 整合、EvidenceInspector、版本差異 | VERIFIED（儲存／定位契約）／PARTIAL（完整物件沿革） | source identity、immutable version/hash、Unicode codepoint spans、缺失／相反來源；定位有效不代表語意支持 |
| 報告／角色／圖譜物件證據 | EvidenceLinks 接 GraphPanel、Step2、Step4、Workbench；手動保存來源關係 | PARTIAL | 正式 generation 尚未自動產出逐物件 evidence citation；不冒充自動語意追溯。手動引用是現有可用功能，不以此阻擋其他本地驗收 |
| 多連線、分階段模型與能力 | provider_settings profiles／stage assignments、models_only 能力測試、Settings | VERIFIED（隔離契約＋實際設定畫面） | 保留舊設定遷移、key 移除／endpoint 分離；可列模型不代表結構化輸出或真實生成已驗證 |
| 統一研究工作台 | WorkbenchView、WorkbenchNavigation、研究搜尋／重新命名／封存／複製／舊頁連結 | VERIFIED（已列操作） | 研究搜尋、全域搜尋、三個案例、設定往返、刷新保留回放位置已操作；封存／複製有隔離 API 與 UI 回歸 |
| 唯讀事件回放 | EventStore、穩定 event/run/attempt IDs、cursor、RunReplay、限定時間 projection | VERIFIED（隔離契約＋引用往返操作） | 事件按平台區分、尾端增量匯入、損壞／缺口可見；已實際保存 story 第一筆事件引用，再從引用清單返回相同 run／seq=1，網路紀錄無生成請求 |
| 已完成情境比較 | EventStore.compare、保存的 report/section/evidence diff、Workbench 比較 | VERIFIED（隔離契約＋實際情境比較） | 比較完整 manifest、事件數與首個差異、保存結論和宣告引用；缺資料不當作相等、不宣稱因果或語意正確 |
| URL 候選預覽與明確納入 | web-plan → web-preview → web-adopt；Workbench 候選選取 | VERIFIED（隔離契約）／BLOCKED_AUTHORIZATION（真實擷取） | 預覽擷取不保存研究來源；adopt 只讀同研究 completed plan，不外呼；跨研究、未知／失敗、超限選取被拒；重複納入不新增相同版本 |
| 來源更新、發布時間與快取 | source_importer、refresh、EvidenceStore、版本差異 | VERIFIED（隔離契約） | 沿用 24h 快取及上限；更新保留舊引用，發布時間僅接受含時區的有效 ISO 時間，缺值不編造 |
| 問題搜尋與定期更新 | status.search、停用的 source_update／sensitivity plans | PARTIAL／BLOCKED_AUTHORIZATION | search capability=unverified、status=disabled_authorization；本輪未探測／執行真搜尋。URL 匯入仍可用，停用排程不發外呼 |
| 擷取嘗試與額度 | source-import SQLite plans、發送前 attempted 計次、持久化結果與快取 | VERIFIED（隔離契約） | 失敗仍計入既有每次 3／每日 10 次限制；adopt external_calls=0；沒有新增搜尋用量或把未知成本填零 |
| 品質與誠實限制 | quality_evaluation、ObservedQuality、定位／缺口／假設／矛盾／樣本排除 | VERIFIED（隔離計算契約＋實際品質畫面） | 定義、分母、版本、sample_size及排除原因可追溯；重複／模型比較只觀察保存事件數，現實準確性與語意支持未評估 |
| 三種離線示範 | product／story／contradiction、workbench_demos、共用來源／回放／比較／報告入口 | VERIFIED（隔離 fixture＋實際三案例開啟） | 合成標記、固定 manifest／6 筆事件、失敗復原不冒充真人資料；實際報告章節有引用，與真實評估樣本分離 |
| 報告版本與交付匯出 | ReportManager、report task/version claims、Markdown／JSON／escaped HTML renderer | VERIFIED（保存／正式 PDF）／PARTIAL（長表格渲染） | 舊版本保留，引用與來源版本完整分頁匯出；正式中文 PDF 7 頁、圖表與引用已檢視；72 列長表格獨立預覽被工具阻擋，另列 BLOCKED_ENVIRONMENT |
| 真實付費生成／完整服務旅程 | 本輪沒有新增費用授權 | BLOCKED_AUTHORIZATION | 持續完成隔離、離線及示範能力，LIVE_E2E 不冒充 PASS |
| 檢查點分支 | 未證明 OASIS／記憶／圖譜一致恢复 | BLOCKED_CAPABILITY | 不把複製設定當成從第 N 輪恢復 |
| 新管理授權／定期搜尋模擬 | 本輪不允許擴權或自動付費 | BLOCKED_AUTHORIZATION | 保留已有配置，不搬移憑證或啟用排程 |

## Phase 0 之後的批次與測試邊界

1. **P0 執行與畫面副作用**：移除 mounted 生成／停止、固定 force；加入共用持久化工作與 run claims、完成屏障、不可覆寫執行及報告版本、孤兒辨識和識別碼驗證。
2. **證據底層**：source/version/span/reference 儲存、定位和語意狀態分開、保存缺失與相反來源、上傳與來源更新整合；EvidenceStore 子批 **31 passed**。
3. **圖譜與模型固定**：private graph snapshot、無 LLM namespace clone、source 唯讀、回條核對、背景更新 scope、未知結果單次呼叫；子批 **131 passed / 1 skipped**，該 skip 的專用 Neo4j 整合另跑 **12 passed**。專用容器無公開埠、未用 live volumes，已清理；細節見既有 `deploy/research-workbench-graph-safety-verification.md`。
4. **具名連線與階段設定**：profiles、stage mapping、能力標示、憑證分離和去密鑰 manifest；準備、模擬、報告使用各自凍結模型。測試檔含 `test_provider_profiles.py`、`test_preparation_retry_boundary.py`、`test_updater_model_snapshot.py`。
5. **統一工作台、回放與比較**：研究 context、舊頁連結、封存／複製、事件 ledger／cursor／時間 projection、報告與引用差異；新增離線品質樣本、三個合成案例和完整分頁匯出／安全 HTML 列印版。大事件效能結果另存既有 `deploy/workbench-event-benchmark.json`，不能代替瀏覽器驗收。
6. **explicit recovery 與 preparation 重試**：recover API 只呼叫 manager 核對，CSRF／Origin／Host 驗證；角色／設定未知回覆不 fallback 或重送，部分文件保留，Task＋Simulation 同步 needs_review。含零實體安全原因與任意 ValueError 隱私回歸的子批 **70 passed**。
7. **Phase 6 候選預覽／選取納入**：27 項新測試先 RED；與既有 source／workbench／graph preservation 合跑 **86 passed**。再補持久化與 cache 替換案例，最新 `test_web_source_adoption.py` **28 passed**。驗證沒有額外 fetch、跨研究拒絕、未知結果不重試、舊版本不漂移、provider 關閉／重啟後仍可離線 adopt。
8. **最後獨立 P0 review 與修復**：實證 source writer 可覆寫已完成 ontology metadata，以及解析文件時改設定會污染已 claimed 工作；新測試先 **3 failed / 1 passed**。跨程序 gate 與 claim 時模型固定後，`test_ontology_input_gate.py` 加 ontology errors／graph preservation／web adoption 子批 **37 passed**。含獨立 spawn process 真正互斥，以及生成期間保存新證據不改既有分析輸入。
9. **報告未知結果與公開錯誤保護**：大綱 timeout／空 JSON／錯誤結構不 fallback；空章節、假工具結果與未知工具錯誤不繼續或標完成。runner 非零退出及圖譜更新錯誤不公開 log tail／provider body。負責代理回報含 report 17 項新回歸及品質／匯出／事件／producer 等整合子批 **167 passed**；此為隔離測試，沒有真實模型呼叫。
10. **訪談程序存活與歷史只讀**：修復 heartbeat 可比 producer 多存活 30 秒，以及 Step5 原無可訪談狀態核對。API／直接 runner 入口都查本 worker 的存活程序；頁面保留未送出問題、顯示保存回答，不把已保存角色數說成仍可訪談數。加入送出前再查、問卷、不可核對及跨情境舊回覆回歸；前端整套 **255 passed**（14 files）。後端訪談／history／updater／execution 子批 **38 passed**（network=none），含 stop_all error body 去敏；本機 idle 後端已更新；未用 live 資料啟動訪談故障注入。

所有上列後端測試均使用 network=none、暫存 uploads／SQLite 與合成資料；只有專用 Neo4j 測試用隔離容器的 loopback。沒有以真實 key、搜尋或付費模型補足測試。最終前端保存的 `deploy/workbench-frontend-verified.json` 記錄 **285 passed**，`deploy/workbench-sources-regression.json` 記錄來源相關 **27 passed**；它們是各自程式快照，最終全量結果見末尾交付驗收。舊 `*-latest`／`*-final` 檔名本身不代表通過，部分中途紀錄 exit_code=1，不能直接當交付證據。

## 最後 P0 核對

- **已修且隔離測試通過**：來源材料化和 ontology claim/freeze 競態；ontology 模型於 claim 前固定，task 保存去密鑰快照。生成期間可保存新來源，但不改本次 frozen input 或版本沿革。
- **FIX_VERIFIED_OFFLINE**：報告 `plan_outline` 的預設三章 fallback／零章大綱已移除；無效大綱、空章節與工具未知結果拒絕完成，停止後續模型呼叫並保存 needs_review。負責代理回報整合子批 167 passed。
- **FIX_VERIFIED_OFFLINE**：runner 不再將 simulation.log 尾端拼入 public error；圖譜 updater stop_all 聚合也只保留例外型別，避免 provider body／來源片段被再發布到一般狀態。
- **FIX_VERIFIED_OFFLINE**：程序退出後即使 heartbeat 尚新，也拒絕新訪談；歷史 API 及前端保持唯讀可用。沒有將「模擬完成但 producer 仍存活」錯當成不能訪談，亦不將保存歷史冒充新生成成功。
- **分層驗收已記錄**：全量測試、建置、部署、畫面及正式 PDF 的結果見「交付驗收」。無 key 契約使用隔離設定；live 案例未刪除原使用者 key，且沒有呼叫模型。
- **PARTIAL**：正式生成物件的自動 evidence citation／語意追溯；目前提供人工附加來源引句與定位檢查，不將其寫成自動推導的證明。

## 執行順序與共用約束

1. 收斂最後 review 的 P0 修復並重跑受影響契約。
2. 由主流程完成最終全量測試、部署／資料保留核對及實際瀏覽器與列印驗收。
3. 真實生成、問題搜尋、檢查點分支與選用管理授權獨立列示；不得用合成成功替代。

故障注入、重啟與競態測試一律使用隔離目錄／容器。執行紀錄放入現有 uploads 下的本機 SQLite，避免新增外部服務；金鑰只留在既有私有設定，公開 manifest 不含憑證。所有新增能力都要接回目前 app，不能以 fixture 宣稱真實模型成功。

## 交付驗收（2026-10-03，Australia/Sydney）

### 測試、部署與操作

- 後端全套：15:22:01–15:25:05，**534 passed / 1 skipped / 1 warning**，175.72 秒。命令 `python -m pytest -q`，Docker `--network none`，未掛载 live uploads 或真实 key。跳過的是專用 Neo4j 整合，另以隔離 Neo4j 完成 **12 passed**；warning 為 Graphiti 依賴的 Pydantic 舊語法提醒。
- 最後後端小修：歷史 API 回傳實際保存的 report_status，缺失、錯配與未知值維持 null；保留原查詢介面。15:41:12–15:41:18，相關 **18 passed**。全套 534 是此小修前快照，18 不是額外可相加的成功數。
- 最終前端：16:26 起，**285 passed / 0 failed**。包含停止 run 的舊報告不可稱完整成功、首頁唯讀進行中工作、讀報告時顯示載入中、回放／引用／設定／對比／三語／控制項對比度。命令為 `node node_modules/vitest/vitest.mjs run --reporter=json --outputFile=../deploy/workbench-frontend-verified.json`。本機 npm 的 `--run` 轉交不相容曾失敗，改用已安裝的 Vitest 入口，未更改 assertion。
- 最終 Vite build 成功，5.57 秒；backend／Graphiti、frontend 都由本 checkout 重建並更新本機 Compose。重啟前核對後端沒有 OASIS producer；只重建閒置應用容器，Neo4j 未重啟、volumes 未刪除。開發程序因工具重連退出後已恢復同一 3000 埠，僅綁定 loopback。
- 分層證據：`deploy/workbench-backend-verified.json|log`、`workbench-history-delta.json|log`、`workbench-frontend-verified.json`、`workbench-ui-build.txt`、`workbench-delivery-verification.json`。小批次輸出與較早 146／261、278／284 不當作最後全套結果。
- 本輪實際開啟三個合成案例，操作來源版本／引句、事件逐步回放、簡報、刷新保留 run/seq、保存事件引用後回到相同 run/seq、情境比較、品質與匯出。story 比較每邊 6 筆事件，首差異 #4；產品案例來源引用定位 10/10、來源可用 2/2，均為合成資料而非準確率。
- 舊資料相容：開啟既有 8 節點／20 關係圖譜，搜尋、文字表格、節點詳情與焦點返回可用；舊報告內容可讀，訪談入口提示原 producer 無法核對，沒有送出新問題。首頁舊報告旁已實際顯示「執行：已停止」，不改寫歷史 status。
- 畫面範圍：390／768／1440 CSS 寬度、深／淺／系統模式、繁中及英文；Inspector 的 Escape／焦點返回／焦點限制、手機導覽及搜尋已操作。對比修正涵蓋文字與控制邊框，21 個 token 回歸；不宣稱全站 WCAG 完整認證。原生 200% 瀏覽器縮放仍未驗證，CSS viewport 重排不作替代證明。
- Browser console 最後讀取沒有警告／錯誤。`workbench-event-reference-ui.json` 為未截斷的該次引用往返紀錄，只有本地引用 POST，沒有 start／generate／fetch；較早 `workbench-browser-network.json` 標記 truncated，不能證明整輪完整網路流量。
- 正式匯出流程產出 `deploy/workbench-contradiction.pdf`：7 頁 A4、214200 bytes，實際檢查中文、引用、品質 SVG 與數值／限制。定位比例 6/9、來源可用 2/2，分母與定義保留。72 列長表格另有正式 renderer 產生的合成 HTML／manifest／產生器，但該份 PDF 的視覺驗收被工具阻擋。

### 保留資料、用量與安全

- 核對原有 130 個檔案：**129 個位元組完全相同、0 缺失**；唯一改變是既有 `source-imports/ledger.sqlite` 的增量 `plan_projects` schema，新增表 0 行。原有 6 筆 completed 計畫、2 筆 cache、歷史 attempted=2 保留；最後計畫時間早於本輪。新資料為三個合成研究、它們的引用／事件、持久化工作與證據 ledger。
- 沒有本輪真實模型生成、網頁搜尋／擷取或新管理連結；未增加 Firecrawl 每次 3／每日 10 擷取嘗試上限，時區仍 Australia/Sydney。沒有外部供應商用量帳單可供本輪對帳，因此不寫「帳戶成本為零」。
- 更新後以白名單重讀 `DO_NOT_TRACK=1`、HF telemetry=1、OTEL disabled=true、Langfuse enabled/tracing=false、Graphiti telemetry=false、Neo4j usage report=false。這是有效設定核對，沒有以此宣稱經封包擷取證明完全零網路。
- 模型 key 與管理授權仍留於原私有配置；未新增／搬移 9Router 管理憑證。能力測試只保留已驗證層級，不把模型清單成功寫成生成或結構化輸出成功。
- 候選提交沒有 uploads、設定私鑰、SQLite 或匯出文件。合成安全測試中的假 key 不是 live key。精確路徑清單見 `RESEARCH-WORKBENCH-CHANGES.md`。

### 效能與適用範圍

- Windows 11 build 26200；Core Ultra 9 285HX（24 核／24 邏輯處理器），191.69 GiB RAM。16:26 idle 容器記憶體約 backend 74.82 MiB／Graphiti 997.2 MiB／frontend 20.34 MiB，僅瞬時樣本，不是壓測峰值。
- 隔離合成 100／1000／10000 事件，讀 100 筆中位延遲分別 1.22／1.97／15.48 ms；回傳約 59 KB。10000 事件歷史 projection 120.05 ms、回傳上限 200 筆約 123 KB；兩側各 10000 比較約 900.93 ms。包含服務與匯入檢查，不含 HTTP、瀏覽器、模型；冷啟動與同時測試會影響樣本。
- Windows bind mount 的小型正式 HTML 匯出曾需 34.057 秒；共用 SQLite 連線及去除重複查詢後同一樣本 2.338 秒。其他 read-only API 樣本 2.382–3.039 秒；不是所有研究的延遲保證。保留 FULL 同步、foreign_keys、rollback、檔案身分與跨程序測試。
- 證據：`deploy/workbench-event-benchmark-final.json`、`workbench-performance-environment.json`、`workbench-live-read-optimized.json`。原 renderer 保留；大圖譜 FPS／瀏覽器記憶體及全设备效能未完整量測，不宣稱任意規模流暢。

### 尚未完成與確切原因

- **BLOCKED_AUTHORIZATION**：LIVE_E2E、實際問題搜尋／擷取、付費能力測試、重複生成／敏感性批次、啟用排程、新 9Router 管理連結。金鑰存在不當作授權。
- **BLOCKED_CAPABILITY**：第 N 輪 OASIS／記憶／圖譜一致檢查點恢復。配置複製只能建立新草稿；回放 reducer 僅重建保存事件投影，不冒充完整世界或代理記憶。
- **BLOCKED_ENVIRONMENT**：72 列長表格的臨時預覽服務被 automatic approval review 拒絕，工具只回報 blocked by policy；既有 Vite 檔案預覽也被瀏覽器拒絕。未繞過、未把 HTML 產生成功說成長表格 PDF PASS。
- **PARTIAL**：正式生成的逐物件自動引用／語意支持核驗；目前提供穩定版本、人工附加引用、定位檢查與缺口呈現。歷史輪次沒有足夠快照時不顯示最終圖譜當早期狀態。原生 200% 縮放及完整效能／可及性矩陣尚未驗收。
- **NOT_APPLICABLE（本輪）**：React／Next.js 重寫、轉回 Zep Cloud、雲端 Langfuse telemetry、另一套搜尋服務；與明確保留架構及授權界線不符。其餘未驗證項目不使用此標籤掩蓋。
