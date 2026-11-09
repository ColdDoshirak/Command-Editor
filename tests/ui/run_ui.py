"""Run the UI checks against the real window, one process per script.

Usage:
    python tests/ui/run_ui.py                 # all checks
    python tests/ui/run_ui.py -k themes       # scripts whose name contains 'themes'
    python tests/ui/run_ui.py --shots DIR     # also save screenshots to DIR
    python tests/ui/run_ui.py --keep          # keep the temporary data folders

Each script gets a fresh temporary data folder (COMMAND_EDITOR_HOME) with
synthetic commands and generated sounds; the developer's own data is never
touched. Needs a desktop session (a real window opens) and an audio device
for check_live_queue.

Exit code: 0 if every check passed, 1 otherwise. Py3.8 compatible.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = [
    "check_themes.py",
    "check_views.py",
    "check_theme_switch.py",
    "check_live_queue.py",
    "check_bot_bridge.py",
    "check_data_safety.py",
    "check_crash_log.py",
    "check_single_config.py",
    "check_ranks.py",
    "check_twitch_reconnect.py",
    "check_commands_model.py",
]
TIMEOUT = 180


def run_script(name, shots, keep):
    data = tempfile.mkdtemp(prefix="ce_ui_%s_" % name[:-3])
    cmd = [sys.executable, os.path.join(HERE, name), data]
    if shots:
        cmd.append(shots)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t = time.time()
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=TIMEOUT)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", "timeout after %ds" % TIMEOUT, -1
    finally:
        if keep:
            print("  data kept in %s" % data)
        else:
            shutil.rmtree(data, ignore_errors=True)
    lines = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "      "))]
    passed = sum(1 for l in lines if l.startswith("PASS"))
    failed = sum(1 for l in lines if l.startswith("FAIL"))
    if passed + failed == 0 or code != 0:
        failed += 1
        lines.append("FAIL  %s did not finish cleanly (exit %s)\n      %s"
                     % (name, code, err.strip()[-2000:].replace("\n", "\n      ")))
    return passed, failed, lines, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    ap.add_argument("--shots", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("-v", action="store_true", help="print passing checks too")
    a = ap.parse_args()
    if a.shots:
        a.shots = os.path.abspath(a.shots)
        os.makedirs(a.shots, exist_ok=True)
    total_p = total_f = 0
    for name in SCRIPTS:
        if a.k not in name:
            continue
        p, f, lines, dt = run_script(name, a.shots, a.keep)
        total_p += p
        total_f += f
        print("[%s] %-24s %d passed, %d failed (%.1fs)"
              % ("x" if f == 0 else " ", name, p, f, dt))
        for l in lines:
            if a.v or not l.startswith("PASS"):
                print("    " + l)
    print("-" * 60)
    print("UI checks: %d passed, %d failed" % (total_p, total_f))
    return 0 if total_f == 0 and total_p > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
