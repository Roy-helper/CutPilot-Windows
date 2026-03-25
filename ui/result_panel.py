"""Results panel showing processed video versions with selection and export options."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.models import ExportOptions, ScriptVersion


class VersionCard(QFrame):
    """Card displaying one script version with selection and export toggles."""

    selection_changed = Signal()

    def __init__(
        self,
        version: ScriptVersion,
        product_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.version = version
        self.product_name = product_name
        self._setup_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        layout.addLayout(self._build_header())
        self._add_cover_labels(layout)
        self._add_publish_text(layout)
        self._add_tags(layout)
        layout.addLayout(self._build_toggle_row())

    # ── UI construction helpers ──

    def _setup_style(self) -> None:
        self.setStyleSheet("""
            VersionCard {
                background-color: #1a1a40;
                border-radius: 10px;
                border: 1px solid #0f3460;
            }
        """)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()

        self._select_cb = QCheckBox()
        self._select_cb.setChecked(True)
        self._select_cb.stateChanged.connect(self._on_selection_toggled)
        header.addWidget(self._select_cb)

        dur = f"{self.version.estimated_duration:.0f}s"
        score = f"{self.version.score:.0f}分"
        title_text = f"版本 {self.version.version_id}  {dur}  {score}"
        title = QLabel(title_text)
        title.setObjectName("versionTitle")
        header.addWidget(title)

        if self.version.approach_tag:
            tag = QLabel(self.version.approach_tag)
            tag.setObjectName("approachTag")
            header.addWidget(tag)

        header.addStretch()

        copy_btn = QPushButton("复制文案")
        copy_btn.setObjectName("copyButton")
        copy_btn.clicked.connect(self._copy_all)
        header.addWidget(copy_btn)

        return header

    def _add_cover_labels(self, layout: QVBoxLayout) -> None:
        if self.version.cover_title:
            cover = QLabel(f"封面: {self.version.cover_title}")
            cover.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #ff6b81;"
            )
            layout.addWidget(cover)

        if self.version.cover_subtitle:
            sub = QLabel(f"副标题: {self.version.cover_subtitle}")
            sub.setStyleSheet("font-size: 12px; color: #a0a0c0;")
            layout.addWidget(sub)

    def _add_publish_text(self, layout: QVBoxLayout) -> None:
        if self.version.publish_text:
            pub = QLabel(self.version.publish_text)
            pub.setObjectName("copyText")
            pub.setWordWrap(True)
            layout.addWidget(pub)

    def _add_tags(self, layout: QVBoxLayout) -> None:
        if self.version.tags:
            tags_text = " ".join(self.version.tags)
            tags_label = QLabel(tags_text)
            tags_label.setStyleSheet("font-size: 11px; color: #533483;")
            tags_label.setWordWrap(True)
            layout.addWidget(tags_label)

    def _build_toggle_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        self._normal_cb = QCheckBox("原速")
        self._normal_cb.setChecked(True)
        self._normal_cb.stateChanged.connect(self._on_selection_toggled)
        row.addWidget(self._normal_cb)

        self._fast_cb = QCheckBox("加速")
        self._fast_cb.setChecked(False)
        self._fast_cb.stateChanged.connect(self._on_selection_toggled)
        row.addWidget(self._fast_cb)

        self._hook_cb = QCheckBox("Hook")
        self._hook_cb.setChecked(False)
        self._hook_cb.stateChanged.connect(self._on_selection_toggled)
        row.addWidget(self._hook_cb)

        row.addStretch()
        return row

    # ── Public API ──

    @property
    def is_selected(self) -> bool:
        return self._select_cb.isChecked()

    def set_selected(self, checked: bool) -> None:
        self._select_cb.setChecked(checked)

    def get_export_options(self) -> ExportOptions:
        """Return an immutable ExportOptions for this card's current state."""
        return ExportOptions(
            version_id=self.version.version_id,
            export_normal=self._normal_cb.isChecked(),
            export_fast=self._fast_cb.isChecked(),
            enable_hook=self._hook_cb.isChecked(),
        )

    # ── Slots ──

    def _on_selection_toggled(self) -> None:
        self.selection_changed.emit()

    def _copy_all(self) -> None:
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
    """Scrollable panel showing all version results with batch selection."""

    selection_changed = Signal(int, int)  # (selected_count, total_count)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultPanel")
        self._cards: list[VersionCard] = []

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(16, 16, 16, 16)

        # Header row: title + select-all toggle
        header_row = QHBoxLayout()
        title = QLabel("成品预览")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e0e0e0;"
        )
        header_row.addWidget(title)

        self._select_all_cb = QCheckBox("全选")
        self._select_all_cb.setChecked(True)
        self._select_all_cb.stateChanged.connect(self._on_select_all_toggled)
        header_row.addStretch()
        header_row.addWidget(self._select_all_cb)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("font-size: 12px; color: #7a7a9e;")
        header_row.addWidget(self._count_label)

        outer_layout.addLayout(header_row)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        scroll.setWidget(self._container)
        outer_layout.addWidget(scroll)

        # Placeholder
        self._placeholder = QLabel("处理完成后在此展示成品")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            "font-size: 14px; color: #7a7a9e; padding: 60px;"
        )
        self._layout.insertWidget(0, self._placeholder)

    # ── Public API ──

    def show_versions(
        self, product_name: str, versions: list[ScriptVersion]
    ) -> None:
        """Display version cards for a processed product."""
        self._hide_placeholder()

        # Product header
        header = QLabel(f"📦 {product_name}")
        header.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #e0e0e0; padding-top: 8px;"
        )
        insert_pos = self._layout.count() - 1  # before stretch
        self._layout.insertWidget(insert_pos, header)

        # Version cards
        for v in versions:
            card = VersionCard(v, product_name)
            card.selection_changed.connect(self._update_selection_count)
            insert_pos = self._layout.count() - 1
            self._layout.insertWidget(insert_pos, card)
            self._cards.append(card)

        self._update_selection_count()

    def get_export_selections(self) -> dict[str, list[ExportOptions]]:
        """Return {product_name: [ExportOptions,...]} for checked cards."""
        result: dict[str, list[ExportOptions]] = {}
        for card in self._cards:
            if card.is_selected:
                opts = card.get_export_options()
                result.setdefault(card.product_name, []).append(opts)
        return result

    def get_selected_count(self) -> int:
        return sum(1 for c in self._cards if c.is_selected)

    def get_total_count(self) -> int:
        return len(self._cards)

    def clear(self) -> None:
        """Remove all version cards and section headers."""
        self._cards.clear()
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._placeholder:
                widget.deleteLater()
        self._show_placeholder()
        self._update_selection_count()

    # ── Private helpers ──

    def _hide_placeholder(self) -> None:
        if self._placeholder is not None:
            try:
                self._placeholder.hide()
            except RuntimeError:
                self._placeholder = None

    def _show_placeholder(self) -> None:
        if self._placeholder is not None:
            try:
                self._placeholder.show()
            except RuntimeError:
                self._placeholder = None

    def _on_select_all_toggled(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        for card in self._cards:
            card.set_selected(checked)
        self._update_selection_count()

    def _update_selection_count(self) -> None:
        selected = self.get_selected_count()
        total = self.get_total_count()
        if total > 0:
            self._count_label.setText(f"已选择 {selected}/{total} 个版本")
        else:
            self._count_label.setText("")
        self.selection_changed.emit(selected, total)
