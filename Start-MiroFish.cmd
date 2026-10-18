@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo 請先開啟 Docker Desktop，等候它啟動完成，再執行此檔案。
  pause
  exit /b 1
)
if not exist ".env" (
  echo 找不到 .env 設定檔。請依照 INSTALLATION-ZH-TW.md 完成設定。
  pause
  exit /b 1
)
docker compose -f docker-compose.local.yml up -d --wait
if errorlevel 1 (
  echo MiroFish 啟動未完成。請將上面的錯誤訊息提供給協助人員。
  pause
  exit /b 1
)
if /I not "%~1"=="--no-browser" start "" "http://localhost:3100"
exit /b 0
