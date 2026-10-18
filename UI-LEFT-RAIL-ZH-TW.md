# 首頁直向流程與載入改善

日期：2026-10-03。修改前已先提交所有當時未忽略的成果，基準版本為 `d354592`；分支為 `codex/workspace-visual-refinement`。沒有推送到遠端。

## 這次改動

- 移除首頁導覽的 GitHub 入口。
- 桌面將三段流程放在左側，依「參考資料 → 人物與互動 → 分析報告」由上往下排列；表單放在右側。
- 使用既有透明插圖的三個場景，搭配垂直箭頭。所有文字仍為可選取、可翻譯的頁面文字。
- 960px 以下改為單欄，先顯示可操作的表單，再顯示流程。沒有移除流程詳情或來源用量保護。
- 保留暖石、炭灰、琥珀色與本機系統字型；輸入文字統一為 16px，流程標題為 20px，步驟標題為 16px，短說明為 14px。
- 設定頁等到開啟時才載入；工作區草稿仍保留在背景，返回後繼續使用。

依指定的 i-adapt、i-bolder、i-optimize、i-typeset 工作流程執行。字體的人工評估與機械掃描先分別完成，再綜合實作；介面完成後集中檢查桌面與窄螢幕，沒有反覆改變視覺方向。

## 實際檢查

- 前端完整測試：**146 項通過、0 項失敗**。延後載入相關測試改為等待真正的動態模組讀取，原有斷言不變。
- 正式建置成功；字體及一般設計掃描均為 0 項機械發現。這不等同完整無障礙認證。
- 瀏覽器實際 CSS 寬度：320、434、854、960、1126、1251px。已涵蓋繁體中文、簡體中文、英文、深色與淺色的代表組合，並非所有組合的窮舉。
- 桌面流程位於表單左側，各階段由上往下；窄版表單在流程前，沒有整頁橫向溢出。兩個輸入框均為 16px。
- 輸入問題及網址後開啟設定，再返回首頁：兩者均保留。
- 使用本機私有網址測試拒絕狀態：顯示可理解的錯誤、焦點移至錯誤區、輸入保留；沒有執行付費擷取或模型模擬。
- 完整流程詳情的方向鍵切換、歷史紀錄焦點、Enter 開啟及 Escape 關閉對話框均正常。
- Docker 前端已更新，首頁與圖像回應 200；正式版設定頁可開啟及返回。前端、後端、Graphiti、Neo4j 均為 healthy。

本輪沒有修改後端，沒有重跑付費完整模擬。沒有以實體手機、200% 瀏覽器縮放或螢幕閱讀器完成驗證。唯一觀察到的瀏覽器錯誤紀錄是預期的無效來源 400 回應。

## 載入測量

使用同一基準快照，比較設定頁延後載入前後的正式建置，排除其他同期版面修改。首頁首次所需程式與樣式總量由 **500,967 bytes 降為 456,690 bytes，減少 8.84%**；逐檔 gzip 合計由 **164,790 降為 156,111 bytes，減少 5.27%**。

這是檔案大小比較，不代表實際載入時間縮短相同比例。沒有測量 LCP、INP、CLS 或 Lighthouse 分數；圖片、HTML 及使用者開啟設定後才下載的內容不包含在上述合計中。

## 證據

- `deploy/left-rail-production.jpg`：Docker 版繁體中文首頁。
- `deploy/left-rail-home-light.jpg`、`left-rail-home-dark.jpg`、`left-rail-home-mobile.jpg`：桌面及手機版代表截圖。
- `deploy/left-rail-validation.json`：瀏覽器、測試及服務檢查摘要。
- `deploy/left-rail-final-tests.json`：完整測試結果。
- `deploy/left-rail-load-performance.json` 與 `deploy/measure-settings-route-bundle.mjs`：受控載入比較及重跑方法。
- `deploy/left-rail-type-assessment.md`、`left-rail-type-before.json`、`left-rail-type-after.json`、`left-rail-design-after.json`：字體評估與掃描結果。

設計規則已同步至 `DESIGN.md` 及 `.impeccable/design.json`。開發版位於 http://localhost:3000/，Docker 版位於 http://localhost:3100/。
