# Testbericht – MKV Audio Converter 1.0.0

Prüfdatum: **26. Oktober 2026**.

## Umgebung

| Komponente | Verwendete Version |
| --- | --- |
| Betriebssystem | Fedora Linux 44, KDE Plasma Desktop Edition |
| Python | 3.14.8 |
| PySide6 | 6.11.2 |
| FFmpeg / FFprobe | 8.1.3 |
| MKVToolNix | 102.0 |
| Qt-Testplattform | offscreen |

## Automatisierte Tests

```text
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v

Ran 26 tests in 19.943s
OK
```

**26 erfolgreich, keine übersprungen.**
Das vollständige Protokoll liegt in [docs/tests.log](docs/tests.log).

18 Unit-Tests prüfen unter anderem:

- DTS-Erkennung einschließlich DTS-HD-Bezeichnung.
- Nicht fortlaufende MKVToolNix-Track-IDs, ursprüngliche Reihenfolge und richtige
  Zuordnung von Optionen zu den Eingabedateien.
- Ersetzen aller Audiotracks und gezieltes Behalten anderer Tonspuren.
- Erhalt beschreibender Tags bei Entfernung veralteter DTS-Statistiken.
- Dateisuche, Deduplizierung und Ausschluss eigener temporärer Arbeitsordner.
- Kollisionsfreie Ausgabe auch bei bereits vorhandenen Symlinks.
- Sonderzeichen ohne Shell-Auswertung.
- Abbruch eines stillen Prozesses, Prozessbeendigung, Zeitlimit und Fehlerstatus.
- Fehlermeldungen auf stderr auch bei Rückgabecode 0, ungültiges JSON.
- Downmix-Schutz, geänderte Quellen, Überspringen ohne DTS und Aufräumen nach Fehlern.

2 GUI-Tests prüfen die Oberfläche ohne Displayserver:

- Anfangszustand der Schaltflächen und Entfernen einer Tabellenzeile.
- Datei einlesen → konvertieren → Ergebnis und Prüfbericht anzeigen → erneut prüfen.

6 Medienintegrationstests verwenden echte, lokal erzeugte MKV-Dateien:

- Zwei DTS-Spuren, zusätzlich eine unveränderte AC3-Spur, VFR-Video,
  Untertitel, Text-/Schriftanhänge, Kapitel mit Spurbezug und Tags mit Track-UIDs.
- Ungewöhnliche Spurreihenfolge mit Untertiteln vor Audio und Video.
- Sprachangaben `de-AT` und `en-US`, Spurtitel, deaktivierte/Forced-/Default-
  und weitere Audioflags. Ausgangsdatei vor/nach Verarbeitung per SHA-256 verglichen.
- Spuren mit einer und sechs Audiokanälen, verzögerter Audiostart und AC3-CodecDelay.
- Einzige DTS-Spur bei Startzeit 0, fehlende Kapitel und Namenskollision.
- Datei ohne DTS, schnelle Prüfoption und vollständige AC3-Decodierung.
- Erst nach zwölf Sekunden beginnende DTS-Spur.
- Tonlücke mit einem nachfolgenden Audiopuls. Die Position des Pulses im
  decodierten Original und im Ergebnis stimmt innerhalb von 6 ms überein.
  Derselbe Inhaltsvergleich erfolgt beim Test mit verzögertem Start.

Die gründliche Prüfung vergleicht die Paketprüfsummen und Präsentationszeitstempel
aller kopierten Spuren sowie die Inhalte der Anhänge.

## Zusätzliche Prüfungen

- `bash start.sh --check`: alle fünf externen Werkzeuge sowie DTS-Decoder und
  AC3-Encoder erfolgreich erkannt.
- Python-Module kompiliert; beide Shellskripte syntaktisch geprüft.
- KDE-Menüeintrag in einem separaten Testordner erzeugt und mit
  `desktop-file-validate` erfolgreich validiert. Es wurde kein Menüeintrag im
  regulären Benutzerprofil installiert.
- CLI-Batch mit beschädigter Datei, gültiger DTS-Datei und einer Datei ohne DTS:
  ein Fehler, eine erfolgreiche Ausgabe, einmal übersprungen. Der Batch lief
  nach dem Fehler weiter, der Bericht enthielt alle drei Ergebnisse und der
  Rückgabecode war wie erwartet 1.
- Die Oberfläche wurde als Bild geprüft:
  [docs/Oberflaeche.png](docs/Oberflaeche.png).

## Praktische Grenzen der Prüfung

Es wurden synthetische, kurze Mediendateien verwendet. Die tatsächlichen
Filmdateien des Nutzers lagen hier nicht vor. Kein Test auf dessen Fernseher,
kein manueller KDE-Wayland-Bedienungstest und kein Dauertest über mehrstündige
Filme. Reale DTS-HD-MA-/DTS:X-/7.1-Dateien wurden nicht getestet. Die 7.1-Regel
wurde als Schutzbedingung im Unit-Test geprüft; der eigentliche 7.1→5.1-Downmix
verwendet FFmpegs Standardmischung und benötigt einen passenden Decoder.

Die sichere Ausgabe benötigt Hardlinks; exFAT/FAT wird deshalb nicht als
direktes Ziel unterstützt. Die Startanleitung erklärt den Weg über ein lokales
Btrfs-/ext4-Laufwerk und anschließendes Kopieren auf USB.
