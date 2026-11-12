"""Choosing a sound file / folder in every editor writes only that field.

Bug found in 2.0 work: the themed editors' Browse went through
CommandEditor.browse_file, which also saved the chosen file into column 12
(FKSoundFile) for any field that was not the classic one - the command's
FK sound was overwritten with its main sound.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    from PyQt5.QtWidgets import QFileDialog
    w, check, pump = k.w, k.check, k.pump
    picked = {"file": os.path.join(DATA, "picked.wav"), "dir": os.path.join(DATA, "picked_dir")}
    open(picked["file"], "wb").close()
    os.makedirs(picked["dir"], exist_ok=True)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **kw: (picked["file"], ""))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **kw: picked["dir"])
    for i in range(len(w.commands)):
        w.command_repo.update(i, {"FKSoundFile": "fk-%d.wav" % i})
    w.save_commands(); pump()

    def fk_untouched():
        return [c.get("FKSoundFile") for c in w.commands] == ["fk-%d.wav" % i for i in range(len(w.commands))]

    # classic
    w.table.selectRow(1); pump()
    w.sound_file_btn.click(); pump()
    check("classic Browse: SoundFile set", w.commands[1]["SoundFile"] == picked["file"])
    check("classic Browse: FK untouched", fk_untouched(), [c.get("FKSoundFile") for c in w.commands])
    w.sound_folder_btn.click(); pump()
    check("classic Folder: SoundFile is the folder", w.commands[1]["SoundFile"] == picked["dir"])

    # sidebar theme editor
    w.apply_theme("sidebar"); pump(300)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(3); pump()
    v.detail.browse_btn.click(); pump(500)
    v.detail.flush(); pump()
    check("themed Browse: SoundFile set", w.commands[3]["SoundFile"] == picked["file"],
          w.commands[3]["SoundFile"])
    check("themed Browse: no FK written anywhere", fk_untouched(), [c.get("FKSoundFile") for c in w.commands])
    v.detail.folder_btn.click(); pump(500)
    v.detail.flush(); pump()
    check("themed Folder: SoundFile is the folder", w.commands[3]["SoundFile"] == picked["dir"])

    # spreadsheet toolbar
    w.apply_theme("spreadsheet"); pump(300)
    v = w.themed_commands_view
    v.select_from_table(4); pump()
    v._browse(); pump(300)
    check("spreadsheet Sound...: SoundFile set", w.commands[4]["SoundFile"] == picked["file"],
          w.commands[4]["SoundFile"])
    check("spreadsheet Sound...: no FK written anywhere", fk_untouched(),
          [c.get("FKSoundFile") for c in w.commands])
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
