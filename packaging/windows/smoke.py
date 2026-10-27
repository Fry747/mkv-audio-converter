"""Execute the frozen app, not the source interpreter, against generated media."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mkv_audio_converter import __version__
from mkv_audio_converter.core import Runner, inspect
from mkv_audio_converter.runtime import configured_tools
sys.path.insert(0, str(ROOT / 'packaging/windows'))
from bundle_policy import audit_bundle
import pefile

bundle = Path(sys.argv[1]).resolve()
cli, gui = bundle/'MKVAudioConverter-cli.exe', bundle/'MKVAudioConverter.exe'
audit_bundle(bundle)
expected_icon = (ROOT/'mkv_audio_converter/assets/icon.png').read_bytes()
installers = sorted((ROOT/'dist/windows').glob('*-setup.exe'))
for exe in (cli, gui, *installers):
    with pefile.PE(str(exe)) as pe:
        assert any(entry.id == 14 for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries), f'Icon missing: {exe}'
        icons = [pe.get_data(language.data.struct.OffsetToData, language.data.struct.Size)
                 for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries if kind.id == 3
                 for resource in kind.directory.entries for language in resource.directory.entries]
        assert expected_icon in icons, f'Application note icon missing or replaced: {exe}'
assert (bundle/'source-manifest.json').is_file()
assert list((bundle/'licenses/upstream').rglob('LGPL-3.0-only.txt'))
assert (bundle/'_internal/mkv_audio_converter/assets/icon.png').is_file()
paths = configured_tools()
def command(*args, **kwargs):
    result = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', timeout=90, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout

assert command(cli, '--version').strip() == __version__
assert len(json.loads(command(cli, '--check'))) == 5
with tempfile.TemporaryDirectory(prefix='mkv-frozen-ü-') as directory:
    root = Path(directory)
    source = root/'Film ü.mkv'
    command(paths['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=24:duration=1',
            '-f', 'lavfi', '-i', 'sine=sample_rate=48000:duration=1', '-c:v', 'ffv1', '-c:a', 'dca',
            '-strict', '-2', '-metadata:s:a:0', 'title=Deutsch DTS', source)
    before = hashlib.sha256(source.read_bytes()).digest()
    report = root/'report.json'
    command(cli, '--cli', '--report', report, '--output-dir', root/'out', source)
    output = Path(json.loads(report.read_text(encoding='utf-8'))['files'][0]['output'])
    media = inspect(output, Runner())
    assert not media.dts_tracks
    assert next(t for t in media.tracks if t.type=='audio').properties['track_name']=='Deutsch AC3'
    assert hashlib.sha256(source.read_bytes()).digest() == before
# A normal close exercises the Qt event loop and returns the actual exit code.
command(gui, '--gui-smoke-test')
print('Frozen version, codecs, Unicode conversion, metadata and GUI startup OK')
