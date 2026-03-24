"""Drag-and-drop zone widget for importing video files."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QFileDialog


class _TransparentLabel(QLabel):
    """Label that passes drag events through to its parent."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


class DropZone(QFrame):
    """Drop zone that accepts video file drag-and-drop.

    Also supports click-to-browse as a fallback for platforms
    where drag-and-drop may not work reliably.
    """

    files_dropped = Signal(list)  # list[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = _TransparentLabel("🎬")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        text_label = _TransparentLabel("拖入视频到这里")
        text_label.setObjectName("dropLabel")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

        hint_label = _TransparentLabel("支持 MP4 / MOV / AVI / MKV  |  点击选择文件")
        hint_label.setStyleSheet("font-size: 11px; color: #7a7a9e;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint_label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if file_paths:
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event):
        """Click to open file browser as fallback."""
        if event.button() == Qt.MouseButton.LeftButton:
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "选择视频文件",
                "",
                "视频文件 (*.mp4 *.mov *.avi *.mkv *.flv);;所有文件 (*)",
            )
            if files:
                self.files_dropped.emit(files)
