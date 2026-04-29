@echo off
setlocal
cd /d "%~dp0"
set "BUILD_OUTPUT=C:\Users\AbduTas\OneDrive - Convera\Desktop\asdasd\BOA3PTY WSFX"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements_v2.txt
python -m PyInstaller --clean --noconfirm --distpath "%BUILD_OUTPUT%" PaymentReconciler_v4.spec

echo.
echo Build complete: %BUILD_OUTPUT%\Exotic Payment Reconciler\Exotic Payment Reconciler.exe
pause
