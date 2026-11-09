# -*- coding: utf-8 -*-
"""Themes, palettes and the QSS built from them.

Python 3.8 / PyQt5.
"""
import os

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF


THEMES = ("classic", "sidebar", "spreadsheet", "midnight")
THEME_LABELS = {
    "classic": "Classic (native)",
    "sidebar": "Sidebar (Design 1)",
    "spreadsheet": "Spreadsheet (Design 9)",
    "midnight": "Midnight (dark stream desk)",
}

# Which layout a theme uses (themes may share a layout with another palette).
_LAYOUTS = {
    "classic": "classic",
    "sidebar": "sidebar",
    "spreadsheet": "spreadsheet",
    "midnight": "sidebar",
}

# Themes that show the persistent Now-Playing bar under every tab.
NOW_PLAYING_THEMES = ("midnight",)

FONT_FAMILY = "Segoe UI"

PERMISSIONS = ["Everyone", "Moderator", "Admin"]
USAGES = ["SC", "Chat", "Both"]


def layout_of(theme):
    return _LAYOUTS.get(theme, "classic")


def palette_for(theme):
    return PALETTES.get(theme) or PALETTES["sidebar"]


def is_dark(pal):
    return bool(pal.get("dark"))


# ---------------------------------------------------------------------------
# Palettes (hex)
# ---------------------------------------------------------------------------

PALETTES = {
    "sidebar": {
        "bg": "#F7F7F8", "surface": "#FFFFFF", "surface2": "#FAFAFB",
        "surface3": "#F0F0F2", "border": "#E7E7EA", "border_strong": "#D6D6DB",
        "text": "#1A1A1E", "text2": "#62626B", "text3": "#9C9CA5",
        "accent": "#5B5BD6", "accent_press": "#4A4AC4", "accent2": "#8B5CF6",
        "accent_soft": "rgba(91,91,214,0.10)",
        "green": "#16A34A", "red": "#DC2626", "amber": "#D97706",
    },
    "spreadsheet": {
        "bg": "#F1F3F6", "surface": "#FFFFFF", "surface2": "#F7F9FC",
        "surface3": "#EDF0F5", "border": "#DDE2EA", "border_strong": "#CBD2DE",
        "text": "#1A1D24", "text2": "#5A6170", "text3": "#98A0AE",
        "accent": "#0891B2", "accent_press": "#0E7490", "accent2": "#06B6D4",
        "accent_soft": "rgba(8,145,178,0.10)",
        "green": "#16A34A", "red": "#DC2626", "amber": "#D97706",
    },
    # Dark palette tuned for long sessions next to OBS: low-glare surfaces,
    # text contrast >= 4.5:1, accent readable as text on every surface.
    "midnight": {
        "dark": True,
        "bg": "#0F1117", "surface": "#161922", "surface2": "#1B1F2A",
        "surface3": "#252A37", "border": "#2A2F3C", "border_strong": "#3A4152",
        "text": "#E6E8EE", "text2": "#A9AFBD", "text3": "#7A8193",
        "accent": "#8B5CF6", "accent_press": "#B49BFA", "accent2": "#EC4899",
        "accent_soft": "rgba(139,92,246,0.20)",
        "green": "#22C55E", "red": "#F87171", "amber": "#FBBF24",
    },
}


# ---------------------------------------------------------------------------
# QSS
# ---------------------------------------------------------------------------

def _base_qss(c):
    """Shared QSS for the themed looks (palette + common widgets)."""
    return """
* { font-family: "%(font)s", "MS Shell Dlg 2", Tahoma, sans-serif; }
QWidget { color: %(text)s; background: %(bg)s; font-size: 13px; }
QLabel { background: transparent; }
QMainWindow, QDialog { background: %(bg)s; }
QToolTip { color: %(text)s; background: %(surface)s; border: 1px solid %(border)s; padding: 4px 6px; }

QTabWidget::pane { border: 1px solid %(border)s; background: %(surface)s; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: %(text2)s; padding: 7px 9px;
    border: none; border-bottom: 2px solid transparent; font-weight: 500; font-size: 12px;
}
QTabBar::tab:hover { color: %(text)s; }
QTabBar::tab:selected { color: %(accent_press)s; border-bottom: 2px solid %(accent)s; font-weight: 600; background: %(surface)s; }

QPushButton {
    background: %(surface)s; border: 1px solid %(border_strong)s;
    border-radius: 7px; padding: 7px 13px; color: %(text)s; font-weight: 500;
}
QPushButton:hover { background: %(surface2)s; border-color: %(text3)s; }
QPushButton:pressed { background: %(surface3)s; }
QPushButton:disabled { color: %(text3)s; border-color: %(border)s; }
QPushButton:focus { border: 1px solid %(accent)s; }
QPushButton#primaryBtn { background: %(accent)s; border: 1px solid %(accent)s; color: #ffffff; }
QPushButton#primaryBtn:hover { background: %(accent_press)s; border-color: %(accent_press)s; }
QPushButton#primaryBtn:disabled { background: %(surface3)s; border-color: %(border)s; color: %(text3)s; }
QPushButton#dangerBtn { color: %(red)s; }
QPushButton::menu-indicator { width: 0; }

QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background: %(surface2)s; border: 1px solid %(border)s;
    border-radius: 7px; padding: 6px 9px; color: %(text)s;
    selection-background-color: %(accent)s; selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid %(accent)s; background: %(surface)s;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: %(text3)s; background: %(surface3)s; }
QLineEdit#searchBox { background: %(surface3)s; border: 1px solid transparent; border-radius: 7px; padding: 7px 11px; }
QLineEdit#searchBox:focus { background: %(surface)s; border: 1px solid %(accent)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
    selection-background-color: %(accent)s; selection-color: #ffffff; outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; background: transparent; }

QSlider::groove:horizontal { height: 4px; background: %(surface3)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; background: %(accent)s; }

QGroupBox {
    border: 1px solid %(border)s; border-radius: 10px;
    margin-top: 12px; padding: 14px 12px 12px 12px;
    font-weight: 600; color: %(text2)s;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: %(text2)s; }

QTableWidget, QTableView {
    background: %(surface)s; alternate-background-color: %(surface2)s; color: %(text)s;
    gridline-color: %(border)s; border: 1px solid %(border)s; border-radius: 8px;
}
QHeaderView { background: %(surface2)s; }
QHeaderView::section {
    background: %(surface2)s; color: %(text3)s; border: none;
    border-bottom: 1px solid %(border)s; padding: 8px 10px;
    font-weight: 600; font-size: 11px;
}
QTableCornerButton::section { background: %(surface2)s; border: none; }
QTableWidget::item:selected, QTableView::item:selected {
    background: %(accent_soft)s; color: %(accent_press)s;
}
QListWidget, QListView, QTreeView {
    background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 8px; outline: 0;
}
QListWidget::item { padding: 6px 8px; }
QListWidget::item:hover { background: %(surface2)s; }
QListWidget::item:selected { background: %(accent_soft)s; color: %(accent_press)s; }
QListWidget#masterList::item { padding: 0; margin: 0; }
QListWidget#masterList::item:selected { background: transparent; }

QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 5px; }
QMenu::item:selected { background: %(accent_soft)s; color: %(accent_press)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 4px 6px; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 6px; min-height: 24px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: %(text3)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 6px; min-width: 24px; margin: 2px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QCheckBox { spacing: 8px; color: %(text)s; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid %(border_strong)s; background: %(surface)s; }
QCheckBox::indicator:checked { background: %(accent)s; border: 1px solid %(accent)s; }
QCheckBox::indicator:disabled { background: %(surface3)s; border-color: %(border)s; }
QProgressBar { background: %(surface3)s; border: none; border-radius: 4px; text-align: center; color: %(text)s; }
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }

QLabel#brandName { font-size: 13px; font-weight: 600; }
QLabel#navSection { color: %(text3)s; font-size: 10px; font-weight: 600; }
QLabel#crumb { color: %(text3)s; font-size: 12px; }
QLabel#fieldLabel { color: %(text2)s; font-size: 11px; font-weight: 600; }
QLabel#dTitle { font-size: 18px; font-weight: 600; }
QLabel#dSub { color: %(text3)s; font-size: 12px; }
QLabel#statusLabel { color: %(text3)s; font-size: 11px; }
QLabel#countLabel { color: %(text3)s; font-size: 11px; }
QLabel#topTitle { font-size: 15px; font-weight: 600; }
QLabel#mheadTitle { font-size: 13px; font-weight: 600; }
QLabel#mheadHint { color: %(text3)s; font-size: 11px; }
QLabel#sideStatus { color: %(text2)s; font-size: 12px; }
QLabel#switchTitle { font-size: 13px; font-weight: 500; }
QLabel#switchDesc { color: %(text3)s; font-size: 11px; }
QLabel#sectionTitle { font-size: 13px; font-weight: 600; color: %(text)s; }
QFrame#nowPlayingCard { background: %(surface2)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#settingsCard { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#nowBar { background: %(surface2)s; border-top: 1px solid %(border)s; }
QFrame#nowBar QLabel#nowGroup { color: %(text3)s; font-size: 10px; font-weight: 700; }
QFrame#nowBar QLabel#nowText { color: %(text)s; font-size: 12.5px; font-weight: 600; }
QFrame#nowBar QLabel#nowMeta { color: %(text3)s; font-size: 11px; }
QFrame#nowBar QPushButton { padding: 4px 9px; }
""" % dict(c, font=FONT_FAMILY)


def _layout_qss(c):
    """Rules for the sidebar / topbar / panels shared by every themed layout."""
    return """
QFrame#sidebarPanel { background: %(surface2)s; border-right: 1px solid %(border)s; }
QPushButton#navBtn {
    text-align: left; background: transparent; border: none; border-radius: 7px;
    padding: 8px 10px; color: %(text2)s; font-weight: 500;
}
QPushButton#navBtn:hover { background: %(surface3)s; color: %(text)s; }
QPushButton#navBtnActive {
    text-align: left; border: none; border-radius: 7px; padding: 8px 10px;
    background: %(accent_soft)s; color: %(accent_press)s; font-weight: 600;
}
QFrame#topbar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
QFrame#toolbar { background: %(surface2)s; border-bottom: 1px solid %(border)s; }
QToolBar#toolbar { background: %(surface2)s; border: none; border-bottom: 1px solid %(border)s; spacing: 4px; padding: 0 12px; }
QToolBar#toolbar QToolButton#qt_toolbar_ext_button { background: transparent; border: none; padding: 2px; }
QScrollArea#themedScroll { border: none; background: transparent; }
QPushButton#toolBtn {
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 6px 10px; color: %(text2)s; font-weight: 500;
}
QPushButton#toolBtn:hover { background: %(surface3)s; color: %(text)s; }
QPushButton#toolBtn:disabled { color: %(text3)s; }
QPushButton#toolBtn:checked { background: %(accent_soft)s; color: %(accent_press)s; }
QFrame#statusbar { background: %(surface2)s; border-top: 1px solid %(border)s; }
QFrame#masterPanel { background: %(surface)s; border-right: 1px solid %(border)s; }
QListWidget#masterList { border: none; background: %(surface)s; }
QFrame#detailPanel { background: %(surface)s; }
QScrollArea#detailScroll { border: none; background: %(surface)s; }
QFrame#switchRow { border-bottom: 1px solid %(border)s; }
QFrame#dIco { background: %(accent_soft)s; border-radius: 10px; }
QLabel#dIcoText { color: %(accent_press)s; font-size: 15px; font-weight: 700; }
QFrame#panel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#statStrip { background: %(surface2)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#statBox { border-right: 1px solid %(border)s; }
QFrame#statBoxLast { border-right: none; }
QFrame#statBox QLabel, QFrame#statBoxLast QLabel { color: %(text3)s; font-size: 11px; }
QFrame#statBox QLabel#statVal, QFrame#statBoxLast QLabel#statVal { color: %(text)s; font-size: 16px; font-weight: 600; }
QFrame#authPill { border-radius: 12px; }
QFrame#authPill QLabel { font-size: 12px; font-weight: 500; }
QFrame#statusbar QLabel#statusLabel { color: %(text2)s; font-size: 11.5px; }
QSplitter::handle { background: %(border)s; }
QTableWidget#denseTable { gridline-color: %(border)s; border-radius: 0; border: none; }
QTableWidget#denseTable::item { padding: 0 4px; }
QTabWidget#viewersTabs::pane { border: none; background: transparent; }
QTabWidget#viewersTabs QTabBar { background: transparent; }
""" % c


def _arrow_qss(c):
    """Drop-down / spin arrows. A styled QComboBox/QSpinBox loses its native
    arrows and QSS can only draw them from image files, so small PNGs are
    rendered once per colour into the temp dir. Without them the combos
    looked like plain text fields."""
    try:
        import tempfile
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is None:
            return ""
        folder = os.path.join(tempfile.gettempdir(), "command_editor_theme")
        if not os.path.isdir(folder):
            os.makedirs(folder)
        paths = {}
        color = c["text2"]
        for kind in ("down", "up"):
            path = os.path.join(folder, "arrow_%s_%s.png" % (kind, color.lstrip("#")))
            if not os.path.exists(path):
                pm = QPixmap(20, 20)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor(color))
                pen.setWidthF(2.2)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                if kind == "down":
                    p.drawPolyline(QPolygonF([QPointF(5, 8), QPointF(10, 13), QPointF(15, 8)]))
                else:
                    p.drawPolyline(QPolygonF([QPointF(5, 12), QPointF(10, 7), QPointF(15, 12)]))
                p.end()
                pm.save(path, "PNG")
            paths[kind] = path.replace("\\", "/")
    except Exception as e:  # never break theming over an icon
        print("theme arrows unavailable: %s" % e)
        return ""
    return """
QComboBox { padding-right: 24px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }
QComboBox::down-arrow { image: url("%(down)s"); width: 11px; height: 11px; }
QSpinBox { padding-right: 20px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px; border: none; background: transparent; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; border: none; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: %(hover)s; border-radius: 4px; }
QSpinBox::up-arrow { image: url("%(up)s"); width: 9px; height: 9px; }
QSpinBox::down-arrow { image: url("%(down)s"); width: 9px; height: 9px; }
""" % dict(paths, hover=c["surface3"])


def qss_for(theme, palette=None):
    if theme == "classic":
        # classic: minimal, preserve native look
        return """
QScrollBar:vertical { width: 16px; background: rgba(0,0,0,0.1); }
QScrollBar:horizontal { height: 16px; background: rgba(0,0,0,0.1); }
"""
    pal = palette or palette_for(theme)
    return _base_qss(pal) + _layout_qss(pal) + _arrow_qss(pal)
