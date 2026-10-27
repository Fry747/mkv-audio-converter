# Testbericht – MKV Audio Converter 1.0.1

Prüfdatum: **27. Oktober 2026**. Umgebung: Fedora 44 KDE, Python 3.14.8,
PySide6 6.11.2, FFmpeg/FFprobe 8.1.3, MKVToolNix 102.0.

## Automatisierte Tests

```text
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
Ran 34 tests in 23.543s
OK
```

**34 erfolgreich, keine übersprungen.** Vollständiges Protokoll:
[docs/tests.log](docs/tests.log).

Zusätzlich zu den bestehenden Konvertierungs-, Metadaten-, Synchronisations-,
Sicherheits- und GUI-Tests decken die Regressionstests jetzt insbesondere ab:

- Kapitel aus älteren Dateien ohne ursprüngliches `ChapLanguageIETF`:
  echter Import-/Export-Durchlauf, ursprünglicher Text und Zeitstempel erhalten.
- Bestehende IETF-Sprachwerte, geänderte Kapiteltexte und Zeiten bleiben streng geprüft.
- Gemeinsam vorbereitete DTS-Spuren: genau ein MKVToolNix-Quelldurchlauf und
  korrekte Zuordnung beider FFmpeg-Audiospuren.
- Stets monotoner Fortschritt im Konvertierungskern und bei GUI-Phasenwechseln.
- Sofortiger Abbruch einer Wiederherstellungssuche, sofort sichtbare Warnungen
  und verständlicher Fehlerstatus mit ausführlichem Bericht.

## Prüfung mit den bereitgestellten Originaldateien

### Test_MKV_01.mkv

**Vollständiger Lauf erfolgreich, ohne Warnungen, 534.17 Sekunden
(rund 8 Minuten 54 Sekunden).** Quelle: 12,09 GiB, Laufzeit 3:48:11.670,
zwei echte DTS-ES-6.1-Tonspuren mit je sieben Kanälen. Beide wurden nach AC3 5.1
konvertiert.

Erfolgreich geprüft:

- Spurreihenfolge, Codecs, UIDs, Sprachen, Namen und Flags.
- Alle 48 Kapitel einschließlich Texte, Zeiten und Referenzen; Filmtitel und Tags.
- Anfangs- und Endzeitpunkte der Audiospuren einschließlich Encoderverzögerung.
- Video und ASS-Untertitel: Paketprüfsummen und alle Präsentationszeitstempel.
- Zwei Anhänge: Metadaten und SHA-256 der Inhalte.
- Vollständige fehlerfreie Decodierung beider erzeugten AC3-Spuren.

### TEST_MKV_02.mkv

**Erwartet abgewiesen nach 22.94 Sekunden.** MKVToolNix meldet
in der Originaldatei einen Strukturfehler bei Byteposition **8.144.052.744**
und will nach dem nächsten Matroska-Element suchen. Version 1.0.1 beendet
sofort diesen Werkzeuglauf. Kein FFmpeg-Encoder gestartet, keine fertige
Ausgabe, temporäre Dateien vollständig entfernt.

Die 78 Originalkapitel wurden unabhängig davon auf einer kleinen temporären
Matroska-Datei importiert und erneut exportiert. Mit dem Fix stimmt ihr
Vergleich; Version 1.0.0 hatte dieselben Daten fälschlich abgelehnt.
Dieser Kapiteltest bestätigt keine Reparatur der beschädigten Filmdatei.

Beide Originaldateien wurden ausschließlich gelesen. Dateiidentität, Größe und
Änderungszeit waren vor und nach den Läufen unverändert. Es wurde kein Update
in den bisherigen Anwendungsordner installiert.

Eine Zusammenfassung ohne persönliche Dateipfade liegt in
[docs/real-validation.json](docs/real-validation.json).

## Weitere Prüfung und Grenzen

Python-Dateien kompiliert, Shellskripte syntaktisch geprüft. Der Quellcode-Patch
lässt sich auf den unveränderten Stand 1.0.0 anwenden (`git apply --check`).

Kein Test auf dem Fernseher und kein manueller Wiedergabetest des mehrstündigen
Films. Die Tests bestätigen die beschriebenen Daten-, Container- und
Audioeigenschaften. Die zweite Datei benötigt eine intakte Quelle bzw. eine
separat geprüfte Reparatur. Reale DTS-HD-MA-/DTS:X-/7.1-Dateien sind weiterhin
nicht abgedeckt; echte DTS-ES-6.1-Dateien wurden mit diesem Lauf geprüft.
