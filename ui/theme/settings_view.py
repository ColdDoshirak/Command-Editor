# -*- coding: utf-8 -*-
"""The themed Settings page.

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QComboBox,
                             QSpinBox, QScrollArea)
from PyQt5.QtCore import QTimer
from ui.theme.style import (THEMES, THEME_LABELS, layout_of, palette_for)
from ui.theme.widgets import (ToggleSwitch)


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
