@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  start "Shopee Affiliate Mobile Hub" /D "%~dp0" cmd /k "python mobile_hub.py"
  python app.py
) else (
  start "Shopee Affiliate Mobile Hub" /D "%~dp0" cmd /k "py -3 mobile_hub.py"
  py -3 app.py
)
if errorlevel 1 (
  echo.
  echo โปรแกรมปิดพร้อมข้อผิดพลาด กรุณาตรวจสอบว่าติดตั้ง Python 3.10+ แล้ว
  pause
)
