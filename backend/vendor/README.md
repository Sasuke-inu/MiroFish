# 本機 OASIS 依賴修正版

`camel_oasis-0.2.5+mirofish.1-py3-none-any.whl` 由官方 PyPI 的 OASIS 0.2.5 製作。
它保留原始 Python 程式和授權檔，只修改套件的版本標記與依賴清單。

上游 SHA256：`9ebd6ba8e331495ee56b25cc63982188b94125dde499e5e9c00398a1d47e606d`

本機 SHA256：`7bf446b1ff3601771aea0b46fd3286051299fb0c7c8d064a194de16e1d2dca9e`

調整原因：上游將舊版測試工具、文件工具及未使用的第三方服務套件列為必要依賴，
會安裝多個已知有安全問題的版本。這份修正版只保留 OASIS 程式實際引用的套件；
CAMEL 更新至官方 OASIS 主分支使用的 0.2.90，文字向量工具則更新至有修正版的系列。
CAMEL 自身需要的 Pillow 仍會安裝。

重製方式：從專案根目錄執行 `python deploy/build-oasis-wheel.py`。
腳本先驗證官方下載檔的 SHA256，再重製套件並驗證原始程式未改動。

模擬啟動時另載入 `app/utils/oasis_camel_compat.py`。它只對 OASIS 的角色類別
移除新版 CAMEL 已不接受的 `num_tokens` 訪談參數，讓訪談與問卷保持可用。
這項執行時修正沒有改寫上述 wheel 或 CAMEL 的原始程式。

官方來源：[PyPI](https://pypi.org/project/camel-oasis/0.2.5/)、
[OASIS 套件清單](https://github.com/camel-ai/oasis/blob/main/pyproject.toml)。
