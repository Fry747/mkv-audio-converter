# Verarbeitung und Ergebnisprüfung

## Was intern passiert

1. `mkvmerge -J` liest die Matroska-Spuren ein. Es werden echte MKVToolNix-IDs
   verwendet, keine angenommenen FFmpeg-Streamnummern.
2. Alle DTS-Spuren werden mit einem einzigen MKVToolNix-Durchlauf gemeinsam in
   einer temporären MKA bereitgestellt. Ihre Reihenfolge wird ausdrücklich
   festgelegt. Die große Quelldatei wird dadurch für diesen Schritt einmal
   gelesen. Video wird dabei nicht übernommen.
3. FFmpeg decodiert jede ausgewählte Audiospur genau einmal und erzeugt je eine AC3-MKA.
   `-copyts` erhält den Zeitbezug; es gibt kein `-start_at_zero`. Die MKA enthält
   auch die von FFmpeg gesetzte AC3-Encoderverzögerung (`CodecDelay`).
   `aresample=async=1` gleicht Tonlücken anhand der Zeitstempel mit Stille aus,
   statt nach einer Lücke dauerhaft asynchron zu werden.
4. `mkvmerge` übernimmt alle übrigen Spuren direkt aus dem Original. Ein
   explizites `--track-order` setzt jede neue AC3-Spur an die Position ihrer
   DTS-Vorgängerspur. **FFmpeg schreibt niemals das Video. Kein Video-Reencoding.**
5. `mkvpropedit` stellt auf der temporären Ausgabe ursprüngliche Track-UIDs,
   Sprachen und Flags wieder her. Spurtitel konvertierter DTS-Spuren werden
   wie unten beschrieben angepasst. Kapitel und Tags werden separat als
   XML übernommen, damit UID-Verweise auch bei automatischer UID-Neuvergabe
   durch MKVToolNix korrekt bleiben. Kapitel-Spurnummern werden bei Bedarf
   auf die entsprechende Ausgabespur abgebildet.
6. Erst nach der Ergebnisprüfung wird die vollständige Datei unter ihrem
   endgültigen Namen sichtbar.

Erhalten bleiben Spurreihenfolge, Video, nicht konvertierte Audiospuren,
Untertitel, Anhänge, Kapitel, Filmtitel, beschreibende Tags, Track-UIDs,
ISO- und IETF-Sprachen sowie Default-, Forced- und Enabled-Flags.
Vorhandene Commentary-, Original-, Hearing-impaired-, Visual-impaired- und
Text-description-Flags werden ebenfalls übernommen.

### Spurtitel automatisch anpassen

Bei konvertierten DTS-Tonspuren werden eigenständige DTS-Bezeichnungen im
Spurtitel durch **AC3** ersetzt, unabhängig von Groß-/Kleinschreibung.
Erkannt werden unter anderem DTS, DTS-ES (auch Discrete/Matrix), DTS-HD,
DTS-HD MA/Master Audio, DTS-HD HR/HRA/High Resolution Audio, DTS:X, DTS 96/24,
DTS Express und DTS Core. Leerzeichen, Punkte, Bindestriche und Unterstriche
als Trenner werden unterstützt.

Sprachen, Kommentare und sonstiger Text bleiben erhalten. Eine direkt auf
den Codec folgende Kanalangabe wird beim Downmix von mehr als sechs Kanälen
auf **5.1** angepasst. Sonst bleibt die vorhandene Kanalangabe erhalten; aus
der bloßen Kanalzahl wird keine neue Anordnung geraten. Beispiele:

| Ursprünglicher Titel | Neuer Titel |
| --- | --- |
| `DTS-ES.6.1.Warner.Fixed.x264-Xell` (7 Kanäle) | `AC3.5.1.Warner.Fixed.x264-Xell` |
| `English DTS-ES 6.1` (7 Kanäle) | `English AC3 5.1` |
| `Deutsch DTS-HD MA 5.1 (Kommentar)` | `Deutsch AC3 5.1 (Kommentar)` |
| `English` oder leerer Titel | unverändert |

Dies gilt automatisch für GUI, CLI und Rettungsmodus. Jede Änderung erscheint
im Protokoll und im JSON-Prüfbericht mit altem und neuem Titel. Die
Ergebnisprüfung vergleicht den tatsächlichen Titel mit dem erwarteten neuen
Titel. Nicht konvertierte Spuren und Titel ohne erkennbare DTS-Bezeichnung
bleiben unverändert. Bereits erzeugte MKVs werden nicht nachträglich geändert;
die Originaldatei muss für angepasste Titel erneut konvertiert werden.

### Weitere Metadaten

Veraltete technische DTS-Tags wie BPS/DURATION/ENCODER und
Track-Statistiken der ersetzten Spuren werden entfernt. MKVToolNix darf
ergänzende, aus vorhandenen Sprachangaben abgeleitete IETF-Felder in Kapitel-
und Tag-XML hinzufügen. Containerdatum, Muxerkennung und Segment-UID können sich
durch das Remuxen ändern.

Die relevanten Verhaltensweisen sind in der offiziellen Dokumentation erklärt:
[MKVToolNix: Track-Auswahl, Reihenfolge und Flags](https://mkvtoolnix.download/doc/mkvmerge.html),
[mkvextract](https://mkvtoolnix.download/doc/mkvextract.html),
[FFmpeg: Zeitstempel](https://ffmpeg.org/ffmpeg.html),
[FFmpeg: Audio-Resampling](https://ffmpeg.org/ffmpeg-filters.html#aresample).

## Ergebnisprüfung und Grenzen

Die Prüfung ist obligatorisch und umfasst:

- Spurenanzahl, Reihenfolge, erwartete Codecs, 48-kHz-AC3-Kanalzahlen, UIDs,
  Sprachen, Titel und Flags.
- Kapitel- und Tag-XML sowie Anhang-Metadaten.
- Vollständiges Lesen der Paketzeitstempel beider Dateien, damit auch sehr spät
  beginnende Tonspuren geprüft werden. AC3-Anfang: höchstens 3 ms Abweichung;
  AC3-Ende: höchstens 80 ms wegen Framegröße/Endpadding. Bei verfügbaren
  MKVToolNix-Anfangswerten gilt zusätzlich eine Toleranz von 2 ms.
- Vollständiges Decodieren jeder neu erzeugten AC3-Spur mit Fehlerabbruch.
- Standardmäßig SHA-256-Vergleich der Pakete aller kopierten Spuren sowie
  Vergleich ihrer PTS mit höchstens 2 ms Rundungstoleranz. Zeitstempelreferenzen
  liegen auf der Platte; auch lange Filme benötigen dafür keinen großen RAM.
  Die Inhalte der Anhänge werden ebenfalls mit SHA-256 verglichen.

„Kopierte Spuren gründlich prüfen“ kann abgeschaltet werden. Die übrigen
Prüfungen einschließlich Audio-Decodierung und Start-/Endvergleich bleiben
aktiv. Die Zusatzprüfung benötigt zusätzliche Lesezeit. Ein Fortschrittsbalken
gewichtet Vorbereitung/Audio, Remux und Prüfung; er ist keine genaue Restzeit.
Innerhalb eines Durchlaufs steigt er ausschließlich oder bleibt stehen. Im
Protokoll stehen Startzeit und Laufzeit jedes Werkzeugaufrufs. MKVToolNix-
Warnungen werden sofort als Text angezeigt, auch wenn daneben Fortschritt
gemeldet wird.

AC3 ist eine verlustbehaftete Umwandlung; DTS-HD-/Objektinformationen werden
nicht erhalten. Exotische Kanalanordnungen, beschädigte Zeitstempel oder vom
installierten FFmpeg nicht unterstützte DTS-Varianten können zu einem
Fehlerstatus führen. Dann entsteht keine fertige Ausgabe. Tonlücken können
Stille erzeugen; die Anwendung repariert keine bereits falsch synchronisierte
Quelle. Ein erfolgreicher Container-/Datencheck ersetzt keinen Wiedergabetest
auf dem konkreten Fernseher.

Im normalen Konvertierungsmodus wird bei einer MKVToolNix-Warnung über eine beschädigte EBML-Struktur bzw. eine
Wiederherstellungssuche (`Resyncing`) der Auftrag sofort abgebrochen. Auch echte
FFmpeg-Decodierfehler brechen die Audio-Konvertierung ab (`-xerror`). Dadurch
entsteht aus einer defekten Quelle keine vermeintlich erfolgreich geprüfte
Datei mit übersprungenen Abschnitten. Eine solche Quelle separat reparieren
oder durch eine intakte Kopie ersetzen und anschließend erneut verarbeiten.

Die Anwendung ist für einzelne, normale MKV-Filmdateien ausgelegt. Bei extern
verknüpften Segmenten/Ordered-Chapter-Sammlungen können Verweise auf andere
Dateien außerhalb dieses Auftrags liegen; solche Sammlungen separat verwalten.

## Temporäre Dateien und Speicherplatz

Jede Quelle erhält einen privaten, automatisch entfernten Arbeitsordner im
Zielordner. So liegen temporäre und endgültige Ausgabe auf demselben Dateisystem.
Vor dem Start wird der freie Platz grob auf Originalgröße plus zweimal
geschätzte AC3-Größe und 256 MiB Reserve geprüft. Fehler wie ein volles Laufwerk
werden abgefangen. Die Quelle wird vor und nach dem Auftrag auf Änderungen
von Größe, Zeitstempel und Dateiidentität geprüft.

Die endgültige Veröffentlichung ersetzt keine vorhandenen Namen, auch wenn
sie während des Auftrags angelegt werden. **Unter Linux** nutzt sie exklusive
Hardlinks; dafür ein lokales Btrfs-/ext4-Ziel verwenden. exFAT/FAT und manche
Netzlaufwerke unterstützen diese Linux-Funktion nicht. **Unter Windows** nutzt
sie natives Umbenennen ohne Überschreiben, sodass lokale NTFS-/exFAT-Ziele
möglich sind. Fertige Dateien können auf USB-Datenträger kopiert werden. Der Ausgabename erscheint erst nach allen
Prüfungen. Die Daten werden davor auf den Datenträger geschrieben (`fsync`).

Bei normalem Fehler oder Abbruch wird aufgeräumt. Nach Stromausfall oder
`kill -9` kann ein versteckter Ordner `.mkv-audio-converter-*` übrig bleiben.
Nur wenn kein Auftrag mehr läuft, darf dieser Restordner manuell gelöscht
werden. Er wird beim Einlesen von Ordnern ignoriert. Originaldateien und
vorhandene Ausgaben dürfen dafür nicht gelöscht werden.
