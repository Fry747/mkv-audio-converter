# Rettungsmodus – Version 1.1.0

Der neue Modus kann eine **konvertierbare Rettungskopie** aus noch lesbaren
Daten einer beschädigten MKV erzeugen. Er rekonstruiert keine verlorenen Bilder
oder Töne. Seine Ausgabe kann Aussetzer, Standbilder, Stille oder fehlende
Inhalte enthalten und ist immer als **gerettet mit möglichen Verlusten**
gekennzeichnet.

## Bedienung

1. Datei in der Tabelle auswählen und **„Beschädigte Datei retten …“** anklicken.
   Ohne ausgewählte Zeile öffnet sich eine Dateiauswahl.
2. Die Anwendung untersucht die Datei ausschließlich lesend. Die Analyse zeigt
   die auszulassenden Bereiche und ihre ungefähren Zeitmarken an.
3. Die Rettung beginnt erst nach dem ausdrücklichen Klick auf
   **„Rettung und AC3-Konvertierung starten“**. „Abbrechen“ ist vorausgewählt.
4. Die Ausgabe heißt beispielsweise `Film_recovered_ac3.mkv`. Daneben entsteht
   automatisch `Film_recovered_ac3.recovery.json` mit dem Verlust-/Prüfbericht.
   Namenskollisionen erhalten fortlaufende Nummern; Dateien werden nicht ersetzt.
5. Die GUI meldet **„Gerettet · mögliche Bild-/Tonlücken“**. Die genannten
   Prüfstellen sollten anschließend in einem Player angesehen und angehört werden.

Die normale Schaltfläche **„Konvertieren“** arbeitet weiterhin streng und
bricht bei beschädigten Quellen ab. Der Rettungsmodus ist ein eigener,
ausdrücklich gewählter Arbeitsablauf für einzelne MKVs mit DTS-Audio.

## Was gerettet wird

Matroska speichert Medien in Clustern mit eigenen Zeitmarken. Bei einer
beschädigten Größenangabe kann ein normaler Demuxer sehr viel mehr Daten
überspringen, als tatsächlich unlesbar sind. Deshalb untersucht die neue
Funktion die Cluster einzeln:

- Elementgrenzen und bekannte Cluster-Unterelements werden geprüft.
- Tracknummern, BlockGroup-Struktur und Lacing-Framegrößen müssen plausibel sein.
- Ein vorhandener Cluster-CRC-32 wird geprüft. Cluster mit falscher Prüfsumme
  werden ausgelassen. Fehlende CRCs sind ausdrücklich kein Integritätsnachweis.
- Nach einer defekten Stelle wird nach einem vollständig strukturell lesbaren
  Cluster gesucht. Eine bloße Fundstelle der vier Cluster-Kennbytes genügt nicht.
- Nur akzeptierte ganze Cluster werden kopiert. Ein innerhalb eines Clusters
  defektes Element führt zum Ausschluss des gesamten Clusters.
- Die Originalzeitstempel bleiben erhalten. Ausgelassene Abschnitte werden
  **nicht zeitlich zusammengeschoben**. Alle Spuren benutzen denselben
  Rettungskandidaten, damit Audio und Video dieselbe verbleibende Zeitachse haben.
- EBML-, Info-, Tracks-, Kapitel-, Tag- und Anhangsdaten werden übernommen,
  sofern sie vorhanden und lesbar sind. Alte Suchindex-/Positionsdaten werden
  verworfen; MKVToolNix schreibt beim finalen Remux neue Indizes.

Jeder übernommene Datenbereich erhält bei der Analyse SHA-256. Beim Kopieren
muss die Prüfsumme weiterhin stimmen. Änderungen der Quelldatei führen zum
Abbruch. Die Originaldatei wird nur mit Leserechten geöffnet.

## Audio-Konvertierung und Prüfung

Die DTS-Spuren des Rettungskandidaten werden gemeinsam mit MKVToolNix
bereitgestellt und nach AC3 konvertiert. Nur in diesem expliziten Modus darf
FFmpeg fehlerhafte Audiopakete überspringen (`ignore_err`). Der bestehende
zeitbasierte Resampler kann entstandene Tonlücken mit Stille ausgleichen.
Unheilbare Decodierfehler können trotzdem zum Abbruch führen.

Die erzeugten AC3-Spuren werden vollständig streng decodiert. Metadaten,
Sprachen, Titel, Flags und Kapitel bleiben geprüft. Die gründliche Prüfung
kopierter Video-/Untertitelpakete und ihrer Zeitstempel ist im Rettungsmodus
obligatorisch. Ihr Bezug ist der **strukturell geprüfte Rettungskandidat**,
nicht die vollständige ursprüngliche Filmdatei. Dass dort Inhalte ausgelassen
wurden, wird dadurch nicht rückgängig gemacht.

Der Bericht enthält:

- Originalgröße und Dateisignatur; übernommene Cluster und strukturelle Frame-Einträge.
- Ausgelassene Bytebereiche mit Grund und ungefähren benachbarten Cluster-Zeitmarken.
- Zahl der mittels CRC geprüften Cluster.
- Werkzeugwarnungen und Zähler bestimmter Decoder-Fehlermeldungen. Diese Zähler
  sind **keine Anzahl verlorener Frames** und ergeben keine exakte Verlustdauer.
- Prüfungen der erzeugten Datei sowie `completeness: NOT_CONFIRMED` und
  `kind: SALVAGED_WITH_POSSIBLE_LOSS`.

Das Video wird nicht neu codiert. Eine vollständige Videodecodierung und die
Rekonstruktion von Referenzbildern nach beschädigten Abschnitten gehören nicht
zu dieser Version. Auch ein strukturell korrekter Cluster kann ohne passende
CRC noch beschädigte Codec-Nutzdaten enthalten. Deshalb ist der Wiedergabetest
an den aufgeführten Stellen erforderlich, bevor die Kopie als brauchbar gilt.

## Konkrete Testdatei TEST_MKV_02.mkv

Der alte MKVToolNix-Wiederherstellungslauf übersprang den Bereich ab etwa
Byte 8.144.052.744 bis 10.111.450.665. Die neue Untersuchung findet dort über
tausend strukturell lesbare Cluster. Über die gesamte Datei werden **14.520
Cluster akzeptiert** und **sieben Bereiche mit zusammen 480.226.340 Bytes**
ausgeschlossen. Auch diese Bytezahl ist keine exakte Film-Verlustdauer.

Die Datei enthält keine Cluster-CRCs; die Nutzdaten sind dadurch nicht als
fehlerfrei bewiesen. Der reale vollständige Probelauf und seine Prüfergebnisse
werden separat in [TESTBERICHT-1.1.0.md](TESTBERICHT-1.1.0.md) dokumentiert.

## CLI

Nur analysieren:

```bash
bash start.sh --analyze-repair "/Pfad/Film.mkv"
```

Nach bewusster Akzeptanz möglicher Bild-/Tonverluste retten und konvertieren:

```bash
bash start.sh --recover --accept-loss --output-dir "/Pfad/Ziel" "/Pfad/Film.mkv"
```

Die CLI benötigt genau eine Datei. Rückgabecode **3** bedeutet: eine gerettete
Datei mit möglichen Verlusten wurde erstellt. **0** bleibt dem erfolgreichen
normalen Lauf bzw. der reinen Analyse vorbehalten, **1** bezeichnet Fehler oder
Abbruch, **2** unzulässige Argumente. `--recover` ohne `--accept-loss` startet
keine Rettung.

## Grenzen und Speicherplatz

Diese Version setzt einen lesbaren EBML-/Info-/Tracks-Kopf und ein einzelnes
Matroska-Segment voraus. Unbekannt große Cluster, sehr große Cluster über
64 MiB, abgeschnittene deklarierte Segmente, externe Segmentverknüpfungen und
zerstörte Codec-Header sind keine zugesicherten Rettungsfälle. Aus intakten
Metadaten kann die Anwendung verlorene Mediennutzdaten nicht ableiten.

Für Arbeitsdateien sollten ungefähr dreimal die Originalgröße plus 1 GiB
frei sein. Das Ziel muss Hardlinks unterstützen (z. B. Btrfs/ext4); das wird vor
dem langen Kopierlauf geprüft. Abbruch und Fehler entfernen die temporären
Kopien. Veröffentlichte Ausgabe und Bericht werden exklusiv unter neuen Namen
angelegt. Nach Stromausfall können wie bisher versteckte Arbeitsordner bleiben.

## Technische Grundlagen

- [Matroska: Cluster, Timestamp und SimpleBlock](https://www.matroska.org/technical/elements.html)
- [EBML: CRC-32, Grenzen und Umgang mit beschädigten Elementen](https://www.rfc-editor.org/rfc/rfc8794.html#section-11.3.1)
- [FFmpeg: err_detect und ignore_err](https://ffmpeg.org/ffmpeg-all.html)

Die Standards beschreiben den Container und die Fehlerbehandlung. Sie garantieren
keine vollständige Wiederherstellung einer konkreten beschädigten Datei.
