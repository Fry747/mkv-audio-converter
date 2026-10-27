#!/usr/bin/env bash
# Install a per-user KDE/application-menu entry. No administrator rights needed.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 - "$project_dir" <<'PY'
from pathlib import Path
import os
import sys

root = Path(sys.argv[1])
launcher = root / 'start.sh'
launcher.chmod(launcher.stat().st_mode | 0o111)
# Desktop Exec escaping has two layers. %% avoids accidental field codes.
def quote_exec(value):
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    return '"' + value.replace('%', '%%') + '"'
exec_line = (quote_exec(str(launcher)) + ' %F').replace('\\', '\\\\')
folder = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications'
folder.mkdir(parents=True, exist_ok=True)
target = folder / 'mkv-audio-converter.desktop'
target.write_text('[Desktop Entry]\nType=Application\nName=MKV Audio Converter\n'
                  'Comment=DTS-Tonspuren nach AC3 konvertieren\n'
                  f'Exec={exec_line}\nIcon={root / "mkv_audio_converter/assets/icon.png"}\nTerminal=false\n'
                  'Categories=AudioVideo;Audio;\nMimeType=video/x-matroska;\n', encoding='utf-8')
print(f'Menüeintrag installiert: {target}')
print('Der Projektordner muss an diesem Ort bleiben. Entfernen: diese .desktop-Datei löschen.')
PY
