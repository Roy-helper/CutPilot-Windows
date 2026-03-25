"""CutPilot main window — AI 副驾驶.

Dark-themed professional desktop UI for e-commerce video automation.
"""
from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QListWidget,
    QListWidgetItem, QFrame, QFileDialog,
    QStatusBar, QMessageBox,
)

from core.config import CutPilotConfig
from core.history import HistoryEntry, add_history_entry
from core.license import check_license, consume_trial, get_trial_remaining
from core.models import ProcessResult
from core.pipeline import generate_copy_text
from core.user_settings import build_config_from_settings, load_user_settings
from ui.activation_dialog import ActivationDialog
from ui.drop_zone import DropZone
from ui.history_dialog import HistoryDialog
from ui.result_panel import ResultPanel
from ui.settings_dialog import SettingsDialog
from ui.styles import DARK_THEME
from ui.worker import PipelineWorker


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CutPilot — AI 副驾驶")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(DARK_THEME)

        self._video_files: list[Path] = []
        self._output_dir: Path | None = None
        self._results: dict[str, ProcessResult] = {}
        self._worker: PipelineWorker | None = None
        self._is_trial_mode: bool = False

        self._setup_ui()
        self._setup_statusbar()
        self._check_license_on_startup()

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

        history_btn = QPushButton("\U0001f4cb")
        history_btn.setObjectName("settingsButton")
        history_btn.setFixedSize(36, 36)
        history_btn.setToolTip("处理历史")
        history_btn.clicked.connect(self._open_history)
        header.addWidget(history_btn)

        settings_btn = QPushButton("\u2699")
        settings_btn.setObjectName("settingsButton")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setToolTip("设置")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)

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

        self.export_btn = QPushButton("导出选中")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)
        sidebar_layout.addWidget(self.export_btn)

        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.clicked.connect(self._on_clear)
        sidebar_layout.addWidget(self.clear_btn)

        sidebar.setFixedWidth(320)
        body.addWidget(sidebar)

        # Right results panel
        self.result_panel = ResultPanel()
        self.result_panel.selection_changed.connect(self._on_selection_changed)
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

    def _setup_statusbar(self):
        status = QStatusBar()
        status.showMessage("CutPilot v0.1.0 — 拖入视频开始使用")
        self.setStatusBar(status)

    # ── License ──

    def _check_license_on_startup(self) -> None:
        """Check license status and show activation dialog if needed."""
        is_valid, message, expiry = check_license()

        if is_valid and expiry is not None:
            self.statusBar().showMessage(
                f"CutPilot v0.1.0 | 授权有效，到期: {expiry.isoformat()}"
            )
            return

        # No valid license — show activation dialog
        dialog = ActivationDialog(self)
        result = dialog.exec()

        if result == ActivationDialog.Accepted:
            # Successfully activated
            _, _, new_expiry = check_license()
            expiry_str = new_expiry.isoformat() if new_expiry else "未知"
            self.statusBar().showMessage(
                f"CutPilot v0.1.0 | 激活成功，到期: {expiry_str}"
            )
        elif ActivationDialog.result_is_trial(result):
            # Trial mode
            remaining = get_trial_remaining()
            self.statusBar().showMessage(
                f"CutPilot v0.1.0 | 试用模式 (剩余 {remaining} 次)"
            )
            self._is_trial_mode = True
        else:
            # User closed dialog without activating or trial
            self.statusBar().showMessage("CutPilot v0.1.0 | 未激活")
            self.generate_btn.setEnabled(False)
            self._lock_for_no_license()

    def _lock_for_no_license(self) -> None:
        """Disable generation when no license and no trial."""
        self.generate_btn.setEnabled(False)
        self.drop_zone.setEnabled(False)

    # ── File management ──

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

    # ── Pipeline ──

    def _open_settings(self) -> None:
        """Open the settings dialog and reload config on accept."""
        dialog = SettingsDialog(self)
        if dialog.exec() == SettingsDialog.Accepted:
            self.statusBar().showMessage("设置已保存")

    def _open_history(self) -> None:
        """Open the processing history dialog."""
        dialog = HistoryDialog(self)
        dialog.exec()

    def _on_generate(self):
        """Start processing all imported videos."""

        if not self._video_files:
            return

        # License check before generation
        is_valid, _, _ = check_license()
        if not is_valid and self._is_trial_mode:
            success, remaining = consume_trial()
            if not success:
                QMessageBox.warning(
                    self, "试用结束",
                    "试用次数已用完，请输入激活码继续使用。",
                )
                self._check_license_on_startup()
                return
            self.statusBar().showMessage(
                f"试用模式 | 剩余 {remaining} 次"
            )
        elif not is_valid:
            self._check_license_on_startup()
            return

        config = build_config_from_settings()
        if not config.api_key:
            self._open_settings()
            # Re-check after dialog
            config = build_config_from_settings()
            if not config.api_key:
                return

        settings = load_user_settings()
        hotwords = settings.get("hotwords", "")

        self.generate_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.result_panel.clear()
        self._results.clear()

        self._worker = PipelineWorker(
            self._video_files, config, hotwords=hotwords,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.video_done.connect(self._on_video_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_progress(self, label: str, percent: int):
        """Update progress bar from worker signal."""
        self.progress_label.setText(label)
        self.progress_bar.setValue(percent)
        self.statusBar().showMessage(label)

    def _on_video_done(self, filename: str, result: ProcessResult):
        """Handle one video completion."""
        self._results[filename] = result

        # Update file list icon
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item and filename in item.text():
                icon = "✓" if result.success else "✗"
                item.setText(f"{icon}  {filename}")
                break

        # Show results in panel
        if result.success:
            product_name = Path(filename).stem
            self.result_panel.show_versions(product_name, result.versions)
        else:
            self.statusBar().showMessage(f"{filename}: {result.error}")

        # Record history
        self._record_history(filename, result)

    def _record_history(self, filename: str, result: ProcessResult) -> None:
        """Record a processing result to the history log."""
        # Find the matching video path
        video_path = ""
        for vf in self._video_files:
            if vf.name == filename:
                video_path = str(vf)
                break

        entry = HistoryEntry(
            video_name=filename,
            video_path=video_path,
            timestamp=datetime.now(UTC).isoformat(),
            success=result.success,
            error=result.error,
            versions_count=len(result.versions),
            output_files=[f["path"] for f in result.output_files],
            approach_tags=[v.approach_tag for v in result.versions if v.approach_tag],
        )
        add_history_entry(entry)

    def _on_all_done(self):
        """Handle all videos processed."""
        self._worker = None
        self.generate_btn.setEnabled(True)

        success_count = sum(1 for r in self._results.values() if r.success)
        total = len(self._results)
        selected = self.result_panel.get_selected_count()
        version_total = self.result_panel.get_total_count()
        self.statusBar().showMessage(
            f"处理完成: {success_count}/{total} 个视频成功 "
            f"| 已选择 {selected}/{version_total} 个版本"
        )

        if success_count > 0:
            self.export_btn.setEnabled(True)

    def _on_selection_changed(self, selected: int, total: int):
        """Update status bar when version selection changes."""
        if total > 0:
            self.statusBar().showMessage(
                f"已选择 {selected}/{total} 个版本"
            )

    def _on_worker_error(self, error_msg: str):
        """Handle fatal worker error."""
        self._worker = None
        self.generate_btn.setEnabled(True)
        self.progress_label.setText("错误")
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "处理失败", error_msg)

    # ── Export ──

    def _on_export(self):
        """Export selected versions to output directory."""
        if self._output_dir is None:
            self._select_output_dir()
        if self._output_dir is None:
            return

        selections = self.result_panel.get_export_selections()
        if not selections:
            self.statusBar().showMessage("未选择任何版本")
            return

        exported = 0
        for filename, result in self._results.items():
            if not result.success:
                continue

            product_name = Path(filename).stem
            opts_list = selections.get(product_name, [])
            if not opts_list:
                continue

            selected_ids = {o.version_id for o in opts_list}
            product_dir = self._output_dir / product_name
            product_dir.mkdir(parents=True, exist_ok=True)

            # Copy only files matching selected versions
            for f in result.output_files:
                src = Path(f["path"])
                vid = f.get("version_id")
                if vid not in selected_ids:
                    continue
                if src.exists():
                    dst = product_dir / src.name
                    shutil.copy2(str(src), str(dst))
                    exported += 1

            # Write copy text for selected versions only
            selected_versions = [
                v for v in result.versions if v.version_id in selected_ids
            ]
            if selected_versions:
                copy_text = generate_copy_text(selected_versions)
                (product_dir / "文案.txt").write_text(
                    copy_text, encoding="utf-8"
                )

        self.statusBar().showMessage(
            f"已导出 {exported} 个文件到 {self._output_dir}"
        )

    # ── Clear ──

    def _on_clear(self):
        """Clear all imported videos, results, and reset UI."""
        self._video_files.clear()
        self._results.clear()
        self.file_list.clear()
        self.result_panel.clear()
        self.generate_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_label.setText("就绪")
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("已清空，拖入新视频开始使用")
