import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.core.app_dir import get_app_dir
from src.core.config import ConfigManager
from src.ui.main_window import MainWindow


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def center_on_primary_screen(window, app):
    screen = app.primaryScreen()
    if screen is None:
        return

    frame = window.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    window.move(frame.topLeft())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Exotic Payment Reconciler")
    app_dir = get_app_dir()
    icon_path = resource_path("assets", "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    config_path = os.path.join(app_dir, "config.json")
    if not os.path.exists(config_path):
        import shutil
        default = resource_path("config.default.json")
        if os.path.exists(default):
            shutil.copy2(default, config_path)
    config = ConfigManager(config_path)
    window = MainWindow(config)
    center_on_primary_screen(window, app)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
