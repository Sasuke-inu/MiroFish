# MiroFish 程式碼審查報告

- 審查日期：2026-10-18（Australia/Sydney）
- 專案：`D:\Dev\Projects\mirofish`
- 分支：`codex/workspace-visual-refinement`
- 審查提交：`43d30e995ac42fc96a1908520622ba2cde85bec8`
- 狀態：僅完成審查；以下修正均未實作。

## 結論與閱讀方式

本輪確認 **17 個獨立問題：5 個 P1、10 個 P2、2 個 P3**。沒有確認到 P0 問題，也不能據此保證其他缺陷不存在。最需要先處理的是「未受一致保護的工作 API」及「不完整工作被標成完成」；介面能打開、語法檢查通過，不能取代這些完成條件。

- **P1／高優先**：可能觸發未經預期的工作、造成保存結果不完整，或阻斷發佈建置。應在相關工作或發佈前修正。
- **P2／一般優先**：在明確條件下導致卡住、錯讀、遺漏或返回錯誤版本。
- **P3／低優先**：影響較有限的紀錄正確性或資源清理問題。

這是一份原始碼審查與隔離重現報告。**沒有操作真實模型、付費搜尋、擷取、現有模擬或現有報告的刪除／重試，也沒有改動既有研究內容。**「隔離重現」使用合成資料、記憶體或暫存檔；不代表現行服務已實際發生相同故障。

| 編號 | 優先度 | 問題 | 證據方式 |
| --- | --- | --- | --- |
| R01 | P1 | 舊工作 API 未套用一致的來源與操作保護 | 原始碼、原 handler 與替身元件 |
| R02 | P1 | 模擬程式提前退出仍發出正常完成回條 | 原始 async 函式隔離重現 |
| R03 | P1 | 未執行圖譜更新仍標記圖譜完成 | 原始 runner 方法隔離重現 |
| R04 | P1 | 刪除生成中的報告後，背景工作重建缺章的完成報告 | 原始保存方法與暫存報告 |
| R05 | P1 | 預設 Dockerfile 在必要檔案複製前安裝本機依賴 | 建置階段與鎖定檔靜態核對 |
| R06 | P2 | 合法的文字分段設定可能永不結束 | 原始分段函式、有限步數觀察 |
| R07 | P2 | 未完成的日誌尾行會被永久跳過 | 原始讀取方法與合成檔案 |
| R08 | P2 | 來源恢復舊文字後，「最新」仍指向錯誤版本 | 原始 EvidenceStore、記憶體 SQLite |
| R09 | P2 | 開啟保存示範會走安裝／補寫路徑 | 前後端資料契約直接對照 |
| R10 | P2 | 部分報告隱藏已保存章節正文 | 原始 Vue 元件、記憶體 API |
| R11 | P2 | 定位同模擬事件後，返回時換成較新報告 | 原始 Vue 元件與記憶體路由 |
| R12 | P2 | 刪除最新報告後，生成請求重用已刪產物的舊工作 | 原始 task／report 方法、暫存資料 |
| R13 | P2 | 平台名稱可夾帶路徑，讀到另一模擬 | 原始讀取函式、合成 SQLite |
| R14 | P2 | 並行報告的控制台紀錄互相混入 | 原始日誌類別、合成報告 |
| R15 | P3 | 累計模擬時數欄位持續被寫成零 | 原始 producer／consumer 契約重現 |
| R16 | P2 | 宣告支援 Node 18，實際工具鏈不支援 | package／lockfile 的 engines 核對 |
| R17 | P3 | 報告下載的暫存檔沒有清理 | 原始 handler、虛擬檔案替身 |

## R01 — P1：舊工作 API 缺少一致的來源與操作保護

**位置：**[全域 CORS 設定](D:/Dev/Projects/mirofish/backend/app/__init__.py:43)、[既有設定保護](D:/Dev/Projects/mirofish/backend/app/api/settings.py:19)、[模型角色生成入口](D:/Dev/Projects/mirofish/backend/app/api/simulation.py:1572)。

**問題與影響：**設定與工作台 API 會檢查 Host、來源及操作驗證碼，但舊的 graph、simulation、report API 沒有同樣的保護，還允許任意來源的 CORS。部分入口能讀研究或報告，部分能生成角色、刪除內容或控制程序。simulation 的共同檢查主要驗證識別碼，無法取代上述保護。角色生成入口預設可使用模型，因此此缺口也可能涉及用量。

**證據：**帶不受信任 Origin 的原 `generate_profiles` 函式，在替身環境仍進入 generator。這確認了應用層缺少攔截，**沒有實際利用瀏覽器或執行模型**。不同瀏覽器的本機網路權限可能另外阻擋部分情境，不能宣稱每種瀏覽器均可成功利用。README 的預設啟動方式另會監聽全部介面；本機 Compose 的 loopback 綁定雖縮小外部可達範圍，仍不是應用層來源驗證。

**修正步驟：**

1. 將本機 Host 與可信來源檢查放在所有 `/api` 共用入口；明確列出健康檢查等例外。
2. 所有修改、模型工作、刪除及程序控制操作均要求操作驗證碼（CSRF token）。上傳入口仍需支援 multipart，不能直接複製只接受 JSON 的限制。
3. 移除舊入口的任意來源 CORS；各前端 API client 統一取得並傳送 token。
4. 先讓缺 token、非法 Host、不可信 Origin 在進入模型或刪除程式前被拒絕，再確認可信介面的正常操作。

**驗證方式：**建立完整端點矩陣，以替身模型／程序控制器確認拒絕情境的副作用呼叫數為零；另測合法 JSON 與檔案上傳。不要直接在現有研究上嘗試刪除或生成。

## R02 — P1：提前退出仍發出正常完成回條

**位置：**[Twitter 完成回條](D:/Dev/Projects/mirofish/backend/scripts/run_parallel_simulation.py:1303)、[Reddit 完成回條](D:/Dev/Projects/mirofish/backend/scripts/run_parallel_simulation.py:1506)、[runner 接收回條](D:/Dev/Projects/mirofish/backend/app/services/simulation_runner.py:985)。

**問題與影響：**兩個平台遇到 `_shutdown_event` 會跳出迴圈，隨後仍無條件寫入 `simulation_end`，而且填入的是計畫輪數。runner 主要核對 run／attempt 身分與事件種類，未核對退出原因及實際完成輪數。因此只對模擬子程序發出外部 SIGTERM／SIGINT、沒有經過後端停止 API 時，提前退出可能被判為正常完成。

**隔離證據：**以原始兩個 async 函式搭配替身環境，計畫 10 輪、事先設定退出事件：

```text
Twitter：實際執行正輪次 0；完成回條仍為 (10, 0)
Reddit：實際執行正輪次 0；完成回條仍為 (10, 0)
```

正常停止 API 已有 manual-stop 防線；不能把本問題描述成「所有停止操作都會誤判」。

**修正步驟：**

1. 在 producer 記錄實際完成輪數與退出原因。
2. 只有自然完成預定工作才發正常完成回條。
3. 提前退出發送 stopped／interrupted 回條，不把計畫輪數填成已完成輪數。
4. runner 同時驗證退出原因、輪數、啟用平台及 run／attempt，再決定是否完成。

**驗證方式：**以替身環境測兩平台在零輪、中途、最後一輪前收到退出訊號，均不得產生正常完成；自然完成與既有停止 API 另測。

## R03 — P1：未更新圖譜，仍解除圖譜完成門檻

**位置：**[完成狀態設定](D:/Dev/Projects/mirofish/backend/app/services/simulation_runner.py:944)、[報告完成門檻](D:/Dev/Projects/mirofish/backend/app/api/report.py:107)、[品質判斷](D:/Dev/Projects/mirofish/backend/app/services/quality_evaluation.py:59)。

**問題與影響：**啟動 API 允許不啟用圖譜記憶更新。`_finish_run` 只有啟用 updater 時才等候圖譜寫入，最後卻只根據 completed、run_id、attempt_id 設 `graph_ready=true`。報告與品質檢查把這個旗標當成圖譜寫入已核對的證明，介面也因此解鎖報告工作。

**隔離證據：**

```json
{"updater_enabled":false,"status":"completed","graph_ready":true}
```

在此情況，模擬事件沒有透過 updater 加入圖譜，圖譜檢索仍可能只有模擬前的複製內容。報告工具另可能進行訪談，所以不能斷言所有報告內容都只來自原圖；已證實的是完成宣告與門檻失真。

**修正步驟：**

1. 分開保存「模擬迴圈完成」與「圖譜更新完成」。
2. 只有要求更新且成功取得 updater 完成回條時，才能設 `graph_ready=true`。
3. 未要求更新可保留模擬 completed，但圖譜旗標維持 false，說明未執行更新。
4. 報告與品質檢查沿用真正的寫入完成證據，不能只放寬介面按鈕。

**驗證方式：**未啟用、成功寫完、寫入失敗、缺平台完成回條四種情境中，只有成功寫完且平台工作完整的情況能解鎖相關報告。

## R04 — P1：生成中的報告被刪後，會重建為缺章的完成報告

**位置：**[刪除報告資料夾](D:/Dev/Projects/mirofish/backend/app/services/report_agent.py:2636)、[刪除 API](D:/Dev/Projects/mirofish/backend/app/api/report.py:591)、[報告組裝](D:/Dev/Projects/mirofish/backend/app/services/report_agent.py:2369)。

**問題與影響：**刪除未檢查報告是否仍有活動工作，也未和章節保存共用生命週期鎖。背景工作可以重新建立已刪資料夾；組裝只採用目前存在的章節檔，未核對大綱要求的完整集合。

**隔離證據：**兩章報告保存第一章後刪除，再保存第二章並依現有流程組裝：

```json
{"report_resurrected":true,"status":"completed","outline_section_count":2,"saved_section_count":1,"first_section_present":false,"second_section_present":true}
```

使用者會看見刪除成功，稍後報告又出現，而且主要全文缺章卻標成完成。記憶體大綱可能仍含文字，不能因此把缺章全文視為完整。

**修正步驟：**

1. 刪除與生成狀態核對共用生命週期鎖。
2. 對仍在 pending／planning／generating 的報告拒絕刪除並回 409，不順便停止模型。
3. 組裝前核對預期章節與保存正文；缺章只能保留為部分或需檢查。
4. 若未來確需支援工作中刪除，另加刪除標記阻止背景復活；目前最小修正是拒絕活動中刪除。

**驗證方式：**在第一、第二章之間嘗試刪除，應被拒絕；另故意移除暫存測試報告的一章，確認組裝不會宣告 completed。

## R05 — P1：預設 Dockerfile 的依賴安裝階段缺少必要檔案

**位置：**[複製與安裝順序](D:/Dev/Projects/mirofish/Dockerfile:14)、[本機 wheel 宣告](D:/Dev/Projects/mirofish/backend/pyproject.toml:66)、[發佈工作採用的 Dockerfile](D:/Dev/Projects/mirofish/.github/workflows/docker-image.yml:56)。

**問題與影響：**預設 Dockerfile 在第 21 行執行 `uv sync --frozen`，但當時只複製了 pyproject 與 lockfile；鎖定依賴要求的 `backend/vendor/camel_oasis-0.2.5+mirofish.1-py3-none-any.whl` 要到後面的 `COPY . .` 才進入映像。安裝專案本身也在來源複製之前執行。乾淨建置無法取得該階段必須存在的檔案，會阻斷採用此 Dockerfile 的發佈流程。

**證據界線：**這是建置階段的直接檔案相依矛盾，未執行 Docker build，也沒有重建目前服務。`Dockerfile.local` 有先複製 vendor 並分開安裝專案的處理，不能將預設檔案問題誤稱為現有本機映像已故障。

**修正步驟：**

1. 先複製 vendor wheel 至鎖定檔要求的位置。
2. 在來源尚未複製的快取層使用 `uv sync --frozen --no-install-project`。
3. 複製專案來源後，再執行專案安裝。
4. 對照發佈工作實際使用的 Dockerfile，避免只改到本機版本。

**驗證方式：**另行獲准建置後，在乾淨環境檢查依賴層與完整映像；不使用現有服務重建作為審查測試。Node 版本問題另見 R16。

## R06 — P2：合法的分段設定可能使工作永不結束

**位置：**[分段位置更新](D:/Dev/Projects/mirofish/backend/app/utils/file_parser.py:189)、[API 接受條件](D:/Dev/Projects/mirofish/backend/app/api/graph.py:604)、[背景工作實際呼叫](D:/Dev/Projects/mirofish/backend/app/api/graph.py:687)。

**問題與影響：**程式會為了在句尾切段而縮短 end，接著仍用 `end - overlap` 作為下一起點。API 雖保證 overlap 小於原設定段長，卻不保證它小於縮短後的段長，導致起點倒退及反覆 append。研究進入 building 後可能卡在分段，持續占用 CPU 與記憶體。

**有限步數重現：**

```text
chunk_size=100、overlap=80、文字="x"*40+"。"+"y"*200
起點：0 → -39 → -19 → 1 → -39 → -19 → 1 → …
```

500／450 的合法組合亦出現循環。觀察器在有限輪次主動停止，沒有執行無界的資源耗盡測試。

**修正步驟：**

1. 句尾候選必須滿足下一起點嚴格大於目前起點；不滿足時採原固定長度邊界。
2. 底層分段函式自行驗證 size／overlap，不能只依靠 API。
3. 加入嚴格前進條件；不能以靜默丟掉文字的方式避免循環。

**驗證方式：**測上述兩組、零 overlap、接近上限 overlap、各種句尾及長文字，確認有限時間完成、文字完整涵蓋、起點嚴格遞增。

## R07 — P2：未完成日誌尾行會永久被略過

**位置：**[讀取日誌](D:/Dev/Projects/mirofish/backend/app/services/simulation_runner.py:979)、[解碼失敗後的游標](D:/Dev/Projects/mirofish/backend/app/services/simulation_runner.py:1064)、[producer 寫入](D:/Dev/Projects/mirofish/backend/scripts/action_logger.py:82)。

**問題與影響：**monitor 在子程序仍存活時持續讀日誌。若剛好讀到尚未寫完的 JSON 尾行，解碼失敗會被忽略，游標卻前進到檔尾。稍後同一行補齊，已經越過的開頭不會再讀，事件因此無法進入動作狀態及圖譜 updater。

**隔離證據：**先寫半筆、讀取、補齊、從原返回游標再讀：

```json
{"first_saved_offset":52,"final_saved_offset":105,"complete_lines_in_file":1,"recorded_actions":0}
```

這證明未完成尾行處理有缺陷；**未量測現行程序是否曾出現半行或其發生頻率**，也不能宣稱每次正常 append 必然會被分段觀察到。

**修正步驟：**

1. 以位元組追蹤每行開始位置，保留尚無換行的尾段。
2. 只在完整解析並接受事件後推進游標。
3. 完整但損壞的行應記錄資料缺口，不能靜默視為完整輸入。
4. 補齊後只處理一次，避免修正後重複寫入事件。

**驗證方式：**在 JSON 任意位置、包含中文字 UTF-8 字元中間切開；補齊後事件應恰好收到一次。損壞完整行必須留下可見的缺口狀態。

## R08 — P2：來源恢復舊內容後，「最新」仍可能錯誤

**位置：**[相同內容直接重用舊版本](D:/Dev/Projects/mirofish/backend/app/services/evidence_store.py:162)、[版本排序](D:/Dev/Projects/mirofish/backend/app/services/evidence_store.py:348)、[草稿採用第一筆版本](D:/Dev/Projects/mirofish/backend/app/services/research_workbench.py:168)。

**問題與影響：**相同來源、相同 hash 會重用既有版本，這有助避免重複內容，但系統沒有另外保存「這次最新觀察到哪個版本」。最新版本仍依新插入紀錄排序。來源從 A 改為 B 再恢復 A 時，API 返回 A，但清單與草稿組裝仍使用 B；來源曾標缺失後恢復原文，也可能仍顯示缺失。

**以原始 EvidenceStore、記憶體 SQLite 重現：**

```text
A → B → A：最後保存回應為 A；list_versions(limit=1) 卻為 B。
A → missing → A：最後保存回應為 saved/A；最新項仍是 missing。
```

草稿組裝會從 `list_versions(..., limit=1)` 取內容，故這不只是排序外觀，還會影響後續輸入；已凍結的舊報告快照則不應因此改寫。

**修正步驟：**

1. 保留不可變內容版本與既有引用，不更新舊版本的文字、時間或 ID。
2. 另存每次採用／觀察的 version_id 與時間，或獨立的目前版本指標；與保存動作放在同一交易。
3. 清單、草稿輸入、複製與品質檢查改用該最新觀察結果，而非把「最新插入的不同文字」當成最新來源。
4. 對已存在資料採保守遷移；沒有保存過的歷史觀察不能補造。

**驗證方式：**A→B→A 與 A→missing→A 最後均採用 A；舊報告引用仍指向原版本；重複同一請求不得製造重複內容。

## R09 — P2：開啟保存示範實際會走安裝／補寫路徑

**位置：**[示範連結判斷](D:/Dev/Projects/mirofish/frontend/src/views/WorkbenchView.vue:29)、[開啟實際呼叫](D:/Dev/Projects/mirofish/frontend/src/views/WorkbenchView.vue:202)、[後端保存標記](D:/Dev/Projects/mirofish/backend/app/services/workbench_demos.py:35)。

**問題與影響：**前端用 `item.demo === demo.id` 判斷示範是否已存在；後端保存的標記是 `synthetic-fixture-v1`，目錄 ID 卻是 `story` 等值，兩者不會相等。按鈕因此呼叫 POST 安裝。後端即使找到已安裝研究，仍會進 `_seed`，可能新增缺少的來源或引用，而非單純讀保存報告。另以第一頁 12 個研究判斷是否存在，亦不足以可靠找到較早的示範。

本輪重新核對的是現行原始碼契約，沒有重新點擊該 live 按鈕。上一輪使用者驗收仍未完成；本問題是代理發現的阻擋，不能寫成使用者操作失敗。

**修正步驟：**

1. 由既有 `demo_installations` 對照，讓示範目錄的 GET 回覆明確包含已保存的 project_id。
2. 已存在項目使用直接研究連結，不再呼叫 install／seed。
3. 不以名稱、通用 synthetic 標記或第一頁研究清單猜測對應關係。
4. 尚未安裝時，把建立示範與閱讀既有內容明確區分；不要在「開啟」時默默補寫歷史資料。

**驗證方式：**使用真正的 `synthetic-fixture-v1` 標記，以及超過 12 份研究的資料；開啟既有故事示範不得送安裝 POST，來源、引用與報告版本均不變。現有測試以 `demo:'story'` 建立資料，未涵蓋實際保存格式。

## R10 — P2：部分報告隱藏已保存的正文

**位置：**[整份章節開關](D:/Dev/Projects/mirofish/frontend/src/views/WorkbenchView.vue:131)、[正文顯示條件](D:/Dev/Projects/mirofish/frontend/src/views/WorkbenchView.vue:71)、[後端逐節保存](D:/Dev/Projects/mirofish/backend/app/services/report_agent.py:1748)。

**問題與影響：**`reportHasSections` 要求每節都有 content；只要一節未完成，就隱藏全部章節正文，改顯示完整 Markdown 或摘要。然而後端逐節保存，最後才組裝完整 Markdown。中斷報告很可能已有第一節正文、第二節空白、整份 Markdown 仍空。

**原始 Vue 元件隔離結果：**保存的部分報告與章節標題有顯示，但合成正文 `PRESERVED_SECTION_BODY` 沒有顯示。資料仍存在，使用者卻可能誤以為沒保存。

**修正步驟：**

1. 分開判斷完整 Markdown 與各節正文是否存在。
2. 沒有完整 Markdown 時，每節獨立顯示已有內容。
3. 空白節保留尚未保存的說明；保持部分報告標示與引用 ID。
4. 有完整全文時避免把相同正文重複顯示。

**驗證方式：**測「一節完成、一節空白、全文空白」；已保存正文必須可讀，空白節不得補造內容。現有部分報告測試直接提供非空 `markdown_content`，因此漏掉此情境。

## R11 — P2：定位事件後，返回時偷偷換報告版本

**位置：**[事件引用連結](D:/Dev/Projects/mirofish/frontend/src/components/EventReferenceLink.vue:2)、[事件位置回存](D:/Dev/Projects/mirofish/frontend/src/components/RunReplay.vue:34)。

**問題與影響：**定位事件重建路由時，只保留 section／ref_run／ref_event，丟掉原 report／replay。事件還原後，回存邏輯因原 replay 已遺失而清除報告選擇；工作台接著自動選最新版。即使事件仍屬同一模擬，也會發生。

**原始元件隔離重現：**讀同一模擬的第 1 版 `older` → 定位同 run 事件 → 返回報告：

```json
{"olderVisible":false,"newerVisible":true,"selected_report":"newer"}
```

這是「模擬事件引用」路徑的已確認缺陷；不能據此說「原文定位視窗」也已證實有相同問題。

**修正步驟：**

1. 同研究內定位事件時，保留原 query 的 replay／report，只覆寫事件定位欄位。
2. 真正跨模擬時，才清除不相容報告。
3. 獨立報告頁如要連至事件，明確傳入該報告及模擬的返回資訊。

**驗證方式：**舊版→同模擬事件→返回→重新整理，仍為舊版；跨模擬事件另測不得套用錯誤版本。既有來源視窗往返測試與跨模擬測試，不能涵蓋本情境。

## R12 — P2：刪除最新報告後，生成請求重用不存在的產物

**位置：**[版本編號與工作重用](D:/Dev/Projects/mirofish/backend/app/api/report.py:242)、[永久 resource_key](D:/Dev/Projects/mirofish/backend/app/models/task.py:81)。

**問題與影響：**下一版依仍存在的最新報告加一，但刪報告不刪舊工作，工作 key 又永久唯一。刪掉 v1 後，再次生成仍算 v1，結果重用 completed 舊工作，返回已刪 report_id；刪最新 vN 也有同樣問題。

**原始方法隔離結果：**

```json
{"next_calculated_version":1,"new_task_created":false,"reused_report_exists":false,"reused_task_status":"completed"}
```

API 宣稱已有完成結果，實際保存產物不存在，新工作也沒有開始。

**修正步驟：**

1. 在持久化版本索引保存已使用編號；刪除正文不回收版本號。
2. 在交易內配發下一版並 claim 工作，避免並行衝突。
3. 返回 reused task 前確認產物存在；缺產物應回需檢查，不能回 already_generated。
4. 不藉刪舊 task key、覆寫舊版本來解鎖。

**驗證方式：**v1→刪除→新建應為 v2；v1/v2→刪 v2→新建應為 v3；同時兩個請求只認領同一份新工作。全部使用暫存資料。

## R13 — P2：平台名稱可導向另一模擬的資料庫

**位置：**[文章資料庫路徑](D:/Dev/Projects/mirofish/backend/app/api/simulation.py:2205)、[留言資料庫路徑](D:/Dev/Projects/mirofish/backend/app/api/simulation.py:2273)。

**問題與影響：**simulation_id 有驗證，但 platform 沒有白名單，直接加入檔案路徑。要求 A 的資料時，platform 可以帶 `../sim_B/reddit`，最後讀到 B 的資料庫。這是跨模擬錯讀與允許未核准路徑；本系統沒有在這裡定義多租戶權限，因此不誇大成繞過使用者權限或可讀任意檔案。

**隔離證據：**合成 A／B 資料庫中，對 A 傳上述 platform，posts 返回 `ONLY_SIM_B`，comments 返回 `ONLY_SIM_B_COMMENT`。

**修正步驟：**

1. 文章與留言共用平台驗證，只接受 `reddit` 或 `twitter`。
2. 使用既有模擬目錄解析方法，不再硬寫 uploads 相對路徑。
3. 對既有資料庫使用唯讀連線。
4. 路徑驗證失敗時先回 400，不能先嘗試開檔。

**驗證方式：**`../`、絕對路徑及 Windows 分隔符都應拒絕，且開檔替身未被呼叫；正常平台只能取得指定模擬的合成內容。

## R14 — P2：並行報告的控制台紀錄互相混入

**位置：**[報告共用 logger 的 handler](D:/Dev/Projects/mirofish/backend/app/services/report_agent.py:366)、[工具會保存查詢文字](D:/Dev/Projects/mirofish/backend/app/services/zep_tools.py:475)。

**問題與影響：**每份報告的 FileHandler 都掛在共用 logger，沒有報告／執行身分過濾。不同圖譜的報告可並行，兩份 handler 存活時都會收到另一份的紀錄，包括查詢文字與圖譜 ID。使用者因而看到錯誤的執行歷史，研究文字也會串入另一份報告。

**隔離證據：**以原日誌類別同時建立 report_A／report_B，交錯記錄兩筆合成查詢；兩份 console_log 均同時包含 A 與 B。

**修正步驟：**

1. 在報告工作開始時綁定 report_id／run_id。
2. 每份 handler 嚴格過濾該身分，或使用每份報告專屬 logger／adapter。
3. 工具服務及執行緒池明確傳遞相同脈絡。
4. 工作結束及錯誤路徑均移除 handler。

**驗證方式：**交錯執行兩份合成報告，各自只能保存自己的查詢；完成後 handler 數量回復原值。

## R15 — P3：累計模擬時數欄位持續為零

**位置：**[runner 讀取欄位](D:/Dev/Projects/mirofish/backend/app/services/simulation_runner.py:1021)、[producer 實際輸出](D:/Dev/Projects/mirofish/backend/scripts/action_logger.py:125)。

**問題與影響：**runner 每次 round_end 讀 `simulated_hours`，沒有便設零；producer 的 round_end 沒有該欄位，其他事件則使用不同欄名。以實際事件形狀隔離執行後，current_round 已為 2，平台及總模擬時數仍為零。

本輪沒有找到目前前端使用這三個時數欄位，因此只確認狀態 API 與保存紀錄不正確，不宣稱主畫面已顯示錯誤時數。

**修正步驟：**

1. 統一 producer／consumer 的累計時間欄位與單位。
2. 由已完成輪數與 minutes_per_round 計算；不能拿每日 0–23 點代替累計時間。
3. 舊資料缺欄保留未知，不在每輪重設成零。

**驗證方式：**測非 30 分鐘輪次、跨兩天、單／雙平台及 max_rounds 截短。

## R16 — P2：Node 支援聲明與實際依賴不符

**位置：**[根目錄 engines](D:/Dev/Projects/mirofish/package.json:17)、[前端工具依賴](D:/Dev/Projects/mirofish/frontend/package.json:19)、[安裝文件的 Node 18+](D:/Dev/Projects/mirofish/README-ZH.md:102)。

**問題與影響：**根目錄宣告 Node >=18，README 也寫 18+，但鎖定版本的 Vite 7.3.6 需要 `^20.19.0 || >=22.12.0`，Vitest 5.0.3 需要較新的 Node，JSDOM 30.1.1 更要求 `^22.22.2 || ^24.15.0 || >=26.0.0`。照文件使用 Node 18 的新環境無法正常使用這套工具鏈。前端 package 亦未宣告 engines，無法在入口及早指出真正條件。

**證據：**上述條件直接取自目前 `frontend/package-lock.json`，沒有依賴外部版本推測。本輪使用的 Node 為 22.23.3，前端語法與元件編譯檢查可執行；這不代表其他 Node 版本均已驗證。

**修正步驟：**

1. 選定符合目前完整工具鏈的支援版本，將根目錄與前端 engines 寫成一致條件。
2. 同步 README 與安裝說明，移除 Node 18+ 的承諾。
3. 預設 Dockerfile 明確提供相容 Node，不靠基底系統套件恰好滿足條件。
4. CI 使用相同版本範圍；不支援版本應在安裝或啟動前清楚失敗。

**驗證方式：**在宣告支援的乾淨環境完成安裝與前端檢查；不支援環境應得到明確版本訊息。此輪未另行安裝 Node 或下載依賴。

## R17 — P3：報告下載留下不清理的暫存檔

**位置：**[下載 fallback](D:/Dev/Projects/mirofish/backend/app/api/report.py:563)。

**問題與影響：**當報告 metadata 存在但全文 Markdown 檔不存在時，每次下載會建立 `delete=False` 暫存檔，傳給 send_file 後沒有清理。重複下載會累積研究文字副本及磁碟占用。

**證據：**以原 handler 與虛擬檔案替身重放三次，得到三個不同的保留檔；此項驗證沒有寫入實際磁碟。

**修正步驟：**

1. 優先使用 `io.BytesIO` 回傳 UTF-8 內容，省去磁碟暫存。
2. 若一定要用磁碟，在 response 關閉後可靠清理，錯誤路徑亦處理。
3. 與 R10 區分：下載內容來源及部分報告標示仍需正確，不能只解決檔案清理。

**驗證方式：**重複下載、傳送失敗及關閉連線後，暫存檔數不增加，下載內容與保存文字一致。

## 建議修正順序

這是待後續授權的修正計畫，本輪沒有執行。

1. **先收緊工作入口：R01、R06、R13。** 不可信請求先被拒絕；合法輸入也必須有限完成，讀取範圍限於指定模擬。
2. **再修完成與保存條件：R02、R03、R04、R07。** 提前退出、未更新圖譜、缺章、日誌缺口均不得被當成完整結果。
3. **修正版本一致性：R08、R12。** 最新來源與版本配發需要獨立保存狀態，不覆寫歷史版本。
4. **恢復使用者閱讀驗收：R09、R10、R11。** 小範圍修入口、部分正文與事件返回；不重新設計工作台。之後再讓使用者自行完成原先三個任務。
5. **在另行允許的建置範圍處理 R05、R16。** 先修檔案與版本條件，再做乾淨建置；不要以重建目前服務作為審查手段。
6. **補正紀錄與清理：R14、R15、R17。** 將並行紀錄隔開、時間欄位一致、避免下載殘留檔。

每一小批修正都應先用合成資料重現問題，再確認預期行為；不要為了讓測試通過，改寫舊研究、模擬狀態或報告版本。

## 本輪驗證與覆蓋界線

**實際完成：**

- 開始時核對分支、完整 HEAD 與乾淨工作區。
- 人工追蹤前端路由、研究與證據保存、task／run 狀態、producer／monitor、報告版本與刪除、API 保護、建置設定。
- 對上述可隔離問題執行原函式／元件重現；替身取代模型、圖譜、程序或網路。
- 136 個已追蹤 Python 檔案語法解析無錯誤。
- 39 個 Vue 元件解析／編譯及 16 個前端 JavaScript 檔案語法解析無錯誤。這些是語法檢查，不是業務流程驗收。

**沒有執行或不能據此確認：**

- 沒有重新跑完整 325 項前端測試；交接中的舊測試數不能當成本輪結果。
- 主機 Python 3.13.15 不符合專案宣告的 3.11／3.12，且缺完整後端依賴；沒有安裝依賴或宣稱完整後端整合測試通過。
- 沒有 Docker build、部署、重啟或 live 故障注入；也沒有重新確認 3000／3100 的現行服務版本或可用性。
- 沒有真實模型、費用／用量核對或語意支持驗證。
- 沒有即時依賴漏洞資料庫掃描；不對目前依賴作「零漏洞」保證。
- 沒有實際瀏覽器跨站攻擊測試或 OS 層日誌寫入原子性量測。

**保留為未確認風險、未計入 17 項：**來源匯入 adapter 先解析 DNS，但將原網址交給 Firecrawl 再處理。此 repo 無法證明下游對再次解析、轉址與瀏覽器子資源的內網防護是否完整；未檢查下游設定或發出擷取，因此不能稱為已證實可利用的 SSRF。

**已排除的疑點：**報告 manifest 預存 complete 字樣，但工作台對非 completed 的報告／模擬會強制顯示 partial；沒有只憑該字面值另列一筆誤標問題。現有 HTML escaping、設定 allowlist、模型端點 redirect 禁止等防護，也沒有被當作缺失。

## 使用者驗收與檔案紀錄

三個原訂任務仍為 **待使用者驗收**；沒有收到使用者完成或卡點回報。R09 是代理檢查發現的入口阻擋；其他隔離重現也不能寫成使用者驗收失敗或通過。

本輪僅新增本報告，並在既有交接文件補索引；沒有程式修正、提交、push 或 merge。任何後續真實模型旅程仍需獨立指定供應商、模型、外部呼叫範圍及費用／用量授權。

審查過程有一個僅含合成 SQLite 測試資料的暫存目錄未清理：`C:\Users\PC\AppData\Local\Temp\mirofish-review-idsooxqb`。自動安全審查在命令啟動前拒絕刪除，只回覆 blocked by policy、未提供具體原因；已保留且未重試。它不是現有研究或報告資料。
