// Dateien lesen (Text, Word, PDF, Fotos), Texterkennung, Schwärzen und Export – alles im Browser.
// Ein Dokument: { name, typ, mime, datei, text, seiten: [{ breite, hoehe, ptBreite, ptHoehe, original, woerter, manuell }] }
// Jedes Wort: { start, end, x, y, w, h } – Position im Gesamttext und auf der Seite (Pixel der Vorschau).

const MAX_SEITEN = 20;
const PDF_BREITE = 1100;        // Pixelbreite einer PDF-Seite in der Vorschau
const BILD_MAX = 2000;          // längste Bildseite für Vorschau + Texterkennung
const OCR_BREITE = 2000;        // gescannte PDF-Seiten werden dafür größer gerendert

const basis = new URL("../", import.meta.url);
const pfad = (p) => new URL(p, basis).href;

const geladen = {};
function skript(src) {
  geladen[src] ||= new Promise((ok, fehler) => {
    const s = document.createElement("script");
    s.src = pfad(src);
    s.onload = ok;
    s.onerror = () => fehler(new Error(`${src} konnte nicht geladen werden`));
    document.head.append(s);
  });
  return geladen[src];
}

let pdfjs;
async function pdfLib() {
  if (!pdfjs) {
    pdfjs = await import(pfad("vendor/pdfjs/pdf.min.mjs"));
    pdfjs.GlobalWorkerOptions.workerSrc = pfad("vendor/pdfjs/pdf.worker.min.mjs");
  }
  return pdfjs;
}

// ------------------------------------------------------------------ Texterkennung
let ocrWorker = null;
let ocrMelden = () => {};
export async function ocrBereitmachen(melden = () => {}) {
  ocrMelden = melden;
  if (!ocrWorker) {
    ocrWorker = (async () => {
      await skript("vendor/tesseract/tesseract.min.js");
      return globalThis.Tesseract.createWorker("deu", 1, {
        workerPath: pfad("vendor/tesseract/worker.min.js"),
        corePath: pfad("vendor/tesseract/core"),
        langPath: pfad("vendor/tesseract/lang"),
        workerBlobURL: false,
        cacheMethod: "none",          // der Service-Worker hält die Dateien schon offline vor
        logger: (m) => ocrMelden(m),
      });
    })().catch((e) => { ocrWorker = null; throw e; });
  }
  return ocrWorker;
}
export async function ocrOffline() {
  if (!("caches" in globalThis)) return false;
  const [lang, core] = await Promise.all([
    caches.match(pfad("vendor/tesseract/lang/deu.traineddata.gz")),
    Promise.all(["", "simd-", "relaxedsimd-"].map((v) => caches.match(pfad(`vendor/tesseract/core/tesseract-core-${v}lstm.wasm.js`)))),
  ]);
  return Boolean(lang && core.some(Boolean));
}

/** Erkennt Text auf einer Leinwand. faktor: Umrechnung OCR-Pixel → Vorschau-Pixel. */
async function erkenne(canvas, faktor, offset, melden) {
  const worker = await ocrBereitmachen((m) => {
    if (m.status === "recognizing text") melden?.(`Texterkennung … ${Math.round(m.progress * 100)} %`, m.progress);
    else if (/loading|initializ/.test(m.status)) melden?.("Texterkennung wird vorbereitet …", null);
  });
  const { data } = await worker.recognize(canvas, {}, { blocks: true, text: true });
  let text = "";
  const woerter = [];
  for (const block of data.blocks || []) {
    for (const absatz of block.paragraphs || []) {
      for (const zeile of absatz.lines || []) {
        const teile = (zeile.words || []).filter((w) => w.text && w.text.trim());
        teile.forEach((w, i) => {
          if (i) text += " ";
          const start = offset + text.length;
          text += w.text;
          const b = w.bbox;
          woerter.push({ start, end: offset + text.length, x: b.x0 * faktor, y: b.y0 * faktor, w: (b.x1 - b.x0) * faktor, h: (b.y1 - b.y0) * faktor });
        });
        if (teile.length) text += "\n";
      }
      text += "\n";
    }
  }
  return { text, woerter };
}

// ------------------------------------------------------------------ Laden
export const art = (datei) => {
  const n = (datei.name || "").toLowerCase(), t = datei.type || "";
  if (t === "application/pdf" || n.endsWith(".pdf")) return "pdf";
  if (t.startsWith("image/") || /\.(jpe?g|png|webp|gif|heic|heif|bmp)$/.test(n)) return "bild";
  if (n.endsWith(".docx") || t.includes("wordprocessingml")) return "docx";
  return "text";
};

export async function laden(datei, melden = () => {}) {
  const typ = art(datei);
  const doc = { name: datei.name || "Datei", typ, mime: datei.type, datei, text: "", seiten: [], hinweis: "" };
  if (typ === "text") doc.text = await datei.text();
  else if (typ === "docx") doc.text = await wordText(datei);
  else if (typ === "bild") await bildLaden(doc, melden);
  else await pdfLaden(doc, melden);
  return doc;
}

async function wordText(datei) {
  await skript("vendor/jszip.min.js");
  const zip = await globalThis.JSZip.loadAsync(datei);
  const xml = await zip.file("word/document.xml")?.async("string");
  if (!xml) throw new Error("Keine gültige Word-Datei (.docx)");
  const dom = new DOMParser().parseFromString(xml, "application/xml");
  const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
  const absaetze = [];
  for (const p of dom.getElementsByTagNameNS(W, "p")) {
    let t = "";
    for (const el of p.getElementsByTagNameNS(W, "*")) {
      if (el.localName === "t") t += el.textContent;
      else if (el.localName === "tab") t += "\t";
      else if (el.localName === "br" || el.localName === "cr") t += "\n";
    }
    absaetze.push(t);
  }
  return absaetze.join("\n");
}

const leinwand = (w, h) => { const c = document.createElement("canvas"); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; };
const alsBlob = (canvas, typ = "image/jpeg", q = 0.92) => new Promise((ok) => canvas.toBlob(ok, typ, q));

async function bildLaden(doc, melden) {
  melden("Foto wird gelesen …", null);
  let bmp;
  try { bmp = await createImageBitmap(doc.datei, { imageOrientation: "from-image" }); } catch {
    throw new Error("Dieses Bildformat kann der Browser nicht öffnen (z. B. HEIC) – bitte als JPEG oder PNG teilen.");
  }
  const f = Math.min(1, BILD_MAX / Math.max(bmp.width, bmp.height));
  const c = leinwand(bmp.width * f, bmp.height * f);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  const { text, woerter } = await erkenne(c, 1, 0, melden);
  doc.text = text.trim() ? text : "";
  doc.seiten.push({ breite: c.width, hoehe: c.height, ptBreite: c.width * 0.75, ptHoehe: c.height * 0.75,
                    original: await alsBlob(c), woerter, manuell: [], gesichter: await gesichter(c) });
  doc.quelle = "Texterkennung";
}

async function pdfLaden(doc, melden) {
  const lib = await pdfLib();
  melden("PDF wird geöffnet …", null);
  const aufgabe = lib.getDocument({
    data: new Uint8Array(await doc.datei.arrayBuffer()), isEvalSupported: false,
    standardFontDataUrl: pfad("vendor/pdfjs/standard_fonts/"), cMapUrl: pfad("vendor/pdfjs/cmaps/"), cMapPacked: true,
    wasmUrl: pfad("vendor/pdfjs/wasm/"),
  });
  const pdf = await aufgabe.promise;
  const anzahl = Math.min(pdf.numPages, MAX_SEITEN);
  if (pdf.numPages > MAX_SEITEN) doc.hinweis = `Sehr lange PDF: nur die ersten ${MAX_SEITEN} von ${pdf.numPages} Seiten werden geprüft.`;
  let ocrSeiten = 0;
  for (let n = 1; n <= anzahl; n++) {
    melden(`Seite ${n} von ${anzahl} …`, (n - 1) / anzahl);
    const page = await pdf.getPage(n);
    const basisVp = page.getViewport({ scale: 1 });
    const scale = PDF_BREITE / basisVp.width;
    const vp = page.getViewport({ scale });
    const offset = doc.text.length;
    const inhalt = await page.getTextContent();
    let { text, woerter } = pdfText(lib, inhalt, vp, offset);
    let c;
    if (text.replace(/\s/g, "").length < 20) {        // kein Text drin → gescannte Seite → Texterkennung
      ocrSeiten++;
      const ocrScale = OCR_BREITE / basisVp.width;
      const gross = leinwand(basisVp.width * ocrScale, basisVp.height * ocrScale);
      await page.render({ canvas: gross, canvasContext: gross.getContext("2d"), viewport: page.getViewport({ scale: ocrScale }) }).promise;
      ({ text, woerter } = await erkenne(gross, scale / ocrScale, offset, (t, p) => melden(`Seite ${n}: ${t}`, p)));
      c = leinwand(vp.width, vp.height);
      c.getContext("2d").drawImage(gross, 0, 0, c.width, c.height);
      gross.width = gross.height = 0;
    } else {
      c = leinwand(vp.width, vp.height);
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, c.width, c.height);
      await page.render({ canvas: c, canvasContext: ctx, viewport: vp }).promise;
    }
    doc.text += text + "\n\n";
    doc.seiten.push({ breite: c.width, hoehe: c.height, ptBreite: basisVp.width, ptHoehe: basisVp.height,
                      original: await alsBlob(c), woerter, manuell: [], gesichter: [] });
    c.width = c.height = 0;
    page.cleanup();
  }
  await aufgabe.destroy();
  doc.quelle = ocrSeiten === anzahl ? "Texterkennung (gescannt)" : ocrSeiten ? `PDF-Text + Texterkennung (${ocrSeiten} S.)` : "PDF-Text";
}

/** Text einer PDF-Seite mit Positionen; Leerzeichen/Zeilenumbrüche aus den Abständen ableiten. */
function pdfText(lib, inhalt, vp, offset) {
  let text = "";
  const woerter = [];
  let letzte = null;
  for (const item of inhalt.items) {
    if (typeof item.str !== "string") continue;
    const tx = lib.Util.transform(vp.transform, item.transform);
    const hoehe = Math.hypot(tx[2], tx[3]) || 10;
    const x = tx[4], basisY = tx[5], breite = item.width * vp.scale;
    if (letzte && item.str) {
      const neueZeile = Math.abs(basisY - letzte.y) > hoehe * 0.5;
      const ende = text.at(-1);
      if (neueZeile && ende !== "\n") text += "\n";
      else if (!neueZeile && ende && !/\s/.test(ende) && !/^\s/.test(item.str) && x - letzte.ende > hoehe * 0.15) text += " ";
    }
    if (item.str) {
      const start = offset + text.length;
      text += item.str;
      woerter.push({ start, end: offset + text.length, x, y: basisY - hoehe * 0.9, w: breite, h: hoehe * 1.15 });
      letzte = { y: basisY, ende: x + breite };
    }
    if (item.hasEOL && text.at(-1) !== "\n") text += "\n";
  }
  return { text, woerter };
}

async function gesichter(canvas) {
  if (!("FaceDetector" in globalThis)) return [];
  try {
    const found = await new globalThis.FaceDetector({ fastMode: false, maxDetectedFaces: 20 }).detect(canvas);
    return found.map((f) => { const b = f.boundingBox; return { x: b.x - b.width * 0.15, y: b.y - b.height * 0.2, w: b.width * 1.3, h: b.height * 1.4 }; });
  } catch { return []; }
}

// ------------------------------------------------------------------ Schwärzen
/** Balken für einen Fund auf einer Seite (Teilwörter anteilig, Nachbarn in einer Zeile zusammengefasst). */
export function balken(seite, fund) {
  const rects = [];
  for (const w of seite.woerter) {
    if (w.end <= fund.start || w.start >= fund.end) continue;
    const len = Math.max(1, w.end - w.start);
    const a = Math.max(0, fund.start - w.start) / len, b = Math.min(len, fund.end - w.start) / len;
    rects.push({ x: w.x + w.w * a, y: w.y, w: w.w * (b - a), h: w.h });
  }
  const out = [];
  for (const r of rects) {
    const z = out.find((o) => Math.abs(o.y + o.h / 2 - (r.y + r.h / 2)) < Math.max(o.h, r.h) * 0.5 && r.x - (o.x + o.w) < r.h * 1.5 && o.x - (r.x + r.w) < r.h * 1.5);
    if (z) {
      const x1 = Math.min(z.x, r.x), y1 = Math.min(z.y, r.y);
      z.w = Math.max(z.x + z.w, r.x + r.w) - x1; z.h = Math.max(z.y + z.h, r.y + r.h) - y1; z.x = x1; z.y = y1;
    } else out.push({ ...r });
  }
  const pad = (r) => ({ x: r.x - 3, y: r.y - 2, w: r.w + 6, h: r.h + 4 });
  return out.map(pad);
}

/** Zeichnet eine Seite mit Balken. kaesten: [{x,y,w,h,label?,art:"balken"|"gesicht"|"manuell"}] */
export async function zeichne(seite, canvas, kaesten) {
  canvas.width = seite.breite;
  canvas.height = seite.hoehe;
  const ctx = canvas.getContext("2d");
  const bmp = await createImageBitmap(seite.original);
  ctx.drawImage(bmp, 0, 0);
  bmp.close?.();
  for (const k of kaesten) {
    if (k.art === "gesicht") { verpixeln(ctx, k); continue; }
    ctx.fillStyle = "#000";
    ctx.fillRect(k.x, k.y, k.w, k.h);
    if (k.label) {
      let size = Math.min(k.h * 0.62, 26);
      ctx.font = `600 ${size}px system-ui, sans-serif`;
      let breite = ctx.measureText(k.label).width;
      if (breite > k.w - 6) { size *= (k.w - 6) / breite; ctx.font = `600 ${size}px system-ui, sans-serif`; breite = ctx.measureText(k.label).width; }
      if (size >= 7) {
        ctx.fillStyle = "#fff";
        ctx.textBaseline = "middle";
        ctx.fillText(k.label, k.x + (k.w - breite) / 2, k.y + k.h / 2);
      }
    }
  }
}

function verpixeln(ctx, k) {
  const x = Math.max(0, Math.round(k.x)), y = Math.max(0, Math.round(k.y));
  const w = Math.min(ctx.canvas.width - x, Math.round(k.w)), h = Math.min(ctx.canvas.height - y, Math.round(k.h));
  if (w < 2 || h < 2) return;
  const block = Math.max(8, Math.round(Math.min(w, h) / 8));
  const klein = leinwand(Math.ceil(w / block), Math.ceil(h / block));
  const kctx = klein.getContext("2d");
  kctx.drawImage(ctx.canvas, x, y, w, h, 0, 0, klein.width, klein.height);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(klein, 0, 0, klein.width, klein.height, x, y, w, h);
  ctx.restore();
}

// ------------------------------------------------------------------ Export
const basisName = (n) => n.replace(/\.[^.]+$/, "") || "dokument";

/** Fertige Datei zum Teilen: geschwärzte PDF/Bild oder anonymisierter Text. canvases: pro Seite die gezeichnete Leinwand. */
export async function exportieren(doc, canvases, anonText) {
  if (doc.typ === "bild") {
    const png = doc.mime === "image/png" && doc.seiten[0].breite * doc.seiten[0].hoehe < 2.5e6;
    const blob = await alsBlob(canvases[0], png ? "image/png" : "image/jpeg", 0.9);
    return new File([blob], `${basisName(doc.name)}-geschwaerzt.${png ? "png" : "jpg"}`, { type: blob.type });
  }
  if (doc.typ === "pdf") {
    await skript("vendor/jspdf.umd.min.js");
    const { jsPDF } = globalThis.jspdf;
    let pdf = null;
    for (const [i, s] of doc.seiten.entries()) {
      const fmt = [s.ptBreite, s.ptHoehe], lage = s.ptBreite > s.ptHoehe ? "landscape" : "portrait";
      if (!pdf) pdf = new jsPDF({ unit: "pt", format: fmt, orientation: lage, compress: true });
      else pdf.addPage(fmt, lage);
      const jpeg = await alsBlob(canvases[i], "image/jpeg", 0.88);
      pdf.addImage(new Uint8Array(await jpeg.arrayBuffer()), "JPEG", 0, 0, s.ptBreite, s.ptHoehe);
    }
    pdf.setProperties({ title: `${basisName(doc.name)} (geschwärzt)`, creator: "Datenwächter" });
    return new File([pdf.output("blob")], `${basisName(doc.name)}-geschwaerzt.pdf`, { type: "application/pdf" });
  }
  return new File([anonText], `${basisName(doc.name)}-anonymisiert.txt`, { type: "text/plain" });
}
