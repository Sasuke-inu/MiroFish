# 模型、餘額與新版設定頁

更新日期：2026-10-03。

開發版：[設定頁](http://localhost:3000/settings)。Docker 版：[設定頁](http://localhost:3100/settings)。

## 使用方式

1. 在「模型與額度」選擇 OpenAI、OpenRouter、OpenCode Zen／Go、9Router，或自訂端點。
2. 填入服務網址及金鑰。原本的金鑰不會顯示在頁面；同一服務、同一網址留空可保留。更換服務或網址會清除正在輸入的金鑰。
3. 按「測試連線並讀取清單」，再選擇或輸入模型名稱。這個測試只讀取模型清單，不生成內容、不啟動模擬。
4. 按「儲存設定」。之後的新工作使用新設定；正在執行的模擬、報告或圖譜批次保留原設定。

自訂端點需支援 OpenAI Chat Completions。API 基底網址通常以 `/v1` 結尾；不要填完整的 `/chat/completions`。Docker 內連接此電腦上的服務使用 `host.docker.internal`。不需登入的自架服務可填入其接受的佔位金鑰，例如 `local`。只有模型清單成功，不能保證所有模型都支援完整模擬需要的能力。

OpenCode 直連僅允許已確認採用 Chat Completions 的模型；使用其他格式的模型請透過 9Router 轉接。這份相容清單會隨上游產品變更，新增模型須重新確認。

## 額度與餘額代表什麼

| 連線 | 設定頁顯示 | 限制 |
|---|---|---|
| OpenRouter | 這把 API 金鑰的剩餘支出額度 | 不是帳戶錢包；沒有金鑰上限時顯示說明，不顯示無限餘額 |
| OpenCode Go 直連 | 短期、每週、每月剩餘比例及重設時間 | 不是美元錢包餘額 |
| 9Router 的 OpenCode 帳戶 | 最近同步的錢包餘額及可取得的用量 | 需要獨立管理授權、選擇帳戶；過期快照會明確標示 |
| OpenAI、OpenCode Zen、自訂端點 | 顯示不提供標準餘額查詢 | 無法取得資料不會假裝是 0 |

9Router 連接工具：[Connect-9RouterBalance.ps1](deploy/Connect-9RouterBalance.ps1)。[操作與權限說明](deploy/Connect-9RouterBalance-ZH-TW.md)。它只把既有授權連結至本機 MiroFish，不修改 9Router、不登入 OpenCode、不更新付款設定。**CLI 授權本身有 9Router 管理權限，並非獨立唯讀金鑰。** 應在了解範圍後才連結；設定頁可「解除餘額連結」。

「更新額度與餘額」讀取 9Router 的現有資料，並不替你完成 OpenCode 帳單頁登入或錢包同步。若從未同步，會顯示尚無資料；有舊值時顯示來源時間與過期狀態。

## 資料收集與外觀

Firecrawl 繼續負責擷取指定網址；模型負責分析和模擬。更換模型服務不需要更換資料收集服務。指定網址擷取與關鍵字全網搜尋是不同功能；目前沒有自動啟用新的搜尋供應商。

原有每次最多 3 頁、每日 10 頁、24 小時快取仍保留，設定頁會讀取目前實際限制與用量。這是本機 Firecrawl 的使用限制，不代表所有外部服務都免費。

全站改用暖石灰、炭黑與琥珀色，保留淺色、深色、跟隨系統及三種介面語言。新版設定頁分成模型與額度、外觀與語言、資料收集、服務狀態；在設定中切換分頁不會丟失尚未儲存的模型欄位。

## 儲存與驗證

模型與額外餘額授權由本機服務保存於忽略版控的 `backend/uploads/settings/providers.json`。設定不會把金鑰回傳到頁面，也不存入瀏覽器偏好。Graphiti 掛載該設定資料夾為唯讀。請保護此電腦、設定資料夾及備份的存取權。

本次修復包含跨網址金鑰誤送、舊餘額回應覆蓋新連線、工作執行期間設定混用、原生啟動忽略已儲存設定，以及模型錯誤原文可能出現在紀錄中的問題。

- 前端：122 項測試通過，其中新增 19 項模型設定測試。[最終結果](deploy/provider-settings-final-tests.json)
- 後端：248 項測試通過；測試容器禁止網路。[結果](deploy/provider-settings-backend-validation.json)
- 配色：48 組主要文字對比達到 4.5:1 以上；不等同完整無障礙認證。[報告](deploy/palette-contrast-report.json)
- 實際 9Router 連線成功取得 88 個模型；目前選擇的模型與原有金鑰保留。本次沒有執行付費生成，也未使用其他供應商的真實金鑰逐一驗證。
- 保存目前設定後重啟服務，後端和 Graphiti 均仍讀取已儲存的設定；四個 Docker 服務健康。[實機結果](deploy/provider-settings-live-validation.json)
- 390px 手機及 1280px 桌面，深淺色、繁中／英文、鍵盤操作及儲存流程均完成檢查；測試頁使用合成資料，不修改真實供應商。[瀏覽器結果](deploy/settings-browser-qa.json)
- 2026-10-03 使用者確認後，已連結 9Router 管理授權，實際讀到 7 個 OpenCode Go 帳戶。先顯示唯一保有錢包紀錄的「GitHub login」，可在設定頁切換。三個方案用量區間可讀取；錢包目前只有 2026-09-04 的手動快照，因此明確標示過期，不能當成現在餘額。需在 9Router 完成對應帳戶的 OpenCode 登入與同步，才能取得新的錢包讀值。模型名稱、網址與模型金鑰保持原設定。[連結驗證](deploy/provider-balance-live-validation.json)

官方資料：[OpenRouter 金鑰額度](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)、[OpenCode Go](https://opencode.ai/docs/go/)、[OpenCode Zen](https://opencode.ai/docs/zen/)。

