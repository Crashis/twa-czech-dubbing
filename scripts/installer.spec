# Build with PYTHONHASHSEED=0 and SOURCE_DATE_EPOCH fixed by tools.release.
from pathlib import Path

project = Path(SPECPATH).parent
a = Analysis([str(project / 'scripts/installer-entry.py')], pathex=[str(project)],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['numpy', 'unittest', 'pip', 'setuptools'],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='TWA-Czech-Dubbing-Installer', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=True,
          uac_admin=False)
