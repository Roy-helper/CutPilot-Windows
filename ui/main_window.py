"""CutPilot main window — AI 副驾驶.

Dark-themed professional desktop UI for e-commerce video automation.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QListWidget,
    QListWidgetItem, QFrame, QFileDialog, QScrollArea,
    QStatusBar, QApplication,
)

from ui.styles import DARK_THEME
from ui.drop_zone import DropZone
from ui.result_panel import ResultPanel


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CutPilot — AI 副驾驶")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(DARK_THEME)

        self._setup_ui()
        self._setup_statusbar()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 16, 20, 12)
        main_layout.setSpacing(16)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("CutPilot")
        title.setObjectName("titleLabel")
        subtitle = QLabel("AI 副驾驶 — 电商短视频智能剪辑")
        subtitle.setObjectName("subtitleLabel")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        main_layout.addLayout(header)

        # ── Body: sidebar + results ──
        body = QHBoxLayout()
        body.setSpacing(16)

        # Left sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        # Drop zone
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        sidebar_layout.addWidget(self.drop_zone)

        # File list
        list_label = QLabel("已导入素材")
        list_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        sidebar_layout.addWidget(list_label)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(200)
        sidebar_layout.addWidget(self.file_list)

        # Output directory
        output_layout = QHBoxLayout()
        self.output_label = QLabel("输出目录: 未选择")
        self.output_label.setStyleSheet("font-size: 11px; color: #7a7a9e;")
        output_btn = QPushButton("选择")
        output_btn.setObjectName("secondaryButton")
        output_btn.setMaximumWidth(60)
        output_btn.clicked.connect(self._select_output_dir)
        output_layout.addWidget(self.output_label, 1)
        output_layout.addWidget(output_btn)
        sidebar_layout.addLayout(output_layout)

        sidebar_layout.addStretch()

        # Action buttons
        self.generate_btn = QPushButton("一键生成")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self._on_generate)
        self.generate_btn.setEnabled(False)
        sidebar_layout.addWidget(self.generate_btn)

        self.export_btn = QPushButton("导出全部")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)
        sidebar_layout.addWidget(self.export_btn)

        sidebar.setFixedWidth(320)
        body.addWidget(sidebar)

        # Right results panel
        self.result_panel = ResultPanel()
        body.addWidget(self.result_panel, 1)

        main_layout.addLayout(body, 1)

        # ── Progress bar ──
        progress_frame = QFrame()
        progress_frame.setObjectName("progressFrame")
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(16, 8, 16, 8)

        self.progress_label = QLabel("就绪")
        self.progress_label.setStyleSheet("font-size: 12px; color: #7a7a9e;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)

        progress_layout.addWidget(self.progress_label, 0)
        progress_layout.addWidget(self.progress_bar, 1)

        main_layout.addWidget(progress_frame)

        # State
        self._video_files: list[Path] = []
        self._output_dir: Path | None = None

    def _setup_statusbar(self):
        status = QStatusBar()
        status.showMessage("CutPilot v0.1.0 — 拖入视频开始使用")
        self.setStatusBar(status)

    def _on_files_dropped(self, file_paths: list[str]):
        """Handle files dropped onto the drop zone."""
        for fp in file_paths:
            path = Path(fp)
            if path.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".flv"):
                if path not in self._video_files:
                    self._video_files.append(path)
                    item = QListWidgetItem(f"○  {path.name}")
                    self.file_list.addItem(item)

        self.generate_btn.setEnabled(len(self._video_files) > 0)
        self.statusBar().showMessage(f"已导入 {len(self._video_files)} 个视频")

    def _select_output_dir(self):
        """Open directory picker for output."""
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self._output_dir = Path(dir_path)
            display = str(self._output_dir)
            if len(display) > 35:
                display = "..." + display[-32:]
            self.output_label.setText(f"输出目录: {display}")

    def _on_generate(self):
        """Start processing all imported videos."""
        if not self._video_files:
            return

        # TODO: Implement pipeline worker thread
        self.generate_btn.setEnabled(False)
        self.progress_label.setText("处理中...")
        self.progress_bar.setValue(10)
        self.statusBar().showMessage("正在处理视频...")

    def _on_export(self):
        """Export all processed videos to output directory."""
        if self._output_dir is None:
            self._select_output_dir()
        if self._output_dir is None:
            return

        # TODO: Implement export logic
        self.statusBar().showMessage(f"已导出到 {self._output_dir}")
