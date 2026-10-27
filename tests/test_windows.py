"""Cross-platform checks plus native Windows process/rename coverage in CI."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from mkv_audio_converter import runtime
from mkv_audio_converter.core import Cancelled, ConversionError, Options, Runner, check_tools, convert, inspect, publish
from mkv_audio_converter.processes import ThreadedPipes, spawn as spawn_process
from mkv_audio_converter.windows_tools import (Package, PACKAGES, check_pe64, check_url, download, extract,
                                               install, safe_members, use_existing)


def fake_pe(path):
    data = bytearray(128)
    data[:2] = b'MZ'
    data[0x3c:0x40] = (64).to_bytes(4, 'little')
    data[64:70] = b'PE\0\0\x64\x86'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class WindowsSupportTests(unittest.TestCase):
    def test_windows_mkv_tools_use_short_english_code_and_utf8(self):
        # Exercise Runner's real pipe/exit handling with a stand-in that rejects
        # the Unix token, as the actual Windows MKVToolNix build does.
        validator = ('import sys;args=sys.argv[1:];'
                     'sys.exit(2) if args[:4] != ["--ui-language","en","--output-charset","UTF-8"] '
                     'else print("English output")')
        with tempfile.TemporaryDirectory() as folder:
            for tool in ('mkvmerge', 'mkvextract', 'mkvpropedit'):
                with self.subTest(tool=tool):
                    path = Path(folder)/(tool + '.exe')
                    path.touch()
                    commands = []
                    def launch(command, env):
                        commands.append(command)
                        return spawn_process([sys.executable, '-c', validator, *command[1:]], env)
                    with patch.object(runtime, 'windows', return_value=True), \
                         patch('mkv_audio_converter.core.spawn', side_effect=launch):
                        output = Runner(tool_paths={tool: path}, threaded_io=True).run(
                            [tool, '--version'], capture=True)
                    self.assertEqual(output, 'English output\n')
                    self.assertEqual(commands, [[str(path), '--ui-language', 'en',
                                               '--output-charset', 'UTF-8', '--version']])

    def test_setup_cli_progress_does_not_flood_logs(self):
        from mkv_audio_converter.__main__ import _setup_progress_printer
        output = io.StringIO()
        with patch('sys.stderr', output):
            progress = _setup_progress_printer()
            for _ in range(1000):
                progress(.88, 'mkvtoolnix herunterladen')
            progress(.89, 'mkvtoolnix herunterladen')
            progress(.89, 'mkvtoolnix entpacken')
        self.assertEqual(output.getvalue().splitlines(), [
            '88% mkvtoolnix herunterladen', '89% mkvtoolnix herunterladen', '89% mkvtoolnix entpacken'])

    def test_threaded_output_preserves_lines_progress_and_both_streams(self):
        lines = []
        raw = Runner(threaded_io=True).run([sys.executable, '-u', '-c',
            'import os;os.write(1,b"one\\r");os.write(2,b"diagnostic\\n");'
            'os.write(1,b"two\\nlast")'], capture=True, on_line=lines.append)
        self.assertEqual(raw, 'one\ntwo\nlast\n')
        self.assertEqual(lines, ['one', 'two', 'last'])
        self.assertFalse(any(t.name == 'mkv-tool-pipe' for t in threading.enumerate()))

    def test_threaded_concurrent_pipe_pressure_is_drained(self):
        size = 20000
        raw = Runner(threaded_io=True).run([sys.executable, '-c',
            f'import os,threading;t=threading.Thread(target=lambda:[os.write(2,b"stderr\\n") for _ in range({size})]);'
            f't.start();[os.write(1,b"stdout\\n") for _ in range({size})];t.join()'], capture=True)
        self.assertEqual(raw.count('stdout\n'), size)

    def test_threaded_cancellation_and_timeout_reap_silent_process(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout):
                cancel = threading.Event()
                timer = threading.Timer(.15, cancel.set)
                if not timeout:
                    timer.start()
                before = time.monotonic()
                try:
                    with self.assertRaises(ConversionError if timeout else Cancelled):
                        Runner(cancel, threaded_io=True).run([sys.executable, '-c', 'import time;time.sleep(30)'],
                                                             timeout=.15 if timeout else None)
                finally:
                    timer.cancel()
                self.assertLess(time.monotonic() - before, 4)
                self.assertFalse(any(t.name == 'mkv-tool-pipe' for t in threading.enumerate()))

    def test_cancellation_still_works_after_both_pipes_close(self):
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        before = time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                Runner(cancel, threaded_io=True).run([sys.executable, '-c',
                    'import os,time;os.close(1);os.close(2);time.sleep(30)'])
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - before, 4)

    def test_safe_archives_reject_traversal_links_aliases_and_windows_devices(self):
        for names in (['../escape'], ['C:/escape'], ['a:stream'], ['\\\\server\\share'],
                      ['a.', 'normal'], ['CON.txt'], ['a', 'A'], ['dir/../../escape']):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    for name in names:
                        z.writestr(name, b'unsafe')
                with self.assertRaises(ValueError):
                    extract(archive, Path(folder) / 'out', Runner())
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z:
            link = zipfile.ZipInfo('link')
            link.external_attr = 0o120777 << 16
            z.writestr(link, '../escape')
        with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as z, self.assertRaises(ValueError):
            safe_members(z)

    def test_download_hash_mismatch_and_cancellation_never_extract_or_activate(self):
        p = Package('test', '1', 'https://www.gyan.dev/test.zip', '0'*64, 3, ())
        response = io.BytesIO(b'bad')
        response.url, response.headers = p.url, {'Content-Length': '3'}
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.OpenerDirector.open', return_value=response):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                download(p, Path(folder)/'test.zip', Runner(), lambda *_: None)
        for url in ('http://www.gyan.dev/a', 'https://example.org/a', 'file:///tmp/a',
                    'https://mkvtoolnix.download.evil.test/a', 'https://user@www.gyan.dev/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                check_url(url)

    def test_install_is_transactional_and_retains_vendor_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            previous = base / 'tools.json'
            previous.write_text('{"previous": true}')
            def fake_download(p, target, runner, progress):
                with zipfile.ZipFile(target, 'w') as z:
                    for tool in p.tools:
                        pe = base / (tool + '.exe')
                        fake_pe(pe)
                        z.writestr(f'bin/{tool}.exe', pe.read_bytes())
                    z.writestr('LICENSE.txt', 'vendor license')
            versions = {tool: f'{p.name} {p.version}' for p in PACKAGES for tool in p.tools}
            def validate(root, runner):
                paths = runtime.find_tools(root)
                for file in paths.values():
                    check_pe64(file)
                return paths, versions
            with patch.object(runtime, 'windows', return_value=True), \
                 patch.object(runtime, 'user_data_dir', return_value=base), \
                 patch('platform.machine', return_value='AMD64'), \
                 patch('mkv_audio_converter.windows_tools.download', side_effect=fake_download), \
                 patch('mkv_audio_converter.windows_tools.validate_tools', side_effect=validate), \
                 patch('shutil.disk_usage', return_value=shutil._ntuple_diskusage(10**12, 0, 10**12)):
                install(Runner())
                configured = json.loads(previous.read_text())
                active = Path(configured['root'])
                self.assertEqual(len(runtime.find_tools(active)), 5)
                self.assertEqual(len(list(active.rglob('LICENSE.txt'))), 2)
                self.assertTrue((active/'download-receipt.json').is_file())
                old_config = previous.read_bytes()
                with patch('mkv_audio_converter.windows_tools.download', side_effect=OSError('offline')):
                    with self.assertRaises(OSError):
                        install(Runner())
                self.assertEqual(previous.read_bytes(), old_config)
                self.assertTrue(active.is_dir())
                self.assertFalse(list((base/'tools').glob('.setup-*')))

    def test_tool_resolution_does_not_search_current_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            fake_pe(base/'ffmpeg.exe')
            with patch.object(runtime, 'windows', return_value=True), \
                 patch.object(runtime, 'configured_tools', return_value={}), \
                 patch.object(runtime, 'user_data_dir', return_value=base/'settings'), \
                 patch.object(runtime.Path, 'cwd', return_value=base), \
                 patch.dict(os.environ, {'PATH': str(base), 'ProgramFiles':'', 'ProgramW6432':''}, clear=True):
                self.assertIsNone(runtime.resolve_tool('ffmpeg'))

    def test_old_installed_tools_are_rejected_before_conversion(self):
        class Tools:
            old = False
            def find_tool(self, name):
                return name
            def run(self, args, **kwargs):
                if args[1] in ('--version', '-version'):
                    if args[0].startswith('ff'):
                        return args[0] + ' version 8.1.3'
                    return args[0] + (' v50.0' if self.old else ' v102.0')
                return ' A..... ac3 encoder\n A..... dca decoder\n'
        runner=Tools()
        with patch.object(runtime, 'windows', return_value=True):
            self.assertEqual(len(check_tools(runner)), 5)
            runner.old=True
            with self.assertRaisesRegex(ConversionError, 'Windows-Werkzeugversion'):
                check_tools(runner)

    def test_explicit_tool_folder_detects_missing_and_duplicate_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for tool in runtime.TOOLS:
                fake_pe(base/'bin'/(tool+'.exe'))
            self.assertEqual(len(runtime.find_tools(base)), 5)
            fake_pe(base/'other/ffmpeg.exe')
            with self.assertRaisesRegex(ValueError, 'Mehrere'):
                runtime.find_tools(base)

    @unittest.skipUnless(all(shutil.which(t) for t in runtime.TOOLS), 'FFmpeg/MKVToolNix fehlen')
    def test_real_conversion_with_windows_style_threaded_pipes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'Film ü.mkv'
            runner=Runner(threaded_io=True)
            runner.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=128x72:rate=24:duration=1', '-f', 'lavfi', '-i',
                        'sine=sample_rate=48000:duration=1', '-c:v', 'ffv1', '-c:a', 'dca',
                        '-strict', '-2', '-metadata:s:a:0', 'title=Deutsch DTS', source])
            original=hashlib.sha256(source.read_bytes()).digest()
            result=convert(inspect(source, runner), Options(root/'out'), runner)
            target=inspect(result.output, runner)
            self.assertFalse(target.dts_tracks)
            self.assertEqual(next(t for t in target.tracks if t.type=='audio').properties['track_name'], 'Deutsch AC3')
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)
            self.assertTrue(any('decodiert' in check for check in result.checks))

    @unittest.skipUnless(sys.platform == 'win32', 'native Windows API required')
    def test_windows_job_terminates_descendant_before_it_can_write(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'child-survived.txt'
            child = f'import time;from pathlib import Path;time.sleep(1);Path({str(target)!r}).write_text("bad")'
            parent = f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);print("ready",flush=True);time.sleep(30)'
            cancel = threading.Event()
            def ready(line):
                if line == 'ready':
                    cancel.set()
            with self.assertRaises(Cancelled):
                Runner(cancel).run([sys.executable, '-u', '-c', parent], on_line=ready)
            time.sleep(1.3)
            self.assertFalse(target.exists())

    @unittest.skipUnless(sys.platform == 'win32', 'native Windows rename semantics required')
    def test_windows_publication_never_replaces_existing_and_moves_without_hardlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            temp=root/'private.mkv'
            temp.write_bytes(b'new')
            (root/'film_ac3.mkv').write_bytes(b'existing')
            with patch('os.link', side_effect=AssertionError('hardlinks not required')):
                final=publish(temp, root/'film.mkv', root)
            self.assertEqual(final.name, 'film_ac3_2.mkv')
            self.assertEqual((root/'film_ac3.mkv').read_bytes(), b'existing')
            self.assertFalse(temp.exists())
