"""Offscreen GUI tests; no display server needed."""
import os
import hashlib
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
    from PySide6.QtCore import QItemSelectionModel, QPoint, QSettings, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox
    from PySide6.QtTest import QTest
    from mkv_audio_converter.gui import RepairSelectionDialog, RepairWorker, Window, Worker
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from mkv_audio_converter.core import (ConversionError, Media, Options, Result,
                                      SourceDamageError, Track, TOOLS, Runner, inspect)
from mkv_audio_converter.repair import RecoveryResult, analyze


def media_for(path, dts=True, signature=(1, 2, 3, 4)):
    return Media(Path(path), {}, (Track(0, 'audio', 'DTS' if dts else 'AC3',
                 {'uid': 1, 'codec_id': 'A_DTS' if dts else 'A_AC3', 'audio_channels': 2}),), signature)


def plan_for(media):
    return SimpleNamespace(media=media, clusters=[1],
                           damage=[SimpleNamespace(before_seconds=0, after_seconds=2)],
                           summary=lambda: {'excluded_bytes': 1024, 'completeness': 'NOT_CONFIRMED'})


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

    def use_file_menu(self, window, row, inspect_menu):
        window.table.customContextMenuRequested.emit(
            window.table.visualItemRect(window.table.item(row, 0)).center())
        self.app.processEvents()
        try:
            self.assertTrue(window.file_menu.isVisible())
            inspect_menu(window.file_menu)
        finally:
            window.file_menu.close()

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
        states, reports, damaged = [], [], []
        worker.state.connect(lambda path, state: states.append(state))
        worker.report_ready.connect(reports.append)
        worker.source_damaged.connect(lambda path, reason: damaged.append((path, reason)))
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.convert', side_effect=SourceDamageError('Resyncing at 1234')):
            worker.run()
        self.assertEqual(states[-1], 'Fehler: beschädigte Quelldatei')
        self.assertIn('Resyncing at 1234', reports[0]['files'][0]['error'])
        self.assertTrue(reports[0]['files'][0]['source_damage'])
        self.assertEqual(damaged, [('/source.mkv', 'Resyncing at 1234')])

    def test_recovery_confirmation_cancel_does_not_start_worker(self):
        window = Window()
        window.recovery_options = Options()
        plan = SimpleNamespace(media=SimpleNamespace(path=Path('/source.mkv')), clusters=[1], damage=[SimpleNamespace(before_seconds=0, after_seconds=2)],
                               summary=lambda: {'excluded_bytes': 1024, 'completeness': 'NOT_CONFIRMED'})
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Cancel), \
             patch.object(window, 'begin') as begin:
            window.confirm_repair([plan])
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
            window.confirm_repair([plan])
            self.assertEqual(begin.call_args.args[0].plans, (plan,))
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


    def test_generic_conversion_error_does_not_mark_source_damaged(self):
        worker = Worker(media=[media_for('/source.mkv')], options=Options())
        reports, damaged = [], []
        worker.report_ready.connect(reports.append)
        worker.source_damaged.connect(lambda *args: damaged.append(args))
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.convert', side_effect=ConversionError('Zu wenig freier Platz')):
            worker.run()
        self.assertFalse(damaged)
        self.assertFalse(reports[0]['files'][0]['source_damage'])

    def test_repair_selection_checks_individual_or_all_with_full_paths(self):
        paths = ['/folder-a/Film.mkv', '/folder-b/Film.mkv']
        dialog = RepairSelectionDialog([(p, 'Resyncing at 1234') for p in paths], [paths[1]])
        self.assertEqual(dialog.selected_paths(), [paths[1]])
        self.assertEqual(dialog.table.item(0, 1).text(), paths[0])
        self.assertEqual(dialog.table.item(1, 1).text(), paths[1])
        self.assertTrue(dialog.analyze_button.isEnabled())
        dialog.select_none.click()
        self.assertEqual(dialog.selected_paths(), [])
        self.assertFalse(dialog.analyze_button.isEnabled())
        dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.selected_paths(), [paths[0]])
        dialog.select_all.click()
        self.assertEqual(dialog.selected_paths(), paths)
        self.assertEqual(dialog.count.text(), '2 von 2 ausgewählt')
        dialog.close()

    def test_repair_candidates_use_structured_damage_not_status_text(self):
        window = Window()
        self.assertFalse(window.repair_button.isEnabled())
        for path in ('/damaged.mkv', '/healthy.mkv', '/space-error.mkv', '/done.mkv'):
            window.found(media_for(path))
        window.found(media_for('/no-dts.mkv', dts=False))
        for path in ('/damaged.mkv', '/done.mkv', '/no-dts.mkv'):
            window.mark_damaged(path, 'Resyncing')
        window.outputs['/done.mkv'] = Path('/done_ac3.mkv')
        window.set_state('/space-error.mkv', 'Fehler: beschädigte Quelldatei')
        window.mark_damaged('/not-inspected.mkv', 'Resyncing')
        window.refresh_actions()
        self.assertEqual(window.recovery_candidates(), [('/damaged.mkv', 'Resyncing')])
        self.assertTrue(window.repair_button.isEnabled())
        self.assertIn('(1)', window.repair_button.text())
        with patch.object(window, 'begin') as begin:
            window.start()
        self.assertEqual([m.path for m in begin.call_args.args[0].media],
                         [Path('/healthy.mkv'), Path('/space-error.mkv')])
        window.close()

    def test_repair_selection_never_opens_file_dialog_and_honors_table_selection(self):
        window = Window()
        for path in ('/a.mkv', '/b.mkv', '/healthy.mkv'):
            window.found(media_for(path))
        for path in ('/a.mkv', '/b.mkv'):
            window.mark_damaged(path, 'Resyncing')
        window.table.selectRow(window.rows['/b.mkv'])
        def choose(dialog):
            self.assertEqual(dialog.selected_paths(), ['/b.mkv'])
            self.assertEqual(dialog.table.rowCount(), 2)
            return QDialog.DialogCode.Accepted
        with patch('mkv_audio_converter.gui.QFileDialog.getOpenFileName', side_effect=AssertionError('File dialog')), \
             patch.object(RepairSelectionDialog, 'exec', new=choose), \
             patch.object(window, 'begin') as begin:
            window.start_repair_analysis()
        worker = begin.call_args.args[0]
        self.assertEqual(worker.sources, (Path('/b.mkv'),))
        self.assertEqual(worker.expected_signatures, {'/b.mkv': (1, 2, 3, 4)})
        window.close()

    def test_repair_selection_cancel_and_no_candidates_start_nothing(self):
        window = Window()
        with patch('mkv_audio_converter.gui.QFileDialog.getOpenFileName', side_effect=AssertionError('File dialog')), \
             patch.object(window, 'begin') as begin, \
             patch.object(RepairSelectionDialog, 'exec', return_value=QDialog.DialogCode.Rejected) as choose:
            window.start_repair_analysis()
            choose.assert_not_called()
            window.found(media_for('/damaged.mkv'))
            window.mark_damaged('/damaged.mkv', 'Resyncing')
            window.start_repair_analysis()
            begin.assert_not_called()
        self.assertEqual(len(window.recovery_candidates()), 1)
        window.close()

    def test_repair_eligibility_cleared_on_removal_rescan_or_success(self):
        window = Window()
        for path in ('/a.mkv', '/b.mkv', '/c.mkv'):
            window.found(media_for(path))
            window.mark_damaged(path, 'Resyncing')
        window.table.selectRow(window.rows['/a.mkv'])
        window.remove_selected()
        self.assertNotIn('/a.mkv', window.damage_errors)
        window.completed(RecoveryResult(Path('/b.mkv'), Path('/b_recovered_ac3.mkv'),
                                        report_path=Path('/b.recovery.json')))
        self.assertEqual([p for p, _ in window.recovery_candidates()], ['/c.mkv'])
        with patch.object(window, 'scan'):
            window.rescan()
        self.assertFalse(window.damage_errors)
        self.assertFalse(window.repair_button.isEnabled())
        self.assertFalse(window.outputs)
        window.close()

    def test_analysis_continues_after_file_error_and_emits_only_successful_plans(self):
        media = [media_for('/bad.mkv'), media_for('/a.mkv'), media_for('/b.mkv')]
        plans = [plan_for(m) for m in media[1:]]
        worker = RepairWorker([m.path for m in media], Options())
        ready, reports, progress, fatal = [], [], [], []
        worker.plans_ready.connect(ready.append)
        worker.report_ready.connect(reports.append)
        worker.progress.connect(lambda value, phase: progress.append(value))
        worker.fatal.connect(fatal.append)
        def analyze_media(m, runner, callback):
            if m.path.name == 'bad.mkv':
                raise ConversionError('Kopf beschädigt')
            callback(.9, 'Analyse')
            callback(.5, 'Analyse')
            return plans[0] if m.path.name == 'a.mkv' else plans[1]
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.inspect', side_effect=media), \
             patch('mkv_audio_converter.gui.analyze', side_effect=analyze_media):
            worker.run()
        self.assertEqual(ready, [plans])
        self.assertEqual(len(reports[0]['files']), 3)
        self.assertEqual(reports[0]['files'][0]['error'], 'Kopf beschädigt')
        self.assertEqual(progress, sorted(progress))
        self.assertFalse(fatal)

    def test_analysis_rejects_replaced_source_or_missing_dts(self):
        for m, reason in ((media_for('/changed.mkv', signature=(9, 9, 9, 9)), 'verändert'),
                          (media_for('/changed.mkv', dts=False), 'Keine DTS')):
            with self.subTest(reason=reason):
                worker = RepairWorker([m.path], Options(), expected_signatures={str(m.path): (1, 2, 3, 4)})
                reports, ready = [], []
                worker.report_ready.connect(reports.append)
                worker.plans_ready.connect(ready.append)
                with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
                     patch('mkv_audio_converter.gui.inspect', return_value=m), \
                     patch('mkv_audio_converter.gui.analyze') as analyze:
                    worker.run()
                analyze.assert_not_called()
                self.assertFalse(ready)
                self.assertIn(reason, reports[0]['files'][0]['error'])

    def test_recovery_batch_continues_after_failure_and_checks_plan_sources(self):
        plans = [plan_for(media_for(p)) for p in ('/a.mkv', '/b.mkv')]
        with self.assertRaises(ValueError):
            RepairWorker([Path('/b.mkv'), Path('/a.mkv')], Options(), plans=plans)
        worker = RepairWorker([p.media.path for p in plans], Options(), plans=plans)
        reports, results, fatal = [], [], []
        worker.report_ready.connect(reports.append)
        worker.result.connect(results.append)
        worker.fatal.connect(fatal.append)
        result = RecoveryResult(Path('/b.mkv'), Path('/b_recovered_ac3.mkv'))
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.recover', side_effect=[ConversionError('Ausgabe voll'), result]) as recover:
            worker.run()
        self.assertEqual(len(recover.call_args_list), 2)
        self.assertTrue(all(call.kwargs['accept_loss'] for call in recover.call_args_list))
        self.assertEqual(results, [result])
        self.assertEqual(reports[0]['files'][0]['error'], 'Ausgabe voll')
        self.assertEqual(reports[0]['files'][1]['output'], result.output)
        self.assertFalse(fatal)

    def test_batch_cancellation_keeps_completed_recoveries_and_stops_remaining(self):
        plans = [plan_for(media_for(p)) for p in ('/a.mkv', '/b.mkv', '/c.mkv')]
        worker = RepairWorker([p.media.path for p in plans], Options(), plans=plans)
        reports, results = [], []
        worker.report_ready.connect(reports.append)
        worker.result.connect(results.append)
        def recover(plan, *args, **kwargs):
            worker.cancel.set()
            return RecoveryResult(plan.media.path, Path('/a_recovered_ac3.mkv'))
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.recover', side_effect=recover) as run:
            worker.run()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(results), 1)
        self.assertTrue(reports[0]['cancelled'])
        self.assertEqual([f.get('error') for f in reports[0]['files']], [None, 'Abgebrochen', 'Abgebrochen'])

    def test_analysis_cancellation_never_opens_confirmation(self):
        media = [media_for('/a.mkv'), media_for('/b.mkv')]
        worker = RepairWorker([m.path for m in media], Options())
        ready, reports, states = [], [], []
        worker.plans_ready.connect(ready.append)
        worker.report_ready.connect(reports.append)
        worker.state.connect(lambda path, status: states.append(status))
        def analyze(m, *args):
            worker.cancel.set()
            return plan_for(m)
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.inspect', return_value=media[0]), \
             patch('mkv_audio_converter.gui.analyze', side_effect=analyze):
            worker.run()
        self.assertFalse(ready)
        self.assertTrue(reports[0]['cancelled'])
        self.assertEqual(states[-1], 'Rettungsanalyse beendet · keine Ausgabe')
        window = Window()
        window.worker = worker
        window.pending_repairs = [plan_for(media[0])]
        with patch.object(window, 'confirm_repair') as confirm:
            window.finished()
        confirm.assert_not_called()
        window.close()

    def test_threaded_queue_damage_selection_analysis_and_recovery(self):
        window = Window()
        paths = ['/folder-a/Film.mkv', '/folder-b/Film.mkv', '/healthy.mkv']
        media = {p: media_for(p) for p in paths}
        for m in media.values():
            window.found(m)
        def convert(m, *args):
            if str(m.path) != '/healthy.mkv':
                raise SourceDamageError('Resyncing at 1234')
            return Result(m.path, Path('/healthy_ac3.mkv'))
        def recover(plan, *args, **kwargs):
            if str(plan.media.path) == paths[0]:
                raise ConversionError('Nicht rettbar')
            return RecoveryResult(plan.media.path, Path('/Film_recovered_ac3.mkv'),
                                  report_path=Path('/Film_recovered_ac3.recovery.json'))
        with patch('mkv_audio_converter.gui.check_tools', return_value={}), \
             patch('mkv_audio_converter.gui.convert', side_effect=convert), \
             patch('mkv_audio_converter.gui.inspect', side_effect=lambda p, runner: media[str(p)]), \
             patch('mkv_audio_converter.gui.analyze', side_effect=lambda m, *args: plan_for(m)), \
             patch('mkv_audio_converter.gui.recover', side_effect=recover), \
             patch.object(RepairSelectionDialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
             patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes):
            window.start()
            self.wait_for_idle(window)
            self.assertEqual([p for p, _ in window.recovery_candidates()], paths[:2])
            self.assertFalse(window.start_button.isEnabled())
            self.assertTrue(window.repair_button.isEnabled())
            window.start_repair_analysis()
            self.wait_for_idle(window)
        self.assertEqual(window.table.item(window.rows[paths[0]], 2).text(), 'Fehler bei der Rettung')
        self.assertIn('Gerettet', window.table.item(window.rows[paths[1]], 2).text())
        self.assertEqual([p for p, _ in window.recovery_candidates()], [paths[0]])
        self.assertEqual(len(window.outputs), 2)
        self.assertEqual(len(window.report['files']), 2)
        self.assertEqual(len(window.report['analysis_report']['files']), 2)
        self.assertTrue(window.save_report.isEnabled())
        window.close()



    def test_batch_confirmation_defaults_to_cancel_and_lists_analysis_failures(self):
        window = Window()
        plans = [plan_for(media_for(p)) for p in ('/folder-a/Film.mkv', '/folder-b/Film.mkv')]
        for plan in plans:
            window.found(plan.media)
            window.mark_damaged(str(plan.media.path), 'Resyncing')
        window.recovery_options = Options()
        window.recovery_analysis_report = {'files': [{'source': '/failed.mkv', 'error': 'Kopf fehlt'}]}
        def cancel(message):
            self.assertEqual(message.defaultButton().text(), 'Abbrechen')
            self.assertIn('2 Datei(en)', message.text())
            self.assertIn('1 weitere', message.informativeText())
            for path in ('/folder-a/Film.mkv', '/folder-b/Film.mkv', '/failed.mkv'):
                self.assertIn(path, message.detailedText())
            return QMessageBox.StandardButton.Cancel
        with patch.object(QMessageBox, 'exec', new=cancel), patch.object(window, 'begin') as begin:
            window.confirm_repair(plans)
        begin.assert_not_called()
        self.assertEqual(len(window.recovery_candidates()), 2)
        window.close()

    @unittest.skipUnless(all(shutil.which(t) for t in TOOLS), 'FFmpeg/MKVToolNix fehlen')
    def test_real_two_damaged_files_recovered_from_queue(self):
        root = self.root / 'real-recovery-batch'
        root.mkdir(exist_ok=True)
        first, second = root / 'first.mkv', root / 'second.mkv'
        proc = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                               'testsrc2=size=128x72:rate=24:duration=3', '-f', 'lavfi', '-i',
                               'sine=sample_rate=48000:duration=3', '-c:v', 'ffv1', '-c:a', 'dca',
                               '-strict', '-2', '-cluster_time_limit', '500', '-y', str(first)], capture_output=True)
        if proc.returncode:
            self.skipTest('DTS-Testencoder dca fehlt')
        runner = Runner()
        plan = analyze(inspect(first, runner), runner)
        with first.open('r+b') as file:
            file.seek(plan.clusters[len(plan.clusters)//2].offset)
            file.write(b'\0\0\0\0')
        shutil.copyfile(first, second)
        hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)]
        window = Window()
        window.output_dir.setText(str(root / 'out'))
        with patch.object(QMessageBox, 'critical') as fatal:
            window.scan([first, second])
            self.wait_for_idle(window)
            window.start()
            self.wait_for_idle(window)
            self.assertEqual(len(window.recovery_candidates()), 2, window.logs.toPlainText())
            self.assertTrue(window.repair_button.isEnabled())
            with patch.object(RepairSelectionDialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
                 patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes):
                window.start_repair_analysis()
                self.wait_for_idle(window)
            fatal.assert_not_called()
        self.assertEqual(len(window.outputs), 2, window.logs.toPlainText())
        self.assertFalse(window.recovery_candidates())
        self.assertFalse(window.repair_button.isEnabled())
        self.assertEqual(len(window.report['files']), 2)
        self.assertEqual(len(window.report['analysis_report']['files']), 2)
        for source, output in window.outputs.items():
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_suffix('.recovery.json').is_file())
            self.assertIn('Gerettet', window.table.item(window.rows[source], 2).text())
            self.assertFalse(inspect(output, runner).dts_tracks)
        self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)], hashes)
        window.close()


    def test_context_menu_on_unselected_row_removes_only_clicked_entry(self):
        window = Window()
        for path in ('/one/Film.mkv', '/two/Film.mkv'):
            window.found(media_for(path))
        window.show()
        self.app.processEvents()
        window.table.selectRow(0)
        def remove(menu, *_):
            action = menu.actions()[0]
            self.assertTrue(action.isEnabled())
            self.assertEqual(action.text(), 'Aus Liste entfernen')
            action.trigger()
        self.use_file_menu(window, 1, remove)
        self.assertEqual(window.rows, {'/one/Film.mkv': 0})
        self.assertEqual(list(window.media), ['/one/Film.mkv'])
        window.close()

    def test_context_multi_remove_cleans_state_without_deleting_files_or_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root / name / 'Film.mkv' for name in ('one', 'keep', 'two')]
            for path in paths:
                path.parent.mkdir()
                path.write_bytes(b'original source')
            output = root / 'finished_ac3.mkv'
            output.write_bytes(b'finished output')
            window = Window()
            for path in paths:
                window.found(media_for(path))
            window.completed(Result(paths[0], output))
            window.mark_damaged(str(paths[2]), 'Resyncing')
            window.report = {'files': [{'source': str(paths[0]), 'output': str(output)}]}
            report = window.report
            window.show()
            self.app.processEvents()
            selection = window.table.selectionModel()
            flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
            for row in (0, 2):
                selection.select(window.table.model().index(row, 0), flags)
            def remove(menu, *_):
                self.assertEqual(menu.actions()[0].text(), '2 Einträge aus Liste entfernen')
                menu.actions()[0].trigger()
            self.use_file_menu(window, 2, remove)
            self.assertEqual(window.rows, {str(paths[1]): 0})
            self.assertEqual(list(window.media), [str(paths[1])])
            self.assertFalse(window.damage_errors)
            self.assertFalse(window.outputs)
            self.assertIs(window.report, report)
            self.assertEqual(report['files'][0]['output'], str(output))
            for path in paths:
                self.assertEqual(path.read_bytes(), b'original source')
            self.assertEqual(output.read_bytes(), b'finished output')
            # Re-adding a finished source must not inherit its old output entry.
            window.found(media_for(paths[0]))
            self.assertEqual(window.rows[str(paths[0])], 1)
            self.assertEqual(window.table.item(1, 2).text(), 'Bereit')
            self.assertTrue(window.start_button.isEnabled())
            window.close()

    def test_remove_is_locked_during_scan_conversion_analysis_and_recovery(self):
        factories = [lambda w: Worker(paths=[Path('/a.mkv')], parent=w),
                     lambda w: Worker(media=[media_for('/a.mkv')], options=Options(), parent=w),
                     lambda w: RepairWorker([Path('/a.mkv')], Options(), parent=w),
                     lambda w: RepairWorker([Path('/a.mkv')], Options(),
                                             plans=[plan_for(media_for('/a.mkv'))], parent=w)]
        for factory in factories:
            with self.subTest(factory=factory):
                window = Window()
                window.found(media_for('/a.mkv'))
                window.table.selectRow(0)
                self.assertTrue(window.remove_button.isEnabled())
                self.assertTrue(window.remove_action.isEnabled())
                worker = factory(window)
                with patch.object(worker, 'start'):
                    window.begin(worker)
                self.assertFalse(window.remove_button.isEnabled())
                self.assertFalse(window.remove_action.isEnabled())
                window.remove_selected()
                window.show()
                self.app.processEvents()
                def inspect_menu(menu, *_):
                    self.assertFalse(menu.actions()[0].isEnabled())
                    self.assertIn('gesperrt', menu.actions()[1].text())
                self.use_file_menu(window, 0, inspect_menu)
                self.assertEqual(window.rows, {'/a.mkv': 0})
                # Guard remains effective even if an outdated menu action was enabled.
                window.remove_action.setEnabled(True)
                window.remove_action.trigger()
                self.assertEqual(window.table.rowCount(), 1)
                window.finished()
                self.assertTrue(window.remove_button.isEnabled())
                window.close()

    def test_delete_shortcut_is_scoped_to_table_and_button_tracks_selection(self):
        window = Window()
        window.show()
        window.activateWindow()
        self.app.processEvents()
        self.assertFalse(window.remove_button.isEnabled())
        self.assertFalse(window.remove_action.isEnabled())
        window.found(media_for('/a.mkv'))
        window.table.selectRow(0)
        self.assertTrue(window.remove_button.isEnabled())
        window.output_dir.setText('abc')
        window.output_dir.setCursorPosition(1)
        window.output_dir.setFocus()
        QTest.keyClick(window.output_dir, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(window.output_dir.text(), 'ac')
        self.assertEqual(window.table.rowCount(), 1)
        window.table.setFocus()
        QTest.keyClick(window.table, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(window.table.rowCount(), 0)
        self.assertFalse(window.remove_button.isEnabled())
        self.assertFalse(window.remove_action.isEnabled())
        window.close()

    def test_empty_context_click_and_cleared_selection_remove_nothing(self):
        window = Window()
        window.found(media_for('/a.mkv'))
        window.show()
        self.app.processEvents()
        window.table.selectRow(0)
        window.show_file_menu(QPoint(5, window.table.viewport().height() - 5))
        self.app.processEvents()
        self.assertFalse(window.file_menu.isVisible())
        self.assertEqual(window.table.rowCount(), 1)
        window.table.clearSelection()
        self.assertFalse(window.remove_button.isEnabled())
        window.remove_selected()
        self.assertEqual(window.rows, {'/a.mkv': 0})
        window.close()


if __name__ == '__main__':
    unittest.main()
