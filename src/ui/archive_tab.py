import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from src.archive.archive_manager import ArchiveManager


class ArchiveTab(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Past Reconciliations"))
        top.addStretch()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        layout.addLayout(top)

        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        layout.addWidget(self.tbl, 1)

        self.refresh()

    def refresh(self):
        archive_path = self.config.archive_path
        if not os.path.isabs(archive_path):
            archive_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", archive_path
            )

        try:
            am = ArchiveManager(archive_path)
            archives = am.list_archives()
        except Exception:
            archives = []

        headers = ["Date", "Counterparty", "File"]
        self.tbl.setColumnCount(len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setRowCount(len(archives))

        for i, arch in enumerate(archives):
            self.tbl.setItem(i, 0, QTableWidgetItem(arch["date"]))
            self.tbl.setItem(i, 1, QTableWidgetItem(arch["counterparty"]))
            self.tbl.setItem(i, 2, QTableWidgetItem(arch["file"]))
