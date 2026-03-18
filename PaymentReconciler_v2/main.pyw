import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from src.core.config import ConfigManager
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Payment Reconciler")
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    config = ConfigManager(config_path)
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
