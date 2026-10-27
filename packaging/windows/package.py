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
from bundle_policy import audit_bundle
from third_party_sources import collect_sources


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
    audit_bundle(bundle)
    shutil.copytree(ROOT / 'LICENSES', notices / 'project-notices', dirs_exist_ok=True)
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
        if name.lower().replace('-', '_') not in {'pyside6_essentials', 'shiboken6', 'pyinstaller'}:
            continue
        for entry in dist.files or ():
            if ('.dist-info' in str(entry) and entry.suffix.lower() not in {'.py', '.pyc'}
                    and any(term in str(entry).lower() for term in ('license', 'copying', 'copyright', 'notice'))):
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
                      'PySide6': f'https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{importlib.metadata.version("PySide6-Essentials")}',
                  }}
    import ssl
    build_info['openssl'] = ssl.OPENSSL_VERSION
    if not ssl.OPENSSL_VERSION.startswith('OpenSSL 3.5.9 '):
        raise RuntimeError('OpenSSL runtime changed: update its license/source notice before release')
    (bundle / 'build-runtime.json').write_text(json.dumps(build_info, indent=2) + '\n', encoding='utf-8')
    for name in ('LICENSE', 'README.md', 'THIRD_PARTY.md', 'CHANGELOG.md'):
        shutil.copyfile(ROOT / name, bundle / name)
    shutil.copytree(ROOT / 'docs', bundle / 'docs', dirs_exist_ok=True)
    collect_sources(ROOT, bundle, output, __version__, qt_version,
                    importlib.metadata.version('PySide6-Essentials'))
    # Include editable icon source and licensing in the binary package too.
    shutil.copytree(ROOT / 'mkv_audio_converter/assets', bundle / 'artwork', dirs_exist_ok=True)
    inventory = audit_bundle(bundle)
    (bundle / 'bundle-files.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
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
        scopes = {
            'mkv_audio_converter': {'.py', '.svg', '.png', '.ico', '.md'},
            'tests': {'.py'}, 'tools': {'.py'},
            'packaging': {'.py', '.ps1', '.iss', '.spec', '.txt'},
            '.github': {'.yml', '.yaml', '.md'},
            'docs': {'.md', '.png', '.json', '.log'},
            'LICENSES': {'.txt', '.md'},
        }
        files = [p for name, suffixes in scopes.items() for p in (ROOT / name).rglob('*')
                 if p.is_file() and p.suffix in suffixes]
        files += [ROOT / name for name in ('LICENSE', 'README.md', 'THIRD_PARTY.md', 'CHANGELOG.md',
                  'SECURITY.md', '.gitignore', '.gitattributes',
                  'pyproject.toml', 'requirements.txt', 'start.cmd', 'start.sh', 'install-desktop.sh')]
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
