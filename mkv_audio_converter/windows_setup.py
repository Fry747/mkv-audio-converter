"""First-run Windows dependency setup; all I/O happens off the GUI thread."""
from pathlib import Path
import threading
import time

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout

from .core import Cancelled, Runner
from . import runtime
from .windows_tools import PACKAGES, install, use_existing


def needs_setup():
    try:
        return bool(runtime.missing_tools())
    except (OSError, ValueError, KeyError):
        return True


class SetupWorker(QThread):
    log = Signal(str)
    progress = Signal(float, str)

    def __init__(self, root=None, parent=None):
        super().__init__(parent)
        self.root = root
        self.cancel = threading.Event()
        self.error = None
        self.versions = None
        self.last_update = 0.
        self.last_phase = ''
        self.value = 0.

    def update_progress(self, value, phase):
        self.value = max(self.value, min(1., max(0., value)))
        now = time.monotonic()
        if now - self.last_update > .1 or phase != self.last_phase or self.value >= 1:
            self.progress.emit(self.value, phase)
            self.last_update, self.last_phase = now, phase

    def run(self):
        runner = Runner(self.cancel, self.log.emit)
        try:
            self.versions = (install(runner, self.update_progress) if self.root is None
                             else use_existing(self.root, runner))
        except Cancelled:
            self.error = 'Einrichtung abgebrochen. Die bisherige Konfiguration bleibt erhalten.'
        except Exception as error:
            self.error = str(error)
            self.log.emit(str(error))


class SetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Windows-Werkzeuge einrichten')
        self.resize(760, 500)
        self.worker = None
        self.closing = False
        layout = QVBoxLayout(self)
        info = QLabel(
            'Die Anwendung benötigt FFmpeg und MKVToolNix. Fehlende Werkzeuge können hier '
            'einmalig eingerichtet werden. Python und Qt sind in der fertigen EXE bereits enthalten.\n\n'
            + '\n'.join(f'• {p.name} {p.version} – {p.url.split("/")[2]}' for p in PACKAGES)
            + f'\n\nDownload: ca. {sum(p.size for p in PACKAGES)/1024**2:.0f} MiB; mindestens 3 GiB freier Platz. '
            'Die Originalpakete werden nach SHA-256-Prüfung im Benutzerprofil entpackt. '
            'Administratorrechte und Änderungen am System-PATH sind nicht nötig. '
            'Die Einrichtung aktiviert die Werkzeuge erst nach erfolgreicher Prüfung. '
            'Internet ist für den Download erforderlich; anschließend funktioniert die Konvertierung offline.')
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(info)
        self.status = QLabel('Herunterladen oder einen vorhandenen Werkzeugordner auswählen.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)
        actions = QHBoxLayout()
        self.download_button = QPushButton('Werkzeuge herunterladen und einrichten')
        self.download_button.clicked.connect(lambda: self.begin())
        self.download_button.setDefault(True)
        actions.addWidget(self.download_button)
        self.existing_button = QPushButton('Vorhandenen Ordner verwenden …')
        self.existing_button.clicked.connect(self.choose_existing)
        actions.addWidget(self.existing_button)
        self.cancel_button = QPushButton('Abbrechen')
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

    def choose_existing(self):
        root = QFileDialog.getExistingDirectory(self, 'Ordner mit entpacktem FFmpeg und MKVToolNix')
        if root:
            self.begin(Path(root))

    def begin(self, root=None):
        if self.worker is not None:
            return
        self.progress.setValue(0)
        self.status.setText('Werkzeuge werden vorbereitet …')
        self.download_button.setEnabled(False)
        self.existing_button.setEnabled(False)
        self.worker = SetupWorker(root, self)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.setup_finished)
        self.worker.start()

    def update_progress(self, value, phase):
        self.progress.setValue(round(value * 1000))
        self.status.setText(phase)

    def setup_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        if self.closing:
            super().reject()
        elif worker.error:
            self.status.setText('Einrichtung nicht abgeschlossen: ' + worker.error)
            self.download_button.setEnabled(True)
            self.existing_button.setEnabled(True)
        else:
            self.accept()

    def reject(self):
        if self.worker is not None:
            self.closing = True
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('Wird abgebrochen; bitte auf das Ende des laufenden Lesevorgangs warten …')
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
