"""Activation dialog for CutPilot license entry.

Modal dialog shown on startup when no valid license exists.
Displays machine ID, accepts activation codes, and offers trial mode.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.license import (
    activate,
    get_license_info,
    get_machine_id,
    get_trial_remaining,
)

logger = logging.getLogger(__name__)

_DIALOG_QSS = """
QDialog {
    background-color: #1a1a2e;
}
QLabel {
    color: #c0c0d8;
    font-size: 13px;
}
QLabel#dialogTitle {
    font-size: 18px;
    font-weight: bold;
    color: #e94560;
}
QLabel#machineLabel {
    font-size: 12px;
    color: #c0c0d8;
    background-color: #1a1a40;
    border-radius: 6px;
    padding: 8px;
    font-family: "SF Mono", "Menlo", monospace;
}
QLabel#statusLabel {
    font-size: 13px;
    padding: 6px;
    border-radius: 4px;
}
QLineEdit {
    background-color: #1a1a40;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 14px;
    font-family: "SF Mono", "Menlo", monospace;
    selection-background-color: #533483;
}
QLineEdit:focus {
    border-color: #e94560;
}
QPushButton#activateButton {
    background-color: #e94560;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#activateButton:hover {
    background-color: #ff6b81;
}
QPushButton#activateButton:disabled {
    background-color: #3a3a5e;
    color: #7a7a9e;
}
QPushButton#trialButton {
    background-color: transparent;
    color: #e94560;
    border: 1px solid #e94560;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 14px;
}
QPushButton#trialButton:hover {
    background-color: #e9456020;
}
QPushButton#trialButton:disabled {
    border-color: #3a3a5e;
    color: #7a7a9e;
}
QPushButton#copyButton {
    background-color: #533483;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 12px;
}
QPushButton#copyButton:hover {
    background-color: #6a4c9c;
}
"""


class ActivationDialog(QDialog):
    """Modal activation dialog for license entry."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CutPilot - 激活")
        self.setMinimumWidth(480)
        self.setFixedWidth(520)
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._trial_allowed = False

        self._build_ui()
        self._update_trial_button()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("CutPilot 激活")
        title.setObjectName("dialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Machine ID section
        layout.addWidget(QLabel("本机标识 (发送给管理员获取激活码):"))

        mid_row = QHBoxLayout()
        machine_id = get_machine_id()
        self._machine_label = QLabel(machine_id)
        self._machine_label.setObjectName("machineLabel")
        self._machine_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        mid_row.addWidget(self._machine_label, 1)

        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("copyButton")
        copy_btn.clicked.connect(self._copy_machine_id)
        mid_row.addWidget(copy_btn)
        layout.addLayout(mid_row)

        # Activation code input
        layout.addWidget(QLabel("激活码:"))
        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText("CP-XXXXXXXX-XXXXXXXX-XXXXXXXXXXXX")
        self._code_edit.textChanged.connect(self._on_code_changed)
        layout.addWidget(self._code_edit)

        # Status message
        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()

        self._trial_btn = QPushButton("试用")
        self._trial_btn.setObjectName("trialButton")
        self._trial_btn.clicked.connect(self._on_trial)
        btn_row.addWidget(self._trial_btn)

        btn_row.addStretch()

        self._activate_btn = QPushButton("激活")
        self._activate_btn.setObjectName("activateButton")
        self._activate_btn.setEnabled(False)
        self._activate_btn.clicked.connect(self._on_activate)
        btn_row.addWidget(self._activate_btn)

        layout.addLayout(btn_row)

    def _update_trial_button(self) -> None:
        remaining = get_trial_remaining()
        if remaining > 0:
            self._trial_btn.setText(f"试用 (剩余 {remaining} 次)")
            self._trial_btn.setEnabled(True)
            self._trial_allowed = True
        else:
            self._trial_btn.setText("试用次数已用完")
            self._trial_btn.setEnabled(False)
            self._trial_allowed = False

    def _on_code_changed(self, text: str) -> None:
        self._activate_btn.setEnabled(len(text.strip()) > 10)

    def _copy_machine_id(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(get_machine_id())
        self._show_status("已复制到剪贴板", success=True)

    def _on_activate(self) -> None:
        code = self._code_edit.text().strip()
        if not code:
            return

        success, message = activate(code)
        if success:
            self._show_status(message, success=True)
            self.accept()
        else:
            self._show_status(message, success=False)

    def _on_trial(self) -> None:
        if not self._trial_allowed:
            return
        self._trial_allowed = True
        self.done(2)  # Custom result code for trial

    def _show_status(self, message: str, *, success: bool) -> None:
        color = "#4caf50" if success else "#e94560"
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setText(message)
        self._status_label.show()

    @staticmethod
    def result_is_trial(result: int) -> bool:
        """Check if dialog result indicates trial mode."""
        return result == 2
