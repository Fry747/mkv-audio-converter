from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import threading

from . import runtime
from .repair import analyze, recover
from . import __version__
from .core import Cancelled, Options, Runner, check_tools, convert, discover, inspect


def main(argv=None):
    parser = argparse.ArgumentParser(description="DTS → AC3 mit unverändertem Video und MKVToolNix.")
    parser.add_argument("paths", nargs="*", type=Path, help="MKV-Dateien oder Ordner")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--gui-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="Werkzeuge und Audio-Codecs prüfen")
    parser.add_argument("--setup-tools", action="store_true", help="Windows-x64-Werkzeuge aus festgelegten Herstellerdownloads einrichten")
    parser.add_argument("--tools-dir", type=Path, help="Expliziter Ordner mit Windows-Werkzeugen")
    parser.add_argument("--cli", action="store_true", help="Ohne GUI konvertieren")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bitrate", type=int, choices=(384, 448, 640), default=448)
    parser.add_argument("--no-downmix", action="store_true")
    parser.add_argument("--quick", action="store_true", help="Ohne Paketdatenvergleich kopierter Spuren")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--report", type=Path, help="JSON-Prüfbericht (darf noch nicht existieren)")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--analyze-repair", action="store_true", help="Eine MKV nur auf Rettungsmöglichkeiten untersuchen")
    recovery.add_argument("--recover", action="store_true", help="Gerettete Kopie mit AC3 erzeugen; mögliche Datenverluste")
    parser.add_argument("--accept-loss", action="store_true", help="Mögliche Bild-/Tonverluste im Rettungsmodus ausdrücklich akzeptieren")
    args = parser.parse_args(argv)
    if args.tools_dir:
        if not runtime.windows():
            parser.error("--tools-dir ist nur für Windows vorgesehen.")
        try:
            runtime.set_tools_directory(args.tools_dir)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    if args.setup_tools and (args.paths or args.cli or args.check or args.recover or args.analyze_repair):
        parser.error("--setup-tools wird als eigener Befehl ohne Dateien verwendet.")
    if args.recover and not args.accept_loss:
        parser.error("--recover benötigt --accept-loss; Bild-/Tonverluste sind möglich.")
    if args.accept_loss and not args.recover:
        parser.error("--accept-loss ist nur zusammen mit --recover zulässig.")
    if (args.recover or args.analyze_repair) and (len(args.paths) != 1 or not args.paths[0].is_file()):
        parser.error("Der Rettungsmodus benötigt genau eine MKV-Datei.")
    args.cli = args.cli or args.recover or args.analyze_repair or args.setup_tools
    if not args.check and not args.cli:
        try:
            from .gui import launch
        except ImportError:
            print("PySide6 fehlt. Bitte Installation gemäß README.md ausführen.", file=sys.stderr)
            return 2
        return launch(args.paths, smoke_test=args.gui_smoke_test)
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    signal.signal(signal.SIGTERM, lambda *_: cancel.set())
    runner = Runner(cancel, lambda line: print(line, file=sys.stderr, flush=True))
    report = {"application": f"MKV Audio Converter {__version__}",
              "started_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    failed = False
    salvaged = False
    try:
        if args.setup_tools:
            from .windows_tools import install
            report["tools"] = install(runner, lambda value, phase: print(f"{value:.0%} {phase}", file=sys.stderr))
            print(json.dumps(report["tools"], indent=2, ensure_ascii=False))
            return 0
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
                media = inspect(path, runner)
                if args.recover or args.analyze_repair:
                    plan = analyze(media, runner)
                    report["analysis"] = plan.summary()
                    if args.analyze_repair:
                        print(json.dumps(plan.summary(), default=str, ensure_ascii=False, indent=2))
                        continue
                    result = recover(plan, options, runner, accept_loss=args.accept_loss)
                    salvaged = True
                    print(f"GERETTET MIT MÖGLICHEN VERLUSTEN. Bericht: {result.report_path}")
                else:
                    result = convert(media, options, runner)
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
    return 1 if failed else (3 if salvaged else 0)


if __name__ == "__main__":
    raise SystemExit(main())
