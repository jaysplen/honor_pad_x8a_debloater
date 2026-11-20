@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 honor_x8a_debloater.py
) else (
  python honor_x8a_debloater.py
)
echo.
pause
