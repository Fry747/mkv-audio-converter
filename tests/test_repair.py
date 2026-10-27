from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from mkv_audio_converter.core import Cancelled, ConversionError, Media, Options, Runner, Track, inspect, signature
from mkv_audio_converter.repair import (CLUSTER, InvalidEBML, analyze, block_frames, element,
                                       recover, validate_cluster, vint, write_candidate)


_real_fsync = os.fsync


def writable_fsync(fd):
    """Enforce Windows' writable-handle requirement on POSIX too."""
    os.write(fd, b'')  # zero bytes: verify access without changing contents
    _real_fsync(fd)


def size_vint(value):
    for width in range(1, 9):
        if value < (1 << (7 * width)) - 1:
            return ((1 << (7 * width)) | value).to_bytes(width, 'big')
    raise ValueError(value)


def elem(identity, content):
    code = identity.to_bytes((identity.bit_length() + 7) // 8, 'big')
    return code + size_vint(len(content)) + content


def cluster(timestamp, extra=b''):
    return elem(CLUSTER, elem(0xE7, timestamp.to_bytes(2, 'big')) +
                elem(0xA3, b'\x81\0\0\x80payload' + extra))


def fake_media(path, content):
    path.write_bytes(content)
    return Media(path, {'container': {'properties': {'duration': 10_000_000_000,
                  'timestamp_scale': 1_000_000}}},
                 (Track(0, 'audio', 'DTS', {'uid': 1, 'number': 1, 'codec_id': 'A_DTS',
                                          'audio_channels': 1}),), signature(path))


def fixture(*clusters):
    return elem(0x1A45DFA3, b'') + b'\x18\x53\x80\x67\x01\xff\xff\xff\xff\xff\xff\xff' + \
        elem(0x1549A966, b'') + elem(0x1654AE6B, b'') + b''.join(clusters)


class RepairTests(unittest.TestCase):
    def test_vint_and_bounds(self):
        self.assertEqual(vint(b'\x81'), (1, 1))
        for bad in (b'', b'\0', b'\x01'):
            with self.assertRaises(InvalidEBML):
                vint(bad)
        with self.assertRaises(InvalidEBML):
            element(b'\xa3\xff', 0, 2)
        with self.assertRaises(InvalidEBML):
            element(b'\xa3\x85a', 0, 3)

    def test_cluster_crc(self):
        import zlib
        body = elem(0xE7, b'\x01') + elem(0xA3, b'\x81\0\0\x80abcd')
        crc = elem(0xBF, zlib.crc32(body).to_bytes(4, 'little'))
        self.assertEqual(validate_cluster(crc + body, {1}), (1, 1, 1, True))
        with self.assertRaisesRegex(InvalidEBML, 'CRC'):
            validate_cluster(crc + body[:-1] + b'x', {1})

    def test_lacing_variants(self):
        for flags, payload in ((0, b'abcd'), (2, b'\x01\x02aabb'),
                               (4, b'\x01aabb'), (6, b'\x01\x82aabb')):
            block = b'\x81\0\0' + bytes([flags]) + payload
            self.assertEqual(block_frames(block, 0, len(block), {1})[1], 1 if flags == 0 else 2)
        with self.assertRaises(InvalidEBML):
            block_frames(b'\x81\0\0\x04\x01abc', 0, 8, {1})
        with self.assertRaises(InvalidEBML):
            block_frames(b'\x82\0\0\0abc', 0, 7, {1})

    def test_damage_resync_and_false_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            media = fake_media(path, fixture(cluster(0), b'\0corrupt\x1f\x43\xb6\x75\xffjunk', cluster(2000)))
            plan = analyze(media, Runner())
            self.assertEqual(len(plan.clusters), 2)
            self.assertEqual(len(plan.damage), 1)
            self.assertEqual(plan.damage[0].before_seconds, 0)
            self.assertEqual(plan.damage[0].after_seconds, 2)
            self.assertEqual(plan.summary()['completeness'], 'NOT_CONFIRMED')
            candidate = Path(folder) / 'candidate.mkv'
            write_candidate(plan, candidate, Runner())
            self.assertIn(cluster(2000), candidate.read_bytes())
            self.assertNotIn(b'corrupt', candidate.read_bytes())

    def test_signature_inside_valid_payload_is_not_resynced(self):
        with tempfile.TemporaryDirectory() as folder:
            media = fake_media(Path(folder) / 'file.mkv', fixture(cluster(0, cluster(1000)), cluster(2000)))
            plan = analyze(media, Runner())
            self.assertEqual(len(plan.clusters), 2)
            self.assertFalse(plan.damage)

    def test_unknown_track_and_bad_cluster_are_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = elem(CLUSTER, elem(0xE7, b'\x01') + elem(0xA3, b'\x82\0\0\x80unknown'))
            media = fake_media(Path(folder) / 'file.mkv', fixture(cluster(0), bad, cluster(2000)))
            self.assertEqual(len(analyze(media, Runner()).clusters), 2)

    def test_changed_source_and_hash_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            media = fake_media(path, fixture(cluster(0), cluster(2000)))
            plan = analyze(media, Runner())
            path.write_bytes(path.read_bytes() + b'changed')
            with self.assertRaisesRegex(ConversionError, 'verändert'):
                write_candidate(plan, Path(folder) / 'candidate.mkv', Runner())

    def test_hash_guard_even_if_size_and_mtime_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            media = fake_media(path, fixture(cluster(0), cluster(2000)))
            plan = analyze(media, Runner())
            original_stat = path.stat()
            data = path.read_bytes()
            path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            self.assertEqual(signature(path), media.signature)
            with self.assertRaisesRegex(ConversionError, 'Quelldaten'):
                write_candidate(plan, Path(folder) / 'candidate.mkv', Runner())

    def test_cancellation_and_explicit_loss_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            media = fake_media(Path(folder) / 'file.mkv', fixture(cluster(0)))
            plan = analyze(media, Runner())
            with self.assertRaisesRegex(ConversionError, 'Zustimmung'):
                recover(plan, Options(), Runner())
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(Cancelled):
                analyze(media, Runner(cancel))


@unittest.skipUnless(all(shutil.which(t) for t in ('mkvmerge', 'ffmpeg', 'ffprobe', 'mkvextract', 'mkvpropedit')),
                     'Medienwerkzeuge fehlen')
class RecoveryIntegrationTests(unittest.TestCase):
    def test_real_damaged_mkv_to_ac3_with_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'damaged.mkv'
            proc = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=128x72:rate=24:duration=3', '-f', 'lavfi', '-i',
                'sine=sample_rate=48000:duration=3', '-c:v', 'ffv1', '-c:a', 'dca', '-strict', '-2',
                '-metadata:s:a:0', 'title=Deutsch DTS',
                '-cluster_time_limit', '500', str(source)], capture_output=True)
            if proc.returncode:
                self.skipTest('DTS-Testencoder fehlt')
            runner = Runner()
            original_plan = analyze(inspect(source, runner), runner)
            self.assertGreater(len(original_plan.clusters), 3)
            # Destroy a whole interior Cluster ID. Good prefix/tail remain intact.
            location = original_plan.clusters[len(original_plan.clusters) // 2].offset
            with source.open('r+b') as file:
                file.seek(location)
                file.write(b'\0\0\0\0')
            before = hashlib.sha256(source.read_bytes()).digest()
            plan = analyze(inspect(source, runner), runner)
            self.assertTrue(plan.damage)
            with patch('os.fsync', side_effect=writable_fsync):
                result = recover(plan, Options(output_dir=root / 'out'), runner, accept_loss=True)
            self.assertTrue(result.recovered)
            self.assertIn('_recovered_ac3', result.output.name)
            self.assertTrue(result.warnings)
            report = json.loads(result.report_path.read_text())
            self.assertEqual(report['kind'], 'SALVAGED_WITH_POSSIBLE_LOSS')
            self.assertGreater(report['excluded_bytes'], 0)
            self.assertFalse(report['video_fully_decoded'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), before)
            target = inspect(result.output, runner)
            self.assertFalse(target.dts_tracks)
            self.assertEqual(next(t for t in target.tracks if t.type == 'audio').properties['track_name'],
                             'Deutsch AC3')
            self.assertTrue(any('Deutsch DTS' in c and 'Deutsch AC3' in c for c in report['checks']))
            self.assertFalse(list((root / 'out').glob('.mkv-audio-converter-*')))
            result2 = recover(plan, Options(output_dir=root / 'out'), runner, accept_loss=True)
            self.assertNotEqual(result.output, result2.output)
            self.assertTrue(result.output.is_file())
            cli = subprocess.run([sys.executable, '-m', 'mkv_audio_converter', '--analyze-repair', str(source)],
                                 capture_output=True, text=True)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertGreater(json.loads(cli.stdout)['excluded_bytes'], 0)
            rejected = subprocess.run([sys.executable, '-m', 'mkv_audio_converter', '--recover', str(source)],
                                      capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            cli = subprocess.run([sys.executable, '-m', 'mkv_audio_converter', '--recover', '--accept-loss',
                                  '--output-dir', str(root / 'cli-output'), str(source)],
                                  capture_output=True, text=True)
            self.assertEqual(cli.returncode, 3, cli.stderr)
            self.assertIn('MÖGLICHEN VERLUSTEN', cli.stdout)


if __name__ == '__main__':
    unittest.main()
