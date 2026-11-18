@echo off
REM Build LanDrop.exe (butuh Python 3.10+). Hasil: dist\LanDrop.exe
cd /d "%~dp0"
set VENV=%TEMP%\ldvenv
if not exist "%VENV%\Scripts\python.exe" (
  python -m venv "%VENV%" || goto :err
  "%VENV%\Scripts\python" -m pip install -q pyinstaller || goto :err
)
if not exist icon.ico python make_icon.py
"%VENV%\Scripts\python" -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name LanDrop --icon "%~dp0icon.ico" ^
  --add-data "%~dp0ui.html;." --add-data "%~dp0icon.ico;." --add-data "%~dp0sandymind-logo.png;." ^
  --workpath "%TEMP%\ldbuild" --specpath "%TEMP%\ldbuild" ^
  landrop.py || goto :err
echo.
echo Selesai: %~dp0dist\LanDrop.exe
exit /b 0
:err
echo Build gagal.
exit /b 1
