"""C4: results of bot-thread requests (viewers, stream status) must reach
the widgets in the UI thread, never be applied in the bot's thread."""
import concurrent.futures
import os
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def _done(result=None, exc=None):
    f = concurrent.futures.Future()
    if exc is not None:
        f.set_exception(exc)
    else:
        f.set_result(result)
    return f


def body(k):
    w, check, pump = k.w, k.check, k.pump
    tab = w.twitch_tab
    main = threading.current_thread()
    seen = []

    def spy(**kw):
        seen.append((threading.current_thread(), sorted(kw.get("all_viewers") or [])))
    w.currency_manager.process_currency_update = spy
    tab.bot = SimpleNamespace(active_users=["fallback"], is_live=None)

    t = threading.Thread(target=tab._on_viewers_done, args=(_done(["bob", "alice"]),))
    t.start(); t.join()
    check("viewers: nothing applied in the bot thread", seen == [], seen)
    pump(300)
    check("viewers: applied once in the UI thread",
          len(seen) == 1 and seen[0][0] is main, seen)
    items = [tab.all_viewers_list.item(i).text() for i in range(tab.all_viewers_list.count())]
    check("viewers: list widget filled", items == ["alice", "bob"], items)

    seen[:] = []
    t = threading.Thread(target=tab._on_viewers_done, args=(_done(exc=RuntimeError("helix")),))
    t.start(); t.join(); pump(300)
    check("viewers: failed request falls back to active users",
          len(seen) == 1 and seen[0][0] is main and seen[0][1] == ["fallback"], seen)

    statuses = []
    tab.signal_handler.stream_status_signal.connect(
        lambda live: statuses.append((threading.current_thread(), live)))
    t = threading.Thread(target=tab._on_stream_status_done, args=(_done(True),))
    t.start(); t.join(); pump(300)
    check("stream status: delivered in the UI thread",
          statuses == [(main, True)] and tab.bot.is_live is True, (statuses, tab.bot.is_live))
    tab.bot = None


kit.start(body, delay_ms=400)
