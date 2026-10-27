# Fehleranalyse und Fix 1.0.1 – 27. Oktober 2026

Die beiden Fehler haben unterschiedliche Ursachen: einen Fehler in der
Kapitelprüfung der Anwendung und zusätzlich eine nicht lesbare Containerstruktur
in der zweiten MKV.

| Beobachtung | Nachgewiesene Ursache | Änderung in 1.0.1 |
| --- | --- | --- |
| Beide Dateien: „chapters verändert“ | MKVToolNix ergänzt beim Kapitelimport `ChapLanguageIETF`. Die Prüfroutine kannte fälschlich `ChapterLanguageIETF`. | Richtigen Elementnamen berücksichtigen; bestehende Sprachwerte, Kapiteltexte, Zeiten und UIDs weiterhin prüfen. Abweichungen mit Elementpfad melden. |
| Zweite Datei: rund eine Stunde Laufzeit | Container-Strukturfehler ab Byteposition **8.144.052.744**. Laut altem Log wurde erst bei **10.111.450.665**, Filmzeit **02:12:15.302**, wieder ein Cluster gefunden. Drei Wiederherstellungssuchen dauerten zusammen **47 min 53 s**. | Beim ersten Struktur-/Resync-Hinweis sofort mit klarer Fehlermeldung abbrechen. |
| Eindruck wiederholter Konvertierung | Das Log enthält je einen FFmpeg-Encoderaufruf für die deutsche und englische DTS-Spur. Beide Vorbereitungen und der spätere Remux lasen die beschädigte Stelle erneut. | Alle DTS-Spuren gemeinsam mit einem Quelldurchlauf vorbereiten, danach jede Audiospur einmal konvertieren. |
| DTS-Fehlermeldungen bei Datei 2 | Unter anderem `Failed to decode block code(s)` und `Deficit samples are not supported`. Version 1.0.0 setzte trotz dieser Meldungen die Verarbeitung fort. | FFmpeg bei Decodierfehlern abbrechen lassen (`-xerror`, strenge Fehlererkennung). |
| Fortschrittsbalken springt zurück | Ungefilterte Werkzeug-Prozentwerte und Paketzeitstempel konnten bei Phasenwechseln und interleavten Spuren kleinere Werte liefern. | Fortschritt im Konvertierungskern und in der GUI auf den bisher erreichten Höchststand begrenzen. |
| Wichtige Warnungsursache schlecht sichtbar | Die alte Warnungszusammenfassung zeigte nur die letzten 30 Ausgabelinien, häufig Fortschrittsmeldungen. | Warnungen sofort anzeigen; Werkzeugaufrufe mit Startzeit und Laufzeit protokollieren. |

Die Terminalmeldung über einen unbekannten **Attachment**-Codec betrifft einen
Dateianhang. Sie belegt für sich keinen Fehler der Audio-Konvertierung. Die
Struktur- und DTS-Decodierfehler in `gui.log` sind dagegen für Datei 2 relevant.
Die Bezeichnung `#GUI#warning` ist das Nachrichtenformat von MKVToolNix und kein
Hinweis auf einen Defekt der Qt-Oberfläche.

Die ursprünglichen MKVs wurden ausschließlich gelesen. Der Fix kann fehlende
oder beschädigte Container-/Audiodaten nicht wiederherstellen. Für die zweite
Datei wird eine intakte Quelle bzw. eine separat geprüfte Reparatur benötigt.

## Aktualisieren

Anwendung schließen. Das Archiv **MKV-Audio-Converter-1.0.1.zip** in einen neuen
Ordner entpacken und dort mit `bash start.sh` starten. Alternativ die enthaltenen
Projektdateien in den bisherigen Projektordner kopieren. Der eigene Ordner
`Test_01` ist kein Bestandteil des Updates und muss nicht ersetzt werden.

Ein bestehender KDE-Menüeintrag zeigt weiterhin auf seinen bisherigen Pfad.
Wenn der neue Projektordner verwendet wird, dort `bash install-desktop.sh`
ausführen, um den Menüeintrag auf den neuen Pfad umzustellen.

Details zu den Tests und zum Probelauf mit den bereitgestellten Dateien stehen
in [TESTBERICHT.md](TESTBERICHT.md).

Die automatische Ergänzung der Kapitel-Sprachfelder ist auch in der offiziellen
[MKVToolNix-Dokumentation zur Sprachbehandlung](https://mkvtoolnix.download/doc/mkvmerge.html#mkvmerge.language_handling)
beschrieben. Die konkrete Ursache wurde zusätzlich mit den Kapiteldaten beider
Originaldateien und einem echten Import-/Export-Durchlauf reproduziert.
