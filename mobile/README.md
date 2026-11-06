# Datenwächter – Handy-App

Installierbare Web-App (PWA) für Android und iPhone. Sie nutzt dieselben Erkennungsregeln wie die Browser-Erweiterung
(`../extension/detectors.js`). Alles läuft auf dem Gerät: pdf.js liest PDFs, tesseract.js erkennt Text auf Fotos und Scans,
jsPDF baut das geschwärzte PDF. Die Bibliotheken werden mitgeliefert, die App lädt nichts von fremden Servern.

```bash
npm ci
npm run build      # → dist/ (statisch, per https ausliefern)
npm test           # Ende-zu-Ende in Chromium mit Pixel-7-Emulation; SCREENSHOTS=pfad für Bildschirmfotos
```

| Datei | Aufgabe |
|---|---|
| `app/index.html`, `app/styles.css` | Oberfläche: Prüfen, KI, Zurück, Einstellungen |
| `app/app.js` | Ablauf, Teilen, Zurückübersetzen, Einstellungen |
| `app/js/dokumente.js` | Text/Word/PDF/Fotos lesen, Texterkennung, Schwärzen, Export |
| `app/js/ki.js` | eigener OpenAI-kompatibler KI-Server (gleiche Fragen wie `datenwaechter/llm.py`) |
| `app/sw.js` | Offline-Speicher und Android-Teilen-Ziel (`POST ./teilen`) |
| `app/manifest.webmanifest` | Name, Symbole, `share_target` |

Grenzen: Android zeigt Web-Apps erst nach der Installation im Teilen-Menü, iOS gar nicht. Ein eigener KI-Server muss
per https erreichbar sein und Browser-Zugriffe (CORS) erlauben.
