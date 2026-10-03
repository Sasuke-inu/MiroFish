# MiroFish 本機安裝與使用

更新日期：2026-10-02。專案位置：`D:\Dev\Projects\mirofish`。

## 現在可以使用什麼

開啟 **http://localhost:3100**，即可上傳文件並讓模型分析內容。
模型已接到這台電腦現有的 **9Router**；目前使用 `cx/gpt-5.6-luna`。

圖譜服務已換成自行架設的 **Graphiti＋Neo4j**，文字向量在本機使用 CPU 處理。
現在不需要 Zep 帳號或金鑰。上傳、建立圖譜、生成角色、雙平台模擬與報告可在原有介面依序操作。
圖譜和記憶保存於本機；文字分析仍走上述 9Router 模型連線。

已完成的網頁範例：[咖啡店桌遊活動分析](http://localhost:3100/process/proj_75860bfb4790)。
這份範例內容與所有測試角色都是虛構的。

## 日常開啟與停止

1. 先確認 Docker Desktop 與 9Router 已啟動。
2. 雙擊專案內的 **Start-MiroFish.cmd**，它會啟動網站並開啟瀏覽器。
3. 使用完後，可雙擊 **Stop-MiroFish.cmd** 停止 MiroFish；已儲存的資料仍保留。

網站目前只供這台電腦使用。對外開放或整機重新開機後的自動恢復，尚未列入此次驗證。

## 圖譜設定

本機 `.env` 已設 `GRAPH_PROVIDER=graphiti`，本機驗證金鑰與資料庫密碼亦已產生。
`ZEP_API_KEY` 維持空白即可使用，不需要另外註冊雲端服務。
`.env` 已排除在 Git 與 Docker 建置內容之外，請勿將金鑰貼到聊天或公開上傳。
各服務的用途、資料位置和維護限制，見 `ZEP-REPLACEMENT-ZH-TW.md`。

## 為什麼這次選 Docker

Docker 將 Python、網站工具與模擬套件放在獨立環境，適合這台 Windows 電腦。
這次建立了可自行修改及重建的版本，使用 Node 22、Python 3.11、Nginx 和 Waitress。
模型請求走既有的 9Router，模擬的文字向量處理使用 CPU 版 PyTorch，不需要下載 CUDA 執行套件。

後端服務：`http://127.0.0.1:5001`。
模型連線位址在 Docker 內是 `http://host.docker.internal:20128/v1`。
9Router 服務在本機；模型運算仍由它所選的模型供應商處理。
此次採用你選擇的 9Router 方案，沒有另外建立 OpenCode 直接連線。
圖譜已由 Graphiti＋Neo4j 取代 Zep Cloud；9Router 專門提供文字模型連線。

## 已修正的問題

- 原始容器使用的 Node 版本與新版網站建置工具不符，改用 Node 22 建置。
- Docker 可以連接本機 9Router，並修正帶有供應商前綴的 GPT 模型參數判斷。
- 缺少 Zep 時，網站仍可啟動並完成內容分析；圖譜操作會清楚顯示等待設定。
- 修正分析已完成卻仍顯示「生成中」、首頁錯誤宣稱整套流程就緒的問題。
- 修正模擬初始貼文在第一輪再次計入動作紀錄的問題。
- 網站代理會重新解析後端位址，支援後端容器重建後繼續連線。
- 更新有已知安全問題的前端依賴，並更新後端套件。
- 整理 OASIS 過時的依賴清單；保留官方程式與授權檔，修改依賴版本及移除未使用的工具。
  來源、雜湊值與重製方式記錄在 `backend/vendor/README.md`。
- 上傳資料、紀錄、模型及下載快取會保留；使用者資料不會被放入新建的映像檔。

## 隱私設定與驗證

Docker Desktop 的「Send usage statistics」已關閉，並讀回已儲存設定確認為 `false`。
MiroFish 已移除自動載入 Google Fonts 的連線，並設定 Hugging Face、CAMEL/Langfuse、
OpenTelemetry 及一般追蹤工具的關閉開關。原本會收集套件使用資訊的 Unstructured 已不再安裝。

實際呼叫已安裝的 Hugging Face 遙測函式，確認沒有啟動遙測執行緒；
CAMEL 的追蹤狀態也確認關閉。重啟 MiroFish 後已再次驗證這些設定。

Graphiti 和 Neo4j 的使用統計亦已關閉，並檢查實際元件設定與程式行為。
中文文字向量另在完全禁止網路的容器中實測成功。
下載套件、首次下載向量模型，以及呼叫 9Router 的模型供應商，仍會使用網路。
此次驗證的是已安裝元件的遙測關閉設定與程式行為，未進行網路封包擷取。

## 初次安裝測試（2026-10-01）

- 前端正式建置成功，兩個 MiroFish 容器皆通過健康檢查。
- 165 項測試通過，另有 42 個子案例通過；測試在禁止網路的容器內執行。
- 104 個後端套件的相依版本檢查通過。
- 前端 `npm audit`：0 個已知漏洞。
- 後端 `pip-audit`：103 個公開套件版本查詢，0 個已知漏洞。
  本機 OASIS 修正版以未改動程式的上游版本查詢，CPU 版 PyTorch 以相同公開版本查詢。
  本專案自己的程式由回歸測試與檢查涵蓋。
- 從主機與 Docker 內實際呼叫 9Router，皆取得非空白模型回覆。
- 網頁實際上傳 Markdown，模型產生 10 種角色／實體類型及 9 種關係類型，結果已保存。
- 使用兩個虛構角色，在 Twitter 與 Reddit 模擬環境各完成一輪真實模型互動，結果保存至 SQLite。
  這項獨立模擬使用手工測試角色，驗證模擬引擎，並未經過 Zep 圖譜產生角色的流程。
- 重啟及重建後端後，原有分析資料仍可讀取，網站代理與模型連線正常。

上述為初次安裝時的驗證結果，當時尚未接入圖譜服務。
後續本機圖譜接入結果見下一節。大型多輪模擬仍未列入本次驗證。

## 資料與測試紀錄的位置

- 分析資料與模擬資料：`backend/uploads/`。
- 服務紀錄：`backend/logs/`。
- 模型與下載快取：Docker 的 `mirofish-local_models`、`mirofish-local_cache` 資料卷。
- 測試結果：`deploy/tests.log`。
- 最後一次實際模擬紀錄：`deploy/oasis-smoke-final.log`。
- 模擬結果：`backend/uploads/installation-check-final/`。
- 套件檢查：`deploy/npm-audit.json`、`deploy/python-audit.json`。
- 驗證摘要：`deploy/validation.json`。

安裝階段已實際操作與讀取頁面，當時畫面擷取不可用。後續介面改版已取得實際畫面，保存於 `deploy/ui-home-ready.png`。

## 後續介面改版（2026-10-01）

已部署米白、深藍與少量橘色的工作室介面，新增繁體中文，保留原有六個頁面與操作流程。
新增的 28 項介面測試全部通過；另在新版 Docker 映像中通過 138 項後端測試。
新版網站實際上傳並分析測試資料，保存至 `proj_575f0ce1f35b`，產生 10 種對象類型及 9 種關係類型。
遙測關閉設定重查通過，前端套件查詢仍為 0 個已知漏洞。

詳見 `UI-REDESIGN-ZH-TW.md`、`ZEP-REPLACEMENT-ZH-TW.md` 與 `deploy/ui-validation.json`。
這段紀錄描述介面初次改版時的結果；現在圖譜服務已切換至 Graphiti＋Neo4j。

## 本機圖譜接入（2026-10-02）

新增 Graphiti Core 0.30.2、Neo4j Community 5.26.31 和本機中文文字向量處理。
保留原有上傳、圖譜詳情、角色設定、雙平台模擬、報告、對話、問卷和歷史紀錄。
修正事件識別碼、模型回傳格式、模擬完成判斷、角色設定格式及報告工具連線問題。
重新開啟模擬頁會保留目前進度，不再強制重跑而清掉紀錄。

167 項後端回歸測試及 31 項介面測試通過。
109 個後端套件版本相容檢查通過；108 個公開套件的已知漏洞查詢為 0，前端查詢也為 0。
本機修正版套件的查詢方式沿用上述安裝階段說明，專案程式另由回歸測試驗證。
實際流程的回覆與各階段結果保存於 `deploy/graphiti-validation.json`。
修正前的虛構測試資料與紀錄仍保留，不會當成新的驗證成功結果。
圖譜容器與資料庫的重啟驗證另保存於該紀錄；沒有執行 Windows 整機重新開機測試。

正式網站已完成虛構資料上傳、圖譜建立、四位角色產生、雙平台兩輪模擬、記憶寫回，
以及四章報告生成與下載。報告各章實際使用三次搜尋工具，共十二次，並取得真實圖譜結果。
單人訪談、批次訪談、四人問卷、報告聊天和歷史紀錄亦通過實際驗證。
瀏覽器另實際完成角色對話及四人問卷；更新後重新讀取十七筆雙平台原始訪談回答成功。

可查看 [完成的測試報告](http://localhost:3100/report/report_8040406ad6d3)。
這是四位虛構角色、每平台兩輪的小規模測試，活動時段與起始公告為測試特別設定，
未用來宣稱大型或長時間模擬已通過。完成驗證後已關閉這份測試的訪談環境；
報告助手仍可搜尋本機圖譜回答問題，新的角色訪談需在新的模擬環境中進行。

## 需要重建或查看狀態時

在專案根目錄開啟 PowerShell：

```powershell
# 修改程式後重新建置並啟動
docker compose -f docker-compose.local.yml up -d --build --wait

# 查看是否正常運作
docker compose -f docker-compose.local.yml ps

# 查看最近的服務紀錄
docker compose -f docker-compose.local.yml logs --tail 50
```

使用的是 `Dockerfile.local` 和 `docker-compose.local.yml`。
原始碼版本：`39d849138ef254f6c737ab4c4705e5545dbe31d4`，加上本機修正。

官方資料：[MiroFish](https://github.com/666ghj/MiroFish)、
[OASIS](https://github.com/camel-ai/oasis/blob/main/pyproject.toml)、
[Docker 使用統計設定](https://docs.docker.com/desktop/settings-and-maintenance/settings/)。
