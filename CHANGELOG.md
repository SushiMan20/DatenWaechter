# Änderungen

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
