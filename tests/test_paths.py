"""Tests for core.paths: one data folder, no working-directory files.

Py3.8 compatible.
"""
import os
from pathlib import Path

from harness import new_tmpdir, drop_tmpdir, make_config_manager, make_real_currency

from core import paths


def _write(p, text="x"):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


async def test_default_dir_is_project_root():
    saved = paths._override
    try:
        paths.set_app_dir(None)
        env = os.environ.pop(paths.ENV_HOME, None)
        try:
            root = Path(__file__).resolve().parent.parent
            assert paths.app_dir() == root, paths.app_dir()
            assert paths.resource_dir() == root
        finally:
            if env is not None:
                os.environ[paths.ENV_HOME] = env
    finally:
        paths._override = saved


async def test_env_var_and_override():
    saved = paths._override
    tmp = new_tmpdir()
    try:
        paths.set_app_dir(None)
        os.environ[paths.ENV_HOME] = tmp
        assert paths.app_dir() == Path(tmp)
        other = os.path.join(tmp, "other")
        paths.set_app_dir(other)
        assert paths.app_dir() == Path(other), "set_app_dir wins over the env var"
        assert paths.ranks_file() == Path(other) / "data" / "ranks.json"
    finally:
        os.environ.pop(paths.ENV_HOME, None)
        paths._override = saved
        drop_tmpdir(tmp)


async def test_managers_use_data_folder_not_cwd():
    tmp = new_tmpdir()
    cwd = os.getcwd()
    elsewhere = new_tmpdir()
    try:
        os.chdir(elsewhere)  # the bug: files used to follow the working dir
        cm = make_config_manager(tmp)
        cur = make_real_currency(tmp)
        assert Path(cm.config_file).parent == Path(tmp)
        cur.settings["name"] = "Coins"
        assert cur.save_settings()
        assert (Path(tmp) / "data" / "currency_settings.json").exists()
        assert not (Path(elsewhere) / "data").exists(), "nothing may be written to the cwd"
        cur.ranks = [{"name": "Fan", "required": 10}]
        cur.save_ranks()
        assert (Path(tmp) / "data" / "ranks.json").exists(), \
            "same file the Ranks tab reads (was ranks.json in the root)"
    finally:
        os.chdir(cwd)
        drop_tmpdir(tmp)
        drop_tmpdir(elsewhere)


async def test_migration_copies_missing_only():
    saved = paths._override
    home, old = new_tmpdir(), new_tmpdir()
    try:
        paths.set_app_dir(home)
        _write(Path(old) / "data" / "ranks.json", "old ranks")
        _write(Path(old) / "data" / "currency_settings.json", "old settings")
        _write(Path(old) / "command_history" / "commands_1.json", "h1")
        _write(Path(home) / "data" / "currency_settings.json", "NEW settings")
        copied = paths.migrate_from_cwd(old)
        names = sorted(Path(d).name for _s, d in copied)
        assert names == ["commands_1.json", "ranks.json"], names
        assert (Path(home) / "data" / "currency_settings.json").read_text(encoding="utf-8") == \
            "NEW settings", "existing files are never overwritten"
        assert (Path(old) / "data" / "ranks.json").exists(), "sources are never deleted"
        assert paths.migrate_from_cwd(old) == [], "second run copies nothing"
    finally:
        paths._override = saved
        drop_tmpdir(home)
        drop_tmpdir(old)


async def test_migration_ignores_unrelated_folders():
    saved = paths._override
    home, other = new_tmpdir(), new_tmpdir()
    try:
        paths.set_app_dir(home)
        _write(Path(other) / "commands.json", "someone else's file")
        assert paths.migrate_from_cwd(other) == []
        assert not (Path(home) / "commands.json").exists()
        assert paths.migrate_from_cwd(home) == [], "same folder: nothing to do"
    finally:
        paths._override = saved
        drop_tmpdir(home)
        drop_tmpdir(other)
