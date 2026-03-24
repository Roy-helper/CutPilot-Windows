"""Results panel showing processed video versions with copy-able metadata."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QApplication,
)

from core.models import ScriptVersion


class VersionCard(QFrame):
    """Card displaying one script version with its metadata."""

    def __init__(self, version: ScriptVersion, parent=None):
        super().__init__(parent)
        self.version = version
        self.setStyleSheet("""
            VersionCard {
                background-color: #1a1a40;
                border-radius: 10px;
                border: 1px solid #0f3460;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header: version + approach tag
        header = QHBoxLayout()
        title = QLabel(f"版本 {version.version_id}")
        title.setObjectName("versionTitle")
        header.addWidget(title)

        if version.approach_tag:
            tag = QLabel(version.approach_tag)
            tag.setObjectName("approachTag")
            header.addWidget(tag)

        header.addStretch()

        copy_btn = QPushButton("复制文案")
        copy_btn.setObjectName("copyButton")
        copy_btn.clicked.connect(self._copy_all)
        header.addWidget(copy_btn)

        layout.addLayout(header)

        # Cover title
        if version.cover_title:
            cover = QLabel(f"封面: {version.cover_title}")
            cover.setStyleSheet("font-size: 14px; font-weight: bold; color: #ff6b81;")
            layout.addWidget(cover)

        if version.cover_subtitle:
            sub = QLabel(f"副标题: {version.cover_subtitle}")
            sub.setStyleSheet("font-size: 12px; color: #a0a0c0;")
            layout.addWidget(sub)

        # Publish text
        if version.publish_text:
            pub = QLabel(version.publish_text)
            pub.setObjectName("copyText")
            pub.setWordWrap(True)
            layout.addWidget(pub)

        # Tags
        if version.tags:
            tags_text = " ".join(version.tags)
            tags_label = QLabel(tags_text)
            tags_label.setStyleSheet("font-size: 11px; color: #533483;")
            tags_label.setWordWrap(True)
            layout.addWidget(tags_label)

    def _copy_all(self):
        """Copy all version metadata to clipboard."""
        v = self.version
        text = (
            f"发布文案: {v.publish_text}\n"
            f"封面主标题: {v.cover_title}\n"
            f"封面副标题: {v.cover_subtitle}\n"
            f"标签: {' '.join(v.tags)}"
        )
        clipboard = QApplication.clipboard()
        clipboard.setText(text)


class ResultPanel(QFrame):
    """Scrollable panel showing all version results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultPanel")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("成品预览")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        outer_layout.addWidget(title)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        scroll.setWidget(self._container)
        outer_layout.addWidget(scroll)

        # Placeholder
        self._placeholder = QLabel("处理完成后在此展示成品")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("font-size: 14px; color: #7a7a9e; padding: 60px;")
        self._layout.insertWidget(0, self._placeholder)

    def show_versions(self, product_name: str, versions: list[ScriptVersion]):
        """Display version cards for a processed product."""
        # Remove placeholder
        if self._placeholder:
            self._placeholder.hide()

        # Add product header
        header = QLabel(f"📦 {product_name}")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0; padding-top: 8px;")
        insert_pos = self._layout.count() - 1  # before stretch
        self._layout.insertWidget(insert_pos, header)

        # Add version cards
        for v in versions:
            card = VersionCard(v)
            insert_pos = self._layout.count() - 1
            self._layout.insertWidget(insert_pos, card)

    def clear(self):
        """Remove all version cards."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._placeholder.show()
