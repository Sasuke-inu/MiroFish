# MiroFish 審查修正實作記錄（2026-10-18）

- 對應審查報告：CODE-REVIEW-2026-10-18.md（審查提交 43d30e9）
- 分支：codex/workspace-visual-refinement（6 條修正流以 --no-ff 逐條合併）
- 方法：每項「先紅後綠」；6 個獨立 worktree／分支並行（intake／simlife／reportlife／evidence／frontend／build）；父層負責合併、重跑驗證與獨立覆核
- 範圍：29 個提交、48 個檔案、+2432/−223 行

## 結果：17/17 完成

| 編號 | 修正摘要 | 主要提交 |
| --- | --- | --- |
| R01 | 全部 /api 加上共用本機來源＋CSRF 保護（multipart 可用）；CORS 由萬用字元收窄為本機清單；新增 GET /api/session 發 token；前端共用 axios 自動帶 X-MiroFish-CSRF | 1c61b71, cd91526 |
| R02 | producer 回條記錄實際完成輪數與退出原因（completed／stopped）；runner 對帶 reason 的回條嚴格驗證 | 7a7b66b, 9acf537 |
| R03 | graph_ready 只在「要求更新且 updater 成功收尾」為 true；新增 graph_update_status；報告／品質沿用該旗標 | 9acf537, fbad9f4 |
| R04 | 生成中報告刪除回 409；每報告生命週期鎖；組裝前核對章節完整，缺章標 NEEDS_REVIEW 不宣告 completed | 44eb9a0 |
| R05 | Dockerfile 先 COPY vendor 再 `uv sync --frozen --no-install-project`，`COPY . .` 後安裝專案 | 33431ec |
| R06 | 分段起點嚴格遞增；句尾切段只在仍前進時採用；函式層驗證 size/overlap；不靜默吞字 | 0223dbd |
| R07 | 日誌以位元組游標讀取；未完成尾行永不跳過；完整但損壞的行記 log_gaps 缺口 | 9acf537 |
| R08 | evidence_latest 最新觀察指標（與 add_version 同交易）；草稿／複製／品質／匯出改用；保守遷移 | 8566513, f9a7e1e |
| R09 | /demos 回覆含已安裝 project_id；前端改直連研究，安裝只由明確按鈕觸發 | da8e531, 0682160 |
| R10 | 部分報告逐節獨立顯示已保存正文；空白節顯示未保存說明；有全文時不重複顯示 | c62e48b |
| R11 | 定位事件保留原 replay／report；跨模擬才清除不相容報告 | c62e48b, 2ec84ef |
| R12 | report_versions 持久版本號（不回收）；配發＋claim 同一交易；重用前驗證產物存在，缺產物回 409 | 8b09755 |
| R13 | platform 白名單（twitter／reddit）；模擬目錄用既有解析器；SQLite 唯讀 file: URI；非法先回 400 | 222eb4c |
| R14 | 每份報告控制台日誌以 ContextVar 身分過濾；結束／錯誤路徑皆移除 handler | 0ae85b4 |
| R15 | round_end 帶累計 simulated_hours；runner 只在欄位存在時更新，缺欄保留不歸零 | 7a7b66b |
| R16 | engines＝`^22.22.2 \|\| ^24.15.0 \|\| >=26.0.0`（由 lockfile engines 交集推導）；Dockerfile 明確安裝 Node 22 | 6d21b38 |
| R17 | 下載 fallback 改 io.BytesIO，不再留 delete=False 暫存檔 | 4950051 |
| 連帶 | simulation_ipc 訪談閘門與 graph_ready 解耦（not_requested 的 completed 執行可受訪） | 746408c |
| 覆核修正 | 獨立覆核 6 項全部成立並修正：刪除中工作閘門（R04）、帳本活動認領重用（R12）、回條嚴格化（R02）、逐行處理缺口（R07）、inspector 採最新觀察版本（R08）、共用 client 改同源（R01） | c04acd4 |

## 最終驗證（合併後主樹）

- 後端：643 passed／7 failed／1 skipped。7 項失敗與未改動基線相同（test_system_status ×3、test_zep_retry_and_client ×3、test_storage_pool ×1），屬既有環境依賴問題，非本次回歸；基線為 534 passed／8 failed。
- 新增測試：後端 +109（共 14 個新測試檔）、前端 +16（325 → 341）。
- 前端：18 檔 341 全過；`npm run build` 成功。
- Docker（真實建置，非靜態判斷）：修正分支乾淨建置成功（mirofish-r05-verify，sha 1766cfe3；二次 12 層全快取）；合併後最終樹再建置成功（mirofish-final-verify，映像內 camel-oasis 0.2.5+mirofish.1 與 mirofish-backend 安裝正確、node v22.23.3）。

## 既定決策與界線

- R02 相容規則：改版前舊日誌沒有 exit_reason，無法區分「自然完成」與「被外部終止後補寫」，故不帶欄位者仍視為 completed；新 producer 產生的回條一律強制驗證。
- R03：未要求圖譜更新的完成執行保留 completed、graph_ready=false（報告維持不解鎖，符合審查要求）；訪談功能另經父層修正改以 graph_update_status=not_requested 放行。
- R08：版本歷史清單順序不變、不覆寫舊版本；「最新」以獨立指標判定，API 新增 latest_version_id。
- R12：刪除報告不回收版本號；重用作業前必檢查產物存在。
- 未執行：真實模型／付費服務、live 服務重啟、瀏覽器跨站實測；來源匯入的下游 SSRF 未確認風險仍在（同審查界線）。

## 覆核

（Codex 唯讀覆核，完整輸出：mirofish-worktrees/_evidence/codex-review-output.txt 與 codex-review2-output.txt）

- 覆核模型：gpt-6.1-sol（Codex CLI 0.163.0，read-only sandbox），對 `git diff 43d30e9...HEAD` 全量複核 17 項與新增缺陷。
- 第一輪結果：1×P1、5×P2，點名 R01／R02／R04／R07／R08／R12 未完整——逐項核實全部成立（含兩項真回歸：127.0.0.1 開啟時 cross-site 被拒、日誌派送失敗後事件永久跳過），已於 c04acd4 修正並補紅先綠後測試（後端 7 紅 → 34 綠；前端 2 紅 → 3 綠）。
- 第二輪（針對 c04acd4 follow-up 提交之聚焦覆核）：2×P2 殘留（R07 游標在處理前前進、R12 啟動失敗後殭屍認領），R01／R02／R04／R08 通過；殘留已修正於 e44859f，詳見下節。

## 第二輪覆核與修正（2026-10-18 收尾）

- 第一輪聚焦覆核的 codex session 在交付 verdict 前中斷（輸出無最終訊息）；以 `codex exec resume 01a14b16-d4c0-7201-901f-c0165c92a5db`（gpt-6.1-sol、read-only）續跑完成。完整輸出：`mirofish-worktrees/_evidence/codex-review2b-output.txt`。
- VERDICT 原文：`VERDICT: R07、R12 / 新增缺陷：啟動失敗後永久重用 pending 工作`。
- 修正（提交 e44859f，紅先綠）：
  1. R07 `_read_action_log`：游標改為只在整行成功處理、或已記錄可見缺口之後才前進；`json.loads` 的 ValueError（超長整數）／RecursionError（過深嵌套）與 JSONDecodeError 同列為損毀完整行並記 log_gaps，不再被外層 except 帶著已前進的游標跳過。
  2. R12 `api/report.py` generate：claim 之後的三段設定（初始保存、reader 登錄、執行緒啟動）納入統一錯誤清理——失敗時工作標 FAILED、解除已完成的登錄、已保存的初始報告標 FAILED；後續請求配發新版本，而非一直重用殭屍認領。
- 紅先綠證據：新增 `tests/test_action_log_ingest_gaps.py`、`tests/test_report_setup_failure_cleanup.py`（共 4 測試）；修正前 3 紅 1 綠（`_evidence/parent2/red-round2-fixes.txt`）；修正後鄰近 12 檔 84 綠（`_evidence/parent2/green-round2-fixes.txt`）。
- 修正後全套後端（父層複驗）：647 passed／7 failed／1 skipped，7 項與未改動基線相同（`_evidence/parent2/backend-full-after-round2.txt`）。前端本輪未變動，維持 341 passed 與 build 成功。
- 收尾：worktree 全部移除（fix/* 分支保留）；本檔、CODE-REVIEW 與 handoff 一併提交。

## 收尾輪（2026-10-18 後段）：基線、Docker、瀏覽器、SSRF、第三輪覆核、PR

- 基線 7 項失敗修正（a620022）：6 項為環境洩漏——本機根目錄 `.env` 設 GRAPH_PROVIDER=graphiti，使 zep 路徑契約測試（test_zep_retry_and_client ×3、test_system_status 的 zep 形狀斷言 ×2、graph/build 503 ×1）實際走到 graphiti 分支；測試改為明確 pin GRAPH_PROVIDER='zep'（只選分支、不改產品碼）。第 7 項（test_storage_pool 檔案替換）在 Windows 不成立（開啟中的 SQLite 檔被鎖、無法外部替換），改為 win32 skip（Linux 仍執行）。修正後全套：653 passed／0 failed／2 skipped（`_evidence/parent2/backend-full-final.txt`、`green-baseline-fixes.txt`）。
- Docker：於 a620022 樹真實建置成功（`mirofish-parent2-final`）；6c3b110 後再建置成功（`mirofish-final-pr`）（`_evidence/parent2/docker-build-final*.txt`）。
- 瀏覽器跨站實測（Playwright/Chromium 156 對執行中後端 5011 與 trusted 代理 3000；`_evidence/parent2/browser-crosssite-test.txt`）：
  - 跨站頁（127.0.0.1:9999）：GET /api/session 被 CORS 擋（無 ACAO，TypeError）；no-cors POST 伺服器回 403、JS 讀不到；JSON POST 之 preflight 被拒。
  - 同源 trusted 頁（127.0.0.1:3000 經 /api 代理）：GET /api/session 200＋token；帶 token POST 通過守衛、回 400 業務驗證（缺 simulation_id）。R01 於真實瀏覽器成立。
- SSRF 下游確認（原保留風險）：adapter 端（normalize_url：scheme／連接埠／非公網主機／文件副檔名白名單；fetch 前 assert_public_dns 全位址檢查；document 層再核最終 sourceURL）如原設計。實測下游：本機 Firecrawl（v2 API，`safeFetch`）在連線階段直接拒絕內網目標——對 host.docker.internal:9999 的抓取被 `Connection violated security rules`（safeFetch.js:88）擋下，重試引擎亦同（`_evidence/parent2/firecrawl-safefetch-block.txt`、`firecrawl-redirect-probe.txt`）。殘餘：未以公開網域實測「公開頁→轉址→內網」鏈；不同 Firecrawl 版本／設定仍需部署時核對。原「未確認」降級為「本機所跑版本具連線級防護已驗證」。
- 第三輪聚焦覆核（c04acd4..HEAD，gpt-6.1-sol read-only；`_evidence/codex-review3b-output.txt`）：1×P2——未啟動即失敗的報告（無 outline、無內文）仍被既有報告早退分支擋住，不帶 force 的重試無法產生新版本；已修正於 6c3b110（僅「FAILED 且零產出」放行一般重試），並補紅先綠重試測試（`_evidence/parent2/red-round3.txt`、`green-round3.txt`）。修正後全套：654 passed／0 failed／2 skipped。
- PR：本分支推送至 fork `Sasuke-inu/MiroFish`（上游 666ghj/MiroFish 為第三方 repo，本帳號僅讀取權，未對上游開 PR）並合併至 fork main；上游 repo 無 PR CI（workflow 僅 tag／排程觸發），品質門檻為本檔所列之全部本機驗證。
