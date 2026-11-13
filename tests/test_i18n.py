"""Interface language (2.0, ui/i18n.py).

Py3.8 compatible. No window: only the language choice and the
translation table are checked here (the window: tests/ui/check_i18n.py).
"""
import ast
import os
import re

from harness import REPO_DIR


def _tr_literals():
    """Every literal passed to tr() in the program code: {text: [where]}."""
    found = {}
    files = [os.path.join(REPO_DIR, "command_editor.py")]
    for root, dirs, names in os.walk(os.path.join(REPO_DIR, "ui")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        files += [os.path.join(root, n) for n in names if n.endswith(".py") and n != "i18n_ru.py"]
    for path in files:
        src = open(path, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "N_") and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    found.setdefault(a.value, []).append("%s:%d" % (os.path.relpath(path, REPO_DIR), node.lineno))
    return found


def _ru():
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_ru_check", os.path.join(REPO_DIR, "ui", "i18n_ru.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RU


async def test_every_tr_text_has_a_russian_version():
    ru = _ru()
    missing = {t: w[:2] for t, w in _tr_literals().items() if t not in ru}
    assert not missing, "no Russian text for %d: %s" % (len(missing), list(missing.items())[:15])


async def test_translations_keep_their_placeholders():
    braces = re.compile(r"\{[^{}]*\}")
    # %-style is positional: the same placeholders IN THE SAME ORDER
    percent = re.compile(r"%(?:\(\w+\))?[-+ 0#]*\d*(?:\.\d+)?[sdfr%]")
    bad = [(en, ru) for en, ru in _ru().items()
           if sorted(braces.findall(en)) != sorted(braces.findall(ru))
           or percent.findall(en) != percent.findall(ru)]
    assert not bad, bad[:10]


async def test_no_russian_left_in_the_english_sources():
    """English is the source: Cyrillic inside tr("...") means a text that was
    translated the wrong way round."""
    cyr = [(t, w[0]) for t, w in _tr_literals().items() if re.search("[Ѐ-ӿ]", t)]
    assert not cyr, cyr[:10]


async def test_language_choice(monkeypatch=None):
    import ui.i18n as i18n
    old_env = os.environ.pop(i18n.ENV, None)
    old_sys = i18n.system_language
    try:
        i18n.system_language = lambda: "ru"
        assert i18n.resolve("system") == "ru" and i18n.resolve(None) == "ru"
        assert i18n.resolve("en") == "en"
        i18n.system_language = lambda: "en"
        assert i18n.resolve("system") == "en" and i18n.resolve("ru") == "ru"
        assert i18n.resolve("de") == "en", "unknown -> the system's (here English)"
        os.environ[i18n.ENV] = "ru"
        assert i18n.resolve("en") == "ru", "the env override wins"
        i18n.set_language("ru")
        assert i18n.tr("Language") == "Язык" and i18n.tr("not translated") == "not translated"
        i18n.set_language("en")
        assert i18n.tr("Language") == "Language"
    finally:
        i18n.system_language = old_sys
        os.environ.pop(i18n.ENV, None)
        if old_env is not None:
            os.environ[i18n.ENV] = old_env
        i18n.set_language("en")
