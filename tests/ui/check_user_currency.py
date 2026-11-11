"""Currency users table (plan, section 4):

- it iterated currency_manager.users while the bot thread changed it
  ("dictionary changed size during iteration" -> table silently not updated)
- every refresh (30 s) re-created an Edit and a Remove button per viewer
"""
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump = k.w, k.check, k.pump
    tab = w.user_currency_tab
    cur = w.currency_manager
    with cur.users_lock:
        cur.users.clear()
        cur.users.update({"alice": {"points": 30, "hours": 1}, "bob": {"points": 20, "hours": 1},
                          "carol": {"points": 10, "hours": 1}})
    tab.populate_table(); pump()
    names = [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())]
    check("table filled, by points", names == ["alice", "bob", "carol"], names)

    buttons = [(tab.table.cellWidget(r, 5), tab.table.cellWidget(r, 6)) for r in range(3)]
    tab.populate_table(); pump()
    again = [(tab.table.cellWidget(r, 5), tab.table.cellWidget(r, 6)) for r in range(3)]
    check("refresh keeps the row buttons", buttons == again)

    # order changes: the button in row 0 must act on the new first viewer
    with cur.users_lock:
        cur.users["carol"]["points"] = 99
    tab.populate_table(); pump()
    hit = []
    orig_edit = tab.edit_user
    tab.edit_user = lambda u: hit.append(u)
    try:
        tab.table.cellWidget(0, 5).click(); pump()
    finally:
        tab.edit_user = orig_edit
    check("Edit acts on the viewer now in that row", hit == ["carol"], hit)

    # the bot thread adds and removes viewers (under users_lock, as it does)
    import ui.user_currency_tab as uct
    errors = []
    real_print = uct.__dict__.get("print", print)
    uct.print = lambda *a, **kw: errors.append(" ".join(map(str, a))) \
        if a and "Error populating" in str(a[0]) else None
    stop = []

    def churn():
        i = 0
        while not stop:
            with cur.users_lock:
                cur.users["u%d" % (i % 400)] = {"points": i % 97, "hours": 0}
                cur.users.pop("u%d" % ((i + 200) % 400), None)
            i += 1
            time.sleep(0.0002)       # a real bot does not hold the lock in a tight loop
    t = threading.Thread(target=churn, daemon=True)
    t.start()
    try:
        for _ in range(15):
            tab.populate_table()
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        stop.append(1)
        t.join(2)
        if real_print is print:
            del uct.print
        else:
            uct.print = real_print
    check("refresh while the bot changes viewers", errors == [], errors[:2])

    with cur.users_lock:
        cur.users.clear()
    tab.populate_table(); pump()
    check("no viewers -> empty table", tab.table.rowCount() == 0, tab.table.rowCount())

    # ---- the Add / Edit dialogs, driven for real ------------------------------------
    import json
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QLineEdit, QAbstractSpinBox, QPushButton

    def drive(fill):
        """Fill the modal dialog that opens next, then press Save."""
        done = []

        def step():
            dlg = QApplication.activeModalWidget()
            if dlg is None:
                QTimer.singleShot(50, step)
                return
            try:
                fill(dlg)
            finally:
                save = [b for b in dlg.findChildren(QPushButton) if b.text() == "Save"]
                (save[0].click() if save else dlg.reject())
                done.append(1)
                # Save failed (exception) -> the dialog stays open: close it
                QTimer.singleShot(100, lambda: dlg.isVisible() and dlg.reject())
        QTimer.singleShot(50, step)
        return done

    def disk():
        with open(str(cur.users_file), encoding="utf-8") as f:
            return json.load(f)

    def fill_add(dlg):
        dlg.findChildren(QLineEdit)[0].setText("MixedCase")
        dlg.findChildren(QAbstractSpinBox)[0].setValue(5)
    errors_before = len([r for r in k.results if r[0] == "FAIL"])
    drive(fill_add)
    tab.add_user(); pump(200)
    check("Add User with capitals in the name works",
          "mixedcase" in cur.users and cur.users["mixedcase"]["points"] == 5
          and len([r for r in k.results if r[0] == "FAIL"]) == errors_before,
          (sorted(cur.users), [r for r in k.results if r[0] == "FAIL"][errors_before:]))

    with cur.users_lock:
        cur.users["whale"] = {"points": 2000000.5, "hours": 3.25, "is_regular": True}
    drive(lambda dlg: None)                      # open Edit, change nothing, Save
    tab.edit_user("whale"); pump(200)
    check("Edit + Save keeps a big / fractional balance",
          cur.users["whale"]["points"] == 2000000.5 and disk()["whale"]["points"] == 2000000.5,
          cur.users["whale"])

    # moderator status set from the Twitch tab reaches the disk
    w.twitch_tab.update_bot_moderators_status("whale", True); pump()
    check("moderator flag from the Twitch tab is saved", disk().get("whale", {}).get("is_mod") is True,
          disk().get("whale"))


    # ---- currency tab: "Active bonus - also offline" is saved ----------------------
    ct = w.currency_tab
    ct.offline_active_bonus_check.setChecked(not ct.offline_active_bonus_check.isChecked()); pump()
    want = ct.offline_active_bonus_check.isChecked()
    with open(str(cur.settings_file), encoding="utf-8") as f:
        saved = json.load(f).get("offline_active_bonus")
    check("Active bonus 'also offline' saved", cur.settings.get("offline_active_bonus") is want
          and saved is want, (want, saved))


    # ---- Sub Bonus is a multiplier, and the estimate says so ------------------------
    check("sub field is a multiplier, at least 1",
          ct.sub_bonus_input.minimum() == 1 and "multiplier" in ct.sub_label.text().lower(),
          (ct.sub_bonus_input.minimum(), ct.sub_label.text()))
    for widget, value in ((ct.live_payout_input, 10), (ct.online_interval_slider, 5),
                          (ct.regular_bonus_input, 1), (ct.sub_bonus_input, 3),
                          (ct.mod_bonus_input, 2), (ct.active_bonus_input, 0)):
        widget.setValue(value)
    pump()
    text = ct.time_info_label.text()
    # a subscriber who is also regular and mod: 10 x 3 + 1 + 2 per 5 min = 396/h
    check("estimate: base x multiplier + bonuses", "Min: 120/h - Max: 396/h" in text, text)


kit.start(body, delay_ms=400)
