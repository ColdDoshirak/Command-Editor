# -*- coding: utf-8 -*-
"""Re-linking of sound files that were moved or renamed folders.

Commands store absolute sound paths. When the user moves the sound folder,
every command breaks. This module finds the missing files and re-links them:

  * by folder search — index a folder (recursively) and match missing files
    by file name; when several files share a name the one whose parent
    folders match the old path best wins (ties are reported as ambiguous);
  * by prefix replace — "D:/Old/Sounds" -> "E:/Stream/Sounds".

Folders used successfully are remembered in config.json ("sound_folders"),
and on start-up missing sounds are re-linked from them automatically.

No Qt here (tested in tests/test_sound_paths.py); the dialog is
ui/sound_relink.py. Python 3.8 compatible.
"""
import os

SOUND_KEYS = ("SoundFile", "FKSoundFile")
SOUND_EXTS = (".wav", ".mp3", ".ogg", ".flac")
MAX_REMEMBERED = 5


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


def _parts(p):
    p = os.path.normpath(p).replace("\\", "/")
    return [x.lower() for x in p.split("/") if x]


def find_missing(commands, exists=os.path.exists):
    """[(row, key, path)] for every non-empty sound path that does not exist."""
    out = []
    for row, cmd in enumerate(commands):
        for key in SOUND_KEYS:
            path = str(cmd.get(key, "") or "").strip()
            if path and not exists(path):
                out.append((row, key, path))
    return out


def index_folder(folder, exts=SOUND_EXTS):
    """{lower-case file name: [full paths]} for sound files under folder."""
    idx = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].lower() in exts:
                idx.setdefault(name.lower(), []).append(os.path.join(root, name))
    return idx


def _tail_score(old, new):
    """How many trailing path components (after the file name) match."""
    a, b = _parts(old)[:-1], _parts(new)[:-1]
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def best_match(old_path, candidates):
    """(path, ambiguous) — the candidate whose folders match old_path best."""
    if not candidates:
        return None, False
    if len(candidates) == 1:
        return candidates[0], False
    scored = sorted(((_tail_score(old_path, c), c) for c in candidates),
                    key=lambda t: (-t[0], t[1].lower()))
    ambiguous = scored[0][0] == scored[1][0]
    return scored[0][1], ambiguous


def plan_from_folders(commands, folders, exists=os.path.exists, index_cache=None):
    """Plan re-links of missing sounds from one or more folders.

    Returns a list of dicts: row, key, old, new (None if not found),
    ambiguous (bool). Earlier folders win over later ones.
    """
    missing = find_missing(commands, exists)
    if not missing:
        return []
    indexes = []
    for f in folders:
        if not f or not os.path.isdir(f):
            continue
        if index_cache is not None and f in index_cache:
            indexes.append(index_cache[f])
            continue
        idx = index_folder(f)
        if index_cache is not None:
            index_cache[f] = idx
        indexes.append(idx)
    plan = []
    for row, key, old in missing:
        name = os.path.basename(old.replace("\\", "/")).lower()
        new, ambiguous = None, False
        for idx in indexes:
            new, ambiguous = best_match(old, idx.get(name, []))
            if new:
                break
        plan.append({"row": row, "key": key, "old": old, "new": new, "ambiguous": ambiguous})
    return plan


def plan_prefix_replace(commands, old_prefix, new_prefix, only_missing=True,
                        exists=os.path.exists):
    """Plan replacing a folder prefix. Only targets that exist are accepted."""
    if not old_prefix:
        return []
    op = _norm(old_prefix).rstrip("\\/")
    plan = []
    for row, cmd in enumerate(commands):
        for key in SOUND_KEYS:
            path = str(cmd.get(key, "") or "").strip()
            if not path:
                continue
            if only_missing and exists(path):
                continue
            np_ = _norm(path)
            if np_ != op and not np_.startswith(op + os.sep):
                continue
            rest = os.path.normpath(path)[len(op):].lstrip("\\/")
            new = os.path.join(new_prefix, rest) if rest else new_prefix
            plan.append({"row": row, "key": key, "old": path,
                         "new": new if exists(new) else None, "ambiguous": False})
    return plan


def common_folder(paths):
    """Deepest folder shared by all paths ('' if none)."""
    dirs = [os.path.dirname(os.path.normpath(p)) for p in paths if p]
    if not dirs:
        return ""
    try:
        return os.path.commonpath(dirs)
    except ValueError:  # different drives
        return dirs[0]


def plan_to_changes(plan):
    """{row: {key: new}} for the plan entries that have a target."""
    changes = {}
    for p in plan:
        if p.get("new"):
            changes.setdefault(p["row"], {})[p["key"]] = p["new"]
    return changes


def remember_folder(folders, folder):
    """New list with folder first (deduplicated, capped)."""
    out = [folder]
    for f in folders or []:
        if f and _norm(f) != _norm(folder):
            out.append(f)
    return out[:MAX_REMEMBERED]
