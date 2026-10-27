# Bedienung

- **Dateien hinzufügen**: mehrere MKV-Dateien gemeinsam auswählen.
- **Ordner hinzufügen**: optional mit Unterordnern einlesen. Drag-and-drop von
  lokalen Dateien und Ordnern funktioniert ebenfalls.
- Die Tabelle zeigt die Zahl der DTS-Spuren und den Status. Die Tooltips
  enthalten vollständige Pfade und Details zu den Tonspuren. DTS-HD wird über
  die Matroska-Codec-ID `A_DTS` ebenfalls erkannt.
- **Einträge entfernen**: Rechtsklick auf eine Zeile → **Aus Liste entfernen**.
  Mehrere Zeilen mit Strg/Umschalt markieren und gemeinsam entfernen; dafür
  funktionieren auch **Auswahl entfernen** und die **Entf-Taste** bei Fokus in
  der Tabelle. Rechtsklick auf eine andere, nicht markierte Zeile wählt nur
  diese Zeile aus; innerhalb einer Mehrfachauswahl bleibt die Auswahl erhalten.
  Originaldateien und fertige Ausgaben bleiben auf der Platte erhalten. Auch
  bereits fertig konvertierte oder beschädigte Einträge lassen sich entfernen.
  Während Einlesen, Konvertierung oder Rettung ist Entfernen für die gesamte
  Liste gesperrt. Ohne Auswahl ist die Schaltfläche deaktiviert. Rechtsklick
  auf den leeren Tabellenbereich entfernt nichts. Protokolle und vorhandene
  Prüfberichte bleiben als Verlauf erhalten.
- **Zielordner** leer lassen, um neben jeder Quelldatei zu speichern, oder einen
  gemeinsamen Zielordner wählen. Die Eingabe wird beim nächsten Start übernommen.
- Standard: **AC3, 448 kbit/s, 48 kHz**. Alternativ 384 oder 640 kbit/s.
  640 kbit/s vor Verwendung am eigenen TV testen.
- AC3 unterstützt höchstens 5.1. Spuren mit mehr als sechs Kanälen werden bei
  aktivierter Option auf 5.1 heruntergemischt. Ohne diese Option erhält die
  betreffende Datei einen Fehlerstatus. Kleinere Kanalzahlen bleiben erhalten.
- **Konvertieren** startet die Warteschlange. Sie wird nacheinander abgearbeitet,
  damit große Videodateien den Datenträger nicht durch parallele Remux-Vorgänge
  überlasten. Dateien ohne DTS werden übersprungen.
- **Beschädigte Dateien retten (N) …** ist verfügbar, sobald die Konvertierung
  Quellschäden erkannt hat. Die Auswahl enthält ausschließlich diese Dateien
  aus der aktuellen Liste, mit vollständigen Pfaden und Fehlergründen. Einzelne
  Einträge anhaken oder **Alle auswählen** verwenden. Ausgewählte beschädigte
  Tabellenzeilen sind vorausgewählt; sonst alle verfügbaren beschädigten Dateien.
  Ein Dateidialog wird dabei nicht geöffnet. Die Analyse läuft zunächst nur
  lesend. Danach werden die Schadstellen je Datei in einer gemeinsamen
  Verlustbestätigung angezeigt. Erst die ausdrückliche Bestätigung startet
  Rettung und AC3-Konvertierung für die erfolgreich analysierten Dateien.
  Details und Grenzen: [RETTUNGSMODUS.md](recovery.md).
- Erkannte beschädigte Dateien werden bei weiteren normalen Konvertierungen
  ausgelassen. Ein Rettungsfehler stoppt die übrigen ausgewählten Dateien nicht.
  Erfolgreich gerettete Einträge verschwinden aus der Rettungsauswahl;
  fehlgeschlagene oder abgebrochene bleiben erneut auswählbar. Speicherplatz-,
  Werkzeug- und sonstige allgemeine Fehler gelten nicht als erkannter Quellschaden.
- **Abbrechen** beendet die aktuellen Werkzeuge und entfernt die unvollständige
  Ausgabe. Bereits fertiggestellte Dateien bleiben erhalten. Beim Schließen
  während eines Auftrags wird zuerst abgebrochen; anschließend kann das Fenster
  geschlossen werden.
- Das Protokoll zeigt die ausgeführten Befehle und Meldungen. Die letzten 4.000
  Zeilen lassen sich speichern; der JSON-Prüfbericht enthält Ergebnisse,
  Fehler, Werkzeugversionen, Optionen und die ausgeführten Prüfungen je Datei.
- Ein Doppelklick auf eine fertige Zeile öffnet ihren Ausgabeordner.
- **Erneut prüfen** liest die Quellen erneut ein und ermöglicht einen weiteren
  Durchlauf, etwa mit einer anderen Bitrate. Dabei werden auch die bisherigen
  Schadensmarkierungen zurückgesetzt; dies repariert keine Quelle. Fertige
  Dateien werden innerhalb derselben Warteschlange sonst nicht erneut verarbeitet.

Aus `Film.mkv` wird `Film_ac3.mkv`. Existiert der Name bereits, folgen
`Film_ac3_2.mkv`, `Film_ac3_3.mkv` usw. Das gilt auch bei gleichen Quelldateinamen
aus unterschiedlichen Ordnern. Vorhandene Dateien werden niemals ersetzt.
