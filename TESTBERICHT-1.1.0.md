# Testbericht – Rettungsmodus 1.1.0

Prüfdatum: **27. Oktober 2026**. Fedora 44 KDE, Python 3.14.8,
PySide6 6.11.2, FFmpeg/FFprobe 8.1.3 und MKVToolNix 102.0.

## Testsuite

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
Ran 46 tests in 35.814s
OK
```

**46 Tests erfolgreich, keine übersprungen.**
[Protokoll](docs/tests-1.1.0.log).

Alle bisherigen Tests des strengen Konvertierungsmodus bestehen weiterhin.
Die neuen Tests prüfen VINT-/Elementgrenzen, CRC-32, Lacing-Varianten,
fehlende/beschädigte Cluster, unbekannte Tracknummern, falsche Cluster-Kennungen
in Nutzdaten, Dateiänderungen und SHA-256-Kopierkontrollen sowie Abbruch.
Ein eigener Test verändert Nutzdaten bei identischer Dateigröße und
wiederhergestellter Änderungszeit; die Kopier-Prüfsumme erkennt dies trotzdem.

Die GUI-Tests prüfen ausdrücklich „Abbrechen“ und die bestätigte Rettung.
CLI-Tests prüfen reine Analyse, Ablehnung ohne `--accept-loss` und den separaten
Rückgabecode 3 nach einer Rettung. Ein echter Medientest zerstört einen Cluster
in einer erzeugten MKV und rettet/konvertiert die verbleibenden Daten. Dabei
werden Verlustbericht, Schutz der Quelle, Dateikollisionen und Aufräumen geprüft.
Nach der abschließenden Änderung der GUI-Zeitmarken und der Abbruchkontrollen
wurden die jeweiligen Tests und danach die vollständige Suite erneut ausgeführt.

## Reale Testdatei TEST_MKV_02.mkv

Der vollständige Rettungs- und AC3-Lauf war **erfolgreich** und dauerte
**871.19 Sekunden, rund 14 Minuten 31 Sekunden**. Erfolgreich bedeutet
hier, dass eine technisch geprüfte **Teilrettung** erstellt wurde. Es bedeutet
keine vollständige Wiederherstellung des Originalfilms.

- 14.520 strukturell lesbare Cluster übernommen.
- Sieben unlesbare Bereiche mit zusammen 480.226.340 Bytes ausgelassen.
- Keine Cluster-CRCs vorhanden; unbemerkte Codec-Nutzdatenfehler sind dadurch
  nicht ausgeschlossen.
- Beide DTS-ES-6.1-Spuren nach AC3 5.1, 48 kHz konvertiert.
- H.264-Video und ASS-Untertitel übernommen; keine Video-Neucodierung.
- Zeitachse weiterhin 15.793,120 Sekunden. Ausgelassene Bereiche wurden nicht
  aus der Zeitachse herausgeschnitten.
- Beide erzeugten AC3-Spuren vollständig und streng fehlerfrei decodiert.
- Übernommene Video-/Untertitelpakete und alle PTS gegenüber dem strukturell
  geprüften Rettungskandidaten verglichen. **Kein Vollständigkeitsvergleich mit
  den unlesbaren Originalbereichen.**
- Spurreihenfolge, UIDs, Sprachen, Namen, Flags, 78 Kapitel und zwei Anhänge
  geprüft; Anhangsinhalte per SHA-256 verglichen.
- In diesem Lauf keine zusätzlichen Decoder-Fehlermeldungen nach dem
  strukturellen Ausschluss der defekten Cluster aufgezeichnet.
- Größe, Änderungszeit und Dateiidentität der Originaldatei vor/nach dem Lauf
  unverändert. Die Quelle wurde ausschließlich lesend geöffnet.

Die Zusammenfassung ohne private absolute Pfade steht unter
[docs/recovery-validation.json](docs/recovery-validation.json).

## Grenzen

Keine vollständige Videodecodierung, kein visueller Wiedergabetest über den
mehrstündigen Film und kein TV-Test. Nach ausgelassenen Referenzbildern sind
weitere sichtbare Bildstörungen bis zum nächsten geeigneten Schlüsselbild
möglich. Ein strukturell lesbarer Cluster ist ohne CRC nicht automatisch ein
fehlerfreier Codec-Datenblock. Die Schadstellen müssen im Player geprüft werden.
Die Ausgabe ist deshalb dauerhaft als `SALVAGED_WITH_POSSIBLE_LOSS` mit
`completeness: NOT_CONFIRMED` gekennzeichnet.

Dieser Bericht dokumentiert den geprüften Stand von Version 1.1.0.
