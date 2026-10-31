"""Dark mode theme."""
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

BG = "#1e1f22"
SURFACE = "#2b2d30"
BASE = "#232428"
BORDER = "#3c3f44"
BORDER_BRIGHT = "#5c6370"
TEXT = "#dfe1e5"
TEXT_DIM = "#8b919a"
ACCENT = "#4c8dff"

STYLESHEET = """
QWidget { color: #dfe1e5; font-size: 10pt; }
QToolTip { background: #2b2d30; color: #dfe1e5; border: 1px solid #3c3f44; padding: 4px; }

QTabWidget::pane { border: 1px solid #3c3f44; border-radius: 6px; top: -1px; }
QTabBar::tab {
    background: #2b2d30; color: #8b919a; padding: 8px 22px;
    border: 1px solid #3c3f44; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px;
}
QTabBar::tab:selected { background: #35373c; color: #ffffff; }
QTabBar::tab:hover { color: #ffffff; }

QGroupBox {
    border: 1px solid #3c3f44; border-radius: 8px;
    margin-top: 14px; padding: 10px; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 12px; padding: 0 4px; color: #8b919a;
}

QPushButton {
    background: #2b2d30; border: 1px solid #3c3f44; border-radius: 6px; padding: 7px 14px;
}
QPushButton:hover { background: #35373c; border-color: #4c8dff; }
QPushButton:pressed { background: #232428; }
QPushButton:disabled { color: #6b6f76; border-color: #2b2d30; }
QPushButton#smallButton { padding: 4px 8px; }

QPushButton#recordButton {
    background: #2e7d32; border: none; color: white;
    font-size: 15pt; font-weight: 700; padding: 14px; border-radius: 10px;
}
QPushButton#recordButton:hover { background: #388e3c; }
QPushButton#recordButton[recording="true"] { background: #c62828; }
QPushButton#recordButton[recording="true"]:hover { background: #d32f2f; }

QPushButton#dangerButton { color: #ff6b6b; }
QPushButton#dangerButton:hover { border-color: #ff6b6b; }

QLabel#statusLabel { font-size: 18pt; font-weight: 700; color: #8b919a; }
QLabel#statusLabel[recording="true"] { color: #ff5252; }
QLabel#dimLabel { color: #8b919a; }
QLabel#valueLabel { font-weight: 600; }

QListWidget {
    background: #232428; border: 1px solid #3c3f44; border-radius: 6px;
    font-family: Consolas, "Courier New", monospace;
}
QScrollArea { border: none; background: transparent; }
QStatusBar { color: #8b919a; }
QMenuBar { background: #1e1f22; border-bottom: 1px solid #3c3f44; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background: #35373c; border-radius: 4px; }
QMenu { background: #2b2d30; border: 1px solid #3c3f44; }
QMenu::item:selected { background: #4c8dff; color: white; }
QMenu::separator { height: 1px; background: #3c3f44; margin: 4px 8px; }
QLabel#hintLabel { color: #8b919a; }
QKeySequenceEdit, QSpinBox { padding: 3px; }
"""


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    pal = QPalette()
    pal.setColor(role.Window, QColor(BG))
    pal.setColor(role.WindowText, QColor(TEXT))
    pal.setColor(role.Base, QColor(BASE))
    pal.setColor(role.AlternateBase, QColor(SURFACE))
    pal.setColor(role.ToolTipBase, QColor(SURFACE))
    pal.setColor(role.ToolTipText, QColor(TEXT))
    pal.setColor(role.PlaceholderText, QColor(TEXT_DIM))
    pal.setColor(role.Text, QColor(TEXT))
    pal.setColor(role.Button, QColor(SURFACE))
    pal.setColor(role.ButtonText, QColor(TEXT))
    pal.setColor(role.BrightText, QColor("#ff5555"))
    pal.setColor(role.Link, QColor(ACCENT))
    pal.setColor(role.Highlight, QColor(ACCENT))
    pal.setColor(role.HighlightedText, QColor("#ffffff"))
    for r in (role.Text, role.ButtonText, role.WindowText):
        pal.setColor(group.Disabled, r, QColor("#6b6f76"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)