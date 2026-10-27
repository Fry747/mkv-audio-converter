"""Capture the actual GUI after converting generated demo media (no personal files)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from mkv_audio_converter.core import Runner
from mkv_audio_converter.gui import Window


def capture():
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setFont(QFont('DejaVu Sans', 10))
    with tempfile.TemporaryDirectory(prefix='mkv-demo-') as folder:
        root = Path(folder)
        source = root/'Beispiel Deutsch + English.mkv'
        Runner().run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=size=128x72:rate=24:duration=1', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=1', '-f', 'lavfi', '-i',
            'sine=frequency=880:sample_rate=48000:duration=1', '-map', '0:v', '-map', '1:a', '-map', '2:a',
            '-c:v', 'ffv1', '-c:a', 'dca', '-strict', '-2', '-metadata:s:a:0', 'title=Deutsch DTS',
            '-metadata:s:a:0', 'language=deu', '-metadata:s:a:1', 'title=English DTS',
            '-metadata:s:a:1', 'language=eng', source])
        settings = QSettings(str(root/'settings.ini'), QSettings.Format.IniFormat)
        with patch('mkv_audio_converter.gui.QSettings', return_value=settings):
            window = Window()
        window.resize(1280, 830)
        window.output_dir.setText(str(root/'Ausgabe'))
        window.show()
        def wait():
            deadline = time.monotonic() + 60
            while window.worker is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            if window.worker is not None:
                window.cancel_job()
                window.worker.wait(5000)
                raise RuntimeError('Screenshot conversion timed out')
            app.processEvents()
        try:
            window.scan([source])
            wait()
            window.start()
            wait()
            if len(window.outputs) != 1:
                raise RuntimeError(window.logs.toPlainText())
            window.logs.verticalScrollBar().setValue(window.logs.verticalScrollBar().maximum())
            app.processEvents()
            if not window.grab().save(str(ROOT/'docs/Oberflaeche.png')):
                raise RuntimeError('Screenshot save failed')
        finally:
            window.close()


if __name__ == '__main__':
    capture()
