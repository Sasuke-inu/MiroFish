# 將本機 9Router 的 OpenCode 餘額連接到 MiroFish

這個助手只用於這台 Windows 電腦上既有的 9Router。先在 MiroFish 設定頁選擇並儲存 **9Router**，確認模型連線可用，再由你自行執行助手。

## 執行前可以先預覽

在 MiroFish 專案的 PowerShell 執行：

```powershell
.\deploy\Connect-9RouterBalance.ps1 -WhatIf
```

預覽只列出目標位置，不讀取授權內容，也不發送網路請求。確認後執行：

```powershell
.\deploy\Connect-9RouterBalance.ps1
```

成功後回到 MiroFish 設定頁，載入 OpenCode 帳戶、選擇帳戶並儲存。助手不會替你選擇帳戶。

預設 MiroFish 後端網址是 `http://127.0.0.1:5001`。如需使用前端代理，可以指定：

```powershell
.\deploy\Connect-9RouterBalance.ps1 -MiroFishBaseUrl 'http://localhost:3000'
```

助手只接受本機 MiroFish 的 3000、3100 或 5001 連接埠。9Router 需使用 `http://localhost:20128/v1`、`http://127.0.0.1:20128/v1` 或 Docker 內的 `http://host.docker.internal:20128/v1`。

9Router 資料夾預設為 `C:\Users\PC\Desktop\9-router\data`。如果你曾搬動它，使用 `-RouterDataDirectory` 指定實際資料夾。找不到既有授權檔時，助手會停止；不會建立或重設 9Router 授權。

## 會保存什麼

助手讀取 9Router 已存在的 `machine-id` 及 `auth\cli-secret`，依 9Router 的原始程式計算目前的 CLI 授權。授權只在記憶體中處理，再由本機 MiroFish 設定 API 儲存為餘額連線授權；不顯示內容、不寫入剪貼簿、不修改 9Router。

它不改寫模型供應商、服務網址、模型名稱、模型金鑰或已選取的餘額帳戶。若操作期間供應商或網址改變，MiroFish 會拒絕此次保存，避免將管理授權套用到另一個服務。

**這份 CLI 授權本身具有 9Router 管理權限，並非專門的唯讀金鑰。** MiroFish 的整合只應對已設定的本機 9Router 使用以下兩個讀取介面：

- 列出 OpenCode Go 帳戶：`GET /api/providers/client?provider=opencode-go&pageSize=500`。
- 讀取所選帳戶的用量與錢包快照：`GET /api/usage/{accountId}`。

沒有額外的 9Router 管理授權複製頁面；助手使用的是 9Router 自己在本機運作時使用的同一份授權，不會建立新的帳戶或金鑰。

## 金額與更新時間

MiroFish 顯示的是 **9Router 最後取得的 OpenCode 錢包金額**。重新整理 MiroFish 不會自動登入 OpenCode 或啟動新的瀏覽器同步。若 9Router 尚未完成相應帳戶的登入與錢包同步，需先在 9Router 完成；沒有讀值時會顯示尚未取得，不會顯示假的零元。

若讀值已超過 11 分鐘，或同步回報需要登入／暫時失敗，應顯示最後讀取時間及過期狀態。每週、每月的方案用量百分比與錢包金額是不同資料。

## 程式來源

計算方式對照 9Router 的 `src/shared/utils/machineId.js`（`getConsistentMachineId`）：將既有 machine ID、固定字串 `9r-cli-auth` 及本機授權秘密依序合併，取 SHA-256 十六進位結果的前 16 字元。此助手只讀取已存在檔案，不沿用原始函式在檔案缺失時自動建立秘密的行為。
