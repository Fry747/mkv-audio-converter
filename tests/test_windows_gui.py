"""Dependency wizard interaction without network requests or native Windows APIs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import time
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication, QDialog
    from mkv_audio_converter.windows_setup import SetupDialog
    from mkv_audio_converter.gui import Window, Worker
    HAVE_QT=True
except ImportError:
    HAVE_QT=False


@unittest.skipUnless(HAVE_QT, 'PySide6 fehlt')
class WindowsSetupGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def wait(self, dialog):
        deadline=time.monotonic()+5
        while dialog.worker is not None and time.monotonic()<deadline:
            self.app.processEvents()
            time.sleep(.01)
        if dialog.worker is not None:
            dialog.reject()
            dialog.worker.wait(2000)
            self.app.processEvents()
            self.fail('Setup worker did not finish')
        self.app.processEvents()

    def test_setup_error_allows_retry_and_success_accepts(self):
        dialog=SetupDialog()
        with patch('mkv_audio_converter.windows_setup.install', side_effect=ValueError('SHA-256 ungültig')):
            dialog.begin()
            self.wait(dialog)
        self.assertIn('SHA-256',dialog.status.text())
        self.assertTrue(dialog.download_button.isEnabled())
        with patch('mkv_audio_converter.windows_setup.install', return_value={'ffmpeg':'test'}):
            dialog.begin()
            self.wait(dialog)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.close()

    def test_close_cancels_setup_before_destroying_worker(self):
        started=threading.Event()
        def install(runner, progress):
            started.set()
            runner.cancel.wait(3)
            runner.check_cancel()
        dialog=SetupDialog()
        with patch('mkv_audio_converter.windows_setup.install', side_effect=install):
            dialog.begin()
            self.assertTrue(started.wait(1))
            dialog.reject()
            self.assertIsNotNone(dialog.worker)
            self.assertTrue(dialog.worker.cancel.is_set())
            self.wait(dialog)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        dialog.close()

    def test_missing_tools_cancel_prevents_conversion_worker_start(self):
        with patch('mkv_audio_converter.runtime.windows', return_value=True), \
             patch('mkv_audio_converter.gui.QSettings') as settings:
            settings.return_value.value.return_value = ''
            window=Window()
            worker=Worker(parent=window)
            with patch('mkv_audio_converter.windows_setup.needs_setup', return_value=True), \
                 patch.object(window,'configure_windows_tools',return_value=False), \
                 patch.object(worker,'start') as start:
                window.begin(worker)
            start.assert_not_called()
            self.assertIsNone(window.worker)
            self.assertIn('Werkzeuge fehlen',window.phase.text())
            window.close()
