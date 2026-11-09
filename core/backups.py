"""Full ("comprehensive") system backups: commands, currency users, ranks,
moderators and settings in one JSON file (step 4.3; was ~400 lines of the
main window).

Layout of the backup folder (unchanged, old backups stay readable):
    system_backup_<YYYYmmdd_HHMMSS>[_N].json        the data
    system_backup_<YYYYmmdd_HHMMSS>[_N].json.meta   counts and size for the list

Command-only backups (the History tab) are core/history_manager.py.

Python 3.8 compatible. No Qt.
"""
import copy
import json
import time
from datetime import datetime
from pathlib import Path

from core import storage

PREFIX = "system_backup_"
FORMAT_VERSION = "1.0"


def human_size(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / (1024.0 * 1024.0))


def _meta_path(path):
    return Path(str(path) + ".meta")


class FullBackups(object):
    def __init__(self, folder):
        self.folder = Path(folder)

    # -- making a backup ---------------------------------------------------------
    def collect(self, commands, currency=None, config=None, history=None):
        """Everything a full backup holds, as plain data (copies)."""
        data = {
            "backup_info": {
                "timestamp": datetime.now().isoformat(),
                "version": FORMAT_VERSION,
                "description": "Comprehensive system backup created during operation",
            },
            "commands": copy.deepcopy(list(commands or [])),
            "currency_users": {},
            "moderators": {"manual": [], "excluded": []},
            "config": {},
            "ranks": [],
            "command_history": {},
            "currency_settings": {},
        }
        if currency is not None:
            # the bot thread changes users while we copy: hold its lock
            lock = getattr(currency, "users_lock", None)
            if lock is not None:
                with lock:
                    data["currency_users"] = copy.deepcopy(getattr(currency, "users", {}) or {})
            else:
                data["currency_users"] = copy.deepcopy(getattr(currency, "users", {}) or {})
            data["ranks"] = copy.deepcopy(list(getattr(currency, "ranks", []) or []))
            data["currency_settings"] = {
                "settings": copy.deepcopy(getattr(currency, "settings", {}) or {}),
                "backup_dir": str(getattr(currency, "backup_dir", "")),
                "max_backups": getattr(currency, "max_currency_backups", 10),
            }
        if config is not None:
            try:
                data["moderators"] = {"manual": list(config.get_manual_moderators()),
                                      "excluded": list(config.get_excluded_moderators())}
            except Exception as e:
                print(f"Full backup: moderators not saved: {e}")
            try:
                data["config"] = {
                    "volume": config.get_volume(),
                    "sound_interruption": config.get_sound_interruption(),
                    "interruption_message": config.get_interruption_message(),
                    "auto_save": config.get_auto_save(),
                    "max_backups": config.get_max_backups(),
                    # Only the channel: the rest of twitch_config.json is the
                    # OAuth token, which does not belong in a backup file
                    # (restore never used it).
                    "twitch_config": {"channel": (config.get_twitch_config() or {}).get("channel", "")},
                }
            except Exception as e:
                print(f"Full backup: settings not saved: {e}")
        if history is not None:
            data["command_history"] = {
                "max_backups": getattr(history, "max_backups", None),
                "backup_dir": str(getattr(history, "history_folder", "")),
            }
        return data

    def _new_path(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.folder / ("%s%s.json" % (PREFIX, stamp))
        n = 2
        while path.exists():                 # two backups in the same second
            path = self.folder / ("%s%s_%d.json" % (PREFIX, stamp, n))
            n += 1
        return path

    def create(self, data, keep=None):
        """Write a backup (+ its .meta); keep the newest `keep`. Returns the path."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._new_path()
        storage.atomic_write_json(path, data, indent=2)
        meta = {
            "backup_time": time.time(),
            "backup_name": path.stem,
            "commands_count": len(data.get("commands") or []),
            "users_count": len(data.get("currency_users") or {}),
            "moderators_count": len((data.get("moderators") or {}).get("manual", [])),
            "total_size": path.stat().st_size,
            "version": (data.get("backup_info") or {}).get("version", FORMAT_VERSION),
        }
        storage.atomic_write_json(_meta_path(path), meta, indent=2, ensure_ascii=True)
        print(f"[COMPREHENSIVE BACKUP] Created backup: {path.name}")
        if keep:
            self.cleanup(keep)
        return path

    # -- the list -----------------------------------------------------------------
    def _files(self):
        if not self.folder.exists():
            return []
        files = list(self.folder.glob(PREFIX + "*.json"))
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def entries(self):
        """Backups, newest first: dicts path, name, meta, size, size_text, error."""
        out = []
        for path in self._files():
            meta, error = {}, None
            try:
                mp = _meta_path(path)
                if mp.exists():
                    with open(str(mp), "r", encoding="utf-8") as f:
                        meta = json.load(f)
            except Exception as e:
                error = str(e)
            try:
                size = int(meta.get("total_size", path.stat().st_size))
            except Exception:
                size = 0
            out.append({"path": path, "name": path.stem, "meta": meta, "size": size,
                        "size_text": human_size(size), "error": error})
        return out

    def cleanup(self, keep):
        """Delete all but the newest `keep` backups. Returns the removed paths."""
        removed = []
        for old in self._files()[max(1, int(keep)):]:
            try:
                old.unlink()
                mp = _meta_path(old)
                if mp.exists():
                    mp.unlink()
                removed.append(old)
                print(f"[COMPREHENSIVE BACKUP] Removed old backup: {old.name}")
            except Exception as e:
                print(f"[COMPREHENSIVE BACKUP] Error removing old backup {old}: {e}")
        return removed

    # -- restoring --------------------------------------------------------------------
    @staticmethod
    def load(path):
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def restore(data, currency=None, config=None):
        """Put users, ranks, moderators and settings back.

        Commands are returned (out["commands"], None if the backup has none)
        for the window to apply through its CommandRepository. Moderators are
        added to the current lists (not replacing them), as before.
        """
        out = {"commands": None, "users": None, "ranks": False,
               "moderators": False, "config": False}
        if isinstance(data.get("commands"), list):
            out["commands"] = data["commands"]

        if currency is not None and isinstance(data.get("currency_users"), dict):
            users = copy.deepcopy(data["currency_users"])
            lock = getattr(currency, "users_lock", None)
            if lock is not None:
                with lock:
                    currency.users = users
            else:
                currency.users = users
            # force: without it save_users() returns early when nothing was
            # pending, and the restored users never reach the disk (S5)
            currency.save_users(force=True)
            out["users"] = len(users)

        if currency is not None and isinstance(data.get("ranks"), list):
            # set_ranks: same list object for the Ranks tab, saved, and every
            # user's rank recalculated for the restored thresholds
            currency.set_ranks(data["ranks"])
            out["ranks"] = True

        mods = data.get("moderators")
        if config is not None and isinstance(mods, dict):
            try:
                for m in mods.get("manual", []) or []:
                    config.add_manual_moderator(m)
                for m in mods.get("excluded", []) or []:
                    config.add_excluded_moderator(m)
                out["moderators"] = True
            except Exception as e:
                print(f"Error restoring moderators: {e}")

        cfg = data.get("config")
        if config is not None and isinstance(cfg, dict) and cfg:
            try:
                if "volume" in cfg:
                    config.set_volume(cfg["volume"])
                if "sound_interruption" in cfg:
                    config.set_sound_interruption(cfg["sound_interruption"])
                if "interruption_message" in cfg:
                    config.set_interruption_message(cfg["interruption_message"])
                if "auto_save" in cfg and isinstance(cfg["auto_save"], dict):
                    config.set_auto_save(cfg["auto_save"].get("enabled", True),
                                         cfg["auto_save"].get("interval", 300))
                if "max_backups" in cfg:
                    config.set_max_backups(cfg["max_backups"])
                channel = (cfg.get("twitch_config") or {}).get("channel")
                if channel:
                    config.set_twitch_channel(channel)
                out["config"] = True
            except Exception as e:
                print(f"Error restoring config: {e}")
        return out
