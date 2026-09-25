"""Reliability suite for the REAL CurrencyManager.

The existing queue tests run against FakeCurrencyManager (a trivial
in-memory dict). The real "lost points" bug lived in the REAL
CurrencyManager: locking, validation, checksum, backup/recovery. This
suite exercises that real code (via harness.make_real_currency) to prove
the point-balance invariants hold under concurrency and corruption.

All tests are async (the runner runs each in a fresh event loop, 30s cap).
Py3.8 compatible.
"""
import asyncio
import json
import os
import threading
import time

from harness import (  # noqa: F401
    make_real_currency, new_tmpdir, drop_tmpdir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload(cm):
    """Force a reload from disk (fresh read of the file)."""
    cm.load_data()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def test_reliability_persistence_roundtrip():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("alice", points=1234, hours=5)
        cm.add_points("bob", 77)
        cm.save_users(force=True)

        # Simulate a process restart: brand-new manager, same dir.
        cm2 = make_real_currency(d)
        assert cm2.get_points("alice") == 1234, "alice points lost on reload"
        assert cm2.get_points("bob") == 77, "bob points lost on reload"
        assert cm2.get_hours("alice") == 5, "alice hours lost on reload"
    finally:
        drop_tmpdir(d)


async def test_reliability_no_negative_balance():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("carol", points=10)
        # Cost exceeds balance -> must refuse, balance unchanged.
        ok = cm.pay_for_command("carol", 50)
        assert ok is False, "pay_for_command must refuse when balance < cost"
        assert cm.get_points("carol") == 10, "balance must not change on refusal"
        # Exact-cost payment drains to zero, not negative.
        ok = cm.pay_for_command("carol", 10)
        assert ok is True
        assert cm.get_points("carol") == 0, "balance must land exactly on 0"
        # Further payment now refused.
        assert cm.pay_for_command("carol", 1) is False
        assert cm.get_points("carol") == 0
    finally:
        drop_tmpdir(d)


# ---------------------------------------------------------------------------
# Lost-update race (the core "lost points" bug)
# ---------------------------------------------------------------------------

async def test_reliability_concurrent_add_pay_exact():
    """add_points (UI thread) racing pay_for_command (bot thread) must not
    lose updates: final balance == exact arithmetic."""
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("u", points=100000)
        cm.save_users(force=True)

        N_ADD, N_PAY, OPS = 4, 4, 800
        barrier = threading.Barrier(N_ADD + N_PAY)

        def adder():
            barrier.wait()
            for _ in range(OPS):
                cm.add_points("u", 1)

        def payer():
            barrier.wait()
            for _ in range(OPS):
                cm.pay_for_command("u", 1)

        th = [threading.Thread(target=adder) for _ in range(N_ADD)]
        th += [threading.Thread(target=payer) for _ in range(N_PAY)]
        for t in th:
            t.start()
        for t in th:
            t.join()

        final = cm.get_points("u")
        expected = 100000 + N_ADD * OPS - N_PAY * OPS
        assert final == expected, (
            "LOST UPDATES: final=%s expected=%s (drift %s)"
            % (final, expected, final - expected)
        )
    finally:
        drop_tmpdir(d)


async def test_reliability_concurrent_pay_never_overdraws():
    """Many threads racing to pay a fixed-cost command: total deducted must
    never exceed the starting balance (no overdraw / negative balance)."""
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        START = 1000
        COST = 10
        cm.add_user("u", points=START)
        cm.save_users(force=True)

        successes = []
        slock = threading.Lock()
        barrier = threading.Barrier(8)

        def payer():
            barrier.wait()
            for _ in range(60):
                if cm.pay_for_command("u", COST):
                    with slock:
                        successes.append(1)

        th = [threading.Thread(target=payer) for _ in range(8)]
        for t in th:
            t.start()
        for t in th:
            t.join()

        final = cm.get_points("u")
        expected = START - len(successes) * COST
        assert final == expected, (
            "overdraw/lost: final=%s expected=%s (successes=%d)"
            % (final, expected, len(successes))
        )
        assert final >= 0, "balance went negative: %s" % final
        # Max possible successes is bounded by the balance.
        assert len(successes) <= START // COST
    finally:
        drop_tmpdir(d)


async def test_reliability_concurrent_add_total_exact():
    """Pure add race: N threads each adding OPS points -> total is exact."""
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("u", points=0)
        N, OPS = 6, 500
        barrier = threading.Barrier(N)

        def adder():
            barrier.wait()
            for _ in range(OPS):
                cm.add_points("u", 1)

        th = [threading.Thread(target=adder) for _ in range(N)]
        for t in th:
            t.start()
        for t in th:
            t.join()

        assert cm.get_points("u") == N * OPS, (
            "add race lost updates: %s != %s" % (cm.get_points("u"), N * OPS)
        )
    finally:
        drop_tmpdir(d)


# ---------------------------------------------------------------------------
# Validation (the layer that "fixed" losses before — must still reject bad input)
# ---------------------------------------------------------------------------

async def test_reliability_validation_rejects_bad_amounts():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("u", points=100)
        before = cm.get_points("u")

        # Each of these must be rejected: balance unchanged.
        for bad in (float("nan"), float("inf"), float("-inf"),
                    10_000_000, 0.001, -5):
            cm.add_points("u", bad)
            assert cm.get_points("u") == before, (
                "add_points accepted invalid amount %r -> %s"
                % (bad, cm.get_points("u"))
            )
    finally:
        drop_tmpdir(d)


# ---------------------------------------------------------------------------
# Corruption -> backup recovery
# ---------------------------------------------------------------------------

async def test_reliability_corrupt_file_recovers_from_backup():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("alice", points=500)
        cm.save_users(force=True)
        # Make a known-good backup.
        cm.create_backup(force=True)

        # Corrupt the live file (simulate a torn write).
        with open(cm.users_file, "w", encoding="utf-8") as f:
            f.write("{ this is not valid json ]]]")

        # Reload must detect corruption and recover from backup.
        cm.load_data()
        assert cm.get_points("alice") == 500, (
            "recovery failed: alice=%s (expected 500 from backup)"
            % cm.get_points("alice")
        )
    finally:
        drop_tmpdir(d)


async def test_reliability_backup_restore_roundtrip():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("bob", points=321)
        cm.save_users(force=True)
        cm.create_backup(force=True)

        backups = cm.get_available_backups()
        assert backups, "no backup available after create_backup(force=True)"
        latest = backups[0]["path"]  # list is newest-first

        # Wipe the live file, then restore from the backup.
        os.remove(cm.users_file)
        ok = cm.restore_from_backup(latest)
        assert ok is True, "restore_from_backup returned False"
        assert cm.get_points("bob") == 321, (
            "restore lost data: bob=%s" % cm.get_points("bob")
        )
    finally:
        drop_tmpdir(d)


async def test_reliability_integrity_detects_corruption():
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        cm.add_user("alice", points=10)
        cm.save_users(force=True)

        with open(cm.users_file, "w", encoding="utf-8") as f:
            f.write("not json at all")

        res = cm.validate_data_integrity()
        assert res["is_valid"] is False, (
            "integrity check must flag corrupt file, got %s" % res
        )
    finally:
        drop_tmpdir(d)


# ---------------------------------------------------------------------------
# Multi-user isolation under concurrency
# ---------------------------------------------------------------------------

async def test_reliability_multi_user_isolation():
    """Concurrent adds across distinct users: each user's total is exact and
    no user's balance leaks into another."""
    d = new_tmpdir()
    try:
        cm = make_real_currency(d)
        users = ["u%d" % i for i in range(8)]
        for u in users:
            cm.add_user(u, points=0)
        OPS = 300
        barrier = threading.Barrier(len(users))

        def adder(u):
            barrier.wait()
            for _ in range(OPS):
                cm.add_points(u, 1)

        th = [threading.Thread(target=adder, args=(u,)) for u in users]
        for t in th:
            t.start()
        for t in th:
            t.join()

        for u in users:
            assert cm.get_points(u) == OPS, (
                "user %s: %s != %s" % (u, cm.get_points(u), OPS)
            )
    finally:
        drop_tmpdir(d)