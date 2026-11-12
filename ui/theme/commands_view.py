# -*- coding: utf-8 -*-
"""The themed Commands tab: one command editor, the sidebar
(master-detail) and spreadsheet views.

Python 3.8 / PyQt5.
"""
import os

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
                             QPushButton, QLineEdit, QListWidget, QListWidgetItem, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView, QTextEdit,
                             QComboBox, QSpinBox, QSlider, QInputDialog, QScrollArea, QSplitter)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QColor
from core.permissions import name_of as permission_name
from ui.theme.style import (PERMISSIONS, USAGES, palette_for)
from ui.theme.widgets import (LogoBadge, MasterDelegate, ToggleSwitch, _ComboDelegate,
                              _SpinDelegate, _known_groups, _matches, _mono_font, _more_menu,
                              _overflow_toolbar, _shrinkable, _toolbar_stretch, _ui_font,
                              cmd_volume, connection_state, group_pill_kind, make_icon,
                              pill_colors, rgba_color)


class CommandDetailEditor(QScrollArea):
    """Full editor for one command (all fields of the classic tab).

    Used by the Sidebar/Midnight Commands view (right pane) and by the
    Spreadsheet view (panel below the table, wide=True). Text edits are applied
    after a short pause (not on every keystroke: each apply rewrites
    commands.json and pushes to the bot). Every edit goes through
    editor.apply_command_edit().
    """

    def __init__(self, editor, table, commands, pal, on_remove, on_changed=None, wide=False):
        super(CommandDetailEditor, self).__init__()
        # wide=True: panel BELOW a table (like the classic tab) - fields in
        # four columns on the left, sound + response on the right, so it
        # needs little height.
        self.wide = wide
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

        cols = 4 if self.wide else 2
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(6)
        for c in range(cols):
            g.setColumnStretch(c, 1)
        pairs = []  # (label, widget) in reading order, placed below

        self.f_command = QLineEdit()
        self.f_command.textChanged.connect(lambda t: self._edit("Command", t))
        self.f_group = QComboBox()
        self.f_group.setEditable(True)
        self.f_group.setInsertPolicy(QComboBox.NoInsert)
        self.f_group.setToolTip("Commands of a group share queue / channel settings (Group Settings tab)")
        self.f_group.editTextChanged.connect(lambda t: self._edit("Group", t))
        pairs += [("Command", self.f_command), ("Group", self.f_group)]

        self.f_perm = QComboBox()
        self.f_perm.addItems(PERMISSIONS)
        self.f_perm.currentTextChanged.connect(lambda t: self._edit("Permission", t, now=True))
        self.f_usage = QComboBox()
        self.f_usage.addItems(USAGES)
        self.f_usage.setToolTip("SC = Streamer.bot/SC style, Chat = chat only, Both")
        self.f_usage.currentTextChanged.connect(lambda t: self._edit("Usage", t, now=True))
        pairs += [("Permission", self.f_perm), ("Usage", self.f_usage)]

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
        pairs += [("Cooldown", self.f_cd), ("User cooldown", self.f_ucd)]

        self.f_cost = QSpinBox()
        self.f_cost.setRange(0, 10000000)
        self.f_cost.setSpecialValueText("free")
        self.f_cost.valueChanged.connect(lambda val: self._edit("Cost", val))
        self.f_count = QSpinBox()
        self.f_count.setRange(0, 100000000)
        self.f_count.setToolTip("How many times the command was used")
        self.f_count.valueChanged.connect(lambda val: self._edit("Count", val))
        pairs += [("Cost (points)", self.f_cost), ("Used", self.f_count)]

        for i, (text, widget) in enumerate(pairs):
            r, c = (i // cols) * 2, i % cols
            g.addWidget(self._label(text), r, c)
            g.addWidget(widget, r + 1, c)
        last = ((len(pairs) + cols - 1) // cols) * 2

        self.f_info = QLineEdit()
        self.f_info.setPlaceholderText("Description for yourself / moderators")
        self.f_info.textChanged.connect(lambda t: self._edit("Info", t))
        g.addWidget(self._label("Info"), last, 0, 1, cols)
        g.addWidget(self.f_info, last + 1, 0, 1, cols)
        self.f_aliases = QLineEdit()
        self.f_aliases.setPlaceholderText("!music, !tune")
        self.f_aliases.setToolTip("Other names for this command, e.g. '!music, !tune'. They share its cooldown, cost and count. Responses may use {user} {target} {args} {1}..{9} {count} {points} {currency} {random:1-100}")
        self.f_aliases.textChanged.connect(lambda t: self._edit("Aliases", t))
        g.addWidget(self._label("Aliases"), last + 2, 0, 1, cols)
        g.addWidget(self.f_aliases, last + 3, 0, 1, cols)

        # Narrow (side panel): everything in one column. Wide (bottom
        # panel): fields on the left, sound + response on the right.
        if self.wide:
            body = QHBoxLayout()
            body.setSpacing(24)
            left = QVBoxLayout()
            left.addLayout(g)
            left.addStretch(1)
            right = QVBoxLayout()
            right.setSpacing(8)
            body.addLayout(left, 3)
            body.addLayout(right, 2)
            v.addLayout(body, 1)
            v = right  # the sound / response block goes to the right column
        else:
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
        self.browse_btn = b
        self.folder_btn = QPushButton("Folder…")
        self.folder_btn.setToolTip("A folder: a random sound from it plays each time")
        self.folder_btn.clicked.connect(lambda: self.editor.browse_folder(self.f_sound))
        srow.addWidget(self.folder_btn)
        self.play_btn = QPushButton()
        self.play_btn.setIcon(make_icon("play", self.pal["accent"]))
        self.play_btn.setToolTip("Preview sound (click again to stop)")
        self.play_btn.clicked.connect(self._preview)
        srow.addWidget(self.play_btn)
        self.test_btn = QPushButton("Test…")
        self.test_btn.setToolTip("What happens if a viewer writes it - without Twitch")
        self.test_btn.clicked.connect(self._test)
        srow.addWidget(self.test_btn)
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
        self.f_response.setMinimumHeight(60 if self.wide else 90)
        self.f_response.textChanged.connect(
            lambda: self._edit("Response", self.f_response.toPlainText()))
        if self.wide:
            v.addWidget(self.f_response, 1)
        else:
            v.addWidget(self.f_response)
            v.addStretch(1)

        self.detail_widgets = [self.f_command, self.f_group, self.f_perm, self.f_usage,
                               self.f_cd, self.f_ucd, self.f_cost, self.f_count, self.f_info,
                               self.f_aliases,
                               self.f_sound, self.f_fk, self.f_volume, self.f_response,
                               self.d_enabled, self.d_delete, self.play_btn, self.test_btn, b, b2]
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

    def _test(self):
        self.flush()
        if self.row >= 0:
            self.editor.test_command(self.row)

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
            perm = permission_name(cmd.get("Permission", "Everyone"))
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
            self.f_aliases.setText(cmd.get("Aliases", ""))
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
        # table above, command settings below - as in the classic tab
        # (the same full editor as the Sidebar layout, in its wide form)
        self.split = QSplitter(Qt.Vertical)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(1)
        self.split.addWidget(self._build_table())
        self.detail = CommandDetailEditor(self.editor, self.table, self.commands, self.pal,
                                          on_remove=self.on_remove,
                                          on_changed=self._on_detail_changed,
                                          wide=True)
        self.detail.setMinimumHeight(170)
        self.split.addWidget(self.detail)
        # both parts shrink with the window (table 2 : settings 1), so a
        # small window keeps some table rows visible
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([420, 330])
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
        self.test_btn = self._tool("Test…", self._test, "What happens if a viewer writes it - without Twitch")
        self.resp_btn = self._tool("Edit response…", self._edit_response,
                                   "Multi-line response editor (or double-click the Response cell)")
        h.addWidget(self.browse_btn)
        h.addWidget(self.play_btn)
        h.addWidget(self.test_btn)
        h.addWidget(self.resp_btn)
        _toolbar_stretch(bar)
        self.details_btn = self._tool("Details ▾", self._toggle_details,
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

    def _test(self):
        idx = self._selected_idx()
        if idx is not None:
            self.editor.test_command(idx)

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
        for b in (self.del_btn, self.browse_btn, self.play_btn, self.test_btn, self.resp_btn):
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
