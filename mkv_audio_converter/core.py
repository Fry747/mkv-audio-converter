"""Qt-independent conversion engine. All external commands run without a shell.

Only files in a private temporary directory are ever modified. Publication uses
exclusive publication on the destination filesystem (Windows no-replace
rename, POSIX hard link); existing names are never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from . import runtime
from .processes import ThreadedPipes, spawn


class ConversionError(RuntimeError):
    pass


class Cancelled(ConversionError):
    pass


class SourceDamageError(ConversionError):
    """Input recovery would silently skip data, so conversion must stop."""


class Progress:
    """Monotonic per-file progress despite interleaving and tool resets."""
    def __init__(self, callback):
        self.callback = callback
        self.value = 0.0

    def __call__(self, value: float, phase: str):
        self.value = max(self.value, min(1.0, max(0.0, value)))
        self.callback(self.value, phase)


TOOLS = runtime.TOOLS
FLAG_OPTIONS = {
    "default_track": ("--default-track-flag", "flag-default", True),
    "forced_track": ("--forced-display-flag", "flag-forced", False),
    "enabled_track": ("--track-enabled-flag", "flag-enabled", True),
    "flag_hearing_impaired": ("--hearing-impaired-flag", "flag-hearing-impaired", False),
    "flag_visual_impaired": ("--visual-impaired-flag", "flag-visual-impaired", False),
    "flag_text_descriptions": ("--text-descriptions-flag", "flag-text-descriptions", False),
    "flag_original": ("--original-flag", "flag-original", False),
    "flag_commentary": ("--commentary-flag", "flag-commentary", False),
}
STALE_TAGS = {"BPS", "DURATION", "NUMBER_OF_BYTES", "NUMBER_OF_FRAMES", "ENCODER",
              "_STATISTICS_WRITING_APP", "_STATISTICS_WRITING_DATE_UTC", "_STATISTICS_TAGS"}


@dataclass(frozen=True)
class Track:
    id: int
    type: str
    codec: str
    properties: dict

    @property
    def dts(self) -> bool:
        return self.type == "audio" and (
            self.properties.get("codec_id") == "A_DTS" or
            self.codec.upper().startswith("DTS"))

    @property
    def uid(self) -> int:
        return int(self.properties["uid"])

    @property
    def channels(self) -> int:
        return int(self.properties.get("audio_channels", 0))


@dataclass(frozen=True)
class Media:
    path: Path
    data: dict
    tracks: tuple[Track, ...]
    signature: tuple[int, int, int, int]

    @property
    def dts_tracks(self) -> tuple[Track, ...]:
        return tuple(t for t in self.tracks if t.dts)

    @property
    def duration(self) -> float:
        return self.data.get("container", {}).get("properties", {}).get("duration", 0) / 1e9


@dataclass(frozen=True)
class Options:
    output_dir: Path | None = None
    bitrate: int = 448
    downmix: bool = True
    deep_verify: bool = True
    audio_recovery: bool = False  # enabled only by the explicit salvage workflow

    def __post_init__(self):
        if self.bitrate not in (384, 448, 640):
            raise ValueError("AC3-Bitrate muss 384, 448 oder 640 kbit/s sein.")


@dataclass
class Result:
    source: Path
    output: Path | None
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


def signature(path: Path) -> tuple[int, int, int, int]:
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def discover(paths: list[Path], recursive: bool = True,
             check_cancel: Callable[[], None] = lambda: None) -> list[Path]:
    """Do not follow directory symlinks; skip this app's private workspaces."""
    found = set()
    for entry in paths:
        check_cancel()
        entry = Path(entry).expanduser().resolve()
        if entry.is_file() and entry.suffix.lower() == ".mkv":
            found.add(entry)
        elif entry.is_dir():
            for root, dirs, files in os.walk(entry, followlinks=False):
                check_cancel()
                dirs[:] = sorted(d for d in dirs if not d.startswith(".mkv-audio-converter-"))
                for name in files:
                    p = Path(root) / name
                    if p.suffix.lower() == ".mkv" and p.is_file():
                        found.add(p.resolve())
                if not recursive:
                    dirs.clear()
    return sorted(found, key=lambda p: str(p).casefold())


class Runner:
    """Drain output incrementally, bound memory, and honour cancellation even
    while a child is silent. A process group also covers child processes."""
    def __init__(self, cancel: threading.Event | None = None,
                 log: Callable[[str], None] = lambda _: None, *,
                 tool_paths: dict[str, Path] | None = None, threaded_io: bool | None = None):
        self.tool_paths = dict(tool_paths or {})
        self.threaded_io = runtime.windows() if threaded_io is None else threaded_io
        self.cancel = cancel if cancel is not None else threading.Event()
        self.log = log
        self.warnings: list[str] = []
        self.diagnostics: dict[str, int] = {}

    def find_tool(self, name):
        if self.tool_paths:
            path = self.tool_paths.get(name)
            return str(path) if path and Path(path).is_file() else None
        return runtime.resolve_tool(name)

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled("Abgebrochen; unvollständige Ausgabe entfernt.")

    def run(self, args: list[str | Path], *, capture: bool = False,
            on_line: Callable[[str], None] | None = None,
            timeout: float | None = None, stderr_error: bool = False,
            reject_resync: bool = False) -> str:
        self.check_cancel()
        command = [str(x) for x in args]
        tool = command[0]
        if tool in TOOLS and (runtime.windows() or self.tool_paths):
            resolved = self.find_tool(tool)
            if not resolved:
                raise ConversionError(f"Werkzeug fehlt: {tool}. Windows-Werkzeuge über das Werkzeugmenü einrichten.")
            command[0] = resolved
        if runtime.windows() and Path(command[0]).stem.casefold().startswith(('mkvmerge', 'mkvextract', 'mkvpropedit')):
            command[1:1] = ['--ui-language', 'en_US', '--output-charset', 'UTF-8']
        rendered = subprocess.list2cmdline(command) if runtime.windows() else shlex.join(command)
        self.log(f"[{time.strftime('%H:%M:%S')}] $ " + rendered)
        env = os.environ.copy()
        env["LC_ALL"] = "C.UTF-8"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        for name in list(env):
            if name.startswith(("MKVMERGE_", "MKVTOOLNIX_", "MTX_")):
                env.pop(name)
        chunks: list[str] = []
        capture_size = 0
        tail: deque[str] = deque(maxlen=30)
        stderr_lines: deque[str] = deque(maxlen=30)
        command_warnings: list[str] = []
        start = time.monotonic()
        try:
            proc, job = spawn(command, env)
        except OSError as e:
            raise ConversionError(f"{command[0]} konnte nicht gestartet werden: {e}") from e
        buffers = {proc.stdout: b"", proc.stderr: b""}

        def emit(raw: bytes, stdout: bool):
            nonlocal capture_size
            line = raw.decode("utf-8", errors="replace")
            if not stdout:
                for label, pattern in (("block_decode_failed", "Failed to decode"),
                                       ("unsupported_deficit_samples", "Deficit samples"),
                                       ("decoder_packet_rejected", "Error submitting packet"),
                                       ("invalid_data", "Invalid data found")):
                    if pattern in line:
                        self.diagnostics[label] = self.diagnostics.get(label, 0) + 1
                        break
            is_warning = line.startswith(("#GUI#warning ", "Warning:"))
            if is_warning:
                message = line.removeprefix("#GUI#warning ")
                warning = f"{Path(command[0]).name}: Warnung: {message}"
                command_warnings.append(warning)
                self.warnings.append(warning)
                self.log(warning)
                if reject_resync and re.search(r"resync|invalid EBML", message, re.I):
                    raise SourceDamageError(
                        "Quelle enthält beschädigte oder nicht lesbare Matroska-Daten; "
                        "Wiederherstellungssuche abgebrochen, damit keine Daten unbemerkt verloren gehen. "
                        + message)
            if stdout and capture:
                capture_size += len(raw) + 1
                if capture_size > 64 * 1024 * 1024:
                    raise ConversionError("Werkzeugausgabe überschreitet 64 MiB.")
                chunks.append(line + "\n")
            if stdout and on_line:
                on_line(line)
            if line:
                tail.append(line)
                if not stdout:
                    stderr_lines.append(line)
                if not is_warning and (not stdout or (not capture and on_line is None)):
                    self.log(line)

        def check_running():
            self.check_cancel()
            if timeout is not None and time.monotonic() - start > timeout:
                raise ConversionError(f"Zeitlimit für {command[0]} überschritten.")

        def consume(pipe, block):
            if not block:
                if buffers[pipe]:
                    emit(buffers[pipe], pipe is proc.stdout)
                buffers.pop(pipe)
                return
            parts = re.split(b"[\r\n]", buffers[pipe] + block)
            buffers[pipe] = parts.pop()
            if len(buffers[pipe]) > 8 * 1024 * 1024:
                raise ConversionError("Ungültig lange Werkzeugausgabe.")
            for raw in parts:
                emit(raw, pipe is proc.stdout)

        readers = None
        try:
            if self.threaded_io:
                readers = ThreadedPipes(list(buffers))
                for pipe, block in readers.blocks(check_running):
                    consume(pipe, block)
            else:
                with selectors.DefaultSelector() as sel:
                    for pipe in buffers:
                        sel.register(pipe, selectors.EVENT_READ)
                    while sel.get_map():
                        check_running()
                        for key, _ in sel.select(0.15):
                            pipe = key.fileobj
                            block = os.read(pipe.fileno(), 65536)
                            consume(pipe, block)
                            if not block:
                                sel.unregister(pipe)
            # A child may close stdout/stderr before exiting. Keep timeout and
            # cancellation effective after both pipes have reached EOF too.
            while proc.poll() is None:
                check_running()
                try:
                    proc.wait(timeout=.15)
                except subprocess.TimeoutExpired:
                    pass
            code = proc.returncode
            self.check_cancel()
            if stderr_error and stderr_lines:
                raise ConversionError(f"{Path(command[0]).name}: Fehlermeldungen:\n" + "\n".join(stderr_lines))
            is_mkv = Path(command[0]).stem.casefold().startswith(("mkvmerge", "mkvextract", "mkvpropedit"))
            if code == 1 and is_mkv:
                if not command_warnings:
                    warning = f"{Path(command[0]).name}: Warnung (Exit 1): " + "\n".join(tail)
                    self.warnings.append(warning)
                    self.log(warning)
            elif code != 0:
                raise ConversionError(f"{Path(command[0]).name}: Exit {code}\n" + "\n".join(tail))
            elif stderr_lines and not capture:
                self.warnings.append(f"{Path(command[0]).name}: " + "\n".join(stderr_lines))
            self.log(f"[{time.strftime('%H:%M:%S')}] {Path(command[0]).name} abgeschlossen "
                     f"in {time.monotonic() - start:.1f} s")
            return "".join(chunks)
        finally:
            if job is not None:
                job.close()  # also terminates descendants holding inherited pipes
                proc.wait(timeout=5)
            elif proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                except ProcessLookupError:
                    proc.wait()
            if readers is not None:
                readers.close()
            proc.stdout.close()
            proc.stderr.close()

    def json(self, args: list[str | Path]) -> dict:
        raw = self.run(args, capture=True, stderr_error=Path(str(args[0])).stem.casefold() == "ffprobe")
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as e:
            raise ConversionError(f"Ungültige JSON-Antwort von {args[0]}.") from e


def check_tools(runner: Runner) -> dict[str, str]:
    missing = [tool for tool in TOOLS if not runner.find_tool(tool)]
    if missing:
        raise ConversionError("Fehlende Programme: " + ", ".join(missing) + ". Siehe README.md.")
    versions = {tool: runner.run([tool, "-version" if tool.startswith("ff") else "--version"],
                                 capture=True, timeout=15).splitlines()[0] for tool in TOOLS}
    if runtime.windows():
        for tool, version in versions.items():
            pattern = r"\bversion\s+n?(\d+)\." if tool.startswith("ff") else r"\bv(\d+)\."
            found = re.search(pattern, version, re.I)
            minimum = 8 if tool.startswith("ff") else 102
            if not found or int(found[1]) < minimum:
                raise ConversionError(f"Nicht unterstützte Windows-Werkzeugversion: {version}. "
                    "Benötigt werden FFmpeg/FFprobe ab 8 und MKVToolNix ab 102. "
                    "Bitte über Werkzeuge → Windows-Werkzeuge einrichten aktualisieren.")
    enc = runner.run(["ffmpeg", "-hide_banner", "-encoders"], capture=True, timeout=15)
    dec = runner.run(["ffmpeg", "-hide_banner", "-decoders"], capture=True, timeout=15)
    if not re.search(r"^\s*A\S*\s+ac3\s", enc, re.M):
        raise ConversionError("Diese FFmpeg-Installation hat keinen AC3-Encoder.")
    if not re.search(r"^\s*A\S*\s+dca\s", dec, re.M):
        raise ConversionError("Diese FFmpeg-Installation hat keinen DTS-Decoder (dca).")
    return versions


def inspect(path: Path, runner: Runner) -> Media:
    path = Path(path).expanduser().resolve(strict=True)
    before = signature(path)
    data = runner.json(["mkvmerge", "-J", path])
    container = data.get("container", {})
    if data.get("errors") or not container.get("supported") or container.get("type") != "Matroska":
        raise ConversionError(f"Keine lesbare Matroska-Datei: {path}")
    tracks = tuple(Track(t["id"], t["type"], t["codec"], t.get("properties", {}))
                   for t in data.get("tracks", []))
    if not tracks or any("uid" not in t.properties for t in tracks):
        raise ConversionError("Datei enthält keine unterstützten Spuren mit Track-UIDs.")
    if len({t.uid for t in tracks}) != len(tracks):
        raise ConversionError("Doppelte Track-UIDs; Metadatenzuordnung ist nicht eindeutig.")
    if signature(path) != before:
        raise ConversionError("Quelldatei wurde während der Prüfung verändert.")
    return Media(path, data, tracks, before)


# Delimiters include underscores used in release-style names. Unicode letters
# and digits remain word characters so DTS inside a word is never replaced.
_DTS_TITLE = re.compile(r"""
    (?<![^\W_])DTS
    (?:
        [ ._-]+HD(?:[ ._-]+(?:Master[ ._-]+Audio|MA|
                             High[ ._-]+Resolution(?:[ ._-]+Audio)?|HRA|HR))?
        |[ ._-]+ES(?:[ ._-]+(?:Discrete|Matrix))?
        |[ ._:\-]+X
        |[ ._-]+(?:96[/ ._-]24|Express|Core|Digital[ ._-]+Surround)
    )?
    (?![^\W_])
    (?: (?P<separator>[ ._-]+)(?P<layout>[1-9]\.[01](?:\.[1-9])?)
        (?![^\W_]|\.\d)
    )?
""", re.IGNORECASE | re.VERBOSE)


def converted_track_name(track: Track) -> str:
    """Update explicit DTS labels only on converted audio tracks.

    Keep surrounding language/descriptive text and separators verbatim. Only
    an immediately attached layout is changed during the known >6 -> 5.1
    downmix. Do not guess a channel layout from channel count otherwise, or
    invent a title/codec suffix when no DTS label was present.
    """
    name = track.properties.get("track_name", "")
    if not track.dts:
        return name

    def replacement(match):
        layout = match["layout"]
        if layout is None:
            return "AC3"
        if track.channels > 6:
            layout = "5.1"
        return "AC3" + match["separator"] + layout

    return _DTS_TITLE.sub(replacement, name)


def track_options(track: Track, tid: int = 0) -> list[str]:
    p = track.properties
    args = ["--language", f"{tid}:{p.get('language_ietf', p.get('language', 'und'))}",
            "--track-name", f"{tid}:{converted_track_name(track)}"]
    for key, (option, _, default) in FLAG_OPTIONS.items():
        if key in p or key in ("default_track", "forced_track", "enabled_track"):
            args += [option, f"{tid}:{int(p.get(key, default))}"]
    return args


def remux_command(media: Media, replacements: dict[int, Path], output: Path) -> list[str | Path]:
    order = []
    file_ids = {tid: i + 1 for i, tid in enumerate(replacements)}
    for track in media.tracks:
        order.append(f"{file_ids[track.id]}:0" if track.id in replacements else f"0:{track.id}")
    args: list[str | Path] = ["mkvmerge", "--gui-mode", "--normalize-language-ietf", "off",
                            "--disable-track-statistics-tags", "--track-order", ",".join(order),
                            "-o", output, "--no-chapters", "--no-track-tags", "--no-global-tags"]
    kept = [str(t.id) for t in media.tracks if t.type == "audio" and t.id not in replacements]
    args += ["--audio-tracks", ",".join(kept)] if kept else ["--no-audio"]
    args.append(media.path)
    for tid, path in replacements.items():
        track = next(t for t in media.tracks if t.id == tid)
        args += ["--no-chapters", "--no-track-tags", "--no-global-tags", "--no-attachments"]
        args += track_options(track)
        args.append(path)
    return args


def sanitize_tags(raw: str, replaced_uids: set[int]) -> str:
    """Keep descriptive tags and references; discard obsolete DTS statistics."""
    try:
        root = ET.fromstring(raw or "<Tags />")
    except ET.ParseError as e:
        raise ConversionError("Ungültige Matroska-Tags (XML).") from e
    for tag in root.findall("Tag"):
        uids = {int(e.text or 0) for e in tag.findall("Targets/TrackUID")}
        if uids & replaced_uids:
            # A tag targeting several tracks cannot safely retain old statistics.
            for parent in tag.iter():
                for child in list(parent):
                    if child.tag == "Simple" and child.findtext("Name", "").upper() in STALE_TAGS:
                        parent.remove(child)
            if not tag.findall("Simple"):
                root.remove(tag)
    return ET.tostring(root, encoding="unicode")


def xml_key(raw: str, template: str | None = None):
    if not raw.strip():
        return None
    root = ET.fromstring(raw)
    if not list(root):
        return None

    if template and template.strip():
        def remove_derived(node, original):
            # MKVToolNix may add an IETF language derived from a legacy field.
            # Existing IETF values must still match exactly.
            present = {child.tag for child in original}
            for child in list(node):
                if child.tag in ("TagLanguageIETF", "ChapLanguageIETF") and child.tag not in present:
                    node.remove(child)
            for child, prior in zip(node, original):
                remove_derived(child, prior)
        remove_derived(root, ET.fromstring(template))

    def key(node):
        return (node.tag, "" if list(node) else (node.text or ""), tuple(sorted(node.attrib.items())),
                tuple(key(child) for child in node))
    return key(root)


def xml_difference(expected: str, actual: str) -> str:
    """Give the first differing element, rather than losing all diagnostics."""
    a, b = xml_key(expected), xml_key(actual, template=expected)

    def difference(old, new, path):
        if old is None or new is None:
            return f"{path}: XML fehlt oder ist leer"
        if old[:3] != new[:3]:
            return f"{path}: erwartet {old[:3]!r}, erhalten {new[:3]!r}"
        if len(old[3]) != len(new[3]):
            return f"{path}: unterschiedliche Unterelemente ({len(old[3])}/{len(new[3])})"
        for index, (left, right) in enumerate(zip(old[3], new[3]), 1):
            if left != right:
                return difference(left, right, f"{path}/{left[0]}[{index}]")
        return path
    return difference(a, b, a[0] if a else "XML")[:600]


def extract_xml(runner: Runner, path: Path, mode: str) -> str:
    return runner.run(["mkvextract", path, mode], capture=True)


def remap_chapters(raw: str, source: Media, target: Media) -> str:
    if not raw.strip():
        return raw
    numbers = {a.properties["number"]: b.properties["number"]
               for a, b in zip(source.tracks, target.tracks)}
    root = ET.fromstring(raw)
    for item in root.iter("ChapterTrackNumber"):
        old = int(item.text or "0")
        if old not in numbers:
            raise ConversionError("Kapitel verweist auf eine unbekannte Spurnummer.")
        item.text = str(numbers[old])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def restore_metadata(media: Media, output: Path, work: Path, runner: Runner,
                     changed_uids: set[int] | None = None) -> tuple[str, str]:
    """Restore UIDs before importing original XML references. This also handles
    mkvmerge's automatic UID regeneration for MakeMKV sources."""
    args: list[str | Path] = ["mkvpropedit", output, "--normalize-language-ietf", "off"]
    for position, track in enumerate(media.tracks, 1):
        p = track.properties
        args += ["--edit", f"track:{position}", "--set", f"track-uid={track.uid}"]
        args += ["--set", f"language={p.get('language', 'und')}"]
        if "language_ietf" in p:
            args += ["--set", f"language-ietf={p['language_ietf']}"]
        else:
            args += ["--delete", "language-ietf"]
        if "track_name" in p:
            args += ["--set", f"name={converted_track_name(track)}"]
        else:
            args += ["--delete", "name"]
        for key, (_, prop, default) in FLAG_OPTIONS.items():
            if key in p or key in ("default_track", "forced_track", "enabled_track"):
                args += ["--set", f"{prop}={int(p.get(key, default))}"]
    runner.run(args)
    chapters = remap_chapters(extract_xml(runner, media.path, "chapters"), media, inspect(output, runner))
    tags = sanitize_tags(extract_xml(runner, media.path, "tags"),
                         changed_uids if changed_uids is not None else {t.uid for t in media.dts_tracks})
    chapters_file, tags_file = work / "chapters.xml", work / "tags.xml"
    chapters_file.write_text(chapters, encoding="utf-8")
    tags_file.write_text(tags, encoding="utf-8")
    runner.run(["mkvpropedit", output, "--chapters", chapters_file if chapters.strip() else "",
                "--tags", f"all:{tags_file}" if xml_key(tags) else "all:"])
    return chapters, tags


def metadata_check(source: Media, target: Media, chapters: str, tags: str,
                   runner: Runner) -> list[str]:
    if len(source.tracks) != len(target.tracks):
        raise ConversionError("Ergebnisprüfung: Anzahl der Spuren stimmt nicht.")
    for old, new in zip(source.tracks, target.tracks):
        a, b = old.properties, new.properties
        codec = "A_AC3" if old.dts else a.get("codec_id")
        if old.type != new.type or b.get("codec_id") != codec or old.uid != new.uid:
            raise ConversionError(f"Ergebnisprüfung: Spurreihenfolge/Codec/UID abweichend (ID {old.id}).")
        for key, default in (("language", "eng"), ("language_ietf", None), ("track_name", "")):
            expected = converted_track_name(old) if key == "track_name" else a.get(key, default)
            if expected != b.get(key, default):
                raise ConversionError(f"Ergebnisprüfung: {key} weicht vom erwarteten Wert ab (ID {old.id}).")
        for key, (_, _, default) in FLAG_OPTIONS.items():
            if a.get(key, default) != b.get(key, default):
                raise ConversionError(f"Ergebnisprüfung: Flag {key} verändert (ID {old.id}).")
        if old.dts:
            if new.channels != min(old.channels, 6) or b.get("audio_sampling_frequency") != 48000:
                raise ConversionError(f"Ergebnisprüfung: AC3-Kanäle/Abtastrate falsch (ID {old.id}).")
    title = lambda m: m.data["container"].get("properties", {}).get("title", "")
    if title(source) != title(target):
        raise ConversionError("Ergebnisprüfung: Filmtitel verändert.")
    attachment_key = lambda m: [(a.get("file_name"), a.get("content_type"), a.get("size"),
                                a.get("description", ""), a.get("properties", {}).get("uid"))
                               for a in m.data.get("attachments", [])]
    if attachment_key(source) != attachment_key(target):
        raise ConversionError("Ergebnisprüfung: Anhänge verändert.")
    for mode, expected in (("chapters", chapters), ("tags", tags)):
        actual = extract_xml(runner, target.path, mode)
        if xml_key(actual, template=expected) != xml_key(expected):
            raise ConversionError(f"Ergebnisprüfung: {mode} verändert. " + xml_difference(expected, actual))
    # minimum_timestamp is available only for tracks starting near the file's
    # beginning. Full packet validation below also covers very late audio tracks.
    for old, new in zip(source.tracks, target.tracks):
        a, b = old.properties.get("minimum_timestamp"), new.properties.get("minimum_timestamp")
        if a is not None and b is not None and abs(a - b) > 2_000_000:
            raise ConversionError(f"Ergebnisprüfung: Startzeit verändert (ID {old.id}).")
    checks = ["Spurreihenfolge, Codecs, UIDs, Sprache, erwartete Spurtitel und Flags geprüft",
              "Kapitel, beschreibende Tags, Filmtitel und Anhang-Metadaten geprüft",
              "Verfügbare Startzeitstempel geprüft (Toleranz 2 ms)"]
    for track in source.tracks:
        old_name = track.properties.get("track_name", "")
        new_name = converted_track_name(track)
        if old_name != new_name:
            checks.append(f"Spurtitel angepasst (ID {track.id}): {old_name!r} → {new_name!r}")
    return checks


def stream_map(media: Media, runner: Runner) -> dict[int, int]:
    data = runner.json(["ffprobe", "-v", "error", "-show_streams", "-of", "json", media.path])
    streams = [s for s in data.get("streams", []) if s.get("codec_type") != "attachment"]
    if len(streams) != len(media.tracks):
        raise ConversionError("FFprobe-Spuren lassen sich nicht eindeutig zuordnen.")
    result = {}
    for track, stream in zip(media.tracks, streams):
        kind = "subtitle" if track.type == "subtitles" else track.type
        if kind != stream.get("codec_type") or (track.dts and stream.get("codec_name") != "dts"):
            raise ConversionError("FFprobe-Spurreihenfolge stimmt nicht mit MKVToolNix überein.")
        result[int(stream["index"])] = track.id
    return result


@dataclass
class PacketStats:
    count: int = 0
    first: float = math.inf
    end: float = -math.inf
    digest: object = field(default_factory=hashlib.sha256)


def scan_packets(media: Media, runner: Runner, work: Path, *, write: bool,
                 reference: dict[int, PacketStats] | None = None,
                 deep: bool = True, progress: Callable[[float], None] = lambda _: None,
                 tolerate_errors: bool = False) -> dict[int, PacketStats]:
    mapping = stream_map(media, runner)
    stats = {t.id: PacketStats() for t in media.tracks}
    tracks = {t.id: t for t in media.tracks}
    # Timestamp records for copied tracks live on disk; memory stays bounded on
    # multi-hour files. Track IDs change on remux; use stable track positions.
    files = {}
    try:
        for pos, track in enumerate(media.tracks):
            if deep and (write and not track.dts or not write and reference is not None and
                         (work / f"packets-{pos}.txt").exists()):
                files[track.id] = (work / f"packets-{pos}.txt").open("w" if write else "r", encoding="ascii")
        def line(raw: str):
            parts = dict(part.split("=", 1) for part in raw.split("|") if "=" in part)
            if "stream_index" not in parts:
                return
            index = int(parts["stream_index"])
            if index not in mapping:  # ffprobe may expose font/image attachments
                return
            tid = mapping[index]
            s = stats[tid]
            s.count += 1
            try:
                pts = float(parts["pts_time"])
                duration = float(parts.get("duration_time", "0"))
            except (KeyError, ValueError) as e:
                raise ConversionError(f"Nicht prüfbare Paketzeitstempel in Spur {tid}.") from e
            if not math.isfinite(pts) or not math.isfinite(duration) or duration < 0:
                raise ConversionError(f"Ungültige Paketzeitstempel in Spur {tid}.")
            delay = tracks[tid].properties.get("codec_delay", 0) / 1e9
            s.first = min(s.first, pts + delay)
            s.end = max(s.end, pts + duration + delay)
            progress(min(1.0, max(0.0, pts / max(media.duration, 1))))
            if tid in files:
                payload = parts.get("data_hash", "")
                if not payload.startswith("SHA256:"):
                    raise ConversionError("FFprobe liefert keine Paketprüfsummen.")
                s.digest.update(payload.encode("ascii"))
                if write:
                    files[tid].write(f"{pts:.9f}\n")
                else:
                    prior = files[tid].readline()
                    if not prior or abs(float(prior) - pts) > .002:
                        raise ConversionError(f"Kopierte Paketzeitstempel verändert (Spur {tid}).")
        args: list[str | Path] = ["ffprobe", "-v", "error", "-show_packets",
                                  "-show_entries", "packet=stream_index,pts_time,duration_time,data_hash",
                                  "-of", "compact=p=0"]
        if deep:
            args += ["-show_data_hash", "sha256"]
        args.append(media.path)
        runner.run(args, on_line=line, stderr_error=not tolerate_errors)
        if not write:
            for f in files.values():
                if f.readline():
                    raise ConversionError("Kopierte Spur enthält weniger Pakete als das Original.")
        for tid, s in stats.items():
            if s.count == 0 and tracks[tid].type in ("audio", "video"):
                raise ConversionError(f"Leere Audio-/Videospur {tid}.")
        return stats
    finally:
        for f in files.values():
            f.close()


def packet_check(source: Media, target: Media, runner: Runner, work: Path, deep: bool,
                 progress: Callable[[float], None], *, tolerate_source_errors: bool = False) -> list[str]:
    before = scan_packets(source, runner, work, write=True, deep=deep, progress=lambda p: progress(p * .5),
                          tolerate_errors=tolerate_source_errors)
    after = scan_packets(target, runner, work, write=False, reference=before, deep=deep,
                         progress=lambda p: progress(.5 + p * .5))
    for old, new in zip(source.tracks, target.tracks):
        a, b = before[old.id], after[new.id]
        if old.dts:
            if abs(a.first - b.first) > .003 or abs(a.end - b.end) > .080:
                raise ConversionError(f"Audio-Synchronisationsprüfung fehlgeschlagen (Spur {old.id}): "
                                      f"Start {b.first-a.first:+.3f}s, Ende {b.end-a.end:+.3f}s.")
        elif deep and (a.count != b.count or a.digest.digest() != b.digest.digest()):
            raise ConversionError(f"Kopierte Spurdaten verändert (Spur {old.id}).")
    return ["Alle Audio-/Video-Paketzeitstempel gelesen; AC3-Start und Ende geprüft",
            "Kopierte Spuren: SHA-256 der Pakete und alle PTS geprüft" if deep else
            "Gründlicher Vergleich kopierter Spuren deaktiviert"]


def attachment_check(source: Media, target: Media, runner: Runner, work: Path) -> list[str]:
    old = source.data.get("attachments", [])
    new = target.data.get("attachments", [])
    def digest(path: Path) -> bytes:
        result = hashlib.sha256()
        with path.open("rb") as file:
            while block := file.read(1024 * 1024):
                runner.check_cancel()
                result.update(block)
        return result.digest()
    for a, b in zip(old, new):
        hashes = []
        for media, attachment in ((source, a), (target, b)):
            temp = work / "attachment.bin"
            runner.run(["mkvextract", media.path, "attachments", f"{attachment['id']}:{temp}"])
            hashes.append(digest(temp))
            temp.unlink()
        if hashes[0] != hashes[1]:
            raise ConversionError(f"Anhangdaten verändert: {a.get('file_name', '')}")
    return [f"Anhänge: {len(old)} Inhalte mit SHA-256 geprüft"]


def publish_exclusive(temp: Path, target: Path):
    """Same-volume publication without replacing an existing name on either OS."""
    if os.name == 'nt':
        os.rename(temp, target)
    else:
        os.link(temp, target)


def publish(temp: Path, source: Path, destination: Path) -> Path:
    """No TOCTOU overwrite: link fails atomically if a candidate already exists."""
    for index in range(10000):
        suffix = "" if index == 0 else f"_{index + 1}"
        target = destination / f"{source.stem}_ac3{suffix}.mkv"
        try:
            publish_exclusive(temp, target)
            return target
        except FileExistsError:
            continue
        except OSError as e:
            raise ConversionError("Fertige Datei konnte nicht sicher veröffentlicht werden. "
                                  "Das Ziel unterstützt die sichere Veröffentlichung nicht "
                                  f"(Linux: Btrfs/ext4; Windows: lokales NTFS/exFAT). Details: {e}") from e
    raise ConversionError("Zu viele gleichnamige Ausgabedateien.")


def convert(media: Media, options: Options, runner: Runner,
            progress: Callable[[float, str], None] = lambda *_: None) -> Result:
    progress = Progress(progress)
    if signature(media.path) != media.signature:
        raise ConversionError("Quelldatei wurde seit dem Einlesen verändert. Bitte erneut prüfen.")
    if not media.dts_tracks:
        return Result(media.path, None, skipped=True)
    if any(t.channels < 1 for t in media.dts_tracks):
        raise ConversionError("Kanalzahl einer DTS-Spur unbekannt.")
    if not options.downmix and any(t.channels > 6 for t in media.dts_tracks):
        raise ConversionError("AC3 unterstützt höchstens 5.1. Downmix aktivieren.")
    destination = (options.output_dir or media.path.parent).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    start_warnings = len(runner.warnings)
    # Check early; actual space demand depends on the source's DTS bit rates.
    audio_estimate = media.duration * options.bitrate * 125 * len(media.dts_tracks)
    needed = int(media.signature[2] + 2 * audio_estimate + 256 * 1024**2)
    if shutil.disk_usage(destination).free < needed:
        raise ConversionError(f"Zu wenig freier Platz: geschätzt {needed / 1024**3:.2f} GiB benötigt.")
    with tempfile.TemporaryDirectory(prefix=".mkv-audio-converter-", dir=destination) as folder:
        work = Path(folder)
        replacements = {}
        isolated = work / "source-audio.mka"
        progress(0., "Alle DTS-Spuren gemeinsam vorbereiten")
        def prepare_progress(line):
            match = re.search(r"(?:#GUI#progress |Progress: )(\d+)%?", line)
            if match:
                progress(.15 * int(match[1]) / 100, "Alle DTS-Spuren gemeinsam vorbereiten")
        # Read the large original only once for all DTS tracks. Explicit order
        # makes 0:a:position below unambiguous without relying on source IDs.
        runner.run(["mkvmerge", "--gui-mode", "--disable-track-statistics-tags",
                    "--track-order", ",".join(f"0:{t.id}" for t in media.dts_tracks),
                    "-o", isolated, "--audio-tracks", ",".join(str(t.id) for t in media.dts_tracks),
                    "--no-video", "--no-subtitles", "--no-buttons", "--no-attachments", "--no-chapters",
                    "--no-global-tags", "--no-track-tags", media.path],
                   on_line=prepare_progress, reject_resync=True)
        for pos, track in enumerate(media.dts_tracks):
            runner.check_cancel()
            label = f"DTS-Spur {pos+1}/{len(media.dts_tracks)}"
            base, width = .15 + .50 * pos / len(media.dts_tracks), .50 / len(media.dts_tracks)
            encoded = work / f"ac3-{track.id}.mka"
            progress(base, label + " → AC3")
            old_name = track.properties.get("track_name", "")
            new_name = converted_track_name(track)
            if new_name != old_name:
                runner.log(f"Spurtitel (ID {track.id}): {old_name!r} → {new_name!r}")
            # Copy timestamps (no start_at_zero) and keep CodecDelay in MKA.
            # aresample fills timestamp gaps without continuous clock stretching.
            args: list[str | Path] = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "warning", "-n"]
            if not options.audio_recovery:
                args.append("-xerror")
            else:
                runner.log("Rettungsmodus: unlesbare Audiopakete dürfen ausgelassen werden; Verlustbericht beachten.")
            args += ["-copyts", "-err_detect", "ignore_err" if options.audio_recovery else "explode", "-i", isolated,
                                     "-map", f"0:a:{pos}", "-vn", "-sn", "-dn",
                                     "-map_metadata", "-1", "-map_chapters", "-1",
                                     "-af", "aresample=async=1", "-c:a", "ac3", "-b:a", f"{options.bitrate}k",
                                     "-ar", "48000"]
            if track.channels > 6:
                runner.log(f"Spur {track.id}: Downmix von {track.channels} Kanälen auf 5.1.")
                args += ["-ac", "6"]
            args += ["-avoid_negative_ts", "disabled", "-progress", "pipe:1", "-nostats", encoded]
            def ff_progress(line, base=base, width=width):
                if line.startswith("out_time_us="):
                    try:
                        part = float(line.split("=", 1)[1]) / 1e6 / max(media.duration, 1)
                        progress(base + width * min(1., max(0., part)), label + " → AC3")
                    except ValueError:
                        pass
            runner.run(args, on_line=ff_progress)
            if not encoded.is_file() or encoded.stat().st_size == 0:
                raise ConversionError("FFmpeg hat keine Audiodatei erzeugt.")
            replacements[track.id] = encoded
        isolated.unlink()
        output = work / "converted.mkv"
        def mux_progress(line):
            match = re.search(r"(?:#GUI#progress |Progress: )(\d+)%?", line)
            if match:
                progress(.65 + .15 * int(match[1]) / 100, "MKV neu verpacken")
        runner.run(remux_command(media, replacements, output), on_line=mux_progress, reject_resync=True)
        progress(.80, "Metadaten wiederherstellen und prüfen")
        chapters, tags = restore_metadata(media, output, work, runner,
                                          {t.uid for t in media.tracks} if options.audio_recovery else None)
        target = inspect(output, runner)
        checks = metadata_check(media, target, chapters, tags, runner)
        checks += packet_check(media, target, runner, work, options.deep_verify,
                               lambda p: progress(.82 + .17 * p, "Ergebnis prüfen"),
                               tolerate_source_errors=options.audio_recovery)
        if options.deep_verify:
            checks += attachment_check(media, target, runner, work)
        # Decode converted tracks completely. FFmpeg never decodes the video.
        audio_index = 0
        verified = 0
        for old in media.tracks:
            if old.type == "audio":
                if old.dts:
                    progress(.99, f"AC3-Spur {verified + 1}/{len(media.dts_tracks)} vollständig prüfen")
                    runner.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-xerror",
                                "-i", output, "-map", f"0:a:{audio_index}", "-vn", "-sn", "-dn",
                                "-f", "null", "-"], stderr_error=True)
                    verified += 1
                audio_index += 1
        checks.append("Alle erzeugten AC3-Spuren vollständig fehlerfrei decodiert")
        runner.check_cancel()
        if signature(media.path) != media.signature:
            raise ConversionError("Original wurde während der Verarbeitung verändert; Ausgabe verworfen.")
        with output.open("rb") as file:
            os.fsync(file.fileno())
        final = publish(output, media.path, destination)
        progress(1., "Fertig")
        return Result(media.path, final, warnings=runner.warnings[start_warnings:], checks=checks)
