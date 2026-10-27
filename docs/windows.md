# Windows – Version 1.3.0

## Empfohlene Verteilung

**Ein Installer für normale Benutzer, zusätzlich eine portable ZIP.** Beide
enthalten dieselbe GUI-EXE, eine zusätzliche Konsolen-EXE für CLI-Aufgaben,
Python, PySide6/Qt und deren Laufzeitdateien. Python muss auf dem Zielrechner
nicht installiert sein. **Praktisch getestet: Windows 11 x64 (Intel/AMD).** Windows 10 ab 1809 ist
technisch vorgesehen, aber bisher nicht praktisch abgenommen. Kein zugesicherter ARM64-/32-Bit-Build.

Der Ordner-Build mit PyInstaller ist bewusst gewählt: zuverlässiger Start,
separate Laufzeitdateien und identischer Inhalt für Installer und ZIP. Eine
Onefile-EXE müsste diese Dateien bei jedem Start wieder temporär entpacken.

### Installer

`MKVAudioConverter-1.3.0-windows-x64-setup.exe` ausführen. Installation im
eigenen Benutzerprofil, ohne Administratorrechte, mit Startmenüeintrag und
optionalem Desktop-Symbol. Deinstallation über die Windows-Einstellungen.

### Portable ZIP

`MKVAudioConverter-1.3.0-windows-x64-portable.zip` vollständig entpacken und
`MKVAudioConverter.exe` starten. Den Unterordner `_internal` mit der EXE
zusammenlassen. Einstellungen und Werkzeugcache liegen auch bei dieser
Variante im Benutzerprofil; „portable“ bedeutet installationsfrei.

## Abhängigkeiten automatisch einrichten

Sind passende Werkzeuge bereits über den PATH bzw. in den üblichen
Installationsordnern verfügbar, werden diese verwendet. Die Windows-Version
erwartet stabile FFmpeg-/FFprobe-Versionen ab 8 und MKVToolNix ab 102; ältere
oder nicht erkennbare Versionen werden vor der Konvertierung abgewiesen. Andernfalls öffnet
sich beim ersten Start der Assistent **Windows-Werkzeuge einrichten**:

1. **Werkzeuge herunterladen und einrichten** anklicken.
2. Der Assistent lädt die festgelegten Originalarchive (zusammen ca. 209 MiB):
   FFmpeg 9.0.2 Essentials von gyan.dev und MKVToolNix 103.0 vom Projektserver.
3. SHA-256 muss mit dem im Anwendungscode festgelegten Wert übereinstimmen.
   Unsichere Archivpfade, Links, doppelte Namen und zu große Archive werden
   abgewiesen. Es werden alle ursprünglichen Lizenzdateien/DLLs erhalten.
4. Die fünf EXEs werden auf x64-Format geprüft und aufgerufen. DTS-Decoder,
   AC3-Encoder und Versionen werden geprüft. Erst danach wird der gesamte
   neue Werkzeugsatz aktiviert. Eine vorhandene Konfiguration bleibt bei
   Downloadfehler oder Abbruch erhalten.

Die Einrichtung benötigt mindestens **3 GiB** freien Platz für Download und
Entpacken. Sie schreibt unter `%LOCALAPPDATA%\MKVAudioConverter\tools`,
ändert weder System-PATH noch systemweite Installationen und benötigt keine
Administratorrechte. Danach funktioniert die Konvertierung offline.

Bei einem Netzwerkfehler zeigt der Assistent den Grund und erlaubt einen
neuen Versuch. Abbruch wird zwischen den Netzwerk-Lesevorgängen geprüft;
diese haben zehn Sekunden Socket-Timeout. Die Oberfläche bleibt dabei bedienbar.
Es wird kein halbfertiger Werkzeugsatz aktiviert.
Über **Werkzeuge → Windows-Werkzeuge einrichten …** ist der Assistent erneut
erreichbar. Es gibt keine stillen Werkzeugupdates; neue Versionen werden mit
einem geprüften Downloadplan in einer Anwendungsversion ausgeliefert.

### Offline oder eigene vorhandene Werkzeuge

Beide Originalarchive auf einem Rechner mit Internet herunterladen und
entpacken, z. B. unter einem gemeinsamen Ordner `C:\MKV-Tools`:

```text
C:\MKV-Tools\ffmpeg\...\bin\ffmpeg.exe
C:\MKV-Tools\ffmpeg\...\bin\ffprobe.exe
C:\MKV-Tools\mkvtoolnix\...\mkvmerge.exe
C:\MKV-Tools\mkvtoolnix\...\mkvextract.exe
C:\MKV-Tools\mkvtoolnix\...\mkvpropedit.exe
```

Im Assistenten **Vorhandenen Ordner verwenden …** wählen. Auch diese Auswahl
wird vor der Aktivierung geprüft. Alternativ denselben Werkzeugbaum unter
`tools` neben die EXE legen. CLI-Override: `--tools-dir C:\MKV-Tools`, oder die
Umgebungsvariable `MKV_AUDIO_CONVERTER_TOOLS_DIR`. Eine explizite Konfiguration
hat Vorrang; defekte/mehrdeutige Konfigurationen fallen nicht still auf andere
EXEs zurück. Der Arbeits-/Filmordner wird nie nach EXEs durchsucht.

Die MKVToolNix-Microsoft-Store-Ausgabe stellt ihre CLI-Werkzeuge laut Hersteller
nicht für andere Anwendungen bereit. Für dieses Tool die normale Installation
oder das portable Originalarchiv verwenden.

## Konvertieren, abbrechen und Ausgaben

Die Oberfläche und die Rettungsauswahl funktionieren wie unter Fedora. Kein
Video-Reencoding. Tool-Konsolenfenster bleiben verborgen. stdout/stderr werden
unter Windows gleichzeitig mit begrenzten Puffern gelesen, damit die GUI auch
bei vielen Meldungen und stillen Prozessen reagiert. Abbruch beendet über ein
Windows Job Object die zugeordneten Prozesse einschließlich ihrer Kinder.

Originaldateien bleiben unverändert. Neue Ausgaben werden auf demselben
Datenträger exklusiv umbenannt: Unter Windows überschreibt `os.rename` keine
bestehende Datei. Dadurch sind auch **lokale NTFS-/exFAT-Ziele** ohne Hardlinks
möglich. Linux verwendet weiterhin exklusive Hardlinks. Netzlaufwerke und
Cloud-Synchronisationsordner sind nicht als verlässliche Arbeitsziele zugesichert.
Bei der Rettung bekommt jede Ausgabe ihren eigenen Verlustbericht.

Die Deinstallation entfernt Programmdateien. Medien und der separate
Werkzeugcache werden nicht automatisch gelöscht. Für eine vollständige
Entfernung den Cache nach Beenden der Anwendung selbst löschen.

## CLI und Quellcode-Start

In PowerShell die Konsolen-EXE verwenden:

```powershell
.\MKVAudioConverter-cli.exe --check
.\MKVAudioConverter-cli.exe --setup-tools
.\MKVAudioConverter-cli.exe --cli --output-dir 'D:\Ausgabe' 'D:\Filme'
```

Für Entwickler ist zusätzlich `start.cmd` vorhanden. Dieser Weg benötigt
selbst installiertes Python und PySide6; er ist nicht der empfohlene Endnutzerweg:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.cmd
```

## Windows-Pakete bauen

Der Windows-Build muss auf Windows erstellt werden. PyInstaller ist kein
Linux→Windows-Crosscompiler. Python 3.13.17 x64 und Inno Setup 6 bereitstellen:

```powershell
.\packaging\windows\build-windows.ps1
```

Das Skript erstellt eine eigene `.venv-build`, installiert die festgelegten
Build-Abhängigkeiten und erzeugt unter `dist\windows`:

- Installer-EXE,
- portable ZIP,
- den aktuellen Anwendungsquellcode als ZIP,
- passende Qt-/PySide6-Originalquellen als separates ZIP,
- `SHA256SUMS.txt`.

Der Build lädt zusätzlich rund 66 MiB gepinnte LGPL-Quellen und prüft deren
SHA-256. Ohne diese Quellen oder bei unerwarteten Qt-Komponenten wird kein
Release-Paket fertiggestellt. Alle fünf Dateien gemeinsam veröffentlichen.

Nur ZIP: `build-windows.ps1 -SkipInstaller`. `build-dependencies.json` und
`licenses` liegen im Programmpaket. Hinweise zu Drittanbietern:
[THIRD_PARTY.md](../THIRD_PARTY.md). Keine Python-/Tooldownloads beim normalen
Programmstart, wenn alles bereits eingerichtet ist.

### GitHub Actions

Workflow **Windows build and test** manuell unter Actions starten oder einen
Versions-Tag pushen. Der Workflow richtet die geprüften Werkzeuge ein, führt
die Tests nativ auf Windows aus, baut EXEs/Installer/ZIP und prüft zusätzlich
die eingefrorene CLI mit einer echten Unicode-Datei und AC3-Konvertierung sowie
den Start der GUI. Auch stille Installation und Deinstallation mit Erhalt
einer Test-Mediendatei und des Werkzeugcaches werden geprüft.
Download unter den Workflow-Artefakten. Das Artefakt `windows-test-logs`
enthält auch die Protokolle der Abhängigkeitseinrichtung und des Werkzeug-Setups,
falls der Lauf bereits vor den Tests abbricht. Ein erneuter Versuch nach einer
Codekorrektur muss über **Run workflow** mit dem aktuellen Branch gestartet werden:
**Re-run failed jobs** wiederholt den alten Commit einschließlich des alten Fehlers.

Es wird kein GitHub-Release automatisch veröffentlicht.

Der Nutzer hat Installation, Ersteinrichtung, Bedienung, echte Medien, Fehlerfälle
und Verteilung auf Windows 11 erfolgreich geprüft (27. Oktober 2026). Änderungen
an Fortschrittsanzeige, Symbolen und Paketinhalt erfordern einen erneuten Build
und einen kurzen praktischen Nachtest vor der Freigabe. Ein Linux-
Testlauf oder ein erfolgreich entpacktes EXE-Archiv ist kein Nachweis eines
funktionierenden Windows-Programms. Der aktuelle Prüfstand steht im
[Prüfstand 1.3.0](testing/README.md).

Die zunächst erzeugten EXEs sind unsigniert. Für öffentliche Downloads ist
Authenticode-Signierung der beiden Programm-EXEs und danach des Installers
vorgesehen; ohne ein Herausgeberzertifikat kann Windows eine Warnung anzeigen.
Mit vorhandenem Zertifikat im Windows-Zertifikatsspeicher und `signtool.exe`:
`build-windows.ps1 -CertificateThumbprint <Fingerabdruck>`.
Die EXEs werden vor dem Verpacken, der Installer danach signiert und die
Prüfsummen zuletzt erstellt. Ein Zertifikat ist nicht Teil dieses Projekts.

## Quellen der technischen Entscheidungen

- [PyInstaller: Ordner-/Onefile-Verteilung](https://pyinstaller.org/en/stable/operating-mode.html)
- [PyInstaller: DLL-Suchpfade externer Programme](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)
- [Python: Windows-Pipes und selectors](https://docs.python.org/3/library/selectors.html)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Python: os.rename](https://docs.python.org/3/library/os.html#os.rename)
- [Inno Setup: Benutzerinstallation](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
- [MKVToolNix: Windows-Downloads](https://mkvtoolnix.download/downloads.html#windows)
- [FFmpeg: Bezugsquellen für Windows-Builds](https://ffmpeg.org/download.html)
