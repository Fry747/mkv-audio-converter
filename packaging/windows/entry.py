"""Shared entry point for the GUI and console bootloaders."""
import os
import sys
import traceback

from mkv_audio_converter.__main__ import main
from mkv_audio_converter.runtime import user_data_dir

for name in ('stdout', 'stderr'):
    stream = getattr(sys, name)
    if stream is None:
        setattr(sys, name, open(os.devnull, 'w', encoding='utf-8'))
    elif hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

try:
    raise SystemExit(main())
except Exception:
    text = traceback.format_exc()
    try:
        log = user_data_dir() / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding='utf-8')
        detail = f'Fehlerprotokoll: {log}'
    except OSError:
        detail = text
    if '-cli' in os.path.basename(sys.executable).lower():
        print(text, file=sys.stderr)
    else:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, 'MKV Audio Converter konnte nicht starten', detail)
    raise SystemExit(1)
