"""The Timers tab (2.0): messages the bot posts to chat by itself
(core/timers.py; the bot runs them, bot/twitch_bot.py _timers_loop).

Every change is saved at once to config.json "timers"; the running bot
reads them on its next check (every 10 s), nothing to restart.

Python 3.8 / PyQt5.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QHeaderView, QCheckBox, QLineEdit, QSpinBox, QAbstractItemView)

from core import variables
from core.timers import DEFAULT_TIMER
from ui.i18n import tr, N_

COLUMNS = (N_("On"), N_("Message"), N_("Every (min)"), N_("After chat lines"), N_("Live only"))


class TimersTab(QWidget):
    def __init__(self, editor):
        super(TimersTab, self).__init__()
        self.editor = editor
        self.config_manager = editor.config_manager
        self._loading = False
        v = QVBoxLayout(self)
        intro = QLabel(
            tr("The bot posts these messages to chat by itself: every N minutes, but only after "
            "at least M chat messages since its last post (so it does not talk to an empty chat). "
            "{channel} and {random:1-100} work in the text."))
        intro.setWordWrap(True)
        v.addWidget(intro)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton(tr("Add timer"))
        self.add_btn.clicked.connect(self.add_timer)
        self.remove_btn = QPushButton(tr("Remove"))
        self.remove_btn.clicked.connect(self.remove_selected)
        self.post_btn = QPushButton(tr("Post now"))
        self.post_btn.setToolTip(tr("Send the selected message to chat now (the bot must be connected)"))
        self.post_btn.clicked.connect(self.post_selected)
        for b in (self.add_btn, self.remove_btn, self.post_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.status = QLabel("")
        buttons.addWidget(self.status)
        v.addLayout(buttons)
        self.reload()

    # -- rows ----------------------------------------------------------------------
    def _row_widgets(self, timer):
        on = QCheckBox()
        on.setChecked(timer["enabled"])
        msg = QLineEdit(timer["message"])
        msg.setPlaceholderText(tr("Follow the channel to get notified!"))
        every = QSpinBox()
        every.setRange(1, 1440)
        every.setValue(timer["interval"])
        lines = QSpinBox()
        lines.setRange(0, 10000)
        lines.setValue(timer["min_lines"])
        live = QCheckBox()
        live.setChecked(timer["live_only"])
        on.toggled.connect(self.save)
        msg.editingFinished.connect(self.save)
        every.valueChanged.connect(self.save)
        lines.valueChanged.connect(self.save)
        live.toggled.connect(self.save)
        return on, msg, every, lines, live

    def _centered(self, w):
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setAlignment(Qt.AlignCenter)
        h.addWidget(w)
        return holder

    def reload(self):
        self._loading = True
        try:
            timers = self.config_manager.get_timers()
            self.table.setRowCount(0)
            self._rows = []
            for t in timers:
                self._append(t)
        finally:
            self._loading = False

    def _append(self, timer):
        r = self.table.rowCount()
        self.table.insertRow(r)
        on, msg, every, lines, live = self._row_widgets(timer)
        self.table.setCellWidget(r, 0, self._centered(on))
        self.table.setCellWidget(r, 1, msg)
        self.table.setCellWidget(r, 2, every)
        self.table.setCellWidget(r, 3, lines)
        self.table.setCellWidget(r, 4, self._centered(live))
        self._rows.append((on, msg, every, lines, live))
        return msg

    def timers(self):
        return [{"enabled": on.isChecked(), "message": msg.text(), "interval": every.value(),
                 "min_lines": lines.value(), "live_only": live.isChecked()}
                for on, msg, every, lines, live in self._rows]

    # -- actions -------------------------------------------------------------------
    def save(self, *_):
        if self._loading:
            return
        self.config_manager.set_timers(self.timers())
        self.status.setText(tr("Saved"))

    def add_timer(self):
        msg = self._append(dict(DEFAULT_TIMER))
        self.save()
        self.table.selectRow(self.table.rowCount() - 1)
        msg.setFocus()

    def _selected(self):
        rows = sorted(set(i.row() for i in self.table.selectionModel().selectedIndexes()))
        return rows[0] if rows else -1

    def remove_selected(self):
        r = self._selected()
        if r < 0:
            return
        self.table.removeRow(r)
        del self._rows[r]
        self.save()

    def post_selected(self):
        r = self._selected()
        if r < 0:
            return
        text = self._rows[r][1].text().strip()
        if not text:
            return
        tab = getattr(self.editor, "twitch_tab", None)
        channel = getattr(getattr(tab, "bot", None), "channel", "") if tab else ""
        text = variables.render(text, {"channel": channel})
        if tab is not None and tab.bridge.submit("send_chat", text):
            self.status.setText(tr("Posted"))
            tab.add_to_chat_safe(tr('[Timer] {0}').format(text))
        else:
            self.status.setText(tr("Not connected"))
