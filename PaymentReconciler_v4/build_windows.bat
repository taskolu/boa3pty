@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements_v2.txt
python -m PyInstaller --clean --noconfirm PaymentReconciler_v4.spec

echo.
echo Build complete: dist\PaymentReconciler_v4\PaymentReconciler_v4.exe
pause
