"""Resolve native tools explicitly on Windows; never search the media's directory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

TOOLS = ('mkvmerge', 'mkvextract', 'mkvpropedit', 'ffmpeg', 'ffprobe')
_explicit_root: Path | None = None


def windows() -> bool:
    return sys.platform == 'win32'


def user_data_dir() -> Path:
    if windows():
        base = os.environ.get('LOCALAPPDATA')
        if not base or not Path(base).is_absolute():
            raise OSError('LOCALAPPDATA fehlt; das Windows-Benutzerprofil ist nicht verfügbar.')
        return Path(base) / 'MKVAudioConverter'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'mkv-audio-converter'


def application_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def find_tools(root: Path) -> dict[str, Path]:
    """Bounded discovery in an explicitly chosen/extracted tool folder."""
    root = root.expanduser().resolve(strict=True)
    matches = {name: [] for name in TOOLS}
    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        depth = len(current.relative_to(root).parts)
        dirs[:] = [d for d in dirs if not (current / d).is_symlink()] if depth < 4 else []
        for filename in files:
            count += 1
            if count > 30000:
                raise ValueError('Werkzeugordner zu groß. Bitte nur die entpackten Werkzeugpakete auswählen.')
            for name in TOOLS:
                if filename.casefold() == name + '.exe':
                    path = current / filename
                    if not path.is_symlink():
                        matches[name].append(path)
    ambiguous = [name for name, paths in matches.items() if len(paths) > 1]
    if ambiguous:
        raise ValueError('Mehrere Versionen im Werkzeugordner: ' + ', '.join(ambiguous))
    return {name: paths[0] for name, paths in matches.items() if paths}


def set_tools_directory(root: Path):
    global _explicit_root
    paths = find_tools(root)
    missing = [name for name in TOOLS if name not in paths]
    if missing:
        raise ValueError('Im Werkzeugordner fehlen: ' + ', '.join(missing))
    _explicit_root = root.expanduser().resolve()


def configured_tools() -> dict[str, Path]:
    if _explicit_root is not None:
        return find_tools(_explicit_root)
    override = os.environ.get('MKV_AUDIO_CONVERTER_TOOLS_DIR')
    if override:
        return find_tools(Path(override))
    config = user_data_dir() / 'tools.json'
    if config.is_file():
        data = json.loads(config.read_text(encoding='utf-8'))
        root = Path(data['root'])
        if not root.is_absolute():
            raise ValueError('Ungültiger gespeicherter Werkzeugordner.')
        # An explicit configuration must not silently fall back to another tool.
        return find_tools(root)
    sidecar = application_dir() / 'tools'
    return find_tools(sidecar) if sidecar.is_dir() else {}


def resolve_tool(name: str) -> str | None:
    if name not in TOOLS:
        raise ValueError('Unbekanntes Werkzeug: ' + name)
    if not windows():
        return shutil.which(name)
    configured = configured_tools()
    if name in configured:
        return str(configured[name])
    if _explicit_root is not None or os.environ.get('MKV_AUDIO_CONVERTER_TOOLS_DIR') or (user_data_dir() / 'tools.json').exists():
        return None
    # Check known install locations and explicit absolute PATH entries. No CWD,
    # PATHEXT scripts or current-drive-relative paths are eligible.
    candidates = []
    for variable in ('ProgramW6432', 'ProgramFiles'):
        base = os.environ.get(variable)
        if base and Path(base).is_absolute():
            candidates += [Path(base) / 'MKVToolNix', Path(base) / 'ffmpeg/bin']
    candidates += [Path(p.strip('"')) for p in os.environ.get('PATH', '').split(os.pathsep) if p]
    for directory in candidates:
        if directory.is_absolute() and directory != Path.cwd():
            candidate = directory / (name + '.exe')
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def missing_tools() -> list[str]:
    return [name for name in TOOLS if not resolve_tool(name)]


def save_tools_directory(root: Path):
    """Publish only after successful validation; old configuration survives failures."""
    import tempfile
    destination = user_data_dir()
    destination.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    fd, temp = tempfile.mkstemp(prefix='.tools-', suffix='.json', dir=destination)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 1, 'root': str(root)}, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, destination / 'tools.json')
    finally:
        Path(temp).unlink(missing_ok=True)
