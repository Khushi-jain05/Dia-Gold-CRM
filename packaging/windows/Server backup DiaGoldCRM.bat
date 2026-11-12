@echo off
rem Daily backup of the Dia Gold CRM database - run ON SERVER2, from Windows
rem Task Scheduler (SQL Server Express has no SQL Agent to schedule it).
rem Writes DiaGoldCRM_YYYYMMDD.bak to the server's own backup folder and keeps
rem the last 14 days. Copy that folder off the server (USB / cloud) regularly.

set SERVER=SERVER2\ERP
set FOLDER=C:\Program Files\Microsoft SQL Server\MSSQL15.ERP\MSSQL\Backup

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set D=%%i

sqlcmd -S %SERVER% -E -b -Q "BACKUP DATABASE DiaGoldCRM TO DISK = N'%FOLDER%\DiaGoldCRM_%D%.bak' WITH INIT, CHECKSUM"
if errorlevel 1 (
  echo BACKUP FAILED %date% %time% >> "%FOLDER%\DiaGoldCRM_backup_log.txt"
  exit /b 1
)
echo backup ok %D% >> "%FOLDER%\DiaGoldCRM_backup_log.txt"

forfiles /p "%FOLDER%" /m DiaGoldCRM_*.bak /d -14 /c "cmd /c del @path" 2>nul
exit /b 0
