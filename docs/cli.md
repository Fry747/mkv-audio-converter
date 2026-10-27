# Kommandozeile

```bash
bash start.sh --cli --output-dir "/Pfad/zum/Ziel" "/Pfad/zu/Filmen"
bash start.sh --cli --bitrate 640 --report bericht.json "Film.mkv"
bash start.sh --cli --no-recursive --no-downmix --quick "/Pfad/zu/Filmen"
```

Für beschädigte Einzeldateien stehen zusätzlich `--analyze-repair` und
`--recover --accept-loss` zur Verfügung. Eine erstellte Rettungskopie liefert
Rückgabecode **3** und immer einen Verlustbericht; siehe [Rettungsmodus](recovery.md).

Der Bericht darf noch nicht existieren. Rückgabecode 0: alle Dateien erfolgreich
verarbeitet oder ohne DTS übersprungen; 1: Fehler/Abbruch; 2: fehlerhafte
Argumente. Strg+C bricht sicher ab. Die reine CLI benötigt PySide6 nicht.
