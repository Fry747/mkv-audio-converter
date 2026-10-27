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

1. Änderungen separat reviewen, committen und pushen. Version 1.3.0 bleibt bis
   zur Freigabe ungetaggt. `Run workflow` auf dem aktuellen `main` ausführen.
2. Native Tests ohne unerwartete Skips, EXE-/Installer-Tests, Icon-Ressourcen,
   Komponentenprüfung und Erzeugung der Lizenz-/Quellbeigaben müssen bestehen.
3. Den neuen Installer/ZIP kurz auf Windows 11 prüfen: Symbol im Explorer,
   Startmenü und Fenster; Abbruch bei teilweisem Fortschritt → nach Aufräumen
   0 %; erfolgreiche Konvertierung bleibt bei 100 %. Der bisherige praktische
   Test gilt für den Vorgängerstand und ersetzt diesen gezielten Nachtest nicht.
4. Release-Notizen und aktuellen Prüfstand fertigstellen, den geprüften
   Commit mit `v1.3.0` markieren und einen GitHub-Release erstellen.
5. **Zusammen aus demselben geprüften Build hochladen:**
   - `MKVAudioConverter-1.3.0-windows-x64-setup.exe`
   - `MKVAudioConverter-1.3.0-windows-x64-portable.zip`
   - `MKVAudioConverter-1.3.0-source.zip`
   - `MKVAudioConverter-1.3.0-third-party-sources.zip`
   - `SHA256SUMS.txt`
6. Öffentlichen Download im abgemeldeten Browser prüfen. Das automatische
   GitHub-Quellarchiv ersetzt die Qt-/PySide6-Quellbeigabe nicht. Release-Assets
   später nicht still austauschen; Korrekturen erhalten eine neue Version.

Der Versions-Tag startet ebenfalls die CI. Falls dieser Lauf neue Pakete erzeugt,
deren Tests und Prüfsummen prüfen; unterschiedliche Builds nicht vermischen.
Es gibt keine automatische Veröffentlichung durch den Workflow.

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
