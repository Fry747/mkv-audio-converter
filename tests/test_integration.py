"""Real ffmpeg/MKVToolNix tests with short generated media; no downloads."""
from array import array
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mkv_audio_converter.core import (
    ConversionError, Options, Runner, TOOLS, check_tools, convert, extract_xml,
    inspect, sanitize_tags, xml_key,
)


def command(*args):
    process = subprocess.run([str(a) for a in args], capture_output=True)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.decode(errors='replace') + process.stdout.decode(errors='replace'))
    return process.stdout


def content_peak_time(path):
    """Map the peak PCM sample back to its decoded frame's timestamp.
    Unlike sample_index/rate alone this also works across source packet gaps."""
    pcm = command('ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-ac', '1',
                  '-ar', '48000', '-f', 'f32le', '-')
    samples = array('f')
    samples.frombytes(pcm)
    if os.sys.byteorder != 'little':
        samples.byteswap()
    peak = max(range(len(samples)), key=lambda i: abs(samples[i]))
    frames = json.loads(command('ffprobe', '-v', 'error', '-select_streams', 'a:0',
                               '-show_frames', '-show_entries', 'frame=pts_time,nb_samples', '-of', 'json', path))
    consumed = 0
    for frame in frames['frames']:
        size = int(frame['nb_samples'])
        if peak < consumed + size:
            return float(frame['pts_time']) + (peak - consumed) / 48000
        consumed += size
    raise AssertionError('PCM peak cannot be mapped to a decoded frame')


@unittest.skipUnless(all(shutil.which(t) for t in TOOLS), 'FFmpeg/MKVToolNix fehlen')
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mkv-converter-tests-')
        cls.root = Path(cls.temp.name)
        cls.runner = Runner()
        try:
            check_tools(cls.runner)
        except ConversionError as e:
            raise unittest.SkipTest(str(e))
        base = cls.root / 'base.mkv'
        srt = cls.root / 'subtitles.srt'
        srt.write_text('1\n00:00:00,500 --> 00:00:02,500\nGrüße vom Test\n', encoding='utf-8')
        # VFR video, a pulse used for actual audio-content alignment, an AC3
        # track that must pass through unchanged, and a second 5.1 DTS track.
        command('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24:duration=4',
                '-f', 'lavfi', '-i', 'aevalsrc=if(between(t\\,0.4\\,0.405)\\,0.8\\,0):s=48000:d=3',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3',
                '-f', 'lavfi', '-i', 'anullsrc=channel_layout=5.1:sample_rate=48000:d=3',
                '-i', srt, '-map', '0:v', '-map', '1:a', '-map', '2:a', '-map', '3:a', '-map', '4:s',
                '-vf', 'select=not(eq(mod(n\\,5)\\,0))', '-fps_mode', 'vfr', '-c:v', 'ffv1',
                '-c:a:0', 'dca', '-c:a:1', 'ac3', '-c:a:2', 'dca', '-strict', '-2', '-c:s', 'srt', base)
        attachment = cls.root / 'info.txt'
        attachment.write_bytes(b'attachment: unchanged\n')
        font = cls.root / 'font.ttf'
        font.write_bytes(b'font attachment payload test\n')
        cls.rich = cls.root / 'Film ü [test] $ ;.mkv'
        command('mkvmerge', '-q', '--track-order', '0:4,0:1,0:0,0:2,0:3',
                '--title', 'Film-Titel ü', '--attachment-mime-type', 'text/plain',
                '--attachment-description', 'Testanhang', '--attach-file', attachment,
                '--attachment-mime-type', 'application/x-truetype-font', '--attach-file', font,
                '-o', cls.rich, '--sync', '1:735', '--sync', '3:1250',
                '--language', '1:de-AT', '--track-name', '1:Deutsch DTS (Originaltitel)',
                '--default-track-flag', '1:0', '--forced-display-flag', '1:1', '--track-enabled-flag', '1:0',
                '--commentary-flag', '1:1', '--hearing-impaired-flag', '1:1',
                '--language', '3:en-US', '--track-name', '3:English DTS 5.1',
                '--default-track-flag', '3:0', '--default-track-flag', '2:0',
                '--default-track-flag', '4:0', '--language', '4:de',
                '--track-name', '2:Deutsch DTS Kommentar (AC3 unverändert)',
                '--track-name', '4:DTS Untertitel', base)
        media = inspect(cls.rich, cls.runner)
        uid = media.dts_tracks[0].uid
        # ChapterTrackNumber refers to an EBML track number, not a TrackUID.
        chapters = cls.root / 'chapters.xml'
        chapters.write_text(f'''<?xml version="1.0"?><Chapters><EditionEntry><EditionUID>42</EditionUID>
        <EditionFlagOrdered>0</EditionFlagOrdered><ChapterAtom><ChapterUID>43</ChapterUID>
        <ChapterTimeStart>00:00:00.000000000</ChapterTimeStart><ChapterTimeEnd>00:00:03.000000000</ChapterTimeEnd>
        <ChapterTrack><ChapterTrackNumber>{media.dts_tracks[0].properties['number']}</ChapterTrackNumber></ChapterTrack>
        <ChapterDisplay><ChapterString>Kapitel Eins</ChapterString><ChapterLanguage>ger</ChapterLanguage></ChapterDisplay>
        </ChapterAtom></EditionEntry></Chapters>''', encoding='utf-8')
        tags = cls.root / 'tags.xml'
        tags.write_text(f'''<Tags><Tag><Targets/><Simple><Name>TITLE</Name><String>Globaler Titel</String></Simple></Tag>
        <Tag><Targets><TrackUID>{uid}</TrackUID></Targets><Simple><Name>COMMENT</Name><String>Beschreibung behalten</String></Simple>
        <Simple><Name>BPS</Name><String>99999999</String></Simple></Tag></Tags>''', encoding='utf-8')
        command('mkvpropedit', cls.rich, '--chapters', chapters, '--tags', f'all:{tags}')
        cls.single = cls.root / 'single.mkv'
        command('mkvmerge', '-q', '-o', cls.single, '--audio-tracks', '1', '--no-subtitles', '--no-chapters',
                '--no-global-tags', '--no-track-tags', base)
        cls.no_dts = cls.root / 'no-dts.mkv'
        command('mkvmerge', '-q', '-o', cls.no_dts, '--audio-tracks', '2', base)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_two_dts_vfr_order_metadata_sync_and_unchanged_payloads(self):
        class RecordingRunner(Runner):
            def __init__(self):
                super().__init__()
                self.commands = []
            def run(self, args, **kwargs):
                self.commands.append([str(x) for x in args])
                return super().run(args, **kwargs)
        recording = RecordingRunner()
        media = inspect(self.rich, self.runner)
        original_hash = hashlib.sha256(self.rich.read_bytes()).digest()
        values = []
        result = convert(media, Options(self.root / 'rich-output'), recording,
                         lambda value, phase: values.append(value))
        prepare = [c for c in recording.commands if c[0] == 'mkvmerge' and '--audio-tracks' in c
                   and any(p.endswith('source-audio.mka') for p in c)]
        self.assertEqual(len(prepare), 1)
        self.assertEqual(prepare[0][prepare[0].index('--audio-tracks')+1], ','.join(str(t.id) for t in media.dts_tracks))
        encoders = [c for c in recording.commands if c[0] == 'ffmpeg' and '-c:a' in c]
        self.assertEqual([c[c.index('-map')+1] for c in encoders], ['0:a:0', '0:a:1'])
        self.assertTrue(all('-xerror' in c for c in encoders))
        self.assertEqual(values, sorted(values))
        target = inspect(result.output, self.runner)
        self.assertEqual(len(media.dts_tracks), 2)
        self.assertFalse(target.dts_tracks)
        self.assertEqual([t.type for t in media.tracks], [t.type for t in target.tracks])
        self.assertEqual([t.uid for t in media.tracks], [t.uid for t in target.tracks])
        self.assertEqual(original_hash, hashlib.sha256(self.rich.read_bytes()).digest())
        self.assertEqual([t.channels for t in target.tracks if t.type == 'audio'], [1, 1, 6])
        self.assertEqual([t.properties.get('track_name', '') for t in target.tracks],
                         ['DTS Untertitel', 'Deutsch AC3 (Originaltitel)', '',
                          'Deutsch DTS Kommentar (AC3 unverändert)', 'English AC3 5.1'])
        self.assertTrue(any('English DTS 5.1' in c and 'English AC3 5.1' in c for c in result.checks))
        self.assertTrue(any('SHA-256' in c for c in result.checks))
        self.assertFalse(list(result.output.parent.glob('.mkv-audio-converter-*')))
        self.assertEqual(xml_key(extract_xml(self.runner, self.rich, 'chapters')),
                         xml_key(extract_xml(self.runner, result.output, 'chapters')))
        expected_tags = sanitize_tags(extract_xml(self.runner, self.rich, 'tags'), {t.uid for t in media.dts_tracks})
        self.assertEqual(xml_key(expected_tags), xml_key(extract_xml(self.runner, result.output, 'tags'), template=expected_tags))
        self.assertAlmostEqual(content_peak_time(self.rich), content_peak_time(result.output), delta=.006)

    def test_single_dts_zero_offset_no_chapters_and_collision(self):
        media = inspect(self.single, self.runner)
        directory = self.root / 'single-output'
        directory.mkdir(exist_ok=True)
        existing = directory / 'single_ac3.mkv'
        existing.write_bytes(b'existing file')
        result = convert(media, Options(directory), self.runner)
        self.assertEqual(result.output.name, 'single_ac3_2.mkv')
        self.assertEqual(existing.read_bytes(), b'existing file')
        self.assertEqual(inspect(result.output, self.runner).tracks[1].properties['codec_id'], 'A_AC3')

    def test_no_dts_creates_nothing(self):
        result = convert(inspect(self.no_dts, self.runner), Options(), self.runner)
        self.assertTrue(result.skipped)
        self.assertIsNone(result.output)

    def test_quick_mode_still_checks_audio(self):
        result = convert(inspect(self.single, self.runner), Options(self.root / 'quick', deep_verify=False), self.runner)
        self.assertTrue(any('deaktiviert' in c for c in result.checks))
        self.assertTrue(any('decodiert' in c for c in result.checks))

    def test_late_audio_beyond_initial_identification_window(self):
        late = self.root / 'late.mkv'
        command('mkvmerge', '-q', '-o', late, '--sync', '1:12000', self.single)
        media = inspect(late, self.runner)
        result = convert(media, Options(self.root / 'late-output'), self.runner)
        target = inspect(result.output, self.runner)
        self.assertFalse(target.dts_tracks)

    def test_timestamp_gap_preserves_pulse_after_gap(self):
        gap = self.root / 'gap.mkv'
        command('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=24:duration=3',
                '-f', 'lavfi', '-i', 'aevalsrc=if(between(t\\,1.4\\,1.405)\\,0.8\\,0):s=48000:d=3',
                '-af', 'aselect=not(between(t\\,0.5\\,1.0))', '-c:v', 'ffv1', '-c:a', 'dca', '-strict', '-2', gap)
        result = convert(inspect(gap, self.runner), Options(self.root / 'gap-output'), self.runner)
        self.assertAlmostEqual(content_peak_time(gap), content_peak_time(result.output), delta=.006)

    def test_real_legacy_chapter_roundtrip_without_initial_ietf(self):
        legacy = self.root / 'legacy-chapters.mkv'
        rich = inspect(self.rich, self.runner)
        command('mkvmerge', '-q', '--disable-language-ietf', '--track-order',
                ','.join(f'0:{t.id}' for t in rich.tracks), '-o', legacy, self.rich)
        original = extract_xml(self.runner, legacy, 'chapters')
        self.assertNotIn('ChapLanguageIETF', original)
        result = convert(inspect(legacy, self.runner), Options(self.root / 'legacy-output'), self.runner)
        chapters = extract_xml(self.runner, result.output, 'chapters')
        self.assertIn('ChapLanguageIETF', chapters)
        self.assertEqual(xml_key(chapters, template=original), xml_key(original))


if __name__ == '__main__':
    unittest.main()
