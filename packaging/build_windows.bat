@echo off
REM ---------------------------------------------------------------------------
REM  Build LocalLeadScraperPro.exe on Windows.
REM
REM    packaging\build_windows.bat
REM
REM  Needs Python 3.10+ on PATH. Everything else is installed into a local
REM  virtual environment under .venv-build\, so your system Python is untouched.
REM  The finished executable lands in dist\LocalLeadScraperPro.exe.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python was not found on PATH. Install Python 3.10 or newer first.
    exit /b 1
)

echo [1/5] Creating the build environment...
if not exist .venv-build (
    python -m venv .venv-build || exit /b 1
)
call .venv-build\Scripts\activate.bat

echo [2/5] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -r requirements-gui.txt || exit /b 1

echo [3/5] Generating the icon and version resource...
python packaging\make_icon.py || exit /b 1
python packaging\make_version_info.py || exit /b 1

echo [4/5] Building the executable (this takes a few minutes)...
pyinstaller --clean --noconfirm packaging\LocalLeadScraperPro.spec || exit /b 1

echo [5/5] Done.
if exist dist\LocalLeadScraperPro.exe (
    echo.
    echo     dist\LocalLeadScraperPro.exe
    echo.
    echo Copy that single file anywhere and double-click it. Google Chrome is
    echo required for live scraping; Demo mode needs nothing at all.
) else (
    echo [X] The build finished but dist\LocalLeadScraperPro.exe is missing.
    exit /b 1
)
endlocal
