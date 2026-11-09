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


kit.start(body, delay_ms=400)
