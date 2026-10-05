@echo off
rem Throws the demo database away and starts it again from the demo data.
start "" "%~dp0DiaGoldCRM.exe" --demo --reset
