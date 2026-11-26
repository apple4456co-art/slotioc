@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m py_compile app.py mobile_hub.py
  if errorlevel 1 goto fail
  python app.py --self-test
) else (
  py -3 -m py_compile app.py mobile_hub.py
  if errorlevel 1 goto fail
  py -3 app.py --self-test
)
if errorlevel 1 goto fail
echo.
echo PASS: Python syntax and core application tests
pause
exit /b 0
:fail
echo.
echo TEST FAILED. Check the error message above.
pause
exit /b 1
