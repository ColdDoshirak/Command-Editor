# -*- coding: utf-8 -*-
"""Small shared widgets and helpers: fonts, pills, icons, delegates,
the sidebar navigation, toolbar helpers.

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
                             QAbstractButton, QStyledItemDelegate, QStyle, QComboBox, QSpinBox,
                             QMenu, QScrollArea, QToolBar, QSizePolicy)
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPixmap, QIcon,
    QLinearGradient, QPainterPath, QPolygonF,
)
from ui.theme.style import (FONT_FAMILY, is_dark)


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
            (11, "Timers", "clock"),
            (5, "Ranks", "star"),
        ]),
        ("Economy", [
            (3, "Currency", "coin"),
            (4, "Users", "bars"),
        ]),
        ("System", [
            (12, "Settings", "gear"),
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
