# Testbericht – Rettung aus der Warteschlange 1.2.0

Prüfdatum: **27. Oktober 2026**.

## Ergebnis

```text
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
Ran 67 tests in 53.081s
OK
```

**67 Tests erfolgreich, keine übersprungen.**
[Protokoll](logs/tests-1.2.0.log).

## Neue Bedienung

Die GUI übernimmt erkannte Quellschäden über ein eigenes Worker-Signal und
speichert deren Gründe unabhängig vom angezeigten Statustext. Der
Rettungsbutton zeigt die Anzahl der verfügbaren Einträge und bleibt ohne
geeignete Einträge bzw. während eines Auftrags deaktiviert.

Die neue Auswahl enthält nur erkannte beschädigte DTS-Dateien der aktuellen
Liste, die noch keine fertige Ausgabe haben. Sie zeigt Dateinamen, vollständige
Pfade und Fehlergründe. Checkboxen erlauben einzelne Dateien, alle oder keine.
Der bisherige Dateidialog entfällt. Nach der sequentiellen Analyse folgt eine
gemeinsame Verlustbestätigung mit Details je Datei und vorausgewähltem Abbruch.
Nur erfolgreich analysierte Dateien werden danach zur Rettung übergeben.

## Geprüfte Fälle

- Quellschäden werden strukturiert erkannt; allgemeine Konvertierungsfehler
  und ein bloßer passender Statustext machen keine Datei zum Rettungskandidaten.
- Gleichnamige Dateien aus unterschiedlichen Ordnern bleiben über ihre vollen
  Pfade eindeutig. Einzelne Tabellenzeilen sind vorausgewählt; alle lassen
  sich mit einem Klick auswählen. Eine leere Auswahl kann nicht starten.
- Kein Dateidialog wird für die Rettung geöffnet; Abbruch ohne Auswahl bzw.
  ohne Kandidaten startet keine Analyse.
- Normale Konvertierungen überspringen bereits erkannte beschädigte Quellen.
- Entfernen, erneutes Prüfen und erfolgreiche Rettung aktualisieren Auswahl
  und Button-Zähler. Fehlgeschlagene Versuche bleiben erneut verfügbar.
- Quellen, die seit der Schadenserkennung verändert wurden, werden abgewiesen.
  Eine nicht mehr vorhandene DTS-Spur führt ebenfalls zu einer Dateimeldung.
- Analyse- und Rettungsfehler einer Datei verhindern die folgenden Versuche
  nicht. Der Bericht enthält Ergebnisse und Fehler aller betroffenen Dateien.
- Der gemeinsame Bestätigungsdialog zeigt Analysefehler als ausgeschlossene
  Dateien; vollständige Pfade und Zeitmarken stehen in den Details.
- Abbruch stoppt ausstehende Versuche und öffnet nach abgebrochener Analyse
  keine Verlustbestätigung. Schon fertig gemeldete Rettungen bleiben erhalten.
- Ein integrierter Test mit echten QThreads prüft Signale, Auswahl, Analyse,
  Bestätigung, gemischten Rettungserfolg, Tabellenstatus und Gesamtbericht.

## Medienintegrationstest mit zwei beschädigten MKVs

Ein kurzer FFV1-/DTS-Testfilm wird lokal erzeugt. Eine innere Cluster-Kennung
wird absichtlich zerstört; eine zweite Datei enthält dieselben beschädigten
Testdaten unter einem anderen Namen. Anschließend läuft der gesamte neue
GUI-Ablauf mit realen FFmpeg-/MKVToolNix-Aufrufen:

1. Beide Dateien werden eingelesen.
2. Die normale Konvertierung erkennt beide Schäden und bietet die Quellen im
   Rettungsdialog an.
3. Nach Auswahl und simulierter ausdrücklicher Bestätigung werden beide
   Dateien nacheinander erfolgreich gerettet und nach AC3 konvertiert.
4. Beide Ausgaben und eigene `*.recovery.json`-Berichte existieren. DTS ist in
   den Ausgaben nicht mehr vorhanden; die GUI meldet beide als gerettet und
   entfernt sie aus der Rettungsauswahl.
5. Die Original-Testdateien bleiben laut SHA-256 unverändert.

Der exportierbare Gesamtbericht enthält beide Rettungsergebnisse und unter
`analysis_report` die Ergebnisse der vorherigen Analyse. Die bestehenden
Tests für Paketdaten, Zeitstempel, Audio-Decodierung und Spurtitel bestehen.

Die neue Auswahl und das Hauptfenster wurden außerdem offscreen gerendert und
visuell auf lesbare Beschriftungen und überlappende Steuerelemente geprüft.
Es wurde kein erneuter mehrstündiger Lauf über die großen Original-Testdateien
ausgeführt. Die technischen Grenzen des Rettungsmodus bleiben unverändert;
auch eine erfolgreiche Rettung kann Bild-/Tonverluste enthalten.
