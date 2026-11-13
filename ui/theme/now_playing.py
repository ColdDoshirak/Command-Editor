# -*- coding: utf-8 -*-
"""The persistent Now-Playing bar (midnight theme): queues from any tab.

Python 3.8 / PyQt5.
"""
import time

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton)
from PyQt5.QtCore import QTimer
from ui.theme.style import (palette_for)
from ui.theme.widgets import (connection_state, make_icon)
from ui.i18n import tr


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
        self._open = QPushButton(tr("Queue Control"))
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
        skip.setToolTip(tr("Skip what %s is playing") % group)
        h.addWidget(pause)
        h.addWidget(skip)
        pause.clicked.connect(lambda: self._toggle_pause(group))
        skip.clicked.connect(lambda: self._call("skip_queue_current", group))
        self._h.insertWidget(self._h.count() - 2, w)
        slot = {"w": w, "text": t, "meta": meta, "pause": pause, "skip": skip}
        self._slots[group] = slot
        return slot

    def _call(self, name, *args):
        tt = getattr(self.editor, "twitch_tab", None)
        bridge = getattr(tt, "bridge", None)
        if self._bot() is not None and bridge is not None:
            bridge.call(name, *args)

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
            self._idle.setText(tr("Queues appear here when the bot is connected (%s).") % text)
            self._idle.show()
            return
        if not groups:
            self._idle.setText(tr("No queued groups — enable a queue in Group Settings."))
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
                slot["text"].setText(tr("!%s") % cur["command"])
                started = cur.get("started")
                elapsed = int(time.time() - started) if started else 0
                slot["meta"].setText(tr("%s · %d:%02d · %d waiting") % (
                    cur["user"], elapsed // 60, elapsed % 60, len(snap["pending"])))
            else:
                slot["text"].setText(tr("paused") if snap["paused"] else tr("idle"))
                slot["meta"].setText(tr("%d waiting") % len(snap["pending"]) if snap["pending"] else "")
            slot["skip"].setEnabled(cur is not None)
            slot["pause"].setIcon(make_icon("play" if snap["paused"] else "pause", self.pal["text"]))
            slot["pause"].setToolTip(tr("Resume %s") % g if snap["paused"] else tr("Pause %s") % g)
