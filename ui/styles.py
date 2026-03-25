"""CutPilot dark theme QSS stylesheet.

Professional dark UI inspired by CapCut/Premiere Pro.
"""

DARK_THEME = """
QMainWindow {
    background-color: #1a1a2e;
}

QWidget {
    color: #e0e0e0;
    font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

/* ── Panels ─────────────────────────────────────────── */
QFrame#sidebar, QFrame#resultPanel {
    background-color: #16213e;
    border-radius: 12px;
    border: 1px solid #0f3460;
}

QFrame#progressFrame {
    background-color: #16213e;
    border-radius: 8px;
    border: 1px solid #0f3460;
}

/* ── Drop Zone ──────────────────────────────────────── */
QFrame#dropZone {
    background-color: #0f3460;
    border: 2px dashed #533483;
    border-radius: 16px;
    min-height: 180px;
}

QFrame#dropZone:hover {
    border-color: #e94560;
    background-color: #1a1a40;
}

/* ── Labels ─────────────────────────────────────────── */
QLabel#titleLabel {
    font-size: 22px;
    font-weight: bold;
    color: #e94560;
}

QLabel#subtitleLabel {
    font-size: 12px;
    color: #7a7a9e;
}

QLabel#dropLabel {
    font-size: 16px;
    color: #a0a0c0;
}

QLabel#versionTitle {
    font-size: 15px;
    font-weight: bold;
    color: #e94560;
}

QLabel#approachTag {
    font-size: 11px;
    color: #1a1a2e;
    background-color: #e94560;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: bold;
}

QLabel#copyText {
    font-size: 12px;
    color: #c0c0d8;
    background-color: #1a1a40;
    border-radius: 6px;
    padding: 8px;
}

/* ── Buttons ────────────────────────────────────────── */
QPushButton#primaryButton {
    background-color: #e94560;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px 32px;
    font-size: 15px;
    font-weight: bold;
    min-width: 140px;
}

QPushButton#primaryButton:hover {
    background-color: #ff6b81;
}

QPushButton#primaryButton:pressed {
    background-color: #c73e54;
}

QPushButton#primaryButton:disabled {
    background-color: #3a3a5e;
    color: #7a7a9e;
}

QPushButton#secondaryButton {
    background-color: transparent;
    color: #e94560;
    border: 1px solid #e94560;
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
}

QPushButton#secondaryButton:hover {
    background-color: #e9456020;
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

/* ── Settings Button ────────────────────────────────── */
QPushButton#settingsButton {
    background-color: transparent;
    color: #7a7a9e;
    border: 1px solid #0f3460;
    border-radius: 18px;
    font-size: 18px;
    padding: 0px;
}

QPushButton#settingsButton:hover {
    color: #e94560;
    border-color: #e94560;
    background-color: #e9456020;
}

/* ── Progress Bar ───────────────────────────────────── */
QProgressBar {
    background-color: #0f3460;
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: white;
    font-size: 10px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560, stop:1 #ff6b81);
    border-radius: 6px;
}

/* ── List Widget ────────────────────────────────────── */
QListWidget {
    background-color: #1a1a40;
    border: none;
    border-radius: 8px;
    padding: 4px;
}

QListWidget::item {
    color: #c0c0d8;
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #533483;
    color: white;
}

QListWidget::item:hover {
    background-color: #0f3460;
}

/* ── Scroll Bar ─────────────────────────────────────── */
QScrollBar:vertical {
    background: #1a1a2e;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #533483;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* ── Checkbox ──────────────────────────────────────── */
QCheckBox {
    color: #e0e0e0;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #533483;
    border-radius: 3px;
    background: #1a1a40;
}

QCheckBox::indicator:checked {
    background: #e94560;
    border-color: #e94560;
}

QCheckBox::indicator:hover {
    border-color: #e94560;
}

/* ── Settings Button ───────────────────────────────── */
QPushButton#settingsButton {
    background-color: transparent;
    color: #7a7a9e;
    border: 1px solid #0f3460;
    border-radius: 18px;
    font-size: 18px;
}

QPushButton#settingsButton:hover {
    color: #e94560;
    border-color: #e94560;
}

/* ── Status Bar ─────────────────────────────────────── */
QStatusBar {
    background-color: #0f3460;
    color: #7a7a9e;
    font-size: 11px;
}
"""
