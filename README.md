# 🛡 Datenwächter

Prüft Texte, PDFs, Word-Dateien, Bilder und Fotos, **bevor** sie in Claude, ChatGPT, Codex & Co. landen.
Alles läuft lokal auf deinem PC, es geht nichts ins Internet.

Der Datenwächter beantwortet zwei Fragen:

1. **Welche sensiblen Daten stecken drin?** Zum Beispiel IBAN, Namen, Adressen, API-Schlüssel oder Gesichter auf Fotos.
2. **Was lädst du da eigentlich hoch?** Zum Beispiel: *„Du lädst gerade Familienunterlagen hoch (Sorgerecht, Jugendamt, Tochter). Willst du das wirklich?“*

Danach entscheidest du: **anonymisiert hochladen**, **Original hochladen** oder **abbrechen**.

| Inhalts-Check | Fundliste |
|---|---|
| ![Inhalts-Warnung](docs/browser-inhalt.png) | ![Fund-Warnung](docs/browser-warnung.png) |

## Oberfläche: Tray-Symbol, Fenster und Browser-Leiste

Ein **Schild im Infobereich** zeigt auf einen Blick den Zustand: grün = Schutz aktiv, blau = prüft gerade,
rot = Warnung, orange = pausiert. Ein **Rechtsklick** öffnet das Menü mit diesen Punkten: Schutz an/aus,
15 Minuten pausieren, Datei prüfen, KI-Antwort zurückübersetzen, Einstellungen, Mit Windows starten und Beenden.
Kommt eine Warnung, während das Fenster geschlossen ist, erscheint eine Windows-Benachrichtigung.

![Fenster und Tray-Symbole](docs/oberflaeche.png)

- **Ein Schalter** schaltet den Schutz an und aus. Nach einer Pause schaltet er sich automatisch wieder ein.
- Die **Ablagefläche** prüft Dateien, die du hineinziehst.
- Die **Tageszähler** zeigen geprüft, gewarnt und anonymisiert. Gezählt werden nur Zahlen, keine Inhalte.
- **„Zuletzt“** zeigt die letzten Ereignisse mit Uhrzeit.
- **Schließen (X)** blendet nur das Fenster aus, der Schutz läuft im Infobereich weiter. Mit „Mit Windows starten“ läuft der Datenwächter ab der Anmeldung (`datenwaechter gui --minimiert`).
- Das Fenster ist **hell oder dunkel**, passend zur Windows-Einstellung.

**In der Browser-Leiste** zeigt das Datenwächter-Symbol denselben Zustand. Pausiert trägt es den Hinweis „AUS“.
Ein Klick zeigt Schalter, Pause-Knöpfe, die Tageszähler und ob der lokale Scanner und der KI-Server verbunden sind.

![Fenster der Browser-Erweiterung](docs/browser-popup.png)

**Anonymisieren heißt bei PDFs und Bildern schwärzen.** Das Layout bleibt erhalten. Funde werden mit einem Kasten
samt Platzhalter überdeckt, Gesichter werden verpixelt. Der Originaltext ist danach nicht mehr in der Datei enthalten.

![Schwärzung](docs/schwaerzung.png)

## Was geprüft wird

| | Wie | Ergebnis beim Anonymisieren |
|---|---|---|
| Text, Code, CSV, JSON … | Regeln mit Prüfsummen | Platzhalter wie `[IBAN_1]` |
| Word (.docx) | Regeln | .docx mit Platzhaltern |
| PDF mit Text | Regeln, Position jedes Zeichens | geschwärztes PDF |
| **Eingescanntes PDF** | Texterkennung (OCR) | geschwärztes PDF |
| **Bilder / Screenshots** | Texterkennung (OCR) | geschwärztes Bild |
| **Fotos von Personen** | Gesichtserkennung (OpenCV) | Gesichter verpixelt |
| **Motiv eines Fotos** („Ausweis“, „Kind am Strand“) | KI-Server mit Bildverständnis (optional) | Warnung mit Beschreibung |

**Sensible Daten:** IBAN, Kreditkarte, Steuer-ID (jeweils mit Prüfsumme), Sozialversicherungsnummer, API-Schlüssel
(Anthropic, OpenAI, AWS, GitHub, Google, Slack, Stripe), private Schlüssel, Tokens, Passwörter, Datenbank-Zugänge,
Namen (nach Anrede, mit KI-Modell auch ohne), E-Mail, Telefon, Adressen, Geburtsdatum, IP-Adressen.

**Inhalts-Check:** Familie, Gesundheit, Finanzen, Recht, Personal/Arbeit, Ausweise, Firmeninterna und besonders
geschützte Daten nach Art. 9 DSGVO (Religion, Politik, Gewerkschaft, Sexualität). Ohne weitere Installation arbeitet
der Check mit Stichwörtern ([`kategorien.json`](datenwaechter/kategorien.json), leicht erweiterbar). Mit einem
**KI-Server** (siehe unten) liest ein Sprachmodell den Inhalt tatsächlich und bewertet auch Fotos.

## KI-Server für den Inhalts-Check: Ollama oder eigener OpenAI-kompatibler Server

Du kannst jeden Server nutzen, der die OpenAI-Schnittstelle (`/v1/chat/completions`) spricht, mit eigener URL und eigenem Token.
Beispiele: LM Studio, vLLM, LocalAI, llama.cpp-Server, Ollama im OpenAI-Modus, ein Firmen-Gateway, OpenRouter, Mistral oder OpenAI.

| Im Fenster | Kommandozeile |
|---|---|
| ![KI-Server einstellen](docs/gui-ki-server.png) | `datenwaechter ki-server --url http://localhost:1234/v1 --modell qwen2.5-7b-instruct --testen`<br><br>Mit Token (`-` liest es von der Eingabe, damit es nicht im Verlauf landet):<br>`datenwaechter ki-server --url https://gateway.firma.de/v1 --token - --testen` |

- **„Modelle laden“** holt die Liste vom Server, **„Verbindung testen“** schickt eine kleine Testanfrage.
- **Ein Ort für alles:** Fenster, Kommandozeile und Browser-Erweiterung nutzen dieselbe Einstellung (`%APPDATA%\Datenwaechter\einstellungen.json`).
- **Token:** Mit `keyring` (im Paket `[windows]` enthalten) liegt es in der Windows-Anmeldeinformationsverwaltung, sonst in der Einstellungsdatei.
- **Firmen-Rollout:** Die Umgebungsvariablen `DATENWAECHTER_LLM_URL`, `DATENWAECHTER_LLM_TOKEN` und `DATENWAECHTER_LLM_MODELL` haben Vorrang.
- **Server ohne JSON-Modus oder ohne Bildverständnis** funktionieren auch, der Datenwächter fragt dann automatisch ohne diese Funktionen nach.

**Datenschutz bei externen Servern:** Liegt der Server außerhalb deines Rechners oder Netzes (z. B. `api.openai.com`),
zeigt der Datenwächter eine Warnung. Er stellt außerdem automatisch Folgendes ein:
- Der Text wird **vor dem Senden anonymisiert**: Aus Namen, IBAN usw. werden Platzhalter. Für die Frage „Was ist das für ein Inhalt?“ braucht die KI keine echten Daten.
- **Bilder werden nicht mitgeschickt.**

Beides lässt sich umstellen. Im Warndialog steht dann z. B. *„Bewertet von KI-Server (gpt-4o-mini@api.openai.com) – Inhalt wurde anonymisiert an api.openai.com gesendet“*.

![Bewertung durch eigenen KI-Server](docs/browser-ki-server.png)

## Die zwei Bausteine

### 1. Browser-Erweiterung (Chrome / Edge / Brave) für claude.ai, chatgpt.com, Gemini, Copilot …

Fängt **alle Upload-Wege** ab, *bevor* die Seite die Daten bekommt:

- **Drag & Drop** von Dateien oder Text
- **„Datei hinzufügen“ / Büroklammer**, auch bei Knöpfen mit unsichtbarem Eingabefeld und beim modernen Dateidialog (`showOpenFilePicker`)
- **Einfügen (Strg+V)** von Text, Dateien oder Screenshots

Kopierst du später eine KI-Antwort mit Platzhaltern, setzt die Erweiterung die echten Werte automatisch wieder ein.

**Installieren:**
1. `chrome://extensions` (bzw. `edge://extensions`) öffnen und den **Entwicklermodus** einschalten
2. **Entpackte Erweiterung laden** und den Ordner `extension/` wählen
3. Für PDFs, Bilder und Fotos den lokalen Scanner installieren (Abschnitt 2 unten). Dann die angezeigte **ID** kopieren und ausführen:
   ```
   python install_browser_bridge.py <ERWEITERUNGS-ID>
   ```
   Danach den Browser neu starten. Ohne diesen Schritt prüft die Erweiterung nur Text und Textdateien.

### 2. Lokaler Scanner + Windows-Fenster (auch für Claude Desktop, ChatGPT-App, Codex)

```
pip install ".[windows,gesichter]"     # Tray-Symbol, Windows-Texterkennung, Zwischenablage, Drag & Drop, Gesichter
datenwaechter-gui                      # Fenster + Tray-Symbol starten
datenwaechter gui --minimiert          # nur als Tray-Symbol starten
```

Desktop-Apps lassen sich nicht sauber beim Hineinziehen abfangen. Das ginge nur per DLL-Injektion, und die wird von
Virenscannern blockiert. Auch ihren eigenen „Datei hinzufügen“-Dialog kann kein anderes Programm abfangen.
Das Fenster setzt deshalb an der **Zwischenablage** und an einer eigenen **Ablagefläche** an:

- **Text kopiert:** Im *sicheren Modus* liegt sofort nur noch die anonymisierte Fassung in der Zwischenablage. Das Original holst du mit einem Klick zurück.
- **Screenshot kopiert (Win+Umschalt+S):** Das Bild wird gelesen. Bei Funden kommt die Warnung, und die geschwärzte Fassung geht in die Zwischenablage.
- **Datei im Explorer kopiert (Strg+C):** Die Datei wird geprüft, Strg+V im Chat fügt die geschwärzte Kopie ein.
- **Datei ins Fenster ziehen:** Die geschwärzte Kopie erscheint im Explorer und kann direkt in die App weitergezogen werden.
- **KI-Antwort zurückübersetzen:** Platzhalter werden wieder zu echten Namen.

![Warnung im Fenster](docs/gui-warnung.png)

### Optionale Zusätze

| Zweck | Installation |
|---|---|
| Texterkennung ohne Windows-OCR | [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) mit Sprachpaket „Deutsch“, dann `pip install ".[tesseract]"` |
| Inhalts-Check und Fotos mit lokaler KI ohne Einrichtung | [Ollama](https://ollama.com) installieren, `ollama pull gemma3:4b` (~3 GB, versteht Text **und** Bilder). Wird automatisch erkannt. Anderes Modell: Umgebungsvariable `DATENWAECHTER_OLLAMA_MODELL` |
| Eigener KI-Server mit URL + Token | siehe Abschnitt „KI-Server“ oben |
| Namen ohne Anrede | `pip install ".[ki]"` (GLiNER, ~600 MB, CPU) |

## Kommandozeile

```
datenwaechter scan Vertrag.pdf Foto.jpg kunden.csv   # Exit-Code 2 = kritische Funde
datenwaechter anonymisieren Scan.pdf --zuordnung     # schreibt Scan_anonymisiert.pdf
```

## Grenzen

- Ohne KI-Server mit Bildverständnis bewertet der Datenwächter das *Motiv* eines Fotos nicht. Er findet dann nur Text im Bild und Gesichter.
- Die Gesichtserkennung (OpenCV) findet vor allem frontale Gesichter. Bei Profilen, kleinen oder verdeckten Gesichtern kann sie etwas übersehen.
- Handschrift erkennt die Texterkennung kaum.
- Geschwärzte PDFs bestehen aus Seitenbildern, Text lässt sich darin nicht mehr markieren. Claude und ChatGPT lesen sie trotzdem.
- Bilder *innerhalb* von Word-Dateien werden noch nicht geprüft.
- In Desktop-Apps (Claude Desktop, Codex) fängt das Tool den eigenen „Datei hinzufügen“-Dialog nicht ab. Dort schützt nur der Weg über die Zwischenablage oder die Ablagefläche.
- Die Erweiterung hängt am Aufbau der Chat-Seiten. Ändert ein Anbieter seine Upload-Logik, muss sie eventuell nachgezogen werden.
- Es ist eine Schutzschicht gegen Versehen, keine Garantie.

## Entwicklung

```
pip install -e ".[dev]"
pytest                               # Regeln, Inhalts-Check (simuliertes Ollama + OpenAI-Server), OCR, Schwärzen, Gesichter, Oberfläche
node --test tests/detectors.test.js  # Browser-Regeln (gleiche Testfälle wie Python)
node tests/e2e_extension.js          # Erweiterung in echtem Chromium: Upload-Wege, Scanner, KI-Server, Leisten-Fenster, Pause
SITE=chatgpt.com node tests/e2e_extension.js   # dasselbe unter der Adresse von ChatGPT
```

Die Erkennungsregeln gibt es zweimal, in `datenwaechter/detectors.py` und `extension/detectors.js`. Die Tests
prüfen beide mit denselben Beispielen. Die Stichwörter stehen nur in `datenwaechter/kategorien.json`. Nach einer
Änderung erzeugst du die Browser-Fassung neu:
`python -c "import datenwaechter.content_check as c; c.write_extension_categories()"`
