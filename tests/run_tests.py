"""Test runner for the offline queue tests.

Usage:
    python3 tests/run_tests.py            # all tests
    python3 tests/run_tests.py red        # only bug-reproduction tests
    python3 tests/run_tests.py green      # only regression tests
    python3 tests/run_tests.py -k name    # only tests whose name contains 'name'

Exit code: 0 if all selected tests pass, 1 otherwise.
Py3.8 compatible.
"""
import asyncio
import importlib
import os
import sys
import time
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

# Grab the real print BEFORE the harness silences it (bot debug spam).
_real_print = print

import harness  # noqa: E402  (installs stubs)
from harness import cleanup_repo_dir  # noqa: E402

TEST_MODULES = [
    ("green", "test_queue_regressions"),
    ("red", "test_queue_bugs"),
    ("stress", "test_queue_stress"),
    ("reliability", "test_reliability"),
    ("reliability", "test_reliability_config"),
]


def collect_tests():
    tests = []
    for tag, modname in TEST_MODULES:
        mod = importlib.import_module(modname)
        for name in dir(mod):
            if name.startswith("test_"):
                fn = getattr(mod, name)
                if asyncio.iscoroutinefunction(fn):
                    tests.append((tag, modname, name, fn))
    return tests


def run_one(fn):
    """Run a single async test in a fresh event loop. Returns (ok, detail)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.wait_for(fn(), timeout=30))
        return True, ""
    except AssertionError as e:
        return False, "ASSERT: %s" % e
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    finally:
        try:
            # Cancel any leftover tasks (queue workers) so the loop closes cleanly.
            pending = asyncio.all_tasks(loop) if hasattr(asyncio, "all_tasks") else asyncio.Task.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        loop.close()


def main():
    args = [a for a in sys.argv[1:]]
    tag_filter = None
    name_filter = None
    if args and args[0] in ("red", "green", "stress", "reliability"):
        tag_filter = args[0]
        args = args[1:]
    if args and args[0] == "-k":
        name_filter = args[1] if len(args) > 1 else None

    tests = collect_tests()
    selected = []
    for tag, modname, name, fn in tests:
        if tag_filter and tag != tag_filter:
            continue
        if name_filter and name_filter not in name:
            continue
        selected.append((tag, modname, name, fn))

    if not selected:
        _real_print("No tests selected.")
        return 1

    passed = 0
    failed = 0
    t_start = time.monotonic()
    for tag, modname, name, fn in selected:
        t0 = time.monotonic()
        ok, detail = run_one(fn)
        dt = time.monotonic() - t0
        status = "PASS" if ok else "FAIL"
        mark = " " if ok else "!"
        _real_print("[%s] %s %s (%.2fs)%s" % (mark, tag, name, dt,
                                        (" - " + detail) if detail else ""))
        if not ok:
            failed += 1
        else:
            passed += 1

    total = time.monotonic() - t_start
    _real_print("-" * 60)
    _real_print("Total: %d  Passed: %d  Failed: %d  (%.2fs)" % (
        len(selected), passed, failed, total))
    cleanup_repo_dir()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())