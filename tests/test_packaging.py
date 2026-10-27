"""Release contents and LGPL source handling; no network or Windows required."""
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packaging/windows'))
from bundle_policy import allowed, audit_bundle, filter_entries
from third_party_sources import copy_notices, obtain


class PackagingTests(unittest.TestCase):
    def test_bundle_policy_removes_unused_qt_plugins_and_gpl_modules(self):
        rejected = ['PySide6/Qt6VirtualKeyboard.dll', 'PySide6/Qt6Pdf.dll',
                    'PySide6/Qt6Qml.dll', 'PySide6/plugins/imageformats/qpdf.dll',
                    'PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
                    'PySide6/opengl32sw.dll']
        for name in rejected:
            with self.subTest(name=name):
                self.assertFalse(allowed(name))
        self.assertEqual(filter_entries([('PySide6/Qt6Core.dll', 'core', 'BINARY'),
                                         (rejected[0], 'virtualkeyboard', 'BINARY')]),
                         [('PySide6/Qt6Core.dll', 'core', 'BINARY')])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'qwindows.dll'):
                (root / name).touch()
            audit_bundle(root)
            (root / 'Qt6VirtualKeyboard.dll').touch()
            with self.assertRaisesRegex(RuntimeError, 'Unreviewed'):
                audit_bundle(root)

    def test_source_download_checksum_failure_preserves_cached_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'source.tar.xz'
            target.write_bytes(b'old cache')
            stream = io.BytesIO(b'corrupt download')
            stream.url = 'https://download.qt.io/source.tar.xz'
            with patch('urllib.request.urlopen', return_value=stream):
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    obtain(root, stream.url, hashlib.sha256(b'expected').hexdigest())
            self.assertEqual(target.read_bytes(), b'old cache')
            self.assertFalse(target.with_suffix('.xz.partial').exists())

    def test_notices_extraction_excludes_code_links_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tar = root/'sources.tar.xz'
            with tarfile.open(tar, 'w:xz') as archive:
                for name in ([f'qt/LICENSES/License-{i}.txt' for i in range(5)] +
                             ['qt/src/private.c', '../escape/LICENSE', 'C:/escape/LICENSE']):
                    info = tarfile.TarInfo(name)
                    info.size = 7
                    archive.addfile(info, io.BytesIO(b'license'))
                link = tarfile.TarInfo('qt/LICENSES/link')
                link.type, link.linkname = tarfile.SYMTYPE, '../../outside'
                archive.addfile(link)
            out = root/'notices'
            copy_notices(tar, out)
            self.assertEqual(len(list(out.rglob('*.txt'))), 5)
            self.assertFalse((out/'qt/src/private.c').exists())
            self.assertFalse((root/'escape').exists())
            self.assertFalse((out/'qt/LICENSES/link').exists())

    def test_source_archive_contains_icons_and_build_tools_but_no_secrets_or_media(self):
        spec = importlib.util.spec_from_file_location('windows_package', ROOT/'packaging/windows/package.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('LICENSE', 'README.md', 'THIRD_PARTY.md', 'CHANGELOG.md', 'SECURITY.md',
                         '.gitignore', '.gitattributes', 'pyproject.toml', 'requirements.txt',
                         'start.cmd', 'start.sh', 'install-desktop.sh',
                         'mkv_audio_converter/assets/icon.svg', 'mkv_audio_converter/assets/icon.ico',
                         'tools/build_icons.py', 'LICENSES/Breeze-COPYING-ICONS.txt',
                         'tools/private.key', 'tools/ffmpeg.exe', 'mkv_audio_converter/movie.mkv'):
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'test fixture')
            with patch.object(module, 'ROOT', root):
                module.source_archive()
            with zipfile.ZipFile(next((root/'dist/windows').glob('*-source.zip'))) as archive:
                names = archive.namelist()
                self.assertIn('mkv-audio-converter/mkv_audio_converter/assets/icon.ico', names)
                self.assertIn('mkv-audio-converter/LICENSES/Breeze-COPYING-ICONS.txt', names)
                self.assertIn('mkv-audio-converter/tools/build_icons.py', names)
                self.assertFalse(any(n.endswith(('.key', '.mkv', '.exe')) for n in names))
