# Testbericht – automatische Spurtitel 1.1.1

Prüfdatum: **27. Oktober 2026**.

## Änderung

Bisher wurden die ursprünglichen DTS-Spurtitel nach dem Remuxen durch
`mkvpropedit` wiederhergestellt. Version 1.1.1 verwendet beim Remuxen, bei der
Metadatenwiederherstellung und bei der Ergebnisprüfung dieselbe gezielte
Titelanpassung. Nur tatsächlich konvertierte DTS-Tonspuren sind betroffen.
Sprachangaben und sonstiger Titeltext bleiben erhalten. Beim Downmix von mehr
als sechs Kanälen wird eine direkt an die DTS-Bezeichnung anschließende
Kanalangabe auf 5.1 geändert. Ohne Downmix wird keine Kanalanordnung geraten.
Änderungen stehen mit altem und neuem Namen im Protokoll und Prüfbericht.

## Automatisierte Tests

```text
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
Ran 53 tests in 32.723s
OK
```

**53 Tests erfolgreich, keine übersprungen.**
[Protokoll](docs/tests-1.1.1.log).

Die neuen Tests prüfen die beiden gemeldeten Titel, DTS-Familien und
Schreibweisen, Unicode-Sprachangaben, Trennzeichen, Downmix-Kanalangaben,
Wörter mit eingebettetem DTS, leere Titel und Titel ohne Codec-Bezeichnung.
Auch die Ablehnung eines alten/falschen Titels durch die Ergebnisprüfung ist
abgedeckt.

Der Medienintegrationstest konvertiert zwei DTS-Spuren und prüft die neuen
Titel nach dem vollständigen Remuxen und der Metadatenwiederherstellung.
Eine vorhandene AC3-Spur und eine Untertitelspur behalten dabei ihre eigenen
DTS-Wörter im Namen. Spurreihenfolge, Flags, UIDs, Sprachen, Kapitel, Anhänge,
kopierte Paketdaten und Audiosynchronisation werden weiterhin geprüft.
Der Rettungsintegrationstest prüft zusätzlich den neuen Titel und dessen
Eintrag im Verlustbericht. Die bestehenden GUI- und CLI-Tests bestehen.

## Audioauszug aus TEST_MKV_02.mkv

Aus der Originaldatei wurden ausschließlich die ersten rund vier Sekunden
beider DTS-Audiospuren per Stream Copy in eine temporäre Test-MKV kopiert.
Dieser Auszug durchlief anschließend die reguläre Konvertierung einschließlich
Metadaten-, Zeitstempelprüfung und vollständiger AC3-Decodierung.

| Quelle (je 7 Kanäle) | Ausgabe (je 6 Kanäle) |
| --- | --- |
| `DTS-ES.6.1.Warner.Fixed.x264-Xell` | `AC3.5.1.Warner.Fixed.x264-Xell` |
| `English DTS-ES 6.1` | `English AC3 5.1` |

Die ursprüngliche Testdatei wurde nur gelesen; Größe, Änderungszeit und
Dateiidentität blieben unverändert. Der temporäre Audioauszug war nach der
Konvertierung laut SHA-256 unverändert. Temporäre Testmedien wurden entfernt.
Die Zusammenfassung enthält keine privaten absoluten Pfade:
[docs/title-validation-1.1.1.json](docs/title-validation-1.1.1.json).

Es wurde kein erneuter vollständiger Konvertierungs- oder Rettungslauf über
den mehrstündigen Originalfilm ausgeführt. Der Videoerhalt ist in den kurzen
generierten Medientests geprüft; der reale Auszug enthält ausschließlich Audio.
Bereits mit einer älteren Version erzeugte Dateien werden nicht nachträglich
geändert. Die Umbenennung greift bei neuen Konvertierungen automatisch in GUI,
CLI und Rettungsmodus.
