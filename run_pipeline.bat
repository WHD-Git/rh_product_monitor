@echo off
setlocal

set "DIR=%~dp0"
set "PYTHON=%DIR%.venv\Scripts\python.exe"

for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"') do set TODAY=%%i

set "LOGS=%DIR%data\logs"
set "LOG=%LOGS%\pipeline_%TODAY%.log"
mkdir "%LOGS%" 2>nul

echo [%TODAY% %TIME%] ===== Pipeline starting ===== >> "%LOG%"

"%PYTHON%" "%DIR%downloader.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%TIME%] ERROR: downloader.py failed - aborting >> "%LOG%"
    exit /b 1
)
echo [%TIME%] downloader.py OK >> "%LOG%"

"%PYTHON%" "%DIR%analyser.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%TIME%] ERROR: analyser.py failed - aborting >> "%LOG%"
    exit /b 1
)
echo [%TIME%] analyser.py OK >> "%LOG%"

"%PYTHON%" "%DIR%comparator.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%TIME%] ERROR: comparator.py failed - aborting >> "%LOG%"
    exit /b 1
)
echo [%TIME%] comparator.py OK >> "%LOG%"

echo [%TIME%] ===== Pipeline completed successfully ===== >> "%LOG%"
exit /b 0
