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
als Artefakte bereit. Er wurde eingerichtet, **nicht auf GitHub gestartet**.
Ein manueller Desktoptest auf Windows 10/11 ergänzt die CI-Prüfungen.

Die Änderungen sind damit implementiert und auf Linux regressionsgeprüft;
eine native Windows-Freigabe ist mit diesem Bericht noch nicht bestätigt.
