@echo off
rem Daily unattended ingestion, launched by Windows Task Scheduler.
rem 1. load Brevo into the warehouse   2. run the data checks and email the owner if needed.
rem No pause at the end; all output is appended to logs\ingest.log.
rem Redirections are written first (">>file echo ...") so that a number such as
rem the exit code is never read by cmd as a stream number ("0>>" would mean stdin).
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set "PY=python"
if defined PORTABLE_PYTHON set "PY=%PORTABLE_PYTHON%"
>>logs\ingest.log echo [%date% %time%] start
>>logs\ingest.log 2>&1 "%PY%" run.py ingest
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  >>logs\ingest.log 2>&1 "%PY%" run.py alerts --failure "Code de sortie %RC%. Voir logs\ingest.log sur le PC."
) else (
  >>logs\ingest.log 2>&1 "%PY%" run.py alerts
)
>>logs\ingest.log echo [%date% %time%] end, exit code %RC%
endlocal & exit /b %RC%
