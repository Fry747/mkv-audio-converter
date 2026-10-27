"""Validate the complete release set, checksums and exact tagged sources."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packaging/windows'))
from bundle_policy import allowed
from third_party_sources import SOURCES


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(directory, version):
    stem = f'MKVAudioConverter-{version}'
    packages = {f'{stem}-windows-x64-setup.exe', f'{stem}-windows-x64-portable.zip',
                f'{stem}-source.zip', f'{stem}-third-party-sources.zip'}
    expected = packages | {'SHA256SUMS.txt'}
    if {p.name for p in directory.iterdir()} != expected:
        raise ValueError('Release must contain exactly the five expected files')
    if any(p.is_symlink() or not p.is_file() for p in directory.iterdir()):
        raise ValueError('Only regular release files are allowed')
    records = {}
    for line in (directory / 'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^/\\]+)', line)
        if not match or match[2] in records:
            raise ValueError('Invalid or duplicate checksum entry')
        records[match[2]] = match[1]
    if records.keys() != packages:
        raise ValueError('Checksums must cover exactly the four packages')
    for name, expected_digest in records.items():
        if digest(directory / name) != expected_digest:
            raise ValueError('Checksum mismatch: ' + name)
    for name in packages:
        if name.endswith('.zip'):
            with zipfile.ZipFile(directory / name) as archive:
                if archive.testzip():
                    raise ValueError('ZIP CRC failure: ' + name)
                if len(archive.namelist()) != len(set(archive.namelist())):
                    raise ValueError('Duplicate ZIP members: ' + name)
    with zipfile.ZipFile(directory / f'{stem}-source.zip') as archive:
        prefix = 'mkv-audio-converter/'
        files = {n[len(prefix):]: n for n in archive.namelist() if not n.endswith('/')}
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')[:-1]
        if set(files) != set(tracked):
            raise ValueError('Source ZIP differs from the complete tracked file set')
        for name in tracked:
            actual = archive.read(files[name])
            original = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
            # Windows Git converts text to CRLF; these are the same sources.
            if not name.endswith(('.png', '.ico')):
                actual, original = actual.replace(b'\r\n', b'\n'), original.replace(b'\r\n', b'\n')
            if actual != original:
                raise ValueError('Source ZIP does not match tagged commit: ' + name)
    with zipfile.ZipFile(directory / f'{stem}-third-party-sources.zip') as archive:
        manifest = json.loads(archive.read('source-manifest.json'))
        if manifest['application'] != version:
            raise ValueError('Wrong application version in source manifest')
        for component, source_version, url, expected_digest in SOURCES:
            name = url.rsplit('/', 1)[-1]
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_digest:
                    raise ValueError('Upstream source mismatch: ' + component)
            if not any(r['component'] == component and r['version'] == source_version
                       and r['sha256'] == expected_digest and r['url'] == url
                       and r['file'] == name for r in manifest['sources']):
                raise ValueError('Incorrect upstream source manifest')
    with zipfile.ZipFile(directory / f'{stem}-windows-x64-portable.zip') as archive:
        prefix = 'MKVAudioConverter/'
        for name in archive.namelist():
            if not name.startswith(prefix) or not allowed(name[len(prefix):]):
                raise ValueError('Unreviewed portable component: ' + name)
        if json.loads(archive.read(prefix + 'source-manifest.json')) != manifest:
            raise ValueError('Portable and source manifests differ')
        for name in ('MKVAudioConverter.exe', 'MKVAudioConverter-cli.exe',
                     'licenses/CPython-LICENSE.txt', 'THIRD_PARTY.md', 'LICENSE'):
            if not archive.read(prefix + name):
                raise ValueError('Missing runtime/license content: ' + name)
    with (directory / f'{stem}-windows-x64-setup.exe').open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Installer is not a Windows executable')
    print('Verified: five files, four SHA-256 values, ZIP integrity, tagged sources, LGPL sources and portable components')
    for path in sorted(directory.iterdir()):
        print(f'{digest(path)}  {path.name}')


if __name__ == '__main__':
    verify(Path(sys.argv[1]), sys.argv[2])
