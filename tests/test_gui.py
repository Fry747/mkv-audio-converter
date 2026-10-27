"""Offscreen GUI tests; no display server needed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from mkv_audio_converter.gui import Window
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from mkv_audio_converter.core import TOOLS


@unittest.skipUnless(HAVE_QT, 'PySide6 fehlt')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mkv-converter-gui-')
        cls.root = Path(cls.temp.name)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(cls.root / 'settings'))
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def wait_for_idle(self, window, seconds=30):
        deadline = time.monotonic() + seconds
        while window.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        if window.worker is not None:
            window.cancel_job()
            window.worker.wait(4000)
            self.app.processEvents()
            self.fail('GUI worker did not finish')
        self.app.processEvents()

    def test_window_controls_and_remove_row(self):
        window = Window()
        window.show()
        self.app.processEvents()
        self.assertFalse(window.start_button.isEnabled())
        self.assertFalse(window.cancel_button.isEnabled())
        window.set_state('/test/a.mkv', 'Fehler: Test')
        window.table.selectRow(0)
        window.remove_selected()
        self.assertEqual(window.table.rowCount(), 0)
        window.close()

    @unittest.skipUnless(all(shutil.which(t) for t in TOOLS), 'FFmpeg/MKVToolNix fehlen')
    def test_scan_convert_report_and_rescan(self):
        source = self.root / 'GUI test.mkv'
        proc = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                               'testsrc2=size=128x72:rate=24:duration=1',
                               '-f', 'lavfi', '-i', 'sine=sample_rate=48000:duration=1',
                               '-c:v', 'ffv1', '-c:a', 'dca', '-strict', '-2', '-y', str(source)], capture_output=True)
        if proc.returncode:
            self.skipTest('DTS-Testencoder dca fehlt')
        window = Window()
        window.output_dir.setText(str(self.root / 'output'))
        window.show()
        window.scan([source])
        self.wait_for_idle(window)
        self.assertEqual(window.table.rowCount(), 1)
        self.assertEqual(window.table.item(0, 1).text(), '1')
        self.assertTrue(window.start_button.isEnabled())
        window.start_button.click()
        self.assertTrue(window.cancel_button.isEnabled())
        self.wait_for_idle(window)
        self.assertEqual(window.table.item(0, 2).text(), 'Fertig · geprüft', window.logs.toPlainText())
        self.assertEqual(len(window.outputs), 1)
        self.assertTrue(window.save_report.isEnabled())
        self.assertTrue(window.report['files'][0]['checks'])
        self.assertFalse(window.start_button.isEnabled())
        screenshot = os.environ.get('MKV_TEST_SCREENSHOT')
        if screenshot:
            window.grab().save(screenshot)
        window.rescan()
        self.wait_for_idle(window)
        self.assertTrue(window.start_button.isEnabled())
        window.close()


if __name__ == '__main__':
    unittest.main()
