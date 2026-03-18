import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from src.core.config import ConfigManager
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Payment Reconciler")
    base = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base, "config.json")
    if not os.path.exists(config_path):
        import shutil
        default = os.path.join(base, "config.default.json")
        if os.path.exists(default):
            shutil.copy2(default, config_path)
    config = ConfigManager(config_path)
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
