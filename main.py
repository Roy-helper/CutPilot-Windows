"""CutPilot — AI 副驾驶

电商短视频智能剪辑工具。拖入素材视频，AI 自动生成多个差异化版本。
"""
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CutPilot")
    app.setApplicationDisplayName("CutPilot — AI 副驾驶")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
