"""Native PySide6 GUI. The conversion engine runs exclusively in a worker."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

from PySide6.QtCore import QSettings, QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .repair import RepairPlan, analyze, recover
from . import __version__
from .core import Cancelled, ConversionError, Media, Options, Runner, SourceDamageError, check_tools, convert, discover, inspect


class Worker(QThread):
    found = Signal(object)
    state = Signal(str, str)
    progress = Signal(float, str)
    log = Signal(str)
    result = Signal(object)
    report_ready = Signal(object)
    fatal = Signal(str)

    def __init__(self, *, paths=(), media=(), options=None, recursive=True, parent=None):
        super().__init__(parent)
        self.paths, self.media = paths, media
        self.options = options
        self.recursive = recursive
        self.cancel = threading.Event()
        self._last_progress = 0.
        self._last_phase = ""
        self._progress_value = 0.

    def update_progress(self, value, phase):
        self._progress_value = max(self._progress_value, min(1., max(0., value)))
        value = self._progress_value
        now = time.monotonic()
        if now - self._last_progress > .1 or phase != self._last_phase or value >= 1:
            self.progress.emit(value, phase)
            self._last_progress, self._last_phase = now, phase

    def run(self):
        runner = Runner(self.cancel, self.log.emit)
        report = {"application": f"MKV Audio Converter {__version__}",
                  "started_utc": datetime.now(timezone.utc).isoformat(), "files": []}
        try:
            report["tools"] = check_tools(runner)
            if self.options is None:
                paths = discover(list(self.paths), self.recursive, runner.check_cancel)
                for i, path in enumerate(paths):
                    runner.check_cancel()
                    self.state.emit(str(path), "Wird geprüft …")
                    try:
                        media = inspect(path, runner)
                        self.found.emit(media)
                    except Cancelled:
                        raise
                    except (ConversionError, OSError) as e:
                        self.state.emit(str(path), f"Fehler: {e}")
                        self.log.emit(f"{path}: {e}")
                    self.update_progress((i + 1) / max(len(paths), 1), "Dateien prüfen")
                if not paths:
                    self.log.emit("Keine MKV-Dateien gefunden.")
                return
            report["options"] = asdict(self.options)
            for i, media in enumerate(self.media):
                runner.check_cancel()
                self.state.emit(str(media.path), "In Arbeit …")
                try:
                    result = convert(media, self.options, runner,
                                     lambda p, phase: self.update_progress(
                                         (i + p) / len(self.media), f"{media.path.name} · {phase}"))
                    self.result.emit(result)
                    report["files"].append(asdict(result))
                except Cancelled:
                    self.state.emit(str(media.path), "Abgebrochen")
                    report["files"].append({"source": str(media.path), "error": "Abgebrochen"})
                    raise
                except (ConversionError, OSError, ValueError) as e:
                    self.state.emit(str(media.path), "Fehler: beschädigte Quelldatei" if
                                    isinstance(e, SourceDamageError) else f"Fehler: {e}")
                    self.log.emit(f"FEHLER: {media.path}: {e}")
                    report["files"].append({"source": str(media.path), "error": str(e)})
                self.update_progress((i + 1) / len(self.media), "Datei abgeschlossen")
        except Cancelled as e:
            report["cancelled"] = True
            self.log.emit(str(e))
        except Exception as e:
            # Keep the UI usable even for an unexpected parser/tool failure.
            report["fatal_error"] = str(e)
            self.fatal.emit(str(e))
        finally:
            if self.options is not None:
                report["finished_utc"] = datetime.now(timezone.utc).isoformat()
                self.report_ready.emit(report)


class RepairWorker(Worker):
    plan_ready = Signal(object)

    def __init__(self, source, options, plan=None, parent=None):
        super().__init__(options=options, parent=parent)
        self.source, self.plan = source, plan

    def run(self):
        runner = Runner(self.cancel, self.log.emit)
        report = {"application": f"MKV Audio Converter {__version__}", "kind": "recovery", "files": []}
        try:
            report["tools"] = check_tools(runner)
            if self.plan is None:
                media = inspect(self.source, runner)
                self.found.emit(media)
                self.state.emit(str(media.path), "Rettungsmöglichkeiten untersuchen …")
                plan = analyze(media, runner, self.update_progress)
                report["analysis"] = plan.summary()
                self.plan_ready.emit(plan)
            else:
                self.state.emit(str(self.source), "Rettung läuft …")
                result = recover(self.plan, self.options, runner, accept_loss=True,
                                 progress=self.update_progress)
                self.result.emit(result)
                report["files"].append(asdict(result))
                report["analysis"] = self.plan.summary()
        except Cancelled as error:
            self.state.emit(str(self.source), "Abgebrochen")
            report["cancelled"] = True
            self.log.emit(str(error))
        except Exception as error:
            self.state.emit(str(self.source), "Fehler bei der Rettung")
            self.log.emit(str(error))
            report["error"] = str(error)
            self.fatal.emit(str(error))
        finally:
            self.report_ready.emit(report)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"MKV Audio Converter {__version__}")
        self.setWindowIcon(QIcon.fromTheme("audio-x-generic"))
        self.resize(1120, 780)
        self.settings = QSettings("MKVAudioConverter", "MKVAudioConverter")
        self.media: dict[str, Media] = {}
        self.rows: dict[str, int] = {}
        self.worker: Worker | None = None
        self.report = None
        self.pending_repair = None
        self.recovery_options = None
        self.outputs: dict[str, Path] = {}
        self.busy_controls = []
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(22, 20, 22, 20)
        heading = QLabel("MKV Audio Converter")
        font = heading.font()
        font.setPointSize(22)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        intro = QLabel("DTS → AC3 · Originale bleiben erhalten · Video wird unverändert übernommen")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        toolbar = QHBoxLayout()
        for label, slot in (("Dateien hinzufügen …", self.add_files), ("Ordner hinzufügen …", self.add_folder),
                            ("Erneut prüfen", self.rescan), ("Auswahl entfernen", self.remove_selected)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
            self.busy_controls.append(button)
        self.recursive = QCheckBox("Unterordner einbeziehen")
        self.recursive.setChecked(True)
        toolbar.addWidget(self.recursive)
        self.busy_controls.append(self.recursive)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Datei", "DTS-Spuren", "Status", "Ausgabe"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.open_output)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(4000)
        self.logs.setPlaceholderText("Status, Werkzeugmeldungen und Prüfergebnisse erscheinen hier.")
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.logs)
        splitter.setSizes([330, 150])
        layout.addWidget(splitter, 1)
        output_row = QHBoxLayout()
        self.output_dir = QLineEdit(str(self.settings.value("output_dir", "")))
        self.output_dir.setPlaceholderText("Leer lassen: Ausgabe neben der jeweiligen Originaldatei")
        output_row.addWidget(self.output_dir, 1)
        browse = QPushButton("Zielordner …")
        browse.clicked.connect(self.choose_output)
        output_row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Ausgabe", output_row)
        settings_row = QHBoxLayout()
        self.bitrate = QComboBox()
        self.bitrate.addItems(["384 kbit/s", "448 kbit/s", "640 kbit/s"])
        self.bitrate.setCurrentIndex(1)
        settings_row.addWidget(self.bitrate)
        self.downmix = QCheckBox("Mehr als 6 Kanäle auf 5.1 reduzieren")
        self.downmix.setChecked(True)
        self.downmix.setToolTip("AC3 unterstützt maximal 5.1. Ohne diese Option werden 7.1-Spuren als Fehler gemeldet.")
        settings_row.addWidget(self.downmix)
        self.deep = QCheckBox("Kopierte Spuren gründlich prüfen")
        self.deep.setChecked(True)
        self.deep.setToolTip("Vergleicht Paketdaten und Zeitstempel von Video, Untertiteln und unverändertem Audio. Benötigt zusätzliche Lesezeit.")
        settings_row.addWidget(self.deep)
        form.addRow("AC3", settings_row)
        layout.addLayout(form)
        self.busy_controls += [self.output_dir, browse, self.bitrate, self.downmix, self.deep]
        self.phase = QLabel("Dateien oder einen Ordner hinzufügen.")
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        layout.addWidget(self.progress_bar)
        actions = QHBoxLayout()
        self.save_log = QPushButton("Protokoll speichern …")
        self.save_log.clicked.connect(self.export_log)
        actions.addWidget(self.save_log)
        self.save_report = QPushButton("Prüfbericht speichern …")
        self.save_report.clicked.connect(self.export_report)
        self.save_report.setEnabled(False)
        actions.addWidget(self.save_report)
        self.repair_button = QPushButton("Beschädigte Datei retten …")
        self.repair_button.clicked.connect(self.start_repair_analysis)
        self.busy_controls.append(self.repair_button)
        actions.addWidget(self.repair_button)
        actions.addStretch()
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_job)
        actions.addWidget(self.cancel_button)
        self.start_button = QPushButton("Konvertieren")
        self.start_button.clicked.connect(self.start)
        self.start_button.setEnabled(False)
        self.start_button.setDefault(True)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)
        self.setAcceptDrops(True)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "MKV-Dateien auswählen", "", "Matroska (*.mkv *.MKV)")
        if paths:
            self.scan([Path(p) for p in paths])

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Ordner mit MKV-Dateien auswählen")
        if path:
            self.scan([Path(path)])

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Zielordner wählen", self.output_dir.text())
        if path:
            self.output_dir.setText(path)

    def row_for(self, path):
        if path not in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[path] = row
            for col, text in enumerate((Path(path).name, "…", "Wartet", "")):
                item = QTableWidgetItem(text)
                item.setToolTip(path if col == 0 else text)
                self.table.setItem(row, col, item)
        return self.rows[path]

    def set_state(self, path, status):
        row = self.row_for(path)
        self.table.item(row, 2).setText(status.splitlines()[0])
        self.table.item(row, 2).setToolTip(status)

    def found(self, media):
        path = str(media.path)
        self.media[path] = media
        row = self.row_for(path)
        self.table.item(row, 1).setText(str(len(media.dts_tracks)))
        details = [f"ID {t.id}: {t.codec} · {t.channels} Kanäle · "
                   f"{t.properties.get('language_ietf', t.properties.get('language', 'und'))} · "
                   f"{t.properties.get('track_name', '')}" for t in media.dts_tracks]
        self.table.item(row, 1).setToolTip("\n".join(details) or "Keine DTS-Spur")
        self.set_state(path, "Bereit" if media.dts_tracks else "Übersprungen · kein DTS")

    def scan(self, paths):
        if self.worker is not None:
            return
        self.begin(Worker(paths=paths, recursive=self.recursive.isChecked(), parent=self))

    def rescan(self):
        paths = [Path(p) for p in self.rows]
        self.media.clear()
        self.outputs.clear()
        for row in range(self.table.rowCount()):
            self.table.item(row, 3).setText("")
        if paths:
            self.scan(paths)

    def remove_selected(self):
        selected = {i.row() for i in self.table.selectionModel().selectedRows()}
        kept = [p for p, row in self.rows.items() if row not in selected]
        for row in sorted(selected, reverse=True):
            self.table.removeRow(row)
        self.rows = {p: row for row, p in enumerate(kept)}
        self.media = {p: m for p, m in self.media.items() if p in self.rows}
        self.start_button.setEnabled(any(m.dts_tracks and p not in self.outputs for p, m in self.media.items()))

    def begin(self, worker):
        self.worker = worker
        self.progress_bar.setValue(0)
        self.phase.setText("Werkzeuge prüfen …")
        for control in self.busy_controls:
            control.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        worker.log.connect(self.logs.appendPlainText)
        worker.found.connect(self.found)
        worker.state.connect(self.set_state)
        worker.progress.connect(self.progress_changed)
        worker.result.connect(self.completed)
        worker.report_ready.connect(self.report_received)
        worker.fatal.connect(lambda text: QMessageBox.critical(self, "Verarbeitung fehlgeschlagen", text))
        if isinstance(worker, RepairWorker):
            worker.plan_ready.connect(self.repair_analyzed)
        worker.finished.connect(self.finished)
        worker.start()

    def start(self):
        items = [m for p, m in self.media.items() if m.dts_tracks and p not in self.outputs]
        if not items:
            return
        directory = self.output_dir.text().strip()
        self.settings.setValue("output_dir", directory)
        options = Options(Path(directory) if directory else None,
                          (384, 448, 640)[self.bitrate.currentIndex()],
                          self.downmix.isChecked(), self.deep.isChecked())
        self.report = None
        self.save_report.setEnabled(False)
        self.begin(Worker(media=items, options=options, parent=self))

    def start_repair_analysis(self):
        selected = {i.row() for i in self.table.selectionModel().selectedRows()}
        source = next((Path(path) for path, row in self.rows.items() if row in selected), None) if len(selected) == 1 else None
        if source is None:
            path, _ = QFileDialog.getOpenFileName(self, "Beschädigte MKV untersuchen", "", "Matroska (*.mkv *.MKV)")
            if not path:
                return
            source = Path(path)
        directory = self.output_dir.text().strip()
        self.recovery_options = Options(Path(directory) if directory else None,
                                        (384, 448, 640)[self.bitrate.currentIndex()],
                                        self.downmix.isChecked(), True)
        self.pending_repair = None
        self.begin(RepairWorker(source, self.recovery_options, parent=self))

    def repair_analyzed(self, plan):
        self.pending_repair = plan

    def confirm_repair(self, plan):
        summary = plan.summary()
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle("Rettung mit möglichen Datenverlusten")
        message.setText(f"{plan.media.path.name}: {len(plan.damage)} Bereiche können nicht übernommen werden "
                        f"({summary['excluded_bytes'] / 1024**2:.1f} MiB).")
        message.setInformativeText("Nur vorhandene, lesbare Daten können übernommen werden. "
            "Bildaussetzer, Stille und fehlende Inhalte sind möglich. Die Zeitachse bleibt erhalten. "
            "Die Ausgabe wird ausdrücklich als gerettete Kopie mit Verlustbericht gekennzeichnet. "
            "Soll die Rettung mit anschließender AC3-Konvertierung ausgeführt werden?")
        def clock(seconds):
            if seconds is None:
                return "unbekannt"
            value = max(0, int(seconds))
            return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"
        positions = [f"• {clock(d.before_seconds)} bis {clock(d.after_seconds)}" for d in plan.damage[:20]]
        if len(plan.damage) > 20:
            positions.append(f"… und {len(plan.damage) - 20} weitere Stellen im Verlustbericht")
        message.setDetailedText("Umgebungen der Schadstellen zur Nachkontrolle (ungefähre Zeitmarken):\n" +
                                ("\n".join(positions) or "Keine strukturellen Schäden gefunden; Audiodecodierfehler bleiben möglich."))
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        message.button(QMessageBox.StandardButton.Yes).setText("Rettung und AC3-Konvertierung starten")
        message.button(QMessageBox.StandardButton.Cancel).setText("Abbrechen")
        message.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if message.exec() == QMessageBox.StandardButton.Yes:
            self.begin(RepairWorker(plan.media.path, self.recovery_options, plan=plan, parent=self))
        else:
            self.set_state(str(plan.media.path), "Rettungsanalyse beendet · keine Ausgabe")

    def progress_changed(self, value, phase):
        self.progress_bar.setValue(round(value * 1000))
        self.phase.setText(phase)

    def completed(self, result):
        path = str(result.source)
        if result.output:
            self.outputs[path] = result.output
            item = self.table.item(self.row_for(path), 3)
            item.setText(result.output.name)
            item.setToolTip(str(result.output))
        status = "Übersprungen · kein DTS" if result.skipped else (
            "Fertig · Warnungen beachten" if result.warnings else "Fertig · geprüft")
        if getattr(result, "recovered", False):
            status = "Gerettet · mögliche Bild-/Tonlücken"
            self.logs.appendPlainText(f"Verlustbericht: {result.report_path}")
        self.set_state(path, status)
        for check in result.checks:
            self.logs.appendPlainText("✓ " + check)

    def report_received(self, report):
        self.report = report
        self.save_report.setEnabled(True)

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        for control in self.busy_controls:
            control.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.start_button.setEnabled(any(m.dts_tracks and p not in self.outputs for p, m in self.media.items()))
        self.phase.setText("Vorgang beendet. Status und Protokoll enthalten die Ergebnisse.")
        if self.pending_repair is not None:
            plan, self.pending_repair = self.pending_repair, None
            self.confirm_repair(plan)

    def cancel_job(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.phase.setText("Wird abgebrochen; temporäre Dateien werden entfernt …")

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Protokoll speichern", "mkv-audio-converter.log", "Text (*.log)")
        if path:
            self.write_export(path, self.logs.toPlainText())

    def export_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Prüfbericht speichern", "mkv-audio-converter-report.json", "JSON (*.json)")
        if path and self.report:
            self.write_export(path, json.dumps(self.report, default=str, ensure_ascii=False, indent=2))

    def write_export(self, path, text):
        try:
            Path(path).write_text(text + "\n", encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(e))

    def open_output(self, row, column):
        path = next((p for p, r in self.rows.items() if r == row), None)
        if path in self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.outputs[path].parent)))

    def dragEnterEvent(self, event):
        if self.worker is None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.worker is None:
            self.scan([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.cancel_job()
            event.ignore()
            return
        super().closeEvent(event)


def launch(paths=()):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("MKV Audio Converter")
    app.setApplicationVersion(__version__)
    window = Window()
    window.show()
    if paths:
        window.scan([Path(p) for p in paths])
    return app.exec()
