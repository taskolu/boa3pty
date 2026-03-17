import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from src.core.config import ConfigManager
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Payment Reconciler")
    app.setStyle("Fusion")

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )
    config = ConfigManager(config_path)

    window = MainWindow(config)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
