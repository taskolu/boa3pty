@echo off
setlocal
cd /d "%~dp0"
set "BUILD_OUTPUT=C:\Users\AbduTas\OneDrive - Convera\Desktop\asdasd\BOA3PTY WSFX"
set "BUILD_WORK=%TEMP%\PaymentReconciler_v4_build"

if exist "%BUILD_WORK%" (
    rmdir /s /q "%BUILD_WORK%"
)
mkdir "%BUILD_WORK%"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto :fail
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements_v2.txt
if errorlevel 1 goto :fail
python -m PyInstaller --clean --noconfirm --workpath "%BUILD_WORK%" --distpath "%BUILD_OUTPUT%" PaymentReconciler_v4.spec
if errorlevel 1 goto :fail

echo.
echo Build complete: %BUILD_OUTPUT%\Exotic Payment Reconciler\Exotic Payment Reconciler.exe
pause
exit /b 0

:fail
echo.
echo Build failed. Close the app/Excel if it is open, then run this build again.
pause
exit /b 1
