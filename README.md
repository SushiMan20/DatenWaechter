<p align="center">
  <img src="docs/banner.png" alt="Datenwächter – sensible Daten erkennen und anonymisieren, bevor sie in ChatGPT, Claude &amp; Co. landen" width="100%">
</p>

<p align="center">
  <a href="https://github.com/SushiMan20/TestRepo/actions/workflows/windows.yml"><img src="https://github.com/SushiMan20/TestRepo/actions/workflows/windows.yml/badge.svg" alt="Windows-Build"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4" alt="Windows 10 | 11">
  <img src="https://img.shields.io/badge/Browser-Chrome%20%7C%20Edge%20%7C%20Brave-4285F4" alt="Chrome | Edge | Brave">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/l%C3%A4uft-lokal-2e7d32" alt="läuft lokal">
</p>

**Datenwächter** prüft Texte, PDFs (auch eingescannte), Word-Dateien, Screenshots und Fotos, **bevor** sie in einen KI-Chat
hochgeladen werden. Findet er Namen, Bankdaten, Adressen, Zugangsdaten oder Gesichter, warnt er. Du kannst dann
eine anonymisierte Fassung hochladen, das Original verwenden oder abbrechen. Die Prüfung läuft auf deinem Rechner.

> 🇬🇧 *Datenwächter (“data guardian”) checks what you paste or upload into AI chats such as ChatGPT or Claude for personal
> and confidential data (IBANs, names, addresses, API keys, faces) and offers an anonymized version instead. It runs
> locally as a Windows app and a Chrome/Edge extension. The UI and documentation are in German.*

<p align="center"><img src="docs/browser-warnung.png" alt="Warnung beim Hochladen eines Arbeitsvertrags in einen KI-Chat" width="860"></p>

## Was er kann

- **Prüft beim Hochladen, Einfügen und Kopieren.** Im Browser fängt er Drag & Drop, „Datei hinzufügen“ und Strg+V auf claude.ai, chatgpt.com, Gemini, Copilot, Mistral und Perplexity ab. Unter Windows prüft er alles, was du kopierst, auch Dateien und Screenshots.
- **Erkennt sensible Daten:** IBAN, Kreditkarte und Steuer-ID (jeweils mit Prüfsumme), Sozialversicherungs-, Ausweis- und Passnummer, API-Schlüssel, Passwörter, E-Mail, Telefon, Adressen, Geburtsdaten, Namen und Gesichter auf Fotos.
- **Liest Bilder und Scans** mit der Windows-Texterkennung, alternativ mit Tesseract.
- **Schwärzt statt zu löschen.** PDFs und Bilder behalten ihr Layout, Funde bekommen einen Kasten mit Platzhalter wie `[IBAN_1]`, Gesichter werden verpixelt.
- **Sagt dir, *was* du hochlädst:** „Du lädst gerade Familienunterlagen hoch – willst du das?“
- **Übersetzt KI-Antworten zurück:** Aus `[PERSON_1]` wird wieder der echte Name.
- **Optional mit eigenem KI-Server** (OpenAI-kompatible API mit Adresse und Token). Die KI bewertet dann Inhalte und Fotos genauer und findet auch Namen ohne „Herr/Frau“.
- **KI-Aktionen** wie „Umformulieren“, „Kürzen“, „Übersetzen“ oder eigene Anweisungen. Im Browser per Rechtsklick, in jedem Windows-Programm per Strg+Alt+Leertaste.

## So sieht es aus

### Im Browser

| Fund-Warnung beim Hochladen | Themen-Warnung beim Einfügen (dunkel) |
|---|---|
| ![Fund-Warnung](docs/browser-warnung.png) | ![Themen-Warnung](docs/browser-thema-dunkel.png) |

Klickst du in der Browserleiste auf das Datenwächter-Symbol, siehst du den Schutzstatus, kannst pausieren und siehst
die Tageszähler. Außerdem zeigt das Fenster, ob der lokale Scanner und der KI-Server verbunden sind.

<p align="center"><img src="docs/browser-popup.png" alt="Fenster der Browser-Erweiterung, hell und dunkel" width="560"></p>

### Auf dem Windows-Desktop

Ein Schild im Infobereich zeigt den Zustand: grün = aktiv, blau = prüft, rot = Warnung, orange = pausiert. Kopierst du
etwas Sensibles, erscheint unten rechts eine Benachrichtigung. Im *sicheren Modus* liegt dann schon die anonymisierte
Fassung in der Zwischenablage.

| Hell | Dunkel (folgt der Windows-Einstellung) |
|---|---|
| ![Desktop hell](docs/desktop-hell.png) | ![Desktop dunkel](docs/desktop-dunkel.png) |

### Schwärzen statt hochladen

Aus einem eingescannten Brief wird ein geschwärztes PDF, aus einem Foto eines mit verpixeltem Gesicht. Hochgeladen wird
nur die rechte Fassung. Die echten Werte stehen in der Datei nicht mehr drin.

![Vorher/Nachher](docs/schwaerzung.png)

### KI-Aktionen

Text markieren, dann im Browser Rechtsklick auf **„Mit KI bearbeiten …“** oder in einem beliebigen Windows-Programm
**Strg+Alt+Leertaste**. Das Ergebnis ersetzt die Markierung, wird darunter eingefügt oder angezeigt. Tippst du etwas
ein, filtert das die Liste. Passt keine Aktion, wird das Getippte als eigene Anweisung ausgeführt.

| Browser | Windows (hell / dunkel) |
|---|---|
| ![Aktionsleiste im Browser](docs/aktionsleiste-browser.png) | ![Aktionsleiste unter Windows](docs/ki-aktionen-windows.png) |

Eigene Aktionen legst du unter *Einstellungen → KI-Aktionen bearbeiten* an:

<p align="center"><img src="docs/ki-aktionen-editor.png" alt="Editor für eigene KI-Aktionen" width="620"></p>

## Installation

### 1. Windows-Programm

1. **`Datenwaechter-Setup-x.y.z.exe`** herunterladen. Die Datei findest du unter [Releases](../../releases) oder im letzten erfolgreichen Lauf von [*Windows-Programm*](../../actions/workflows/windows.yml) unter *Artifacts*.
2. Installieren. Du brauchst keine Admin-Rechte und kein Python. Der Installer ist nicht signiert, deshalb fragt Windows beim ersten Start nach: *Weitere Informationen → Trotzdem ausführen*.
3. Fertig: Das grüne Schild erscheint im Infobereich. Wenn du willst, startet der Datenwächter künftig automatisch mit Windows.

### 2. Browser-Erweiterung (Chrome, Edge, Brave)

1. `chrome://extensions` bzw. `edge://extensions` öffnen und den **Entwicklermodus** einschalten.
2. **Entpackte Erweiterung laden** wählen und den Ordner *Datenwächter – Browser-Erweiterung* auswählen. Eine Verknüpfung dazu legt der Installer im Startmenü an.
3. Die Verbindung zum Windows-Programm, die für PDFs, Bilder und KI-Aktionen nötig ist, richtet der Installer automatisch ein. Ohne das Programm prüft die Erweiterung nur Text.

### Mit Python (für Entwickler und andere Systeme)

```bash
pip install ".[windows,gesichter]"     # unter Windows: Tray, Windows-Texterkennung, Gesichter
datenwaechter-gui                      # Fenster + Tray-Symbol
datenwaechter browser-bruecke          # Browser-Erweiterung mit dem Scanner verbinden
```

Unter Linux/macOS: `pip install ".[tesseract,gesichter]"` und Tesseract mit Sprachpaket Deutsch installieren.

## Eigener KI-Server (optional)

Ohne KI arbeitet der Datenwächter mit Regeln und Stichwörtern. Mit einer KI wird er genauer. Unter *Einstellungen →
KI-Server einrichten* trägst du die **API-Adresse** und dein **Token** ein. Das funktioniert mit jedem Dienst, der die
OpenAI-Schnittstelle (`/v1/chat/completions`) spricht, z. B. OpenAI, Azure OpenAI, Mistral, OpenRouter, ein
Firmen-Gateway, LM Studio oder vLLM.

<p align="center"><img src="docs/ki-server.png" alt="KI-Server einrichten: API-Adresse, Token, Modell" width="620"></p>

Du legst fest, was die KI prüfen soll:

- **Inhalt bewerten:** z. B. „Du lädst gerade Personal- und Arbeitsunterlagen hoch“.
- **Namen ohne „Herr/Frau“ finden**, z. B. den Kindernamen „Mia Schneider“ in einem Gerichtsbrief.
- **Fotos und Screenshots bewerten**, z. B. „Foto eines Ausweises“.
- **Vor dem Senden anonymisieren:** IBAN, Telefon und bekannte Namen gehen nur als Platzhalter raus.

Bei einem **externen Server** sagt der Dialog genau, was deinen Rechner verlässt. Standardmäßig wird vorher
anonymisiert, und Fotos werden nicht gesendet. Das Token liegt in der Windows-Anmeldeinformationsverwaltung. Für
Firmen-Rollouts gibt es zusätzlich die Umgebungsvariablen `DATENWAECHTER_LLM_URL`, `DATENWAECHTER_LLM_TOKEN` und
`DATENWAECHTER_LLM_MODELL`.

```bash
datenwaechter ki-server --url https://gateway.firma.de/v1 --token - --modell gpt-4.1-mini --testen
```

## Datenschutz: Was passiert mit meinen Daten?

| | Ohne KI-Server | Mit eigenem KI-Server |
|---|---|---|
| Erkennung von IBAN, Namen, Adressen … | lokal | lokal |
| Texterkennung, Gesichter, Schwärzen | lokal | lokal |
| Inhalts-Check | lokal (Stichwörter) | Text an deinen Server, standardmäßig anonymisiert |
| Fotos bewerten | – | nur wenn eingeschaltet |
| Namen ohne Anrede finden | – | nur wenn eingeschaltet; bekannte Angaben vorher als Platzhalter |
| Statistik, Telemetrie | nur Tageszähler (Zahlen) auf deinem PC | dito |

Die Zuordnung der Platzhalter (`[PERSON_1]` = …) bleibt auf deinem Rechner, damit du KI-Antworten zurückübersetzen kannst.

## Was erkannt wird

| Stufe | Daten |
|---|---|
| **hoch** | IBAN (auch mit OCR-Lesefehlern wie „O“ statt „0“), Kreditkarte, Steuer-ID, Sozialversicherungsnummer, Ausweis-/Passnummer, API-Schlüssel (Anthropic, OpenAI, AWS, GitHub, Google, Slack, Stripe), private Schlüssel, Tokens, Passwörter, Datenbank-Zugänge |
| **mittel** | Namen (nach Anrede, mit KI auch ohne), E-Mail, Telefon, Straße + Hausnummer, PLZ + Ort, Geburtsdatum, Gesichter |
| **niedrig** | IP-Adressen |
| **Themen** | Familie, Gesundheit, Finanzen, Recht, Personal/Arbeit, Ausweise, Firmeninterna, besonders geschützte Daten nach Art. 9 DSGVO ([Stichwörter](datenwaechter/kategorien.json)) |

## Grenzen und häufige Fragen

- **Gibt es eine Handy-App?** Noch nicht. iOS und Android erlauben Apps nicht, die Zwischenablage im Hintergrund zu lesen oder Uploads in anderen Apps abzufangen. Möglich wäre „Teilen → Datenwächter → weiter an die KI“.
- **Warum gibt es keinen Eintrag im Windows-Rechtsklick-Menü?** Fremde Programme lassen sich dort nicht erweitern. Deshalb gibt es das Tastenkürzel Strg+Alt+Leertaste.
- **Desktop-Apps wie die ChatGPT-App?** Deren eigener „Datei hinzufügen“-Dialog lässt sich nicht abfangen. Geschützt sind Kopieren/Einfügen sowie Dateien, die du erst ins Datenwächter-Fenster ziehst.
- **Warum Entwicklermodus?** Die Erweiterung ist (noch) nicht im Chrome Web Store.
- **Was wird nicht geschwärzt?** Gesundheitsangaben im Fließtext lösen eine Warnung aus, werden aber nicht geschwärzt. Handschrift erkennt die Texterkennung kaum. Bilder *in* Word-Dateien werden nicht geprüft.
- **Ist das eine Garantie?** Nein. Der Datenwächter ist eine Schutzschicht gegen Versehen. Regeln und KI haben Lücken.

## Kommandozeile

```bash
datenwaechter scan Vertrag.pdf Foto.jpg kunden.csv     # Exit-Code 2 = kritische Funde, 1 = mittlere
datenwaechter anonymisieren Scan.pdf --zuordnung       # schreibt Scan_anonymisiert.pdf
datenwaechter aktion Umformulieren --text "…"          # KI-Aktion auf Text anwenden
datenwaechter aktionen --neu "Als Tweet" --anweisung "Mach daraus einen Tweet" --modus anzeigen
```

## Entwicklung

```bash
pip install -e ".[dev]"
pytest                                   # Regeln, Schwärzen, OCR, Gesichter, KI-Anbindung (simulierte Server), Oberfläche
node --test tests/detectors.test.js      # Browser-Regeln = Python-Regeln
node tests/e2e_extension.js              # Erweiterung in echtem Chromium (SITE=chatgpt.com für ChatGPT)
node tests/e2e_ki_aktionen.js            # KI-Aktionen im Browser
python tests/windows_smoke.py            # nur Windows: Zwischenablage, OCR, Tastenkürzel, Benachrichtigung, Notepad
```

Bei jedem Push baut [GitHub Actions](.github/workflows/windows.yml) auf echtem Windows. Der Lauf führt die Tests und
den Windows-Praxistest aus, baut das Programm (PyInstaller) und den Installer (Inno Setup) und installiert ihn testweise
still und wieder ab. Bei einem Tag `v*` entsteht ein Release. Selbst bauen kannst du mit `packaging\build_windows.ps1`.

```
datenwaechter/      Python-Paket: Regeln, OCR, Schwärzen, KI-Anbindung, Fenster, Tray, Browser-Brücke
extension/          Browser-Erweiterung (Manifest V3)
packaging/          PyInstaller-Rezept, Installer, Programm-Symbol
tests/              pytest, Browser- und Windows-Tests
```

Die Erkennungsregeln gibt es zweimal, in `datenwaechter/detectors.py` und `extension/detectors.js`. Die Tests prüfen
beide mit denselben Beispielen. Ändern sich die Stichwörter, erzeugst du die Browser-Fassung so neu:
`python -c "import datenwaechter.content_check as c; c.write_extension_categories()"`.

## Mitmachen

Fehler und Ideen bitte als Issue melden. Sicherheitslücken bitte nicht öffentlich, siehe [SECURITY.md](SECURITY.md).
Wie du beiträgst, steht in [CONTRIBUTING.md](CONTRIBUTING.md), Änderungen im [CHANGELOG](CHANGELOG.md).

## Danksagung

[pypdfium2](https://github.com/pypdfium2-team/pypdfium2), [pypdf](https://github.com/py-pdf/pypdf),
[OpenCV](https://opencv.org), [Tesseract](https://github.com/tesseract-ocr/tesseract), [pystray](https://github.com/moses-palmer/pystray),
[PyInstaller](https://pyinstaller.org), [Inno Setup](https://jrsoftware.org/isinfo.php).
Das Testfoto stammt aus einem gemeinfreien NASA-Foto (über [scikit-image](https://scikit-image.org)). Alle Personen,
Adressen, Kontonummern und Firmen in Beispielen und Screenshots sind erfunden.
