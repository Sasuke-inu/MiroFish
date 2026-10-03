---
version: "alpha"
name: "MiroFish"
description: "以暖石、炭灰與琥珀色建立清楚可視的群體模擬工作室。"
colors:
  studio-accent-light: "#805014"
  studio-accent-dark: "#e8b869"
  studio-soft-light: "#e8d8b9"
  studio-soft-dark: "#3e3422"
  studio-paper-light: "#d5cec1"
  studio-paper-dark: "#1b1d19"
  studio-surface-light: "#e4ded2"
  studio-surface-dark: "#252822"
  studio-ink-light: "#282b25"
  studio-ink-dark: "#f0eadc"
  studio-muted-light: "#515548"
  studio-muted-dark: "#b9bca9"
  studio-line-light: "#b4b1a3"
  studio-line-dark: "#4a5041"
  theme-line-strong-light: "#878c78"
  theme-line-strong-dark: "#7f896c"
  studio-button-light: "#34392d"
  studio-button-dark: "#4e593f"
  studio-button-hover-light: "#474e3c"
  studio-button-hover-dark: "#606d4c"
  theme-surface-soft-light: "#d9d5c9"
  theme-surface-soft-dark: "#30352b"
  theme-accent-line-light: "#a57332"
  theme-accent-line-dark: "#bf934b"
  studio-green-light: "#355b40"
  studio-green-dark: "#aed19a"
  studio-success-soft-light: "#d4dfcf"
  studio-success-soft-dark: "#2b3928"
  studio-error-light: "#963e31"
  studio-error-dark: "#efac95"
  theme-error-surface-light: "#ead0c5"
  theme-error-surface-dark: "#432d27"
  theme-on-filled: "#f5efdf"
typography:
  display:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "clamp(2rem, 3.2vw, 2.5rem)"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "36px"
    fontWeight: 700
    letterSpacing: "-1px"
  title:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.5
  title-workbench:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.5
  title-journey:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.45
  stage-journey:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  detail-journey:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.75
  caption-journey:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.75
  input:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.7
  body:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.8
  reading:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.85
  label:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  control:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  caption:
    fontFamily: "Segoe UI, Microsoft JhengHei, PingFang TC, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.8
rounded:
  tag: "6px"
  control: "8px"
  field: "9px"
  compact-panel: "10px"
  panel: "12px"
  provider-panel: "14px"
  project: "16px"
  pill: "20px"
spacing:
  control-gap: "8px"
  compact: "12px"
  section-sm: "16px"
  group-gap: "24px"
  card: "24px"
  workspace-gap: "40px"
components:
  button-primary:
    backgroundColor: "{colors.studio-button-light}"
    textColor: "{colors.theme-on-filled}"
    typography: "{typography.control}"
    rounded: "{rounded.field}"
    padding: "12px 18px"
  button-primary-dark:
    backgroundColor: "{colors.studio-button-dark}"
    textColor: "{colors.theme-on-filled}"
    typography: "{typography.control}"
    rounded: "{rounded.field}"
    padding: "12px 18px"
  button-primary-hover:
    backgroundColor: "{colors.studio-button-hover-light}"
  button-primary-hover-dark:
    backgroundColor: "{colors.studio-button-hover-dark}"
  button-primary-disabled:
    backgroundColor: "{colors.theme-surface-soft-light}"
    textColor: "{colors.studio-muted-light}"
  button-primary-disabled-dark:
    backgroundColor: "{colors.theme-surface-soft-dark}"
    textColor: "{colors.studio-muted-dark}"
  button-secondary:
    backgroundColor: "{colors.studio-surface-light}"
    textColor: "{colors.studio-muted-light}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  button-ghost:
    textColor: "{colors.studio-muted-light}"
    padding: "8px 0"
  field-source:
    backgroundColor: "{colors.studio-surface-light}"
    textColor: "{colors.studio-ink-light}"
    typography: "{typography.input}"
    rounded: "{rounded.field}"
    padding: "10px 13px"
  nav-settings-active:
    backgroundColor: "{colors.studio-surface-light}"
    textColor: "{colors.studio-ink-light}"
    rounded: "{rounded.field}"
    padding: "14px"
  chip-success:
    backgroundColor: "{colors.studio-success-soft-light}"
    textColor: "{colors.studio-green-light}"
    rounded: "{rounded.tag}"
    padding: "5px 8px"
  card-project:
    backgroundColor: "{colors.studio-surface-light}"
    textColor: "{colors.studio-ink-light}"
    rounded: "{rounded.project}"
    padding: "{spacing.card}"
  workflow-progress:
    backgroundColor: "{colors.studio-paper-light}"
    textColor: "{colors.studio-muted-light}"
    typography: "{typography.label}"
    padding: "15px 24px"
  journey-caption:
    textColor: "{colors.studio-muted-light}"
    typography: "{typography.caption-journey}"
  history-row:
    backgroundColor: "{colors.studio-paper-light}"
    textColor: "{colors.studio-ink-light}"
    padding: "18px 12px"
---

# Design System: MiroFish

## Overview

**Creative North Star: "暖石探索工作室"**

MiroFish 的視覺像一張整理思路的工作桌：暖石色與炭灰色提供安定的底，琥珀色指向目前重點。文件、人物關係與報告以可辨識的圖像連起來，讓第一次使用的人也能理解資料如何變成可追問的結果。

介面以清楚、沉穩、易操作為主。圖示、示意圖與簡短文字共同說明工作；進一步的細節可在需要時展開。淺色與深色共用同一套層次與狀態語意，並支援跟隨系統；繁體中文、簡體中文與英文都必須保留完整內容與可讀排版。

本文件記錄現有程式採用的視覺系統。配色以 `frontend/src/styles/studio.css` 與 `theme.css` 為準；頁面與元件取自 Home、SettingsView、PreferenceControls、WebSources、WorkflowProgress、WorkflowExplorer、ExplorationJourney 及 HistoryDatabase。首頁排列只描述目前首頁，不限制圖譜、報告或設定頁必須採用相同版型。

**Key Characteristics:**

- 暖石、炭灰與琥珀色，保留清楚的文字和邊界。
- 圖像與短句一起解釋資料、關係、模擬與報告。
- 以底色、細邊框與留白分層，陰影只作輔助。
- 可收合說明，但保留既有操作、進度、錯誤和復原入口。
- 深淺外觀、三種語言與鍵盤操作採相同的設計標準。

## Colors

整體由偏暖、帶少量橄欖色的中性色構成，琥珀色負責指引注意力。精確值置於檔案開頭；帶 `-light` 和 `-dark` 的成對項目，分別對應同一個 CSS 變數的淺色與深色版本。元件透過既有變數自動切換，跟隨系統沿用同一組明暗色票。

sidecar 的八階 OKLCH 色帶由每個色票的色相與彩度產生，供面板比色預覽使用；實際元件沿用上述來源中的語意色。

### Primary

- **琥珀重點**：`studio-accent` 用於目前步驟、互動重點、文字連結與輸入游標。
- **琥珀底色**：`studio-soft` 用於選取、拖曳進入與局部提示；文字選取也沿用這一組顏色。
- **琥珀焦點**：`theme-accent-line` 用於需要清楚辨認的焦點和活動邊界。

### Secondary

這些是狀態用色，不擴張成第二套品牌主色。

- **草木綠**：`studio-green` 與 `studio-success-soft` 共同表示已連線、來源就緒與完成。
- **陶土紅**：`studio-error` 與 `theme-error-surface` 表示錯誤與需要處理的訊息；同時保留說明文字及後續操作。
- 資訊、警告、紫灰狀態與圖譜分類沿用 `theme.css` 的既有語意色。圖譜不同角色可使用多色分類，並搭配圖例、名稱和選取狀態。

### Neutral

- **暖石／炭灰頁面**：`studio-paper` 是整頁工作背景；`studio-surface` 放置表單、內容及設定。
- **文字層次**：`studio-ink` 用於標題與重要內容；`studio-muted` 用於次要說明、時間與中性的控制文字。
- **細框與輸入邊界**：`studio-line` 分組內容，`theme-line-strong` 清楚界定可輸入的位置。
- **橄欖炭灰按鈕**：`studio-button` 與 `studio-button-hover` 承載主要動作，搭配 `theme-on-filled` 的暖白文字。
- **次層表面**：`theme-surface-soft` 用於日誌、指向回饋與部分停用狀態。不要把次要文字降低到難以辨識。

**The Amber Focus Rule.** 琥珀色用於目前步驟、選取、焦點與需要注意的狀態；同層級的一般資訊維持中性色。

**The Shared Theme Rule.** 新元件使用既有語意色彩變數，深色與淺色同步設計；不要只替單一頁面硬編一套色票。

## Typography

**Display Font / Body Font:** Segoe UI，依序使用 Microsoft JhengHei、PingFang TC、system-ui 與 sans-serif 作替代。沿用作業系統字型。

**Label / Mono Font:** 一般標籤沿用相同字體；執行日誌使用 Consolas、Microsoft JhengHei 與 monospace。

字體以實用、穩定和容易閱讀為主。大小與字重建立層次；較長的中文說明留足行距，避免用多種裝飾字體製造區別。

### Hierarchy

- **Display**：首頁簡短問題標題，使用 `display` 的彈性尺寸；支援平衡換行。
- **Headline**：設定頁主標題使用 `headline`；小於等於 560px 時縮為 30px。
- **Title**：一般段落標題使用 `title`；工作頁卡片標題使用 `title-workbench`。首頁流程標題使用 `title-journey`（1.25rem，預設 20px），步驟名稱使用 `stage-journey`（1rem，預設 16px），短說明使用 `detail-journey`（0.875rem，預設 14px）；流程備註使用 `caption-journey`（0.8125rem，預設 13px）。
- **Body / Reading**：一般解釋使用 `body`，報告內容使用 `reading`。首頁簡介的行長上限為 65ch；長報告允許換行，程式碼區塊可獨立水平捲動。
- **Label / Control / Caption**：表單標籤、主要按鈕與補充說明各自使用對應角色。短狀態、數量和時間採清楚可辨的字級；需要對齊的數字使用等寬數字。
- 首頁網址欄與問題欄在所有螢幕寬度使用 `input`（1rem，預設 16px）；首頁簡介、表單分組標題與主要按鈕也使用 1rem。對話與問卷保留各自的手機字級規則；表單不得靠縮小字體硬塞內容。

**The Readable Language Rule.** 文字容器必須容納繁體中文、簡體中文與英文；讓內容換行，並保留圖示操作的可讀名稱。

## Layout

共同原則是將相關操作放在一起，以空間、標題和邊界清楚分組。首頁已抽出控制間距、群組間距與工作區間距；其他頁面保留適合其工作的空間密度，不強制使用單一欄數。

目前首頁的主容器上限為 1168px，桌面左右留 24px。寬度至少 960px 時，左側放直向流程說明、右側放內容表單；左欄以 320px 為目標，CSS 使用 `minmax(280px, 320px)`，右欄取得剩餘空間，兩欄間距為 40px。小於 960px 時改成單欄，表單先出現、流程在後，區塊間距為 32px，流程區上限為 540px。小於等於 600px 時左右留 16px，主要動作佔據可用寬度。表單內的順序為「描述問題 → 加入資料 → 開始分析」，分組間距為 24px。

**The Home Layout Rule.** 首頁以「桌面流程在左、表單在右；窄螢幕表單在先」為設計約束。原生內容順序保留表單在流程之前，桌面只改視覺位置；流程三階段維持由上到下的閱讀順序。

設定頁主容器上限為 1440px；桌面使用 200px 分區導覽。小於等於 900px 時導覽改成四欄，小於等於 560px 時為兩欄。模型設定有自己的 1150px 斷點，讓表單與餘額資訊重新排列。

五個工作頁保留圖譜、工作區與分割畫面三種配置。小於等於 680px 時，分割畫面改成上下排列；報告與對話另依工作區容器寬度 850px 調整。圖譜與長文可以擁有不同的捲動區域，不需要套用首頁的卡片排列。

主要操作與偏好控制以至少 44px 的可點選高度為基準；首頁開始按鈕與部分收合入口更高。圖譜的小型工具保留目前的 36px 配置，周圍需要足夠間隔。窄螢幕時讓標籤換行，並把重要操作保持在自然閱讀順序中。

## Elevation & Depth

深度主要來自頁面底、內容表面、細邊框與留白。首頁表單和一般工作卡片保持平穩；語言選單、圖譜浮層與提示才使用柔和陰影。選取和進行中的狀態以細框或內側線條加強，不依賴大型投影。

### Shadow Vocabulary

- **語言選單**：柔和的下拉浮層陰影；精確 CSS 見 sidecar 的 `language-menu`。
- **圖譜浮層**：圖例與詳情使用較淡的陰影；見 `graph-overlay`。
- **活動卡片**：琥珀底色形成小範圍外框；見 `active-card`。
- **設定分區**：選取頁籤使用琥珀內側線；窄版導覽會移到下緣。
- **歷史回放視窗**：遮罩隔開背景，視窗使用柔和的較大陰影；見 `history-dialog`。歷史清單本身以分隔線與指向底色分層。
- 一般狀態切換多使用 150–200ms 的短過渡，圖譜開關使用 300ms；減少動態效果時，沿用全域的極短動畫與停用平滑捲動處理。

**The Quiet Depth Rule.** 大部分表面先以底色和邊框分層；焦點、選取與浮層才加強外框或陰影。

## Shapes

元件以輕度圓角和細邊框構成。標籤最緊湊，按鈕與輸入框稍柔和，內容卡與對話框有較大圓角；精確共用值列在 `rounded`。

一般邊界為 1px。虛線框表示可以加入檔案，實線框表示欄位或內容分組。圓形主要用於流程節點、狀態點與小型提示；它們的狀態須搭配文字或可讀名稱。

SVG 圖示沿用圓端線條與少量筆畫。插畫使用透明背景、暖石紙張、炭灰或橄欖色物件與少量琥珀色；圖片的大小讓實際工作仍保持優先。

## Components

### Buttons

按鈕清楚、安定，讓使用者一眼分辨主要動作與輔助選項。

- **Primary**：沿用 `button-primary`。首頁「開始分析」使用至少 48px 高度，文字與箭頭並列；指向時切到既有較亮的按鈕色。
- **Secondary**：偏好控制使用 1px 邊框與內容表面色；指向時切換琥珀文字、邊框及淡琥珀底。
- **Ghost**：歷史紀錄等低強度導覽使用純文字，仍保有足夠點選範圍。
- **Focus / Disabled**：全域焦點框一般為 3px，來源區等部分控制為 2px；外移 3px。不可操作時保留文字與視覺停用狀態；不要讓準備中或錯誤時的重試入口消失。

### Chips

狀態標籤緊湊而有明確語意。已完成使用成功底色與綠色文字，進行中使用琥珀色，未開始使用中性色。標籤不因外形像按鈕就可點選；真正可操作的項目保留完整焦點與指向樣式。

### Cards / Containers

首頁表單使用 `card-project` 的圓角、底色與內距。工作卡片、設定卡與模型設定面板各有已實作的尺寸，並沿用相同的表面與邊框語言。內部標題、欄位和狀態以間距分組；收合詳情依需要展開，避免同一資訊在多層卡片重複出現。

### History List / Dialog

歷史紀錄使用單欄緊湊清單；以水平細線分隔，每列呈現問題、時間、進度、檔案摘要與回放入口。標題最多顯示兩行，列表摘要保持簡潔。指向時換成次層底色，鍵盤焦點保持清楚；頁首的歷史入口會把焦點帶到清單標題。

每次載入 20 筆，還有紀錄時提供載入更多。選取後開啟回放視窗，顯示完整問題與檔案清單，以及圖譜、模擬和報告入口。視窗上限為 680px，圓角使用 `panel`，保留關閉按鈕、Escape、焦點管理及可捲動內容；小於等於 540px 時操作按鈕改為直向排列。

### Inputs / Fields

輸入區有清楚標籤、較強邊框和可辨的游標。網址欄使用 `field-source`，最小高度為 80px；問題欄使用相同色彩與圓角，最小高度為 112px。兩者一律使用 1rem 字體及 1.7 行高，網址短說明使用 0.875rem 及 1.75 行高。保留 placeholder、輔助文字、無效狀態、停用狀態和鍵盤焦點，不用圖片取代標籤。

來源區維持一個「開始分析」流程，自動處理網頁資料準備。通常只顯示必要欄位與短說明；使用限制與完整內容可展開。讀取進度、部分成功、錯誤、重試與用現有資料繼續的選項，按實際狀態清楚呈現。

### Navigation

首頁頁首保留品牌、歷史、語言和偏好入口，移除 GitHub 連結；首頁導覽不再加入此連結。小螢幕可收起圖示旁的文字，但按鈕仍有可讀名稱。設定頁目前分區以底色、字重、邊界與琥珀線共同表示。

工作頁五步進度顯示目前、完成和待進行狀態。手機保留目前步驟名稱，其餘名稱保留給輔助閱讀；不要把圖示導覽變成只有顏色差異。

### Visual Journey

首頁的 ExplorationJourney 沿用 `research-journey-v2.webp`，由 CSS 裁出「參考資料 → 人物與互動 → 分析報告」三個場景，逐段由上到下排列。每段左側為場景、右側為可翻譯的原生標籤與短說明；相鄰場景使用向下的 SVG 箭頭連接。三個場景共用原圖，必要文案不寫入圖片。

桌面每個場景為 116px 正方形，小於 960px 時為 96px；場景與文字相隔 16px，相鄰步驟相隔 28px。裁切容器隱藏溢出，原圖寬度設為容器的 300%，依階段索引水平位移並垂直置中。圖片及箭頭為裝飾，內容由有序清單中的原生文字提供。詳細五步導覽是另一個可展開的說明，保留方向鍵、Home / End 與焦點操作。圖像與說明須明確表示這是流程示意，不將模擬視為未來結果。

此組圖文是首頁目前的表達方式；其他頁面依內容選擇合適的圖像或資料視覺化。

以上是本輪依 Home、ExplorationJourney 與 WebSources 原始碼同步的設計約束，不代表已完成本輪瀏覽器驗證。

## Do's and Don'ts

### Do:

- **Do** 延用炭灰、暖石與琥珀色的共同主題，讓一般文字、次要說明和邊框都能清楚辨識。
- **Do** 用圖示、簡短標題與適量圖像說明流程，並讓使用者看得到下一個操作。
- **Do** 保留淺色、深色、跟隨系統，以及繁體中文、簡體中文、英文的完整功能。
- **Do** 在收合詳細說明時，保留操作中的進度、來源數量、錯誤、重試和繼續入口。
- **Do** 讓主要操作維持足夠點選範圍，提供清楚的鍵盤焦點，並尊重減少動態效果的偏好。
- **Do** 依工作需要安排首頁、圖譜、報告、互動與設定的空間，沿用共同色彩與元件語言。

### Don't:

- **Don't** 把大面積亮白、通用 AI 藍色或霓虹漸層引入主要介面。
- **Don't** 以簡化畫面為由移除 Firecrawl 一鍵來源流程、模型設定、歷史紀錄或五個工作步驟。
- **Don't** 把首頁的示意圖、欄數或排列方式當成所有頁面必須遵守的規則。
- **Don't** 只靠顏色或沒有名稱的圖示表達成功、失敗、選取或可操作狀態。
- **Don't** 把裝飾性示意圖標成真實執行結果，或讓圖片代替必要的表單標籤。
