"""Archive the exact upstream LGPL sources beside the downloadable binaries."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile

SOURCES = (
    ('qtbase', '6.11.2',
     'https://download.qt.io/archive/qt/6.11/6.11.2/submodules/qtbase-everywhere-src-6.11.2.tar.xz',
     '5b2e00eccaf5a4d8c14134ffa0ea8dfd0a35ae1ffc7f8d87fa4305a1ed23cf22'),
    ('pyside-setup', '6.11.2',
     'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz',
     'cba47efbaad1bedd529725cbc14e21f156c7a19366f07b3edfbb076ffd7afdf8'),
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024**2):
            digest.update(block)
    return digest.hexdigest()


def obtain(cache, url, expected):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / url.rsplit('/', 1)[-1]
    if target.is_file() and sha256(target) == expected:
        return target
    partial = target.with_suffix(target.suffix + '.partial')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
            if not response.url.startswith('https://'):
                raise RuntimeError('Source download redirected to insecure transport')
            total = 0
            while block := response.read(1024**2):
                total += len(block)
                if total > 150 * 1024**2:
                    raise RuntimeError('Unexpected source archive size')
                output.write(block)
        if sha256(partial) != expected:
            raise RuntimeError('Upstream source checksum mismatch: ' + target.name)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def copy_notices(archive_path, destination):
    """Copy attribution/license text only; never execute or blindly extract tar paths."""
    copied = 0
    with tarfile.open(archive_path) as archive:
        for member in archive:
            path = PurePosixPath(member.name.replace('\\', '/'))
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or any(':' in part for part in path.parts)):
                continue
            name = path.name.lower()
            if not ('LICENSES' in path.parts or name.startswith(('license', 'copying', 'copyright', 'notice'))
                    or name == 'qt_attribution.json'):
                continue
            if member.size > 4 * 1024**2:
                raise RuntimeError('Unexpected license text size')
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('wb') as out:
                shutil.copyfileobj(source, out)
            copied += 1
    if copied < 5:
        raise RuntimeError('Missing upstream license texts')


def collect_sources(root, bundle, output, version, qt_version, pyside_version):
    if qt_version != '6.11.2' or pyside_version != '6.11.2':
        raise RuntimeError('Runtime version changed: review and pin matching upstream sources first')
    records, archives = [], []
    for name, upstream_version, url, digest in SOURCES:
        path = obtain(root / 'build/upstream-sources', url, digest)
        copy_notices(path, bundle / 'licenses/upstream')
        records.append(dict(component=name, version=upstream_version, url=url, sha256=digest,
                            file=path.name, modifications='none'))
        archives.append(path)
    manifest = {'application': version, 'sources': records,
                'distribution': f'MKVAudioConverter-{version}-third-party-sources.zip',
                'release_url': f'https://github.com/Fry747/mkv-audio-converter/releases/tag/v{version}'}
    (bundle / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output / manifest['distribution'], 'w', zipfile.ZIP_STORED) as archive:
        for path in archives:
            archive.write(path, path.name)
        archive.write(bundle / 'source-manifest.json', 'source-manifest.json')
        archive.write(bundle / 'build-runtime.json', 'build-runtime.json')
        archive.write(root / 'docs/library-replacement.md', 'library-replacement.md')
    return manifest
