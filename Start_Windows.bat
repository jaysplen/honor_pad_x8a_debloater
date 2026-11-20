@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"

py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_py

python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_python

echo Python 3.9 or newer is required. Install Python from https://www.python.org/downloads/windows/. 1>&2
if "%~1"=="" pause
exit /b 1

:run_py
py -3 "%~dp0honor_x8a_debloater.py" %*
goto finish

:run_python
python "%~dp0honor_x8a_debloater.py" %*

:finish
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
