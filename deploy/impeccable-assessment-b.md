# Assessment B — independent detector, technical audit and mechanical layout

日期：2026-10-03。工作目錄：D:\Dev\Projects\mirofish。
主要對象：frontend/src/views/Home.vue；相關對象：WebSources.vue、HistoryDatabase.vue、WorkflowExplorer.vue。只讀取周邊 LanguageSwitcher.vue、PreferenceControls.vue、App.vue 和共享樣式以核對實際結果。沒有修改產品碼、測試、語系或資產。

## 方法與邊界

- 此評估未讀取 Assessment A 的發現。A 只通知其瀏覽器工作已完成、分頁已關閉；B 隨後建立自己的背景臨時分頁。
- 使用指定 Impeccable 4.3.1 critique/audit/layout playbooks；沿用 root 已完成的 context，未重跑。
- 限定四個 Vue 檔案執行完整與 layout 掃描，沒有掃全專案。沒有 ignore.md。
- CUA evaluate 明確為 read-only，因此不嘗試 document.title/script mutation、不繞過注入、不啟動 overlay live-server、不宣稱存在可見 overlay。改採 source、實際 DOM、可及性樹、畫面與尺寸量測。
- 瀏覽器背景檢查。原偏好 English/light，結束前已恢復；viewport override 已 reset；專用 tab 已 close。使用者 dev server 保持運行。
- 未觸發網頁擷取、上傳、分析/模型呼叫、任何設定頁修改或帳戶財務資料讀取。历史視窗使用現有明確標示虛構的 smoke-test 記錄，只查看回放選項，沒有啟動回放流程。

## 五面向分數

| 面向 | 分數 | 已確認理由 |
|---|---:|---|
| 可及性 | 2/4 | 大部分控件有標籤與鍵盤支援；深色語言選單選取項文字只有 1.62:1 對比，歷史快捷導覽未移動焦點且無區段標題語意。 |
| 效能 | 3/4 | 主要插圖 61,426 bytes、空狀態圖 17,498 bytes，後者 lazy、兩者設尺寸；存在小型裝飾 width 動畫，未測得掉幀。 |
| 響應式 | 3/4 | 320、434、768、1423 CSS px 寬度檢查無頁面水平溢出；資料保護 disclosure 約 36px 高，桌面示例按鈕約 38px 高。 |
| 深淺色 | 3/4 | 主體使用共享色彩變數且兩色外觀清楚；語言選單一處未定義 token 落入固定淺色背景。 |
| 實作一致性 | 3/4 | 一鍵準備資料、錯誤與回放保護具體；歷史元件殘留部分舊字體/動態樣式及多層覆蓋。 |
| **合計** | **14/20** | **Good，優先處理局部可及性問題。此為有限範圍評估，不是完整 WCAG 認證。** |

## 已確認問題（0 P0、1 P1、2 P2、1 P3）

### P1 — 深色語言選單的目前語言難以閱讀

- 位置：frontend/src/components/LanguageSwitcher.vue:163；共享顏色 frontend/src/styles/theme.css:60 起。
- 原因：選取按鈕使用 `var(--studio-accent-soft, #fbefe9)`，全專案沒有定義 studio-accent-soft。深色模式仍使用 rgb(251,239,233) 背景，而文字變為 rgb(232,184,105)。
- 瀏覽器實测：14px、600 字重；對比 **1.6207929962:1**。畫面可見琥珀文字幾乎融入粉白色背景。WCAG 1.4.3 一般文字門檻為 4.5:1。
- 建議：這個按鈕使用現有 `--studio-soft`（或定義具備深色值的正確 token），保持選取語意與文字對比。對应命令：impeccable harden/colorize，最後 polish。

### P2 — 歷史快捷導覽只捲動，鍵盤與標題導覽無法一起到位

- 位置：frontend/src/views/Home.vue:229-230；frontend/src/components/HistoryDatabase.vue:12。
- 實測點選 History 後焦點仍在頂部 History 按鈕；下一次 Tab 將继续前往語言等頂部控件。歷史區標題是 span，DOM 標題清單沒有 History h2。
- 影響：依賴鍵盤或標題跳轉的人，看到已到歷史區卻仍需穿過首頁表單才能操作記錄。
- 建議：歷史區使用有 id 的 h2，快捷導覽在捲動後聚焦可聚焦的該區段/標題，採 `tabindex=-1` 避免增加平常 Tab 停留點。對应命令：impeccable harden。

### P2 — 次要 disclosure 與部分示例按鈕的觸控高度不一致

- 位置：frontend/src/components/WebSources.vue:64；frontend/src/views/Home.vue:385、417。
- 實測保護說明 summary 約 **36px 高**；桌面示例按鈕約 **38px 高**；手機示例已提升至 44px。其他主要控件大部分達 44px，流程 tab 約56px。
- 影響：小型展開區與平板上的示例較不容易點選。這是本 audit 的44px觸控舒適度要求，**不以此單獨宣稱 WCAG AA 失敗**。
- 建議：次要 summary 及可觸控示例統一 min-height 44px，保持目前緊湊文字尺寸。對应命令：impeccable adapt/layout。

### P3 — 歷史元件有局部舊樣式，宜在同次整理中清除

- 位置：HistoryDatabase.vue:713（filename Inter）、842（width 動畫）、916（彈性 modal easing）。
- 已核對：filename 的 computed font 仍為 `Inter, sans-serif`；卡片標題和描述已由共享樣式覆蓋為 studio-font。卡片底線是真實的 absolute 2px 裝飾，hover 由 width:0 到100%；不能據此聲稱嚴重效能問題。
- 建議：檔名字體改共享變數；底線用 scaleX；回放視窗改穩定 ease-out。此為低優先整理，不應推翻目前炭灰/暖石/琥珀視覺。對应命令：impeccable optimize/polish。

## Detector 原始結果與誤判核對

原始 JSON：deploy/impeccable-detector-before.json；mechanical JSON：deploy/impeccable-detector-before-layout.json。

- 完整掃描 **6** 筆：5 warning、1 advisory；全部在 HistoryDatabase.vue。實際 launcher exit 為0，即使 JSON 有警示；保留這個觀測，不以 exit 推論 clean。
- `overused-font` **3** 筆，line713、764、782。line764/782 已由 studio.css:130-131 覆蓋，瀏覽器 computed font 證實，因此是目前畫面的 **2個誤判**。line713 filename 尚有效，但字體流行與否本身不是可及性缺陷，只作一致性整理。
- `bounce-easing` **1** 筆，line916：有效 modal 過渡，P3。
- `layout-transition` **1** 筆，line842：有效，但只影響裝飾底線；沒有實測 jank，P3。
- `codex-grid-background` **1** advisory，line481：`.grid-pattern` 無 template/DOM 實例，瀏覽器計數0，為 **誤判/未使用 CSS**。
- 總計 **3 inactive false positives**、**3 active signals**；不把6筆當成6個使用者缺陷。
- `--scope layout` 結果 **[] / 0筆**；這不代表視覺層級或觸控面積已全面合格。

## 瀏覽器與機械版面證據

CUA 所要求的 viewport 與頁內 CSS viewport 有縮放差異，以下一律記錄 `innerWidth/innerHeight` 實際值：

| 實際 CSS viewport | 語言/顏色/狀態 | 頁面 scrollWidth / clientWidth | 結果 |
|---|---|---:|---|
| 1423×800 | English/light 首頁、English/dark 語言選單 | 1416 / 1416 | 無橫向頁面捲動；深色語言選項失敗如上。 |
| 434×937 | English/dark 收合與展開流程 | 428 / 428 | 主表單改為單欄、插圖收起；流程控件約56px。 |
| 320×800 | English/dark、繁中/dark，展開流程與歷史 modal | 313 / 313 | 無橫向頁面捲動。Modal 寬296.08px、內部 clientWidth/scrollWidth=294/294。 |
| 768×800 | 簡中/dark、展開流程 | 762 / 762 | 主表單仍雙欄328.17px/298.34px；support兩欄325.24px，無橫向溢出。 |

- 讀取順序：桌面先主題與簡短說明，再左側資料/右側目標，最後單一主要按鈕；窄螢幕保持資料→目標→提交的DOM順序。
- 分組：網頁與檔案同屬第一步；目標與示例同屬第二步。服務與五步流程置於原生 details，避免擋住開始工作。
- 節奏：主要卡片以較大的區段間距分隔，內部提示更緊；但 Home.vue 同一 selector 重複覆蓋多次（尤其269起、351起、419起、435起），不是視覺缺陷的直接證据，却增加後續改版誤傷風險。
- 結構：桌面兩欄是同一個工作的兩種輸入；mobile改單欄合理。歷史卡片與回放dialog保留原行為。
- 密度：操作區本身已比流程全部展開簡單；768px展開的support資訊較密但無截斷。真正主視覺簡化需求由獨立Assessment A判斷。
- 極端內容：現有長繁中模擬需求與檔名在320px modal可換行；modal top33.69、bottom766.50、height732.81位於800px視口內。螢幕截圖工具在深捲動modal狀態呈現裁切，因此modal幾何結論依可讀DOM量測，不把該截圖當完整可視證明。
- 鍵盤：流程選中tab按ArrowDown後移到第二步，aria-selected只剩1個、焦點有outline。歷史dialog開啟後聚焦Close、app具有inert且body overflow hidden；Shift+Tab繞到最後回放鈕，再Tab繞回Close；Escape關閉後還原原卡片焦點及app inert。
- 語言：English/繁體中文/简体中文都通过可見控件切換，html lang分別en/zh-TW/zh，未見主要表單遺漏翻譯鍵。固定Step1/2/4文字是既有回放微文案，作P3觀察。
- 未驗證：200%文字放大、完整六組語言×theme×viewport矩陣、網頁擷取錯誤實際伺服器狀態、真實模型執行、空歷史與文件結果頁（後二者只審source）、效能trace。

## 其他觀察及正向實作

- 有 skip link、main landmark、輸入label、錯誤role=alert與進度status；來源失敗後聚焦錯誤；關閉歷史視窗恢復焦點。
- 原生details與流程tab支持鍵盤；WebSources的pending URLs、網頁文字預覽與modal需求都有換行措施。
- 本機檔案有空檔/副檔名/重複/大小檢查；提交期間禁用；Home離開後不自動啟動分析；service錯誤可重試。這些是source驗證，未執行模型。
- studio.css:172-174 使用全域 .01ms reduced-motion kill。已另有狀態文字保持資訊，因此沒有證据顯示任務完成受阻；建議未來改為指定動畫的簡化替代，不將此列入高嚴重度缺陷。
- 未新增server、未建立overlay/temp injection檔；只保留本評估與兩份原始detector JSON。

Questions skipped: 本子任務只提供獨立Assessment B給root整合；使用者原任務已要求進行改善，是否需要收尾提問由root依原要求處理。
