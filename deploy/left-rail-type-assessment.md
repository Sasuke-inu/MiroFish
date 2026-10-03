# 首頁左側直向流程：獨立字體評估

日期：2026-10-03。基準：`d354592`。此評估先於機械掃描，未閱讀或執行 detector，也未修改介面原始碼。

依據：`DESIGN.md` 的 Typography／Layout、`Home.vue`、`ExplorationJourney.vue`、`WebSources.vue`、`studio.css`、`theme.css`、`App.vue`、`frontend/index.html`，以及既有深色首頁截圖 `deploy/refined-home-complete.jpg`。本評估是來源與截圖審視；新排版仍需實際瀏覽器驗證。

## 六個面向

1. **字體權威與適用性**：`studio.css:11` 的 `--studio-font` 為 Segoe UI、Microsoft JhengHei、PingFang TC、system-ui、sans-serif，與 `DESIGN.md` 一致。它符合操作與閱讀優先的工作室用途；不需增加第二套字體。`Home.vue .form-section-heading`、`.start-engine-btn` 與 `ExplorationJourney.vue h2/strong` 使用 650；一般非可變系統字體未必有 650，可能映射到既有字重，因此不應以 600／650 的差別承擔主要層次。
2. **層次**：`Home.vue .studio-intro h1` 是 `clamp(26px, 2.8vw, 34px)/1.35/700`，`ExplorationJourney.vue h2` 為 `18px/1.5/650`，主要與次要標題已有區別。但表單章節 `15px/650`、流程步驟 `14px/650`、網址標籤 `13px/600` 彼此接近；截圖中次要提示與流程說明都顯得細小。直向 rail 應以 20px 分區標題、16px 步驟標題和 14px 說明形成更清楚的差距。
3. **字級與一致性**：首頁現有 10、11、12、13、14、15、16、18、22、26–34px 等字級，各自有用途但正文與控制分布過細。`Home.vue .goal-input` 是 15px，`WebSources.vue textarea` 是 14px，兩者手機才變 16px；同屬輸入內容應統一 16px。`Home.vue .studio-intro p` 由 14px 在 600px 斷點降成 13px，降低窄版的閱讀便利性，建議固定 16px。
4. **閱讀**：`Home.vue .studio-intro p` 的 `max-width:65ch; line-height:1.8` 是合理的上限，但中文的 ch 並非字數，不宜解讀成 65 個中文字。現有 `.journey-stages` 三欄配合 `12px/1.65`、置中、`text-wrap:balance`，使短說明在局部窄欄更零碎；改為單欄左對齊、`14px/1.75`、自然換行即可。`studio-muted` 在 paper 的原始色值對比約淺色 4.90:1、深色 8.76:1，在 surface 約 5.72:1／7.71:1，無需再淡化。流程說明是簡短段落，可用實際 rail 寬度；較長說明仍以約 45–65ch 上限控制。
5. **壓力條件**：`Home.vue .studio-home-grid` 目前為 `minmax(0,1.5fr) minmax(300px,1fr)`，880px 以下單欄；DOM 現在表單在前，適合保留手機及輔助閱讀的主要工作順序。桌面可用命名 grid areas 把 rail 放左，表單放右。`.file-meta` 與來源網址已有 `overflow-wrap:anywhere`；新 rail 的標題和說明也需 `min-width:0` 及合理換行。移除三欄等分、固定文字高度及無意義 nowrap，才可容納英文與放大。`frontend/index.html:15` 沒有限制最大縮放；避免新增限制。
6. **載入與替代字體**：已檢視範圍沒有 `@font-face`、外部 Google Fonts 或字體預載；目前使用本機字體，無需新增下載或可變字體設定。`studio.css:23` 讓表單控制繼承字體，`App.vue` 的 app 字體清單與設計一致。主要風險是平台替代字體的字寬與 650 映射，應以 400／600／700 及自動高度降低影響。字體載入沒有需要修正的阻塞證據。

## 編輯前建議的角色系統

- **主要問題標題**：保留現有系統字體、700，改用 `clamp(2rem, 3vw, 2.5rem)`／1.3；`letter-spacing:-.02em` 只用於短標題，保留 `text-wrap:balance`。
- **表單章節標題**：`.form-section-heading` 為 `1rem/1.5`、700；編號保持 12px／等寬數字，不把編號當正文。
- **左欄分區標題**：`.exploration-journey h2` 為 `1.25rem/1.45`、700，視覺強度低於主標題。
- **左欄步驟標題**：`.journey-stages strong` 為 `1rem/1.5`、600；左對齊。
- **一般說明／輸入內容**：`.studio-intro p`、`.goal-input`、`WebSources textarea` 為 `1rem/1.7–1.8`、400。手機維持相同字級，不縮字。
- **短說明與控制**：`.journey-stages li > span:last-child`、`.sources-help`、`.sources-label`、`.goal-examples button`、`.upload-title`、`.project-submit-row > p`、各 summary 為 `.875rem/1.65–1.75`，標籤與控制使用 600，說明使用 400。按鈕保持至少 44px 高；主按鈕保持至少 48px。
- **補充註記／純資料**：`.journey-caption`、檔案大小與格式為 `.8125rem/1.75`。字數、檔案大小等保持 `font-variant-numeric:tabular-nums`；非互動的小型編號可保留 12px。

左欄建議約 300–340px，右欄取得剩餘空間；表單的長行以欄位自身寬度約束，避免把 rail 為求緊湊縮到 12px。以既有暖石／炭灰／琥珀色與留白建立層次，無需替換字體或改變識別。

## 交由主代理驗證

- 1280／1440px：流程在左且垂直、表單在右；各步標題和說明不被裝飾圖或連線擠壓。
- 320／390px 及 200% 縮放：表單先出現；無橫向整頁捲動、文字裁切或按鈕相互覆蓋。
- 繁體中文／簡體中文／英文、深色／淺色：檢查長標題、來源錯誤、已選檔案、展開詳情和按鈕換行。
- 保留表單、網址、來源結果與流程詳情的鍵盤焦點；字級變大後不縮小 44px 觸控範圍。
- 綜合本評估與獨立 detector 結果後再定稿；機械通過不能取代上述視覺驗證。
