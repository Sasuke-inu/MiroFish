@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker compose -f docker-compose.local.yml stop
if errorlevel 1 (
  echo 停止服務時發生問題，請查看上面的錯誤訊息。
  pause
  exit /b 1
)
echo MiroFish 已停止，已儲存的資料仍保留。
pause
