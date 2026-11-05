# -*- coding: utf-8 -*-
"""Theme system for Command Editor.

Three themes:
  * classic     - native Qt look (no QSS, the original appearance)
  * sidebar     - Design 1: Linear/Notion sidebar + master-detail Commands
  * spreadsheet - Design 9: dense inline-edit table + toolbar + status bar

The theme is stored in config.json under the "theme" key. Switching themes
re-styles the whole app via QSS and swaps the Commands tab for a themed view.
All other tabs keep their widgets and are only re-styled.

Python 3.8 / PyQt5 (Qt5) only. No walrus, no PEP 585/604 generics.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QAbstractButton,
    QStyledItemDelegate, QTextEdit, QStyle,
)
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPixmap, QIcon,
    QLinearGradient, QPainterPath, QPolygonF,
)


THEMES = ("classic", "sidebar", "spreadsheet")
THEME_LABELS = {
    "classic": "Classic (native)",
    "sidebar": "Sidebar (Design 1)",
    "spreadsheet": "Spreadsheet (Design 9)",
}

FONT_FAMILY = "Segoe UI"


# ---------------------------------------------------------------------------
# Palettes (hex) for the two themed looks
# ---------------------------------------------------------------------------

PALETTES = {
    "sidebar": {
        "bg": "#F7F7F8", "surface": "#FFFFFF", "surface2": "#FAFAFB",
        "surface3": "#F0F0F2", "border": "#E7E7EA", "border_strong": "#D6D6DB",
        "text": "#1A1A1E", "text2": "#62626B", "text3": "#9C9CA5",
        "accent": "#5B5BD6", "accent_press": "#4A4AC4",
        "accent_soft": "rgba(91,91,214,0.10)",
        "green": "#16A34A", "red": "#DC2626", "amber": "#D97706",
    },
    "spreadsheet": {
        "bg": "#F1F3F6", "surface": "#FFFFFF", "surface2": "#F7F9FC",
        "surface3": "#EDF0F5", "border": "#DDE2EA", "border_strong": "#CBD2DE",
        "text": "#1A1D24", "text2": "#5A6170", "text3": "#98A0AE",
        "accent": "#0891B2", "accent_press": "#0E7490",
        "accent_soft": "rgba(8,145,178,0.10)",
        "green": "#16A34A", "red": "#DC2626", "amber": "#D97706",
    },
}


# ---------------------------------------------------------------------------
# QSS
# ---------------------------------------------------------------------------

def _base_qss(c):
    """Shared QSS for the two themed looks (palette + common widgets)."""
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
QPushButton:hover { background: %(surface2)s; }
QPushButton:pressed { background: %(surface3)s; }
QPushButton:disabled { color: %(text3)s; }
QPushButton#primaryBtn { background: %(accent)s; border: 1px solid %(accent)s; color: #ffffff; }
QPushButton#primaryBtn:hover { background: %(accent_press)s; }
QPushButton#primaryBtn:pressed { background: %(accent_press)s; }

QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background: %(surface2)s; border: 1px solid %(border)s;
    border-radius: 7px; padding: 7px 10px; color: %(text)s; selection-background-color: %(accent)s;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid %(accent)s; background: %(surface)s;
}
QLineEdit#searchBox { background: %(surface3)s; border: 1px solid transparent; border-radius: 7px; padding: 7px 11px; }
QLineEdit#searchBox:focus { background: %(surface)s; border: 1px solid %(accent)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(border)s;
    selection-background-color: %(accent)s; selection-color: #ffffff;
}

QGroupBox {
    border: 1px solid %(border)s; border-radius: 10px;
    margin-top: 12px; padding: 14px 12px 12px 12px;
    font-weight: 600; color: %(text2)s;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: %(text2)s; }

QTableWidget, QTableView {
    background: %(surface)s; alternate-background-color: %(surface2)s;
    gridline-color: %(border)s; border: 1px solid %(border)s; border-radius: 8px;
}
QHeaderView::section {
    background: %(surface2)s; color: %(text3)s; border: none;
    border-bottom: 1px solid %(border)s; padding: 8px 10px;
    font-weight: 600; font-size: 11px;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: %(accent_soft)s; color: %(accent_press)s;
}
QListWidget { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; }
QListWidget::item { padding: 0; margin: 0; }
QListWidget::item:selected { background: transparent; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 6px; min-height: 24px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: %(text3)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 6px; min-width: 24px; margin: 2px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QCheckBox { spacing: 8px; color: %(text)s; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid %(border_strong)s; background: %(surface)s; }
QCheckBox::indicator:checked { background: %(accent)s; border: 1px solid %(accent)s; }

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
""" % dict(c, font=FONT_FAMILY)


def _sidebar_qss(c):
    return _base_qss(c) + """
QFrame#sidebarPanel { background: %(surface2)s; border-right: 1px solid %(border)s; }
QPushButton#navBtn {
    text-align: left; background: transparent; border: none; border-radius: 7px;
    padding: 8px 10px; color: %(text2)s; font-weight: 500;
}
QPushButton#navBtn:hover { background: %(surface3)s; color: %(text)s; }
QPushButton#navBtnActive { background: %(accent_soft)s; color: %(accent_press)s; font-weight: 600; }
QFrame#topbar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
QFrame#masterPanel { background: %(surface)s; border-right: 1px solid %(border)s; }
QListWidget#masterList { border: none; background: %(surface)s; }
QFrame#detailPanel { background: %(surface)s; }
QFrame#switchRow { border-bottom: 1px solid %(border)s; }
QFrame#dIco { background: %(accent_soft)s; border-radius: 10px; }
QLabel#dIcoText { color: %(accent_press)s; font-size: 15px; font-weight: 700; }
QFrame#panel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#panel .panelHead { color: %(text)s; font-size: 12.5px; font-weight: 600; }
QFrame#panel .panelHint { color: %(text3)s; font-size: 11px; }
QFrame#statStrip { background: %(surface2)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#statBox { border-right: 1px solid %(border)s; }
QFrame#statBoxLast { border-right: none; }
QFrame#statBox QLabel { color: %(text3)s; font-size: 11px; }
QFrame#statBox QLabel#statVal { color: %(text)s; font-size: 16px; font-weight: 600; }
QFrame#authPill { border-radius: 12px; }
QFrame#authPill QLabel { font-size: 12px; font-weight: 500; }
QFrame#statusbar QLabel#statusLabel { color: %(text2)s; font-size: 11.5px; }
QLabel#sideStatus { color: %(text2)s; font-size: 12px; }
QTabWidget#viewersTabs::pane { border: none; background: transparent; }
QTabWidget#viewersTabs QTabBar { background: transparent; }
""" % c


def _spreadsheet_qss(c):
    return _base_qss(c) + """
QFrame#toolbar { background: %(surface2)s; border-bottom: 1px solid %(border)s; }
QFrame#topbar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
QPushButton#toolBtn {
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 6px 10px; color: %(text2)s; font-weight: 500;
}
QPushButton#toolBtn:hover { background: %(surface3)s; color: %(text)s; }
QFrame#statusbar { background: %(surface2)s; border-top: 1px solid %(border)s; }
QTableWidget#denseTable { gridline-color: %(border)s; }
QTableWidget#denseTable::item { padding: 0; }
QFrame#panel { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#panel .panelHead { color: %(text)s; font-size: 12.5px; font-weight: 600; }
QFrame#panel .panelHint { color: %(text3)s; font-size: 11px; }
QFrame#authPill { border-radius: 12px; }
QFrame#authPill QLabel { font-size: 12px; font-weight: 500; }
QFrame#statusbar QLabel#statusLabel { color: %(text2)s; font-size: 11.5px; }
QTabWidget#viewersTabs::pane { border: none; background: transparent; }
QTabWidget#viewersTabs QTabBar { background: transparent; }
""" % c


def qss_for(theme, palette):
    if theme == "sidebar":
        return _sidebar_qss(palette)
    if theme == "spreadsheet":
        return _spreadsheet_qss(palette)
    # classic: minimal, preserve native look
    return """
QScrollBar:vertical { width: 16px; background: rgba(0,0,0,0.1); }
QScrollBar:horizontal { height: 16px; background: rgba(0,0,0,0.1); }
"""


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
    if g == "VIP":
        return "amber"
    if g == "MUSIC":
        return "teal"
    if g in ("MODS", "MODERATOR", "MOD"):
        return "red"
    return "neutral"


def pill_colors(kind, pal):
    if kind == "accent":
        return pal["accent_soft"], pal["accent_press"]
    if kind == "amber":
        return "rgba(217,119,6,0.12)", pal["amber"]
    if kind == "teal":
        return "rgba(8,145,178,0.12)", pal["accent"]
    if kind == "red":
        return "rgba(220,38,38,0.12)", pal["red"]
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
        grad.setColorAt(1.0, QColor("#8B5CF6" if self.pal is PALETTES["sidebar"] else "#06B6D4"))
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

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.pal["green"] if on else self.pal["surface3"]))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2.0, h / 2.0)
        r = h - 4
        x = (w - r - 2) if on else 2
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, 2, r, r))
        p.end()


def make_icon(name, color, size=17):
    """Draw a simple stroke icon into a QIcon (no image assets)."""
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
        import math
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
        # stacked diamonds (group/settings)
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
        # settings cog: center hub + 8 spokes
        cx, cy = s / 2, s / 2
        p.drawEllipse(QRectF(cx - 2.2, cy - 2.2, 4.4, 4.4))
        import math
        for i in range(8):
            ang = i * math.pi / 4
            x1 = cx + 4.2 * math.cos(ang)
            y1 = cy + 4.2 * math.sin(ang)
            x2 = cx + 6.3 * math.cos(ang)
            y2 = cy + 6.3 * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Sidebar (Design 1) Commands view
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

        cmd = index.data(Qt.UserRole)
        if not isinstance(cmd, dict):
            painter.restore()
            return

        name = cmd.get("Command", "")
        group = cmd.get("Group", "")
        enabled = cmd.get("Enabled", True)
        perm = cmd.get("Permission", "")
        cd = cmd.get("Cooldown", 0)
        vol = int(round(float(cmd.get("Volume", 0)) * 100))

        # status dot
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.pal["green"] if enabled else self.pal["text3"]))
        painter.drawEllipse(QRectF(rect.left() + 14, rect.top() + 15, 7, 7))

        # command name
        painter.setPen(QColor(self.pal["accent_press"] if selected else self.pal["text"]))
        painter.setFont(_ui_font(13, bold=True))
        name_rect = QRectF(rect.left() + 30, rect.top() + 8,
                           rect.width() - 30 - 90, 18)
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

        # group pill (right)
        kind = group_pill_kind(group)
        bg, fg = pill_colors(kind, self.pal)
        painter.setFont(_ui_font(10, bold=True))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(group) if hasattr(fm, "horizontalAdvance") else fm.width(group)
        pw = tw + 16
        px = rect.right() - 14 - pw
        py = rect.top() + 11
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba_color(bg))
        painter.drawRoundedRect(QRectF(px, py, pw, 16), 8, 8)
        painter.setPen(QColor(fg))
        painter.drawText(QRectF(px, py, pw, 16), Qt.AlignCenter, group)

        # meta line
        painter.setPen(QColor(self.pal["text3"]))
        painter.setFont(_ui_font(11))
        meta = "%s · %ss · %d%%" % (perm, cd, vol)
        painter.drawText(QRectF(rect.left() + 30, rect.top() + 30,
                                rect.width() - 44, 16),
                         Qt.AlignVCenter | Qt.AlignLeft, meta)
        painter.restore()


# ---------------------------------------------------------------------------
# Sidebar (Design 1) Commands view
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Persistent sidebar navigation (Design 1)
#
# A standalone left nav rail (brand + sectioned tab buttons + status footer).
# The main window shows it on EVERY tab in the sidebar theme; the Commands
# view reuses the same class so the look is identical.
# ---------------------------------------------------------------------------

class SidebarNav(QFrame):
    """Left navigation rail. NAV items map to main-tab indices."""

    NAV = [
        ("Manage", [
            (0, "Commands", "lines"),
            (7, "Queue Control", "chevron"),
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
            (9, "History", "lines"),
            (10, "Backups", "shield"),
            (8, "About", "info"),
            (11, "Settings", "gear"),
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
        self.setFixedWidth(220)
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

        for section, items in self.NAV:
            lbl = QLabel(section.upper())
            lbl.setObjectName("navSection")
            lbl.setContentsMargins(10, 12, 0, 4)
            v.addWidget(lbl)
            for idx, label, icon in items:
                b = QPushButton("  " + label)
                b.setObjectName("navBtn")
                b.setIcon(make_icon(icon, self.pal["text2"]))
                b.setIconSize(QSize(17, 17))
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, i=idx: self._go_tab(i))
                self._nav_buttons[idx] = b
                v.addWidget(b)

        v.addStretch(1)
        status = QLabel("\u25cf  main_channel \u00b7 live")
        status.setObjectName("sideStatus")
        status.setStyleSheet("color: %s; font-size: 12px; padding: 8px;" % self.pal["text2"])
        v.addWidget(status)

        if self.tab_widget is not None:
            self.tab_widget.currentChanged.connect(self.highlight_tab)

    def _go_tab(self, idx):
        if self.tab_widget is not None and 0 <= idx < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(idx)

    def highlight_tab(self, idx):
        for i, b in self._nav_buttons.items():
            b.setObjectName("navBtnActive" if i == idx else "navBtn")
            b.style().unpolish(b)
            b.style().polish(b)


class SidebarCommandsView(QWidget):
    """Design 1: master-detail for the Commands tab (nav rail is in the main window)."""

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
        self.pal = PALETTES["sidebar"]
        self._build()
        self.refresh()

    # -- construction -------------------------------------------------
    def _build(self):
        # The left nav rail is now a persistent element of the main window
        # (shown on every tab in the sidebar theme), so this view only builds
        # the topbar + master + detail.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar(), 0)

        body = QWidget()
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)
        bh.addWidget(self._build_master(), 0)
        bh.addWidget(self._build_detail(), 1)
        root.addWidget(body, 1)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(54)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)
        title = QLabel("Commands")
        title.setObjectName("topTitle")
        h.addWidget(title)
        self.crumb = QLabel("/ GENERAL")
        self.crumb.setObjectName("crumb")
        h.addWidget(self.crumb)
        h.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchBox")
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(self._on_search)
        h.addWidget(self.search_edit)
        save = QPushButton("Save")
        save.clicked.connect(self.on_save)
        new = QPushButton("+ New")
        new.setObjectName("primaryBtn")
        new.clicked.connect(self.on_add)
        h.addWidget(save)
        h.addWidget(new)
        return bar

    def _build_master(self):
        panel = QFrame()
        panel.setObjectName("masterPanel")
        panel.setFixedWidth(340)
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
        self.master_list.setItemDelegate(MasterDelegate(self.pal, self.master_list))
        self.master_list.itemSelectionChanged.connect(self._on_master_selected)
        v.addWidget(self.master_list, 1)
        return panel

    def _build_detail(self):
        panel = QFrame()
        panel.setObjectName("detailPanel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(14)

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
        self.d_sub = QLabel("GENERAL · Everyone")
        self.d_sub.setObjectName("dSub")
        ttl.addWidget(self.d_title)
        ttl.addWidget(self.d_sub)
        head.addLayout(ttl)
        head.addStretch(1)
        self.d_enabled = ToggleSwitch(self.pal)
        self.d_enabled.setChecked(True)
        self.d_enabled.toggled.connect(self._on_detail_enabled)
        head.addWidget(self.d_enabled)
        v.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.f_command = self._field(grid, 0, 0, "Command")
        self.f_group = self._field(grid, 0, 1, "Group")
        self.f_perm = self._field(grid, 1, 0, "Permission")
        self.f_volume = self._field(grid, 1, 1, "Volume")
        self.f_cd = self._field(grid, 2, 0, "Cooldown (s)")
        self.f_ucd = self._field(grid, 2, 1, "User Cooldown (s)")
        self.f_cost = self._field(grid, 3, 0, "Cost")
        self.f_info = self._field(grid, 3, 1, "Info")
        self.f_sound = self._field(grid, 4, 0, "Sound File")
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)

        resp_lab = QLabel("Response")
        resp_lab.setObjectName("fieldLabel")
        v.addWidget(resp_lab)
        self.f_response = QTextEdit()
        self.f_response.setMinimumHeight(70)
        self.f_response.textChanged.connect(self._on_detail_edited)
        v.addWidget(self.f_response)

        for w in (self.f_command, self.f_group, self.f_perm, self.f_info,
                  self.f_volume, self.f_cd, self.f_ucd, self.f_cost, self.f_sound):
            w.textChanged.connect(self._on_detail_edited)

        v.addSpacing(6)
        v.addWidget(self._switch_row("Allow sounds to interrupt",
                                     "Play over currently playing sound",
                                     self._get_interrupt, self._set_interrupt))
        v.addWidget(self._switch_row("Show blocked message",
                                     "Notify user when a sound is queued",
                                     self._get_blocked_msg, self._set_blocked_msg))
        v.addStretch(1)
        return panel

    def _field(self, grid, row, col, label):
        lab = QLabel(label)
        lab.setObjectName("fieldLabel")
        grid.addWidget(lab, row * 2, col)
        edit = QLineEdit()
        grid.addWidget(edit, row * 2 + 1, col)
        return edit

    def _switch_row(self, title, desc, getter, setter):
        row = QFrame()
        row.setObjectName("switchRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 12, 2, 12)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("switchTitle")
        d = QLabel(desc)
        d.setObjectName("switchDesc")
        texts.addWidget(t)
        texts.addWidget(d)
        h.addLayout(texts)
        h.addStretch(1)
        sw = ToggleSwitch(self.pal)
        sw.setChecked(bool(getter()))
        sw.toggled.connect(lambda on: setter(on))
        h.addWidget(sw)
        return row

    def _get_interrupt(self):
        return self.editor.config_manager.get_sound_interruption()

    def _set_interrupt(self, on):
        self.editor.config_manager.set_sound_interruption(bool(on))

    def _get_blocked_msg(self):
        return self.editor.config_manager.get_interruption_message()

    def _set_blocked_msg(self, on):
        self.editor.config_manager.set_interruption_message(bool(on))

    # -- behaviour ----------------------------------------------------
    def refresh(self):
        """Rebuild the master list from current commands."""
        self.refresh_master()
        if self.master_list.count() > 0:
            self._guard = True
            self.master_list.setCurrentRow(0)
            self._guard = False
            self._populate_detail(0)

    def _on_search(self, _text):
        if self.editor is not None and hasattr(self.editor, "filter_commands"):
            self.editor.filter_commands()

    def _go_tab(self, idx):
        tw = self.main_tab
        if 0 <= idx < tw.count():
            tw.setCurrentIndex(idx)

    def highlight_tab(self, idx):
        # The nav rail lives in the main window now — delegate to it.
        nav = getattr(self.editor, "sidebar_nav", None)
        if nav is not None:
            nav.highlight_tab(idx)

    def refresh_master(self):
        self.master_list.blockSignals(True)
        self.master_list.clear()
        search = self.search_edit.text().lower()
        shown = 0
        for cmd in self.commands:
            name = cmd.get("Command", "")
            if search and search not in name.lower():
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cmd)
            item.setSizeHint(QSize(0, 54))
            item.setText(name)
            self.master_list.addItem(item)
            shown += 1
        self.hint.setText("%d total" % shown)
        self.master_list.blockSignals(False)

    def _on_master_selected(self):
        if self._guard:
            return
        items = self.master_list.selectedItems()
        if not items:
            return
        cmd = items[0].data(Qt.UserRole)
        if not isinstance(cmd, dict):
            return
        self._select_in_table(cmd.get("Command", ""))

    def _select_in_table(self, name):
        self._guard = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.text() == name:
                self.table.selectRow(r)
                break
        self._guard = False

    def select_from_table(self, row):
        """Called when the main table selection changes."""
        if self._guard:
            return
        if row < 0 or row >= len(self.commands):
            return
        name = self.commands[row].get("Command", "")
        self._guard = True
        for i in range(self.master_list.count()):
            mi = self.master_list.item(i)
            data = mi.data(Qt.UserRole)
            if isinstance(data, dict) and data.get("Command") == name:
                self.master_list.setCurrentItem(mi)
                break
        self._guard = False
        self._populate_detail(row)

    def _populate_detail(self, row):
        if row < 0 or row >= len(self.commands):
            return
        cmd = self.commands[row]
        self._guard = True
        self.d_title.setText(cmd.get("Command", ""))
        self.d_sub.setText("%s · %s" % (cmd.get("Group", ""), cmd.get("Permission", "")))
        self.crumb.setText("/ %s" % (cmd.get("Group", "") or "GENERAL"))
        self.f_command.setText(cmd.get("Command", ""))
        self.f_group.setText(cmd.get("Group", ""))
        self.f_perm.setText(cmd.get("Permission", ""))
        self.f_info.setText(cmd.get("Info", ""))
        self.f_volume.setText("%d%%" % int(round(float(cmd.get("Volume", 0)) * 100)))
        self.f_cd.setText(str(cmd.get("Cooldown", 0)))
        self.f_ucd.setText(str(cmd.get("UserCooldown", 0)))
        self.f_cost.setText(str(cmd.get("Cost", 0)))
        self.f_sound.setText(cmd.get("SoundFile", ""))
        self.f_response.setPlainText(cmd.get("Response", ""))
        self.d_enabled.setChecked(bool(cmd.get("Enabled", True)))
        self._guard = False

    def _on_detail_edited(self):
        if self._guard:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.commands):
            return
        cmd = self.commands[row]
        cmd["Command"] = self.f_command.text()
        cmd["Group"] = self.f_group.text()
        cmd["Permission"] = self.f_perm.text()
        cmd["Info"] = self.f_info.text()
        try:
            cmd["Volume"] = float(self.f_volume.text().replace("%", "")) / 100.0
        except (ValueError, TypeError):
            pass
        for key, w in (("Cooldown", self.f_cd), ("UserCooldown", self.f_ucd), ("Cost", self.f_cost)):
            try:
                cmd[key] = int(w.text())
            except (ValueError, TypeError):
                pass
        cmd["SoundFile"] = self.f_sound.text()
        cmd["Response"] = self.f_response.toPlainText()
        self._refresh_table_row(row)

    def _on_detail_enabled(self, checked):
        if self._guard:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.commands):
            return
        self.commands[row]["Enabled"] = bool(checked)
        self._refresh_table_row(row)

    def _refresh_table_row(self, row):
        if row < 0 or row >= len(self.commands):
            return
        cmd = self.commands[row]
        self._guard = True
        self.table.setItem(row, 0, QTableWidgetItem(cmd.get("Command", "")))
        self.table.setItem(row, 3, QTableWidgetItem(cmd.get("Group", "")))
        self.table.setItem(row, 1, QTableWidgetItem(cmd.get("Permission", "")))
        self.table.setItem(row, 2, QTableWidgetItem(cmd.get("Info", "")))
        self.table.setItem(row, 13, QTableWidgetItem(str(cmd.get("Volume", 0))))
        self.table.setItem(row, 10, QTableWidgetItem("✓" if cmd.get("Enabled") else "✗"))
        self._guard = False
        self.refresh_master()


# ---------------------------------------------------------------------------
# Spreadsheet (Design 9) Commands view
# ---------------------------------------------------------------------------

class SpreadsheetCommandsView(QWidget):
    """Design 9: dense inline-edit table + toolbar + status bar."""

    COLS = ["#", "Command", "Group", "Permission", "CD", "UCD", "Cost", "Vol", "Sound", "On"]

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
        self.pal = PALETTES["spreadsheet"]
        self._build()
        self.refresh()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_topbar(), 0)
        v.addWidget(self._build_toolbar(), 0)
        v.addWidget(self._build_table(), 1)
        v.addWidget(self._build_statusbar(), 0)

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
        self.search_edit.setPlaceholderText("Filter…")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._on_search)
        h.addWidget(self.search_edit)
        save = QPushButton("Save File")
        save.clicked.connect(self.on_save)
        new = QPushButton("+ Row")
        new.setObjectName("primaryBtn")
        new.clicked.connect(self.on_add)
        h.addWidget(save)
        h.addWidget(new)
        return bar

    def _on_search(self, _text):
        if self.editor is not None and hasattr(self.editor, "filter_commands"):
            self.editor.filter_commands()

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(44)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(8)
        add = QPushButton("+ Insert")
        add.setObjectName("toolBtn")
        add.clicked.connect(self.on_add)
        rem = QPushButton("Delete")
        rem.setObjectName("toolBtn")
        rem.clicked.connect(self.on_remove)
        load = QPushButton("Load")
        load.setObjectName("toolBtn")
        load.clicked.connect(self.on_load)
        save = QPushButton("Save")
        save.setObjectName("toolBtn")
        save.clicked.connect(self.on_save)
        h.addWidget(add)
        h.addWidget(rem)
        h.addWidget(load)
        h.addWidget(save)
        h.addStretch(1)
        self.count_label = QLabel("0 rows")
        self.count_label.setObjectName("countLabel")
        h.addWidget(self.count_label)
        return bar

    def _build_table(self):
        self.dense = QTableWidget()
        self.dense.setObjectName("denseTable")
        self.dense.setColumnCount(len(self.COLS))
        self.dense.setHorizontalHeaderLabels(self.COLS)
        self.dense.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.dense.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dense.verticalHeader().setVisible(False)
        self.dense.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dense.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dense.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.dense.itemChanged.connect(self._on_item_changed)
        self.dense.itemSelectionChanged.connect(self._on_selection)
        return self.dense

    def _build_statusbar(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(28)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(16)
        dot = QLabel("●  connected")
        dot.setStyleSheet("color: %s; font-size: 11px;" % self.pal["green"])
        h.addWidget(dot)
        f = QLabel("commands.json")
        f.setObjectName("statusLabel")
        h.addWidget(f)
        self.status_label = QLabel("ready")
        self.status_label.setObjectName("statusLabel")
        h.addWidget(self.status_label)
        h.addStretch(1)
        enc = QLabel("UTF-8")
        enc.setObjectName("statusLabel")
        h.addWidget(enc)
        return bar

    def refresh(self):
        self.dense.blockSignals(True)
        self.dense.setRowCount(0)
        search = self.search_edit.text().lower()
        shown = 0
        for i, cmd in enumerate(self.commands):
            if search:
                hay = " ".join([
                    str(cmd.get("Command", "")), str(cmd.get("Group", "")),
                    str(cmd.get("Permission", "")), str(cmd.get("Info", "")),
                    str(cmd.get("SoundFile", "")),
                ]).lower()
                if search not in hay:
                    continue
            self.dense.insertRow(shown)
            self._set_row(shown, i, cmd)
            shown += 1
        self.dense.blockSignals(False)
        self.count_label.setText("%d rows" % shown)

    def _set_row(self, row_pos, actual_idx, cmd):
        self.dense.setRowHeight(row_pos, 34)
        rn = QTableWidgetItem(str(actual_idx + 1))
        rn.setTextAlignment(Qt.AlignCenter)
        rn.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        rn.setData(Qt.UserRole, actual_idx)
        self.dense.setItem(row_pos, 0, rn)
        c = QTableWidgetItem(cmd.get("Command", ""))
        c.setFont(_mono_font())
        self.dense.setItem(row_pos, 1, c)
        self.dense.setCellWidget(row_pos, 2,
                                 make_pill_label(cmd.get("Group", ""),
                                                 group_pill_kind(cmd.get("Group", "")),
                                                 self.pal))
        self.dense.setItem(row_pos, 3, QTableWidgetItem(cmd.get("Permission", "")))
        self.dense.setItem(row_pos, 4, QTableWidgetItem(str(cmd.get("Cooldown", 0))))
        self.dense.setItem(row_pos, 5, QTableWidgetItem(str(cmd.get("UserCooldown", 0))))
        self.dense.setItem(row_pos, 6, QTableWidgetItem(str(cmd.get("Cost", 0))))
        vol = QTableWidgetItem("%d%%" % int(round(float(cmd.get("Volume", 0)) * 100)))
        vol.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.dense.setItem(row_pos, 7, vol)
        snd = QTableWidgetItem(cmd.get("SoundFile", "") or "—")
        snd.setFont(_mono_font(9))
        self.dense.setItem(row_pos, 8, snd)
        sw = ToggleSwitch(self.pal, width=32, height=18)
        sw.setChecked(bool(cmd.get("Enabled", True)))
        sw.toggled.connect(lambda on_chk, rp=row_pos: self._on_toggle(rp, on_chk))
        self.dense.setCellWidget(row_pos, 9, sw)

    def _on_toggle(self, row_pos, on):
        r = self._row_index(row_pos)
        if r >= len(self.commands):
            return
        self.commands[r]["Enabled"] = bool(on)
        self._sync_main_row(r)

    def _row_index(self, row_pos):
        """Map a table row position to the real command index (handles filter)."""
        item = self.dense.item(row_pos, 0)
        if item is not None:
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                return idx
        return row_pos

    def _on_item_changed(self, item):
        if self._guard:
            return
        r = self._row_index(item.row())
        col = item.column()
        if r >= len(self.commands):
            return
        cmd = self.commands[r]
        if col == 1:
            cmd["Command"] = item.text()
        elif col == 2:
            cmd["Group"] = item.text()
        elif col == 3:
            cmd["Permission"] = item.text()
        elif col == 4:
            self._set_int(cmd, "Cooldown", item.text())
        elif col == 5:
            self._set_int(cmd, "UserCooldown", item.text())
        elif col == 6:
            self._set_int(cmd, "Cost", item.text())
        elif col == 7:
            try:
                cmd["Volume"] = float(item.text().replace("%", "")) / 100.0
            except (ValueError, TypeError):
                pass
        elif col == 8:
            cmd["SoundFile"] = item.text()
        self._sync_main_row(r)

    def _set_int(self, cmd, key, text):
        try:
            cmd[key] = int(text)
        except (ValueError, TypeError):
            pass

    def _sync_main_row(self, r):
        if r < 0 or r >= len(self.commands):
            return
        cmd = self.commands[r]
        self._guard = True
        self.table.setItem(r, 0, QTableWidgetItem(cmd.get("Command", "")))
        self.table.setItem(r, 3, QTableWidgetItem(cmd.get("Group", "")))
        self.table.setItem(r, 1, QTableWidgetItem(cmd.get("Permission", "")))
        self.table.setItem(r, 2, QTableWidgetItem(cmd.get("Info", "")))
        self.table.setItem(r, 13, QTableWidgetItem(str(cmd.get("Volume", 0))))
        self._guard = False

    def _on_selection(self):
        if self._guard:
            return
        rows = self.dense.selectionModel().selectedRows()
        if not rows:
            return
        r = self._row_index(rows[0].row())
        self._guard = True
        self.table.selectRow(r)
        self._guard = False
        cmd = self.commands[r] if r < len(self.commands) else {}
        self.status_label.setText("row %d · %s" % (r + 1, cmd.get("Command", "")))

    def highlight_tab(self, idx):
        """No-op: the spreadsheet view has no sidebar nav to highlight."""
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
        if 0 <= row < len(self.commands):
            self.status_label.setText("row %d · %s" % (row + 1, self.commands[row].get("Command", "")))

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
        self.pal = PALETTES["sidebar"]
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
        self.pal = PALETTES["sidebar"]
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
        root.addWidget(content, 1)

        root.addWidget(self._build_status_bar())

        self._start_status_timer()


class SpreadsheetTwitchView(TwitchThemedBase):
    """Design 9: brand topbar + toolbar (auth/channel/actions) + chat|viewers + status bar."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(SpreadsheetTwitchView, self).__init__(parent, tab_widget, twitch_tab)
        self.pal = PALETTES["spreadsheet"]
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
        tb = QFrame()
        tb.setObjectName("toolbar")
        tb.setFixedHeight(46)
        tbh = QHBoxLayout(tb)
        tbh.setContentsMargins(16, 0, 16, 0)
        tbh.setSpacing(10)
        tbh.addWidget(self._build_auth_pill())
        chan = QLabel("channel")
        chan.setStyleSheet("color:%s;font-size:12px;" % self.pal["text2"])
        tbh.addWidget(chan)
        tt.channel_input.setFixedWidth(150)
        tbh.addWidget(tt.channel_input)
        sep = QFrame()
        sep.setFixedSize(1, 22)
        sep.setStyleSheet("background:%s;" % self.pal["border"])
        tbh.addWidget(sep)
        tbh.addWidget(tt.check_connection_button)
        tbh.addWidget(tt.auth_button)
        tbh.addWidget(tt.token_button)
        tbh.addStretch(1)
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

        root.addWidget(body, 1)
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

class ThemedTabView(QWidget):
    """Themed frame around an original tab widget (topbar + content)."""

    def __init__(self, parent, tab_widget, original_tab, title, subtitle=""):
        super(ThemedTabView, self).__init__(parent)
        self.editor = parent
        self.tab_widget = tab_widget
        self.original_tab = original_tab
        self.pal = PALETTES.get(self.editor.theme, PALETTES["sidebar"])
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
        root.addWidget(top)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 14, 16, 14)
        bv.setSpacing(0)
        # Re-parent the original tab into the themed body
        self.original_tab.setParent(body)
        self.original_tab.show()
        self.original_tab.setStyleSheet(
            "QWidget{background:%s;}" % self.pal["surface"])
        bv.addWidget(self.original_tab, 1)
        root.addWidget(body, 1)

    def highlight_tab(self, idx):
        pass
