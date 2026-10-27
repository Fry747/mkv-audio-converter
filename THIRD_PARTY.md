# Drittanbieter und Windows-Pakete

Der Anwendungscode steht unter MIT, siehe LICENSE. Unveränderte
Drittanbieterbestandteile behalten ihre eigenen Lizenzen.

Der Windows-Build enthält CPython, PySide6/Qt und die benötigten Laufzeitbibliotheken.
Das Buildskript sammelt die Lizenz-, Copyright- und Notice-Dateien der
Buildumgebung unter `licenses/` und protokolliert die genauen Paketversionen in
`build-dependencies.json`. PyInstaller wird mit seiner Bootloader-Ausnahme
verwendet. Die Anwendung wird als Ordnerpaket verteilt; Qt-DLLs werden nicht
in eine undurchsichtige Onefile-EXE eingeschlossen und können ersetzt werden.

PySide6/Qt ist u. a. unter LGPLv3 verfügbar. Lizenztexte, Hinweise, die genaue
Version und der Zugang zum korrespondierenden Quellcode müssen mit einer
veröffentlichten Binärdistribution erhalten bleiben. Eine kommerzielle
Qt-Lizenz ist eine alternative Lizenzierung, wird hier aber nicht vorausgesetzt.
Das Anwendungsquellpaket wird neben Installer und ZIP erzeugt. Für die
unveränderten Bibliotheken stehen die offiziellen Quellarchive zur Verfügung:

- [CPython Quellcode und Lizenzen](https://www.python.org/downloads/source/)
- [PySide/Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/)
- [Qt-Quellarchive](https://download.qt.io/archive/qt/)
- [PySide6 Lizenzangaben](https://pypi.org/project/PySide6/)
- [PyInstaller Lizenz und Bootloader-Ausnahme](https://pyinstaller.org/en/stable/license.html)

FFmpeg und MKVToolNix werden **nicht als Binaries mit unserem Installer oder
unserer ZIP weiterverteilt**. Der Einrichtungsassistent lädt die unveränderten,
versionierten Originalarchive unmittelbar von den angegebenen Anbietern und
belässt deren Lizenz-/Dokumentationsdateien in den entpackten Ordnern.
Die Werkzeuge laufen als separate Prozesse. Bezugsquellen und Prüfsummen sind
in `mkv_audio_converter/windows_tools.py` festgelegt und im Downloadbeleg
`download-receipt.json` dokumentiert.

- [FFmpeg Downloads](https://ffmpeg.org/download.html)
- [Gyan Windows-Builds](https://www.gyan.dev/ffmpeg/builds/)
- [FFmpeg Lizenzinformationen](https://ffmpeg.org/legal.html)
- [MKVToolNix Downloads und Prüfsummen](https://mkvtoolnix.download/downloads.html#windows)
- [MKVToolNix Quellen](https://mkvtoolnix.download/source.html)

Wer eigene Komplettpakete mit diesen Werkzeugen weiterverteilen möchte, muss
zusätzlich die jeweiligen Bedingungen für diese konkrete Binärdistribution,
einschließlich korrespondierendem Quellcode und enthaltenen Bibliotheken,
erfüllen. Der Erststart-Download vermeidet diese zusätzliche Bündelung.

Inno Setup wird nur zum Erstellen des Installers benötigt. Die jeweils aktuellen
Bedingungen des Herstellers für die Nutzung des Compilers gelten unabhängig
von der MIT-Lizenz dieses Projekts:
[Inno Setup](https://jrsoftware.org/isinfo.php).
