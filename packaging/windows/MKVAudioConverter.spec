# Build only on Windows x64. Both EXEs share one collected runtime directory.
from pathlib import Path
import sys

if sys.platform != 'win32':
    raise SystemExit('Windows-Build bitte auf Windows x64 ausführen.')
root = Path(SPECPATH).resolve().parents[1]
a = Analysis([str(root / 'packaging/windows/entry.py')], pathex=[str(root)],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2'])
pyz = PYZ(a.pure)
options = [('X utf8', None, 'OPTION')]
gui = EXE(pyz, a.scripts, options, exclude_binaries=True, name='MKVAudioConverter',
          console=False, debug=False, strip=False, upx=False,
          version=str(root / 'build/windows-version.txt'))
cli = EXE(pyz, a.scripts, options, exclude_binaries=True, name='MKVAudioConverter-cli',
          console=True, debug=False, strip=False, upx=False,
          version=str(root / 'build/windows-version.txt'))
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='MKVAudioConverter')
