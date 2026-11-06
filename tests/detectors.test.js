// node --test tests/  –  prüft, dass die Browser-Regeln dasselbe finden wie die Python-Regeln.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const DW = require("../extension/detectors.js");

const py = fs.readFileSync(path.join(__dirname, "test_core.py"), "utf8");
const BEISPIEL = py.split('"""')[1];
const HARMLOS = [
  "Das Meeting ist am 01.02.2024 um 14:30 Uhr.",
  "Wir haben 12345 Euro Umsatz und 40000 Nutzer.",
  "Version 1.2.3 ist stabil, Ticket #123456789.",
  "Die Funktion hat 3 Parameter und gibt 0 zurück.",
];

test("findet alles im Beispiel", () => {
  const found = Object.fromEntries(DW.scan(BEISPIEL).map((f) => [f.text, f.kind]));
  const expected = {
    "DE89 3704 0044 0532 0130 00": "IBAN", "Müller": "PERSON", "Klaus Becker": "PERSON",
    "klaus.becker@example.de": "EMAIL", "+49 30 1234 5678": "TELEFON", "Hauptstraße 12a": "ADRESSE",
    "10115 Berlin": "ADRESSE", "86095742719": "STEUER_ID", "03.04.1985": "GEBURTSDATUM",
    "4111 1111 1111 1111": "KREDITKARTE", "postgres://admin:geheim123@db.intern:5432/kunden": "ZUGANGSDATEN_URL",
    "192.168.10.5": "IP_ADRESSE",
  };
  for (const [t, k] of Object.entries(expected)) assert.strictEqual(found[t], k, t);
  assert.ok(DW.scan(BEISPIEL).some((f) => f.kind === "API_SCHLUESSEL" && f.text.startsWith("sk-ant-")));
});

test("keine Fehlalarme", () => {
  for (const t of HARMLOS) assert.deepStrictEqual(DW.scan(t), [], t);
});

test("anonymisieren und zurück", () => {
  const a = new DW.Anonymizer();
  const anon = a.anonymize("Frau Müller schreibt an Frau Müller: IBAN DE89 3704 0044 0532 0130 00");
  assert.ok(!anon.includes("Müller") && !anon.includes("DE89"));
  assert.strictEqual(anon.split("[PERSON_1]").length - 1, 2);
  assert.strictEqual(a.restore("[PERSON_1] / [IBAN_1]"), "Müller / DE89 3704 0044 0532 0130 00");
});

test("Inhalts-Check wie in Python", () => {
  const v = DW.contentCheck("Arztbrief: Diagnose Depression. Kopie an meinen Ehemann wegen Sorgerecht.");
  assert.ok(v.categories.includes("Gesundheitsdaten") && v.categories.includes("Familienunterlagen"));
  assert.strictEqual(v.severity, 3);
  for (const t of ["Kannst du diese Python-Funktion optimieren? Sie sortiert eine Liste von Zahlen.",
    "Fehlerdiagnose im Build-Prozess: Version 3.1 schlägt bei den Unit-Tests fehl.",
    "Wie mache ich ein Rezept für Apfelkuchen ohne Zucker?"]) assert.strictEqual(DW.contentCheck(t).warning, null, t);
});

test("übernimmt Platzhalter-Zuordnung", () => {
  const a = new DW.Anonymizer();
  a.importMapping({ "[PERSON_2]": "Müller", kaputt: "x" });
  assert.strictEqual(a.anonymize("Frau Müller und Frau Schmidt"), "Frau [PERSON_2] und Frau [PERSON_3]");
});

test("Hinweise ohne doppelte Wörter", () => {
  const v = DW.contentCheck("Familiengericht Musterstadt – Sorgerecht");
  assert.strictEqual(v.hints.length, new Set(v.hints).size, v.hints.join(","));
  assert.strictEqual(DW.contentCheck("Die Familie Familie Familie").warning, null);
});

test("Straße ohne ganzen Satz davor", () => {
  const faelle = [
    ["wohnt in der Hauptstraße 12, 10115 Berlin", "Hauptstraße 12"],
    ["Büro: Karl-Marx-Straße 5a", "Karl-Marx-Straße 5a"],
    ["Abholung Bad Homburger Weg 3", "Bad Homburger Weg 3"],
    ["Lieferung an Kölner Straße 17", "Kölner Straße 17"],
    ["Nach der Trennung von meinem Ehemann Herrn Thomas Schneider wohnt Lena in der Hauptstraße 12", "Hauptstraße 12"],
  ];
  for (const [text, adresse] of faelle) {
    const found = DW.scan(text);
    assert.ok(found.some((f) => f.kind === "ADRESSE" && f.text === adresse), `${text} -> ${JSON.stringify(found.map((f) => f.text))}`);
  }
  assert.ok(DW.scan(faelle[4][0]).some((f) => f.kind === "PERSON" && f.text === "Thomas Schneider"), "Name darf nicht verschluckt werden");
});

test("IBAN mit OCR-Verwechslern", () => {
  for (const t of ["DE89 37O4 OO44 O532 O13O OO", "DE 89 3704 0044 0532 0130 00", "DE89 3704 0044 0532 0l30 00"]) {
    assert.deepStrictEqual(DW.scan(`IBAN: ${t}`).map((f) => f.kind), ["IBAN"], t);
  }
  assert.deepStrictEqual(DW.scan("IBAN: DE89 37O4 OO44 O532 O13O O1"), []);
});

test("gleiche Person, gleicher Platzhalter", () => {
  const a = new DW.Anonymizer();
  assert.strictEqual(a.anonymize("Herrn Thomas Schneider ... Sehr geehrter Herr Schneider, Frau Mia Schneider ist informiert."),
    "Herrn [PERSON_1] ... Sehr geehrter Herr [PERSON_1], Frau [PERSON_2] ist informiert.");
  const b = new DW.Anonymizer();
  assert.strictEqual(b.anonymize("Herr Thomas Schneider, Frau Mia Schneider, Herr Schneider"), "Herr [PERSON_1], Frau [PERSON_2], Herr [PERSON_3]");
});
