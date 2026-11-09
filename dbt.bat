@echo off
rem Runs dbt on the warehouse, from the transform folder, with %PORTABLE_PYTHON% if set.
rem Examples:  dbt.bat build      dbt.bat docs generate --static
setlocal
cd /d "%~dp0transform"
set "PY=python"
if defined PORTABLE_PYTHON set "PY=%PORTABLE_PYTHON%"
"%PY%" run_dbt.py %* --profiles-dir .
set "RC=%errorlevel%"
endlocal & exit /b %RC%
