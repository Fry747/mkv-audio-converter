from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import threading

from . import __version__
from .core import Cancelled, Options, Runner, check_tools, convert, discover, inspect


def main(argv=None):
    parser = argparse.ArgumentParser(description="DTS → AC3 mit unverändertem Video und MKVToolNix.")
    parser.add_argument("paths", nargs="*", type=Path, help="MKV-Dateien oder Ordner")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--check", action="store_true", help="Werkzeuge und Audio-Codecs prüfen")
    parser.add_argument("--cli", action="store_true", help="Ohne GUI konvertieren")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bitrate", type=int, choices=(384, 448, 640), default=448)
    parser.add_argument("--no-downmix", action="store_true")
    parser.add_argument("--quick", action="store_true", help="Ohne Paketdatenvergleich kopierter Spuren")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--report", type=Path, help="JSON-Prüfbericht (darf noch nicht existieren)")
    args = parser.parse_args(argv)
    if not args.check and not args.cli:
        try:
            from .gui import launch
        except ImportError:
            print("PySide6 fehlt. Bitte Installation gemäß README.md ausführen.", file=sys.stderr)
            return 2
        return launch(args.paths)
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    signal.signal(signal.SIGTERM, lambda *_: cancel.set())
    runner = Runner(cancel, lambda line: print(line, file=sys.stderr, flush=True))
    report = {"application": f"MKV Audio Converter {__version__}",
              "started_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    failed = False
    try:
        report["tools"] = check_tools(runner)
        if args.check:
            print(json.dumps(report["tools"], indent=2, ensure_ascii=False))
            return 0
        if not args.paths:
            parser.error("--cli benötigt mindestens eine Datei oder einen Ordner.")
        if args.report and args.report.exists():
            parser.error("Die Berichtsdatei existiert bereits.")
        paths = discover(args.paths, recursive=not args.no_recursive, check_cancel=runner.check_cancel)
        if not paths:
            raise ValueError("Keine MKV-Dateien gefunden.")
        options = Options(args.output_dir, args.bitrate, not args.no_downmix, not args.quick)
        report["options"] = asdict(options)
        for path in paths:
            runner.check_cancel()
            try:
                result = convert(inspect(path, runner), options, runner)
                report["files"].append(asdict(result))
                print(f"{path}: " + ("kein DTS; übersprungen" if result.skipped else str(result.output)))
            except Cancelled:
                raise
            except Exception as e:
                failed = True
                report["files"].append({"source": str(path), "error": str(e)})
                print(f"{path}: FEHLER: {e}", file=sys.stderr)
    except Cancelled:
        report["cancelled"] = True
        failed = True
    except Exception as e:
        report["fatal_error"] = str(e)
        print(str(e), file=sys.stderr)
        failed = True
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        if args.report:
            try:
                with args.report.open("x", encoding="utf-8") as file:
                    json.dump(report, file, default=str, ensure_ascii=False, indent=2)
                    file.write("\n")
            except OSError as e:
                failed = True
                print(f"Prüfbericht konnte nicht gespeichert werden: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
