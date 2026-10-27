import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mkv_audio_converter.core import (
    Cancelled, ConversionError, Media, Options, Runner, Track, convert, discover,
    publish, remux_command, sanitize_tags, signature, xml_key,
)


def track(tid, kind="audio", codec="A_DTS", **props):
    return Track(tid, kind, "DTS" if codec == "A_DTS" else codec,
                 {"uid": tid + 1000, "codec_id": codec, "audio_channels": 2, **props})


class CoreTests(unittest.TestCase):
    def test_dts_family_and_non_dts(self):
        self.assertTrue(track(1).dts)
        self.assertTrue(Track(4, "audio", "DTS-HD Master Audio", {}).dts)
        self.assertFalse(track(1, codec="A_AC3").dts)
        self.assertFalse(track(1, kind="video").dts)

    def test_order_and_input_scoping_with_non_contiguous_ids(self):
        tracks = (track(12, "subtitles", "S_TEXT/UTF8"), track(40),
                  track(91, "video", "V_AV1"), track(3, codec="A_AC3"), track(77))
        media = Media(Path("/input.mkv"), {}, tracks, (0, 0, 0, 0))
        cmd = remux_command(media, {40: Path("/dts1.mka"), 77: Path("/dts2.mka")}, Path("/output.mkv"))
        self.assertEqual(cmd[cmd.index("--track-order") + 1], "0:12,1:0,0:91,0:3,2:0")
        self.assertEqual(cmd[cmd.index("--audio-tracks") + 1], "3")
        self.assertLess(cmd.index("--audio-tracks"), cmd.index(media.path))
        self.assertEqual(cmd.count("--default-track-flag"), 2)
        self.assertNotIn("ffmpeg", cmd)

    def test_all_audio_replaced_uses_no_audio(self):
        media = Media(Path("/input.mkv"), {}, (track(4),), (0, 0, 0, 0))
        cmd = remux_command(media, {4: Path("/one.mka")}, Path("/out.mkv"))
        self.assertIn("--no-audio", cmd)
        self.assertNotIn("--audio-tracks", cmd)

    def test_tag_cleanup_keeps_descriptive_and_unrelated_tags(self):
        raw = """<Tags><Tag><Targets><TrackUID>1001</TrackUID></Targets>
        <Simple><Name>BPS</Name><String>999</String></Simple>
        <Simple><Name>COMMENT</Name><String>Originaltitel DTS</String></Simple></Tag>
        <Tag><Targets><TrackUID>9</TrackUID></Targets>
        <Simple><Name>BPS</Name><String>123</String></Simple></Tag></Tags>"""
        cleaned = sanitize_tags(raw, {1001})
        self.assertNotIn("999", cleaned)
        self.assertIn("123", cleaned)
        self.assertIn("Originaltitel DTS", cleaned)
        self.assertIsNone(xml_key(sanitize_tags("", set())))
        empty = '<Tags><Tag><Targets><TrackUID>1</TrackUID></Targets><Simple><Name>BPS</Name></Simple></Tag></Tags>'
        self.assertIsNone(xml_key(sanitize_tags(empty, {1})))

    def test_semantic_xml_accepts_only_added_derived_language(self):
        old = '<Tags><Tag><Simple><Name>A</Name><String> B </String></Simple></Tag></Tags>'
        new = '<Tags><Tag><Simple><Name>A</Name><String> B </String><TagLanguageIETF>und</TagLanguageIETF></Simple></Tag></Tags>'
        self.assertEqual(xml_key(new, template=old), xml_key(old))
        self.assertNotEqual(xml_key(new.replace(' B ', 'B'), template=old), xml_key(old))

    def test_recursive_discovery_deduplicates_and_ignores_temp_dirs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'sub').mkdir()
            (root / '.mkv-audio-converter-test').mkdir()
            for name in ('a.MKV', 'sub/b.mkv', '.mkv-audio-converter-test/c.mkv'):
                (root / name).touch()
            self.assertEqual(len(discover([root, root / 'a.MKV'])), 2)
            self.assertEqual(len(discover([root], recursive=False)), 1)

    def test_publish_never_overwrites_even_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            temp = root / 'private.mkv'
            temp.write_bytes(b'converted')
            existing = root / 'film_ac3.mkv'
            existing.write_bytes(b'old')
            (root / 'film_ac3_2.mkv').symlink_to(root / 'missing')
            final = publish(temp, root / 'film.mkv', root)
            self.assertEqual(final.name, 'film_ac3_3.mkv')
            self.assertEqual(existing.read_bytes(), b'old')
            self.assertEqual(final.read_bytes(), b'converted')

    def test_runner_uses_no_shell_for_special_characters(self):
        value = 'ü $(touch BAD) ; [test]'
        raw = Runner().run([sys.executable, '-c', 'import sys;print(sys.argv[1])', value], capture=True)
        self.assertEqual(raw.strip(), value)

    def test_silent_child_can_be_cancelled_and_is_reaped(self):
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                Runner(cancel).run([sys.executable, '-c', 'import time;time.sleep(30)'])
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - start, 3)

    def test_failure_is_reported(self):
        with self.assertRaisesRegex(ConversionError, 'Exit 7'):
            Runner().run([sys.executable, '-c', 'import sys;print("broken",file=sys.stderr);sys.exit(7)'])

    def test_stderr_error_even_if_tool_exits_zero(self):
        with self.assertRaisesRegex(ConversionError, 'corrupt'):
            Runner().run([sys.executable, '-c', 'import sys;print("corrupt",file=sys.stderr)'], stderr_error=True)

    def test_discovery_cancellation(self):
        def stop():
            raise Cancelled('stop')
        with self.assertRaises(Cancelled):
            discover([Path('.')], check_cancel=stop)

    def test_timeout(self):
        with self.assertRaisesRegex(ConversionError, 'Zeitlimit'):
            Runner().run([sys.executable, '-c', 'import time;time.sleep(20)'], timeout=.1)

    def test_invalid_json(self):
        with self.assertRaisesRegex(ConversionError, 'JSON'):
            Runner().json([sys.executable, '-c', 'print("not json")'])

    def test_bitrate_validation(self):
        with self.assertRaises(ValueError):
            Options(bitrate=123)

    def test_changed_input_and_downmix_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            path.write_bytes(b'original')
            media = Media(path, {}, (track(1, audio_channels=8),), signature(path))
            with self.assertRaisesRegex(ConversionError, '5.1'):
                convert(media, Options(downmix=False), Runner())
            path.write_bytes(b'changed original')
            with self.assertRaisesRegex(ConversionError, 'verändert'):
                convert(media, Options(), Runner())

    def test_no_dts_is_skipped_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            path.touch()
            media = Media(path, {}, (track(1, codec='A_AC3'),), signature(path))
            result = convert(media, Options(), Runner())
            self.assertTrue(result.skipped)
            self.assertIsNone(result.output)

    def test_failed_conversion_cleans_private_directory(self):
        class FailingRunner(Runner):
            def run(self, *args, **kwargs):
                raise ConversionError('simulated tool failure')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.mkv'
            path.write_bytes(b'original')
            media = Media(path, {}, (track(1),), signature(path))
            with self.assertRaisesRegex(ConversionError, 'simulated'):
                convert(media, Options(), FailingRunner())
            self.assertEqual(list(Path(folder).iterdir()), [path])
            self.assertEqual(path.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
