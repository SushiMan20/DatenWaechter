// Ende-zu-Ende-Test der KI-Aktionen (Rechtsklick-Menü) mit echtem Chromium, echtem Python-Scanner und
// simuliertem OpenAI-kompatiblem Server. Aufruf:  node tests/e2e_ki_aktionen.js
// Das echte Kontextmenü lässt sich nicht fernsteuern; der Test ruft dieselbe Funktion auf, die ein Klick auf den
// Menüeintrag auslöst (runAction), und gibt der Test-Kopie der Erweiterung den Tab-Zugriff, den der Rechtsklick
// sonst automatisch gewährt (activeTab).
const { chromium } = require("playwright");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");

const REPO = path.resolve(__dirname, "..");
const PY = process.env.PYTHON || "python3";
const TOKEN = "e2e-token";
const requests = [];

const PAGE = `<!doctype html><meta charset=utf-8><title>Irgendeine Webseite</title>
<style>body{font:15px system-ui;margin:20px;width:560px} textarea,div[contenteditable]{width:100%;box-sizing:border-box;border:1px solid #999;padding:6px;margin:6px 0 14px}</style>
<label>E-Mail-Entwurf</label><textarea id=ta rows=3>Hallo Herr Becker, anbei die Unterlagen. Grüße</textarea>
<label>Editor</label><div id=ce contenteditable>Kommst du morgen zum Termin?</div>
<p id=txt>Dies ist ein langer Artikeltext auf einer normalen Webseite, der zusammengefasst werden soll.</p>`;

function startAi() {
  const srv = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const send = (obj) => { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
      if (req.headers.authorization !== `Bearer ${TOKEN}`) { res.writeHead(401); return res.end("{}"); }
      if (req.url === "/v1/models") return send({ data: [{ id: "schreib-modell" }] });
      const b = JSON.parse(body);
      if (b.response_format) {   // Inhalts-Check: unkritisch
        return send({ choices: [{ message: { content: '{"kategorien":[],"warnung":"","stufe":0}' } }] });
      }
      requests.push(b);
      const inner = /<<<\n([\s\S]*)\n>>>/.exec(b.messages.at(-1).content)[1];
      send({ choices: [{ message: { content: `Neu: ${inner}` } }] });
    });
  });
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

(async () => {
  const ai = await startAi();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "dw-ki-"));
  // Test-Kopie der Erweiterung mit Tab-Zugriff (ersetzt das activeTab-Recht des Rechtsklicks)
  const ext = path.join(tmp, "extension");
  fs.cpSync(path.join(REPO, "extension"), ext, { recursive: true });
  const manifest = JSON.parse(fs.readFileSync(path.join(ext, "manifest.json"), "utf8"));
  manifest.host_permissions = ["<all_urls>"];
  fs.writeFileSync(path.join(ext, "manifest.json"), JSON.stringify(manifest));

  const userData = path.join(tmp, "profil");
  const ctx = await chromium.launchPersistentContext(userData, {
    headless: true, channel: "chromium", viewport: { width: 760, height: 560 },
    args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`],
  });
  let [sw] = ctx.serviceWorkers();
  if (!sw) sw = await ctx.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;
  fs.mkdirSync(path.join(userData, "NativeMessagingHosts"), { recursive: true });
  const sh = path.join(tmp, "host.sh");
  fs.writeFileSync(sh, ["#!/bin/sh", `cd ${JSON.stringify(REPO)}`,
    `export DATENWAECHTER_EINSTELLUNGEN=${JSON.stringify(path.join(tmp, "einstellungen.json"))}`,
    `export DATENWAECHTER_LLM_URL=http://127.0.0.1:${ai.address().port}/v1`, `export DATENWAECHTER_LLM_TOKEN=${TOKEN}`,
    `exec ${PY} -m datenwaechter native-host`, ""].join("\n"), { mode: 0o755 });
  fs.writeFileSync(path.join(userData, "NativeMessagingHosts", "de.datenwaechter.host.json"), JSON.stringify({
    name: "de.datenwaechter.host", description: "test", path: sh, type: "stdio", allowed_origins: [`chrome-extension://${extId}/`],
  }));

  await ctx.route("https://example.org/**", (r) => r.fulfill({ contentType: "text/html", body: PAGE }));
  const page = await ctx.newPage();
  await page.goto("https://example.org/artikel");
  const shotDir = process.env.SHOT_DIR;
  let n = 0;
  const step = (msg) => console.log(`  ✔ ${++n}. ${msg}`);
  const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ url: "https://example.org/*" }))[0].id);
  const run = (id) => sw.evaluate(([id, tabId]) => runAction(id, tabId, 0), [id, tabId]);

  // 1) Aktionen kommen vom lokalen Scanner
  const names = await sw.evaluate(() => buildMenus().then(() => menuItems.map((a) => a.name)));
  assert.ok(names.includes("Umformulieren") && names.includes("Zusammenfassen"), names.join(", "));
  assert.match(await sw.evaluate(() => menuInfo.server), /schreib-modell · lokal/);
  step(`Rechtsklick „Mit KI bearbeiten …“ kennt ${names.length} Aktionen (${names.slice(0, 3).join(", ")} …)`);

  // 1b) Aktionsleiste: öffnet an der Markierung, Tippen filtert, Enter führt aus
  const palette = () => sw.evaluate((tabId) => openPalette(tabId, 0), tabId);
  const paletteOpen = () => page.evaluate(() => !!document.querySelector("datenwaechter-ki"));
  await page.evaluate(() => { ta.value = "hallo herr becker, anbei die unterlagen"; ta.focus(); ta.setSelectionRange(0, ta.value.length); });
  assert.strictEqual(await palette(), true);
  assert.ok(await paletteOpen());
  await page.waitForTimeout(250);   // Einblend-Animation
  if (shotDir) await page.screenshot({ path: path.join(shotDir, "ki-palette-browser-hell.png") });
  await page.keyboard.type("kürz");
  if (shotDir) await page.screenshot({ path: path.join(shotDir, "ki-palette-browser-filter.png") });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("ta").value.startsWith("Neu:"), null, { timeout: 20_000 });
  assert.strictEqual(await page.inputValue("#ta"), "Neu: hallo herr becker, anbei die unterlagen");
  assert.match(requests.at(-1).messages.at(-1).content, /Kürze den Text/);
  step("Aktionsleiste: „kürz“ getippt + Enter → Kürzen ausgeführt, Text ersetzt");

  // 1c) Eigene Anweisung direkt in der Leiste
  await page.evaluate(() => { ta.value = "termin morgen 10 uhr"; ta.focus(); ta.setSelectionRange(0, ta.value.length); });
  await palette();
  await page.keyboard.type("in Reimform");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(250);
  if (shotDir) await page.screenshot({ path: path.join(shotDir, "ki-palette-browser-dunkel.png") });
  await page.emulateMedia({ colorScheme: "light" });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("ta").value === "Neu: termin morgen 10 uhr", null, { timeout: 20_000 });
  assert.match(requests.at(-1).messages.at(-1).content, /Anweisung: in Reimform/);
  step("eigene Anweisung „in Reimform“ aus der Leiste ausgeführt");

  // 1d) Esc schließt ohne Anfrage
  const count = requests.length;
  await page.evaluate(() => { ta.focus(); ta.setSelectionRange(0, 5); });
  await palette();
  await page.keyboard.press("Escape");
  assert.ok(!(await paletteOpen()));
  assert.strictEqual(requests.length, count);
  await page.evaluate(() => { ta.value = "Hallo Herr Becker, anbei die Unterlagen. Grüße"; });
  step("Esc schließt die Leiste, nichts gesendet");

  // 2) Textfeld: Teil markieren -> Umformulieren -> nur die Markierung wird ersetzt
  await page.evaluate(() => { ta.focus(); ta.setSelectionRange(0, 17); });
  let r = await run("umformulieren");
  assert.strictEqual(r.result, "Neu: Hallo Herr Becker");
  assert.strictEqual(await page.inputValue("#ta"), "Neu: Hallo Herr Becker, anbei die Unterlagen. Grüße");
  assert.match(requests.at(-1).messages.at(-1).content, /Formuliere den Text um/);
  if (shotDir) await page.screenshot({ path: path.join(shotDir, "ki-ersetzt.png") });
  step("Textfeld: Markierung umformuliert und ersetzt");

  // 3) Editor (contenteditable): „Antwort entwerfen“ fügt unter dem Text ein
  await page.evaluate(() => { ce.focus(); const rg = document.createRange(); rg.selectNodeContents(ce);
    getSelection().removeAllRanges(); getSelection().addRange(rg); });
  r = await run("antwort-entwerfen");
  const ceText = await page.innerText("#ce");
  assert.ok(ceText.startsWith("Kommst du morgen zum Termin?") && ceText.includes("Neu: Kommst du morgen zum Termin?"), ceText);
  step("Editor: Antwort darunter eingefügt, Original bleibt");

  // 4) Normaler Seitentext: „Zusammenfassen“ zeigt das Ergebnis zum Kopieren, Seite bleibt unverändert
  await page.evaluate(() => { document.activeElement.blur(); const rg = document.createRange(); rg.selectNodeContents(txt);
    getSelection().removeAllRanges(); getSelection().addRange(rg); });
  r = await run("zusammenfassen");
  assert.ok(await page.evaluate(() => !!document.querySelector("datenwaechter-ki")), "Ergebnisfenster fehlt");
  assert.ok((await page.innerText("#txt")).startsWith("Dies ist ein langer Artikeltext"));
  if (shotDir) await page.screenshot({ path: path.join(shotDir, "ki-anzeigen.png") });
  step("Seitentext: Ergebnis wird angezeigt (Kopieren / Schließen)");

  // 5) Nichts markiert -> verständliche Meldung, keine Anfrage an die KI
  const before = requests.length;
  await page.evaluate(() => { document.querySelectorAll("datenwaechter-ki").forEach((x) => x.remove());
    document.activeElement.blur(); getSelection().removeAllRanges(); });
  r = await run("umformulieren");
  assert.strictEqual(r, null);
  assert.strictEqual(requests.length, before);
  step("ohne Markierung: Hinweis „Kein Text markiert“, nichts gesendet");

  await ctx.close();
  ai.close();
  console.log(`✔ KI-Aktionen: alle ${n} Ende-zu-Ende-Prüfungen bestanden`);
})().catch((e) => { console.error(e); process.exit(1); });
