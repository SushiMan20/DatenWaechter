# Sicherheit

Der Datenwächter verarbeitet sensible Daten. Sicherheitslücken – z. B. ein Weg, wie Daten ungewollt den Rechner
verlassen, oder eine Umgehung der Prüfung – bitte **nicht** als öffentliches Issue melden, sondern über
*Security → Report a vulnerability* in diesem Repository (private Meldung an die Betreuer).

Bitte beschreibe, wie sich das Problem nachstellen lässt, und verwende dabei nur erfundene Beispieldaten.

## Grundsätze

- Erkennung, Texterkennung, Gesichtserkennung und Schwärzen laufen lokal.
- Daten gehen nur an einen KI-Server, wenn du selbst einen einträgst; bei externen Servern wird standardmäßig vorher
  anonymisiert, Fotos werden standardmäßig nicht gesendet.
- Das Token des KI-Servers liegt in der Windows-Anmeldeinformationsverwaltung (sonst in einer nur für deinen Benutzer
  lesbaren Datei).
- Keine Telemetrie. Die Tageszähler (nur Zahlen) liegen auf deinem Rechner.
