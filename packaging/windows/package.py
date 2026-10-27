"""Build metadata, legal notices and archives; no vendor binaries in our package."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mkv_audio_converter import __version__


def prepare():
    directory = ROOT / 'build'
    directory.mkdir(exist_ok=True)
    parts = tuple(int(p) for p in __version__.split('.')) + (0,)
    (directory / 'windows-version.txt').write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, "
        "mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), "
        "kids=[StringFileInfo([StringTable('040904B0', ["
        "StringStruct('CompanyName', 'Fry747'), StringStruct('FileDescription', 'MKV Audio Converter'),"
        f"StringStruct('FileVersion', '{__version__}'), StringStruct('ProductVersion', '{__version__}'),"
        "StringStruct('ProductName', 'MKV Audio Converter')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])",
        encoding='utf-8')


def collect():
    bundle = ROOT / 'dist/MKVAudioConverter'
    output = ROOT / 'dist/windows'
    output.mkdir(parents=True, exist_ok=True)
    notices = bundle / 'licenses'
    notices.mkdir(exist_ok=True)
    for filename in ('LICENSE.txt', 'LICENSE'):
        license_file = Path(sys.base_prefix) / filename
        if license_file.is_file():
            shutil.copyfile(license_file, notices / 'CPython-LICENSE.txt')
            break
    else:
        raise RuntimeError('CPython-Lizenzdatei fehlt in der Build-Installation.')
    installed = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        installed[name] = dist.version
        for entry in dist.files or ():
            if any(term in str(entry).lower() for term in ('license', 'copying', 'copyright', 'notice')):
                source = Path(dist.locate_file(entry))
                if source.is_file() and not source.is_symlink():
                    safe = [part for part in entry.parts if part not in ('..', '.')]
                    target = notices / name / Path(*safe)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (bundle / 'build-dependencies.json').write_text(json.dumps(installed, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    from PySide6.QtCore import qVersion
    import platform
    python_version = '.'.join(str(p) for p in sys.version_info[:3])
    qt_version = qVersion()
    build_info = {'application': __version__, 'python': sys.version,
                  'architecture': platform.machine(), 'qt': qt_version,
                  'sources': {
                      'CPython': f'https://www.python.org/ftp/python/{python_version}/Python-{python_version}.tar.xz',
                      'Qt': f'https://download.qt.io/archive/qt/{".".join(qt_version.split(".")[:2])}/{qt_version}/single/',
                      'PySide6': f'https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{installed["PySide6"]}',
                  }}
    (bundle / 'build-runtime.json').write_text(json.dumps(build_info, indent=2) + '\n', encoding='utf-8')
    for name in ('LICENSE', 'README.md', 'WINDOWS.md', 'THIRD_PARTY.md', 'RETTUNGSMODUS.md'):
        shutil.copyfile(ROOT / name, bundle / name)
    portable = output / f'MKVAudioConverter-{__version__}-windows-x64-portable.zip'
    with zipfile.ZipFile(portable, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                archive.write(path, Path(bundle.name) / path.relative_to(bundle))
    source_archive()


def source_archive():
    output = ROOT / 'dist/windows'
    output.mkdir(parents=True, exist_ok=True)
    # Include the exact current sources, including changes not yet committed.
    source_archive = output / f'MKVAudioConverter-{__version__}-source.zip'
    with zipfile.ZipFile(source_archive, 'w', zipfile.ZIP_DEFLATED) as archive:
        names = ['mkv_audio_converter', 'tests', 'packaging', '.github', 'docs']
        files = [p for name in names for p in (ROOT / name).rglob('*') if p.is_file()]
        files += list(ROOT.glob('TESTBERICHT*.md')) + [ROOT / 'FEHLERANALYSE.md']
        files += [ROOT / name for name in ('LICENSE', 'README.md', 'WINDOWS.md', 'THIRD_PARTY.md',
                  'RETTUNGSMODUS.md', 'pyproject.toml', 'requirements.txt', 'start.cmd', 'start.sh', 'install-desktop.sh')]
        for path in sorted(set(files)):
            if path.is_symlink() or '__pycache__' in path.parts or path.suffix in ('.pyc', '.exe', '.dll', '.mkv', '.zip'):
                continue
            archive.write(path, Path('mkv-audio-converter') / path.relative_to(ROOT))


def checksums():
    output = ROOT / 'dist/windows'
    lines = []
    for path in sorted(output.iterdir()):
        if path.suffix in ('.exe', '.zip'):
            digest = hashlib.sha256()
            with path.open('rb') as source:
                while block := source.read(1024**2):
                    digest.update(block)
            lines.append(f'{digest.hexdigest()}  {path.name}')
    (output / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    {'prepare': prepare, 'collect': collect, 'source': source_archive, 'checksums': checksums}[sys.argv[1]]()
