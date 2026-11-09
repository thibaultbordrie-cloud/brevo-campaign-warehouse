@echo off
rem Runs the pipeline with %PORTABLE_PYTHON% if set (portable Python, no install rights), otherwise python.
setlocal
cd /d "%~dp0"
set "PY=python"
if defined PORTABLE_PYTHON set "PY=%PORTABLE_PYTHON%"
if "%~1"=="" (
  "%PY%" run.py ingest && "%PY%" run.py kpis --limit 20
) else (
  "%PY%" run.py %*
)
echo.
pause
endlocal
