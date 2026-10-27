"""Offscreen GUI tests; no display server needed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from mkv_audio_converter.gui import Window, Worker
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from mkv_audio_converter.core import Options, SourceDamageError, TOOLS


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

    def test_worker_progress_never_regresses_on_phase_changes(self):
        worker = Worker()
        values = []
        worker.progress.connect(lambda value, phase: values.append(value))
        for value, phase in ((.7, 'mux'), (.65, 'mux restarted progress'), (.8, 'metadata')):
            worker.update_progress(value, phase)
        self.assertEqual(values, [.7, .7, .8])

    def test_source_damage_has_clear_status_and_detailed_report(self):
        worker = Worker(media=[SimpleNamespace(path=Path('/source.mkv'))], options=Options())
        states, reports = [], []
        worker.state.connect(lambda path, state: states.append(state))
        worker.report_ready.connect(reports.append)
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.convert', side_effect=SourceDamageError('Resyncing at 1234')):
            worker.run()
        self.assertEqual(states[-1], 'Fehler: beschädigte Quelldatei')
        self.assertIn('Resyncing at 1234', reports[0]['files'][0]['error'])

    def test_recovery_confirmation_cancel_does_not_start_worker(self):
        window = Window()
        window.recovery_options = Options()
        plan = SimpleNamespace(media=SimpleNamespace(path=Path('/source.mkv')), clusters=[1], damage=[SimpleNamespace(before_seconds=0, after_seconds=2)],
                               summary=lambda: {'excluded_bytes': 1024, 'completeness': 'NOT_CONFIRMED'})
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Cancel), \
             patch.object(window, 'begin') as begin:
            window.confirm_repair(plan)
            begin.assert_not_called()
        self.assertIn('keine Ausgabe', window.table.item(0, 2).text())
        window.close()

    def test_recovery_confirmation_yes_starts_explicit_recovery(self):
        window = Window()
        window.recovery_options = Options()
        plan = SimpleNamespace(media=SimpleNamespace(path=Path('/source.mkv')), clusters=[1], damage=[SimpleNamespace(before_seconds=0, after_seconds=2)],
                               summary=lambda: {'excluded_bytes': 1024, 'completeness': 'NOT_CONFIRMED'})
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes), \
             patch.object(window, 'begin') as begin:
            window.confirm_repair(plan)
            self.assertIs(begin.call_args.args[0].plan, plan)
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
