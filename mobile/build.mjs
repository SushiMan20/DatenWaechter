// Baut die Handy-App nach dist/: App-Dateien + Erkennungsregeln der Browser-Erweiterung + Bibliotheken.
// Alles wird mitgeliefert – die App lädt nichts von fremden Servern (CDNs) nach.
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, "dist");
const NM = join(HERE, "node_modules");

rmSync(DIST, { recursive: true, force: true });
mkdirSync(DIST, { recursive: true });

const copy = (from, to) => { mkdirSync(dirname(join(DIST, to)), { recursive: true }); cpSync(from, join(DIST, to), { recursive: true }); };

// 1. App
cpSync(join(HERE, "app"), DIST, { recursive: true });
// 2. Gleiche Regeln wie Browser-Erweiterung und Windows-Programm
copy(join(HERE, "../extension/detectors.js"), "shared/detectors.js");
copy(join(HERE, "../extension/kategorien.js"), "shared/kategorien.js");
// 3. Bibliotheken
const vendor = {
  "vendor/pdfjs/pdf.min.mjs": "pdfjs-dist/build/pdf.min.mjs",
  "vendor/pdfjs/pdf.worker.min.mjs": "pdfjs-dist/build/pdf.worker.min.mjs",
  "vendor/pdfjs/standard_fonts": "pdfjs-dist/standard_fonts",
  "vendor/pdfjs/cmaps": "pdfjs-dist/cmaps",
  "vendor/pdfjs/wasm": "pdfjs-dist/wasm",
  "vendor/pdfjs/LICENSE": "pdfjs-dist/LICENSE",
  "vendor/tesseract/tesseract.min.js": "tesseract.js/dist/tesseract.min.js",
  "vendor/tesseract/worker.min.js": "tesseract.js/dist/worker.min.js",
  "vendor/tesseract/LICENSE": "tesseract.js/LICENSE.md",
  "vendor/tesseract/core/tesseract-core-lstm.wasm.js": "tesseract.js-core/tesseract-core-lstm.wasm.js",
  "vendor/tesseract/core/tesseract-core-simd-lstm.wasm.js": "tesseract.js-core/tesseract-core-simd-lstm.wasm.js",
  "vendor/tesseract/core/tesseract-core-relaxedsimd-lstm.wasm.js": "tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js",
  "vendor/tesseract/core/LICENSE": "tesseract.js-core/LICENSE",
  "vendor/tesseract/lang/deu.traineddata.gz": "@tesseract.js-data/deu/4.0.0_best_int/deu.traineddata.gz",
  "vendor/jspdf.umd.min.js": "jspdf/dist/jspdf.umd.min.js",
  "vendor/jszip.min.js": "jszip/dist/jszip.min.js",
  "vendor/LICENSE-jspdf": "jspdf/LICENSE",
  "vendor/LICENSE-jszip": "jszip/LICENSE.markdown",
  "vendor/tesseract/lang/LICENSE": "@tesseract.js-data/deu/LICENSE",
};
for (const [to, from] of Object.entries(vendor)) {
  const src = join(NM, from);
  try { statSync(src); } catch { if (/LICENSE/.test(to)) continue; throw new Error(`Fehlt: ${from} – erst „npm ci“ ausführen`); }
  copy(src, to);
}

// 4. Service-Worker: Liste der Dateien für den Offline-Betrieb + Version aus dem Inhalt
const files = [];
const walk = (d) => { for (const n of readdirSync(d)) { const p = join(d, n); statSync(p).isDirectory() ? walk(p) : files.push(p); } };
walk(DIST);
const hash = createHash("sha256");
const rel = files.map((p) => relative(DIST, p).split("\\").join("/")).sort();
for (const r of rel) hash.update(r).update(readFileSync(join(DIST, r)));
const version = hash.digest("hex").slice(0, 12);
const vendorHash = createHash("sha256");
for (const r of rel.filter((r) => r.startsWith("vendor/"))) vendorHash.update(r).update(readFileSync(join(DIST, r)));
// Sofort offline: App + kleine Bibliotheken. Texterkennung (~5 MB) und PDF-Schriften kommen beim ersten Gebrauch dazu.
const later = /^(vendor\/tesseract\/(core|lang)\/|vendor\/pdfjs\/(cmaps|standard_fonts|wasm)\/)|LICENSE|\.map$|^sw\.js$/;
const precache = ["./", ...rel.filter((r) => !later.test(r) && r !== "index.html").map((r) => "./" + r)];
const sw = readFileSync(join(DIST, "sw.js"), "utf8")
  .replace("__VERSION__", version)
  .replace("__VENDOR__", vendorHash.digest("hex").slice(0, 12))
  .replace("__PRECACHE__", JSON.stringify(precache, null, 1));
writeFileSync(join(DIST, "sw.js"), sw);

const size = rel.reduce((s, r) => s + statSync(join(DIST, r)).size, 0);
console.log(`dist/ fertig: ${rel.length} Dateien, ${(size / 1e6).toFixed(1)} MB, Version ${version}`);
