"""OBS overlay (2.0): a small local web page for an OBS Browser Source.

    http://127.0.0.1:<port>/                     the page (transparent)
    http://127.0.0.1:<port>/?show=now,queue      only some blocks
    http://127.0.0.1:<port>/state.json           what the page polls

The server has its own thread and asyncio loop (aiohttp is already a
dependency of twitchio), so it works with or without a bot and never
touches Qt. The window puts a fresh snapshot here (OverlayServer.update)
twice a second; the page asks for it every second. Bound to 127.0.0.1 only.

Python 3.8 compatible. No Qt.
"""
import asyncio
import copy
import json
import threading
import time

EMPTY = {"connected": False, "live": False, "now": [], "queues": [], "recent": []}
RECENT_MAX = 10


def snapshot_from_bot(bot, recent=()):
    """The overlay state from the bot's queue snapshots (read-only, called
    from the UI thread like the Queue Control tab does)."""
    state = copy.deepcopy(EMPTY)
    state["recent"] = list(recent)[-RECENT_MAX:]
    if bot is None or not hasattr(bot, "queue_snapshot"):
        return state
    state["connected"] = bool(getattr(bot, "is_running", False))
    state["live"] = bool(getattr(bot, "is_live", False))
    now = time.time()
    for group in sorted(getattr(bot, "command_queues", {}) or {}):
        try:
            snap = bot.queue_snapshot(group)
        except Exception:
            continue
        if not snap:
            continue
        cur = snap.get("current")
        if cur:
            started = cur.get("started")
            state["now"].append({"group": group, "command": "!" + str(cur.get("command", "")),
                                 "user": cur.get("user", ""),
                                 "elapsed": int(now - started) if started else 0})
        state["queues"].append({"group": group, "paused": bool(snap.get("paused")),
                                "pending": [{"command": "!" + str(p.get("command", "")),
                                             "user": p.get("user", "")}
                                            for p in snap.get("pending", [])[:15]],
                                "more": max(0, len(snap.get("pending", [])) - 15)})
    return state


class OverlayServer(object):
    def __init__(self, page_html):
        self.page_html = page_html
        self._state = copy.deepcopy(EMPTY)
        self._lock = threading.Lock()
        self._thread = None
        self._loop = None
        self._runner = None
        self.port = None
        self.error = None

    # -- state (any thread) ------------------------------------------------------
    def update(self, state):
        with self._lock:
            self._state = copy.deepcopy(state)

    def state(self):
        with self._lock:
            return copy.deepcopy(self._state)

    # -- server -------------------------------------------------------------------
    def running(self):
        return self._thread is not None and self._thread.is_alive() and self.port is not None

    def start(self, port, timeout=5.0):
        """Start on 127.0.0.1:port. Returns True, or False with self.error
        (port in use, ...)."""
        self.stop()
        self.error = None
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(int(port), ready),
                                        name="obs-overlay", daemon=True)
        self._thread.start()
        ready.wait(timeout)
        return self.running()

    def _run(self, port, ready):
        from aiohttp import web

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        async def page(request):
            return web.Response(text=self.page_html, content_type="text/html", charset="utf-8")

        async def state(request):
            return web.Response(text=json.dumps(self.state(), ensure_ascii=False),
                                content_type="application/json", charset="utf-8",
                                headers={"Cache-Control": "no-store"})

        app = web.Application()
        app.router.add_get("/", page)
        app.router.add_get("/state.json", state)
        runner = web.AppRunner(app, access_log=None)
        try:
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, "127.0.0.1", port)
            loop.run_until_complete(site.start())
            self._runner = runner
            self.port = site._server.sockets[0].getsockname()[1]
        except Exception as e:
            self.error = str(e)
            self.port = None
            ready.set()
            try:
                loop.run_until_complete(runner.cleanup())
            except Exception:
                pass
            loop.close()
            return
        ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(runner.cleanup())
            except Exception:
                pass
            loop.close()

    def stop(self):
        loop, thread = self._loop, self._thread
        if loop is not None and thread is not None and thread.is_alive():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
            thread.join(5)
        self._thread = None
        self._loop = None
        self.port = None
