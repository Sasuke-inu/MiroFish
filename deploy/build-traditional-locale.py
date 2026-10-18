"""Rebuild the Traditional Chinese catalog without adding a runtime dependency.

Run: uv run --no-project --with opencc-python-reimplemented --python 3.11 python deploy/build-traditional-locale.py
"""
import json
from pathlib import Path
from opencc import OpenCC

root = Path(__file__).resolve().parents[1]
locales = root / "locales"
converter = OpenCC("s2twp")

def convert(value):
    if isinstance(value, str):
        return converter.convert(value)
    if isinstance(value, dict):
        return {key: convert(item) for key, item in value.items()}
    if isinstance(value, list):
        return [convert(item) for item in value]
    return value

traditional = convert(json.loads((locales / "zh.json").read_text(encoding="utf-8")))
traditional["studio"] = {
    "navigation": "主要導覽", "brandSubtitle": "群體模擬工作室", "history": "歷史紀錄",
    "workspace": "探索工作室", "headline": "先探索，再做決定。",
    "intro": "從一份資料開始，整理人物關係、模擬不同反應，再用報告與對話探索可能的結果。",
    "preview": "預覽版本", "newProject": "新的探索", "startTitle": "你想了解什麼？",
    "uploadTitle": "加入參考資料", "dropFiles": "將檔案拖曳到這裡", "browseFiles": "或點選選擇檔案，可加入多份資料",
    "addFiles": "繼續加入檔案", "removeFile": "移除 {name}", "uploadHelp": "支援 PDF、Markdown 和純文字。可先從一份簡短資料開始。",
    "goalTitle": "寫下探索目標", "plainLanguage": "用自己的話描述即可",
    "goalPlaceholder": "例如：一家咖啡店準備延長營業時間，附近居民與常客可能會有什麼反應？",
    "goalHelp": "說明你想觀察的事件、對象與變化，有助於產生更合適的模擬。",
    "start": "開始分析", "startHelp": "加入資料並填寫目標後，即可開始。你的資料會保存在本機專案。", "stopSimulation": "停止模擬",
    "serviceStatus": "目前可用功能", "modelConnection": "模型連線", "graphConnection": "圖譜服務",
    "checking": "檢查中", "connected": "已設定", "needsSetup": "待設定", "workflow": "探索流程", "fiveSteps": "共 5 個步驟",
    "step1Title": "整理關係", "step1Desc": "分析資料，建立人物與事件的關係圖。",
    "step2Title": "設定模擬", "step2Desc": "建立角色，安排情境與模擬輪數。",
    "step3Title": "觀察互動", "step3Desc": "查看不同平台上的發言與反應。",
    "step4Title": "閱讀報告", "step4Desc": "整理模擬過程，了解結果與原因。",
    "step5Title": "繼續追問", "step5Desc": "與角色和報告助手對話。",
    "explorationNote": "模擬提供探索的線索。請搭配原始資料與實際情況判讀結果。",
    "footer": "從資料，到更清楚的想法。", "noHistory": "尚無模擬紀錄", "historyHelp": "建立模擬後，這裡會保存進度，方便你繼續探索。",
    "checkingTitle": "正在檢查服務狀態", "checkingDesc": "請稍候，正在確認目前可用的功能。",
    "analysisReady": "內容分析可用", "modelPending": "等待模型連線設定",
    "analysisReadyDesc": "可以上傳資料並分析內容。建立圖譜與完整模擬流程，還需要設定圖譜服務。",
    "modelPendingDesc": "請先完成模型連線設定，再開始上傳與分析。",
    "serviceError": "無法連接網站服務，請確認 MiroFish 已啟動，然後重新整理網頁。",
    "serviceStarted": "網站已啟動，可以上傳資料並分析內容。",
    "modelNotice": "尚未設定模型連線，暫時無法分析資料。",
    "graphNotice": "圖譜服務待設定：建立圖譜、模擬與完整報告需要 Zep Cloud 連線。",
    "refresh": "重新整理", "name": "名稱", "created": "建立時間", "properties": "屬性", "summary": "摘要", "labels": "分類",
    "fact": "關係說明", "type": "類型", "episodes": "來源記憶", "attributes": "屬性", "examples": "範例", "connections": "連接對象",
    "entityTypes": "已辨識的對象類型", "relationTypes": "已辨識的關係類型", "entity": "對象", "relation": "關係", "chatQuestion": "你的問題", "sendQuestion": "送出問題", "graphLegend": "對象類型", "showEdgeLabels": "顯示關係名稱",
    "reportTitle": "模擬分析報告", "waitingReport": "等待報告內容…", "sections": "章節", "elapsed": "已用時間", "tools": "工具呼叫", "waitingActivity": "等待分析活動…", "reportComplete": "報告已完成", "consoleOutput": "執行紀錄", "you": "你", "reportAssistant": "報告助手", "plaza": "資訊廣場", "community": "話題社群", "round": "輪次", "time": "時間", "actions": "互動", "totalEvents": "互動總數"
}
traditional["meta"].update(title="MiroFish — 群體模擬工作室", description="從參考資料建立人物關係、模擬互動，再以報告與對話探索可能的結果。")
traditional["home"].update(systemReady="所有功能已就緒", systemReadyDesc="模型與圖譜服務已設定，可以開始完整的探索流程。")
traditional["main"]["stepNames"] = ["建立圖譜", "設定模擬", "執行模擬", "分析報告", "互動對話"]
traditional["step1"].update(ontologyGeneration="分析資料內容", ontologyDesc="閱讀參考資料與探索目標，辨識人物、組織、事件和它們可能的關係。", graphRagBuild="建立關係圖譜", graphRagDesc="把分析結果與原始資料連接起來，保存人物關係、事件與時間變化。", schemaTypes="對象與關係類型")
traditional["step2"].update(simInstanceInit="建立模擬", simInstanceDesc="載入這次探索的資料，建立模擬所需的基本設定。", generateAgentPersona="建立角色", generateAgentPersonaDesc="從人物關係中整理每個角色的背景、觀點與記憶。", dualPlatformConfig="安排模擬情境", dualPlatformConfigDesc="根據探索目標安排模擬時間、角色活動、事件與兩個平台的互動方式。", initialActivation="設定初始事件", initialActivationDesc="準備起始話題與發言，讓角色有共同的情境可以回應。", currentAgentCount="目前角色數", expectedAgentTotal="預計角色數", generatedAgentPersonas="已建立的角色", roundsConfig="模擬輪數", backToGraphBuild="返回關係圖譜", startDualWorldSim="開始模擬")
traditional["step5"].update(reportAgentChat="報告助手", reportAgentDesc="可查詢模擬資料並協助你理解結果的對話助手。", chatWithReportAgent="報告助手", chatWithAgent="角色對話", sendSurvey="問卷調查", interactiveTools="繼續探索", selectChatTarget="選擇對話角色")
traditional["step5"].update(toolInsightForge="原因分析", toolInsightForgeDesc="整理相關事件與角色記憶，探索反應背後的可能原因。", toolPanoramaSearch="事件追蹤", toolPanoramaSearchDesc="查看事件如何傳播，以及相關人物之間的聯繫。", toolQuickSearch="資料查詢", toolQuickSearchDesc="快速找出與問題有關的人物、關係與事實。", toolInterviewSubAgent="角色訪談", toolInterviewSubAgentDesc="向模擬角色提問，了解不同觀點與經驗。", chatEmptyReportAgent="向報告助手提問，進一步理解內容與結果。")
traditional["graph"].update(panelTitle="人物與事件關係圖", graphMemoryRealtime="正在更新角色記憶與人物關係")
traditional["step4"]["goToInteraction"] = "繼續追問"

english_studio = {
    "navigation": "Main navigation", "brandSubtitle": "Simulation studio", "history": "History",
    "workspace": "EXPLORATION STUDIO", "headline": "Explore before you decide.",
    "intro": "Start with a document. Map relationships, simulate different reactions, and explore possible outcomes through reports and conversation.",
    "preview": "Preview", "newProject": "NEW EXPLORATION", "startTitle": "What would you like to explore?",
    "uploadTitle": "Add reference material", "dropFiles": "Drop your files here", "browseFiles": "Or choose files. You can add more than one.",
    "addFiles": "Add more files", "removeFile": "Remove {name}", "uploadHelp": "PDF, Markdown and plain text are supported. A short document is a good place to start.",
    "goalTitle": "Describe your goal", "plainLanguage": "Your own words are enough",
    "goalPlaceholder": "For example: A cafe plans to extend its opening hours. How might nearby residents and regular customers react?",
    "goalHelp": "Describe the event, people and change you want to observe to help shape the simulation.",
    "start": "Start analysis", "startHelp": "Add material and a goal to begin. Project files are saved on this computer.", "stopSimulation": "Stop simulation",
    "serviceStatus": "Available features", "modelConnection": "Model connection", "graphConnection": "Graph service",
    "checking": "Checking", "connected": "Configured", "needsSetup": "Setup needed", "workflow": "Exploration workflow", "fiveSteps": "5 steps",
    "step1Title": "Map relationships", "step1Desc": "Analyze material and connect people and events.",
    "step2Title": "Set up the simulation", "step2Desc": "Create characters, a scenario and simulation rounds.",
    "step3Title": "Observe interactions", "step3Desc": "Follow posts and reactions on both platforms.",
    "step4Title": "Read the report", "step4Desc": "Understand the results and how they emerged.",
    "step5Title": "Ask follow-up questions", "step5Desc": "Talk to characters and the report assistant.",
    "explorationNote": "Simulations offer clues for exploration. Interpret them alongside source material and real-world observations.",
    "footer": "From information to clearer ideas.", "noHistory": "No simulations yet", "historyHelp": "Your progress will appear here once a simulation has been created.",
    "checkingTitle": "Checking service status", "checkingDesc": "Checking which features are currently available.",
    "analysisReady": "Document analysis available", "modelPending": "Model setup needed",
    "analysisReadyDesc": "You can upload and analyze material. A graph service is still needed for graphs and the full simulation workflow.",
    "modelPendingDesc": "Configure a model connection before uploading and analyzing material.",
    "serviceError": "Cannot connect to the service. Check that MiroFish is running, then refresh the page.",
    "serviceStarted": "MiroFish is running. You can upload and analyze material.",
    "modelNotice": "A model connection is needed before document analysis is available.",
    "graphNotice": "Graph setup needed: graphs, simulations and full reports require a Zep Cloud connection.",
    "refresh": "Refresh", "name": "Name", "created": "Created", "properties": "Properties", "summary": "Summary", "labels": "Labels",
    "fact": "Fact", "type": "Type", "episodes": "Source episodes", "attributes": "Attributes", "examples": "Examples", "connections": "Connections",
    "entityTypes": "Identified entity types", "relationTypes": "Identified relationship types", "entity": "Entity", "relation": "Relationship", "chatQuestion": "Your question", "sendQuestion": "Send question", "graphLegend": "Entity types", "showEdgeLabels": "Show relationship labels",
    "reportTitle": "Simulation report", "waitingReport": "Waiting for report content…", "sections": "Sections", "elapsed": "Elapsed", "tools": "Tool calls", "waitingActivity": "Waiting for analysis activity…", "reportComplete": "Report complete", "consoleOutput": "Execution log", "you": "You", "reportAssistant": "Report assistant", "plaza": "Info Plaza", "community": "Topic Community", "round": "Round", "time": "Time", "actions": "Actions", "totalEvents": "Total events"
}
english = json.loads((locales / "en.json").read_text(encoding="utf-8"))
english["studio"] = english_studio
simplified = json.loads((locales / "zh.json").read_text(encoding="utf-8"))
simplified["studio"] = json.loads(OpenCC("t2s").convert(json.dumps(traditional["studio"], ensure_ascii=False)))
registry = json.loads((locales / "languages.json").read_text(encoding="utf-8"))
registry["zh"]["label"] = "简体中文"
registry["zh-TW"] = {"label": "繁體中文", "llmInstruction": "請使用繁體中文回答。"}
for name, data in [("zh-TW", traditional), ("en", english), ("zh", simplified), ("languages", registry)]:
    (locales / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Traditional Chinese catalog generated; English and Simplified Chinese retained.")
