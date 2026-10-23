@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === PC Time: step 1/2 - building PCTime.exe ===
python -m pip install --upgrade -r requirements.txt pyinstaller || goto :error
python -m PyInstaller --noconfirm --clean --noconsole --onefile ^
  --name PCTime ^
  --icon assets\icon.ico ^
  --version-file version_info.txt ^
  pc_time.py || goto :error

echo.
echo === PC Time: step 2/2 - building installer ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto :noinno
"%ISCC%" installer.iss || goto :error
echo.
echo Done: dist\PCTime-Setup-1.1.0.exe  [installer]
echo       dist\PCTime.exe                [portable]
explorer dist
pause
exit /b 0

:noinno
echo Inno Setup 6 not found, installer skipped.
echo Install it: winget install JRSoftware.InnoSetup
echo   or download: https://jrsoftware.org/isdl.php
echo Then run build.bat again.
echo.
echo Portable exe is ready: dist\PCTime.exe
explorer dist
pause
exit /b 0

:error
echo.
echo Build failed. See the messages above.
pause
exit /b 1
