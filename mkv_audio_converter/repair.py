"""Opt-in, lossy Matroska salvage. Originals are opened read-only.

This scanner validates whole finite-size Clusters, not arbitrary signatures.
It never claims to reconstruct lost codec data or to prove visual correctness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from .core import (publish_exclusive, ConversionError, Media, Options, Progress, Result, Runner,
                   convert, inspect, signature)

CLUSTER = 0x1F43B675
CLUSTER_BYTES = b'\x1f\x43\xb6\x75'
SEGMENT = 0x18538067
METADATA = {0x1549A966, 0x1654AE6B, 0x1941A469, 0x1043A770, 0x1254C367}
SKIP = {0x114D9B74, 0x1C53BB6B, 0xEC, 0xBF}
MAX_CLUSTER = 64 * 1024**2


class InvalidEBML(ValueError):
    pass


def vint(data, offset=0, *, identity=False, limit=8):
    if offset >= len(data) or not data[offset]:
        raise InvalidEBML('ungültiger VINT-Anfang')
    width = 9 - data[offset].bit_length()
    if width > limit or offset + width > len(data):
        raise InvalidEBML('ungültige VINT-Länge')
    value = int.from_bytes(data[offset:offset + width], 'big')
    if not identity:
        value &= (1 << (7 * width)) - 1
    return value, width


def element(data, offset, end):
    identity, iw = vint(data, offset, identity=True, limit=4)
    size, sw = vint(data, offset + iw)
    start = offset + iw + sw
    if size == (1 << (7 * sw)) - 1:
        raise InvalidEBML('Element mit unbekannter Länge wird nicht unterstützt')
    if start + size > end:
        raise InvalidEBML('Element reicht über seine Grenze hinaus')
    return identity, start, start + size


def block_frames(data, start, end, tracks):
    track, width = vint(data, start)
    p = start + width
    if track not in tracks or p + 4 > end:
        raise InvalidEBML('ungültiger Block/Track')
    relative = int.from_bytes(data[p:p + 2], 'big', signed=True)
    lacing = (data[p + 2] >> 1) & 3
    p += 3
    if not lacing:
        return relative, 1
    count = data[p] + 1
    p += 1
    lengths = []
    if lacing == 2:
        if (end - p) <= 0 or (end - p) % count:
            raise InvalidEBML('ungültiges Fixed-Lacing')
        return relative, count
    if count < 2:
        raise InvalidEBML('Lacing mit weniger als zwei Frames')
    if lacing == 1:
        for _ in range(count - 1):
            size = 0
            while True:
                if p >= end:
                    raise InvalidEBML('abgeschnittenes Xiph-Lacing')
                value = data[p]
                p += 1
                size += value
                if value != 255:
                    break
            lengths.append(size)
    else:
        first, width = vint(data, p)
        p += width
        lengths.append(first)
        for _ in range(count - 2):
            delta, width = vint(data, p)
            p += width
            lengths.append(lengths[-1] + delta - ((1 << (7 * width - 1)) - 1))
    lengths.append(end - p - sum(lengths))
    if p > end or any(size <= 0 for size in lengths):
        raise InvalidEBML('Lacing-Framegrößen passen nicht zum Block')
    return relative, count


def validate_cluster(data: bytes, tracks: set[int], check_cancel=lambda: None):
    p, timestamp, blocks, frames, crc_count = 0, None, 0, 0, 0
    iterations = 0
    while p < len(data):
        if iterations % 256 == 0:
            check_cancel()
        iterations += 1
        identity, start, end = element(data, p, len(data))
        if identity == 0xE7:
            if timestamp is not None or not 1 <= end - start <= 8:
                raise InvalidEBML('ungültiger Cluster-Zeitstempel')
            timestamp = int.from_bytes(data[start:end], 'big')
        elif identity == 0xBF:
            crc_count += 1
            if crc_count > 1 or p != 0 or end - start != 4:
                raise InvalidEBML('ungültiges Cluster-CRC-Element')
            calculated = zlib.crc32(data[end:]) & 0xffffffff
            if calculated != int.from_bytes(data[start:end], 'little'):
                raise InvalidEBML('Cluster-CRC stimmt nicht')
        elif identity == 0xA3:
            _, count = block_frames(data, start, end, tracks)
            blocks += 1
            frames += count
        elif identity == 0xA0:
            q, found = start, False
            while q < end:
                child, content, child_end = element(data, q, end)
                if child == 0xA1:
                    if found:
                        raise InvalidEBML('mehrere Blocks in einer BlockGroup')
                    _, count = block_frames(data, content, child_end, tracks)
                    blocks += 1
                    frames += count
                    found = True
                q = child_end
            if not found:
                raise InvalidEBML('BlockGroup ohne Block')
        elif identity not in (0xA7, 0xAB, 0xEC, 0x5854):
            raise InvalidEBML(f'unbekanntes Cluster-Unterelements {identity:#x}')
        p = end
    if timestamp is None or not blocks:
        raise InvalidEBML('Cluster ohne Zeitstempel oder Medienblöcke')
    return timestamp, blocks, frames, bool(crc_count)


@dataclass(frozen=True)
class Span:
    offset: int
    length: int
    digest: str
    timestamp: int | None = None


@dataclass(frozen=True)
class Damage:
    start_byte: int
    end_byte: int
    before_seconds: float | None
    after_seconds: float | None
    reason: str


@dataclass(frozen=True)
class RepairPlan:
    media: Media
    ebml: Span
    metadata: tuple[Span, ...]
    clusters: tuple[Span, ...]
    damage: tuple[Damage, ...]
    frames: int
    crc_clusters: int

    def summary(self):
        return {
            'source': str(self.media.path), 'source_size': self.media.signature[2],
            'source_signature': list(self.media.signature),
            'accepted_clusters': len(self.clusters), 'accepted_frames': self.frames,
            'crc_checked_clusters': self.crc_clusters,
            'excluded_bytes': sum(d.end_byte - d.start_byte for d in self.damage),
            'damage': [asdict(d) for d in self.damage],
            'completeness': 'NOT_CONFIRMED',
            'limitations': [
                'Strukturprüfung ist kein Nachweis fehlerfreier Codec-Nutzdaten.',
                'Beschädigte Cluster werden vollständig ausgelassen; weitere Inhalte können unrettbar sein.',
                'Zeitangaben begrenzen Clusterbereiche ungefähr; sie sind keine exakte Verlustdauer.',
                'Zeitachse bleibt erhalten. Bildaussetzer, Stille und fehlende Inhalte sind möglich.'],
        }


def span_digest(data, start, end, check_cancel=lambda: None):
    result = hashlib.sha256()
    for offset in range(start, end, 1024**2):
        check_cancel()
        result.update(data[offset:min(end, offset + 1024**2)])
    return result.hexdigest()


def analyze(media: Media, runner: Runner, progress=lambda *_: None) -> RepairPlan:
    if signature(media.path) != media.signature:
        raise ConversionError('Quelle wurde seit dem Einlesen verändert.')
    if struct.calcsize('P') < 8:
        raise ConversionError('Der Rettungsmodus benötigt ein 64-Bit-System.')
    tracks = {int(t.properties['number']) for t in media.tracks}
    scale = media.data['container'].get('properties', {}).get('timestamp_scale', 1_000_000) / 1e9
    size = media.signature[2]
    clusters, metadata, damage = [], [], []
    frames = crc_clusters = 0
    previous = None
    required = {0x1549A966: 0, 0x1654AE6B: 0}
    with media.path.open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
        identity, _, ebml_end = element(data, 0, size)
        if identity != 0x1A45DFA3 or ebml_end > 1024**2:
            raise ConversionError('Kein unterstützter EBML-Dateikopf.')
        identity, iw = vint(data, ebml_end, identity=True, limit=4)
        length, sw = vint(data, ebml_end + iw)
        if identity != SEGMENT:
            raise ConversionError('Matroska-Segment fehlt.')
        p = ebml_end + iw + sw
        if length != (1 << (7 * sw)) - 1 and p + length != size:
            raise ConversionError('Verknüpfte/mehrteilige oder abgeschnittene Segmente werden nicht unterstützt.')
        ebml = Span(0, ebml_end, hashlib.sha256(data[:ebml_end]).hexdigest())
        missing_start, missing_reason = None, ''
        while p < size:
            runner.check_cancel()
            progress(p / size, 'Matroska-Cluster untersuchen')
            try:
                identity, start, end = element(data, p, size)
                if identity == CLUSTER:
                    if end - start > MAX_CLUSTER:
                        raise InvalidEBML('Cluster größer als 64 MiB')
                    body = data[start:end]
                    timestamp, block_count, frame_count, has_crc = validate_cluster(body, tracks, runner.check_cancel)
                    if (previous is not None and timestamp * scale < previous * scale - 1) or (
                            media.duration > 0 and timestamp * scale > media.duration + 60):
                        raise InvalidEBML('unplausibler Cluster-Zeitstempel')
                    if missing_start is not None:
                        damage.append(Damage(missing_start, p, previous * scale if previous is not None else None,
                                             timestamp * scale, missing_reason))
                        missing_start = None
                    clusters.append(Span(p, end - p, span_digest(data, p, end, runner.check_cancel), timestamp))
                    frames += frame_count
                    crc_clusters += has_crc
                    previous = timestamp
                elif identity in METADATA and missing_start is None:
                    if identity in required:
                        required[identity] += 1
                    metadata.append(Span(p, end - p, span_digest(data, p, end, runner.check_cancel)))
                elif identity not in SKIP or missing_start is not None:
                    raise InvalidEBML(f'unerwartetes Segment-Element {identity:#x}')
                p = end
                continue
            except (InvalidEBML, IndexError) as error:
                if missing_start is None:
                    missing_start, missing_reason = p, str(error)
            # Bounded searches remain cancellable even on a long damaged area.
            search = p + 1
            while search < size:
                runner.check_cancel()
                stop = min(size, search + 8 * 1024**2)
                found = data.find(CLUSTER_BYTES, search, stop)
                if found >= 0:
                    p = found
                    break
                progress(stop / size, 'Nach lesbaren Clustern suchen')
                search = max(search + 1, stop - 3)
            else:
                p = size
        if missing_start is not None:
            damage.append(Damage(missing_start, size, previous * scale if previous is not None else None,
                                 None, missing_reason))
    if any(n != 1 for n in required.values()) or not clusters:
        raise ConversionError('Info-/Tracks-Kopf oder lesbare Cluster fehlen; automatische Rettung nicht möglich.')
    if signature(media.path) != media.signature:
        raise ConversionError('Quelle wurde während der Rettungsanalyse verändert.')
    progress(1., 'Rettungsanalyse abgeschlossen')
    return RepairPlan(media, ebml, tuple(metadata), tuple(clusters), tuple(damage), frames, crc_clusters)


def write_candidate(plan: RepairPlan, destination: Path, runner: Runner, progress=lambda *_: None):
    if signature(plan.media.path) != plan.media.signature:
        raise ConversionError('Quelle wurde nach der Rettungsanalyse verändert.')
    spans = [plan.ebml, *plan.metadata, *plan.clusters]
    total = sum(s.length for s in spans)
    copied = 0
    with plan.media.path.open('rb') as source, destination.open('xb') as target:
        for index, span in enumerate(spans):
            if index == 1:
                target.write(b'\x18\x53\x80\x67\x01\xff\xff\xff\xff\xff\xff\xff')
            source.seek(span.offset)
            digest = hashlib.sha256()
            remaining = span.length
            while remaining:
                runner.check_cancel()
                block = source.read(min(1024**2, remaining))
                if not block:
                    raise ConversionError('Quelle wurde beim Kopieren abgeschnitten.')
                target.write(block)
                digest.update(block)
                copied += len(block)
                remaining -= len(block)
                progress(copied / total, 'Lesbare Cluster unverändert kopieren')
            if digest.hexdigest() != span.digest:
                raise ConversionError('Quelldaten stimmen nicht mehr mit dem Rettungsplan überein.')
        target.flush()
        os.fsync(target.fileno())
    if signature(plan.media.path) != plan.media.signature:
        raise ConversionError('Quelle wurde während der Rettung verändert.')


@dataclass
class RecoveryResult(Result):
    recovered: bool = True
    report_path: Path | None = None


def recover(plan: RepairPlan, options: Options, runner: Runner, *, accept_loss: bool = False,
            progress=lambda *_: None) -> RecoveryResult:
    if not accept_loss:
        raise ConversionError('Rettung benötigt ausdrückliche Zustimmung zu möglichen Datenverlusten.')
    if not plan.media.dts_tracks:
        raise ConversionError('Dieser Rettungsmodus ist für MKVs mit DTS-Tonspuren vorgesehen.')
    progress = Progress(progress)
    destination = (options.output_dir or plan.media.path.parent).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    # Candidate + audio preparation + converted result coexist temporarily.
    if shutil.disk_usage(destination).free < plan.media.signature[2] * 3 + 1024**3:
        raise ConversionError('Rettung benötigt ungefähr dreimal die Originalgröße plus 1 GiB freien Platz.')
    start_warnings = len(runner.warnings)
    initial_diagnostics = dict(runner.diagnostics)
    with tempfile.TemporaryDirectory(prefix='.mkv-audio-converter-recovery-', dir=destination) as directory:
        work = Path(directory)
        # Fail before a long salvage job if safe exclusive publication is unavailable.
        probe = work / 'hardlink-check'
        probe.write_bytes(b'')
        try:
            publish_exclusive(probe, work / 'publication-target')
        except OSError as error:
            raise ConversionError('Das Ziel unterstützt keine sichere Veröffentlichung '
                                  '(Linux: Btrfs/ext4; Windows: lokales NTFS/exFAT).') from error
        candidate = work / (plan.media.path.stem + '_recovered.mkv')
        write_candidate(plan, candidate, runner, lambda p, phase: progress(.2 * p, phase))
        media = inspect(candidate, runner)
        # Only this explicit workflow enables tolerant input decoding. All output
        # checks and the complete AC3 decode remain strict.
        result = convert(media, replace(options, output_dir=work, audio_recovery=True, deep_verify=True), runner,
                         lambda p, phase: progress(.2 + .79 * p, phase))
        if result.output is None:
            raise ConversionError('Rettung hat keine konvertierte Datei erzeugt.')
        runner.check_cancel()
        if signature(plan.media.path) != plan.media.signature:
            raise ConversionError('Original wurde während des Rettungsversuchs verändert.')
        report = plan.summary()
        report.update({'kind': 'SALVAGED_WITH_POSSIBLE_LOSS', 'audio_error_concealment_enabled': True,
                       'warnings': runner.warnings[start_warnings:], 'checks': result.checks,
                       'video_fully_decoded': False,
                       'checks_reference': 'validated_cluster_candidate_not_complete_original',
                       'decoder_diagnostic_counts': {key: count - initial_diagnostics.get(key, 0)
                            for key, count in runner.diagnostics.items() if count > initial_diagnostics.get(key, 0)}})
        for index in range(10000):
            suffix = '' if not index else f'_{index + 1}'
            final = destination / f'{plan.media.path.stem}_recovered_ac3{suffix}.mkv'
            sidecar = final.with_suffix('.recovery.json')
            report['output'] = str(final)
            temp_report = work / 'report.json'
            temp_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
            with temp_report.open('rb') as file:
                os.fsync(file.fileno())
            linked = False
            report_signature = signature(temp_report)
            try:
                publish_exclusive(temp_report, sidecar)
                linked = True
                publish_exclusive(result.output, final)
                break
            except FileExistsError:
                if linked and signature(sidecar) == report_signature:
                    sidecar.unlink()
                continue
            except OSError as error:
                if linked and signature(sidecar) == report_signature:
                    sidecar.unlink()
                raise ConversionError(f'Rettung konnte nicht sicher veröffentlicht werden: {error}') from error
        else:
            raise ConversionError('Zu viele gleichnamige Rettungsdateien.')
        progress(1., 'Gerettete Kopie erstellt; Verlustbericht beachten')
        return RecoveryResult(plan.media.path, final, warnings=[
            'Gerettete Datei mit möglichen Bild-/Tonlücken; Vollständigkeit nicht bestätigt.',
            *runner.warnings[start_warnings:]], checks=result.checks, report_path=sidecar)
