# 🛡 Datenwächter

Prüft Texte und Dateien auf persönliche oder geheime Daten, **bevor** sie in Claude, ChatGPT, Codex & Co. landen.
Bei einem Fund erscheint eine Warnung mit der Liste der gefundenen Daten. Du kannst dann anonymisieren,
das Original trotzdem verwenden oder abbrechen. Alles läuft lokal, es geht nichts ins Internet.

| Browser (claude.ai, chatgpt.com, …) | Windows-Fenster (Zwischenablage, Desktop-Apps) |
|---|---|
| ![Browser-Warnung](docs/browser-warnung.png) | ![Fenster-Warnung](docs/gui-warnung.png) |

## Was erkannt wird

| Stufe | Daten |
|---|---|
| **hoch** | IBAN (mit Prüfsumme), Kreditkarten (Luhn-Prüfung), Steuer-ID (mit Prüfsumme), Sozialversicherungsnummer, API-Schlüssel (Anthropic, OpenAI, AWS, GitHub, Google, Slack, Stripe), private Schlüssel, JWT-Tokens, Passwörter in Konfigurationen, Datenbank-URLs mit Passwort |
| **mittel** | Namen (nach Anrede), E-Mail, Telefonnummern, Straße + Hausnummer, PLZ + Ort, Geburtsdatum |
| **niedrig** | IP-Adressen |
| **mit lokalem KI-Modell** | zusätzlich Namen ohne Anrede, Adressen in Freitext, Ausweisnummern, Gesundheitsdaten |

Anonymisiert wird mit Platzhaltern wie `[PERSON_1]` oder `[IBAN_1]`. Gleiche Werte bekommen denselben Platzhalter,
so versteht die KI weiterhin die Zusammenhänge. Die Zuordnung bleibt nur lokal gespeichert, damit du die Antwort
der KI zurückübersetzen kannst.

## Die zwei Bausteine

### 1. Browser-Erweiterung (Chrome / Edge / Brave): der eigentliche „Drop-Schutz“

Fängt in KI-Chats drei Wege ab, **bevor** die Seite die Daten erhält:

- **Einfügen** (Strg+V) von Text oder Dateien
- **Hineinziehen** (Drag & Drop) von Dateien oder Text
- **Büroklammer** (Datei-Auswahl-Dialog)

Text- und Code-Dateien (.txt, .csv, .json, .py, .env, …) prüft die Erweiterung selbst. Für **PDF und Word** nutzt
sie den lokalen Python-Scanner (Schritt 2 unten), denn ohne ihn kann der Browser diese Formate nicht lesen.
Kopierst du später eine KI-Antwort mit Platzhaltern, setzt die Erweiterung die Originalwerte automatisch wieder ein.

**Installieren:**
1. `chrome://extensions` (bzw. `edge://extensions`) öffnen, **Entwicklermodus** einschalten
2. **Entpackte Erweiterung laden** und den Ordner `extension/` auswählen
3. Für PDF/Word: die angezeigte **ID** kopieren und ausführen:
   ```
   pip install .
   python install_browser_bridge.py <ERWEITERUNGS-ID>
   ```
   Danach den Browser neu starten.

### 2. Windows-Fenster: Schutz für Desktop-Apps (Claude Desktop, ChatGPT-App, Codex …)

In Desktop-Apps kann sich kein fremdes Programm sauber in deren Drag & Drop einklinken. Das ginge nur mit
DLL-Injektion, und die ist fehleranfällig und wird von Virenscannern blockiert. Der Datenwächter setzt deshalb
an der **Zwischenablage** an:

- **Text kopiert:** Im *sicheren Modus* liegt sofort nur noch die anonymisierte Fassung in der Zwischenablage.
  Das Original kannst du im Warnfenster mit einem Klick zurückholen.
- **Datei im Explorer kopiert (Strg+C):** Die Datei wird geprüft. Bei Funden legt „Anonymisierte Kopie erstellen“
  die bereinigte Datei in die Zwischenablage, Strg+V im Chat fügt dann diese ein.
- **Datei ins Fenster ziehen:** Sie wird geprüft, die anonymisierte Kopie erscheint im Explorer und kann weitergezogen werden.
- **KI-Antwort zurückübersetzen:** Antwort kopieren und auf den Knopf klicken, dann stehen wieder die echten Namen drin.

```
pip install ".[windows]"          # pywin32 + Drag & Drop
datenwaechter-gui                 # Fenster starten
```

### Lokales KI-Modell (optional)

```
pip install ".[ki]"
```

Installiert [GLiNER](https://github.com/urchade/GLiNER) (`urchade/gliner_multi_pii-v1`), ein kleines,
mehrsprachiges Modell nur für die Erkennung persönlicher Daten (~600 MB, läuft auf der CPU). Es wird einmalig
heruntergeladen und läuft danach offline. Im Fenster per Häkchen aktivieren, in der Kommandozeile mit `--ki`.

## Kommandozeile

```
datenwaechter scan Vertrag.pdf kunden.csv           # Exit-Code 2 = kritische Funde
datenwaechter anonymisieren Vertrag.pdf --zuordnung # schreibt Vertrag_anonymisiert.txt
```

## Grenzen (Stand Prototyp)

- Bilder und eingescannte PDFs werden noch nicht geprüft (dafür bräuchte es Texterkennung/OCR).
- PDF/Word werden als anonymisierter **Text** hochgeladen, das Layout geht verloren. Word-Dateien aus dem Fenster bleiben `.docx`.
- Ohne KI-Modell findet die Regelprüfung Namen nur mit Anrede („Frau Müller“, „Herr Dr. Becker“).
- Die Browser-Erweiterung hängt am Aufbau der Chat-Seiten. Ändert ein Anbieter seine Upload-Logik, muss sie eventuell nachgezogen werden.
- Es ist eine Schutzschicht gegen Versehen, keine Garantie. Regeln haben immer Lücken.

## Entwicklung

```
pip install -e ".[dev]"
pytest                              # Python-Regeln, Anonymisierung, Dateien
node --test tests/detectors.test.js # Browser-Regeln (gleiche Testfälle)
node tests/e2e_extension.js         # Erweiterung in echtem Chromium inkl. PDF über Python
```

Die Regeln gibt es zweimal, in `datenwaechter/detectors.py` und `extension/detectors.js`. Die Tests prüfen
beide mit denselben Beispielen, damit sie nicht auseinanderlaufen.
