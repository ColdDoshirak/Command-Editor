"""Step 4.1: package layout.

core/  - no Qt, never imports bot/ or ui/
bot/   - no Qt, never imports ui/
ui/    - Qt; the window's tabs, theme and the bridge to the bot
command_editor.py stays the entry point at the top.

Py3.8 compatible.
"""
import os
import re

from harness import REPO_DIR

_IMPORT = re.compile(r"^[ \t]*(?:from|import)[ \t]+([\w.]+)", re.M)


def _imports(pkg):
    out = []
    d = os.path.join(REPO_DIR, pkg)
    for n in sorted(os.listdir(d)):
        if n.endswith(".py"):
            with open(os.path.join(d, n), encoding="utf-8") as f:
                for m in _IMPORT.finditer(f.read()):
                    out.append((pkg + "/" + n, m.group(1)))
    return out


def _bad(pkg, forbidden):
    return [(f, mod) for f, mod in _imports(pkg)
            if any(mod == x or mod.startswith(x + ".") for x in forbidden)]


async def test_core_has_no_qt_and_no_upward_imports():
    bad = _bad("core", ("PyQt5", "bot", "ui", "twitch_bot", "command_editor"))
    assert not bad, bad


async def test_bot_has_no_qt_and_does_not_import_the_window():
    bad = _bad("bot", ("PyQt5", "ui", "command_editor"))
    assert not bad, bad


async def test_only_the_entry_point_stays_at_the_top():
    top = sorted(n for n in os.listdir(REPO_DIR) if n.endswith(".py"))
    assert top == ["command_editor.py"], top


async def test_pyflakes_clean():
    """Undefined names and unused imports/variables (requirements-dev.txt).
    Skipped when pyflakes is not installed."""
    import subprocess
    import sys
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        return
    out = subprocess.run([sys.executable, "-m", "pyflakes", "command_editor.py", "core", "bot", "ui"],
                         cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    lines = [l for l in out.decode("utf-8", "replace").splitlines()
             if "f-string is missing placeholders" not in l
             and not l.replace("\\", "/").startswith("ui/theme/__init__.py")]   # re-exports
    assert not lines, "\n".join(lines[:20])
