@echo off
setlocal
REM Build the AG Image Tune GUI into a standalone Windows .exe.
REM Prerequisites: Python 3.9+ (python.org, tick "Add python.exe to PATH")
REM                 py -m pip install --upgrade pillow pyinstaller
REM Run this file from the project root (double-click is fine).
REM
REM --- Antivirus false positives: why these flags are here -------------------
REM   --noupx         UPX-packed binaries are the single biggest heuristic-AV
REM                   trigger. PyInstaller uses UPX automatically if it finds
REM                   it on PATH, so we switch it off explicitly.
REM   --version-file  embeds real product/company metadata (see
REM                   version_info.txt). An unsigned exe with no version
REM                   resource looks anonymous to ML engines.
REM   --clean         build from scratch, so no stale objects get bundled.
REM
REM   Still flagged? Set MODE=--onedir below and rebuild. One-file builds are
REM   a self-extracting bootloader that unpacks to %TEMP% at startup - that is
REM   literally what droppers do, so ML engines hate it. One-dir layouts get
REM   far fewer detections; ship dist\AGImageTune\ as a .zip instead.
REM --------------------------------------------------------------------------

set NAME=AGImageTune
set ENTRY=agimage_tune_gui.py
set MODE=--onefile
REM set MODE=--onedir

pyinstaller --noconfirm --clean %MODE% --noupx --windowed ^
  --name %NAME% --version-file version_info.txt %ENTRY%

if errorlevel 1 (
  echo.
  echo Build FAILED - see the messages above.
  pause
  exit /b 1
)

echo.
if "%MODE%"=="--onedir" (
  echo Build finished. Run dist\%NAME%\%NAME%.exe - the whole folder is the app.
) else (
  echo Build finished. The .exe is at dist\%NAME%.exe
)
echo Note: some antivirus engines flag PyInstaller output as a false positive.
echo See "Antivirus false positives" in docs\AGIMAGE_GUI.md before publishing.
pause

REM --- Original build command (kept for reference) --------------------------
REM pyinstaller --noconfirm --clean --onefile --windowed --name AGImageTune ^
REM   agimage_tune_gui.py
