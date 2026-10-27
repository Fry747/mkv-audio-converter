# Testbericht – Windows-Unterstützung 1.3.0

Prüfdatum: **27. Oktober 2026**. Lokaler Host: **Linux**, Python
3.14.8, PySide6 6.11.2.

## Tatsächlich ausgeführte Tests

```text
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
Ran 88 tests in 46.273s
OK (skipped=2)
```

**86 erfolgreich, zwei native Windows-Tests auf Linux übersprungen.**
[Gesamtes Testprotokoll](docs/tests-1.3.0.log).

Alle bisherigen GUI-, Metadaten-, Medien- und Rettungstests bestehen. Neu sind
begrenzte gleichzeitige Pipe-Leser, hoher stdout/stderr-Durchsatz, Fortschritt,
Abbruch/Timeout bei stillen Prozessen sowie Abbruch nach geschlossenem stdout
und stderr. Eine echte kurze DTS-MKV mit Unicode-Dateinamen wurde mit den für
Windows vorgesehenen Pipe-Threads vollständig nach AC3 konvertiert. Spurtitel,
Audio-Decodierung, Zeitstempel und der unveränderte Quellhash werden dabei geprüft.

Die Downloadtests prüfen Hashabweichungen, erlaubte HTTPS-Ziele,
Archiv-Traversal, Windows-Gerätenamen, Groß-/Kleinschreibungs-Dubletten und
Links. Die Einrichtung wird transaktional geprüft: Bei Fehlern bleiben die
aktivierte Konfiguration und der vorhandene Werkzeugbaum erhalten, temporäre
Dateien werden entfernt und die Originallizenzen werden mit entpackt.
Explizite EXE-Suche ignoriert den Arbeitsordner; mehrdeutige Werkzeugsätze und
zu alte vorhandene Windows-Versionen werden abgewiesen.

GUI-Tests prüfen Fehler und erneuten Versuch im Assistenten, Abbruch vor dem
Zerstören des Hintergrundthreads und dass fehlende Werkzeuge keinen
Konvertierungsworker starten. Der Assistent wurde unter Linux offscreen
visuell geprüft. Der GUI-Starttest `--gui-smoke-test` wurde erfolgreich ausgeführt.
Python-, Spec-/Versionsressourcen-Syntax und YAML-Struktur des Workflows wurden
geprüft. Das ist keine Kompilierung der PowerShell-/Inno-Setup-Dateien.

## Echte Windows-Originalarchive

Die festgelegten Original-ZIPs wurden tatsächlich heruntergeladen und mit den
Herstellerprüfsummen verglichen, danach durch den neuen sicheren Entpacker
verarbeitet:

- FFmpeg 9.0.2 Essentials: **114.768.076 Bytes**, SHA-256 stimmt.
- MKVToolNix 103.0: **103.859.301 Bytes**, SHA-256 stimmt.
- Alle fünf benötigten Programme wurden gefunden und auf x64-PE-Kopf geprüft.
- Die EXEs wurden **nicht unter Linux ausgeführt**.

[Prüfbeleg mit URLs und Hashes](docs/windows-archive-validation.json).
Die Archive liegen nur in den lokalen Prüfdaten, nicht im Git-Repository oder
im angebotenen Anwendungsquellpaket.

## Noch nicht unter Windows ausgeführt

Auf diesem Rechner stehen Windows, Wine und PowerShell nicht zur Verfügung.
Es gibt daher bislang **keinen tatsächlich gebauten/geprüften Windows-Installer
oder Windows-EXE aus diesem Arbeitsstand**. Insbesondere sind folgende Prüfungen
vorbereitet, aber noch nicht ausgeführt:

- Windows Job Object: Abbruch beendet auch den Test-Kindprozess.
- Windows-Umbenennen: Kollisionen ersetzen keine vorhandenen Ausgaben und
  benötigen keine Hardlinks.
- Native Windows-Tests der Anwendung mit den festgelegten Werkzeugen.
- PyInstaller-Build der GUI-/CLI-EXEs und Inno-Setup-Kompilierung.
- Eingefrorene EXE: Codecprüfung, echte Unicode-Dateikonvertierung und normaler
  GUI-Start/-Abschluss einschließlich DLL-Suchpfad-Isolation.
- Stille Installation und Deinstallation mit Erhalt einer Test-Mediendatei
  und der gesonderten Werkzeugkonfiguration.

Der Workflow [.github/workflows/windows.yml](.github/workflows/windows.yml)
führt diese Schritte auf Windows x64 aus und stellt nur bei Erfolg die Pakete
als Artefakte bereit. Der erste GitHub-Lauf brach vor den Tests bei der Werkzeugeinrichtung ab;
siehe den folgenden Nachtrag.
Ein manueller Desktoptest auf Windows 10/11 ergänzt die CI-Prüfungen.

Die Änderungen sind damit implementiert und auf Linux regressionsgeprüft;
eine native Windows-Freigabe ist mit diesem Bericht noch nicht bestätigt.


## Nachtrag: erster GitHub-Windows-Lauf und Korrektur

Der [Windows-Lauf 40501193664](https://github.com/Fry747/mkv-audio-converter/actions/runs/40501193664)
auf Commit `c0fa37f` scheiterte am 27. Oktober 2026 bereits nach Download und
Entpacken der Werkzeuge. Der erste Versionsaufruf von `mkvmerge.exe` meldete:

```text
Error: There is no translation available for 'en_US'.
```

Der Runner hatte den Unix-Sprachcode `en_US` an die Windows-Binaries übergeben;
diese erwarten `en`. Die Korrektur gilt für `mkvmerge`, `mkvextract` und
`mkvpropedit`. Ein plattformübergreifender Regressionstest führt den Runner mit
einem Prozess aus, der den falschen Sprachcode ablehnt, und prüft alle drei
Werkzeuge einschließlich UTF-8-Ausgabe.

Die fehlenden Test-/Installer-Logs waren eine Folge des frühen Abbruchs. Der
Workflow zeichnet nun auch Umgebung, Abhängigkeiten, Werkzeug-Setup, Build und
EXE-Prüfung auf und lädt vorhandene Protokolle auch bei Fehlern hoch. Die
verwendeten Actions sind auf die am Prüfdatum verfügbaren stabilen Versionen
mit Node 24 aktualisiert und weiterhin auf vollständige Commit-SHAs festgelegt:
Checkout 7.0.1, Setup Python 7.1.0 und Upload Artifact 7.0.2. Die `action.yml`
aller drei konkreten Commits wurde auf `runs.using: node24` geprüft.

Die CLI schreibt beim Setup nur noch geänderte Prozent-/Phasenanzeigen; der
erste Lauf hatte über 13.000 Zeilen mit überwiegend identischen Prozenten.
Ein Regressionstest prüft, dass 1.000 identische Meldungen nur einmal erscheinen.

Ein neuer nativer Windows-Lauf ist für die korrigierte Fassung weiterhin
notwendig. **Run workflow** auf dem aktualisierten Branch ausführen;
**Re-run failed jobs** verwendet weiterhin den alten Commit.


Lokale Prüfung nach der Korrektur (Linux):

```text
Ran 90 tests in 50.655s
OK (skipped=2)
```

**88 erfolgreich, zwei native Windows-Tests übersprungen.**
[Protokoll der korrigierten Fassung](docs/tests-windows-workflow-fix.log).
Die YAML-Struktur, vollständigen Action-Pins und Python-Syntax wurden ebenfalls
geprüft. PowerShell-Transkripte und der vollständige Installer-Build sind erst
im neuen Windows-Lauf ausführbar.
