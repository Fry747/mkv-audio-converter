"""Native PySide6 GUI. The conversion engine runs exclusively in a worker."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

from PySide6.QtCore import QSettings, QThread, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import runtime
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
    source_damaged = Signal(str, str)

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
                    damaged = isinstance(e, SourceDamageError)
                    if damaged:
                        self.source_damaged.emit(str(media.path), str(e))
                    self.log.emit(f"FEHLER: {media.path}: {e}")
                    report["files"].append({"source": str(media.path), "error": str(e),
                                            "source_damage": damaged})
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


class RepairSelectionDialog(QDialog):
    """Choose only known damaged entries from the current conversion queue."""
    def __init__(self, candidates, selected=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Beschädigte Dateien auswählen")
        self.resize(960, 440)
        layout = QVBoxLayout(self)
        intro = QLabel("Diese Dateien aus der aktuellen Liste wurden wegen erkannter Quellschäden "
                       "nicht konvertiert. Wählen Sie einzelne Dateien oder alle aus. "
                       "Zunächst wird nur analysiert; die Rettung bestätigen Sie anschließend separat.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(candidates), 3)
        self.table.setHorizontalHeaderLabels(["Datei", "Vollständiger Pfad", "Fehlergrund"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(False)
        checked = set(selected)
        for row, (path, reason) in enumerate(candidates):
            name = QTableWidgetItem(Path(path).name)
            name.setData(Qt.ItemDataRole.UserRole, path)
            name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            name.setCheckState(Qt.CheckState.Checked if path in checked else Qt.CheckState.Unchecked)
            for column, item in enumerate((name, QTableWidgetItem(path), QTableWidgetItem(reason.splitlines()[0] if reason else "Quellschaden erkannt"))):
                item.setToolTip(reason if column == 2 else path)
                self.table.setItem(row, column, item)
        layout.addWidget(self.table, 1)
        selection = QHBoxLayout()
        self.select_all = QPushButton("Alle auswählen")
        self.select_none = QPushButton("Auswahl aufheben")
        self.select_all.clicked.connect(lambda: self.set_checked(True))
        self.select_none.clicked.connect(lambda: self.set_checked(False))
        selection.addWidget(self.select_all)
        selection.addWidget(self.select_none)
        selection.addStretch()
        self.count = QLabel()
        selection.addWidget(self.count)
        layout.addLayout(selection)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self.analyze_button = buttons.addButton("Auswahl untersuchen", QDialogButtonBox.ButtonRole.AcceptRole)
        self.analyze_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.table.itemChanged.connect(self.update_selection)
        self.update_selection()

    def selected_paths(self):
        return [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def set_checked(self, checked):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def update_selection(self, *_):
        count = len(self.selected_paths())
        self.count.setText(f"{count} von {self.table.rowCount()} ausgewählt")
        self.analyze_button.setEnabled(count > 0)


class RepairWorker(Worker):
    plans_ready = Signal(object)

    def __init__(self, sources, options, plans=None, expected_signatures=None, parent=None):
        super().__init__(options=options, parent=parent)
        self.sources = tuple(sources)
        self.expected_signatures = dict(expected_signatures or {})
        self.plans = tuple(plans) if plans is not None else None
        if self.plans is not None and tuple(p.media.path for p in self.plans) != self.sources:
            raise ValueError("Rettungspläne stimmen nicht mit der ausgewählten Warteschlange überein.")

    def run(self):
        runner = Runner(self.cancel, self.log.emit)
        report = {"application": f"MKV Audio Converter {__version__}",
                  "kind": "recovery_analysis" if self.plans is None else "recovery",
                  "started_utc": datetime.now(timezone.utc).isoformat(),
                  "options": asdict(self.options), "files": []}
        analyzed = []
        index = 0
        try:
            report["tools"] = check_tools(runner)
            for index, source in enumerate(self.sources):
                runner.check_cancel()
                def progress(value, phase, index=index, source=source):
                    self.update_progress((index + value) / len(self.sources), f"{source.name} · {phase}")
                try:
                    if self.plans is None:
                        self.state.emit(str(source), "Rettungsmöglichkeiten untersuchen …")
                        media = inspect(source, runner)
                        expected = self.expected_signatures.get(str(source))
                        if expected is not None and media.signature != expected:
                            raise ConversionError("Quelldatei wurde seit der Schadenserkennung verändert. "
                                                  "Bitte die Dateiliste erneut prüfen.")
                        if not media.dts_tracks:
                            raise ConversionError("Keine DTS-Spur mehr vorhanden. Bitte die Dateiliste erneut prüfen.")
                        plan = analyze(media, runner, progress)
                        analyzed.append(plan)
                        report["files"].append({"source": str(source), "analysis": plan.summary()})
                        self.state.emit(str(source), "Analysiert · wartet auf Bestätigung")
                    else:
                        self.state.emit(str(source), "Rettung läuft …")
                        result = recover(self.plans[index], self.options, runner, accept_loss=True,
                                         progress=progress)
                        self.result.emit(result)
                        entry = asdict(result)
                        entry["analysis"] = self.plans[index].summary()
                        report["files"].append(entry)
                except Cancelled:
                    raise
                except (ConversionError, OSError, ValueError) as error:
                    self.state.emit(str(source), "Rettungsanalyse fehlgeschlagen" if self.plans is None
                                    else "Fehler bei der Rettung")
                    self.log.emit(f"FEHLER: {source}: {error}")
                    report["files"].append({"source": str(source), "error": str(error)})
                self.update_progress((index + 1) / len(self.sources), "Datei abgeschlossen")
            runner.check_cancel()
            if analyzed:
                self.plans_ready.emit(analyzed)
        except Cancelled as error:
            report["cancelled"] = True
            processed = {str(entry["source"]) for entry in report["files"]}
            for source in self.sources:
                if str(source) not in processed:
                    self.state.emit(str(source), "Abgebrochen · Rettung weiterhin verfügbar")
                    report["files"].append({"source": str(source), "error": "Abgebrochen"})
            # Analyzed plans are not submitted for confirmation after cancellation.
            for plan in analyzed:
                self.state.emit(str(plan.media.path), "Rettungsanalyse beendet · keine Ausgabe")
            self.log.emit(str(error))
        except Exception as error:
            report["fatal_error"] = str(error)
            self.log.emit(str(error))
            for source in self.sources[index:]:
                self.state.emit(str(source), "Rettungsauftrag fehlgeschlagen")
            self.fatal.emit(str(error))
        finally:
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            self.report_ready.emit(report)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"MKV Audio Converter {__version__}")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.png")))
        self.resize(1120, 780)
        self.settings = QSettings("MKVAudioConverter", "MKVAudioConverter")
        self.media: dict[str, Media] = {}
        self.rows: dict[str, int] = {}
        self.worker: Worker | None = None
        self.report = None
        self.pending_repairs = None
        self.recovery_options = None
        self.recovery_analysis_report = None
        self.damage_errors: dict[str, str] = {}
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
        heading_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(44, 44))
        heading_row.addWidget(logo)
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(QLabel(f"Version {__version__}"))
        layout.addLayout(heading_row)
        intro = QLabel("DTS → AC3 · Originale bleiben erhalten · Video wird unverändert übernommen")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        toolbar = QHBoxLayout()
        for label, slot in (("Dateien hinzufügen …", self.add_files), ("Ordner hinzufügen …", self.add_folder),
                            ("Erneut prüfen", self.rescan)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
            self.busy_controls.append(button)
        self.remove_button = QPushButton(QIcon.fromTheme("list-remove"), "Auswahl entfernen")
        self.remove_button.setToolTip("Markierte Einträge aus der Liste entfernen (Entf). Dateien bleiben erhalten.")
        self.remove_button.clicked.connect(self.remove_selected)
        toolbar.addWidget(self.remove_button)
        self.busy_controls.append(self.remove_button)
        self.recursive = QCheckBox("Unterordner einbeziehen")
        self.recursive.setChecked(True)
        toolbar.addWidget(self.recursive)
        self.busy_controls.append(self.recursive)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 4)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setHorizontalHeaderLabels(["Datei", "DTS-Spuren", "Status", "Ausgabe"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.open_output)
        self.remove_action = QAction(QIcon.fromTheme("list-remove"), "Aus Liste entfernen", self.table)
        self.remove_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self.remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.remove_action.setToolTip("Entfernt nur Listeneinträge. Originale und Ausgaben bleiben erhalten.")
        self.remove_action.triggered.connect(self.remove_selected)
        self.table.addAction(self.remove_action)
        # Keep one menu owned by the table. popup() uses the normal event loop,
        # so worker signals do not run inside a nested menu event loop.
        self.file_menu = QMenu(self.table)
        self.file_menu.addAction(self.remove_action)
        self.remove_locked_hint = self.file_menu.addAction("Entfernen während eines Auftrags gesperrt")
        self.remove_locked_hint.setEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_file_menu)
        self.table.itemSelectionChanged.connect(self.refresh_actions)
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
        self.repair_button = QPushButton("Beschädigte Dateien retten …")
        self.repair_button.setEnabled(False)
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
        if runtime.windows():
            tools_menu = self.menuBar().addMenu("Werkzeuge")
            setup_action = tools_menu.addAction("Windows-Werkzeuge einrichten …")
            setup_action.triggered.connect(self.configure_windows_tools)
            self.busy_controls.append(setup_action)
        help_menu = self.menuBar().addMenu("Hilfe")
        help_menu.addAction("Über MKV Audio Converter …", self.show_about)
        help_menu.addAction("Über Qt …", lambda: QMessageBox.aboutQt(self))
        self.refresh_actions()

    def show_about(self):
        QMessageBox.about(self, "Über MKV Audio Converter",
            f"<h3>MKV Audio Converter {__version__}</h3>"
            "<p>DTS → AC3 mit unverändertem Video. Anwendungscode: MIT.</p>"
            "<p>Verwendet Qt/PySide6 von The Qt Company Ltd. und Mitwirkenden "
            "unter LGPLv3. Das Notensymbol stammt aus KDE Breeze, "
            "© 2014 Uri Herrera und weitere Mitwirkende, LGPLv3 oder neuer.</p>"
            "<p>Lizenztexte und Hinweise: THIRD_PARTY.md und licenses/ im Programmpaket. "
            "Quellcode und Bauanleitung: "
            '<a href="https://github.com/Fry747/mkv-audio-converter">GitHub-Projekt</a>.</p>')

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
        previous = self.media.get(path)
        if previous is not None and previous.signature != media.signature:
            self.damage_errors.pop(path, None)
        self.media[path] = media
        row = self.row_for(path)
        self.table.item(row, 1).setText(str(len(media.dts_tracks)))
        details = [f"ID {t.id}: {t.codec} · {t.channels} Kanäle · "
                   f"{t.properties.get('language_ietf', t.properties.get('language', 'und'))} · "
                   f"{t.properties.get('track_name', '')}" for t in media.dts_tracks]
        self.table.item(row, 1).setToolTip("\n".join(details) or "Keine DTS-Spur")
        if path in self.damage_errors:
            self.mark_damaged(path, self.damage_errors[path])
        else:
            self.set_state(path, "Bereit" if media.dts_tracks else "Übersprungen · kein DTS")
        self.refresh_actions()

    def recovery_candidates(self):
        return [(path, self.damage_errors[path]) for path in self.rows
                if path in self.damage_errors and path in self.media
                and self.media[path].dts_tracks and path not in self.outputs]

    def refresh_actions(self):
        idle = self.worker is None
        selected = len(self.table.selectionModel().selectedRows())
        self.remove_button.setEnabled(idle and selected > 0)
        self.remove_action.setEnabled(idle and selected > 0)
        self.remove_locked_hint.setVisible(not idle)
        self.remove_action.setText(f"{selected} Einträge aus Liste entfernen" if selected > 1
                                   else "Aus Liste entfernen")
        count = len(self.recovery_candidates())
        self.repair_button.setText(f"Beschädigte Dateien retten ({count}) …" if count
                                   else "Beschädigte Dateien retten …")
        self.repair_button.setEnabled(idle and count > 0)
        self.repair_button.setToolTip("Einzelne oder alle erkannten beschädigten Dateien aus der Liste auswählen."
                                     if count else "Verfügbar, sobald die Konvertierung einen Quellschaden erkennt.")
        self.start_button.setEnabled(idle and any(m.dts_tracks and p not in self.outputs
                                     and p not in self.damage_errors for p, m in self.media.items()))

    def mark_damaged(self, path, reason):
        self.damage_errors[path] = reason
        self.set_state(path, "Fehler: beschädigte Quelldatei\n" + reason)
        self.refresh_actions()

    def scan(self, paths):
        if self.worker is not None:
            return
        self.begin(Worker(paths=paths, recursive=self.recursive.isChecked(), parent=self))

    def rescan(self):
        if self.worker is not None:
            return
        paths = [Path(p) for p in self.rows]
        self.media.clear()
        self.outputs.clear()
        self.damage_errors.clear()
        self.refresh_actions()
        for row in range(self.table.rowCount()):
            self.table.item(row, 3).setText("")
        if paths:
            self.scan(paths)

    def show_file_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        selected = {i.row() for i in self.table.selectionModel().selectedRows()}
        # A right-click on another row targets only that row. A right-click
        # inside a multi-selection keeps the intended group intact.
        if index.row() not in selected:
            self.table.clearSelection()
            self.table.selectRow(index.row())
        self.refresh_actions()
        self.file_menu.popup(self.table.viewport().mapToGlobal(position))

    def remove_selected(self):
        if self.worker is not None:
            return
        selected = {i.row() for i in self.table.selectionModel().selectedRows()}
        if not selected:
            return
        self.file_menu.close()
        kept = [p for p, row in self.rows.items() if row not in selected]
        for row in sorted(selected, reverse=True):
            self.table.removeRow(row)
        self.rows = {p: row for row, p in enumerate(kept)}
        self.media = {p: m for p, m in self.media.items() if p in self.rows}
        self.outputs = {p: output for p, output in self.outputs.items() if p in self.rows}
        self.damage_errors = {p: reason for p, reason in self.damage_errors.items() if p in self.rows}
        self.refresh_actions()

    def configure_windows_tools(self):
        if self.worker is not None:
            return False
        from .windows_setup import SetupDialog
        dialog = SetupDialog(self)
        try:
            return dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            dialog.deleteLater()

    def begin(self, worker):
        if runtime.windows():
            from .windows_setup import needs_setup
            if needs_setup() and not self.configure_windows_tools():
                worker.deleteLater()
                self.phase.setText("Werkzeuge fehlen. Einrichtung über das Menü Werkzeuge möglich.")
                return
        self.worker = worker
        self.file_menu.close()
        self.progress_bar.setValue(0)
        self.phase.setText("Werkzeuge prüfen …")
        for control in self.busy_controls:
            control.setEnabled(False)
        self.refresh_actions()
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        worker.log.connect(self.logs.appendPlainText)
        worker.found.connect(self.found)
        worker.state.connect(self.set_state)
        worker.source_damaged.connect(self.mark_damaged)
        worker.progress.connect(self.progress_changed)
        worker.result.connect(self.completed)
        worker.report_ready.connect(self.report_received)
        worker.fatal.connect(lambda text: QMessageBox.critical(self, "Verarbeitung fehlgeschlagen", text))
        if isinstance(worker, RepairWorker):
            worker.plans_ready.connect(self.repair_analyzed)
        worker.finished.connect(self.finished)
        worker.start()

    def start(self):
        if self.worker is not None:
            return
        items = [m for p, m in self.media.items() if m.dts_tracks and p not in self.outputs
                 and p not in self.damage_errors]
        if not items:
            return
        directory = self.output_dir.text().strip()
        self.settings.setValue("output_dir", directory)
        options = Options(Path(directory) if directory else None,
                          (384, 448, 640)[self.bitrate.currentIndex()],
                          self.downmix.isChecked(), self.deep.isChecked())
        self.report = None
        self.recovery_analysis_report = None
        self.save_report.setEnabled(False)
        self.begin(Worker(media=items, options=options, parent=self))

    def start_repair_analysis(self):
        if self.worker is not None:
            return
        candidates = self.recovery_candidates()
        if not candidates:
            return
        selected_rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        selected = [path for path, _ in candidates if self.rows[path] in selected_rows]
        dialog = RepairSelectionDialog(candidates, selected or [p for p, _ in candidates], self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            checked = set(dialog.selected_paths())
        finally:
            dialog.deleteLater()
        sources = [Path(path) for path, _ in candidates if path in checked]
        if not sources:
            return
        directory = self.output_dir.text().strip()
        self.settings.setValue("output_dir", directory)
        self.recovery_options = Options(Path(directory) if directory else None,
                                        (384, 448, 640)[self.bitrate.currentIndex()],
                                        self.downmix.isChecked(), True)
        self.pending_repairs = None
        self.recovery_analysis_report = None
        self.report = None
        self.save_report.setEnabled(False)
        self.begin(RepairWorker(sources, self.recovery_options,
                                expected_signatures={str(p): self.media[str(p)].signature for p in sources},
                                parent=self))

    def repair_analyzed(self, plans):
        self.pending_repairs = plans

    def confirm_repair(self, plans):
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle("Rettung mit möglichen Datenverlusten")
        summaries = [plan.summary() for plan in plans]
        failures = [entry for entry in (self.recovery_analysis_report or {}).get("files", [])
                    if "error" in entry]
        count = len(plans)
        regions = sum(len(plan.damage) for plan in plans)
        lost = sum(summary['excluded_bytes'] for summary in summaries)
        names = "\n".join(plan.media.path.name for plan in plans[:8])
        if count > 8:
            names += f"\n… und {count - 8} weitere Dateien (siehe Details)"
        message.setText(f"{count} Datei(en) zur Rettung:\n{names}\n\n"
                        f"{regions} Bereiche können nicht übernommen werden ({lost / 1024**2:.1f} MiB).")
        message.setInformativeText(
            (f"{len(failures)} weitere ausgewählte Datei(en) konnten nicht analysiert werden "
             "und werden nicht gerettet (siehe Details). " if failures else "") +
            "Nur vorhandene, lesbare Daten können übernommen werden. "
            "Bildaussetzer, Stille und fehlende Inhalte sind möglich. Die Zeitachse bleibt erhalten. "
            "Jede Ausgabe wird als gerettete Kopie mit eigenem Verlustbericht gekennzeichnet. "
            "Die ausgewählten Dateien werden nacheinander verarbeitet. "
            "Soll die Rettung mit anschließender AC3-Konvertierung für diese Dateien ausgeführt werden?")
        def clock(seconds):
            if seconds is None:
                return "unbekannt"
            value = max(0, int(seconds))
            return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"
        details = []
        for plan, summary in zip(plans, summaries):
            details += [str(plan.media.path),
                        f"{len(plan.damage)} Bereiche, {summary['excluded_bytes'] / 1024**2:.1f} MiB"]
            details += [f"• {clock(d.before_seconds)} bis {clock(d.after_seconds)}" for d in plan.damage[:20]]
            if len(plan.damage) > 20:
                details.append(f"… und {len(plan.damage) - 20} weitere Stellen im Verlustbericht")
            if not plan.damage:
                details.append("Keine strukturellen Schäden gefunden; Audiodecodierfehler bleiben möglich.")
            details.append("")
        if failures:
            details.append("Analyse fehlgeschlagen, von der Rettung ausgeschlossen:")
            details += [f"{entry['source']}: {entry['error']}" for entry in failures]
        message.setDetailedText("Schadstellen je Datei (ungefähre Zeitmarken):\n" + "\n".join(details))
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        message.button(QMessageBox.StandardButton.Yes).setText(f"{count} Datei(en) retten und AC3 konvertieren")
        message.button(QMessageBox.StandardButton.Cancel).setText("Abbrechen")
        message.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if message.exec() == QMessageBox.StandardButton.Yes:
            self.begin(RepairWorker([p.media.path for p in plans], self.recovery_options, plans=plans, parent=self))
        else:
            for plan in plans:
                self.set_state(str(plan.media.path), "Rettungsanalyse beendet · keine Ausgabe")

    def progress_changed(self, value, phase):
        # Queued tool updates may still arrive while cancellation is cleaning up.
        if self.worker is None or self.worker.cancel.is_set():
            return
        self.progress_bar.setValue(round(value * 1000))
        self.phase.setText(phase)

    def completed(self, result):
        path = str(result.source)
        if result.output:
            self.damage_errors.pop(path, None)
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
        self.refresh_actions()

    def report_received(self, report):
        if report.get("kind") == "recovery_analysis":
            self.recovery_analysis_report = report
        elif report.get("kind") == "recovery" and self.recovery_analysis_report is not None:
            report["analysis_report"] = self.recovery_analysis_report
        self.report = report
        self.save_report.setEnabled(True)

    def finished(self):
        worker = self.worker
        cancelled = worker.cancel.is_set()
        self.worker = None
        worker.deleteLater()
        if cancelled:
            self.progress_bar.setValue(0)
        for control in self.busy_controls:
            control.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.refresh_actions()
        count = len(self.recovery_candidates())
        prefix = "Abgebrochen." if cancelled else "Vorgang beendet."
        detail = (f"{count} beschädigte Datei(en) können über „Beschädigte Dateien retten“ "
                  "ausgewählt werden." if count else
                  "Status und Protokoll enthalten die Ergebnisse.")
        self.phase.setText(f"{prefix} {detail}")
        if self.pending_repairs is not None:
            plans, self.pending_repairs = self.pending_repairs, None
            if worker.cancel.is_set():
                for plan in plans:
                    self.set_state(str(plan.media.path), "Rettungsanalyse beendet · keine Ausgabe")
            else:
                self.confirm_repair(plans)

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


def launch(paths=(), *, smoke_test=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("MKV Audio Converter")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.png")))
    import sys
    if sys.platform == "win32":
        import ctypes
        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes, set_id.restype = [ctypes.c_wchar_p], ctypes.c_long
        set_id("Fry747.MKVAudioConverter")
    window = Window()
    window.show()
    if smoke_test:
        QTimer.singleShot(350, window.close)
    elif paths:
        QTimer.singleShot(0, lambda: window.scan([Path(p) for p in paths]))
    elif runtime.windows():
        from .windows_setup import needs_setup
        if needs_setup():
            QTimer.singleShot(0, window.configure_windows_tools)
    return app.exec()
