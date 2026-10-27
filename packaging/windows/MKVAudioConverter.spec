# Build only on Windows x64. Both EXEs share one collected runtime directory.
from pathlib import Path
import sys

if sys.platform != 'win32':
    raise SystemExit('Windows-Build bitte auf Windows x64 ausführen.')
root = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(root / 'packaging/windows'))
from bundle_policy import filter_entries
a = Analysis([str(root / 'packaging/windows/entry.py')], pathex=[str(root)],
             binaries=[], datas=[(str(root / 'mkv_audio_converter/assets'), 'mkv_audio_converter/assets')],
             hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2'])
a.binaries = filter_entries(a.binaries)
a.datas = filter_entries(a.datas)
pyz = PYZ(a.pure)
options = [('X utf8', None, 'OPTION')]
gui = EXE(pyz, a.scripts, options, exclude_binaries=True, name='MKVAudioConverter',
          console=False, debug=False, strip=False, upx=False,
          icon=str(root / 'mkv_audio_converter/assets/icon.ico'),
          version=str(root / 'build/windows-version.txt'))
cli = EXE(pyz, a.scripts, options, exclude_binaries=True, name='MKVAudioConverter-cli',
          console=True, debug=False, strip=False, upx=False,
          icon=str(root / 'mkv_audio_converter/assets/icon.ico'),
          version=str(root / 'build/windows-version.txt'))
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='MKVAudioConverter')
