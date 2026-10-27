# Testbericht – Listeneinträge entfernen 1.2.1

Prüfdatum: **27. Oktober 2026**.

## Ergebnis

```text
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
Ran 72 tests in 43.431s
OK
```

**72 Tests erfolgreich, keine übersprungen.**
[Protokoll](logs/tests-1.2.1.log).

## Änderung

Die Tabelle bietet ein Rechtsklick-Menü **„Aus Liste entfernen“** und die
Entf-Taste bei Tabellenfokus. Beide verwenden dieselbe geschützte Routine wie
die vorhandene Schaltfläche **„Auswahl entfernen“**. Diese ist ohne Auswahl
und während eines Auftrags deaktiviert. Das Kontextmenü zeigt bei laufendem
Auftrag die Sperre an. Auch ein veralteter, noch aktivierter Menüaufruf kann
die Sperre in der Routine nicht umgehen.

Ein Rechtsklick auf eine unmarkierte Zeile wählt genau diese aus; innerhalb
einer Mehrfachauswahl bleibt die Gruppe erhalten. Entfernt werden nur die
Zeilen und deren interne Medien-, Ausgabe- und Schadenszuordnungen. Originale,
fertige Dateien und vorhandene Berichte bleiben erhalten. Das Menü gehört
dauerhaft zur Tabelle und wird ohne verschachtelte Ereignisschleife geöffnet.
Beim Start eines Auftrags wird ein offenes Menü geschlossen.

## Neue Regressionstests

- Rechtsklick auf einen anderen Eintrag entfernt die angeklickte Datei;
  gleichnamige Dateien in verschiedenen Ordnern bleiben korrekt zugeordnet.
- Mehrere nicht benachbarte Zeilen werden gemeinsam entfernt. Verbleibende
  Zeilennummern und Zuordnungen stimmen danach weiterhin.
- Originaldateien und fertige Ausgabe werden in einem temporären Verzeichnis
  angelegt und bleiben nach dem Entfernen bytegleich erhalten. Der bestehende
  Prüfbericht bleibt verfügbar. Eine erneut hinzugefügte Quelle erbt keine
  alte Ausgabezuordnung.
- Einlesen, Konvertierung, Rettungsanalyse und Rettung sperren Schaltfläche,
  Menüaktion und direkten Entfernen-Aufruf. Nach Abschluss ist die Aktion
  für vorhandene Auswahlen wieder verfügbar.
- Echte Qt-Tastaturereignisse prüfen Entf in der Tabelle und im Zielordnerfeld:
  Im Textfeld wird Text bearbeitet; Listeneinträge bleiben dabei erhalten.
- Rechtsklick in den leeren Bereich und Entfernen ohne Auswahl verändern nichts.

Die neuen Tests benutzen das echte Qt-Kontextmenü. Menü und Hauptfenster
wurden zusätzlich offscreen gerendert und visuell geprüft. Die bestehenden
Medien-, Konvertierungs- und Mehrdateien-Rettungstests bestehen weiterhin.
Die Audio-/Videoverarbeitung wurde für diese Erweiterung nicht verändert.
