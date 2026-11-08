# Änderungen

## 1.6.0

- **✨-Knopf erscheint sofort** (vorher bis zu 0,2 s Verzögerung) – und jetzt auch nach **Strg+A** („alles markieren“) und nach Markieren mit **Umschalt + Pfeil/Pos1/Ende**. Er erscheint an der Maus oder, wenn sie woanders ist, am Text-Cursor. Im Explorer, auf dem Desktop, in Excel und in Konsolen bleibt er weg (dort markiert man Dateien oder Zellen). Weitertippen blendet ihn aus.
- **Nachdenken (Reasoning) einstellbar:** *KI-Server einrichten → Nachdenken: wie der Server es macht / aus – schneller / an – gründlicher*, und je KI-Aktion abweichend (z. B. „Zusammenfassen“ gründlich, „Umformulieren“ schnell). Der Datenwächter prüft einmal, welchen Schalter der Server versteht (OpenAI `reasoning_effort`, Qwen/vLLM `chat_template_kwargs`, DashScope `enable_thinking`, Claude `thinking`) – und ob er wirklich wirkt.

## 1.5.3

- **KI-Aktionsleiste direkt am Mauszeiger** – auch auf dem zweiten Bildschirm und am Bildschirmrand (dort links bzw. oberhalb der Maus). Gilt ebenso für den ✨-Knopf. Im Browser öffnet sie sich nach einem Rechtsklick auf KI-Seiten an der Maus, sonst am Ende der Markierung.
- **Die Leiste bleibt stehen, während die KI arbeitet:** drehender Kreis, Name der Aktion, Sekunden und „Abbrechen“ (auch mit Esc). Danach ✓ „Ersetzt“; Ergebnisse zum Anzeigen und Fehler erscheinen an derselben Stelle. Windows-Programm und Browser gleich.
- **Behoben: Nach „Umformulieren“ verschwand die Leiste und das Fenster zeigte dauerhaft „prüft …“.** Unerwartete Fehler beim KI-Aufruf oder beim Einfügen kommen jetzt als Meldung zurück; nach spätestens zweieinhalb Minuten ohne Antwort wird die Aktion beendet. Liegt das Ergebnis nicht im Programm, steht es in der Zwischenablage.
- Fehlerprotokoll `fehler.log` neben den Einstellungen (ohne Inhalte), damit sich Probleme nachvollziehen lassen.

## 1.5.2

- **Drop-Schutz verdeckt keine anderen Fenster mehr:** Die Auffangfläche liegt jetzt direkt über der KI-App statt über allem. Liegt ein Explorer- oder Browserfenster vor der Claude- oder ChatGPT-App, bleibt es davor, und Ziehen zwischen anderen Fenstern funktioniert normal. Verlässt die Maus die App, verschwindet die Fläche; zurück über der App erscheint sie wieder.

## 1.5.1

- **KI-Server-Adresse wird aufgeräumt:** `https:\\server\v1` (Backslashes), `server/v1` (ohne https://) oder die ganze Endpunkt-Adresse funktionieren jetzt. Vorher hieß es „no host given“, und der Server galt fälschlich als lokal (Fotos an, Anonymisieren aus). Gespeicherte Einstellungen mit Backslashes werden beim Start korrigiert.
- **HTTPS wie im Browser:** Zertifikate prüft jetzt Windows selbst. Behebt „CERTIFICATE_VERIFY_FAILED … unable to get issuer certificate“ bei Servern mit neuen Let's-Encrypt-Zertifikaten und gilt auch für Firmen-Zertifikate.
- Klare Meldung bei ungültiger Adresse; „Verbindung testen“ nennt das verwendete Modell.

## 1.5.0

- **KI-Server an/aus im Tray-Menü:** „KI-Server benutzen“ schaltet alle Anfragen an den KI-Server ab (Inhalts-Check, Namenssuche, KI-Aktionen). Adresse, Token und Modell bleiben gespeichert.
- Der Haken **„Inhalts-Check mit KI“** bleibt jetzt auch nach einem Neustart so, wie du ihn gesetzt hast.
- Kein fest eingebauter KI-Dienst: Adresse und Token deines KI-Servers trägst du selbst ein.
- Modelle, die keinen Chat können (Realtime, Instruct, ältere Completion-Modelle), werden nicht mehr als Standard gewählt.

## 1.4.2

- Feste Angaben je KI-Dienst möglich: Standardmodell, Zusatzangaben (z. B. „ohne Nachdenken“ für schnellere Antworten) und Schlüssel als Pflicht – ohne Schlüssel geht dann nichts raus.
- Antworten von Modellen, die „laut nachdenken“ (`<think>…</think>`), werden bereinigt – auch bei anderen Servern.

## 1.4.1

- Server wie LiteLLM listen auch Sprach-, Vorlese-, Embedding- und OCR-Modelle. Ist kein Modell eingestellt, nimmt der Datenwächter jetzt das erste Chat-Modell statt z. B. „stt“.

## 1.4.0

- **Lokales KI-Modell:** *Einstellungen → Lokales KI-Modell → Laden* holt einmalig ein Modell (180 MB), das danach ohne Internet und ohne Server auf dem PC Namen und Orte findet, die keine Regel kennt („Wenzeslaus Brummer“, „Kowalczyk“, „Pirna“). Fester Modellstand, SHA-256-geprüft, Download wird fortgesetzt; läuft mit onnxruntime (im Windows-Programm enthalten), ohne PyTorch.
  - Gemessen an GraSCCo: Orte 59 % → 81 %, Adressen 93 % → 96 %, Namen 97,5 % → 97,8 % bei einem zusätzlichen Fehlalarm. Organe, Medikamente, Überschriften und Wortstücke filtert der Datenwächter heraus.
  - Gilt überall, wo der Windows-Scanner prüft: Zwischenablage, Dateien, KI-App-Schutz, Dateien aus der Browser-Erweiterung.
  - Kommandozeile: `datenwaechter modell laden | entfernen`.
- Ersetzt das bisherige GLiNER-Modell (600 MB, PyTorch, nur in der Python-Installation).

## 1.3.0

- **Einstellbar, was geschwärzt wird** („Was soll geschwärzt werden?“ in Windows-Programm und Handy-App; die Browser-Erweiterung übernimmt die Einstellung des Windows-Programms):
  - *Angaben zur Person* – immer: Name, Adresse, Geburtsdatum, Kontakt, IBAN, Ausweis-, Steuer- und Versichertennummer, Fall- und Patientennummern, Kfz-Kennzeichen, IMEI, GPS.
  - *Firmen & Kunden* – Standard an: Firmen (GmbH, AG, e.V. …), Kliniken und Praxen, Kunden-, Vertrags- und Angebotsnummern, USt-IdNr., Aktenzeichen.
  - *Preise & Beträge* – Standard aus.
  - *Medizinische Inhalte* – Standard aus: Diagnosen, ICD-Codes, Medikamente, Laborwerte.
  - *Themen-Warnung nur mit Person* – Standard an: „Erkläre mir CRP 200 und 15.000 Leukos“ geht ohne Rückfrage durch, ein Arztbrief mit Namen nicht.
- **Deutlich bessere Erkennung in Arztbriefen und Formularen**, gemessen an 63 Arztbriefen des Forschungskorpus GraSCCo: Namen, Geburtsdaten, Adressen, Kontakt und Kennnummern von 66 % auf 95 % (Namen 97 %, Geburtsdaten 97 %, Adressen 93 %). Neu u. a.: Titel-Ketten („Univ.-Prof. Dr. med.“, „OÄ Dr.“, „Drs. Seiler und Wantzer“), Namen in Großbuchstaben, Initialen („Holger M. Recklinghausen“, „Herr K.“), österreichische und Schweizer PLZ, Adressblöcke, „Am Waldsaum 21“, Telefonnummern wie „+43(0)333 775-8447“, „Albers (* 4.4.1997)“.
- Weniger Fehlalarme: „die Leber“ ist kein Dr. Leber, „Rektumamputation“ kein Nachname, „Krankengymnastik KG“ keine Firma.
- Windows-Programm, Browser-Erweiterung und Handy-App finden jetzt nachweislich dasselbe (eigener Test vergleicht beide Fassungen Fund für Fund).

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
