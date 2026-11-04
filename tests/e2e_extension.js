// Ende-zu-Ende-Test der Browser-Erweiterung mit echtem Chromium und echtem Python-Scanner.
// Aufruf:  node tests/e2e_extension.js
// Simuliert außerdem einen eigenen OpenAI-kompatiblen KI-Server (URL + Token) für den Inhalts-Check.
// Braucht: Playwright, Python mit datenwaechter + pypdfium2 + pytesseract (Tesseract mit „deu“) + OpenCV 4 + reportlab.
// Eine Testseite wird unter https://claude.ai/ ausgeliefert, damit die Erweiterung dort aktiv wird.
const { chromium } = require("playwright");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const http = require("node:http");

const REPO = path.resolve(__dirname, "..");
const EXT = path.join(REPO, "extension");
const PY = process.env.PYTHON || "python3";

const PAGE = `<!doctype html><meta charset=utf-8><title>Test</title>
<div id=editor contenteditable style="height:60px;border:1px solid">.</div>
<div id=zone style="height:60px;border:1px dashed">Drop</div>
<input id=file type=file multiple>
<button id=add>Datei hinzufügen</button>
<script>
  window.log = [];
  const read = (f) => new Promise(r => { const fr = new FileReader(); fr.onload = () => r(String(fr.result).split(",")[1]); fr.readAsDataURL(f); });
  const record = async (how, files) => log.push({ how, names: files.map(f => f.name), b64: files.length ? await read(files[0]) : "" });
  editor.addEventListener("paste", e => { e.preventDefault(); log.push({ how: "paste", text: e.clipboardData.getData("text/plain") }); });
  zone.addEventListener("dragover", e => e.preventDefault());
  zone.addEventListener("drop", e => { e.preventDefault(); record("drop", [...e.dataTransfer.files]); });
  file.addEventListener("change", () => record("input", [...file.files]));
  // typischer „Datei hinzufügen“-Knopf: unsichtbares Eingabefeld, das nie ins Dokument eingefügt wird
  add.addEventListener("click", () => { const i = document.createElement("input"); i.type = "file";
    i.addEventListener("change", () => record("hidden-input", [...i.files])); i.click(); });
</script>`;

function py(code) {
  return execFileSync(PY, ["-c", code], { cwd: REPO, encoding: "utf8" });
}

function makeFixtures(dir) {
  py(`
from reportlab.pdfgen import canvas
c = canvas.Canvas(${JSON.stringify(path.join(dir, "Vertrag.pdf"))})
c.setFont("Helvetica", 14)
c.drawString(72, 750, "Vertrag mit Herrn Klaus Becker, IBAN DE89 3704 0044 0532 0130 00")
c.drawString(72, 725, "E-Mail: klaus.becker@example.de")
c.save()
from PIL import Image, ImageDraw, ImageFont
f = ImageFont.truetype("DejaVuSans.ttf", 22)
img = Image.new("RGB", (900, 220), "white"); d = ImageDraw.Draw(img)
d.text((30, 30), "Überweisung an Frau Anna Müller", font=f, fill="black")
d.text((30, 80), "IBAN: DE89 3704 0044 0532 0130 00", font=f, fill="black")
d.text((30, 130), "Betreff: Unterhalt für unsere Tochter", font=f, fill="black")
img.save(${JSON.stringify(path.join(dir, "Screenshot.png"))})`);
}

// Simulierter OpenAI-kompatibler Server: prüft das Token, meldet „private Details“
const TOKEN = "e2e-token-42";
const aiRequests = [];
function startAiServer() {
  const srv = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const send = (code, obj) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
      if (req.headers.authorization !== `Bearer ${TOKEN}`) return send(401, { error: "invalid token" });
      if (req.url === "/v1/models") return send(200, { data: [{ id: "test-modell" }] });
      aiRequests.push(JSON.parse(body));
      const answer = { kategorien: ["intim"], beschreibung: "Nachricht über ein anvertrautes Geheimnis der Nachbarin.",
        warnung: "Du teilst gerade private Details über deine Nachbarin.", stufe: 2 };
      send(200, { choices: [{ message: { role: "assistant", content: JSON.stringify(answer) } }] });
    });
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

(async () => {
  const ai = await startAiServer();
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "dw-e2e-"));
  makeFixtures(userData);
  const ctx = await chromium.launchPersistentContext(userData, {
    headless: true, channel: "chromium", viewport: { width: 780, height: 560 },
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  });
  let [sw] = ctx.serviceWorkers();
  if (!sw) sw = await ctx.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;

  // Native-Messaging-Host für Linux-Chromium im Profilordner registrieren
  const hostDir = path.join(userData, "NativeMessagingHosts");
  fs.mkdirSync(hostDir, { recursive: true });
  const sh = path.join(userData, "host.sh");
  fs.writeFileSync(sh, [
    "#!/bin/sh", `cd ${JSON.stringify(REPO)}`,
    `export DATENWAECHTER_EINSTELLUNGEN=${JSON.stringify(path.join(userData, "einstellungen.json"))}`,
    `export DATENWAECHTER_LLM_URL=http://127.0.0.1:${ai.address().port}/v1`,
    `export DATENWAECHTER_LLM_TOKEN=${TOKEN}`,
    `exec ${PY} -m datenwaechter native-host`, ""].join("\n"), { mode: 0o755 });
  fs.writeFileSync(path.join(hostDir, "de.datenwaechter.host.json"), JSON.stringify({
    name: "de.datenwaechter.host", description: "test", path: sh, type: "stdio",
    allowed_origins: [`chrome-extension://${extId}/`],
  }));

  await ctx.route("https://claude.ai/**", (r) => r.fulfill({ contentType: "text/html", body: PAGE }));
  const page = await ctx.newPage();
  await page.goto("https://claude.ai/new");
  const log = () => page.evaluate(() => window.log);
  const waitLog = (n) => page.waitForFunction((n) => window.log.length === n, n, { timeout: 60_000 });
  const waitDialog = () => page.waitForFunction(() => !!document.querySelector("datenwaechter-ui"), null, { timeout: 60_000 });
  const shotDir = process.env.SHOT_DIR;
  const shot = async (name) => shotDir && page.screenshot({ path: path.join(shotDir, name) });
  const paste = (text) => page.evaluate((text) => { editor.focus(); const d = new DataTransfer(); d.setData("text/plain", text);
    editor.dispatchEvent(new ClipboardEvent("paste", { clipboardData: d, bubbles: true, cancelable: true })); }, text);
  const drop = (name, type) => page.evaluate(([b64, name, type]) => {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)); const d = new DataTransfer();
    d.items.add(new File([bin], name, { type }));
    zone.dispatchEvent(new DragEvent("drop", { dataTransfer: d, bubbles: true, cancelable: true }));
  }, [fs.readFileSync(path.join(userData, name)).toString("base64"), name, type]);
  const ocrB64 = (b64, ext) => {
    const f = path.join(userData, "check" + ext);
    fs.writeFileSync(f, Buffer.from(b64, "base64"));
    return py(`
import sys; sys.path.insert(0, ".")
from datenwaechter.files import load
print(load(${JSON.stringify(f)}).text)`);
  };
  let n = 0;
  const step = (msg) => console.log(`  ✔ ${++n}. ${msg}`);

  // 1) Harmloser Text geht ohne Rückfrage durch
  await paste("Hallo Welt");
  assert.deepStrictEqual((await log())[0], { how: "paste", text: "Hallo Welt" });
  step("harmloser Text wird ohne Rückfrage eingefügt");

  // 2) Sensibler Text -> Warnung -> Enter = „Anonymisiert einfügen“
  await paste("Bitte an Frau Müller, IBAN DE89 3704 0044 0532 0130 00");
  await waitDialog();
  assert.strictEqual((await log()).length, 1, "Seite darf den Text vor der Entscheidung nicht sehen");
  await page.keyboard.press("Enter");
  await waitLog(2);
  assert.strictEqual((await log())[1].text, "Bitte an Frau [PERSON_1], IBAN [IBAN_1]");
  step("persönliche Daten im Text -> anonymisiert eingefügt");

  // 3) Text ohne Personendaten, aber mit Familienthema -> Inhalts-Warnung -> Enter = „Abbrechen“
  await paste("Hallo, kannst du mir helfen? Es geht um das Sorgerecht für unsere Tochter nach der Trennung, das Jugendamt hat geschrieben.");
  await waitDialog();
  await shot("browser-inhalt.png");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.strictEqual((await log()).length, 2, "abgebrochener Text darf nicht ankommen");
  step("Familienthema erkannt (Inhalts-Check) -> abgebrochen");

  // 3b) Text ohne Stichwörter – nur der eigene KI-Server (URL + Token) erkennt, dass er privat ist
  await paste("Kannst du mir helfen, eine Nachricht zu formulieren? Meine Nachbarin hat mir gestern im Treppenhaus anvertraut, " +
    "dass sie seit Monaten heimlich Geld von ihrem Bruder leiht und niemand davon wissen darf. Ich will ihr schreiben, dass ich " +
    "das für mich behalte, aber mir Sorgen mache. Bitte freundlich und kurz, ohne zu belehren, vielleicht mit einem Vorschlag " +
    "für ein Treffen am Wochenende.");
  await waitDialog();
  await shot("browser-ki-server.png");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.strictEqual((await log()).length, 2, "abgebrochener Text darf nicht ankommen");
  assert.ok(aiRequests.length >= 1 && aiRequests[0].model === "test-modell", "KI-Server muss mit Token gefragt worden sein");
  step("eigener KI-Server (URL + Token) erkennt private Details -> abgebrochen");

  // 4) Text-PDF per Büroklammer -> Abbrechen (Tab, Tab, Enter)
  await page.setInputFiles("#file", path.join(userData, "Vertrag.pdf"));
  await waitDialog();
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.strictEqual((await log()).length, 2, "abgebrochene Datei darf nicht ankommen");
  step("PDF über „Datei hinzufügen“ -> Warnung -> abgebrochen");

  // 5) Gleiches PDF per Drag & Drop -> geschwärztes PDF kommt an, Name und IBAN nicht mehr enthalten
  await drop("Vertrag.pdf", "application/pdf");
  await waitDialog();
  await shot("browser-warnung.png");
  await page.keyboard.press("Enter");
  await waitLog(3);
  let e = (await log())[2];
  assert.deepStrictEqual(e.names, ["Vertrag_anonymisiert.pdf"]);
  let text = ocrB64(e.b64, ".pdf");
  assert.ok(!text.includes("Becker") && !text.includes("3704"), text);
  assert.ok(text.includes("Vertrag mit"), "Rest des Dokuments muss lesbar bleiben: " + text);
  step("PDF per Drag & Drop -> geschwärztes PDF (Layout bleibt)");

  // 6) Screenshot (Bild mit Text) per Drag & Drop -> Texterkennung -> geschwärztes Bild
  await drop("Screenshot.png", "image/png");
  await waitDialog();
  await page.keyboard.press("Enter");
  await waitLog(4);
  e = (await log())[3];
  assert.deepStrictEqual(e.names, ["Screenshot_anonymisiert.png"]);
  text = ocrB64(e.b64, ".png");
  assert.ok(!text.includes("Müller") && !text.includes("3704"), text);
  step("Bild mit Text -> OCR -> Funde geschwärzt");

  // 7) Foto über versteckten „Datei hinzufügen“-Knopf -> Gesicht erkannt -> verpixelt
  const chooser = page.waitForEvent("filechooser");
  await page.click("#add");
  await (await chooser).setFiles(path.join(REPO, "tests", "fixtures", "gesicht.jpg"));
  await waitDialog();
  await page.keyboard.press("Enter");
  await waitLog(5);
  e = (await log())[4];
  assert.strictEqual(e.how, "hidden-input");
  assert.deepStrictEqual(e.names, ["gesicht_anonymisiert.jpg"]);
  const faces = py(`
import base64, io, sys; sys.path.insert(0, ".")
from PIL import Image
from datenwaechter.faces import detect
print(len(detect(Image.open(io.BytesIO(base64.b64decode(${JSON.stringify(e.b64)}))))))`).trim();
  assert.strictEqual(faces, "0", "im anonymisierten Foto darf kein Gesicht mehr erkennbar sein");
  step("Foto über versteckten „Datei hinzufügen“-Knopf -> Gesicht verpixelt");

  await ctx.close();
  ai.close();
  console.log(`✔ Erweiterung: alle ${n} Ende-zu-Ende-Prüfungen bestanden`);
})().catch((e) => { console.error(e); process.exit(1); });
