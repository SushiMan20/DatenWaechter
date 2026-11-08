// Ende-zu-Ende-Test der Handy-App in einem echten Chromium mit Pixel-7-Emulation.
// Aufruf:  npm run build && npm test          (SCREENSHOTS=../docs/handy  → zusätzlich Bildschirmfotos)
// Testdateien (Text-PDF, gescanntes PDF, Foto) erzeugt der Test selbst im Browser – kein Python nötig.
import { chromium, devices } from "playwright";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { dirname, extname, join, normalize } from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const GESICHT = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "gesicht.jpg"));
const SHOTS = process.env.SCREENSHOTS;
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png", ".wasm": "application/wasm",
  ".gz": "application/gzip", ".pfb": "application/octet-stream", ".ttf": "font/ttf", ".bcmap": "application/octet-stream" };

// ------------------------------------------------------------------ Server: App + eigener „KI-Server“
const app = createServer(async (req, res) => {
  const p = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  const file = join(DIST, p.endsWith("/") ? p + "index.html" : p);
  try {
    const body = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch { res.writeHead(404); res.end("nicht gefunden"); }
});

const kiAnfragen = [];
const ki = createServer((req, res) => {
  const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
  if (req.method === "OPTIONS") { res.writeHead(204, cors); return res.end(); }
  const send = (obj, status = 200) => { res.writeHead(status, { ...cors, "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
  if (req.headers.authorization !== "Bearer geheim-123") return send({ error: "unauthorized" }, 401);
  if (req.url.endsWith("/models")) return send({ data: [{ id: "test-modell" }, { id: "anderes-modell" }] });
  let raw = "";
  req.on("data", (c) => { raw += c; });
  req.on("end", () => {
    const body = JSON.parse(raw);
    kiAnfragen.push(body);
    const user = body.messages.at(-1).content;
    const text = typeof user === "string" ? user : user[0].text;
    let antwort;
    if (body.messages[0].content.includes("Schreibassistent")) {
      const inhalt = text.split("<<<\n")[1].split("\n>>>")[0];
      antwort = `„Kurz: ${inhalt.split(/[.!?]/)[0]}.“`;
    } else if (text.startsWith("Finde in dem Text")) {
      antwort = JSON.stringify({ namen: text.includes("Wenzeslaus Brummer") ? ["Wenzeslaus Brummer"] : [], adressen: [], geburtsdaten: [] });
    } else {
      antwort = "```json\n" + JSON.stringify({ beschreibung: "Ein Schreiben über das Sorgerecht für ein Kind", familie: true, kinder: true }) + "\n```";
    }
    send({ choices: [{ message: { role: "assistant", content: antwort } }] });
  });
});

await new Promise((r) => app.listen(0, "127.0.0.1", r));
await new Promise((r) => ki.listen(0, "127.0.0.1", r));
const URL_APP = `http://localhost:${app.address().port}/`;
const URL_KI = `http://127.0.0.1:${ki.address().port}/v1`;

// ------------------------------------------------------------------ Browser
const browser = await chromium.launch();
const context = await browser.newContext({ ...devices["Pixel 7"], locale: "de-DE", permissions: ["clipboard-read", "clipboard-write"] });
await context.addInitScript(() => {
  // navigator.share abfangen: geteilte Dateien landen in window.__geteilt
  window.__geteilt = [];
  navigator.canShare = () => true;
  navigator.share = async (d) => {
    const files = [];
    for (const f of d.files || []) files.push({ name: f.name, type: f.type, b64: btoa(String.fromCharCode(...new Uint8Array(await f.arrayBuffer()))) });
    window.__geteilt.push({ text: d.text, files });
  };
});
const page = await context.newPage();
const fehler = [];
page.on("pageerror", (e) => fehler.push(e.message));
page.on("console", (m) => { if (m.type() === "error") fehler.push(m.text()); });

let nr = 0;
const schritt = (t) => console.log(`\n▶ ${++nr}. ${t}`);
const ok = (t) => console.log(`  ✔ ${t}`);
const foto = async (name, ziel) => {
  if (!SHOTS) return;
  await mkdir(SHOTS, { recursive: true });
  await page.evaluate((sel) => {
    document.getElementById("toast").hidden = true;
    if (sel) window.scrollTo({ top: document.querySelector(sel).getBoundingClientRect().top + window.scrollY - 76, behavior: "instant" });
  }, ziel);
  await page.waitForTimeout(250);
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
};
const bereit = () => page.waitForFunction(() => document.documentElement.dataset.bereit === "1");
const textVon = (sel) => page.locator(sel).innerText();

const BRIEF = `Sehr geehrte Frau Dr. Wagner,

im Verfahren zum Sorgerecht für unseren Sohn bitte ich um Rückruf unter 0171 2345678.
Der Unterhalt geht wie besprochen auf mein Konto DE89 3704 0044 0532 0130 00.

Mit freundlichen Grüßen
Thomas Schneider
Lindenstraße 12, 50667 Köln
thomas.schneider@example.de`;

try {
  schritt("App öffnen, Service-Worker aktiv");
  await page.goto(URL_APP);
  await bereit();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await bereit();
  assert.ok(await page.evaluate(() => Boolean(navigator.serviceWorker.controller)), "Service-Worker steuert die Seite");
  ok("Service-Worker steuert die App");
  await foto("01-start");

  schritt("Text einfügen → Funde, Thema, Platzhalter");
  await page.evaluate((t) => navigator.clipboard.writeText(t), BRIEF);
  await page.click("#btn-einfuegen");
  await page.waitForSelector("#ergebnis:not([hidden]) .fund");
  const urteil = await textVon("#urteil");
  assert.match(urteil, /sensible Angaben gefunden/);
  const funde = await page.locator(".fund").allInnerTexts();
  for (const label of ["IBAN", "Telefonnummer", "E-Mail", "Straße", "Name"]) assert.ok(funde.some((f) => f.includes(label)), `Fund ${label}: ${funde}`);
  assert.match(await textVon("#thema"), /Familienunterlagen/);
  let anon = await textVon("#anon-text");
  assert.ok(anon.includes("[IBAN_1]") && !anon.includes("DE89"), anon);
  assert.ok(!anon.includes("0171 2345678") && !anon.includes("Lindenstraße 12"), anon);
  ok(`${funde.length} Funde, Thema „Familienunterlagen“, IBAN → [IBAN_1]`);
  await foto("02-text-funde");

  schritt("Fund antippen → bleibt stehen; Kopieren liefert geschützten Text");
  await page.locator(".fund", { hasText: "Telefonnummer" }).click();
  anon = await textVon("#anon-text");
  assert.ok(anon.includes("0171 2345678"), "Telefonnummer bleibt nach Antippen");
  await page.locator(".fund", { hasText: "Telefonnummer" }).click();
  await page.click("#kopieren");
  const kopiert = await page.evaluate(() => navigator.clipboard.readText());
  assert.ok(kopiert.includes("[IBAN_1]") && !kopiert.includes("0171 2345678") && !kopiert.includes("DE89"), kopiert);
  ok("Ausnahme funktioniert, Zwischenablage enthält nur Platzhalter");

  schritt("Geschützt teilen (z. B. an ChatGPT)");
  await page.click("#teilen");
  await page.waitForFunction(() => window.__geteilt.length === 1);
  const geteilt1 = await page.evaluate(() => window.__geteilt[0]);
  assert.ok(geteilt1.text.includes("[PERSON_1]") && !geteilt1.text.includes("Wagner"), geteilt1.text);
  ok("Teilen-Menü bekommt den anonymisierten Text");

  schritt("KI-Antwort zurückübersetzen");
  await page.click('.tabs [data-gehe="zurueck"]');
  await page.fill("#zurueck-eingabe", "Hallo [PERSON_1], ich habe die Überweisung auf [IBAN_1] geprüft. Kopie an [EMAIL_1]!");
  const zurueck = await textVon("#zurueck-text");
  assert.ok(zurueck.includes("Wagner") && zurueck.includes("DE89 3704 0044 0532 0130 00") && zurueck.includes("thomas.schneider@example.de"), zurueck);
  assert.match(await textVon("#zurueck-info"), /3 Platzhalter ersetzt/);
  ok("Platzhalter → echte Angaben");
  await foto("05-zurueck");

  // Testdateien im Browser bauen (jsPDF der App)
  const dateien = await page.evaluate(async (brief) => {
    await new Promise((ok) => { const s = document.createElement("script"); s.src = "vendor/jspdf.umd.min.js"; s.onload = ok; document.head.append(s); });
    const { jsPDF } = window.jspdf;
    const b64 = async (blob) => btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
    // 1) PDF mit echtem Text
    const p1 = new jsPDF({ unit: "pt", format: "a4" });
    p1.setFontSize(12);
    brief.split("\n").forEach((z, i) => p1.text(z, 60, 80 + i * 18));
    // 2) „gescanntes“ PDF: nur ein Bild, kein Text
    const zeichne = (w, h, zeilen, size) => {
      const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#111"; ctx.font = `${size}px Arial, Helvetica, sans-serif`;
      zeilen.forEach((z, i) => ctx.fillText(z, size * 2, size * 3 + i * size * 1.6));
      return c;
    };
    const scan = zeichne(1240, 1754, ["Arztbrief", "", "Patient: Herr Jonas Becker", "geb. am 14.03.1985", "IBAN: DE89 3704 0044 0532 0130 00", "Diagnose: Asthma bronchiale"], 34);
    const p2 = new jsPDF({ unit: "pt", format: "a4" });
    p2.addImage(scan.toDataURL("image/jpeg", 0.92), "JPEG", 0, 0, 595.28, 841.89);
    // 3) Foto/Screenshot
    const bild = zeichne(1000, 560, ["Kontoauszug", "Frau Anna Keller", "IBAN DE89 3704 0044 0532 0130 00", "Telefon 0171 2345678"], 36);
    return {
      textpdf: await b64(p1.output("blob")),
      scanpdf: await b64(p2.output("blob")),
      foto: await b64(await new Promise((ok) => bild.toBlob(ok, "image/png"))),
    };
  }, BRIEF);
  const datei = (name, mimeType, b64) => ({ name, mimeType, buffer: Buffer.from(b64, "base64") });

  schritt("PDF mit Text über „Datei“ → geschwärzte Vorschau → geschwärztes PDF teilen");
  await page.click('.tabs [data-gehe="pruefen"]');
  await page.click("#btn-leeren");
  await page.setInputFiles("#datei", datei("Brief ans Jugendamt.pdf", "application/pdf", dateien.textpdf));
  await page.waitForSelector(".seite canvas");
  await page.waitForSelector(".fund");
  const pdfFunde = await page.locator(".fund").allInnerTexts();
  assert.ok(pdfFunde.some((f) => f.includes("IBAN")), pdfFunde.join(" | "));
  assert.match(await textVon("#urteil"), /gefunden/);
  assert.match(await textVon(".seite .nr"), /Brief ans Jugendamt\.pdf/);
  await page.waitForTimeout(400);
  await foto("03-pdf-geschwaerzt", "#vorschau-karte");
  await page.click("#teilen");
  await page.waitForFunction(() => window.__geteilt.length === 2);
  const geteilt2 = await page.evaluate(() => window.__geteilt[1]);
  assert.equal(geteilt2.files.length, 1);
  assert.equal(geteilt2.files[0].name, "Brief ans Jugendamt-geschwaerzt.pdf");
  const pdfBytes = Buffer.from(geteilt2.files[0].b64, "base64");
  assert.equal(pdfBytes.subarray(0, 4).toString(), "%PDF");
  const restText = await page.evaluate(async (b64) => {
    const lib = await import("./vendor/pdfjs/pdf.min.mjs");
    lib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.mjs";
    const pdf = await lib.getDocument({ data: Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)) }).promise;
    const t = await (await pdf.getPage(1)).getTextContent();
    return t.items.map((i) => i.str).join("");
  }, geteilt2.files[0].b64);
  assert.equal(restText.trim(), "", "geschwärztes PDF enthält keinen versteckten Text mehr");
  ok(`PDF erkannt (${pdfFunde.length} Funde), geteilt als ${geteilt2.files[0].name} ohne Textebene`);

  schritt("Gescanntes PDF → Texterkennung auf dem Handy");
  await page.click("#btn-leeren");
  const t0 = Date.now();
  await page.setInputFiles("#datei", datei("Arztbrief-Scan.pdf", "application/pdf", dateien.scanpdf));
  await page.waitForSelector(".fund", { timeout: 120000 });
  const scanFunde = await page.locator(".fund").allInnerTexts();
  assert.ok(scanFunde.some((f) => f.includes("IBAN")), scanFunde.join(" | "));
  assert.ok(scanFunde.some((f) => f.includes("Becker")), scanFunde.join(" | "));
  assert.ok(scanFunde.some((f) => f.includes("Geburtsdatum")), scanFunde.join(" | "));
  assert.match(await textVon("#urteil"), /Texterkennung|gefunden/);
  ok(`OCR in ${((Date.now() - t0) / 1000).toFixed(1)} s: ${scanFunde.length} Funde (IBAN, Name, Geburtsdatum)`);

  schritt("Foto über die Kamera-Schaltfläche → Balken + selbst schwärzen");
  await page.click("#btn-leeren");
  await page.setInputFiles("#foto", datei("Kontoauszug.png", "image/png", dateien.foto));
  await page.waitForSelector(".fund", { timeout: 60000 });
  await page.waitForSelector(".seite canvas");
  const fotoFunde = await page.locator(".fund").allInnerTexts();
  assert.ok(fotoFunde.some((f) => f.includes("IBAN")) && fotoFunde.some((f) => f.includes("Keller")), fotoFunde.join(" | "));
  await page.click("#schwaerz-hinweis");
  const box = await page.locator(".seite canvas").boundingBox();
  const von = { x: box.x + box.width * 0.6, y: box.y + box.height * 0.08 }, bis = { x: box.x + box.width * 0.95, y: box.y + box.height * 0.2 };
  await page.mouse.move(von.x, von.y);
  await page.mouse.down();
  await page.mouse.move((von.x + bis.x) / 2, (von.y + bis.y) / 2, { steps: 4 });
  await page.mouse.move(bis.x, bis.y, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(400);
  const schwarz = await page.evaluate(() => {
    const c = document.querySelector(".seite canvas");
    const d = c.getContext("2d").getImageData(Math.round(c.width * 0.78), Math.round(c.height * 0.14), 1, 1).data;
    return d[0] + d[1] + d[2];
  });
  assert.equal(schwarz, 0, "selbst gezogener Bereich ist schwarz");
  await page.click("#schwaerz-hinweis");
  await foto("04-foto-geschwaerzt", "#vorschau-karte");
  await page.click("#teilen");
  await page.waitForFunction(() => window.__geteilt.length === 3);
  const geteilt3 = await page.evaluate(() => window.__geteilt[2]);
  assert.equal(geteilt3.files[0].name, "Kontoauszug-geschwaerzt.png");
  ok("Foto erkannt, eigener Balken gezeichnet, geschwärztes PNG geteilt");

  // Findet die App auf einer geteilten Datei (Bild oder PDF-Seite) noch ein Gesicht?
  const gesichterIn = (datei) => page.evaluate(async ({ b64, typ }) => {
    const { gesichterAuf } = await import("./js/gesichter.js");
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    let c;
    if (typ === "application/pdf") {
      const lib = await import("./vendor/pdfjs/pdf.min.mjs");
      lib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.mjs";
      const seite = await (await lib.getDocument({ data: bytes }).promise).getPage(1);
      const vp = seite.getViewport({ scale: 1100 / seite.getViewport({ scale: 1 }).width });
      c = Object.assign(document.createElement("canvas"), { width: vp.width, height: vp.height });
      await seite.render({ canvas: c, canvasContext: c.getContext("2d"), viewport: vp }).promise;
    } else {
      const bmp = await createImageBitmap(new Blob([bytes], { type: typ }));
      c = Object.assign(document.createElement("canvas"), { width: bmp.width, height: bmp.height });
      c.getContext("2d").drawImage(bmp, 0, 0);
    }
    return (await gesichterAuf(c)).length;
  }, { b64: datei.b64, typ: datei.type });

  schritt("Foto mit Gesicht → erkannt und beim Teilen verpixelt");
  await page.click("#btn-leeren");
  const tg = Date.now();
  await page.setInputFiles("#foto", { name: "Portrait.jpg", mimeType: "image/jpeg", buffer: GESICHT });
  await page.waitForSelector(".fund[data-gesicht]", { timeout: 60000 });
  assert.match(await textVon(".fund[data-gesicht]"), /Gesicht auf Fotos\s+1 erkannt/);
  assert.match(await textVon("#urteil"), /1 Gesicht gefunden/);
  await page.locator(".fund[data-gesicht]").click();               // antippen = nicht verpixeln
  assert.match(await textVon(".fund[data-gesicht]"), /bleibt/);
  assert.match(await textVon("#teilen-text"), /^Teilen$/);
  await page.locator(".fund[data-gesicht]").click();
  await page.click("#teilen");
  await page.waitForFunction(() => window.__geteilt.length === 4);
  const geteilt4 = await page.evaluate(() => window.__geteilt[3]);
  assert.equal(geteilt4.files[0].name, "Portrait-geschwaerzt.jpg");
  assert.equal(await gesichterIn(geteilt4.files[0]), 0, "im geteilten Foto ist kein Gesicht mehr zu erkennen");
  ok(`Gesicht in ${((Date.now() - tg) / 1000).toFixed(1)} s gefunden, abschaltbar, geteiltes Foto verpixelt`);
  await foto("08-gesicht-verpixelt", "#vorschau-karte");

  schritt("PDF mit Passfoto (Lebenslauf) → Gesicht auf der Textseite verpixelt");
  await page.click("#btn-leeren");
  const lebenslauf = await page.evaluate(async (b64) => {
    const { jsPDF } = window.jspdf;
    const p = new jsPDF({ unit: "pt", format: "a4" });
    p.setFontSize(20); p.text("Lebenslauf", 60, 80);
    p.setFontSize(12); ["Berufserfahrung", "2019 – heute: Projektleitung", "2015 – 2019: Entwicklung"].forEach((z, i) => p.text(z, 60, 130 + i * 18));
    p.addImage("data:image/jpeg;base64," + b64, "JPEG", 360, 60, 180, 180);
    return btoa(String.fromCharCode(...new Uint8Array(await p.output("blob").arrayBuffer())));
  }, GESICHT.toString("base64"));
  await page.setInputFiles("#datei", datei("Lebenslauf.pdf", "application/pdf", lebenslauf));
  await page.waitForSelector(".fund[data-gesicht]", { timeout: 60000 });
  await page.click("#teilen");
  await page.waitForFunction(() => window.__geteilt.length === 5);
  const geteilt5 = await page.evaluate(() => window.__geteilt[4]);
  assert.equal(geteilt5.files[0].name, "Lebenslauf-geschwaerzt.pdf");
  assert.equal(await gesichterIn(geteilt5.files[0]), 0, "im geteilten PDF ist kein Gesicht mehr zu erkennen");
  ok("Passfoto im PDF gefunden und im geteilten PDF verpixelt");

  schritt("Android „Teilen → Datenwächter“: Datei aus anderer App");
  await page.evaluate(() => {
    const form = Object.assign(document.createElement("form"), { method: "POST", action: "teilen", enctype: "multipart/form-data" });
    const input = Object.assign(document.createElement("input"), { type: "file", name: "dateien" });
    const dt = new DataTransfer();
    dt.items.add(new File(["Kündigung: Herr Max Mustermann, IBAN DE89 3704 0044 0532 0130 00"], "kuendigung.txt", { type: "text/plain" }));
    input.files = dt.files;
    const text = Object.assign(document.createElement("input"), { name: "text", value: "" });
    form.append(input, text);
    document.body.append(form);
    form.submit();
  });
  await page.waitForURL((u) => !u.search.includes("geteilt"), { timeout: 15000 });
  await bereit();
  await page.waitForSelector(".fund");
  assert.match(await textVon("#dateiliste"), /kuendigung\.txt/);
  assert.ok((await page.locator(".fund").allInnerTexts()).some((f) => f.includes("Mustermann")));
  ok("geteilte Datei kommt an und wird sofort geprüft");

  schritt("KI-Antwort per „Teilen → Datenwächter“ → landet in „Zurück“");
  await page.evaluate(() => {
    const form = Object.assign(document.createElement("form"), { method: "POST", action: "teilen", enctype: "multipart/form-data" });
    form.append(Object.assign(document.createElement("input"), { name: "text", value: "Entwurf: Sehr geehrter [PERSON_1], bitte auf [IBAN_1] überweisen." }));
    document.body.append(form);
    form.submit();
  });
  await page.waitForURL((u) => !u.search.includes("geteilt"));
  await bereit();
  await page.waitForSelector("#tab-zurueck:not([hidden]) #zurueck-ergebnis:not([hidden])");
  const zurueck2 = await textVon("#zurueck-text");
  assert.ok(zurueck2.includes("DE89 3704 0044 0532 0130 00"), zurueck2);
  ok("Zuordnung überlebt Neustart, Antwort wird automatisch zurückübersetzt");

  schritt("Laborwerte ohne Person: kein Fund, keine Warnung – „Medizinische Inhalte“ einschaltbar");
  await page.click('.tabs [data-gehe="pruefen"]');
  await page.click("#btn-leeren");
  await page.fill("#eingabe", "Bitte interpretieren: CRP 200 mg/l, Leukozyten 15.000, Diagnose: Pneumonie, Therapie mit Amoxicillin.");
  await page.waitForSelector("#ergebnis:not([hidden])");
  assert.match(await textVon("#urteil"), /Keine persönlichen Daten/);
  assert.ok(await page.locator("#thema").isHidden(), "ohne Person keine Themen-Warnung");
  await page.click('.tabs [data-gehe="einstellungen"]');
  assert.ok(!(await page.isChecked("#opt-medizin")) && await page.isChecked("#opt-firmen"), "Standard: Medizin aus, Firmen an");
  await page.check("#opt-medizin");
  await page.click('.tabs [data-gehe="pruefen"]');
  await page.waitForSelector(".fund");
  const med = await page.locator(".fund").allInnerTexts();
  assert.ok(med.some((f) => f.includes("Laborwert")) && med.some((f) => f.includes("Medikament")), `Medizin-Funde: ${med}`);
  await page.reload();
  await bereit();
  await page.click('.tabs [data-gehe="einstellungen"]');
  assert.ok(await page.isChecked("#opt-medizin"), "Einstellung bleibt nach Neustart");
  await page.uncheck("#opt-medizin");
  ok(`ohne Person: nichts markiert; mit „Medizinische Inhalte“: ${med.length} Funde`);

  schritt("Eigener KI-Server (Adresse + Token): Verbindung testen");
  await page.click('.tabs [data-gehe="einstellungen"]');
  await page.click("#ki-aktiv");
  await page.fill("#ki-url", URL_KI);
  await page.fill("#ki-token", "falsch");
  await page.click("#ki-testen");
  await page.waitForSelector("#ki-status.fehler");
  assert.match(await textVon("#ki-status"), /Token prüfen/);
  await page.fill("#ki-token", "geheim-123");
  await page.check("#opt-anonym");
  await page.check("#opt-namen");
  await page.click("#ki-testen");
  await page.waitForSelector("#ki-status.ok");
  assert.equal(await page.inputValue("#ki-modell"), "test-modell");
  assert.match(await textVon("#status-text"), /KI-Server: 127\.0\.0\.1/);
  ok((await textVon("#ki-status")).replace(/^✔ /, ""));
  await foto("07-einstellungen", "#tab-einstellungen");

  schritt("KI findet Namen ohne Herr/Frau + prüft das Thema");
  kiAnfragen.length = 0;
  await page.click('.tabs [data-gehe="pruefen"]');
  await page.click("#btn-leeren");
  await page.fill("#eingabe", "Wenzeslaus Brummer (7) wohnt beim Vater. Sorgerecht klären, Rückruf an 0171 2345678.");
  await page.waitForSelector(".fund .ki", { timeout: 15000 });
  assert.match(await textVon("#thema"), /Daten über Kinder/);
  assert.match(await textVon("#thema"), /Geprüft von: KI/);
  assert.ok(kiAnfragen.length >= 2);
  for (const a of kiAnfragen) assert.ok(!JSON.stringify(a).includes("0171 2345678"), "Server sieht keine Telefonnummer");
  anon = await textVon("#anon-text");
  assert.ok(!anon.includes("Wenzeslaus Brummer"), anon);
  ok("seltener Name „Wenzeslaus Brummer“ von der KI gefunden, Telefonnummer ging nie an den Server");

  schritt("KI-Aktion „Kürzen“: anonym hin, echt zurück");
  kiAnfragen.length = 0;
  await page.click('.tabs [data-gehe="ki"]');
  await page.fill("#ki-eingabe", "Bitte überweise 50 Euro auf DE89 3704 0044 0532 0130 00. Danke dir sehr, das war ein toller Abend.");
  await page.locator(".aktion", { hasText: "Kürzen" }).click();
  await page.waitForFunction(() => document.querySelector("#ki-text").textContent.startsWith("Kurz:"));
  const kurz = await textVon("#ki-text");
  assert.ok(kurz.includes("DE89 3704 0044 0532 0130 00"), kurz);
  assert.ok(!JSON.stringify(kiAnfragen).includes("DE89"), "Server hat die IBAN nie gesehen");
  assert.match(await textVon("#ki-info"), /eigener Server/);
  ok(kurz);
  await foto("06-ki-aktionen", "#tab-ki .kopf.aussen");

  schritt("Offline: App startet ohne Netz und prüft weiter");
  await context.setOffline(true);
  await page.reload();
  await bereit();
  await page.fill("#eingabe", "Meine IBAN: DE89 3704 0044 0532 0130 00");
  await page.waitForSelector(".fund");
  await context.setOffline(false);
  ok("läuft offline");

  const echteFehler = fehler.filter((f) => !/Failed to load resource|net::ERR_INTERNET_DISCONNECTED|status of 401/.test(f));
  assert.deepEqual(echteFehler, [], "keine Fehler in der Konsole");
  console.log(`\n✔ Alle ${nr} Schritte bestanden`);
} catch (e) {
  console.error("\n✘ Fehler:", e.message);
  if (fehler.length) console.error("Konsole:", fehler.join("\n"));
  await page.screenshot({ path: "test-fehler.png" }).catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
  app.close();
  ki.close();
}
