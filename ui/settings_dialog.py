"""Settings dialog for CutPilot user configuration.

Modal dialog that reads/writes ~/.cutpilot/settings.json.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.user_settings import load_user_settings, save_user_settings

logger = logging.getLogger(__name__)

_QUALITY_OPTIONS = [
    ("快速预览 (draft)", "draft"),
    ("标准 (standard)", "standard"),
    ("高质量 (high)", "high"),
]

SETTINGS_DIALOG_QSS = """
QDialog {
    background-color: #1a1a2e;
}
QGroupBox {
    font-size: 14px;
    font-weight: bold;
    color: #e94560;
    border: 1px solid #0f3460;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit {
    background-color: #1a1a40;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: #533483;
}
QLineEdit:focus {
    border-color: #e94560;
}
QSpinBox, QDoubleSpinBox {
    background-color: #1a1a40;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 13px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #0f3460;
    border: none;
    width: 18px;
}
QComboBox {
    background-color: #1a1a40;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    selection-background-color: #533483;
    border: 1px solid #0f3460;
}
QCheckBox {
    color: #e0e0e0;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #0f3460;
    border-radius: 4px;
    background-color: #1a1a40;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QLabel {
    color: #c0c0d8;
    font-size: 13px;
}
QPushButton#dialogPrimary {
    background-color: #e94560;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#dialogPrimary:hover {
    background-color: #ff6b81;
}
QPushButton#dialogSecondary {
    background-color: transparent;
    color: #e94560;
    border: 1px solid #e94560;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 14px;
}
QPushButton#dialogSecondary:hover {
    background-color: #e9456020;
}
QPushButton#testButton {
    background-color: #533483;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#testButton:hover {
    background-color: #6a4c9c;
}
QPushButton#browseButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#browseButton:hover {
    background-color: #16213e;
}
"""


class _ApiTestWorker(QThread):
    """Background worker for API connection test."""

    finished = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def run(self) -> None:
        try:
            import openai

            client = openai.OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=10.0,
            )
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            if resp.choices:
                self.finished.emit(True, "连接成功")
            else:
                self.finished.emit(False, "API 返回为空")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc)[:200])


class SettingsDialog(QDialog):
    """Modal settings dialog for CutPilot configuration."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self.setStyleSheet(SETTINGS_DIALOG_QSS)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._api_test_worker: _ApiTestWorker | None = None

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(self._build_api_group())
        layout.addWidget(self._build_processing_group())
        layout.addWidget(self._build_asr_group())
        layout.addWidget(self._build_output_group())
        layout.addLayout(self._build_buttons())

    # ── Section builders ──

    def _build_api_group(self) -> QGroupBox:
        group = QGroupBox("API 设置")
        layout = QVBoxLayout(group)

        # API Key
        layout.addWidget(QLabel("API Key"))
        key_row = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("sk-...")

        self._toggle_vis_btn = QPushButton("显示")
        self._toggle_vis_btn.setObjectName("browseButton")
        self._toggle_vis_btn.setFixedWidth(50)
        self._toggle_vis_btn.clicked.connect(self._toggle_key_visibility)

        self._test_btn = QPushButton("测试连接")
        self._test_btn.setObjectName("testButton")
        self._test_btn.clicked.connect(self._test_connection)

        key_row.addWidget(self._api_key_edit, 1)
        key_row.addWidget(self._toggle_vis_btn)
        key_row.addWidget(self._test_btn)
        layout.addLayout(key_row)

        # Base URL
        layout.addWidget(QLabel("API Base URL"))
        self._base_url_edit = QLineEdit()
        layout.addWidget(self._base_url_edit)

        # Model
        layout.addWidget(QLabel("模型名称"))
        self._model_edit = QLineEdit()
        layout.addWidget(self._model_edit)

        return group

    def _build_processing_group(self) -> QGroupBox:
        group = QGroupBox("处理设置")
        layout = QVBoxLayout(group)

        # Max versions
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("版本数量"))
        self._max_versions_spin = QSpinBox()
        self._max_versions_spin.setRange(1, 5)
        row1.addWidget(self._max_versions_spin)
        row1.addStretch()
        layout.addLayout(row1)

        # Min sentences
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("最少句数"))
        self._min_sentences_spin = QSpinBox()
        self._min_sentences_spin.setRange(5, 50)
        row2.addWidget(self._min_sentences_spin)
        row2.addStretch()
        layout.addLayout(row2)

        # Video quality
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("视频质量"))
        self._quality_combo = QComboBox()
        for display_text, _value in _QUALITY_OPTIONS:
            self._quality_combo.addItem(display_text)
        row3.addWidget(self._quality_combo)
        row3.addStretch()
        layout.addLayout(row3)

        # Hook duration
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Hook 时长 (秒)"))
        self._hook_duration_spin = QDoubleSpinBox()
        self._hook_duration_spin.setRange(0.5, 10.0)
        self._hook_duration_spin.setSingleStep(0.5)
        self._hook_duration_spin.setDecimals(1)
        row4.addWidget(self._hook_duration_spin)
        row4.addStretch()
        layout.addLayout(row4)

        # Checkboxes
        self._fast_check = QCheckBox("生成加速版")
        layout.addWidget(self._fast_check)

        self._hook_overlay_check = QCheckBox("Hook 文字叠加")
        layout.addWidget(self._hook_overlay_check)

        self._diarization_check = QCheckBox("说话人分离")
        layout.addWidget(self._diarization_check)

        return group

    def _build_asr_group(self) -> QGroupBox:
        group = QGroupBox("ASR 设置")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("热词"))
        self._hotwords_edit = QLineEdit()
        self._hotwords_edit.setPlaceholderText("输入产品名/品牌名，空格分隔")
        layout.addWidget(self._hotwords_edit)

        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("输出设置")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("默认输出目录"))
        row = QHBoxLayout()
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("留空则每次手动选择")

        browse_btn = QPushButton("浏览...")
        browse_btn.setObjectName("browseButton")
        browse_btn.clicked.connect(self._browse_output_dir)

        row.addWidget(self._output_dir_edit, 1)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        return group

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("dialogSecondary")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("dialogPrimary")
        save_btn.clicked.connect(self._on_save)

        row.addWidget(cancel_btn)
        row.addWidget(save_btn)
        return row

    # ── Data loading / saving ──

    def _load_settings(self) -> None:
        settings = load_user_settings()
        self._api_key_edit.setText(settings.get("api_key", ""))
        self._base_url_edit.setText(settings.get("base_url", ""))
        self._model_edit.setText(settings.get("model", ""))
        self._max_versions_spin.setValue(settings.get("max_versions", 3))
        self._min_sentences_spin.setValue(settings.get("min_sentences", 15))
        self._fast_check.setChecked(settings.get("generate_fast", True))
        self._hook_overlay_check.setChecked(
            settings.get("enable_hook_overlay", True),
        )
        self._hook_duration_spin.setValue(settings.get("hook_duration", 3.0))
        self._diarization_check.setChecked(
            settings.get("enable_speaker_diarization", True),
        )
        self._hotwords_edit.setText(settings.get("hotwords", ""))
        self._output_dir_edit.setText(settings.get("output_dir", ""))

        # Set quality combo
        quality = settings.get("video_quality", "standard")
        for idx, (_label, value) in enumerate(_QUALITY_OPTIONS):
            if value == quality:
                self._quality_combo.setCurrentIndex(idx)
                break

    def _collect_settings(self) -> dict[str, Any]:
        quality_idx = self._quality_combo.currentIndex()
        quality_value = _QUALITY_OPTIONS[quality_idx][1]

        return {
            "api_key": self._api_key_edit.text().strip(),
            "base_url": self._base_url_edit.text().strip(),
            "model": self._model_edit.text().strip(),
            "max_versions": self._max_versions_spin.value(),
            "min_sentences": self._min_sentences_spin.value(),
            "generate_fast": self._fast_check.isChecked(),
            "enable_hook_overlay": self._hook_overlay_check.isChecked(),
            "hook_duration": self._hook_duration_spin.value(),
            "enable_speaker_diarization": self._diarization_check.isChecked(),
            "video_quality": quality_value,
            "output_dir": self._output_dir_edit.text().strip(),
            "hotwords": self._hotwords_edit.text().strip(),
        }

    def _on_save(self) -> None:
        settings = self._collect_settings()
        try:
            save_user_settings(settings)
            self.accept()
        except OSError as exc:
            QMessageBox.critical(
                self, "保存失败", f"无法写入设置文件:\n{exc}"
            )

    # ── Actions ──

    def _toggle_key_visibility(self) -> None:
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_vis_btn.setText("隐藏")
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_vis_btn.setText("显示")

    def _browse_output_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self._output_dir_edit.setText(dir_path)

    def _test_connection(self) -> None:
        api_key = self._api_key_edit.text().strip()
        base_url = self._base_url_edit.text().strip()
        model = self._model_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "提示", "请先输入 API Key")
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")

        self._api_test_worker = _ApiTestWorker(base_url, api_key, model)
        self._api_test_worker.finished.connect(self._on_test_finished)
        self._api_test_worker.start()

    def _on_test_finished(self, success: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_btn.setText("测试连接")
        self._api_test_worker = None

        if success:
            QMessageBox.information(self, "测试结果", message)
        else:
            QMessageBox.warning(self, "测试失败", message)
