# -*- coding: utf-8 -*-
"""Theme system for Command Editor.

Themes:
  * classic     - native Qt look (no QSS, the original appearance)
  * sidebar     - Design 1: Linear/Notion sidebar + master-detail Commands
  * spreadsheet - Design 9: dense inline-edit table + toolbar + status bar
  * midnight    - dark "stream desk": sidebar layout on a dark palette plus a
                  persistent Now-Playing bar (queues controllable from any tab)

The theme is stored in config.json under the "theme" key. Switching themes
re-styles the whole app via QSS and swaps the Commands/Twitch tabs for themed
views. Other tabs keep their widgets and are only re-styled.

Data rule: themed views never write the hidden classic table themselves —
every edit goes through CommandEditor.apply_command_edit(), which updates the
command dict, the classic table, commands.json and the running bot together.

Python 3.8 / PyQt5 (Qt5) only. No walrus, no PEP 585/604 generics.
"""
import os
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QAbstractButton,
    QStyledItemDelegate, QTextEdit, QStyle, QComboBox, QSpinBox, QSlider,
    QMenu, QInputDialog, QScrollArea, QCheckBox, QGroupBox, QSplitter,
    QToolBar, QSizePolicy,
)
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPixmap, QIcon,
    QLinearGradient, QPainterPath, QPolygonF,
)


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


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------

def _mono_font(point=10):
    f = QFont("Consolas")
    f.setPointSize(point)
    return f


def _ui_font(size=13, bold=False):
    f = QFont(FONT_FAMILY)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def group_pill_kind(group):
    g = (group or "").upper()
    if g == "GENERAL":
        return "accent"
    if g in ("VIP", "COPY"):
        return "amber"
    if g in ("MUSIC", "SONG", "SONGS"):
        return "teal"
    if g in ("MODS", "MODERATOR", "MOD"):
        return "red"
    return "neutral"


def pill_colors(kind, pal):
    if kind == "accent":
        return pal["accent_soft"], pal["accent_press"]
    if kind == "amber":
        return "rgba(217,119,6,0.16)", pal["amber"]
    if kind == "teal":
        return "rgba(8,145,178,0.16)", ("#38BDF8" if is_dark(pal) else "#0E7490")
    if kind == "red":
        return "rgba(220,38,38,0.14)", pal["red"]
    return pal["surface3"], pal["text2"]


def make_pill_label(text, kind, pal):
    bg, fg = pill_colors(kind, pal)
    lab = QLabel(text)
    lab.setStyleSheet(
        "background: %s; color: %s; border-radius: 8px; padding: 1px 8px;"
        "font-size: 10px; font-weight: 600;" % (bg, fg))
    return lab


def rgba_color(s):
    """Parse 'rgba(r,g,b,a)' (a in 0..1) into a QColor. QSS accepts 0..1 alpha,
    but the QColor() string constructor expects 0..255 — so convert by hand."""
    try:
        inner = s[s.index("(") + 1:s.rindex(")")]
        parts = [p.strip() for p in inner.split(",")]
        r = int(float(parts[0]))
        g = int(float(parts[1]))
        b = int(float(parts[2]))
        a = int(round(float(parts[3]) * 255)) if len(parts) > 3 else 255
        return QColor(r, g, b, a)
    except (ValueError, IndexError):
        return QColor(s)


def cmd_volume(cmd):
    """Command volume as an int percentage. Commands store 0..100; a few
    files written by the old themed views hold 0..1 floats — read both."""
    try:
        v = float(cmd.get("Volume", 100))
    except (TypeError, ValueError):
        return 100
    if 0 < v <= 1 and not float(v).is_integer():
        v *= 100
    return int(max(0, min(100, round(v))))


def connection_state(editor):
    """(text, colour_key) describing the bot connection for status labels."""
    tt = getattr(editor, "twitch_tab", None)
    bot = getattr(tt, "bot", None) if tt is not None else None
    if bot is None or not getattr(bot, "is_running", False):
        return "offline", "text3"
    channel = getattr(bot, "channel", "") or ""
    live = bool(getattr(tt, "currently_live", False) or getattr(bot, "is_live", False))
    return ("%s · %s" % (channel, "live" if live else "connected")), ("green" if live else "accent")


class LogoBadge(QWidget):
    """Rounded square with a gradient fill and a letter (brand mark)."""

    def __init__(self, pal, letter="C", size=28):
        super(LogoBadge, self).__init__()
        self.pal = pal
        self.letter = letter
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0.0, QColor(self.pal["accent"]))
        grad.setColorAt(1.0, QColor(self.pal.get("accent2", self.pal["accent"])))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.28, s * 0.28)
        p.setPen(QColor("#ffffff"))
        f = QFont(FONT_FAMILY)
        f.setBold(True)
        f.setPointSizeF(s * 0.46)
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, self.letter)
        p.end()


class ToggleSwitch(QAbstractButton):
    """iOS-style on/off switch drawn with QPainter."""

    def __init__(self, pal, width=36, height=20, parent=None):
        super(ToggleSwitch, self).__init__(parent)
        self.pal = pal
        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        off_col = self.pal["border_strong"] if is_dark(self.pal) else self.pal["surface3"]
        p.setBrush(QColor(self.pal["green"] if on else off_col))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2.0, h / 2.0)
        if self.hasFocus():
            p.setPen(QPen(QColor(self.pal["accent"]), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.75, 0.75, w - 1.5, h - 1.5), h / 2.0, h / 2.0)
            p.setPen(Qt.NoPen)
        r = h - 4
        x = (w - r - 2) if on else 2
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, 2, r, r))
        p.end()


def make_icon(name, color, size=17):
    """Draw a simple stroke icon into a QIcon (no image assets)."""
    import math
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = float(size)
    if name == "lines":
        p.drawLine(QPointF(3, 5), QPointF(s - 3, 5))
        p.drawLine(QPointF(3, 9), QPointF(s - 3, 9))
        p.drawLine(QPointF(3, 13), QPointF(s - 6, 13))
    elif name == "chevron":
        p.drawLine(QPointF(7, 5), QPointF(12, 9))
        p.drawLine(QPointF(12, 9), QPointF(7, 13))
    elif name == "queue":
        p.drawLine(QPointF(3, 5), QPointF(s - 7, 5))
        p.drawLine(QPointF(3, 9), QPointF(s - 7, 9))
        p.drawLine(QPointF(3, 13), QPointF(s - 9, 13))
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(s - 5, 8), QPointF(s - 5, 15), QPointF(s - 1.5, 11.5)]))
    elif name == "clock":
        p.drawEllipse(QRectF(3.5, 3.5, s - 7, s - 7))
        p.drawLine(QPointF(s / 2, s / 2), QPointF(s / 2, 6))
        p.drawLine(QPointF(s / 2, s / 2), QPointF(s / 2 + 2.5, s / 2 + 1.5))
    elif name == "rect":
        p.drawRoundedRect(QRectF(3, 5, s - 6, s - 10), 2, 2)
    elif name == "star":
        path = QPainterPath()
        cx, cy = s / 2, s / 2
        r1, r2 = s / 2 - 2, (s / 2 - 2) * 0.45
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = r1 if i % 2 == 0 else r2
            pt = QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "coin":
        p.drawEllipse(QRectF(3.5, 3.5, s - 7, s - 7))
        p.drawLine(QPointF(s / 2, 6.5), QPointF(s / 2, s - 6.5))
        p.drawLine(QPointF(s / 2 - 2.5, 8.5), QPointF(s / 2 + 2.5, 8.5))
        p.drawLine(QPointF(s / 2 - 2.5, s - 8.5), QPointF(s / 2 + 2.5, s - 8.5))
    elif name == "bars":
        p.drawLine(QPointF(5, s - 4), QPointF(5, 10))
        p.drawLine(QPointF(s / 2, s - 4), QPointF(s / 2, 6))
        p.drawLine(QPointF(s - 5, s - 4), QPointF(s - 5, 8))
    elif name == "shield":
        path = QPainterPath()
        path.moveTo(s / 2, 3)
        path.lineTo(s - 3.5, 6)
        path.lineTo(s - 3.5, 10)
        path.cubicTo(s - 3.5, 14, s / 2 + 2, 15.5, s / 2, 16.5)
        path.cubicTo(s / 2 - 2, 15.5, 3.5, 14, 3.5, 10)
        path.lineTo(3.5, 6)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "layers":
        p.drawPolygon(QPolygonF([
            QPointF(s / 2, 3), QPointF(s - 3, 6.5),
            QPointF(s / 2, 10), QPointF(3, 6.5),
        ]))
        p.drawLine(QPointF(3, 10.5), QPointF(s / 2, 14))
        p.drawLine(QPointF(s - 3, 10.5), QPointF(s / 2, 14))
    elif name == "info":
        p.drawEllipse(QRectF(3.5, 3.5, s - 7, s - 7))
        p.drawPoint(QPointF(s / 2, 7))
        p.drawLine(QPointF(s / 2, 9.5), QPointF(s / 2, 13))
    elif name == "gear":
        cx, cy = s / 2, s / 2
        p.drawEllipse(QRectF(cx - 2.4, cy - 2.4, 4.8, 4.8))
        for i in range(8):
            ang = i * math.pi / 4
            p.drawLine(QPointF(cx + 4.4 * math.cos(ang), cy + 4.4 * math.sin(ang)),
                       QPointF(cx + 6.6 * math.cos(ang), cy + 6.6 * math.sin(ang)))
    elif name == "play":
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(5, 3.5), QPointF(5, s - 3.5), QPointF(s - 3.5, s / 2)]))
    elif name == "pause":
        p.drawLine(QPointF(6, 4), QPointF(6, s - 4))
        p.drawLine(QPointF(s - 6, 4), QPointF(s - 6, s - 4))
    elif name == "skip":
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(4, 4), QPointF(4, s - 4), QPointF(s - 6, s / 2)]))
        p.drawLine(QPointF(s - 4, 4), QPointF(s - 4, s - 4))
    elif name == "folder":
        p.drawPolyline(QPolygonF([QPointF(3, 5), QPointF(7, 5), QPointF(8.5, 6.5),
                                  QPointF(s - 3, 6.5), QPointF(s - 3, s - 4),
                                  QPointF(3, s - 4), QPointF(3, 5)]))
    elif name == "dots":
        p.setBrush(QColor(color))
        for x in (4.5, s / 2, s - 4.5):
            p.drawEllipse(QPointF(x, s / 2), 1.1, 1.1)
    elif name == "trash":
        p.drawLine(QPointF(3.5, 5), QPointF(s - 3.5, 5))
        p.drawLine(QPointF(7, 5), QPointF(7.5, 3))
        p.drawLine(QPointF(s - 7, 5), QPointF(s - 7.5, 3))
        p.drawPolyline(QPolygonF([QPointF(5, 5), QPointF(6, s - 3), QPointF(s - 6, s - 3), QPointF(s - 5, 5)]))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Item delegates for the dense table
# ---------------------------------------------------------------------------

class _ComboDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super(_ComboDelegate, self).__init__(parent)
        self.items = list(items)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self.items)
        return cb

    def setEditorData(self, editor, index):
        text = index.data(Qt.EditRole) or ""
        i = editor.findText(text, Qt.MatchFixedString)
        editor.setCurrentIndex(max(0, i))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


class _SpinDelegate(QStyledItemDelegate):
    def __init__(self, lo, hi, suffix="", parent=None):
        super(_SpinDelegate, self).__init__(parent)
        self.lo, self.hi, self.suffix = lo, hi, suffix

    def createEditor(self, parent, option, index):
        sp = QSpinBox(parent)
        sp.setRange(self.lo, self.hi)
        sp.setSuffix(self.suffix)
        return sp

    def setEditorData(self, editor, index):
        try:
            editor.setValue(int(str(index.data(Qt.EditRole)).replace(self.suffix, "").strip() or 0))
        except ValueError:
            editor.setValue(self.lo)

    def setModelData(self, editor, model, index):
        editor.interpretText()
        model.setData(index, "%d%s" % (editor.value(), self.suffix), Qt.EditRole)


# ---------------------------------------------------------------------------
# Sidebar (Design 1) master list delegate
# ---------------------------------------------------------------------------

class MasterDelegate(QStyledItemDelegate):
    """Two-line command rows: dot + name + group pill / meta line."""

    def __init__(self, pal, parent=None):
        super(MasterDelegate, self).__init__(parent)
        self.pal = pal

    def sizeHint(self, option, index):
        return QSize(0, 54)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        selected = bool(option.state & QStyle.State_Selected)
        if selected:
            painter.fillRect(rect, rgba_color(self.pal["accent_soft"]))
            painter.fillRect(rect.left(), rect.top(), 2, rect.height(),
                             QColor(self.pal["accent"]))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(self.pal["surface2"]))

        cmd = index.data(Qt.UserRole)
        if not isinstance(cmd, dict):
            painter.restore()
            return

        name = cmd.get("Command", "")
        group = cmd.get("Group", "")
        enabled = cmd.get("Enabled", True)
        perm = cmd.get("Permission", "")
        cd = cmd.get("Cooldown", 0)
        cost = cmd.get("Cost", 0)
        has_sound = bool(cmd.get("SoundFile"))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.pal["green"] if enabled else self.pal["text3"]))
        painter.drawEllipse(QRectF(rect.left() + 14, rect.top() + 15, 7, 7))

        painter.setPen(QColor(self.pal["accent_press"] if selected else
                              (self.pal["text"] if enabled else self.pal["text3"])))
        painter.setFont(_ui_font(13, bold=True))
        name_rect = QRectF(rect.left() + 30, rect.top() + 8,
                           rect.width() - 30 - 100, 18)
        fm = painter.fontMetrics()
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         fm.elidedText(name, Qt.ElideRight, int(name_rect.width())))

        if group:
            bg, fg = pill_colors(group_pill_kind(group), self.pal)
            painter.setFont(_ui_font(10, bold=True))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(group) if hasattr(fm, "horizontalAdvance") else fm.width(group)
            pw = min(tw + 16, 96)
            px = rect.right() - 14 - pw
            py = rect.top() + 11
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba_color(bg))
            painter.drawRoundedRect(QRectF(px, py, pw, 16), 8, 8)
            painter.setPen(QColor(fg))
            painter.drawText(QRectF(px, py, pw, 16), Qt.AlignCenter,
                             fm.elidedText(group, Qt.ElideRight, int(pw - 8)))

        painter.setPen(QColor(self.pal["text3"]))
        painter.setFont(_ui_font(11))
        if "_meta" in cmd:  # rows that are not sound commands (Sys.Commands)
            meta_text = cmd["_meta"]
        else:
            meta = [perm]
            if cd:
                meta.append("%s min" % cd)
            if cost:
                meta.append("%s pts" % cost)
            meta.append("%d%%" % cmd_volume(cmd) if has_sound else "no sound")
            meta_text = " · ".join(meta)
        meta_rect = QRectF(rect.left() + 30, rect.top() + 30, rect.width() - 44, 16)
        painter.drawText(meta_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         painter.fontMetrics().elidedText(meta_text, Qt.ElideRight,
                                                          int(meta_rect.width())))
        painter.restore()


# ---------------------------------------------------------------------------
# Persistent sidebar navigation (Design 1 / Midnight)
# ---------------------------------------------------------------------------

class SidebarNav(QFrame):
    """Left navigation rail. NAV items map to main-tab indices."""

    NAV = [
        ("Manage", [
            (0, "Commands", "lines"),
            (7, "Queue Control", "queue"),
            (1, "Sys.Commands", "clock"),
            (6, "Group Settings", "layers"),
        ]),
        ("Twitch", [
            (2, "Twitch", "rect"),
            (5, "Ranks", "star"),
        ]),
        ("Economy", [
            (3, "Currency", "coin"),
            (4, "Users", "bars"),
        ]),
        ("System", [
            (11, "Settings", "gear"),
            (9, "History", "lines"),
            (10, "Backups", "shield"),
            (8, "About", "info"),
        ]),
    ]

    def __init__(self, editor, tab_widget, pal):
        super(SidebarNav, self).__init__()
        self.editor = editor
        self.tab_widget = tab_widget
        self.pal = pal
        self._nav_buttons = {}
        self._build()

    def _build(self):
        self.setObjectName("sidebarPanel")
        self.setFixedWidth(210)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 14, 12, 12)
        v.setSpacing(2)

        brand = QHBoxLayout()
        brand.setSpacing(9)
        brand.addWidget(LogoBadge(self.pal))
        name = QLabel("Command Editor")
        name.setObjectName("brandName")
        brand.addWidget(name)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(6)

        # The items scroll when the window is short (the 12-item rail used
        # to force a minimum window height of ~630 px).
        items_box = QWidget()
        items_box.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(items_box)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(2)
        for section, items in self.NAV:
            lbl = QLabel(section.upper())
            lbl.setObjectName("navSection")
            lbl.setContentsMargins(10, 12, 0, 4)
            iv.addWidget(lbl)
            for idx, label, icon in items:
                b = QPushButton("  " + label)
                b.setObjectName("navBtn")
                b.setIcon(make_icon(icon, self.pal["text2"]))
                b.setIconSize(QSize(17, 17))
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, i=idx: self._go_tab(i))
                self._nav_buttons[idx] = b
                iv.addWidget(b)
        iv.addStretch(1)
        nav_scroll = _scroll_wrap(items_box, horizontal=False)
        nav_scroll.viewport().setStyleSheet("background: transparent;")
        v.addWidget(nav_scroll, 1)
        # Real connection state (was a hard-coded "main_channel · live").
        self.status = QLabel("")
        self.status.setObjectName("sideStatus")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(2000)
        self._update_status()

        if self.tab_widget is not None:
            self.tab_widget.currentChanged.connect(self.highlight_tab)

    def _update_status(self):
        text, key = connection_state(self.editor)
        self.status.setText("●  " + text)
        self.status.setStyleSheet("color: %s; font-size: 12px; padding: 8px;" % self.pal[key])

    def _go_tab(self, idx):
        if self.tab_widget is not None and 0 <= idx < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(idx)

    def highlight_tab(self, idx):
        for i, b in self._nav_buttons.items():
            b.setObjectName("navBtnActive" if i == idx else "navBtn")
            b.setIcon(make_icon(self._icon_of(i), self.pal["accent_press"] if i == idx else self.pal["text2"]))
            b.style().unpolish(b)
            b.style().polish(b)
        for i, b in self._nav_buttons.items():
            b.setVisible(self.tab_widget is None or i < self.tab_widget.count())

    def _icon_of(self, idx):
        for _section, items in self.NAV:
            for i, _label, icon in items:
                if i == idx:
                    return icon
        return "lines"


# ---------------------------------------------------------------------------
# Shared pieces of the themed Commands views
# ---------------------------------------------------------------------------

def _scroll_wrap(widget, horizontal=True):
    """Put a page in a frameless scroll area. A themed page then no longer
    dictates the window's minimum size: when the window is smaller than the
    page, scroll bars appear instead (the window used to refuse to shrink
    below ~1120x650 in the themed layouts)."""
    sa = QScrollArea()
    sa.setObjectName("themedScroll")
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded if horizontal else Qt.ScrollBarAlwaysOff)
    sa.setWidget(widget)
    return sa


def _shrinkable(edit, max_width, min_width=110):
    """Search boxes: up to max_width, but allowed to shrink."""
    edit.setMinimumWidth(min_width)
    edit.setMaximumWidth(max_width)
    edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return edit


def _overflow_toolbar(height):
    """Toolbar whose buttons that don't fit move into a "»" menu."""
    tb = QToolBar()
    tb.setObjectName("toolbar")
    tb.setMovable(False)
    tb.setFloatable(False)
    tb.setFixedHeight(height)
    return tb


def _held(widget):
    """Wrap a widget that the toolbar must NOT own.

    QToolBar.addWidget() hands the widget to a QWidgetAction, which hides it
    on overflow and deletes it together with the toolbar — even after the
    widget was moved elsewhere. The Twitch tab's own buttons are moved from
    view to view on every theme switch, so they go in a holder: the toolbar
    owns only the holder ("wrapped C/C++ object of type QPushButton has been
    deleted" on the next theme switch, auth button missing in classic)."""
    holder = QWidget()
    holder.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(widget)
    widget.show()
    return holder


def _toolbar_stretch(tb):
    sp = QWidget()
    sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    sp.setStyleSheet("background: transparent;")
    tb.addWidget(sp)


def _known_groups(commands, editor):
    groups = set()
    for c in commands:
        if c.get("Group"):
            groups.add(c.get("Group"))
    try:
        groups.update(editor.config_manager.get_audio_categories().keys())
    except Exception:
        pass
    return sorted(groups, key=lambda s: str(s).upper())


def _more_menu(parent, editor):
    """Secondary file actions that were missing from the themed views."""
    m = QMenu(parent)
    m.addAction("Load file…", editor.load_file)
    m.addAction("Save file", editor.save_file)
    m.addAction("Save legacy format…", editor.save_legacy_format)
    m.addSeparator()
    m.addAction("Auto-assign sounds…", editor.auto_assign_sounds)
    m.addAction("Fix sound paths (moved folder)…", editor.fix_sound_paths)
    return m


def _matches(cmd, needle):
    if not needle:
        return True
    hay = " ".join(str(cmd.get(k, "")) for k in
                   ("Command", "Group", "Permission", "Info", "Response", "SoundFile")).lower()
    return needle in hay


class CommandDetailEditor(QScrollArea):
    """Full editor for one command (all fields of the classic tab).

    Used by the Sidebar/Midnight Commands view (right pane) and by the
    Spreadsheet view (inspector next to the table). Text edits are applied
    after a short pause (not on every keystroke: each apply rewrites
    commands.json and pushes to the bot). Every edit goes through
    editor.apply_command_edit().
    """

    def __init__(self, editor, table, commands, pal, on_remove, on_changed=None):
        super(CommandDetailEditor, self).__init__()
        self.editor = editor
        self.table = table
        self.commands = commands
        self.pal = pal
        self.on_remove = on_remove
        self.on_changed = on_changed  # callback(row) after an applied edit
        self._guard = False
        self.row = -1
        self._pending = {}
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(350)
        self._apply_timer.timeout.connect(self.flush)
        self.setObjectName("detailScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._build()
        self.populate(-1)

    def _label(self, text):
        lab = QLabel(text)
        lab.setObjectName("fieldLabel")
        return lab

    def _build(self):
        panel = QFrame()
        panel.setObjectName("detailPanel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        ico = QFrame()
        ico.setObjectName("dIco")
        ico.setFixedSize(40, 40)
        ico_l = QVBoxLayout(ico)
        ico_l.setContentsMargins(0, 0, 0, 0)
        ico_t = QLabel("!")
        ico_t.setObjectName("dIcoText")
        ico_t.setAlignment(Qt.AlignCenter)
        ico_l.addWidget(ico_t)
        head.addWidget(ico)
        ttl = QVBoxLayout()
        ttl.setSpacing(2)
        self.d_title = QLabel("!command")
        self.d_title.setObjectName("dTitle")
        self.d_sub = QLabel("")
        self.d_sub.setObjectName("dSub")
        ttl.addWidget(self.d_title)
        ttl.addWidget(self.d_sub)
        head.addLayout(ttl, 1)
        en_lab = QLabel("Enabled")
        en_lab.setObjectName("switchDesc")
        head.addWidget(en_lab)
        self.d_enabled = ToggleSwitch(self.pal)
        self.d_enabled.setToolTip("Enable / disable this command")
        self.d_enabled.toggled.connect(lambda on: self._edit("Enabled", bool(on), now=True))
        head.addWidget(self.d_enabled)
        self.d_delete = QPushButton()
        self.d_delete.setObjectName("dangerBtn")
        self.d_delete.setIcon(make_icon("trash", self.pal["red"]))
        self.d_delete.setToolTip("Delete this command")
        self.d_delete.clicked.connect(self._remove)
        head.addWidget(self.d_delete)
        v.addLayout(head)

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(6)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)

        self.f_command = QLineEdit()
        self.f_command.textChanged.connect(lambda t: self._edit("Command", t))
        self.f_group = QComboBox()
        self.f_group.setEditable(True)
        self.f_group.setInsertPolicy(QComboBox.NoInsert)
        self.f_group.setToolTip("Commands of a group share queue / channel settings (Group Settings tab)")
        self.f_group.editTextChanged.connect(lambda t: self._edit("Group", t))
        g.addWidget(self._label("Command"), 0, 0)
        g.addWidget(self._label("Group"), 0, 1)
        g.addWidget(self.f_command, 1, 0)
        g.addWidget(self.f_group, 1, 1)

        self.f_perm = QComboBox()
        self.f_perm.addItems(PERMISSIONS)
        self.f_perm.currentTextChanged.connect(lambda t: self._edit("Permission", t, now=True))
        self.f_usage = QComboBox()
        self.f_usage.addItems(USAGES)
        self.f_usage.setToolTip("SC = Streamer.bot/SC style, Chat = chat only, Both")
        self.f_usage.currentTextChanged.connect(lambda t: self._edit("Usage", t, now=True))
        g.addWidget(self._label("Permission"), 2, 0)
        g.addWidget(self._label("Usage"), 2, 1)
        g.addWidget(self.f_perm, 3, 0)
        g.addWidget(self.f_usage, 3, 1)

        self.f_cd = QSpinBox()
        self.f_cd.setRange(0, 100000)
        self.f_cd.setSuffix(" min")
        self.f_cd.setSpecialValueText("none")
        self.f_cd.setToolTip("Global cooldown in MINUTES")
        self.f_cd.valueChanged.connect(lambda val: self._edit("Cooldown", val))
        self.f_ucd = QSpinBox()
        self.f_ucd.setRange(0, 100000)
        self.f_ucd.setSuffix(" min")
        self.f_ucd.setSpecialValueText("none")
        self.f_ucd.setToolTip("Per-viewer cooldown in MINUTES")
        self.f_ucd.valueChanged.connect(lambda val: self._edit("UserCooldown", val))
        g.addWidget(self._label("Cooldown"), 4, 0)
        g.addWidget(self._label("User cooldown"), 4, 1)
        g.addWidget(self.f_cd, 5, 0)
        g.addWidget(self.f_ucd, 5, 1)

        self.f_cost = QSpinBox()
        self.f_cost.setRange(0, 10000000)
        self.f_cost.setSpecialValueText("free")
        self.f_cost.valueChanged.connect(lambda val: self._edit("Cost", val))
        self.f_count = QSpinBox()
        self.f_count.setRange(0, 100000000)
        self.f_count.setToolTip("How many times the command was used")
        self.f_count.valueChanged.connect(lambda val: self._edit("Count", val))
        g.addWidget(self._label("Cost (points)"), 6, 0)
        g.addWidget(self._label("Used"), 6, 1)
        g.addWidget(self.f_cost, 7, 0)
        g.addWidget(self.f_count, 7, 1)

        self.f_info = QLineEdit()
        self.f_info.setPlaceholderText("Description for yourself / moderators")
        self.f_info.textChanged.connect(lambda t: self._edit("Info", t))
        g.addWidget(self._label("Info"), 8, 0, 1, 2)
        g.addWidget(self.f_info, 9, 0, 1, 2)
        v.addLayout(g)

        # Sound
        v.addWidget(self._label("Sound file"))
        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.f_sound = QLineEdit()
        self.f_sound.setPlaceholderText("No sound")
        self.f_sound.textChanged.connect(lambda t: self._edit("SoundFile", t))
        self.f_sound.textChanged.connect(self._mark_missing)
        srow.addWidget(self.f_sound, 1)
        b = QPushButton()
        b.setIcon(make_icon("folder", self.pal["text2"]))
        b.setToolTip("Browse…")
        b.clicked.connect(lambda: self.editor.browse_file(self.f_sound))
        srow.addWidget(b)
        self.play_btn = QPushButton()
        self.play_btn.setIcon(make_icon("play", self.pal["accent"]))
        self.play_btn.setToolTip("Preview sound (click again to stop)")
        self.play_btn.clicked.connect(self._preview)
        srow.addWidget(self.play_btn)
        v.addLayout(srow)
        self.missing_lab = QLabel("File not found (moved?). Use “Fix sound paths” in the file menu.")
        self.missing_lab.setStyleSheet("color: %s; font-size: 11px;" % self.pal["red"])
        self.missing_lab.setWordWrap(True)
        self.missing_lab.hide()
        v.addWidget(self.missing_lab)

        vrow = QHBoxLayout()
        vrow.setSpacing(10)
        vrow.addWidget(self._label("Volume"))
        self.f_volume = QSlider(Qt.Horizontal)
        self.f_volume.setRange(0, 100)
        self.f_volume.valueChanged.connect(self._on_volume)
        vrow.addWidget(self.f_volume, 1)
        self.f_volume_lab = QLabel("100%")
        self.f_volume_lab.setMinimumWidth(40)
        vrow.addWidget(self.f_volume_lab)
        v.addLayout(vrow)

        v.addWidget(self._label("FK sound file (fallback)"))
        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.f_fk = QLineEdit()
        self.f_fk.textChanged.connect(lambda t: self._edit("FKSoundFile", t))
        frow.addWidget(self.f_fk, 1)
        b2 = QPushButton()
        b2.setIcon(make_icon("folder", self.pal["text2"]))
        b2.setToolTip("Browse…")
        b2.clicked.connect(lambda: self.editor.browse_file(self.f_fk))
        frow.addWidget(b2)
        v.addLayout(frow)

        rl = QHBoxLayout()
        rl.addWidget(self._label("Response"))
        rl.addStretch(1)
        rh = QLabel("{user} = viewer · empty line = pause · each line = message")
        rh.setObjectName("switchDesc")
        rl.addWidget(rh)
        v.addLayout(rl)
        self.f_response = QTextEdit()
        self.f_response.setAcceptRichText(False)
        self.f_response.setMinimumHeight(90)
        self.f_response.textChanged.connect(
            lambda: self._edit("Response", self.f_response.toPlainText()))
        v.addWidget(self.f_response)
        v.addStretch(1)

        self.detail_widgets = [self.f_command, self.f_group, self.f_perm, self.f_usage,
                               self.f_cd, self.f_ucd, self.f_cost, self.f_count, self.f_info,
                               self.f_sound, self.f_fk, self.f_volume, self.f_response,
                               self.d_enabled, self.d_delete, self.play_btn, b, b2]
        self.setWidget(panel)

    # -- edits --------------------------------------------------------
    def _edit(self, key, value, now=False):
        if self._guard or self.row < 0:
            return
        self._pending[key] = value
        if key == "Command":
            self.d_title.setText(value or "!command")
        if now:
            self.flush()
        else:
            self._apply_timer.start()

    def flush(self):
        self._apply_timer.stop()
        if not self._pending or self.row < 0:
            self._pending = {}
            return
        changes, self._pending = self._pending, {}
        self.editor.apply_command_edit(self.row, changes)
        self._update_header()
        if self.on_changed is not None:
            self.on_changed(self.row)

    def _on_volume(self, val):
        self.f_volume_lab.setText("%d%%" % val)
        self._edit("Volume", int(val))

    def _mark_missing(self, text):
        text = (text or "").strip()
        self.missing_lab.setVisible(bool(text) and not os.path.exists(text))

    def _preview(self):
        self.flush()
        if self.row >= 0:
            self.table.selectRow(self.row)
            self.editor.play_or_stop_sound()

    def _remove(self):
        self.flush()
        if self.row < 0:
            return
        self.table.selectRow(self.row)
        self.on_remove()

    def set_groups(self, groups):
        self.f_group.blockSignals(True)
        text = self.f_group.currentText()
        self.f_group.clear()
        self.f_group.addItems(groups)
        self.f_group.setEditText(text)
        self.f_group.blockSignals(False)

    def _update_header(self):
        if self.row < 0:
            return
        cmd = self.commands[self.row]
        self.d_title.setText(cmd.get("Command", "") or "!command")
        bits = [cmd.get("Group", "") or "no group", cmd.get("Permission", "")]
        if not cmd.get("Enabled", True):
            bits.append("disabled")
        self.d_sub.setText(" · ".join(b for b in bits if b))

    def populate(self, row):
        ok = 0 <= row < len(self.commands)
        for w in self.detail_widgets:
            w.setEnabled(ok)
        self.row = row if ok else -1
        if not ok:
            self.d_title.setText("No command selected")
            self.d_sub.setText("Select a row or create one with + New")
            self.missing_lab.hide()
            return
        cmd = self.commands[row]
        self._guard = True
        try:
            self.f_command.setText(cmd.get("Command", ""))
            self.f_group.setEditText(cmd.get("Group", ""))
            perm = cmd.get("Permission", "Everyone")
            if self.f_perm.findText(perm) < 0:
                self.f_perm.addItem(perm)
            self.f_perm.setCurrentText(perm)
            usage = cmd.get("Usage", "SC")
            if self.f_usage.findText(usage) < 0:
                self.f_usage.addItem(usage)
            self.f_usage.setCurrentText(usage)
            self.f_cd.setValue(int(cmd.get("Cooldown", 0) or 0))
            self.f_ucd.setValue(int(cmd.get("UserCooldown", 0) or 0))
            self.f_cost.setValue(int(cmd.get("Cost", 0) or 0))
            self.f_count.setValue(int(cmd.get("Count", 0) or 0))
            self.f_info.setText(cmd.get("Info", ""))
            self.f_sound.setText(cmd.get("SoundFile", ""))
            self.f_fk.setText(str(cmd.get("FKSoundFile", "") or ""))
            vol = cmd_volume(cmd)
            self.f_volume.setValue(vol)
            self.f_volume_lab.setText("%d%%" % vol)
            self.f_response.setPlainText(cmd.get("Response", ""))
            self.d_enabled.setChecked(bool(cmd.get("Enabled", True)))
        finally:
            self._guard = False
        self._mark_missing(self.f_sound.text())
        self._update_header()


class SidebarCommandsView(QWidget):
    """Design 1: master list + full detail editor for the Commands tab."""

    def __init__(self, parent, main_tab, table, commands, search_input,
                 on_add, on_remove, on_load, on_save):
        super(SidebarCommandsView, self).__init__(parent)
        self.editor = parent
        self.main_tab = main_tab
        self.table = table
        self.commands = commands
        self.search_input = search_input
        self.on_add = on_add
        self.on_remove = on_remove
        self.on_load = on_load
        self.on_save = on_save
        self._guard = False
        self.pal = palette_for(getattr(parent, "theme", "sidebar"))
        self._build()
        self.refresh()

    @property
    def _row(self):
        return self.detail.row

    # -- construction -------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar(), 0)
        body = QWidget()
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)
        bh.addWidget(self._build_master(), 0)
        self.detail = CommandDetailEditor(self.editor, self.table, self.commands, self.pal,
                                          on_remove=self._remove, on_changed=self._on_detail_changed)
        bh.addWidget(self.detail, 1)
        root.addWidget(body, 1)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(54)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(10)
        title = QLabel("Commands")
        title.setObjectName("topTitle")
        h.addWidget(title)
        self.crumb = QLabel("")
        self.crumb.setObjectName("crumb")
        h.addWidget(self.crumb)
        h.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchBox")
        self.search_edit.setPlaceholderText("Search name, group, response…")
        self.search_edit.setClearButtonEnabled(True)
        _shrinkable(self.search_edit, 240)
        self.search_edit.textChanged.connect(self._on_search)
        h.addWidget(self.search_edit, 3)
        more = QPushButton()
        more.setIcon(make_icon("dots", self.pal["text2"]))
        more.setToolTip("Load / save / legacy export / auto-assign / fix sound paths")
        more.setMenu(_more_menu(more, self.editor))
        h.addWidget(more)
        save = QPushButton("Save")
        save.setToolTip("Save commands to file")
        save.clicked.connect(self.on_save)
        h.addWidget(save)
        new = QPushButton("+ New")
        new.setObjectName("primaryBtn")
        new.clicked.connect(self._add)
        h.addWidget(new)
        return bar

    def _build_master(self):
        panel = QFrame()
        panel.setObjectName("masterPanel")
        panel.setMinimumWidth(220)  # shrinks with the window (was fixed 320)
        panel.setMaximumWidth(320)
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(14, 12, 14, 12)
        t = QLabel("All commands")
        t.setObjectName("mheadTitle")
        self.hint = QLabel("")
        self.hint.setObjectName("mheadHint")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.hint)
        frame = QFrame()
        frame.setStyleSheet("border-bottom: 1px solid %s;" % self.pal["border"])
        frame.setLayout(head)
        v.addWidget(frame)
        self.master_list = QListWidget()
        self.master_list.setObjectName("masterList")
        self.master_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.master_list.setUniformItemSizes(True)
        self.master_list.setMouseTracking(True)
        self.master_list.setItemDelegate(MasterDelegate(self.pal, self.master_list))
        self.master_list.itemSelectionChanged.connect(self._on_master_selected)
        v.addWidget(self.master_list, 1)
        self.empty_hint = QLabel("No commands match the search.")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setObjectName("statusLabel")
        self.empty_hint.hide()
        v.addWidget(self.empty_hint)
        return panel

    # -- edits --------------------------------------------------------
    def _flush_pending(self):
        self.detail.flush()

    def _on_detail_changed(self, row):
        self._update_crumb()
        self._update_master_item(row)

    def _add(self):
        self._flush_pending()
        self.on_add()
        if self.commands:
            self.search_edit.clear()
            self.refresh(select_row=len(self.commands) - 1)
            self.detail.f_command.setFocus()
            self.detail.f_command.selectAll()

    def _remove(self):
        if self._row < 0:
            return
        self.table.selectRow(self._row)
        self.on_remove()

    # -- behaviour ----------------------------------------------------
    def refresh(self, select_row=None):
        """Rebuild the list; keep the current command selected."""
        self._flush_pending()
        if select_row is None:
            select_row = self._row
        self.detail.set_groups(_known_groups(self.commands, self.editor))
        self.refresh_master()
        if not self.commands:
            self._populate_detail(-1)
            return
        if select_row is None or select_row < 0 or select_row >= len(self.commands):
            select_row = 0
        self._select_master_row(select_row)
        self._populate_detail(select_row)

    def _on_search(self, _text):
        self.refresh_master()
        self._select_master_row(self._row)

    def highlight_tab(self, idx):
        nav = getattr(self.editor, "sidebar_nav", None)
        if nav is not None:
            nav.highlight_tab(idx)

    def refresh_master(self):
        self.master_list.blockSignals(True)
        self.master_list.clear()
        needle = self.search_edit.text().strip().lower()
        shown = 0
        for i, cmd in enumerate(self.commands):
            if not _matches(cmd, needle):
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cmd)
            item.setData(Qt.UserRole + 1, i)
            item.setSizeHint(QSize(0, 54))
            item.setText(cmd.get("Command", ""))
            self.master_list.addItem(item)
            shown += 1
        total = len(self.commands)
        self.hint.setText("%d total" % total if shown == total else "%d of %d" % (shown, total))
        self.empty_hint.setVisible(shown == 0 and total > 0)
        self.master_list.blockSignals(False)

    def _select_master_row(self, row):
        self._guard = True
        for i in range(self.master_list.count()):
            it = self.master_list.item(i)
            if it.data(Qt.UserRole + 1) == row:
                self.master_list.setCurrentItem(it)
                self.master_list.scrollToItem(it)
                break
        else:
            self.master_list.clearSelection()
        self._guard = False

    def _update_master_item(self, row):
        for i in range(self.master_list.count()):
            it = self.master_list.item(i)
            if it.data(Qt.UserRole + 1) == row:
                it.setText(self.commands[row].get("Command", ""))
                self.master_list.update(self.master_list.indexFromItem(it))
                break

    def _on_master_selected(self):
        if self._guard:
            return
        items = self.master_list.selectedItems()
        if not items:
            return
        row = items[0].data(Qt.UserRole + 1)
        if not isinstance(row, int):
            return
        self._flush_pending()
        self._guard = True
        self.table.selectRow(row)  # keeps the classic widgets in sync
        self._guard = False
        self._populate_detail(row)

    def select_from_table(self, row):
        """Called when the main table selection changes."""
        if self._guard or row == self._row:
            return
        self._flush_pending()
        self._select_master_row(row)
        self._populate_detail(row)

    def _update_crumb(self):
        if self._row < 0:
            self.crumb.setText("")
            return
        self.crumb.setText("/ %s" % (self.commands[self._row].get("Group", "") or "GENERAL"))

    def _populate_detail(self, row):
        self.detail.populate(row)
        self._update_crumb()


# ---------------------------------------------------------------------------
# Spreadsheet (Design 9) Commands view
# ---------------------------------------------------------------------------

class SpreadsheetCommandsView(QWidget):
    """Design 9: dense inline-edit table + toolbar + status bar."""

    # (header, command key, width)
    COLS = [
        ("#", None, 44),
        ("Command", "Command", 150),
        ("Group", "Group", 100),
        ("Permission", "Permission", 96),
        ("Usage", "Usage", 64),
        ("CD", "Cooldown", 64),
        ("User CD", "UserCooldown", 70),
        ("Cost", "Cost", 64),
        ("Vol", "Volume", 60),
        ("Sound", "SoundFile", 170),
        ("Response", "Response", 220),
        ("Info", "Info", 140),
        ("Used", "Count", 56),
        ("On", "Enabled", 48),
    ]
    INT_KEYS = ("Cooldown", "UserCooldown", "Cost", "Count")

    def __init__(self, parent, main_tab, table, commands, search_input,
                 on_add, on_remove, on_load, on_save):
        super(SpreadsheetCommandsView, self).__init__(parent)
        self.editor = parent
        self.main_tab = main_tab
        self.table = table
        self.commands = commands
        self.search_input = search_input
        self.on_add = on_add
        self.on_remove = on_remove
        self.on_load = on_load
        self.on_save = on_save
        self._guard = False
        self.pal = palette_for(getattr(parent, "theme", "spreadsheet"))
        self._col = dict((key, i) for i, (_h, key, _w) in enumerate(self.COLS) if key)
        self._build()
        self.refresh()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_conn)
        self._status_timer.start(2000)

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_topbar(), 0)
        v.addWidget(self._build_toolbar(), 0)
        # table | inspector (the same full editor as the Sidebar layout)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(1)
        self.split.addWidget(self._build_table())
        self.detail = CommandDetailEditor(self.editor, self.table, self.commands, self.pal,
                                          on_remove=self.on_remove,
                                          on_changed=self._on_detail_changed)
        self.detail.setMinimumWidth(360)
        self.split.addWidget(self.detail)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setSizes([860, 420])
        v.addWidget(self.split, 1)
        v.addWidget(self._build_statusbar(), 0)
        shown = True
        try:
            shown = bool(self.editor.config_manager.config.get("spreadsheet_inspector", True))
        except Exception:
            pass
        self.detail.setVisible(shown)
        self.details_btn.setChecked(shown)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(56)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)
        h.addWidget(LogoBadge(self.pal))
        name = QLabel("Command Editor")
        name.setObjectName("brandName")
        h.addWidget(name)
        h.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchBox")
        self.search_edit.setPlaceholderText("Filter rows…")
        self.search_edit.setClearButtonEnabled(True)
        _shrinkable(self.search_edit, 220)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        h.addWidget(self.search_edit, 3)
        save = QPushButton("Save File")
        save.clicked.connect(self.on_save)
        new = QPushButton("+ Row")
        new.setObjectName("primaryBtn")
        new.clicked.connect(self._add)
        h.addWidget(save)
        h.addWidget(new)
        return bar

    def _tool(self, text, slot, tip=""):
        b = QPushButton(text)
        b.setObjectName("toolBtn")
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _build_toolbar(self):
        bar = _overflow_toolbar(44)
        h = bar  # QToolBar.addWidget, same calls as the old QHBoxLayout
        h.addWidget(self._tool("+ Insert", self._add))
        self.del_btn = self._tool("Delete", self._remove, "Delete selected row")
        h.addWidget(self.del_btn)
        h.addWidget(self._tool("Load", self.on_load))
        h.addWidget(self._tool("Save", self.on_save))
        more = QPushButton("More ▾")
        more.setObjectName("toolBtn")
        more.setMenu(_more_menu(more, self.editor))
        h.addWidget(more)
        sep = QFrame()
        sep.setFixedSize(1, 22)
        sep.setStyleSheet("background:%s;" % self.pal["border"])
        h.addWidget(sep)
        self.browse_btn = self._tool("Sound…", self._browse, "Choose a sound file for the selected row")
        self.play_btn = self._tool("▶ Play", self._preview, "Preview the selected row's sound")
        self.resp_btn = self._tool("Edit response…", self._edit_response,
                                   "Multi-line response editor (or double-click the Response cell)")
        h.addWidget(self.browse_btn)
        h.addWidget(self.play_btn)
        h.addWidget(self.resp_btn)
        _toolbar_stretch(bar)
        self.details_btn = self._tool("Details ▸", self._toggle_details,
                                      "Show / hide the editor with all fields of the selected row")
        self.details_btn.setCheckable(True)
        h.addWidget(self.details_btn)
        self.count_label = QLabel("0 rows")
        self.count_label.setObjectName("countLabel")
        h.addWidget(self.count_label)
        return bar

    def _build_table(self):
        self.dense = QTableWidget()
        self.dense.setObjectName("denseTable")
        self.dense.setColumnCount(len(self.COLS))
        self.dense.setHorizontalHeaderLabels([c[0] for c in self.COLS])
        tips = {"CD": "Global cooldown, minutes", "User CD": "Per-viewer cooldown, minutes",
                "Vol": "Volume 0-100%", "Used": "Times used", "On": "Enabled",
                "Response": "Double-click to edit (multi-line)"}
        for i, (hdr, _k, w) in enumerate(self.COLS):
            if hdr in tips:
                self.dense.horizontalHeaderItem(i).setToolTip(tips[hdr])
            self.dense.setColumnWidth(i, w)
        hh = self.dense.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(False)
        self.dense.verticalHeader().setVisible(False)
        self.dense.verticalHeader().setDefaultSectionSize(32)
        self.dense.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dense.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dense.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.SelectedClicked |
                                   QAbstractItemView.EditKeyPressed)
        self.dense.setItemDelegateForColumn(self._col["Permission"], _ComboDelegate(PERMISSIONS, self.dense))
        self.dense.setItemDelegateForColumn(self._col["Usage"], _ComboDelegate(USAGES, self.dense))
        for key in self.INT_KEYS:
            self.dense.setItemDelegateForColumn(self._col[key], _SpinDelegate(0, 10000000, "", self.dense))
        self.dense.setItemDelegateForColumn(self._col["Volume"], _SpinDelegate(0, 100, "%", self.dense))
        self.dense.itemChanged.connect(self._on_item_changed)
        self.dense.itemSelectionChanged.connect(self._on_selection)
        self.dense.cellDoubleClicked.connect(self._on_double_click)
        return self.dense

    def _build_statusbar(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(28)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(16)
        self.conn_label = QLabel("")
        h.addWidget(self.conn_label)
        self.file_label = QLabel("")
        self.file_label.setObjectName("statusLabel")
        h.addWidget(self.file_label)
        self.status_label = QLabel("ready")
        self.status_label.setObjectName("statusLabel")
        h.addWidget(self.status_label)
        h.addStretch(1)
        hint = QLabel("Double-click a cell to edit · Del deletes row")
        hint.setObjectName("statusLabel")
        h.addWidget(hint)
        self._update_conn()
        return bar

    def _toggle_details(self):
        on = self.details_btn.isChecked()
        self.detail.setVisible(on)
        try:
            self.editor.config_manager.config["spreadsheet_inspector"] = on
            self.editor.config_manager.save_config()
        except Exception:
            pass

    def _on_detail_changed(self, idx):
        """An edit in the inspector: re-render that table row."""
        for r in range(self.dense.rowCount()):
            if self._row_index(r) == idx:
                self._guard = True
                self._set_row(r, idx, self.commands[idx])
                self._guard = False
                break

    def _sync_detail(self):
        idx = self._selected_idx()
        target = idx if idx is not None else -1
        if target != self.detail.row:
            self.detail.flush()
            self.detail.populate(target)

    def _update_conn(self):
        text, key = connection_state(self.editor)
        self.conn_label.setText("●  " + text)
        self.conn_label.setStyleSheet("color: %s; font-size: 11px;" % self.pal[key])
        cur = getattr(self.editor, "current_file", None)
        self.file_label.setText(os.path.basename(cur) if cur else "commands.json")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.dense.hasFocus() and self.dense.state() != QAbstractItemView.EditingState:
            self._remove()
            return
        super(SpreadsheetCommandsView, self).keyPressEvent(event)

    # -- rows ---------------------------------------------------------
    def refresh(self):
        self.detail.flush()
        keep = self._current_index()
        if keep is None and self.detail.row >= 0:
            keep = self.detail.row
        self.detail.set_groups(_known_groups(self.commands, self.editor))
        self._guard = True
        self.dense.setRowCount(0)
        needle = self.search_edit.text().strip().lower()
        shown = 0
        for i, cmd in enumerate(self.commands):
            if not _matches(cmd, needle):
                continue
            self.dense.insertRow(shown)
            self._set_row(shown, i, cmd)
            shown += 1
        self._guard = False
        total = len(self.commands)
        self.count_label.setText("%d rows" % total if shown == total else "%d of %d rows" % (shown, total))
        if keep is not None:
            self.select_from_table(keep)
        self._update_actions()
        # data may have changed (response dialog, browse, add/remove)
        idx = self._selected_idx()
        self.detail.populate(idx if idx is not None else -1)

    def _item(self, text, editable=True, align=None, mono=False, tip=None):
        it = QTableWidgetItem(text)
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if editable:
            flags |= Qt.ItemIsEditable
        it.setFlags(flags)
        if align is not None:
            it.setTextAlignment(align)
        if mono:
            it.setFont(_mono_font(9))
        if tip:
            it.setToolTip(tip)
        return it

    def _set_row(self, row_pos, actual_idx, cmd):
        c = self._col
        right = Qt.AlignRight | Qt.AlignVCenter
        rn = self._item(str(actual_idx + 1), editable=False, align=Qt.AlignCenter)
        rn.setData(Qt.UserRole, actual_idx)
        rn.setForeground(QColor(self.pal["text3"]))
        self.dense.setItem(row_pos, 0, rn)
        name = self._item(cmd.get("Command", ""), tip=cmd.get("Info", "") or None)
        name.setFont(_mono_font(10))
        self.dense.setItem(row_pos, c["Command"], name)
        group = cmd.get("Group", "")
        gi = self._item(group, align=Qt.AlignCenter)
        bg, fg = pill_colors(group_pill_kind(group), self.pal)
        gi.setBackground(rgba_color(bg))
        gi.setForeground(QColor(fg))
        gf = _ui_font(9, bold=True)
        gi.setFont(gf)
        self.dense.setItem(row_pos, c["Group"], gi)
        self.dense.setItem(row_pos, c["Permission"], self._item(cmd.get("Permission", "")))
        self.dense.setItem(row_pos, c["Usage"], self._item(cmd.get("Usage", "")))
        for key in self.INT_KEYS:
            self.dense.setItem(row_pos, c[key], self._item(str(cmd.get(key, 0) or 0), align=right))
        self.dense.setItem(row_pos, c["Volume"], self._item("%d%%" % cmd_volume(cmd), align=right))
        snd = cmd.get("SoundFile", "") or ""
        self.dense.setItem(row_pos, c["SoundFile"],
                           self._item(os.path.basename(snd) if snd else "—", editable=False,
                                      mono=True, tip=snd or "No sound — use Sound… to choose one"))
        resp = cmd.get("Response", "") or ""
        first = resp.strip().split("\n")[0] if resp.strip() else ""
        shown = first + (" ↵…" if "\n" in resp.strip() else "")
        self.dense.setItem(row_pos, c["Response"],
                           self._item(shown or "—", editable=False, tip=resp or None))
        self.dense.setItem(row_pos, c["Info"], self._item(cmd.get("Info", "")))
        sw = ToggleSwitch(self.pal, width=32, height=18)
        sw.setChecked(bool(cmd.get("Enabled", True)))
        sw.toggled.connect(lambda on_chk, idx=actual_idx: self._apply(idx, {"Enabled": bool(on_chk)}))
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignCenter)
        hl.addWidget(sw)
        self.dense.setCellWidget(row_pos, c["Enabled"], holder)

    def _row_index(self, row_pos):
        item = self.dense.item(row_pos, 0)
        if item is not None:
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                return idx
        return -1

    def _current_index(self):
        rows = self.dense.selectionModel().selectedRows() if self.dense.selectionModel() else []
        return self._row_index(rows[0].row()) if rows else None

    def _apply(self, idx, changes):
        if 0 <= idx < len(self.commands):
            self.editor.apply_command_edit(idx, changes)
            if self.detail.row == idx and "Enabled" in changes:
                self.detail.populate(idx)

    def _on_item_changed(self, item):
        if self._guard:
            return
        col = item.column()
        key = self.COLS[col][1]
        idx = self._row_index(item.row())
        if key is None or idx < 0:
            return
        self.detail.flush()
        text = item.text().strip()
        if key in self.INT_KEYS:
            try:
                value = max(0, int(text or 0))
            except ValueError:
                value = self.commands[idx].get(key, 0)
        elif key == "Volume":
            try:
                value = max(0, min(100, int(float(text.replace("%", "") or 100))))
            except ValueError:
                value = cmd_volume(self.commands[idx])
        else:
            value = item.text()
        self._apply(idx, {key: value})
        # re-render the row (pill colour, % sign, ...) without losing selection
        self._guard = True
        self._set_row(item.row(), idx, self.commands[idx])
        self._guard = False
        if self.detail.row == idx:
            self.detail.populate(idx)

    def _on_double_click(self, row_pos, col):
        key = self.COLS[col][1]
        if key == "Response":
            self._edit_response()
        elif key == "SoundFile":
            self._browse()

    def _selected_idx(self):
        idx = self._current_index()
        return idx if idx is not None and 0 <= idx < len(self.commands) else None

    def _edit_response(self):
        idx = self._selected_idx()
        if idx is None:
            return
        cmd = self.commands[idx]
        text, ok = QInputDialog.getMultiLineText(
            self, "Response for %s" % cmd.get("Command", ""),
            "Each line is sent as a separate message. {user} = viewer name.\n"
            "An empty line adds a short pause.", cmd.get("Response", ""))
        if ok:
            self._apply(idx, {"Response": text})
            self.refresh()

    def _browse(self):
        idx = self._selected_idx()
        if idx is None:
            return
        tmp = QLineEdit(self.commands[idx].get("SoundFile", ""))
        self.editor.browse_file(tmp)
        if tmp.text() != self.commands[idx].get("SoundFile", ""):
            self._apply(idx, {"SoundFile": tmp.text()})
            self.refresh()

    def _preview(self):
        idx = self._selected_idx()
        if idx is None:
            return
        self.table.selectRow(idx)
        self.editor.play_or_stop_sound()

    def _add(self):
        self.on_add()
        self.search_edit.clear()
        self.refresh()
        if self.commands:
            self.select_from_table(len(self.commands) - 1)
            r = self.dense.currentRow()
            if r >= 0:
                self.dense.editItem(self.dense.item(r, self._col["Command"]))

    def _remove(self):
        idx = self._selected_idx()
        if idx is None:
            return
        self.table.selectRow(idx)
        self.on_remove()

    def _update_actions(self):
        has = self._selected_idx() is not None
        for b in (self.del_btn, self.browse_btn, self.play_btn, self.resp_btn):
            b.setEnabled(has)

    def _on_selection(self):
        self._update_actions()
        if self._guard:
            return
        self._sync_detail()
        idx = self._selected_idx()
        if idx is None:
            return
        self._guard = True
        self.table.selectRow(idx)
        self._guard = False
        self.status_label.setText("row %d · %s" % (idx + 1, self.commands[idx].get("Command", "")))

    def highlight_tab(self, idx):
        pass

    def select_from_table(self, row):
        if self._guard:
            return
        self._guard = True
        for i in range(self.dense.rowCount()):
            if self._row_index(i) == row:
                self.dense.selectRow(i)
                break
        self._guard = False
        self._update_actions()
        self._sync_detail()
        if 0 <= row < len(self.commands):
            self.status_label.setText("row %d · %s" % (row + 1, self.commands[row].get("Command", "")))


# ---------------------------------------------------------------------------
# Settings tab for the themed layouts
#
# In the classic layout these settings live in the Commands tab's right
# column; the themed Commands views have no room for them, so a separate tab
# shows proxies. Each proxy drives the ORIGINAL classic widget (setChecked /
# setValue), so the existing handlers keep doing the work (config, timers,
# running bot) and nothing is duplicated.
# ---------------------------------------------------------------------------

class SettingsPanel(QWidget):
    def __init__(self, editor):
        super(SettingsPanel, self).__init__(editor)
        self.editor = editor
        self.pal = palette_for(getattr(editor, "theme", "sidebar"))
        self._bindings = []
        self._build()

    def _card(self, title, desc):
        card = QFrame()
        card.setObjectName("settingsCard")
        if layout_of(getattr(self.editor, "theme", "")) == "classic":
            card.setFrameShape(QFrame.StyledPanel)  # no QSS in classic
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 8)
        v.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        v.addWidget(t)
        if desc:
            d = QLabel(desc)
            d.setObjectName("switchDesc")
            d.setWordWrap(True)
            v.addWidget(d)
        v.addSpacing(6)
        return card, v

    def _switch_row(self, layout, title, desc, source_check, spin=None, last=False):
        row = QFrame()
        row.setObjectName("switchRow" if not last else "")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("switchTitle")
        texts.addWidget(t)
        if desc:
            d = QLabel(desc)
            d.setObjectName("switchDesc")
            d.setWordWrap(True)
            texts.addWidget(d)
        h.addLayout(texts, 1)
        proxy_spin = None
        if spin is not None:
            proxy_spin = QSpinBox()
            proxy_spin.setRange(spin.minimum(), spin.maximum())
            proxy_spin.setSingleStep(spin.singleStep())
            proxy_spin.setSuffix(" s")
            proxy_spin.setFixedWidth(110)
            proxy_spin.setValue(spin.value())
            proxy_spin.valueChanged.connect(spin.setValue)
            h.addWidget(proxy_spin)
        sw = ToggleSwitch(self.pal)
        sw.setChecked(source_check.isChecked())
        sw.toggled.connect(source_check.setChecked)
        if proxy_spin is not None:
            proxy_spin.setEnabled(sw.isChecked())
            sw.toggled.connect(proxy_spin.setEnabled)
        h.addWidget(sw)
        layout.addWidget(row)
        self._bindings.append((sw, source_check, proxy_spin, spin))

    def _build(self):
        e = self.editor
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(14)

        card, cv = self._card("Sound", "How sounds of commands WITHOUT a queue behave on the shared channel.")
        self._switch_row(cv, "Allow sounds to interrupt each other",
                         "A new command stops the sound that is playing. Off: the new sound is skipped.",
                         e.allow_interruption_check)
        self._switch_row(cv, "Tell the viewer when their sound was blocked",
                         "Sends a chat message and refunds the points.",
                         e.show_interruption_message_check, last=True)
        v.addWidget(card)

        card, cv = self._card("Auto-save & backups", "Intervals are in seconds.")
        self._switch_row(cv, "Auto-save commands", "Write commands.json periodically.",
                         e.auto_save_checkbox, e.auto_save_interval_input)
        self._switch_row(cv, "Automatic full backups", "Commands + currency + settings snapshot.",
                         e.system_auto_backup_checkbox, e.system_backup_interval_input)
        self._switch_row(cv, "Auto-save currency users", "Points, hours and ranks.",
                         e.currency_auto_save_checkbox, e.currency_backup_interval_input, last=True)
        v.addWidget(card)

        card, cv = self._card("Appearance", "")
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 12)
        lab = QLabel("Theme")
        lab.setObjectName("switchTitle")
        row.addWidget(lab)
        row.addStretch(1)
        self.theme_combo = QComboBox()
        for key in THEMES:
            self.theme_combo.addItem(THEME_LABELS[key], key)
        self.theme_combo.setCurrentIndex(max(0, list(THEMES).index(getattr(e, "theme", "sidebar"))
                                            if getattr(e, "theme", "") in THEMES else 0))
        self.theme_combo.activated.connect(
            lambda i: QTimer.singleShot(0, lambda: e.set_theme(self.theme_combo.itemData(i))))
        row.addWidget(self.theme_combo)
        cv.addLayout(row)
        v.addWidget(card)
        v.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def showEvent(self, event):
        # Re-read values: they may have been changed elsewhere (e.g. restore).
        for sw, src, proxy_spin, spin in self._bindings:
            sw.blockSignals(True)
            sw.setChecked(src.isChecked())
            sw.blockSignals(False)
            if proxy_spin is not None:
                proxy_spin.blockSignals(True)
                proxy_spin.setValue(spin.value())
                proxy_spin.setEnabled(sw.isChecked())
                proxy_spin.blockSignals(False)
        super(SettingsPanel, self).showEvent(event)

    def highlight_tab(self, idx):
        pass


# ---------------------------------------------------------------------------
# Now-Playing bar (Midnight): every queue at a glance, under every tab
# ---------------------------------------------------------------------------

class NowPlayingBar(QFrame):
    """Compact strip with each queue group's current item + Skip/Pause."""

    def __init__(self, editor):
        super(NowPlayingBar, self).__init__(editor)
        self.editor = editor
        self.pal = palette_for(getattr(editor, "theme", "midnight"))
        self.setObjectName("nowBar")
        self.setFixedHeight(46)
        self._h = QHBoxLayout(self)
        self._h.setContentsMargins(14, 6, 14, 6)
        self._h.setSpacing(18)
        self._idle = QLabel("")
        self._idle.setObjectName("nowMeta")
        self._h.addWidget(self._idle)
        self._slots = {}
        self._h.addStretch(1)
        self._open = QPushButton("Queue Control")
        self._open.setIcon(make_icon("queue", self.pal["text2"]))
        self._open.clicked.connect(lambda: self._go(7))
        self._h.addWidget(self._open)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(500)
        self.refresh()

    def _go(self, idx):
        tw = getattr(self.editor, "tab_widget", None)
        if tw is not None and idx < tw.count():
            tw.setCurrentIndex(idx)

    def _bot(self):
        tt = getattr(self.editor, "twitch_tab", None)
        bot = getattr(tt, "bot", None) if tt is not None else None
        return bot if bot is not None and hasattr(bot, "queue_snapshot") else None

    def _make_slot(self, group):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        g = QLabel(group.upper())
        g.setObjectName("nowGroup")
        t = QLabel("")
        t.setObjectName("nowText")
        texts.addWidget(g)
        texts.addWidget(t)
        h.addLayout(texts)
        meta = QLabel("")
        meta.setObjectName("nowMeta")
        h.addWidget(meta)
        pause = QPushButton()
        pause.setFixedSize(30, 28)
        skip = QPushButton()
        skip.setIcon(make_icon("skip", self.pal["text"]))
        skip.setFixedSize(30, 28)
        skip.setToolTip("Skip what %s is playing" % group)
        h.addWidget(pause)
        h.addWidget(skip)
        pause.clicked.connect(lambda: self._toggle_pause(group))
        skip.clicked.connect(lambda: self._call("skip_queue_current", group))
        self._h.insertWidget(self._h.count() - 2, w)
        slot = {"w": w, "text": t, "meta": meta, "pause": pause, "skip": skip}
        self._slots[group] = slot
        return slot

    def _call(self, name, *args):
        bot = self._bot()
        loop = getattr(bot, "loop", None) if bot is not None else None
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(getattr(bot, name), *args)

    def _toggle_pause(self, group):
        bot = self._bot()
        if bot is not None:
            self._call("set_queue_paused", group, group not in bot.queue_paused)

    def refresh(self):
        bot = self._bot()
        groups = sorted(bot.command_queues) if bot is not None else []
        for g in list(self._slots):
            if g not in groups:
                self._slots.pop(g)["w"].deleteLater()
        if bot is None:
            text, _key = connection_state(self.editor)
            self._idle.setText("Queues appear here when the bot is connected (%s)." % text)
            self._idle.show()
            return
        if not groups:
            self._idle.setText("No queued groups — enable a queue in Group Settings.")
            self._idle.show()
            return
        self._idle.hide()
        for g in groups:
            snap = bot.queue_snapshot(g)
            if snap is None:
                continue
            slot = self._slots.get(g) or self._make_slot(g)
            cur = snap["current"]
            if cur is not None:
                slot["text"].setText("!%s" % cur["command"])
                started = cur.get("started")
                elapsed = int(time.time() - started) if started else 0
                slot["meta"].setText("%s · %d:%02d · %d waiting" % (
                    cur["user"], elapsed // 60, elapsed % 60, len(snap["pending"])))
            else:
                slot["text"].setText("paused" if snap["paused"] else "idle")
                slot["meta"].setText("%d waiting" % len(snap["pending"]) if snap["pending"] else "")
            slot["skip"].setEnabled(cur is not None)
            slot["pause"].setIcon(make_icon("play" if snap["paused"] else "pause", self.pal["text"]))
            slot["pause"].setToolTip("Resume %s" % g if snap["paused"] else "Pause %s" % g)


# ---------------------------------------------------------------------------
# Themed Twitch views (Design 1 sidebar / Design 9 spreadsheet)
#
# These re-parent the ORIGINAL TwitchTab widgets into a new themed layout, so
# every method on TwitchTab (chat, viewers, moderators, status, connect) keeps
# working unchanged. The classic TwitchTab is swapped out of the tab widget and
# re-parented back to the main window when the theme changes.
# ---------------------------------------------------------------------------

class TwitchThemedBase(QWidget):
    """Shared helpers for the two themed Twitch layouts."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(TwitchThemedBase, self).__init__(parent)
        self.editor = parent
        self.tab_widget = tab_widget
        self.twitch_tab = twitch_tab
        self.pal = palette_for(getattr(parent, "theme", "sidebar"))
        # Status labels (re-parented from the original tab into the status bar)
        self.connection_status = twitch_tab.connection_status
        self.stream_status = twitch_tab.stream_status
        self.active_viewers_count = twitch_tab.active_viewers_count
        self.all_viewers_count = twitch_tab.all_viewers_count

    # -- auth pill -------------------------------------------------------
    def _build_auth_pill(self):
        pill = QFrame()
        pill.setObjectName("authPill")
        h = QHBoxLayout(pill)
        h.setContentsMargins(11, 5, 11, 5)
        h.setSpacing(7)
        dot = QLabel("\u25cf")
        dot.setObjectName("authDot")
        text = QLabel("Not authenticated")
        text.setObjectName("authText")
        h.addWidget(dot)
        h.addWidget(text)
        self._auth_pill = pill
        self._auth_dot = dot
        self._auth_text = text
        self._apply_auth_state()
        return pill

    def _apply_auth_state(self):
        tt = self.twitch_tab
        authed = bool(tt.config_manager.get_twitch_config().get("access_token"))
        if authed:
            bg = "rgba(22,163,74,0.10)"
            fg = self.pal["green"]
            self._auth_text.setText("Authenticated")
        else:
            bg = "rgba(220,38,38,0.08)"
            fg = self.pal["red"]
            self._auth_text.setText("Not authenticated")
        self._auth_pill.setStyleSheet(
            "QFrame#authPill{background:%s;border:none;}"
            "QLabel{color:%s;font-size:12px;font-weight:500;}" % (bg, fg))
        self._auth_dot.setStyleSheet("color:%s;font-size:9px;" % fg)

    # -- stat strip ------------------------------------------------------
    def _build_stat_strip(self):
        strip = QFrame()
        strip.setObjectName("statStrip")
        strip.setFixedHeight(58)
        h = QHBoxLayout(strip)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(0)
        boxes = [
            ("\u25cf Live", "Stream status", "statLive"),
            ("0", "Active viewers", "statActive"),
            ("0", "All viewers", "statAll"),
            ("0", "Moderators", "statMods"),
        ]
        self._stat_live = self._stat_active = self._stat_all = self._stat_mods = None
        for i, (val, lab, key) in enumerate(boxes):
            box = QFrame()
            box.setObjectName("statBoxLast" if i == len(boxes) - 1 else "statBox")
            boxv = QVBoxLayout(box)
            boxv.setContentsMargins(16, 0, 16, 0)
            boxv.setSpacing(2)
            v = QLabel(val)
            v.setObjectName("statVal")
            l = QLabel(lab)
            boxv.addWidget(v)
            boxv.addWidget(l)
            h.addWidget(box, 1)
            if key == "statLive":
                self._stat_live = v
            elif key == "statActive":
                self._stat_active = v
            elif key == "statAll":
                self._stat_all = v
            elif key == "statMods":
                self._stat_mods = v
        self._stat_strip = strip
        self._update_stat_strip()
        return strip

    def _update_stat_strip(self):
        if getattr(self, "_stat_live", None) is None:
            return
        tt = self.twitch_tab
        live = getattr(tt, "currently_live", False)
        self._stat_live.setText("\u25cf Live" if live else "\u25cb Offline")
        self._stat_live.setStyleSheet(
            "color:%s;font-size:16px;font-weight:600;" %
            (self.pal["green"] if live else self.pal["text3"]))
        self._stat_active.setText(str(len(getattr(tt, "active_users", []) or [])))
        self._stat_all.setText(str(self.all_viewers_count.text().split(":")[-1].strip()))
        self._stat_mods.setText(str(len(getattr(tt, "moderators_list", []) or [])))

    # -- status bar ------------------------------------------------------
    def _build_status_bar(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(30)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(16)
        self.connection_status.setObjectName("statusLabel")
        self.stream_status.setObjectName("statusLabel")
        self.active_viewers_count.setObjectName("statusLabel")
        self.all_viewers_count.setObjectName("statusLabel")
        h.addWidget(self.connection_status)
        h.addWidget(self.stream_status)
        h.addStretch(1)
        h.addWidget(self.active_viewers_count)
        h.addWidget(self.all_viewers_count)
        self._status_bar = bar
        self._update_statusbar()
        return bar

    def _update_statusbar(self):
        tt = self.twitch_tab
        connected = bool(tt.bot and getattr(tt.bot, "is_running", False))
        self.connection_status.setText("connected" if connected else "not connected")
        self.connection_status.setStyleSheet(
            "color:%s;font-size:11.5px;" %
            (self.pal["green"] if connected else self.pal["text3"]))
        self.stream_status.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self.active_viewers_count.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self.all_viewers_count.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self._update_stat_strip()

    # -- panel helpers ---------------------------------------------------
    def _panel(self, title, hint):
        panel = QFrame()
        panel.setObjectName("panel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("panelHead")
        head.addWidget(t)
        if hint:
            hh = QLabel(hint)
            hh.setObjectName("panelHint")
            head.addWidget(hh)
        head.addStretch(1)
        v.addLayout(head)
        return panel, v

    def _sync_viewers_tabs(self, idx):
        labels = {0: "All Viewers", 1: "Active Chatters", 2: "Moderators"}
        want = labels.get(idx)
        for i in range(self.twitch_tab.viewers_tabs.count()):
            if self.twitch_tab.viewers_tabs.tabText(i) == want:
                self.twitch_tab.viewers_tabs.setCurrentIndex(i)
                break

    def _build_moderator_controls(self):
        tt = self.twitch_tab
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(tt.add_moderator_input)
        row1.addWidget(tt.add_moderator_button)
        row1.addWidget(tt.remove_moderator_button)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(tt.open_moderators_file_button)
        row2.addWidget(tt.refresh_moderators_button)
        row2.addStretch(1)
        return row1, row2

    def _build_legend(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        for color, label in [
            (self.pal["text3"], "API"),
            (self.pal["green"], "manual"),
            (self.pal["accent"], "both"),
            (self.pal["red"], "excluded"),
        ]:
            li = QHBoxLayout()
            li.setSpacing(5)
            sw = QLabel("\u25cf")
            sw.setStyleSheet("color:%s;font-size:8px;" % color)
            tx = QLabel(label)
            tx.setStyleSheet("color:%s;font-size:11px;" % self.pal["text3"])
            li.addWidget(sw)
            li.addWidget(tx)
            row.addLayout(li)
        row.addStretch(1)
        return row

    def refresh(self):
        self._apply_auth_state()
        self._update_statusbar()

    def highlight_tab(self, idx):
        pass

    def _start_status_timer(self):
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_statusbar)
        self._status_timer.start(1000)


class _Segment(QWidget):
    """All / Active / Moderators segmented control (syncs a QTabWidget)."""

    def __init__(self, tab_widget, pal):
        super(_Segment, self).__init__()
        self._tabs = tab_widget
        self._pal = pal
        tab_widget.setObjectName("viewersTabs")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self._btns = []
        for i, label in enumerate(["All", "Active", "Moderators"]):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self._pick(i))
            self._btns.append(b)
            h.addWidget(b, 1)
        self._paint()
        tab_widget.currentChanged.connect(self._on_tab_changed)
        # The segment control replaces the native tab bar — hide it so the
        # two don't duplicate. The tab pages themselves stay functional.
        tab_widget.tabBar().setVisible(False)

    def _pick(self, i):
        self._tabs.setCurrentIndex(i)

    def _on_tab_changed(self, i):
        self._paint()

    def _paint(self):
        cur = self._tabs.currentIndex()
        for i, b in enumerate(self._btns):
            if i == cur:
                b.setStyleSheet(
                    "QPushButton{background:%s;color:%s;font-weight:600;"
                    "border:1px solid transparent;border-radius:6px;padding:5px 4px;}"
                    % (self._pal["surface"], self._pal["text"]))
            else:
                b.setStyleSheet(
                    "QPushButton{background:transparent;color:%s;font-weight:500;"
                    "border:1px solid transparent;border-radius:6px;padding:5px 4px;}"
                    "QPushButton:hover{color:%s;}"
                    % (self._pal["text2"], self._pal["text"]))


class SidebarTwitchView(TwitchThemedBase):
    """Design 1: topbar + stat strip + two-column (chat | viewers) + status bar."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(SidebarTwitchView, self).__init__(parent, tab_widget, twitch_tab)
        self.pal = palette_for(getattr(parent, "theme", "sidebar"))
        self._build()

    def _build(self):
        tt = self.twitch_tab
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # topbar
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(12)
        title = QLabel("Twitch")
        title.setObjectName("topTitle")
        th.addWidget(title)
        crumb = QLabel("/ connection \u00b7 chat \u00b7 viewers")
        crumb.setObjectName("crumb")
        th.addWidget(crumb)
        th.addStretch(1)
        th.addWidget(tt.disconnect_button)
        tt.connect_button.setObjectName("primaryBtn")
        th.addWidget(tt.connect_button)
        root.addWidget(top)

        # stat strip
        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(18, 16, 18, 0)
        cv.setSpacing(14)
        cv.addWidget(self._build_stat_strip())

        # two columns
        cols = QWidget()
        ch = QHBoxLayout(cols)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(14)

        colL = QWidget()
        lv = QVBoxLayout(colL)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(14)

        # auth panel
        ap, av = self._panel("Authentication", "Twitch OAuth")
        arow = QHBoxLayout()
        arow.setSpacing(10)
        arow.addWidget(self._build_auth_pill())
        arow.addStretch(1)
        tt.auth_button.setObjectName("primaryBtn")
        arow.addWidget(tt.auth_button)
        arow.addWidget(tt.token_button)
        av.addLayout(arow)
        lv.addWidget(ap)

        # connection panel
        cp, cvv = self._panel("Connection", "chat channel")
        crow = QHBoxLayout()
        crow.setSpacing(10)
        tt.channel_input.setMinimumWidth(220)
        crow.addWidget(tt.channel_input)
        crow.addWidget(tt.check_connection_button)
        crow.addStretch(1)
        cvv.addLayout(crow)
        lv.addWidget(cp)

        # chat panel
        chp, chv = self._panel("Chat", "live preview")
        chv.addWidget(tt.chat_display, 1)
        comp = QHBoxLayout()
        comp.setSpacing(8)
        comp.addWidget(tt.message_input, 1)
        tt.send_button.setObjectName("primaryBtn")
        comp.addWidget(tt.send_button)
        chv.addLayout(comp)
        lv.addWidget(chp, 1)

        colR = QWidget()
        rv = QVBoxLayout(colR)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # viewers panel
        vp, vv = self._panel("Viewers", "total")
        self._seg = _Segment(tt.viewers_tabs, self.pal)
        vv.addWidget(self._seg)
        vv.addWidget(tt.viewers_tabs, 1)
        vv.addLayout(self._build_legend())
        rrow = QHBoxLayout()
        rrow.setSpacing(10)
        rrow.addWidget(tt.refresh_viewers_button)
        auto = QLabel("Auto:")
        auto.setStyleSheet("color:%s;font-size:12px;" % self.pal["text3"])
        rrow.addWidget(auto)
        rrow.addWidget(tt.update_frequency)
        rrow.addStretch(1)
        rrow.addWidget(tt.last_update_label)
        vv.addLayout(rrow)
        rv.addWidget(vp, 1)

        ch.addWidget(colL, 155)
        ch.addWidget(colR, 100)
        cv.addWidget(cols, 1)
        root.addWidget(_scroll_wrap(content), 1)

        root.addWidget(self._build_status_bar())

        self._start_status_timer()


class SpreadsheetTwitchView(TwitchThemedBase):
    """Design 9: brand topbar + toolbar (auth/channel/actions) + chat|viewers + status bar."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(SpreadsheetTwitchView, self).__init__(parent, tab_widget, twitch_tab)
        self.pal = palette_for(getattr(parent, "theme", "spreadsheet"))
        self._build()

    def _build(self):
        tt = self.twitch_tab
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # topbar (brand + connect/disconnect)
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(56)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(10)
        th.addWidget(LogoBadge(self.pal))
        name = QLabel("Command Editor")
        name.setStyleSheet("font-size:14px;font-weight:600;color:%s;" % self.pal["text"])
        th.addWidget(name)
        th.addStretch(1)
        th.addWidget(tt.disconnect_button)
        tt.connect_button.setObjectName("primaryBtn")
        th.addWidget(tt.connect_button)
        root.addWidget(top)

        # toolbar
        tb = _overflow_toolbar(46)
        tbh = tb
        tbh.addWidget(self._build_auth_pill())
        chan = QLabel("channel")
        chan.setStyleSheet("color:%s;font-size:12px;" % self.pal["text2"])
        tbh.addWidget(chan)
        tt.channel_input.setFixedWidth(150)
        tbh.addWidget(_held(tt.channel_input))
        sep = QFrame()
        sep.setFixedSize(1, 22)
        sep.setStyleSheet("background:%s;" % self.pal["border"])
        tbh.addWidget(sep)
        tbh.addWidget(_held(tt.check_connection_button))
        tbh.addWidget(_held(tt.auth_button))
        tbh.addWidget(_held(tt.token_button))
        _toolbar_stretch(tb)
        self._tb_stats = QLabel("")
        self._tb_stats.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text3"])
        tbh.addWidget(self._tb_stats)
        root.addWidget(tb)

        # body: chat | viewers
        body = QWidget()
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)

        chatcol = QWidget()
        chcv = QVBoxLayout(chatcol)
        chcv.setContentsMargins(0, 0, 0, 0)
        chcv.setSpacing(0)
        chatcol.setStyleSheet("border-right:1px solid %s;" % self.pal["border"])
        chcv.addWidget(tt.chat_display, 1)
        comp = QFrame()
        comp.setStyleSheet("background:%s;border-top:1px solid %s;" % (self.pal["surface2"], self.pal["border"]))
        compv = QHBoxLayout(comp)
        compv.setContentsMargins(14, 10, 14, 10)
        compv.setSpacing(8)
        compv.addWidget(tt.message_input, 1)
        tt.send_button.setObjectName("primaryBtn")
        compv.addWidget(tt.send_button)
        chcv.addWidget(comp)
        bh.addWidget(chatcol, 155)

        viewcol = QWidget()
        vcv = QVBoxLayout(viewcol)
        vcv.setContentsMargins(0, 0, 0, 0)
        vcv.setSpacing(0)
        self._seg = _Segment(tt.viewers_tabs, self.pal)
        self._seg.setContentsMargins(14, 10, 14, 10)
        vcv.addWidget(self._seg)
        vcv.addWidget(tt.viewers_tabs, 1)
        vcv.addLayout(self._build_legend())
        foot = QFrame()
        foot.setStyleSheet("background:%s;border-top:1px solid %s;" % (self.pal["surface2"], self.pal["border"]))
        footv = QHBoxLayout(foot)
        footv.setContentsMargins(14, 8, 14, 8)
        footv.setSpacing(8)
        footv.addWidget(tt.refresh_viewers_button)
        auto = QLabel("Auto:")
        auto.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text3"])
        footv.addWidget(auto)
        footv.addWidget(tt.update_frequency)
        footv.addStretch(1)
        footv.addWidget(tt.last_update_label)
        vcv.addWidget(foot)
        bh.addWidget(viewcol, 100)

        root.addWidget(_scroll_wrap(body), 1)
        root.addWidget(self._build_status_bar())

        self._start_status_timer()

    def _update_statusbar(self):
        super(SpreadsheetTwitchView, self)._update_statusbar()
        tt = self.twitch_tab
        live = getattr(tt, "currently_live", False)
        self._tb_stats.setText(
            "%s \u00b7 %s active \u00b7 %s all \u00b7 %s mods" % (
                "Live" if live else "Offline",
                len(getattr(tt, "active_users", []) or []),
                self.all_viewers_count.text().split(":")[-1].strip(),
                len(getattr(tt, "moderators_list", []) or [])))


# ---------------------------------------------------------------------------
# Generic themed tab wrapper (Design 1 / Design 9)
#
# For the tabs that don't have a bespoke themed layout yet, this wraps the
# ORIGINAL tab widget in a themed frame (topbar with title + the original
# content). The original tab is re-parented into the wrapper; its internal
# widgets and logic are untouched, so everything keeps working. Switching back
# to classic re-parents the original tab into the tab widget.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sys.Commands in the sidebar layouts: master list + detail editor, like the
# themed Commands view (it used to be the classic table in a themed frame).
# All changes go through SysCommandsTab.set_field / duplicate_at / remove_at,
# so the classic tab, system_commands.json and the bot stay in sync.
# ---------------------------------------------------------------------------

class SysCommandsView(QWidget):
    TEXT_FIELDS = ("command_name", "info", "group", "random_group",
                   "picked_command_response", "default_group")

    def __init__(self, editor, sys_tab):
        super(SysCommandsView, self).__init__(editor)
        self.editor = editor
        self.tab = sys_tab
        self.pal = palette_for(getattr(editor, "theme", "sidebar"))
        self._row = -1
        self._guard = False
        self._pending = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._flush)
        self._make_top()
        self._build()
        self.refresh()

    @property
    def cmds(self):
        return self.tab.system_commands

    # -- topbar buttons (placed by ThemedTabView) ------------------------
    def topbar_widgets(self):
        return [self.search_edit, self.dup_btn]

    def _make_top(self):
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchBox")
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.setClearButtonEnabled(True)
        _shrinkable(self.search_edit, 200, 90)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.setToolTip("Create a copy of this command under another name "
                                "(e.g. !money as an alias of !points)")
        self.dup_btn.clicked.connect(self._duplicate)

    # -- construction -----------------------------------------------------
    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("masterPanel")
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(300)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        self.list = QListWidget()
        self.list.setObjectName("masterList")
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(MasterDelegate(self.pal, self.list))
        self.list.itemSelectionChanged.connect(self._on_selected)
        pv.addWidget(self.list, 1)
        h.addWidget(panel, 0)

        scroll = QScrollArea()
        scroll.setObjectName("detailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        d = QFrame()
        d.setObjectName("detailPanel")
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        tt = QVBoxLayout()
        tt.setSpacing(2)
        self.d_title = QLabel("")
        self.d_title.setObjectName("dTitle")
        self.d_sub = QLabel("")
        self.d_sub.setObjectName("dSub")
        tt.addWidget(self.d_title)
        tt.addWidget(self.d_sub)
        head.addLayout(tt)
        head.addStretch(1)
        lab = QLabel("Enabled")
        lab.setObjectName("switchDesc")
        head.addWidget(lab)
        self.f_enabled = ToggleSwitch(self.pal)
        self.f_enabled.toggled.connect(lambda on: self._edit("enabled", bool(on), now=True))
        head.addWidget(self.f_enabled)
        self.rm_btn = QPushButton()
        self.rm_btn.setObjectName("dangerBtn")
        self.rm_btn.setIcon(make_icon("trash", self.pal["red"]))
        self.rm_btn.setToolTip("Remove this duplicate (originals can't be removed)")
        self.rm_btn.clicked.connect(self._remove)
        head.addWidget(self.rm_btn)
        v.addLayout(head)

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(6)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)

        def lab_(t):
            x = QLabel(t)
            x.setObjectName("fieldLabel")
            return x

        self.f_name = QLineEdit()
        self.f_name.textChanged.connect(lambda t: self._edit("command_name", t))
        self.f_group = QLineEdit()
        self.f_group.textChanged.connect(lambda t: self._edit("group", t))
        g.addWidget(lab_("Command"), 0, 0)
        g.addWidget(lab_("Group"), 0, 1)
        g.addWidget(self.f_name, 1, 0)
        g.addWidget(self.f_group, 1, 1)

        self.f_perm = QComboBox()
        self.f_perm.addItems(PERMISSIONS)
        self.f_perm.currentTextChanged.connect(lambda t: self._edit("permission", t, now=True))
        self.f_usage = QComboBox()
        self.f_usage.addItems(USAGES)
        self.f_usage.currentTextChanged.connect(lambda t: self._edit("usage", t, now=True))
        g.addWidget(lab_("Permission"), 2, 0)
        g.addWidget(lab_("Usage"), 2, 1)
        g.addWidget(self.f_perm, 3, 0)
        g.addWidget(self.f_usage, 3, 1)

        self.f_cd = QSpinBox()
        self.f_cd.setRange(0, 3600)
        self.f_cd.setSuffix(" min")
        self.f_cd.setSpecialValueText("none")
        self.f_cd.setToolTip("Global cooldown in MINUTES")
        self.f_cd.valueChanged.connect(lambda val: self._edit("cooldown", int(val)))
        self.f_ucd = QSpinBox()
        self.f_ucd.setRange(0, 3600)
        self.f_ucd.setSuffix(" min")
        self.f_ucd.setSpecialValueText("none")
        self.f_ucd.setToolTip("Per-viewer cooldown in MINUTES")
        self.f_ucd.valueChanged.connect(lambda val: self._edit("user_cooldown", int(val)))
        g.addWidget(lab_("Cooldown"), 4, 0)
        g.addWidget(lab_("User cooldown"), 4, 1)
        g.addWidget(self.f_cd, 5, 0)
        g.addWidget(self.f_ucd, 5, 1)

        self.f_cost = QSpinBox()
        self.f_cost.setRange(0, 1000000)
        self.f_cost.setSpecialValueText("free")
        self.f_cost.valueChanged.connect(lambda val: self._edit("cost", int(val)))
        g.addWidget(lab_("Cost (points)"), 6, 0)
        g.addWidget(self.f_cost, 7, 0)

        self.f_info = QLineEdit()
        self.f_info.textChanged.connect(lambda t: self._edit("info", t))
        g.addWidget(lab_("Info"), 8, 0, 1, 2)
        g.addWidget(self.f_info, 9, 0, 1, 2)
        v.addLayout(g)

        # !random / !volume specific settings
        self.extra_card = QFrame()
        self.extra_card.setObjectName("settingsCard")
        ev = QGridLayout(self.extra_card)
        ev.setContentsMargins(16, 12, 16, 12)
        ev.setHorizontalSpacing(14)
        ev.setVerticalSpacing(6)
        self.extra_title = QLabel("")
        self.extra_title.setObjectName("sectionTitle")
        ev.addWidget(self.extra_title, 0, 0, 1, 2)
        self.l_random = lab_("Random group (ALL = any group)")
        self.f_random = QComboBox()
        self.f_random.setEditable(True)
        self.f_random.setInsertPolicy(QComboBox.NoInsert)
        self.f_random.editTextChanged.connect(lambda t: self._edit("random_group", t))
        self.f_show_picked = QCheckBox("Show the picked command in chat")
        self.f_show_picked.toggled.connect(lambda on: self._edit("show_picked_command", bool(on), now=True))
        self.l_picked = lab_("Picked command message ({command} = picked command)")
        self.f_picked = QLineEdit()
        self.f_picked.setPlaceholderText("Picked {command}.")
        self.f_picked.textChanged.connect(lambda t: self._edit("picked_command_response", t))
        self.l_default = lab_("Default group (when !volume is used without a group)")
        self.f_default = QComboBox()
        self.f_default.setEditable(True)
        self.f_default.setInsertPolicy(QComboBox.NoInsert)
        self.f_default.editTextChanged.connect(lambda t: self._edit("default_group", t))
        ev.addWidget(self.l_random, 1, 0)
        ev.addWidget(self.f_random, 2, 0)
        ev.addWidget(self.f_show_picked, 2, 1)
        ev.addWidget(self.l_picked, 3, 0, 1, 2)
        ev.addWidget(self.f_picked, 4, 0, 1, 2)
        ev.addWidget(self.l_default, 5, 0, 1, 2)
        ev.addWidget(self.f_default, 6, 0)
        v.addWidget(self.extra_card)

        self.error = QLabel("")
        self.error.setStyleSheet("color: %s;" % self.pal["red"])
        self.error.setWordWrap(True)
        v.addWidget(self.error)
        hint = QLabel("Originals are built into the bot: their name is fixed, everything else can "
                      "be changed. Use Duplicate to add the same command under another name.")
        hint.setObjectName("switchDesc")
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch(1)
        scroll.setWidget(d)
        h.addWidget(scroll, 1)
        self.fields = [self.f_name, self.f_group, self.f_perm, self.f_usage, self.f_cd,
                       self.f_ucd, self.f_cost, self.f_info, self.f_enabled, self.rm_btn]

    # -- list ---------------------------------------------------------------
    def _row_data(self, cmd):
        dup = cmd.get("is_duplicate", False)
        meta = [cmd.get("permission", "")]
        if cmd.get("cooldown"):
            meta.append("%s min" % cmd.get("cooldown"))
        if cmd.get("cost"):
            meta.append("%s pts" % cmd.get("cost"))
        meta.append(("copy of " + cmd.get("command", "")) if dup else (cmd.get("info", "") or ""))
        return {"Command": self.tab.display_name(cmd), "Group": "COPY" if dup else "ORIGINAL",
                "Enabled": bool(cmd.get("enabled", True)),
                "_meta": " · ".join(m for m in meta if m)}

    def refresh(self, select_row=None):
        self._flush()
        if select_row is None:
            select_row = self._row
        needle = self.search_edit.text().strip().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for i, cmd in enumerate(self.cmds):
            hay = " ".join(str(cmd.get(k, "")) for k in
                           ("command", "command_name", "info", "group", "permission")).lower()
            if needle and needle not in hay:
                continue
            it = QListWidgetItem(self.tab.display_name(cmd))
            it.setData(Qt.UserRole, self._row_data(cmd))
            it.setData(Qt.UserRole + 1, i)
            it.setSizeHint(QSize(0, 54))
            self.list.addItem(it)
        self.list.blockSignals(False)
        groups = _known_groups(getattr(self.editor, "commands", []), self.editor)
        for combo, first in ((self.f_random, ["ALL"]), (self.f_default, [])):
            combo.blockSignals(True)
            text = combo.currentText()
            combo.clear()
            combo.addItems(first + [x for x in groups if x != "ALL"])
            combo.setEditText(text)
            combo.blockSignals(False)
        if not self.cmds:
            self._populate(-1)
            return
        if select_row is None or not (0 <= select_row < len(self.cmds)):
            select_row = 0
        self._select(select_row)
        self._populate(select_row)

    def _select(self, row):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole + 1) == row:
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                break
        else:
            self.list.clearSelection()
        self.list.blockSignals(False)

    def _update_item(self, row):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole + 1) == row:
                it.setData(Qt.UserRole, self._row_data(self.cmds[row]))
                it.setText(self.tab.display_name(self.cmds[row]))
                break

    def _on_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        row = items[0].data(Qt.UserRole + 1)
        if isinstance(row, int) and row != self._row:
            self._flush()
            self._populate(row)

    # -- detail ---------------------------------------------------------------
    def _populate(self, row):
        ok = 0 <= row < len(self.cmds)
        self._row = row if ok else -1
        for w in self.fields:
            w.setEnabled(ok)
        self.error.setText("")
        if not ok:
            self.d_title.setText("No command selected")
            self.d_sub.setText("")
            self.extra_card.hide()
            self.dup_btn.setEnabled(False)
            return
        cmd = self.cmds[row]
        dup = cmd.get("is_duplicate", False)
        self._guard = True
        try:
            self.f_name.setText(self.tab.display_name(cmd))
            self.f_name.setReadOnly(not dup)
            self.f_name.setToolTip("" if dup else "The name of an original command is fixed. "
                                   "Duplicate it to use another name.")
            self.f_group.setText(cmd.get("group", ""))
            for combo, value in ((self.f_perm, cmd.get("permission", "Everyone")),
                                 (self.f_usage, cmd.get("usage", "Chat"))):
                if combo.findText(value) < 0:
                    combo.addItem(value)
                combo.setCurrentText(value)
            self.f_cd.setValue(int(cmd.get("cooldown", 0) or 0))
            self.f_ucd.setValue(int(cmd.get("user_cooldown", 0) or 0))
            self.f_cost.setValue(int(cmd.get("cost", 0) or 0))
            self.f_info.setText(cmd.get("info", ""))
            self.f_enabled.setChecked(bool(cmd.get("enabled", True)))
            base = cmd.get("command", "")
            name = self.tab.display_name(cmd)
            is_random = base == "!random" or name.startswith("!random")
            is_volume = base == "!volume" or name.startswith("!volume")
            for w in (self.l_random, self.f_random, self.f_show_picked, self.l_picked, self.f_picked):
                w.setVisible(is_random)
            for w in (self.l_default, self.f_default):
                w.setVisible(is_volume)
            self.extra_card.setVisible(is_random or is_volume)
            self.extra_title.setText("!random settings" if is_random else "!volume settings")
            self.f_random.setEditText(cmd.get("random_group", "ALL"))
            self.f_show_picked.setChecked(bool(cmd.get("show_picked_command", True)))
            self.f_picked.setText(cmd.get("picked_command_response", "Picked {command}."))
            self.f_default.setEditText(cmd.get("default_group", "SONG"))
        finally:
            self._guard = False
        self.rm_btn.setVisible(dup)
        self.dup_btn.setEnabled(not dup)
        self._update_header()

    def _update_header(self):
        if self._row < 0:
            return
        cmd = self.cmds[self._row]
        self.d_title.setText(self.tab.display_name(cmd))
        if cmd.get("is_duplicate", False):
            sub = "copy of %s" % cmd.get("command", "")
        else:
            sub = "built-in command"
        if not cmd.get("enabled", True):
            sub += " · disabled"
        self.d_sub.setText(sub)

    # -- edits ----------------------------------------------------------------
    def _edit(self, field, value, now=False):
        if self._guard or self._row < 0:
            return
        self._pending[field] = value
        if now or field not in self.TEXT_FIELDS:
            self._flush()
        else:
            self._timer.start()

    def _flush(self):
        self._timer.stop()
        if not self._pending or self._row < 0:
            self._pending = {}
            return
        pending, self._pending = self._pending, {}
        errors = []
        for field, value in pending.items():
            err = self.tab.set_field(self._row, field, value)
            if err:
                errors.append(err)
        self.error.setText(" ".join(errors))
        self._update_item(self._row)
        self._update_header()

    def _duplicate(self):
        self._flush()
        res = self.tab.duplicate_at(self._row)
        if isinstance(res, str):
            self.error.setText(res)
            return
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.refresh(select_row=res)
        self.f_name.setFocus()
        self.f_name.selectAll()

    def _remove(self):
        self._flush()
        if self.tab.remove_at(self._row, self):
            self.refresh(select_row=max(0, self._row - 1))

    def showEvent(self, event):
        # data may have been changed in the classic tab / by a restore
        self.refresh()
        super(SysCommandsView, self).showEvent(event)

    def highlight_tab(self, idx):
        pass


class ThemedTabView(QWidget):
    """Themed frame around an original tab widget (topbar + content).

    With `content`, that widget is shown instead of the original tab (which
    is kept, hidden, so switching back to classic can restore it)."""

    def __init__(self, parent, tab_widget, original_tab, title, subtitle="", content=None):
        super(ThemedTabView, self).__init__(parent)
        self.editor = parent
        self.tab_widget = tab_widget
        self.original_tab = original_tab
        self.content = content
        self.pal = palette_for(self.editor.theme)
        self._build(title, subtitle)

    def _build(self, title, subtitle):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(12)
        t = QLabel(title)
        t.setObjectName("topTitle")
        th.addWidget(t)
        if subtitle:
            c = QLabel(subtitle)
            c.setObjectName("crumb")
            th.addWidget(c)
        th.addStretch(1)
        if self.content is not None and hasattr(self.content, "topbar_widgets"):
            for w in self.content.topbar_widgets():
                th.addWidget(w)
        root.addWidget(top)

        body = QWidget()
        body.setObjectName("themedBody")
        body.setStyleSheet("QWidget#themedBody{background:%s;}" % self.pal["bg"])
        bv = QVBoxLayout(body)
        bv.setSpacing(0)
        # Re-parent the original tab into the themed body. No blanket
        # "QWidget{background}" on it any more: that painted every label and
        # input of the tab and survived theme switches.
        self.original_tab.setParent(body)
        self.original_tab.setStyleSheet("")
        if self.content is not None:
            bv.setContentsMargins(0, 0, 0, 0)
            self.original_tab.hide()
            bv.addWidget(self.content, 1)
        else:
            bv.setContentsMargins(16, 14, 16, 14)
            self.original_tab.show()
            bv.addWidget(self.original_tab, 1)
        root.addWidget(_scroll_wrap(body), 1)

    def highlight_tab(self, idx):
        pass
