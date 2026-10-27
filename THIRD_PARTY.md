# Drittanbieter, Lizenzen und Quellen

Die [MIT-Lizenz](LICENSE) gilt für den eigenen Anwendungscode, nicht pauschal
für sämtliche Dateien im Windows-Paket. Drittanbieter behalten ihre Lizenzen
und Copyright-Hinweise. Das Projekt steht in keiner Herausgeberbeziehung zu ihnen.

## Mit dem Windows-Paket verteilt

| Bestandteil | Lizenz / Behandlung |
| --- | --- |
| CPython 3.13.17 und enthaltene Standardbibliotheken | PSF und weitere Originallizenzen; vollständige Windows-`LICENSE.txt` wird übernommen |
| Qt Base 6.11.2, PySide6 Essentials und Shiboken 6.11.2 | LGPLv3, dynamische Bibliotheken; Originalquellen und Lizenztexte werden beigefügt |
| KDE-Breeze-Notensymbol | LGPLv3 oder neuer, © 2014 Uri Herrera und weitere Mitwirkende; SVG und Artwork-Klarstellung enthalten |
| OpenSSL 3.5.9 (Python-Laufzeit) | Apache-2.0; Original-Lizenz und Copyright-/README-Hinweise unter `LICENSES/` |
| Microsoft-C++-/Universal-CRT-Laufzeiten | Microsoft Distributable Code; Hinweise und Weitergabebedingungen in der übernommenen CPython-Windows-Lizenz |
| PyInstaller-Bootloader | GPLv2 mit Bootloader-Ausnahme; die Ausnahme erlaubt unabhängig lizenzierte Anwendungspakete |

Die Mitwirkenden von Qt/PySide6, Python und den jeweiligen Unterkomponenten
werden in deren Originalquellen und Lizenzdateien genannt. Die Auflistung ist
eine Orientierung; die unveränderten Originaltexte im Paket gelten.

Die PyInstaller-Sammlung ist auf Qt Base (Core/Gui/Widgets/Network) und benötigte
Base-Plugins begrenzt. Insbesondere werden **Qt Virtual Keyboard, Qt PDF,
QML/Quick und der Software-OpenGL-Renderer nicht mitgeliefert**. Ein Buildcheck
verweigert unerwartete Qt-Komponenten. Der bloße Einbau eines anderen Qt-Moduls
bedarf einer erneuten Prüfung; nicht alle Qt-Module sind LGPL-lizenziert.

## LGPL-Quellen und Austauschbarkeit

Zusammen mit Installer und Portable-ZIP wird auf derselben Release-Seite
`MKVAudioConverter-<Version>-third-party-sources.zip` bereitgestellt. Es enthält
die vollständigen, unveränderten und per SHA-256 geprüften Qt-Base- und
PySide-Setup-Quellarchive der verwendeten Version, einschließlich Shiboken.
`source-manifest.json` dokumentiert Herkunft und Prüfsummen. Das zusätzliche
`-source.zip` enthält Anwendungscode, SVG und vollständige Paketierungswerkzeuge.
Die zugehörigen Lizenz- und Attributionstexte werden in `licenses/` des
Programmpakets übernommen; bloße Links ersetzen diese Beigaben nicht.

Qt-/PySide6-DLLs bleiben als Dateien austauschbar. Es gibt keine Einschränkung
der Änderung und des Reverse Engineering zum Debuggen solcher Bibliotheksänderungen.
[Quellen und Austausch-Anleitung](docs/library-replacement.md).
**Beide Quellarchive gehören zu jedem öffentlichen Binärrelease.**

## Separat heruntergeladene Programme

FFmpeg und MKVToolNix sind **nicht im Installer oder Portable-ZIP enthalten**.
Nach ausdrücklichem Klick lädt der Assistent unveränderte Originalarchive von
den festgelegten Anbietern direkt zum Nutzer herunter. Originaldokumentation
und Lizenzdateien bleiben erhalten. Die Programme laufen als externe Prozesse;
die Anwendung bindet ihre Bibliotheken nicht ein.

- **FFmpeg 9.0.2 Essentials von Gyan:** GPL-Build; Lizenzumfang und enthaltene
  Bibliotheken richten sich nach genau diesem Build. FFmpeg ist nicht pauschal
  immer nur LGPL. [Builds und Quellen](https://www.gyan.dev/ffmpeg/builds/),
  [FFmpeg-Lizenzinformationen](https://ffmpeg.org/legal.html).
- **MKVToolNix 103.0:** GPLv2; maßgeblich sind die Lizenztexte des Originalarchivs.
  [Downloads](https://mkvtoolnix.download/downloads.html),
  [Quellcode](https://mkvtoolnix.download/source.html).

Downloadplan, Hersteller-URLs und SHA-256 stehen in
`mkv_audio_converter/windows_tools.py`; `download-receipt.json` dokumentiert
die Einrichtung. Wer diese Programme selbst mit einem Komplettpaket
weiterverteilt, muss zusätzlich deren konkrete Weitergabebedingungen erfüllen.
Eine öffentliche Kopie unseres Repositorys bündelt diese Programme nicht.

## Entwicklungswerkzeuge und Rechtsumfang

Inno Setup wird nur zum Erstellen des Installers verwendet; seine
[Nutzungsbedingungen](https://jrsoftware.org/isinfo.php) gelten zusätzlich für
die Verwendung des Compilers. Ein PyPI-Paket ist nicht allein deshalb Bestandteil
der Laufzeit, weil es auf dem Buildrechner installiert ist.

Softwarelizenzen regeln keine Rechte an den verarbeiteten Filmen und sind keine
pauschale Zusage zu Marken- oder Codecpatentrechten in jeder Rechtsordnung.
Diese technischen Maßnahmen und Quellenhinweise sind keine verbindliche
rechtliche Einzelfallprüfung.

## Maßgebliche Quellen

- [Qt: LGPL-Pflichten](https://www.qt.io/development/open-source-lgpl-obligations)
- [Qt Virtual Keyboard: kommerziell oder GPLv3](https://doc.qt.io/qt-6/qtvirtualkeyboard-index.html#licenses-and-attributions)
- [Qt-Base-Quellen](https://download.qt.io/archive/qt/6.11/6.11.2/submodules/)
- [Qt-for-Python-Quellen](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/)
- [KDE Breeze: Artwork-Lizenz](https://invent.kde.org/frameworks/breeze-icons/-/blob/master/COPYING-ICONS)
- [OpenSSL 3.5.9](https://github.com/openssl/openssl/tree/openssl-3.5.9)
- [PyInstaller-Ausnahme](https://pyinstaller.org/en/stable/license.html)
