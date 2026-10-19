"""Small ttk frontend. Long reads/builds run off the Tk event thread."""
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tools.installer.backend import Installer, known_game_folders, state_directory
from tools.installer.catalog import discover, selection
from tools.pack.reader import require
from tools.resources import VERSION


class App:
    def __init__(self, root, *, state_root=None, auto_detect=True):
        self.root = root
        self.state_root = Path(state_root) if state_root is not None else state_directory()
        self.available_commanders = discover()
        if not self.available_commanders:
            raise ValueError('No dubbing payload found. Extract the complete release ZIP before running the installer.')
        self.events = queue.Queue()
        self.busy = False
        self.last = None
        self.installed_commanders = frozenset()
        self.pending_commanders = frozenset()
        self.path = tk.StringVar(root)
        self.status = tk.StringVar(root, value='Select your Total War: Arena folder to begin.')
        self.selection_status = tk.StringVar(root)
        self.source_status = tk.StringVar(root)
        self.choices = [(m, tk.BooleanVar(root, value=False)) for m in self.available_commanders]
        self.timer = None
        root.title('Total War: Arena – Czech Dubbing')
        root.geometry('740x805')
        root.minsize(680, 770)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'))
        style.configure('Subtitle.TLabel', font=('Segoe UI', 14))
        style.configure('Action.TButton', font=('Segoe UI', 11, 'bold'), padding=(18, 10))
        frame = ttk.Frame(root, padding=28)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(11, weight=1)
        ttk.Label(frame, text='Total War: Arena', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(frame, text='Czech Dubbing', style='Subtitle.TLabel').grid(row=1, column=0, sticky='w', pady=(0, 18))
        box = ttk.LabelFrame(frame, text='Available dubbing — select changes, then click Install', padding=12)
        box.grid(row=2, column=0, sticky='ew', pady=(0, 18))
        self.checks = []
        for manifest, var in self.choices:
            check = ttk.Checkbutton(box, text=f"{manifest['display_name']}  —  {manifest['replacement_count']} / {manifest['spoken_count']} lines",
                                    variable=var, command=self.selection_changed)
            check.pack(anchor='w', pady=2)
            self.checks.append(check)
        ttk.Label(frame, text='Game folder').grid(row=3, column=0, sticky='w', pady=(0, 5))
        paths = ttk.Frame(frame)
        paths.grid(row=4, column=0, sticky='ew')
        paths.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(paths, textvariable=self.path)
        self.entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.browse_button = ttk.Button(paths, text='Browse…', command=self.browse)
        self.browse_button.grid(row=0, column=1)
        ttk.Label(frame, textvariable=self.status, wraplength=650).grid(row=5, column=0, sticky='w', pady=(14, 6))
        ttk.Label(frame, textvariable=self.selection_status, wraplength=650).grid(row=6, column=0, sticky='w', pady=(0, 6))
        ttk.Label(frame, textvariable=self.source_status, wraplength=650).grid(row=7, column=0, sticky='w', pady=(0, 14))
        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, sticky='ew')
        self.install_button = ttk.Button(actions, text='Install', style='Action.TButton', command=lambda: self.start('install'))
        self.install_button.pack(side='left')
        self.verify_button = ttk.Button(actions, text='Verify', command=lambda: self.start('inspect'))
        self.verify_button.pack(side='left', padx=10)
        self.restore_button = ttk.Button(actions, text='Restore Original', command=self.confirm_restore)
        self.restore_button.pack(side='left')
        self.progress = ttk.Progressbar(frame, mode='determinate', maximum=100)
        self.progress.grid(row=9, column=0, sticky='ew', pady=(18, 10))
        ttk.Label(frame, text='Status log').grid(row=10, column=0, sticky='w')
        self.log = tk.Text(frame, height=8, wrap='word', font=('Consolas', 9), relief='solid', borderwidth=1, state='disabled')
        self.log.grid(row=11, column=0, sticky='nsew', pady=(6, 12))
        ttk.Label(frame, text=f'Version {VERSION}  ·  Close the game and launcher before installing or restoring.').grid(row=12, column=0, sticky='w')
        self.path.trace_add('write', lambda *_: self.folder_changed())
        self.controls()
        self.poll_id = root.after(80, self.poll)
        if auto_detect:
            found = known_game_folders()
            if len(found) == 1:
                self.path.set(str(found[0]))

    def selected(self):
        # Read the current widgets at the explicit Install click, never a startup cache.
        return selection([m for m, var in self.choices if var.get()])

    def selection_changed(self):
        # Selection is local UI state. This callback must never schedule backend work.
        self.pending_commanders = frozenset(m['commander'] for m, var in self.choices if var.get())
        self.controls()

    def folder_changed(self):
        self.last = None
        self.installed_commanders = frozenset()
        self.set_pending(())
        self.status.set('Checking folder…' if self.path.get().strip() else 'Select your Total War: Arena folder to begin.')
        self.controls()
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.path.get().strip():
            self.timer = self.root.after(700, lambda: self.start('inspect', quiet=True))

    def set_pending(self, commanders):
        self.pending_commanders = frozenset(commanders)
        for manifest, var in self.choices:
            var.set(manifest['commander'] in self.pending_commanders)

    def accept_verified_state(self, state):
        installed = frozenset(state.get('installed_commanders', ()))
        require(installed <= {m['commander'] for m in self.available_commanders},
                'Installed commander is missing from this release')
        self.last = state
        self.installed_commanders = installed
        # BooleanVar.set does not invoke Checkbutton.command; no backend callback here.
        self.set_pending(installed)

    def original_available(self):
        """A verified backup, clean current PACK or proven game file can supply original bytes."""
        last = self.last or {}
        return bool(last.get('original_source')) and last.get('backup_state') != 'INVALID'

    def removed_commanders(self):
        return [m['display_name'] for m in self.available_commanders
                if m['commander'] in self.installed_commanders - self.pending_commanders]

    def refresh_install_button_state(self):
        """One decision for startup, pending edits and every operation outcome.

        A missing backup never blocks adding dubbing. Only removing installed
        dubbing needs original bytes; an invalid backup blocks every write.
        """
        state = self.last.get('state') if self.last else None
        valid_folder = bool(self.path.get().strip()) and state in ('ORIGINAL', 'INSTALLED')
        selected_hash = None
        try:
            selected_hash = self.selected()['release']['sha256']
        except ValueError:
            pass
        matches = valid_folder and bool(self.pending_commanders) and self.pending_commanders == self.installed_commanders
        invalid = valid_folder and self.last.get('backup_state') == 'INVALID'
        needs_original = valid_folder and bool(self.removed_commanders()) and not self.original_available()
        enabled = (not self.busy and valid_folder and bool(self.pending_commanders)
                   and not matches and bool(selected_hash) and not invalid and not needs_original)
        self.install_button['state'] = 'normal' if enabled else 'disabled'
        self.install_button['text'] = 'Installed' if matches else 'Install'
        return matches, selected_hash, invalid, needs_original

    def source_text(self):
        last = self.last or {}
        if last.get('state') not in ('ORIGINAL', 'INSTALLED'):
            return ''
        source = last.get('original_source')
        if last.get('backup_state') == 'INVALID':
            return 'Original backup: INVALID. Install and Restore Original are disabled; no game files will be modified.'
        if source == 'BACKUP':
            return 'Original backup: verified. Restore Original and removing dubbing are available.'
        if source == 'CURRENT_PACK':
            return 'Original backup: will be created and verified before the first installation.'
        if source == 'GAME_FILE':
            return ('Original backup: missing. Verified original audio found in ' + last['original_source_file']
                    + ' (read-only); a backup will be created before the next change.')
        return ('Original backup: unavailable. Adding dubbing is possible; removing dubbing and '
                'Restore Original are disabled.')

    def controls(self):
        ready = bool(self.path.get().strip()) and not self.busy
        self.verify_button['state'] = 'normal' if ready else 'disabled'
        state = self.last.get('state') if self.last else None
        matches, selected_hash, invalid, needs_original = self.refresh_install_button_state()
        restorable = ready and state == 'INSTALLED' and self.original_available()
        self.restore_button['state'] = 'normal' if restorable else 'disabled'
        for control in [self.entry, self.browse_button]:
            control['state'] = 'disabled' if self.busy else 'normal'
        for check in self.checks:
            check['state'] = 'normal' if ready and state in ('ORIGINAL', 'INSTALLED') else 'disabled'
        if not self.last:
            text = 'Verify the game folder before selecting dubbing.'
        elif state == 'UNSUPPORTED':
            text = 'This game version is unsupported.'
        elif not self.pending_commanders:
            text = ('No dubbing selected. Use Restore Original to restore the original pack.'
                    if self.original_available() or state != 'INSTALLED' else
                    'No dubbing selected. Restore Original needs the original game audio backup.')
        elif matches:
            text = 'Selection matches the installed dubbing.'
        elif not selected_hash:
            text = 'This selection has no validated release.'
        elif invalid:
            text = 'The original backup is invalid; the installer will not modify game files.'
        elif needs_original:
            text = ('Original backup required to remove installed dubbing: '
                    + ' + '.join(self.removed_commanders()) + '.')
        else:
            names = ' + '.join(m['display_name'] for m in self.available_commanders
                               if m['commander'] in self.pending_commanders)
            text = 'Pending: ' + names + '. Click Install to apply.'
        self.selection_status.set(text)
        self.source_status.set(self.source_text())

    def browse(self):
        value = filedialog.askdirectory(parent=self.root, title='Select Total War: Arena folder', mustexist=True)
        if value:
            self.path.set(value)

    def confirm_restore(self):
        last = self.last or {}
        detail = ('after creating a verified backup from ' + last['original_source_file']
                  if last.get('original_source') == 'GAME_FILE' else 'from the verified backup')
        if messagebox.askyesno('Restore Original', 'Restore the original game audio ' + detail + '?', parent=self.root):
            self.start('restore')

    def start(self, action, quiet=False):
        if self.busy:
            return
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        try:
            require(action in ('install', 'inspect', 'restore'), 'Unknown installer action')
            if action == 'install':
                manifest = self.selected()
                snapshot = frozenset(manifest.get('components', [manifest['commander']]))
                require(self.last is not None and self.last['state'] in ('ORIGINAL', 'INSTALLED'),
                        'Verify the game folder before installing')
            else:
                # Inspect recognizes every known PACK; Restore uses the common canonical base.
                # Neither operation depends on a nonempty pending selection.
                manifest = self.available_commanders[0]
                snapshot = None
            service = Installer(manifest, self.state_root,
                                lambda p, m: self.events.put(('progress', (p, m))))
        except Exception as error:
            self.fail(error, quiet)
            return
        path = self.path.get().strip()
        self.busy = True
        self.progress['value'] = 0
        self.controls()
        def work():
            try:
                result = getattr(service, action)(path)
                state = result if action == 'inspect' else service.inspect(path)
                if action == 'install':
                    require(state['state'] == 'INSTALLED' and state['sha256'] == result['sha256']
                            and state['sha256'] == manifest['release']['sha256']
                            and frozenset(state['installed_commanders']) == snapshot
                            and state['changed_entries'] == result['changed_entries']
                            and state['RSA'] == 'PASS',
                            'Installed PACK does not match the requested commander selection')
                self.events.put(('done', (action, result, state, quiet)))
            except Exception as error:
                self.events.put(('error', (error, quiet)))
        threading.Thread(target=work, name='dubbing-installer', daemon=False).start()

    def append(self, text):
        self.log['state'] = 'normal'
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log['state'] = 'disabled'

    def record(self, action, result):
        # Explicit allowlist: no environment, exception traceback, credentials or request data.
        value = {k: result[k] for k in ('status', 'state', 'sha256', 'RSA', 'changed_entries',
                                     'unchanged_entries', 'installed_commanders', 'mode',
                                     'backup_created', 'backup_state', 'original_source') if k in result}
        value.update(action=action, timestamp=datetime.now(timezone.utc).isoformat())
        try:
            folder = self.state_root / 'logs'
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'installer.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(value, ensure_ascii=True) + '\n')
        except OSError:
            self.append('Technical log could not be saved.')

    def fail(self, error, quiet):
        self.busy = False
        self.last = None
        text = str(error)
        if 'Game/launcher is running' in text:
            text = 'Game or launcher is currently running. Close Total War: Arena and its launcher before continuing.'
        self.status.set(text)
        self.append(text)
        self.record('error', {'status': getattr(error, 'code', type(error).__name__)})
        self.controls()
        if not quiet:
            messagebox.showerror('Czech Dubbing', text, parent=self.root)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    percent, message = value
                    self.progress['value'] = percent
                    self.status.set(message)
                elif kind == 'error':
                    self.fail(*value)
                else:
                    action, result, state, quiet = value
                    self.busy = False
                    self.accept_verified_state(state)
                    self.status.set(state['message'])
                    if result.get('backup_created'):
                        self.append(f"Original backup created and verified: {result['backup_size']:,} bytes "
                                    f"from {result['backup_source']}.")
                    if result.get('mode') == 'ADDITIVE':
                        self.append('Added to the verified installed dubbing; no original backup was needed.')
                    self.append(state['message'])
                    if 'sha256' in state:
                        self.append('SHA-256: ' + state['sha256'])
                    if state.get('RSA') == 'PASS':
                        self.append(f"RSA PASS · {state['entry_count']} entries · {state['changed_entries']} replacements")
                    self.record(action, {**state, 'status': result.get('status', state['state']),
                                         **{k: result[k] for k in ('mode', 'backup_created') if k in result}})
                    self.controls()
                    if not quiet:
                        messagebox.showinfo('Czech Dubbing', state['message'], parent=self.root)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(80, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Please wait', 'Wait for the current operation to finish before closing.', parent=self.root)
            return
        if self.timer:
            self.root.after_cancel(self.timer)
        self.root.after_cancel(self.poll_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        App(root)
    except Exception as error:
        root.withdraw()
        messagebox.showerror('Czech Dubbing', str(error), parent=root)
        root.destroy()
        return 2
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
