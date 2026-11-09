"""Stage 0.5: crash logging (docs/refactor-plan.md).

- the previous run's log is shifted to .1/.2/.3, not deleted at start
- unhandled exceptions (main thread, other threads, asyncio loop) land in
  command_editor_crash.log with their traceback

Py3.8 compatible.
"""
import asyncio
import os
import sys
import threading

from harness import new_tmpdir, drop_tmpdir

import app_log


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


async def test_previous_logs_are_shifted_not_deleted():
    tmp = new_tmpdir()
    try:
        log = os.path.join(tmp, app_log.LOG_FILE_NAME)
        for run in ("run1", "run2", "run3", "run4", "run5"):
            app_log.rotate_previous_log(log)
            with open(log, "w", encoding="utf-8") as f:
                f.write(run)
        assert _read(log) == "run5"
        assert _read(log + ".1") == "run4"
        assert _read(log + ".2") == "run3"
        assert _read(log + ".3") == "run2"
        assert not os.path.exists(log + ".4")
    finally:
        drop_tmpdir(tmp)


async def test_unhandled_exceptions_reach_crash_log():
    tmp = new_tmpdir()
    saved = (sys.excepthook, threading.excepthook)
    try:
        crash = app_log.install_crash_handlers(tmp, fault_handler=False)

        try:
            raise ValueError("main thread boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())

        def worker():
            raise KeyError("worker boom")
        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # the test itself runs inside a loop, so the bot's loop is not run
        # here; its exception handler is what asyncio calls on such errors
        loop = asyncio.new_event_loop()
        try:
            app_log.install_asyncio_handler(loop)
            try:
                raise OSError("handler boom")
            except OSError as e:
                loop.call_exception_handler({"message": "Task exception was never retrieved",
                                             "exception": e})
        finally:
            loop.close()

        text = _read(crash)
        for needle in ("main thread boom", "worker boom", "handler boom", "Traceback"):
            assert needle in text, (needle, text[-2000:])
    finally:
        sys.excepthook, threading.excepthook = saved
        app_log.uninstall_crash_handlers()
        drop_tmpdir(tmp)
