# -*- coding: utf-8 -*-
"""Queue Control tab: live view and control of the command queues.

Shows, per group:
  - what is playing right now (command, viewer, elapsed time)
  - the pending list (drag & drop or Up/Down to reorder)
  - Pause/Resume, Skip current, Remove selected, Clear

Threading: the bot runs in its own thread with its own asyncio loop.
Every mutation is sent to that loop with loop.call_soon_threadsafe; the UI
only reads snapshots (bot.queue_snapshot) for display. Pending entries are
addressed by a stable id, so two identical commands in the queue are never
confused (the old version removed/reordered by command name).

Python 3.8 / PyQt5.
"""
import time

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QAbstractItemView, QFrame, QMessageBox,
                             QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PyQt5.QtGui import (QIcon, QPixmap, QPainter, QColor, QPolygonF,
                         QPen, QBrush, QKeySequence, QFont)


def _draw_icon(kind, size=32, color=(60, 60, 60)):
    """Draw a button icon programmatically (no image files).
    kind: refresh|pause|play|skip|clear|remove|up|down. Returns QIcon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(*color)
    pen = QPen(c)
    pen.setWidthF(size * 0.09)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    m = size * 0.22
    x0, y0, x1, y1 = m, m, size - m, size - m
    cx, cy = size / 2.0, size / 2.0
    if kind == "pause":
        w = size * 0.13
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(x0 + size * 0.06, y0, w, y1 - y0))
        p.drawRect(QRectF(x1 - w - size * 0.06, y0, w, y1 - y0))
    elif kind == "play":
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(x0 + size * 0.08, y0),
                                 QPointF(x0 + size * 0.08, y1),
                                 QPointF(x1 - size * 0.02, cy)]))
    elif kind == "skip":
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(x0, y0), QPointF(x0, y1),
                                 QPointF(x1 - size * 0.14, cy)]))
        p.setPen(pen)
        p.drawLine(QPointF(x1 - size * 0.06, y0), QPointF(x1 - size * 0.06, y1))
    elif kind == "clear":
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        p.drawLine(QPointF(x1, y0), QPointF(x0, y1))
    elif kind == "remove":
        p.setBrush(Qt.NoBrush)
        r = (x1 - x0) / 2.0
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.drawLine(QPointF(cx - r * 0.55, cy), QPointF(cx + r * 0.55, cy))
    elif kind in ("up", "down"):
        p.setBrush(Qt.NoBrush)
        d = -1 if kind == "up" else 1
        tip = QPointF(cx, cy + d * (y1 - y0) * 0.38)
        p.drawLine(QPointF(cx, cy - d * (y1 - y0) * 0.42), tip)
        p.drawLine(tip, QPointF(cx - size * 0.18, tip.y() - d * size * 0.18))
        p.drawLine(tip, QPointF(cx + size * 0.18, tip.y() - d * size * 0.18))
    elif kind == "refresh":
        p.setBrush(Qt.NoBrush)
        r = (x1 - x0) / 2.0
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), 60 * 16, 250 * 16)
        p.setPen(Qt.NoPen)
        tip = QPointF(cx + r * 0.5, cy - r * 0.87)
        p.drawPolygon(QPolygonF([
            tip, QPointF(tip.x() - size * 0.14, tip.y() + size * 0.02),
            QPointF(tip.x() + size * 0.02, tip.y() + size * 0.14)]))
    p.end()
    return QIcon(pm)


def _fmt_elapsed(started):
    if not started:
        return ""
    secs = max(0, int(time.time() - started))
    return "%d:%02d" % (secs // 60, secs % 60)


class QueueControlTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = parent.config_manager
        self._items_key = None   # last rendered pending ids
        self._init_ui()

        # Poll the bot every 500 ms (cheap: reads a snapshot only)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(500)
        self.poll_timer.timeout.connect(self.refresh_queue)
        self.poll_timer.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _btn(self, icon, text, tip, slot):
        b = QPushButton(_draw_icon(icon), " " + text)
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tip)
        b.setMinimumHeight(34)
        b.clicked.connect(slot)
        return b

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Group selector row
        top = QHBoxLayout()
        top.addWidget(QLabel("Group:"))
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(220)
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        top.addWidget(self.group_combo)
        self.refresh_groups_btn = QPushButton(_draw_icon("refresh"), "")
        self.refresh_groups_btn.setToolTip("Reload the list of queue groups")
        self.refresh_groups_btn.setFixedSize(34, 34)
        self.refresh_groups_btn.clicked.connect(self.refresh_groups)
        top.addWidget(self.refresh_groups_btn)
        top.addStretch(1)
        self.limit_label = QLabel("")
        self.limit_label.setObjectName("statusLabel")
        top.addWidget(self.limit_label)
        layout.addLayout(top)

        # Now playing card
        self.now_card = QFrame()
        self.now_card.setObjectName("nowPlayingCard")
        self.now_card.setFrameShape(QFrame.StyledPanel)
        nc = QHBoxLayout(self.now_card)
        nc.setContentsMargins(14, 10, 14, 10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        cap = QLabel("NOW PLAYING")
        cap.setObjectName("navSection")
        f = cap.font()
        f.setBold(True)
        f.setPointSize(max(7, f.pointSize() - 1))
        cap.setFont(f)
        self.now_title = QLabel("—")
        tf = self.now_title.font()
        tf.setPointSize(tf.pointSize() + 3)
        tf.setBold(True)
        self.now_title.setFont(tf)
        self.now_sub = QLabel("")
        texts.addWidget(cap)
        texts.addWidget(self.now_title)
        texts.addWidget(self.now_sub)
        nc.addLayout(texts, 1)
        self.pause_btn = self._btn("pause", "Pause", "Pause the queue (the current item finishes)", self.toggle_pause)
        self.skip_btn = self._btn("skip", "Skip", "Skip the item that is playing now", self.skip_current)
        nc.addWidget(self.pause_btn)
        nc.addWidget(self.skip_btn)
        layout.addWidget(self.now_card)

        # Pending list + side controls
        layout.addWidget(QLabel("Up next — drag to reorder, Del to remove:"))
        body = QHBoxLayout()
        self.queue_list = QListWidget()
        self.queue_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue_list.model().rowsMoved.connect(self._on_rows_moved)
        self.queue_list.itemSelectionChanged.connect(self._update_buttons)
        body.addWidget(self.queue_list, 1)

        side = QVBoxLayout()
        self.up_btn = self._btn("up", "Up", "Move selected item up", lambda: self.move_selected(-1))
        self.down_btn = self._btn("down", "Down", "Move selected item down", lambda: self.move_selected(1))
        self.remove_btn = self._btn("remove", "Remove", "Remove selected item from the queue", self.remove_selected)
        self.clear_btn = self._btn("clear", "Clear all", "Remove every pending item", self.clear_queue)
        for b in (self.up_btn, self.down_btn, self.remove_btn):
            side.addWidget(b)
        side.addStretch(1)
        side.addWidget(self.clear_btn)
        body.addLayout(side)
        layout.addLayout(body, 1)

        self.status_label = QLabel("Waiting for bot...")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        self.refresh_groups()

    def _icon_rgb(self):
        """Icon colour that matches the active theme (dark themes need light icons)."""
        try:
            import theme as _theme
            name = getattr(self.parent, "theme", "classic")
            if _theme.layout_of(name) != "classic":
                c = QColor(_theme.palette_for(name)["text2"])
                return (c.red(), c.green(), c.blue())
        except Exception:
            pass
        return (60, 60, 60)

    def showEvent(self, event):
        rgb = self._icon_rgb()
        if rgb != getattr(self, "_icons_rgb", None):
            self._icons_rgb = rgb
            for btn, kind in ((self.refresh_groups_btn, "refresh"), (self.skip_btn, "skip"),
                              (self.up_btn, "up"), (self.down_btn, "down"),
                              (self.remove_btn, "remove"), (self.clear_btn, "clear")):
                btn.setIcon(_draw_icon(kind, color=rgb))
            self._items_key = None
        super().showEvent(event)
        self.refresh_queue()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Delete) and self.queue_list.hasFocus():
            self.remove_selected()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bot(self):
        tw = getattr(self.parent, 'twitch_tab', None)
        bot = getattr(tw, 'bot', None) if tw is not None else None
        if bot is None or not hasattr(bot, 'queue_snapshot'):
            return None
        return bot

    def _loop(self, bot):
        loop = getattr(bot, 'loop', None)
        if loop is None or loop.is_closed():
            return None
        return loop

    def _send(self, func, *args):
        """Run a bot method in the bot loop, then refresh the view."""
        bot = self._bot()
        loop = self._loop(bot) if bot is not None else None
        if loop is None:
            return
        loop.call_soon_threadsafe(func, *args)
        QTimer.singleShot(120, self.refresh_queue)

    def _queue_groups(self):
        cats = self.config_manager.get_audio_categories()
        return sorted(g for g, v in cats.items()
                      if isinstance(v, dict) and v.get('queue_enabled', False))

    def refresh_groups(self):
        current = self.current_group()
        groups = self._queue_groups()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for g in groups:
            self.group_combo.addItem(g, g)
        if current in groups:
            self.group_combo.setCurrentIndex(groups.index(current))
        self.group_combo.blockSignals(False)
        self._items_key = None
        self.refresh_queue()

    def current_group(self):
        data = self.group_combo.currentData()
        return data if data else self.group_combo.currentText()

    def _on_group_changed(self, _i):
        self._items_key = None
        self.refresh_queue()

    def _selected_id(self):
        item = self.queue_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _update_buttons(self, snap=None):
        has_sel = self.queue_list.currentItem() is not None
        row = self.queue_list.currentRow()
        live = self._bot() is not None
        self.remove_btn.setEnabled(live and has_sel)
        self.up_btn.setEnabled(live and has_sel and row > 0)
        self.down_btn.setEnabled(live and has_sel and row < self.queue_list.count() - 1)
        self.clear_btn.setEnabled(live and self.queue_list.count() > 0)
        if snap is not None:
            self.skip_btn.setEnabled(live and snap.get('current') is not None)
            self.pause_btn.setEnabled(live)

    # ------------------------------------------------------------------
    # Read-only snapshot (UI thread)
    # ------------------------------------------------------------------
    def refresh_queue(self):
        if not self.isVisible() and self._items_key is not None:
            return  # nothing to repaint while hidden
        bot = self._bot()
        group = self.current_group()

        # Group names with live counts in the combo
        if bot is not None:
            for i in range(self.group_combo.count()):
                g = self.group_combo.itemData(i)
                n = bot.queue_pending_count(g) if g in bot.command_queues else 0
                text = "%s  (%d)" % (g, n) if n else g
                if self.group_combo.itemText(i) != text:
                    self.group_combo.setItemText(i, text)

        if bot is None:
            self._render_idle("Bot is not running. Connect on the Twitch tab to manage queues.")
            return
        if not group:
            self._render_idle("No groups with a queue. Enable one in Group Settings.")
            return
        snap = bot.queue_snapshot(group)
        if snap is None:
            self._render_idle("Queue for %s is not initialised yet." % group)
            return

        # Now playing
        cur = snap['current']
        if cur is not None:
            self.now_title.setText("!%s" % cur['command'])
            self.now_sub.setText("by %s · %s%s" % (
                cur['user'], _fmt_elapsed(cur.get('started')),
                " · skipping…" if cur.get('skipped') else ""))
        else:
            self.now_title.setText("Nothing playing")
            self.now_sub.setText("Paused — press Resume to continue" if snap['paused']
                                 else "Waiting for viewers' commands")

        # Pending list (don't touch it mid-drag)
        dragging = self.queue_list.state() == QAbstractItemView.DraggingState
        key = tuple(p['id'] for p in snap['pending'])
        if not dragging and key != self._items_key:
            keep = self._selected_id()
            self.queue_list.blockSignals(True)
            self.queue_list.clear()
            for pos, p in enumerate(snap['pending'], start=1):
                it = QListWidgetItem("%d.  !%s   —  %s" % (pos, p['command'], p['user']))
                it.setData(Qt.UserRole, p['id'])
                self.queue_list.addItem(it)
                if p['id'] == keep:
                    self.queue_list.setCurrentItem(it)
            self.queue_list.blockSignals(False)
            self._items_key = key

        paused = snap['paused']
        pause_key = (paused, getattr(self, "_icons_rgb", None))
        if pause_key != getattr(self, "_pause_key", None):  # don't repaint every poll
            self._pause_key = pause_key
            self.pause_btn.setIcon(_draw_icon("play" if paused else "pause",
                                              color=pause_key[1] or (60, 60, 60)))
            self.pause_btn.setText(" Resume" if paused else " Pause")
        if snap['max'] > 0:
            self.limit_label.setText("Limit %d · %d free" % (snap['max'], snap['free'] or 0))
        else:
            self.limit_label.setText("No size limit")
        state = "PAUSED" if paused else ("playing" if cur else "idle")
        if not snap.get('enabled', True):
            state += " · queue disabled, finishing remaining items"
        self.status_label.setText("%s · %d waiting · %s" % (group, len(snap['pending']), state))
        self._update_buttons(snap)

    def _render_idle(self, message):
        self.now_title.setText("—")
        self.now_sub.setText("")
        if self.queue_list.count():
            self.queue_list.clear()
        self._items_key = ()
        self.limit_label.setText("")
        self.status_label.setText(message)
        for b in (self.pause_btn, self.skip_btn, self.up_btn, self.down_btn,
                  self.remove_btn, self.clear_btn):
            b.setEnabled(False)

    # ------------------------------------------------------------------
    # Actions (all hop onto the bot loop)
    # ------------------------------------------------------------------
    def toggle_pause(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        self._send(bot.set_queue_paused, group, group not in bot.queue_paused)

    def skip_current(self):
        bot = self._bot()
        group = self.current_group()
        if bot is not None and group:
            self._send(bot.skip_queue_current, group)

    def remove_selected(self):
        bot = self._bot()
        group = self.current_group()
        item_id = self._selected_id()
        if bot is None or not group or item_id is None:
            return
        row = self.queue_list.currentRow()
        self._send(bot.remove_from_queue_by_id, group, item_id)
        # keep a sensible selection for repeated Del presses
        QTimer.singleShot(160, lambda: self.queue_list.setCurrentRow(
            min(row, self.queue_list.count() - 1)))

    def move_selected(self, delta):
        bot = self._bot()
        group = self.current_group()
        item_id = self._selected_id()
        if bot is None or not group or item_id is None:
            return
        self._send(bot.move_queue_item, group, item_id, delta)

    def clear_queue(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        n = self.queue_list.count()
        if n == 0:
            return
        answer = QMessageBox.question(
            self, "Clear queue",
            "Remove all %d waiting item(s) from %s?\nPoints are not refunded." % (n, group),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._send(bot.clear_queue, group)

    def _on_rows_moved(self, *args):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        ids = [self.queue_list.item(i).data(Qt.UserRole)
               for i in range(self.queue_list.count())]
        # renumber immediately so the list doesn't look stale
        self._items_key = tuple(ids)
        self._send(bot.reorder_queue_by_ids, group, ids)
        self._items_key = None
