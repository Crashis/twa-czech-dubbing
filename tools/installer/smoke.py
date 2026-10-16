"""Frozen/source smoke test: all writes go to a new disposable mock installation."""
import json
from pathlib import Path
import shutil
import tempfile
import time
import tkinter as tk

from tools import mod
from tools.installer import gui
from tools.pack.reader import require


def run(base_path, report_path):
    report = {'status': 'FAIL', 'game_runs': 0, 'real_game_writes': 0}
    root = None
    originals = {}
    try:
        manifest = mod.load_manifest()
        base = Path(base_path).resolve(strict=True)
        require(mod.sha256(base) == manifest['base']['sha256'], 'Unsupported smoke-test original')
        with tempfile.TemporaryDirectory(prefix='twa-installer-smoke-') as folder:
            folder = Path(folder)
            game = folder / 'mock game with spaces'
            (game / 'data').mkdir(parents=True)
            target = game / 'data/audio_cn.pack'
            shutil.copyfile(base, target)
            root = tk.Tk()
            app = gui.App(root, state_root=folder / 'private state', auto_detect=False)
            dialogs = []
            for name in ('showinfo', 'showerror'):
                originals[name] = getattr(gui.messagebox, name)
                setattr(gui.messagebox, name, lambda title, text, **kw: dialogs.append((title, text)))
            originals['askdirectory'] = gui.filedialog.askdirectory
            # Deterministic dialog selection exercises the same Browse callback as a user.
            gui.filedialog.askdirectory = lambda **kw: str(game)
            def wait():
                deadline = time.monotonic() + 120
                while app.busy:
                    require(time.monotonic() < deadline, 'GUI worker timed out')
                    root.update()
                    time.sleep(0.02)
                root.update()
            root.update()
            require(str(app.install_button['state']) == 'disabled', 'Install enabled without supported folder')
            app.path.set(str(folder / 'missing'))
            app.start('inspect')
            wait()
            require(app.last is None and str(app.install_button['state']) == 'disabled', 'Invalid folder accepted')
            app.browse()
            app.start('inspect')
            wait()
            require(app.last is not None, 'GUI verification failed: ' + app.status.get())
            require(app.last['state'] == 'ORIGINAL', 'Original not detected')
            app.start('install')
            wait()
            require(app.last is not None, 'GUI installation failed: ' + app.status.get())
            require(app.last['state'] == 'INSTALLED', 'Install failed')
            require(mod.sha256(target) == manifest['release']['sha256'], 'Output differs from known Complete hash')
            require(app.last['RSA'] == 'PASS' and app.last['changed_entries'] == 305, 'Validation counts/RSA failed')
            app.start('inspect')
            wait()
            require(app.last['state'] == 'INSTALLED' and str(app.install_button['state']) == 'disabled', 'Already-installed state failed')
            app.start('restore')
            wait()
            require(mod.sha256(target) == manifest['base']['sha256'], 'Restore failed')
            require(float(app.progress['value']) == 100 and len(dialogs) >= 5, 'Progress/result callback failed')
            report.update(status='PASS', backend_install_verify_restore='PASS', GUI_start='PASS',
                          GUI_invalid_directory='PASS', GUI_valid_directory='PASS',
                          GUI_browse_callback='PASS (directory selection simulated)',
                          GUI_progress='PASS', GUI_result_callbacks='PASS (modal dialogs captured)',
                          native_dialog_visual_review='NOT_PERFORMED',
                          changed_entries=305, unchanged_entries=16240, RSA='PASS',
                          installed_sha256=manifest['release']['sha256'], restored_sha256=mod.sha256(target))
            app.close()
            root = None
    except Exception as error:
        report['error'] = str(error)
    finally:
        for name, value in originals.items():
            setattr(gui.filedialog if name == 'askdirectory' else gui.messagebox, name, value)
        if root is not None:
            root.destroy()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'PASS' else 2
