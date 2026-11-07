# Mitmachen

Danke, dass du helfen willst! So klappt es am besten:

## Fehler melden

Bitte ein Issue mit:
- was du gemacht hast (z. B. „PDF in chatgpt.com gezogen“),
- was passiert ist und was du erwartet hättest,
- Version (Einstellungen → unten) und Windows-/Browser-Version.

**Keine echten persönlichen Daten in Issues!** Für Beispiele bitte erfundene Namen, `DE89 3704 0044 0532 0130 00`
(Test-IBAN) oder `example.de`-Adressen verwenden.

## Keine vertraulichen Daten im Repository

Das Repository wird öffentlich. Alles, was einmal committet ist, bleibt in der Historie sichtbar – auch wenn es später
gelöscht wird. Deshalb gilt für Code, Tests, Dokumentation, Bilder und Commit-Nachrichten:

- **Keine echten Schlüssel, Tokens, Passwörter.** Testwerte so, dass man sie als ausgedacht erkennt
  (`sk-proj-AbCdEfGh…0123456789`, `e2e-token`).
- **Keine echten Personen- oder Kundendaten.** Erfundene Namen, `example.de`-Adressen, Test-IBAN
  `DE89 3704 0044 0532 0130 00`. Forschungsdaten (z. B. GraSCCo) nur herunterladen, nie einchecken.
- **Keine internen Server, IP-Adressen oder Modellnamen** eigener Dienste. Beispiele: `ki.firma.example`, `qwen3-chat`.
- **Keine Werkzeug- oder Co-Autor-Zeilen** in Commit-Nachrichten; Commits mit der GitHub-noreply-Adresse.

`tests/test_repo_sauber.py` prüft das bei jedem Push (und lokal mit `pytest`). Interne Begriffe stehen dort nur als
SHA-256-Fingerabdruck; einen neuen Begriff sperrst du mit
`python tests/test_repo_sauber.py --sperren "intern.firma.de"`.

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
