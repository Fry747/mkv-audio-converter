# Öffentliche Freigabe

## Repository öffentlich stellen

Öffentlicher Quellcode und öffentliche Binärpakete sind zwei getrennte Schritte.
Für Downloads ohne GitHub-Anmeldung Release-Assets verwenden; Actions-Artefakte
bleiben an die GitHub-Anmeldung und ihre Aufbewahrungsfrist gebunden.

Vor dem Sichtbarkeitswechsel:

- Aktuellen Baum **und die gesamte Git-Historie** auf Zugangsdaten, private
  Medien, private Pfade und ungewollte Identitätsangaben prüfen. Commit-Autoren
  und ihre E-Mail-Adressen werden ebenfalls öffentlich. Verschieben oder
  Löschen einer Datei entfernt frühere Fassungen nicht aus Git.
- Vorhandene alte Actions-Artefakte/-Logs prüfen. Alte Windows-Binärartefakte
  vor dem Sichtbarkeitswechsel löschen oder ablaufen lassen. Der bisherige Windows-Build
  enthielt unbenötigte Qt-Addons und ist nicht das zur Veröffentlichung
  vorgesehene Paket. Nur den neuen geprüften Build als Release-Asset anbieten.
- In GitHub **Private vulnerability reporting**, Dependency Graph und verfügbare
  Secret-Scanning-/Push-Protection-Funktionen einschalten. Sichtbarkeit nicht
  über einen Commit, sondern separat in den Repository-Einstellungen ändern.

Die lokale Prüfung fand keine privaten MKV-/Audio-Binaries oder typischen
Zugangsdaten im versionierten Baum bzw. seinen Textrevisionen. Das ist ein
begrenzter technischer Scan, keine Garantie für alle Arten vertraulicher Daten.
Die bestehenden Commit-Autorinformationen bleiben erhalten; es wurde keine
Historie umgeschrieben. Persönliche Testmedien liegen außerhalb des Repos.

## Version 1.3.0 veröffentlichen

1. Änderungen reviewen, committen und pushen. Der aktuelle praktische und native
   Windows-Prüfstand ist in [testing/README.md](testing/README.md) dokumentiert.
2. Den finalen Commit mit dem annotierten Tag `v1.3.0` markieren und den Tag
   pushen. Er startet den vollständigen Windows-Build einschließlich Tests,
   EXE-/Installerprüfungen, Icon- und Komponentenprüfung.
3. Nach Erfolg bereitet der nachgelagerte Job `release-draft` einen Entwurf vor.
   Er übernimmt ausschließlich die fünf Dateien aus demselben Workflow-Lauf:
   - `MKVAudioConverter-1.3.0-windows-x64-setup.exe`
   - `MKVAudioConverter-1.3.0-windows-x64-portable.zip`
   - `MKVAudioConverter-1.3.0-source.zip`
   - `MKVAudioConverter-1.3.0-third-party-sources.zip`
   - `SHA256SUMS.txt`
4. Die Kontrolle verlangt exakt diese fünf Dateien, vier gültige SHA-256-Werte,
   intakte ZIPs, Projektquellen passend zum Tag sowie die gepinnten LGPL-Quellen.
   Nach dem Upload werden alle fünf Dateien erneut heruntergeladen, nochmals
   geprüft und byteweise mit dem Build verglichen. Der konkrete Lauf und Commit
   werden den [Release-Notizen](releases/v1.3.0.md) angefügt.
5. Der Job entfernt nach erfolgreicher Überprüfung ausschließlich das bekannte
   veraltete Windows-Binärartefakt `12735821690` aus Lauf `40507148245`, falls
   es noch vorhanden ist. Testprotokolle und der bestätigte neuere Build bleiben
   erhalten. Alte Actions-Logs separat vor dem Sichtbarkeitswechsel prüfen.
6. Unter Repository-Einstellungen → General → Danger Zone → Change visibility
   das Repository öffentlich schalten. Die bestehenden Commit-Autorinformationen
   werden mit veröffentlicht. Der Workflow hat keine Administrationsberechtigung
   und kann die Sichtbarkeit nicht selbst ändern.
7. Den vollständig geprüften Entwurf unter Releases öffnen und **Publish release**
   wählen; Version 1.3.0 als aktuelle stabile Version anbieten. Den öffentlichen
   Download im abgemeldeten Browser prüfen.

Der Build und die lokale Tag-Erstellung veröffentlichen keinen Release automatisch.
Der Entwurfsjob erhält nur die dafür erforderlichen Contents-/Actions-Rechte;
der Windows-Build behält Lesezugriff. Eine Wiederholung überschreibt bestehende
Release-Dateien nicht stillschweigend. Bei einem abgebrochenen Upload den Entwurf
prüfen und die fehlenden Dateien aus demselben Lauf ergänzen. Veröffentlichte
Pakete nicht still austauschen; Korrekturen erhalten eine neue Version.

Das automatische GitHub-Quellarchiv ersetzt die Qt-/PySide6-Quellbeigabe nicht.

## Lizenzen

[THIRD_PARTY.md](../THIRD_PARTY.md) beschreibt gebündelte und separat geladene
Komponenten, Quellen und den Bibliotheksaustausch. Der Build ist auf die
geprüften Versionen festgelegt. Änderungen an Qt, Python, OpenSSL oder anderen
Runtime-Komponenten erfordern eine erneute Prüfung der konkreten Binärinhalte,
Lizenztexte und korrespondierenden Quellen. Die Veröffentlichung des Codes
unter MIT ersetzt diese Pflichten nicht.

Codecpatente, Marken und Nutzungsrechte an Medien sind durch diese technische
Prüfung nicht weltweit abschließend geklärt. Es wird keine rechtliche Freigabe
oder Zusage vollständiger Rechtssicherheit behauptet.
