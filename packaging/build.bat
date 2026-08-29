@echo off
REM Build the Dia Gold CRM desktop app on Windows.
setlocal
cd /d "%~dp0\.."

python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller packaging\DiaGoldCRM.spec --noconfirm

powershell -Command "Compress-Archive -Path dist/DiaGoldCRM/* -DestinationPath dist/DiaGoldCRM-Windows-x64.zip -Force"
echo Built: dist\DiaGoldCRM-Windows-x64.zip
endlocal
