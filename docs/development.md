# Entwicklung und Tests

Python ≥ 3.10, PySide6 Essentials ≥ 6.7 und die fünf externen Werkzeuge
`ffmpeg`, `ffprobe`, `mkvmerge`, `mkvextract`, `mkvpropedit` werden benötigt.
Fedora kann die Systempakete aus der README verwenden.

## Eigene Python-Umgebung

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash start.sh --check
bash start.sh
```

`start.sh` bevorzugt eine vorhandene `.venv`. Alternativ: `python -m pip install .`,
danach `mkv-audio-converter`. Windows-Quellcode-Start und native Paketierung:
[windows.md](windows.md).

## Tests

Linux/Fedora:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Windows/PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s tests -v
```

Die Tests erzeugen kurze synthetische Medien in temporären Ordnern und laden
keine Filme herunter. Für Medientests sind zusätzlich die FFmpeg-Encoder
`dca` und `ffv1` erforderlich; der Konverter selbst benötigt sie nicht.
Fehlende Qt-/Medienabhängigkeiten führen zu übersprungenen Tests. Vor einer
Freigabe deren Anzahl prüfen. Windows-spezifische Betriebssystemtests laufen
in der Windows-CI; Linux-Tests ersetzen sie nicht.

## Projektaufbau

| Verzeichnis | Inhalt |
| --- | --- |
| `mkv_audio_converter/` | GUI, Verarbeitung, Rettung und Werkzeugverwaltung |
| `mkv_audio_converter/assets/` | Gemeinsames Symbol, PNG/ICO und bearbeitbares SVG |
| `tests/` | Unit-, GUI-, Medien- und Paketierungstests |
| `packaging/windows/` | Native Builds, Komponentenprüfung und Quellbeigaben |
| `tools/` | Screenshot- und Icon-Erzeugung |
| `docs/` | Benutzer- und Entwicklerdokumentation |
| `docs/testing/` | Aktueller Prüfstand und ausdrücklich historische Berichte |
| `LICENSES/` | Drittanbietertexte für Artwork und Binärpakete |

## Änderungen beitragen

Fehler über GitHub Issues melden; Version, Betriebssystem und relevante
Fehlermeldung angeben. Pfade, Filmtitel und persönliche Daten vor einem Upload
aus Protokollen entfernen. Keine Filmdateien, Zugangsdaten oder privaten
Werkzeugarchive hochladen. Sicherheitslücken: siehe [SECURITY.md](../SECURITY.md).

Änderungen möglichst mit einem reproduzierenden Test und knapper Beschreibung
einreichen. Neue Runtime-Komponenten erfordern eine Prüfung ihrer Lizenzen,
Quellen und des Windows-Pakets. [Release-Ablauf](releasing.md).
