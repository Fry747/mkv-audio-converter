# Qt-/PySide6-Bibliotheken ersetzen

Die Windows-Anwendung verwendet dynamische Qt-/PySide6-/Shiboken-Bibliotheken
unter LGPLv3. Austausch, Änderung und Reverse Engineering zum Debuggen solcher
Änderungen werden durch dieses Projekt nicht eingeschränkt.

## Quellen und Bauinformationen

Bei jedem binären Release stehen unter derselben
[Release-Seite](https://github.com/Fry747/mkv-audio-converter/releases) bereit:

- `MKVAudioConverter-<Version>-source.zip`: Anwendung, Icons und Buildskripte;
- `MKVAudioConverter-<Version>-third-party-sources.zip`: unveränderte,
  versionsgleiche Qt-Base- und PySide-Setup-Quellarchive einschließlich Shiboken;
- `SHA256SUMS.txt`: Prüfsummen der veröffentlichten Archive und Programme.

Das Programmpaket enthält `source-manifest.json` mit Versionen, URLs und
geprüften SHA-256-Werten sowie `build-runtime.json` und `build-dependencies.json`.
Die Bibliotheken werden unverändert aus den offiziellen PyPI-Wheels übernommen.
Originale Buildskripte und Buildoptionen liegen im jeweiligen Quellarchiv.
Bauanleitungen: [Qt for Python](https://doc.qt.io/qtforpython-6/building_from_source/index.html)
und [Qt für Windows](https://doc.qt.io/qt-6/windows-building.html).

## Austausch im Ordnerpaket

1. Portable ZIP entpacken und eine Arbeitskopie davon anlegen. Anwendung beenden.
2. Mit den Quellen eine ABI-kompatible Version für dieselbe Python-/Qt-Version,
   x64-Architektur und kompatible Microsoft-C++-Laufzeit bauen. Beispielsweise
   Qt Base 6.11.2 mit eigenen Korrekturen statt einer anderen Hauptversion.
3. Die entsprechenden DLLs unter `_internal/PySide6/` bzw.
   `_internal/shiboken6/` und bei Bedarf die passenden Plugins und `.pyd`-Module
   durch die eigenen Dateien ersetzen. Zusammengehörige Bibliotheken gemeinsam ersetzen.
4. Mit `MKVAudioConverter-cli.exe --check` und anschließend der GUI prüfen.

Es gibt keine Anwendungssignaturprüfung oder Prüfsummensperre für diese
Bibliotheken. Die Downloadprüfsummen im Werkzeugassistenten betreffen nur die
separaten FFmpeg-/MKVToolNix-Downloads, nicht eigene Qt-Bibliotheken.
Bei inkompatiblen ABI-/Compileränderungen kann die Anwendung aus dem offenen
Quellcode mit der eigenen Bibliotheksversion neu gebaut werden;
siehe [Entwicklung](development.md). Lizenztexte unter `licenses/` bleiben erhalten.
