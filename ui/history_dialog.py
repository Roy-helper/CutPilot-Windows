"""Processing history dialog for CutPilot.

Displays a table of past processing runs with status, version count,
and approach tags. Supports clearing history and opening output directories.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.history import clear_history, load_history

logger = logging.getLogger(__name__)

_COLUMN_HEADERS = ["时间", "视频名", "状态", "版本数", "切入角度", "操作"]
_COLUMN_COUNT = len(_COLUMN_HEADERS)


class HistoryDialog(QDialog):
    """Dialog showing processing history in a dark-themed table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("处理历史")
        self.setMinimumSize(800, 480)
        self.resize(900, 540)

        self._setup_ui()
        self._load_entries()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(_COLUMN_COUNT)
        self._table.setHorizontalHeaderLabels(_COLUMN_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, 1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        clear_btn = QPushButton("清空历史")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(clear_btn)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_entries(self) -> None:
        """Populate table from history file, newest first."""
        entries = load_history()
        entries.reverse()  # newest first

        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._set_row(row, entry)

    def _set_row(self, row: int, entry: dict) -> None:
        """Fill one table row from a history entry dict."""
        timestamp = entry.get("timestamp", "")[:19].replace("T", " ")
        video_name = entry.get("video_name", "")
        success = entry.get("success", False)
        versions_count = entry.get("versions_count", 0)
        approach_tags = entry.get("approach_tags", [])

        status_text = "成功" if success else "失败"
        tags_text = ", ".join(approach_tags) if approach_tags else "-"

        self._table.setItem(row, 0, QTableWidgetItem(timestamp))
        self._table.setItem(row, 1, QTableWidgetItem(video_name))

        status_item = QTableWidgetItem(status_text)
        status_item.setForeground(
            Qt.GlobalColor.green if success else Qt.GlobalColor.red
        )
        self._table.setItem(row, 2, status_item)

        count_item = QTableWidgetItem(str(versions_count))
        count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 3, count_item)

        self._table.setItem(row, 4, QTableWidgetItem(tags_text))

        # "Open output" button
        output_files = entry.get("output_files", [])
        if output_files:
            open_btn = QPushButton("打开目录")
            open_btn.setObjectName("copyButton")
            first_file = output_files[0]
            open_btn.clicked.connect(
                lambda checked=False, p=first_file: self._open_output_dir(p)
            )
            self._table.setCellWidget(row, 5, open_btn)
        else:
            self._table.setItem(row, 5, QTableWidgetItem("-"))

    def _on_clear(self) -> None:
        """Clear history after user confirmation."""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有处理历史吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_history()
            self._table.setRowCount(0)

    @staticmethod
    def _open_output_dir(file_path: str) -> None:
        """Open the directory containing the given file in the system explorer."""
        target = Path(file_path)
        directory = target.parent if target.is_file() else target
        if not directory.exists():
            logger.warning("Output directory does not exist: %s", directory)
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])  # noqa: S603
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(directory)])  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(directory)])  # noqa: S603
