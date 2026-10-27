# MKV Audio Converter

**DTS → AC3 für MKV-Dateien, mit unverändertem Video.**

Eine Python-/Qt-Anwendung für Fedora KDE und Windows x64. Dateien oder ganze
Ordner hinzufügen, DTS-Tonspuren erkennen und gemeinsam verarbeiten. Neue
Ausgaben werden separat gespeichert; Originaldateien bleiben unverändert.

![MKV Audio Converter 1.3.0 nach einer geprüften Konvertierung](docs/Oberflaeche.png)

## Funktionen

- Alle DTS-Spuren einer Datei nach AC3 konvertieren; andere Spuren kopieren.
- Spurreihenfolge, Sprachen, Flags, Untertitel, Kapitel und Anhänge erhalten.
- DTS-Bezeichnungen in konvertierten Spurtiteln durch AC3 ersetzen.
- Fortschritt, Abbruch, Protokolle und Ergebnisprüfung mit Prüfbericht.
- Optionaler Rettungsmodus für beschädigte MKVs, mit ausdrücklicher
  Verlustbestätigung und gesondertem Bericht.

Video wird mit MKVToolNix übernommen und **nicht neu codiert**. FFmpeg schreibt
ausschließlich Audio. AC3 ist verlustbehaftet; mehr als sechs Audiokanäle
können auf 5.1 reduziert werden.

## Windows

Die [Releases](https://github.com/Fry747/mkv-audio-converter/releases) enthalten
den **Installer** und ein **portables ZIP**. Für öffentliche
Release-Downloads ist kein GitHub-Konto erforderlich.

1. `MKVAudioConverter-1.3.0-windows-x64-setup.exe` installieren oder die portable
   ZIP vollständig entpacken und `MKVAudioConverter.exe` starten.
2. Beim ersten Start fehlende Werkzeuge über den Assistenten einrichten.
   Dafür ist einmalig Internet nötig. Vorhandene Werkzeugordner sind ebenfalls nutzbar.
3. MKVs hinzufügen, Zielordner wählen und **Konvertieren** anklicken.

Python und Qt sind enthalten. Die Installation erfolgt im Benutzerprofil
ohne Administratorrechte. FFmpeg und MKVToolNix werden separat von den
angegebenen Anbietern heruntergeladen; sie sind nicht im Anwendungspaket enthalten.

**Praktisch getestet: Windows 11 x64.** Windows 10 ab 1809 ist technisch
vorgesehen, bisher jedoch nicht praktisch abgenommen. ARM64 und 32-Bit sind
keine zugesicherten Ziele. [Windows-Anleitung](docs/windows.md).

## Fedora KDE

Repository klonen oder das Quellarchiv entpacken, dann im Projektordner:

```bash
sudo dnf install python3 python3-pyside6 mkvtoolnix ffmpeg-free
bash start.sh --check
bash start.sh
```

FFmpeg muss den DTS-Decoder `dca` und den AC3-Encoder `ac3` enthalten; der
Werkzeugcheck prüft dies. Optionaler Eintrag im KDE-Menü:

```bash
bash install-desktop.sh
```

Der Projektordner muss danach am selben Ort bleiben.
[Weitere Installations- und Entwicklungsoptionen](docs/development.md).

## Bedienung und Dokumentation

Aus `Film.mkv` wird `Film_ac3.mkv`. Vorhandene Namen erhalten fortlaufende
Nummern und werden nicht überschrieben. Dateien ohne DTS werden übersprungen.
Nach einem Abbruch bleiben fertige Ausgaben erhalten; temporäre Dateien
werden entfernt und der Fortschrittsbalken wird zurückgesetzt.

- [Bedienung, Warteschlange und Optionen](docs/usage.md)
- [Windows: Installation, Werkzeuge und Paketbau](docs/windows.md)
- [Rettungsmodus und seine Grenzen](docs/recovery.md)
- [Kommandozeile](docs/cli.md)
- [Verarbeitung, Metadaten und Ergebnisprüfung](docs/design-and-validation.md)
- [Entwicklung und Tests](docs/development.md) · [Prüfstand 1.3.0](docs/testing/README.md)
- [Änderungen](CHANGELOG.md) · [Fehler melden](https://github.com/Fry747/mkv-audio-converter/issues)

Eine erfolgreiche technische Prüfung ersetzt keinen Wiedergabetest auf dem
eigenen Fernseher. Der Rettungsmodus rekonstruiert keine verlorenen Bilder
oder Töne und kann Lücken erzeugen.

## Lizenz und Drittanbieter

Der Anwendungscode steht unter der [MIT-Lizenz](LICENSE). Qt/PySide6, Python,
das KDE-Breeze-Notensymbol und andere Bestandteile besitzen eigene Lizenzen.
Der Windows-Build enthält Lizenztexte und Versionsangaben; die zugehörigen
Qt-/PySide6-Quellen werden als zusätzliches Release-Archiv bereitgestellt.
[Drittanbieter, Quellen und Nutzungsrechte](THIRD_PARTY.md).

Das Projekt ist unabhängig von FFmpeg, MKVToolNix, Qt, KDE und Fedora und wird
von diesen Projekten nicht herausgegeben.
