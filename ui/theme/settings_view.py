# -*- coding: utf-8 -*-
"""The themed Settings page.

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QComboBox,
                             QSpinBox, QScrollArea, QKeySequenceEdit, QLineEdit, QPushButton,
                             QApplication)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QKeySequence
from ui.hotkeys import ACTIONS as HOTKEY_ACTIONS, available as hotkeys_available
from ui import i18n
from ui.i18n import tr
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
        t = QLabel(tr(title))
        t.setObjectName("sectionTitle")
        v.addWidget(t)
        if desc:
            d = QLabel(tr(desc))
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

        card, cv = self._card(tr("Sound"), tr("How sounds of commands WITHOUT a queue behave on the shared channel."))
        self._switch_row(cv, tr("Allow sounds to interrupt each other"),
                         tr("A new command stops the sound that is playing. Off: the new sound is skipped."),
                         e.allow_interruption_check)
        self._switch_row(cv, tr("Tell the viewer when their sound was blocked"),
                         tr("Sends a chat message and refunds the points."),
                         e.show_interruption_message_check, last=True)
        v.addWidget(card)

        card, cv = self._card(tr("Auto-save & backups"), tr("Intervals are in seconds."))
        self._switch_row(cv, tr("Auto-save commands"), tr("Write commands.json periodically."),
                         e.auto_save_checkbox, e.auto_save_interval_input)
        self._switch_row(cv, tr("Automatic full backups"), tr("Commands + currency + settings snapshot."),
                         e.system_auto_backup_checkbox, e.system_backup_interval_input)
        self._switch_row(cv, tr("Auto-save currency users"), tr("Points, hours and ranks."),
                         e.currency_auto_save_checkbox, e.currency_backup_interval_input, last=True)
        v.addWidget(card)

        cfg = getattr(e, "config_manager", None)
        if cfg is not None and hasattr(cfg, "get_moderators_are_admins"):
            card, cv = self._card(
                tr("Permissions"),
                tr("Admin commands: the channel owner and the \"admins\" list in moderators.json "
                "(Twitch tab -> Open moderators file)."))
            row = QFrame()
            row.setObjectName("")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 10, 0, 10)
            texts = QVBoxLayout()
            t = QLabel(tr("Moderators have Admin rights"))
            t.setObjectName("switchTitle")
            texts.addWidget(t)
            d = QLabel(tr("On (as in 1.x): every moderator may use Admin commands. "
                       "Off: only the channel owner and the admins list."))
            d.setObjectName("switchDesc")
            d.setWordWrap(True)
            texts.addWidget(d)
            h.addLayout(texts, 1)
            self.mods_admin_switch = ToggleSwitch(self.pal)
            self.mods_admin_switch.setChecked(cfg.get_moderators_are_admins())
            self.mods_admin_switch.toggled.connect(cfg.set_moderators_are_admins)
            h.addWidget(self.mods_admin_switch)
            cv.addWidget(row)
            v.addWidget(card)

        if hasattr(e, "hotkey_settings"):
            card, cv = self._card(
                tr("Global hotkeys"),
                tr("Work while the window is minimised or a game has the focus. Off by default: "
                "while on, these keys do nothing in other programs."))
            self._hotkey_rows(cv)
            v.addWidget(card)

        if hasattr(e, "overlay_settings"):
            card, cv = self._card(
                tr("OBS overlay"),
                tr("A page for an OBS Browser Source: now playing, the queues, recent commands. "
                "Only this computer can open it (127.0.0.1)."))
            self._overlay_rows(cv)
            v.addWidget(card)

        cfg_lang = getattr(getattr(e, "config_manager", None), "get_language", None)
        if cfg_lang is not None:
            card, cv = self._card(tr("Language"), tr(
                "The language of the interface. \"System\": Russian when Windows is in Russian, "
                "otherwise English."))
            row = QHBoxLayout()
            row.setContentsMargins(0, 8, 0, 4)
            self.language_combo = QComboBox()
            for key, label in i18n.LANGUAGES:
                self.language_combo.addItem(tr(label), key)
            self.language_combo.setCurrentIndex(
                max(0, [k for k, _l in i18n.LANGUAGES].index(cfg_lang())))
            self.language_combo.activated.connect(self._language_changed)
            row.addStretch(1)
            row.addWidget(self.language_combo)
            cv.addLayout(row)
            self.language_note = QLabel("")
            self.language_note.setObjectName("switchDesc")
            cv.addWidget(self.language_note)
            v.addWidget(card)

        card, cv = self._card(tr("Appearance"), "")
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 12)
        lab = QLabel(tr("Theme"))
        lab.setObjectName("switchTitle")
        row.addWidget(lab)
        row.addStretch(1)
        self.theme_combo = QComboBox()
        for key in THEMES:
            self.theme_combo.addItem(tr(THEME_LABELS[key]), key)
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

    def _hotkey_rows(self, layout):
        e = self.editor
        settings = e.hotkey_settings()
        row = QFrame()
        row.setObjectName("switchRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        t = QLabel(tr("Enable global hotkeys"))
        t.setObjectName("switchTitle")
        h.addWidget(t, 1)
        self.hotkey_switch = ToggleSwitch(self.pal)
        self.hotkey_switch.setChecked(bool(settings.get("enabled")))
        self.hotkey_switch.setEnabled(hotkeys_available())
        self.hotkey_switch.toggled.connect(self._hotkeys_changed)
        h.addWidget(self.hotkey_switch)
        layout.addWidget(row)
        self.hotkey_edits = {}
        for name, label, default in HOTKEY_ACTIONS:
            r = QHBoxLayout()
            r.setContentsMargins(0, 6, 0, 6)
            lab = QLabel(tr(label))
            lab.setObjectName("switchDesc")
            r.addWidget(lab, 1)
            ed = QKeySequenceEdit(QKeySequence(settings.get(name, default) or ""))
            ed.setFixedWidth(170)
            ed.editingFinished.connect(self._hotkeys_changed)
            r.addWidget(ed)
            layout.addLayout(r)
            self.hotkey_edits[name] = ed
        self.hotkey_status = QLabel("")
        self.hotkey_status.setObjectName("switchDesc")
        self.hotkey_status.setWordWrap(True)
        layout.addWidget(self.hotkey_status)
        self._show_hotkey_problems(getattr(e, "hotkey_problems", {}) or {})

    def _hotkeys_changed(self, *_):
        settings = {"enabled": self.hotkey_switch.isChecked()}
        for name, ed in self.hotkey_edits.items():
            # one combination per action (QKeySequenceEdit allows up to four)
            text = ed.keySequence().toString(QKeySequence.PortableText).split(",")[0].strip()
            settings[name] = text
        self._show_hotkey_problems(self.editor.set_hotkey_settings(settings))

    def _show_hotkey_problems(self, problems):
        if not hotkeys_available():
            self.hotkey_status.setText(tr("Global hotkeys work on Windows only."))
            return
        labels = dict((n, l) for n, l, _d in HOTKEY_ACTIONS)
        lines = ["%s: %s" % (labels.get(n, n), why) for n, why in sorted(problems.items())]
        self.hotkey_status.setText("\n".join(lines))

    def _overlay_rows(self, layout):
        e = self.editor
        s = e.overlay_settings()
        row = QFrame()
        row.setObjectName("switchRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        t = QLabel(tr("Enable the overlay"))
        t.setObjectName("switchTitle")
        h.addWidget(t, 1)
        self.overlay_port = QSpinBox()
        self.overlay_port.setRange(1024, 65535)
        self.overlay_port.setValue(int(s.get("port", 8765) or 8765))
        self.overlay_port.setPrefix(tr("port "))
        self.overlay_port.setFixedWidth(120)
        self.overlay_port.editingFinished.connect(self._overlay_changed)
        h.addWidget(self.overlay_port)
        self.overlay_switch = ToggleSwitch(self.pal)
        self.overlay_switch.setChecked(bool(s.get("enabled")))
        self.overlay_switch.toggled.connect(self._overlay_changed)
        h.addWidget(self.overlay_switch)
        layout.addWidget(row)
        r = QHBoxLayout()
        r.setContentsMargins(0, 6, 0, 6)
        self.overlay_url = QLineEdit()
        self.overlay_url.setReadOnly(True)
        self.overlay_url.setPlaceholderText(tr("off"))
        r.addWidget(self.overlay_url, 1)
        copy_btn = QPushButton(tr("Copy"))
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.overlay_url.text()))
        r.addWidget(copy_btn)
        layout.addLayout(r)
        self.overlay_status = QLabel("")
        self.overlay_status.setObjectName("switchDesc")
        self.overlay_status.setWordWrap(True)
        layout.addWidget(self.overlay_status)
        self._show_overlay()

    def _overlay_changed(self, *_):
        settings = {"enabled": self.overlay_switch.isChecked(), "port": self.overlay_port.value()}
        if settings != {k: self.editor.overlay_settings().get(k) for k in settings} \
                or settings["enabled"] != self.editor.overlay.running():
            self.editor.apply_overlay_settings(settings)
        self._show_overlay()

    def _show_overlay(self):
        e = self.editor
        url = e.overlay_url()
        self.overlay_url.setText(url)
        if url:
            self.overlay_status.setText(
                tr("OBS: Sources -> Browser, this URL, width 400, height 600. "
                "Options: ?show=now,queue,recent (blocks) and &size=28 (font)."))
        elif e.overlay_settings().get("enabled"):
            self.overlay_status.setText(tr("Could not start on port %d: %s")
                                        % (self.overlay_port.value(), e.overlay.error or "?"))
        else:
            self.overlay_status.setText("")

    def _language_changed(self, *_):
        key = self.language_combo.currentData()
        self.editor.config_manager.set_language(key)
        differs = i18n.resolve(key) != i18n.language()
        self.language_note.setText(tr("Restart Command Editor to switch the language.") if differs else "")

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
