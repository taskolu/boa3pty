# Build Windows EXE

Open this `PaymentReconciler_v4` folder in VS Code on Windows.

## One-click VS Code Build

1. Install Python 3.11 or 3.12 for Windows.
2. Open `PaymentReconciler_v4` in VS Code.
3. Press `Ctrl+Shift+B`.
4. Choose `Build Windows EXE` if VS Code asks.

The finished app will be here:

```text
C:\Users\AbduTas\OneDrive - Convera\Desktop\asdasd\BOA3PTY WSFX\Exotic Payment Reconciler\Exotic Payment Reconciler.exe
```

## Manual Build

From a VS Code terminal in `PaymentReconciler_v4`:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements_v2.txt
python -m PyInstaller --clean --noconfirm --distpath "C:\Users\AbduTas\OneDrive - Convera\Desktop\asdasd\BOA3PTY WSFX" PaymentReconciler_v4.spec
```

## Notes

- The app icon is bundled from `assets\app_icon.ico`.
- `config.json` is created beside the `.exe` on first launch by copying `config.default.json`.
- Keep the whole `C:\Users\AbduTas\OneDrive - Convera\Desktop\asdasd\BOA3PTY WSFX\Exotic Payment Reconciler` folder together when sharing the app.
