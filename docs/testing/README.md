# Prüfstand 1.3.0

## Bestätigter Vorgängerstand

Am 27. Oktober 2026 bestand Commit `d53d7a9` den vollständigen
[Windows-Lauf 40507148245](https://github.com/Fry747/mkv-audio-converter/actions/runs/40507148245):

- 92 Tests erfolgreich in 32,515 Sekunden, keine Skips;
- Windows-Installer und Portable-ZIP erstellt;
- gebaute EXE: Version/Codecs, echte Unicode-DTS→AC3-Konvertierung, Metadaten,
  Quellhash und Qt-Start/-Ende erfolgreich;
- stille Installation, installierte CLI und Deinstallation geprüft;
  Test-Mediendatei und separater Werkzeugcache blieben erhalten.

Der Nutzer bestätigte am selben Tag einen praktischen Test auf **Windows 11**:
Erstinstallation, Bedienung, echte Medien, Fehlerfälle und Verteilung bestanden.
Ein bestimmter Windows-11-Build oder Dateisystemtyp wurde dabei nicht angegeben.
Windows 10 ist bisher nicht praktisch abgenommen.

## Änderungen vor der Veröffentlichung

- Fortschrittsbalken nach abgeschlossenem Abbruch auf 0 %, späte Meldungen ignoriert.
- Gemeinsames Breeze-Symbol mit SVG-Quelle, ICO-Ressourcen und Lizenzbeigaben.
- Öffentliche Dokumentation und historische Berichte in Unterverzeichnissen.
- Qt-Komponenten auf benötigten Umfang begrenzt; Quellen und Lizenztexte ergänzt.

Lokaler vollständiger Lauf auf Linux nach diesen Änderungen:

```text
Ran 98 tests in 66.699s
OK (skipped=2)
```

**96 erfolgreich, zwei native Windows-Tests lokal übersprungen.** Neue Tests
prüfen Abbruch-/Erfolgsfortschritt, unerwartete Qt-Komponenten, sichere
Lizenztextextraktion, Prüfsummenfehler und die Inhalte des Quellarchivs.
Die zwei Original-Quellarchive wurden wirklich heruntergeladen und mit den
Hersteller-SHA-256 verglichen; 196 Lizenz-/Attributionsdateien wurden durch
den neuen Collector verarbeitet. Das Quellen-ZIP ist 68.639.908 Bytes groß.
Ein lokales Python-Wheel wurde gebaut und auf Icons und Artwork-Lizenztexte
geprüft. Alle relativen Markdown-Links wurden geprüft.

Der Screenshot wurde mit dem aktuellen GUI-Code nach einer echten Konvertierung
synthetischer Beispieldaten erzeugt. Er zeigt Version 1.3.0 und enthält keine
privaten Medien. Die Windows-PE-Importtabellen der benötigten Qt-DLLs wurden
geprüft; die entfernten Qt-Addons sind keine deren notwendigen Qt-Abhängigkeiten.
Native CI und ein kurzer praktischer Nachtest der neuen Pakete stehen aus.
Der frühere Windows-Erfolg wird nicht als Test des geänderten Pakets ausgegeben.

## Historische Nachweise

Die [Archivberichte](archive/) dokumentieren frühere Versionen und Fehlersuchen.
Zeitangaben, Fehler und Aussagen zum damaligen Prüfstand sind historisch und
beschreiben nicht automatisch den aktuellen Stand. Die kleinen ursprünglichen
Testprotokolle und anonymisierten Messdaten bleiben unter `archive/logs/` und
`archive/evidence/` als Nachweise erhalten; sie enthalten keine Filmdateien.
Neue vollständige CI-Protokolle werden als Actions-Artefakte aufbewahrt und
nicht bei jedem Lauf zusätzlich ins Repository kopiert.

- [Erste Version / Kapitelkorrektur](archive/TESTBERICHT.md)
- [Rettungsmodus](archive/TESTBERICHT-1.1.0.md)
- [Spurtitel](archive/TESTBERICHT-1.1.1.md)
- [Rettungsauswahl](archive/TESTBERICHT-1.2.0.md)
- [Listeneinträge entfernen](archive/TESTBERICHT-1.2.1.md)
- [Windows-Implementierung und Fehlerkorrekturen](archive/TESTBERICHT-1.3.0.md)
