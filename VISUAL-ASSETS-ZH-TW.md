# MiroFish 視覺素材與操作地圖

2026-10-03：已使用內建 `image_gen.imagegen` 產生兩張原創透明插畫，並以真正的 SVG 繪製操作導覽。沒有使用外部圖片、字型服務或新增追蹤。

## 已加入實際介面

- 首頁插畫：文件逐漸形成關係網絡與對話。採用米白、深藍、粉藍及少量橘色，支援淺色與深色背景。
- 尚無歷史紀錄：文件托盤與第一組連結，配合原有提示文字；不影響既有紀錄。
- 五步操作導覽：點選「整理關係 → 設定模擬 → 觀察互動 → 閱讀報告 → 繼續追問」，查看投入、操作及成果。這是說明導覽，不會發送模型或擷取請求。
- 上傳按鈕：可縮放的文件上傳 SVG 圖示，沿用原有檔案操作。

五步導覽支援方向鍵上下切換、Home / End 跳到首尾、Tab 進入說明，以及繁體中文、簡體中文、英文。裝飾性插畫不干擾螢幕閱讀器。

## 素材位置

所有素材位於 `D:\Dev\Projects\mirofish\frontend\public\assets\visuals`。

- [首頁插畫原圖](frontend/public/assets/visuals/exploration-studio.png)：1536 × 1024 PNG，透明背景。
- [首頁網頁用圖](frontend/public/assets/visuals/exploration-studio.webp)：768 × 512 WebP，47,188 bytes。
- [空白紀錄插畫原圖](frontend/public/assets/visuals/first-connection.png)：1536 × 1024 PNG，透明背景。
- [空白紀錄網頁用圖](frontend/public/assets/visuals/first-connection.webp)：480 × 320 WebP，13,540 bytes。
- [五步操作地圖](frontend/public/assets/visuals/workflow-map.svg)：可編輯的原生 SVG，含投入、操作與成果。
- [介面配置地圖](frontend/public/assets/visuals/ui-blueprint.svg)：桌面、手機、深淺模式與操作層級的 SVG 說明。
- [素材預覽頁](http://localhost:3100/assets/visuals/index.html)：查看插畫、切換背景、開啟及下載 SVG。
- [完整生成提示詞](frontend/public/assets/visuals/prompts.json)：記錄兩張插畫的完整英文提示詞及生成工具。

插畫由內建工具生成，原始 PNG 保留。網頁版本僅縮小尺寸及轉成 WebP，保留透明度，兩張合計 60,728 bytes；首頁不會載入原始大圖。SVG 為直接撰寫的向量內容，文字可選取及修改，沒有將圖片包裝成假 SVG。

## 驗證

- 前端測試 103 項全部通過，包含新導覽的選取、鍵盤焦點及三語完整性。
- 瀏覽器實際確認五步說明可點選與用方向鍵切換，網址維持首頁。
- 確認插畫的深淺背景效果，以及手機版 390 CSS px 無橫向溢出。
- 使用虛構空白紀錄測試畫面確認第二張插畫載入，不刪除任何現有紀錄。
- 已更新 localhost:3100 的前端；素材頁、兩張網頁插畫、兩張 SVG 及提示詞均回傳正確檔案類型。四個服務健康，後端、圖譜與資料庫的容器沒有重啟。
- 正式首頁確認插畫載入、SVG 說明可切換，瀏覽器未出現錯誤；檢查後還原「跟隨系統」外觀。
- 本次只更新前端呈現，不修改後端、模型連線、Graphiti、Neo4j 或擷取上限。

測試結果存於 `deploy/visual-assets-tests.json`，部署檢查存於 `deploy/visual-assets-validation.json`。本次沒有啟動新的真實模型模擬或 Firecrawl 擷取。

## 2026-10-03 更新：炭黑、暖灰與琥珀色插畫

兩張插畫已透過內建 `image_gen.imagegen` 分別參考原圖重新生成，改用炭黑、暖灰與琥珀色，移除原有藍色。保留透明背景、文件與節點的構圖，以及紙張、霧面陶質的材質表現。素材預覽頁的替代文字也已更新。

目前使用的檔案如下；本節資訊取代上方初版插畫的色彩、尺寸及檔案大小說明，原有測試紀錄保留供追溯。

| 素材 | 尺寸 | 大小 |
| --- | --- | ---: |
| `exploration-studio.png` | 1536 × 1024 | 1,757,514 bytes |
| `exploration-studio.webp` | 768 × 512 | 61,426 bytes |
| `first-connection.png` | 1536 × 1024 | 1,546,854 bytes |
| `first-connection.webp` | 480 × 320 | 17,498 bytes |

兩張 PNG 為生成工具提供的完整尺寸原檔，已確認複製後的檔案內容與生成原檔完全相同，方便後續編輯。網頁使用的兩張 WebP 合計 78,924 bytes，維持原本顯示尺寸；僅透過 Pillow 縮放及編碼，沒有以程式重新調色。

初版兩張 PNG、兩張 WebP 及提示詞檔案完整保留於 `deploy/visual-assets-before-charcoal-20261003`，可隨時還原。新版本的尺寸、大小、完整提示詞與處理方式已同步記錄於 `frontend/public/assets/visuals/prompts.json`。本次只核對素材檔案與文案，沒有改寫上方既有功能測試或部署驗證結果。
