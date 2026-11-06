# Änderungen

## 1.2.0

- **KI-Desktop-Apps geschützt (Windows):** ChatGPT, Claude, Copilot, Perplexity.
  - *Drop-Schutz:* Zieht man eine Datei (Explorer, Desktop, Browser, Outlook …) über das App-Fenster, erscheint eine Auffangfläche. Die Datei wird geprüft und erst danach – Original oder geschwärzt – per Einfügen übergeben.
  - *„Datei öffnen“-Schutz:* Im Windows-Dialog der App werden „Öffnen“, Enter und Doppelklick angehalten, bis die Datei geprüft ist; auf Wunsch wird die geschwärzte Kopie eingesetzt. Die App sieht das Original nie.
- ✨-Knopf erscheint auch bei 125/150 % Bildschirmskalierung an der richtigen Stelle.

## 1.1.0

- **Namen ohne KI:** Vornamenliste (~1.500, deutsch und international) plus typische Stellen: Anrede („Liebe Mia,“), Grußformel, Formularfelder („Name:“, „Kontoinhaber:“), „Familie Schneider“, „Sohn Lukas (5)“, „Schneider, Thomas“, „Fr./Hr./Dr.“, Großbuchstaben in Formularen. Ein erkannter Name wird überall im Text markiert; „Mia“ bekommt denselben Platzhalter wie „Mia Schneider“. Mehrdeutige Wörter („Ernst“, „Rose“, „Claude“) nur mit Nachnamen.
- **Geburtsdatum:** viele Schreibweisen („12. März 1985“, „01/02/1975“, „Geburtsdatum“ in der Zeile darüber, „* 12.03.1985“, „Jahrgang 1962“, „geb. 1985“, DOB).
- **✨-Knopf beim Markieren (Windows):** Text in einem beliebigen Programm markieren → Knopf daneben → KI-Aktionen. Nimmt keinen Fokus, abschaltbar.
- Gleiche Regeln in Windows-Programm, Browser-Erweiterung und Handy-App; gemeinsame Testbeispiele für beide Sprachen.

## 1.0.0 – erste Veröffentlichung

**Erkennen**
- Regeln mit Prüfsummen: IBAN (robust gegen OCR-Lesefehler), Kreditkarte, Steuer-ID; außerdem SV-, Ausweis- und Passnummer, API-Schlüssel, private Schlüssel, Tokens, Passwörter, Datenbank-Zugänge, E-Mail, Telefon, Adressen, Geburtsdatum, Namen nach Anrede, IP-Adressen
- Texterkennung (Windows-OCR oder Tesseract) für Screenshots und eingescannte PDFs, Gesichtserkennung (OpenCV)
- Inhalts-Check „Du lädst gerade Familienunterlagen hoch“ per Stichwörtern oder KI
- Gleiche Person, gleicher Platzhalter („Herrn Thomas Schneider“ … „Herr Schneider“ → `[PERSON_1]`)

**Schützen**
- Anonymisieren mit Platzhaltern, Zurückübersetzen von KI-Antworten
- PDFs und Bilder werden geschwärzt (Layout bleibt), Gesichter verpixelt

**Windows-Programm**
- Tray-Symbol, Benachrichtigung unten rechts beim Kopieren (ohne Fokus-Klau), sicherer Modus, Ablagefläche, Tageszähler, hell/dunkel, Autostart
- Installer ohne Admin-Rechte, portable Version

**Browser-Erweiterung** (Chrome, Edge, Brave)
- Fängt Drag & Drop, „Datei hinzufügen“ und Strg+V auf KI-Chat-Seiten ab; Symbol in der Leiste mit Pause und Zählern
- PDFs, Bilder und Word-Dateien über den lokalen Scanner (Native Messaging)

**Handy-App** (Android, iPhone – installierbare Web-App)
- „Teilen → Datenwächter“ aus jeder Android-App (PDF, Fotos, Text), danach „Geschützt teilen“ an ChatGPT, Claude & Co.
- Text, PDF (auch gescannt), Word und Fotos prüfen; Texterkennung und Schwärzen auf dem Gerät, Bereiche per Finger nachschwärzen
- Zurückübersetzen von KI-Antworten (auch per Teilen), KI-Aktionen und Inhalts-Check mit eigenem KI-Server
- Offline nutzbar, alle Bibliotheken mitgeliefert, Veröffentlichung über GitHub Pages

**KI (optional)**
- Eigener KI-Server über OpenAI-kompatible API (Adresse + Token): Inhalt bewerten, Fotos bewerten, Namen ohne Anrede finden; bei externen Servern standardmäßig vorher anonymisiert
- KI-Aktionen („Umformulieren“, „Kürzen“ … und eigene) – im Browser per Rechtsklick, unter Windows per Strg+Alt+Leertaste
