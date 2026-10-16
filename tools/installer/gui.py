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
from tools.resources import VERSION


class App:
    def __init__(self, root, *, state_root=None, auto_detect=True):
        self.root = root
        self.state_root = Path(state_root) if state_root is not None else state_directory()
        self.catalog = discover()
        if not self.catalog:
            raise ValueError('No dubbing payload found. Extract the complete release ZIP before running the installer.')
        self.events = queue.Queue()
        self.busy = False
        self.last = None
        self.path = tk.StringVar()
        self.status = tk.StringVar(value='Select your Total War: Arena folder to begin.')
        self.choices = [(m, tk.BooleanVar(value=i == 0)) for i, m in enumerate(self.catalog)]
        self.timer = None
        root.title('Total War: Arena – Czech Dubbing')
        root.geometry('720x650')
        root.minsize(660, 600)
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
        frame.rowconfigure(10, weight=1)
        ttk.Label(frame, text='Total War: Arena', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(frame, text='Czech Dubbing', style='Subtitle.TLabel').grid(row=1, column=0, sticky='w', pady=(0, 18))
        box = ttk.LabelFrame(frame, text='Available dubbing', padding=12)
        box.grid(row=2, column=0, sticky='ew', pady=(0, 18))
        self.checks = []
        for manifest, var in self.choices:
            check = ttk.Checkbutton(box, text=f"{manifest['display_name']}  —  {manifest['replacement_count']} / {manifest['spoken_count']} lines",
                                    variable=var, command=self.changed)
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
        ttk.Label(frame, textvariable=self.status, wraplength=620).grid(row=5, column=0, sticky='w', pady=(14, 14))
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, sticky='ew')
        self.install_button = ttk.Button(actions, text='Install Czech Dubbing', style='Action.TButton', command=lambda: self.start('install'))
        self.install_button.pack(side='left')
        self.verify_button = ttk.Button(actions, text='Verify', command=lambda: self.start('inspect'))
        self.verify_button.pack(side='left', padx=10)
        self.restore_button = ttk.Button(actions, text='Restore Original', command=self.confirm_restore)
        self.restore_button.pack(side='left')
        self.progress = ttk.Progressbar(frame, mode='determinate', maximum=100)
        self.progress.grid(row=7, column=0, sticky='ew', pady=(18, 10))
        ttk.Label(frame, text='Status log').grid(row=8, column=0, sticky='w')
        self.log = tk.Text(frame, height=8, wrap='word', font=('Consolas', 9), relief='solid', borderwidth=1, state='disabled')
        self.log.grid(row=10, column=0, sticky='nsew', pady=(6, 12))
        ttk.Label(frame, text=f'Version {VERSION}  ·  Close the game and launcher before installing or restoring.').grid(row=11, column=0, sticky='w')
        self.path.trace_add('write', lambda *_: self.changed())
        self.controls()
        self.poll_id = root.after(80, self.poll)
        if auto_detect:
            found = known_game_folders()
            if len(found) == 1:
                self.path.set(str(found[0]))

    def selected(self):
        return selection([m for m, var in self.choices if var.get()])

    def changed(self):
        self.last = None
        self.status.set('Checking folder…' if self.path.get().strip() else 'Select your Total War: Arena folder to begin.')
        self.controls()
        if self.timer:
            self.root.after_cancel(self.timer)
        if self.path.get().strip():
            self.timer = self.root.after(700, lambda: self.start('inspect', quiet=True))

    def controls(self):
        ready = bool(self.path.get().strip()) and not self.busy
        self.verify_button['state'] = 'normal' if ready else 'disabled'
        state = self.last.get('state') if self.last else None
        self.install_button['state'] = 'normal' if ready and state == 'ORIGINAL' else 'disabled'
        self.install_button['text'] = 'Installed' if state == 'INSTALLED' else 'Install Czech Dubbing'
        self.restore_button['state'] = 'normal' if ready and state == 'INSTALLED' else 'disabled'
        for control in [self.entry, self.browse_button, *self.checks]:
            control['state'] = 'disabled' if self.busy else 'normal'

    def browse(self):
        value = filedialog.askdirectory(parent=self.root, title='Select Total War: Arena folder', mustexist=True)
        if value:
            self.path.set(value)

    def confirm_restore(self):
        if messagebox.askyesno('Restore Original', 'Restore the original game audio from the verified backup?', parent=self.root):
            self.start('restore')

    def start(self, action, quiet=False):
        if self.busy:
            return
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        try:
            service = Installer(self.selected(), self.state_root,
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
        value = {k: result[k] for k in ('status', 'state', 'sha256', 'RSA', 'changed_entries', 'unchanged_entries') if k in result}
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
        self.record('error', {'status': type(error).__name__})
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
                    action, result, self.last, quiet = value
                    self.busy = False
                    self.status.set(self.last['message'])
                    self.append(self.last['message'])
                    if 'sha256' in self.last:
                        self.append('SHA-256: ' + self.last['sha256'])
                    if self.last.get('RSA') == 'PASS':
                        self.append(f"RSA PASS · {self.last['entry_count']} entries · {self.last['changed_entries']} replacements")
                    self.record(action, result)
                    self.controls()
                    if not quiet:
                        messagebox.showinfo('Czech Dubbing', self.last['message'], parent=self.root)
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
