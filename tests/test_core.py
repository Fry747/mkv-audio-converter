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
    Cancelled, ConversionError, Media, Options, Progress, Runner, SourceDamageError, Track, convert, discover,
    converted_track_name, metadata_check, publish, remux_command, sanitize_tags, signature, xml_difference, xml_key,
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

    def test_converted_titles_keep_language_and_release_text(self):
        cases = [
            ("DTS-ES.6.1.Warner.Fixed.x264-Xell", 7, "AC3.5.1.Warner.Fixed.x264-Xell"),
            ("English DTS-ES 6.1", 7, "English AC3 5.1"),
            ("Deutsch DTS 5.1 (Kommentar)", 6, "Deutsch AC3 5.1 (Kommentar)"),
            ("日本語 DTS-HD MA 7.1 / Français", 8, "日本語 AC3 5.1 / Français"),
            ("English_DTS-HD_MA_7.1_Original", 8, "English_AC3_5.1_Original"),
            ("DTS-ES.6.1 / Release 6.1", 7, "AC3.5.1 / Release 6.1"),
            ("DTS:X 7.1.4", 12, "AC3 5.1"),
        ]
        for name, channels, expected in cases:
            with self.subTest(name=name):
                original = track(1, track_name=name, audio_channels=channels)
                self.assertEqual(converted_track_name(original), expected)
                self.assertEqual(original.properties["track_name"], name)

    def test_recognized_dts_profiles_and_case(self):
        for label in ("DTS", "dts-es", "DTS ES Discrete", "DTS-ES Matrix",
                      "DTS-HD", "dts-hd ma", "DTS HD Master Audio", "DTS-HD HRA",
                      "DTS-HD HR", "DTS-HD High Resolution Audio", "DTS:X",
                      "DTS-96/24", "DTS Express", "DTS Core", "DTS Digital Surround"):
            with self.subTest(label=label):
                self.assertEqual(converted_track_name(track(1, track_name=f"English ({label})")),
                                 "English (AC3)")

    def test_titles_without_explicit_dts_labels_are_not_invented(self):
        for name in ("", "English", "Deutsch – Hörfassung", "ADTS", "DTSync", "préDTS", "DTS日本語"):
            with self.subTest(name=name):
                self.assertEqual(converted_track_name(track(1, track_name=name)), name)
        self.assertEqual(converted_track_name(track(1)), "")

    def test_other_tracks_keep_dts_wording(self):
        for kind, codec in (("audio", "A_AC3"), ("subtitles", "S_TEXT/UTF8"), ("video", "V_AV1")):
            with self.subTest(kind=kind):
                original = track(1, kind, codec, track_name="English DTS-HD MA 7.1")
                self.assertEqual(converted_track_name(original), "English DTS-HD MA 7.1")

    def test_only_downmix_changes_attached_channel_label(self):
        for name, channels, expected in (("DTS 2.1", 3, "AC3 2.1"),
                                         ("DTS 3.0", 3, "AC3 3.0"),
                                         ("DTS 4.0", 4, "AC3 4.0"),
                                         ("DTS-HD MA", 8, "AC3")):
            with self.subTest(name=name):
                self.assertEqual(converted_track_name(track(1, track_name=name, audio_channels=channels)), expected)

    def test_remux_uses_converted_title(self):
        media = Media(Path("/input.mkv"), {},
                      (track(1, track_name="English DTS-ES 6.1", audio_channels=7),), (0, 0, 0, 0))
        cmd = remux_command(media, {1: Path("/ac3.mka")}, Path("/out.mkv"))
        self.assertEqual(cmd[cmd.index("--track-name") + 1], "0:English AC3 5.1")

    def test_title_validation_accepts_only_expected_output(self):
        old = track(1, track_name="English DTS-ES 6.1", audio_channels=7)
        source = Media(Path("/input.mkv"), {"container": {}}, (old,), (0, 0, 0, 0))
        def target(name):
            new = track(1, codec="A_AC3", track_name=name, audio_channels=6,
                        audio_sampling_frequency=48000)
            return Media(Path("/output.mkv"), {"container": {}}, (new,), (0, 0, 0, 0))
        with patch("mkv_audio_converter.core.extract_xml", return_value=""):
            checks = metadata_check(source, target("English AC3 5.1"), "", "", Runner())
            self.assertTrue(any("English DTS-ES 6.1" in c and "English AC3 5.1" in c for c in checks))
            for wrong in ("English DTS-ES 6.1", "English AC3 6.1", "Deutsch AC3 5.1"):
                with self.subTest(wrong=wrong), self.assertRaisesRegex(ConversionError, "track_name"):
                    metadata_check(source, target(wrong), "", "", Runner())

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

    def test_legacy_chapters_accept_actual_chap_language_ietf_element(self):
        old = '\ufeff<?xml version="1.0"?><Chapters><EditionEntry><ChapterAtom><ChapterUID>17</ChapterUID><ChapterTimeStart>00:00:01.000000000</ChapterTimeStart><ChapterDisplay><ChapterString>Kapitel 1</ChapterString><ChapterLanguage>eng</ChapterLanguage></ChapterDisplay></ChapterAtom></EditionEntry></Chapters>'
        new = old.replace('</ChapterDisplay>', '<ChapLanguageIETF>en</ChapLanguageIETF></ChapterDisplay>')
        self.assertEqual(xml_key(new, template=old), xml_key(old))
        changed = new.replace('Kapitel 1', 'Kapitel 2')
        self.assertNotEqual(xml_key(changed, template=old), xml_key(old))
        self.assertIn('ChapterString', xml_difference(old, changed))
        self.assertNotEqual(xml_key(new.replace('00:00:01.', '00:00:02.'), template=old), xml_key(old))

    def test_existing_chapter_ietf_language_stays_strict(self):
        old = '<Chapters><EditionEntry><ChapterAtom><ChapterDisplay><ChapterString>One</ChapterString><ChapterLanguage>eng</ChapterLanguage><ChapLanguageIETF>en-US</ChapLanguageIETF></ChapterDisplay></ChapterAtom></EditionEntry></Chapters>'
        self.assertNotEqual(xml_key(old.replace('en-US', 'en-GB'), template=old), xml_key(old))

    def test_progress_never_moves_backwards(self):
        values = []
        progress = Progress(lambda value, phase: values.append(value))
        for value in (0, .4, .35, .7, .1, 1.2, .9):
            progress(value, 'phase')
        self.assertEqual(values, [0, .4, .4, .7, .7, 1, 1])

    def test_resync_warning_aborts_silent_recovery_immediately(self):
        logs = []
        start = time.monotonic()
        with self.assertRaisesRegex(SourceDamageError, 'Matroska'):
            Runner(log=logs.append).run([sys.executable, '-u', '-c',
                'import time;print("#GUI#warning Resyncing at position 1234");time.sleep(30)'],
                on_line=lambda _: None, reject_resync=True)
        self.assertLess(time.monotonic() - start, 3)
        self.assertTrue(any('Resyncing at position 1234' in line for line in logs))

    def test_gui_warning_is_logged_live_without_progress_tail(self):
        logs = []
        runner = Runner(log=logs.append)
        runner.run([sys.executable, '-c',
            'print("#GUI#warning Important warning");print("#GUI#progress 100%")'], on_line=lambda _: None)
        self.assertEqual(len(runner.warnings), 1)
        self.assertIn('Important warning', runner.warnings[0])
        self.assertNotIn('#GUI#progress', runner.warnings[0])

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
