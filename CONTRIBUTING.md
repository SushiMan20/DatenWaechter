# Mitmachen

Danke, dass du helfen willst! So klappt es am besten:

## Fehler melden

Bitte ein Issue mit:
- was du gemacht hast (z. B. „PDF in chatgpt.com gezogen“),
- was passiert ist und was du erwartet hättest,
- Version (Einstellungen → unten) und Windows-/Browser-Version.

**Keine echten persönlichen Daten in Issues!** Für Beispiele bitte erfundene Namen, `DE89 3704 0044 0532 0130 00`
(Test-IBAN) oder `example.de`-Adressen verwenden.

## Code beitragen

Der Datenwächter ist derzeit nicht quelloffen: Alle Rechte liegen bei portamedia (siehe [LICENSE](LICENSE)).
Code-Beiträge bitte nur nach Absprache. Wer etwas einreicht, räumt portamedia daran die vollen Nutzungsrechte ein.

```bash
pip install -e ".[dev]"
pytest
node --test tests/detectors.test.js
node tests/e2e_extension.js        # braucht Playwright + Chromium
```

- Neue Erkennungsregeln gehören **in beide** Dateien: `datenwaechter/detectors.py` und `extension/detectors.js` –
  mit einem Test in `tests/test_core.py` und `tests/detectors.test.js` (gleiche Beispiele).
- Jede Regel braucht auch einen Test gegen Fehlalarme (harmlose Texte, die *nicht* anschlagen dürfen).
- Stichwörter für den Inhalts-Check stehen in `datenwaechter/kategorien.json`; danach
  `python -c "import datenwaechter.content_check as c; c.write_extension_categories()"`.
- Oberfläche und Meldungen sind deutsch, in Du-Form, kurz und konkret.
- Windows-spezifisches wird in GitHub Actions auf echtem Windows getestet (`tests/windows_smoke.py`).
