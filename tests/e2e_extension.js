// Ende-zu-Ende-Test der Browser-Erweiterung mit echtem Chromium.
// Aufruf:  node tests/e2e_extension.js   (braucht Playwright und Python mit datenwaechter + reportlab)
// Eine Testseite wird unter https://claude.ai/ ausgeliefert, damit die Erweiterung dort aktiv wird.
const { chromium } = require("playwright");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const REPO = path.resolve(__dirname, "..");
const EXT = path.join(REPO, "extension");
const PY = process.env.PYTHON || "python3";

const PAGE = `<!doctype html><meta charset=utf-8><title>Test</title>
<div id=editor contenteditable style="height:80px;border:1px solid">.</div>
<div id=zone style="height:80px;border:1px dashed">Drop</div>
<input id=file type=file multiple>
<script>
  window.log = [];
  editor.addEventListener("paste", e => { e.preventDefault(); log.push({paste: e.clipboardData.getData("text/plain"),
    files: [...e.clipboardData.files].map(f => f.name)}); });
  zone.addEventListener("dragover", e => e.preventDefault());
  zone.addEventListener("drop", async e => { e.preventDefault();
    const fs = [...e.dataTransfer.files]; log.push({drop: fs.map(f => f.name), text: fs.length ? await fs[0].text() : ""}); });
  file.addEventListener("change", async () => { const fs = [...file.files];
    log.push({input: fs.map(f => f.name), text: fs.length ? await fs[0].text() : ""}); });
</script>`;

function makePdf(dir) {
  const out = path.join(dir, "Vertrag.pdf");
  execFileSync(PY, ["-c", `
from reportlab.pdfgen import canvas
c = canvas.Canvas(${JSON.stringify(out)})
c.drawString(72, 750, "Vertrag mit Herrn Klaus Becker, IBAN DE89 3704 0044 0532 0130 00")
c.drawString(72, 730, "E-Mail: klaus.becker@example.de")
c.save()`]);
  return out;
}

(async () => {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "dw-e2e-"));
  const ctx = await chromium.launchPersistentContext(userData, {
    headless: true, channel: "chromium", viewport: { width: 760, height: 460 }, args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  });
  let [sw] = ctx.serviceWorkers();
  if (!sw) sw = await ctx.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;

  // Native-Messaging-Host für Linux-Chromium im Profilordner registrieren
  const hostDir = path.join(userData, "NativeMessagingHosts");
  fs.mkdirSync(hostDir, { recursive: true });
  const sh = path.join(userData, "host.sh");
  fs.writeFileSync(sh, `#!/bin/sh\ncd ${JSON.stringify(REPO)}\nexec ${PY} -m datenwaechter native-host\n`, { mode: 0o755 });
  fs.writeFileSync(path.join(hostDir, "de.datenwaechter.host.json"), JSON.stringify({
    name: "de.datenwaechter.host", description: "test", path: sh, type: "stdio",
    allowed_origins: [`chrome-extension://${extId}/`],
  }));

  await ctx.route("https://claude.ai/**", (r) => r.fulfill({ contentType: "text/html", body: PAGE }));
  const page = await ctx.newPage();
  await page.goto("https://claude.ai/new");
  const log = () => page.evaluate(() => window.log);
  const dialogOpen = () => page.evaluate(() => !!document.querySelector("datenwaechter-ui"));
  const waitDialog = () => page.waitForFunction(() => !!document.querySelector("datenwaechter-ui"));

  // 1) Harmloser Text geht ohne Rückfrage durch
  await page.evaluate(() => { const d = new DataTransfer(); d.setData("text/plain", "Hallo Welt");
    editor.dispatchEvent(new ClipboardEvent("paste", { clipboardData: d, bubbles: true, cancelable: true })); });
  assert.deepStrictEqual((await log())[0], { paste: "Hallo Welt", files: [] });
  assert.strictEqual(await dialogOpen(), false);

  // 2) Sensibler Text -> Warnung -> Enter = „Anonymisiert einfügen“
  await page.evaluate(() => { editor.focus(); const d = new DataTransfer();
    d.setData("text/plain", "Bitte an Frau Müller, IBAN DE89 3704 0044 0532 0130 00");
    editor.dispatchEvent(new ClipboardEvent("paste", { clipboardData: d, bubbles: true, cancelable: true })); });
  await waitDialog();
  assert.strictEqual((await log()).length, 1, "Seite darf den Text vor der Entscheidung nicht sehen");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.log.length === 2);
  assert.strictEqual((await log())[1].paste, "Bitte an Frau [PERSON_1], IBAN [IBAN_1]");

  // 3) Textdatei per Drag & Drop -> anonymisierte Kopie
  await page.evaluate(() => { const d = new DataTransfer();
    d.items.add(new File(["Kontakt: klaus.becker@example.de, Tel. 030 12345678"], "kunden.csv", { type: "text/csv" }));
    zone.dispatchEvent(new DragEvent("drop", { dataTransfer: d, bubbles: true, cancelable: true })); });
  await waitDialog();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.log.length === 3);
  assert.deepStrictEqual((await log())[2], { drop: ["kunden_anonymisiert.csv"], text: "Kontakt: [EMAIL_1], Tel. [TELEFON_1]" });

  // 4) PDF über die Büroklammer -> lokaler Python-Scanner -> Abbrechen (Tab, Tab, Enter)
  const pdf = makePdf(userData);
  await page.setInputFiles("#file", pdf);
  await waitDialog();
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.strictEqual((await log()).length, 3, "abgebrochene Datei darf nicht ankommen");

  // 5) gleiches PDF per Drop -> anonymisiert -> kommt als .txt an
  const b64 = fs.readFileSync(pdf).toString("base64");
  await page.evaluate((b64) => { const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)); const d = new DataTransfer();
    d.items.add(new File([bin], "Vertrag.pdf", { type: "application/pdf" }));
    zone.dispatchEvent(new DragEvent("drop", { dataTransfer: d, bubbles: true, cancelable: true })); }, b64);
  await waitDialog();
  if (process.env.SHOT_DIR) await page.screenshot({ path: path.join(process.env.SHOT_DIR, "browser-warnung.png") });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.log.length === 4);
  const last = (await log())[3];
  assert.deepStrictEqual(last.drop, ["Vertrag_anonymisiert.txt"]);
  assert.ok(last.text.includes("[PERSON_1]") && last.text.includes("[IBAN_1]") && !last.text.includes("Becker"), last.text);

  await ctx.close();
  console.log("✔ Erweiterung: alle 5 Ende-zu-Ende-Prüfungen bestanden");
})().catch((e) => { console.error(e); process.exit(1); });
