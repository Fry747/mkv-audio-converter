"""Explicit, cancellable first-run download from upstream; no package manager/admin."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import shutil
import stat
import tempfile
from urllib.parse import urlparse
import urllib.request
import uuid
import zipfile

from . import runtime


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    url: str
    sha256: str
    size: int
    tools: tuple[str, ...]


# Hashes from the publishers' versioned SHA-256 lists, reviewed 2026-10-27.
# Deliberately no 'latest' URLs or downloaded-and-trusted checksum files.
PACKAGES = (
    Package('ffmpeg', '9.0.2',
            'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip',
            '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba',
            114768076, ('ffmpeg', 'ffprobe')),
    Package('mkvtoolnix', '103.0',
            'https://mkvtoolnix.download/windows/releases/103.0/mkvtoolnix-64-bit-103.0.zip',
            'c860a10c707cb1ee587d1464f6171842f2ada3bb6f031dfff55fec75542f0417',
            103859301, ('mkvmerge', 'mkvextract', 'mkvpropedit')),
)
ALLOWED_HOSTS = {'www.gyan.dev', 'mkvtoolnix.download', 'github.com',
                 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
MAX_ARCHIVE = 512 * 1024**2
MAX_EXTRACTED = 2 * 1024**3


def check_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError('Nicht erlaubtes Downloadziel: ' + url)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(package, target, runner, progress):
    check_url(package.url)
    opener = urllib.request.build_opener(SafeRedirect())
    digest, total = hashlib.sha256(), 0
    runner.log(f'{package.name} {package.version}: {package.url}')
    request = urllib.request.Request(package.url, headers={'User-Agent': 'MKVAudioConverter-Windows-Setup'})
    # A blocking network read can take at most ten seconds before cancellation
    # is observed; all extraction/copy loops check cancellation between blocks.
    with opener.open(request, timeout=10) as response, target.open('xb') as file:
        check_url(response.url)
        length = int(response.headers.get('Content-Length', package.size))
        if length > MAX_ARCHIVE:
            raise ValueError('Download größer als zugelassen.')
        while True:
            runner.check_cancel()
            block = response.read1(256 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_ARCHIVE:
                raise ValueError('Download größer als zugelassen.')
            digest.update(block)
            file.write(block)
            progress(min(.99, total / max(length, 1)), f'{package.name} herunterladen')
    if digest.hexdigest() != package.sha256:
        raise ValueError(f'SHA-256-Prüfung fehlgeschlagen: {package.name}. Es wird nichts aktiviert.')
    progress(1., f'{package.name}: Download geprüft')


def safe_members(archive):
    seen, total, result = set(), 0, []
    for info in archive.infolist():
        name = info.filename.replace('\\', '/')
        path = PurePosixPath(name)
        if (not name or name.startswith('/') or PureWindowsPath(name).drive or
                '..' in path.parts or ':' in name or '\x00' in name):
            raise ValueError('Unsicherer Archivpfad: ' + name)
        for part in path.parts:
            if part.endswith((' ', '.')) or part.split('.')[0].upper() in {
                'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
                raise ValueError('Ungültiger Windows-Archivpfad: ' + name)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError('Links/Spezialdateien im Downloadarchiv sind nicht erlaubt.')
        key = '/'.join(path.parts).casefold()
        if key in seen or info.flag_bits & 1:
            raise ValueError('Doppelte oder verschlüsselte Archivdatei: ' + name)
        seen.add(key)
        total += info.file_size
        if total > MAX_EXTRACTED or len(seen) > 30000:
            raise ValueError('Downloadarchiv überschreitet die Entpackgrenze.')
        result.append((info, path))
    return result


def extract(archive_path, target, runner):
    target.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_members(archive)
        for info, path in members:
            runner.check_cancel()
            destination = target.joinpath(*path.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open('xb') as output:
                while True:
                    runner.check_cancel()
                    block = source.read(256 * 1024)
                    if not block:
                        break
                    output.write(block)


def check_pe64(path):
    with path.open('rb') as file:
        if file.read(2) != b'MZ':
            raise ValueError('Keine Windows-EXE: ' + path.name)
        file.seek(0x3c)
        offset = int.from_bytes(file.read(4), 'little')
        if offset > path.stat().st_size - 6:
            raise ValueError('Beschädigter EXE-Kopf: ' + path.name)
        file.seek(offset)
        if file.read(6) != b'PE\0\0\x64\x86':
            raise ValueError('Es wird eine Windows-x64-EXE benötigt: ' + path.name)


def validate_tools(root, runner):
    from .core import Runner, check_tools
    paths = runtime.find_tools(root)
    missing = [tool for tool in runtime.TOOLS if tool not in paths]
    if missing:
        raise ValueError('Werkzeuge fehlen: ' + ', '.join(missing))
    for path in paths.values():
        check_pe64(path)
    versions = check_tools(Runner(runner.cancel, runner.log, tool_paths=paths))
    return paths, versions


def use_existing(root, runner):
    _, versions = validate_tools(root, runner)
    runner.check_cancel()
    runtime.save_tools_directory(root)
    return versions


def install(runner, progress=lambda *_: None):
    if not runtime.windows() or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Die automatische Einrichtung unterstützt Windows x64 (Intel/AMD).')
    base = runtime.user_data_dir() / 'tools'
    base.mkdir(parents=True, exist_ok=True)
    # Whole vendor archives (including licenses and DLLs) are kept, separately
    # from our app. No redistributing tool executables in the app installer.
    if shutil.disk_usage(base).free < 3 * 1024**3:
        raise OSError('Für Download und Entpacken werden mindestens 3 GiB freier Platz benötigt.')
    final = base / ('windows-x64-' + uuid.uuid4().hex)
    published = activated = False
    try:
        with tempfile.TemporaryDirectory(prefix='.setup-', dir=base) as temp:
            work = Path(temp)
            unpacked = work / 'ready'
            unpacked.mkdir()
            for i, package in enumerate(PACKAGES):
                archive = work / (package.name + '.zip')
                download(package, archive, runner,
                         lambda p, phase, i=i: progress((i + .8*p) / len(PACKAGES), phase))
                progress((i + .8) / len(PACKAGES), f'{package.name} entpacken')
                extract(archive, unpacked / package.name, runner)
                archive.unlink()
                progress((i + .95) / len(PACKAGES), f'{package.name} entpackt')
            paths, versions = validate_tools(unpacked, runner)
            for package in PACKAGES:
                if any(package.version not in versions[tool] for tool in package.tools):
                    raise ValueError('Werkzeugversion stimmt nicht mit dem Downloadplan überein.')
            receipt = {'schema': 1, 'packages': [p.__dict__ for p in PACKAGES], 'versions': versions,
                       'tools': {k: str(v.relative_to(unpacked)) for k, v in paths.items()}}
            (unpacked / 'download-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
            runner.check_cancel()
            unpacked.rename(final)  # unique directory, no previous tools modified
            published = True
            runtime.save_tools_directory(final)  # activate all five tools together
            activated = True
        progress(1., 'Werkzeuge eingerichtet und geprüft')
        return versions
    except BaseException:
        if published and not activated:
            shutil.rmtree(final, ignore_errors=True)
        raise
