# -*- coding: utf-8 -*-
"""Queue Control tab: live view of a group's command queue.

Controls:
  - group combo (only groups with queue_enabled=true)
  - player-style buttons: Pause/Resume, Skip current, Clear queue
  - drag & drop list to reorder queued items by priority

Threading: the bot runs in its own thread with its own asyncio loop.
All mutations go through bot.loop.call_soon_threadsafe / coroutines;
the UI only takes read-only snapshots (iterating q._queue) for display.
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QAbstractItemView)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import (QIcon, QPixmap, QPainter, QColor, QPolygonF,
                         QPen, QBrush)


def _draw_icon(kind, size=32, color=(60, 60, 60)):
    """Рисуем иконку кнопкой программно (без файлов). kind: refresh|pause|
    play|skip|clear. Возвращает QIcon."""
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
    m = size * 0.22  # margin
    x0, y0, x1, y1 = m, m, size - m, size - m
    cx, cy = size / 2.0, size / 2.0
    if kind == "pause":
        w = size * 0.13
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(x0 + size * 0.06, y0, w, y1 - y0))
        p.drawRect(QRectF(x1 - w - size * 0.06, y0, w, y1 - y0))
    elif kind == "play":
        p.setPen(Qt.NoPen)
        tri = QPolygonF([QPointF(x0 + size * 0.08, y0),
                         QPointF(x0 + size * 0.08, y1),
                         QPointF(x1 - size * 0.02, cy)])
        p.drawPolygon(tri)
    elif kind == "skip":
        # треугольник вперёд + вертикальная черта
        p.setPen(Qt.NoPen)
        tri = QPolygonF([QPointF(x0, y0), QPointF(x0, y1),
                         QPointF(x1 - size * 0.14, cy)])
        p.drawPolygon(tri)
        p.setPen(pen)
        p.drawLine(QPointF(x1 - size * 0.06, y0), QPointF(x1 - size * 0.06, y1))
    elif kind == "clear":
        # крестик
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        p.drawLine(QPointF(x1, y0), QPointF(x0, y1))
    elif kind == "refresh":
        # дуга со стрелкой
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = (x1 - x0) / 2.0
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, 60 * 16, 250 * 16)
        # стрелка в начале дуги (справа-сверху)
        p.setPen(Qt.NoPen)
        tip = QPointF(cx + r * 0.5, cy - r * 0.87)
        ar = QPolygonF([tip, QPointF(tip.x() - size * 0.14, tip.y() + size * 0.02),
                        QPointF(tip.x() + size * 0.02, tip.y() + size * 0.14)])
        p.drawPolygon(ar)
    p.end()
    return QIcon(pm)


class QueueControlTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = parent.config_manager
        self._items_cache = []  # last displayed (author, command) pairs
        self.init_ui()

        # Poll the queue every second while the tab is visible
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.refresh_queue)
        self.poll_timer.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def init_ui(self):
        layout = QVBoxLayout()

        # Group selector row
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Group:"))
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(200)
        top_row.addWidget(self.group_combo)
        self.refresh_groups_btn = QPushButton(_draw_icon("refresh"), "")
        self.refresh_groups_btn.setToolTip("Refresh group list")
        self.refresh_groups_btn.setFixedSize(34, 34)
        self.refresh_groups_btn.clicked.connect(self.refresh_groups)
        top_row.addWidget(self.refresh_groups_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        # Player-style controls (иконки)
        ctrl_row = QHBoxLayout()
        self.pause_btn = QPushButton(_draw_icon("pause"), "")
        self.pause_btn.setToolTip("Pause / Resume queue")
        self.pause_btn.setFixedSize(44, 44)
        self.pause_btn.clicked.connect(self.toggle_pause)
        ctrl_row.addWidget(self.pause_btn)

        self.skip_btn = QPushButton(_draw_icon("skip"), "")
        self.skip_btn.setToolTip("Skip current command")
        self.skip_btn.setFixedSize(44, 44)
        self.skip_btn.clicked.connect(self.skip_current)
        ctrl_row.addWidget(self.skip_btn)

        self.clear_btn = QPushButton(_draw_icon("clear"), "")
        self.clear_btn.setToolTip("Clear queue")
        self.clear_btn.setFixedSize(44, 44)
        self.clear_btn.clicked.connect(self.clear_queue)
        ctrl_row.addWidget(self.clear_btn)
        ctrl_row.addStretch(1)
        layout.addLayout(ctrl_row)

        # Queue list (drag & drop reorder)
        self.queue_list = QListWidget()
        self.queue_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        # Qt5: itemMoved отсутствует — ловим перемещение через model
        self.queue_list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(QLabel("Queued commands (drag to reorder by priority):"))
        layout.addWidget(self.queue_list)

        self.status_label = QLabel("Waiting for bot...")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.refresh_groups()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bot(self):
        """The running bot instance, or None."""
        tw = getattr(self.parent, 'twitch_tab', None)
        if tw is not None and getattr(tw, 'bot', None) is not None:
            return tw.bot
        return None

    def _queue_groups(self):
        """Groups with queue enabled (uppercase keys)."""
        cats = self.config_manager.get_audio_categories()
        return sorted(g for g, v in cats.items()
                      if isinstance(v, dict) and v.get('queue_enabled', False))

    def refresh_groups(self):
        current = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for g in self._queue_groups():
            self.group_combo.addItem(g)
        if current in self._queue_groups():
            self.group_combo.setCurrentText(current)
        self.group_combo.blockSignals(False)
        self.refresh_queue()

    def current_group(self):
        return self.group_combo.currentText()

    # ------------------------------------------------------------------
    # Read-only snapshot (UI thread)
    # ------------------------------------------------------------------
    def refresh_queue(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None:
            self.status_label.setText("Bot is not running. Start the bot to manage queues.")
            return
        if not group:
            self.status_label.setText("No groups with queue enabled. Enable a queue in Group Settings.")
            return

        q = bot.command_queues.get(group)
        if q is None:
            self.status_label.setText("Queue for group %s not initialized." % group)
            return

        # Read-only snapshot: iterate the deque directly, never drain.
        items = [(getattr(m, 'author', None) and m.author.name or '?',
                  c.get('Command', '?')) for (m, c) in list(q._queue)]

        # Don't clobber the list while the user is mid-drag
        if self.queue_list.hasFocus() and self.queue_list.inDropMode():
            return

        new_key = [tuple(i) for i in items]
        if new_key != self._items_cache:
            self.queue_list.blockSignals(True)
            self.queue_list.clear()
            for idx, (author, cmd) in enumerate(items):
                name = str(cmd).lstrip('!')
                it = QListWidgetItem("%d. !%s | by %s" % (idx + 1, name, author))
                self.queue_list.addItem(it)
            self.queue_list.blockSignals(False)
            self._items_cache = new_key

        paused = group in getattr(bot, 'queue_paused', set())
        # Иконка паузы/воспроизведения + подсказка
        if paused:
            self.pause_btn.setIcon(_draw_icon("play"))
            self.pause_btn.setToolTip("Resume queue")
        else:
            self.pause_btn.setIcon(_draw_icon("pause"))
            self.pause_btn.setToolTip("Pause queue")
        self.status_label.setText(
            "Group: %s | In queue: %d | State: %s" % (
                group, len(items), "PAUSED" if paused else "processing"))

    # ------------------------------------------------------------------
    # Actions (all hop onto the bot loop)
    # ------------------------------------------------------------------
    def toggle_pause(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        if not hasattr(bot, 'queue_paused'):
            bot.queue_paused = set()
        paused = group in bot.queue_paused
        if paused:
            bot.queue_paused.discard(group)
        else:
            bot.queue_paused.add(group)
        self.refresh_queue()

    def skip_current(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        loop = getattr(bot, 'loop', None)
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(bot._ui_skip_next, group)

    def clear_queue(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        loop = getattr(bot, 'loop', None)
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(bot._ui_clear_queue, group)

    def _on_rows_moved(self, *args):
        # rowsMoved(source, dest, count) — пересчитываем порядок после drop
        self.on_items_reordered()

    def on_items_reordered(self):
        bot = self._bot()
        group = self.current_group()
        if bot is None or not group:
            return
        # New order of command names, as displayed
        order = []
        for i in range(self.queue_list.count()):
            text = self.queue_list.item(i).text()
            # "1. !cmd | by user" -> cmd
            try:
                order.append(text.split('. !', 1)[1].split(' | by ', 1)[0])
            except (IndexError, ValueError):
                order.append(text)
        loop = getattr(bot, 'loop', None)
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(bot._ui_reorder_queue, group, list(order))