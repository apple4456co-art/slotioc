@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Shopee Affiliate Mobile Hub" cmd /k "cd /d ""%~dp0"" && py -3 mobile_hub.py"
  py -3 app.py
) else (
  start "Shopee Affiliate Mobile Hub" cmd /k "cd /d ""%~dp0"" && python mobile_hub.py"
  python app.py
)
if errorlevel 1 (
  echo.
  echo โปรแกรมปิดพร้อมข้อผิดพลาด กรุณาตรวจสอบว่าติดตั้ง Python 3.10+ แล้ว
  pause
)
