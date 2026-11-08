// Gesichter finden – auf dem Gerät, ohne Bibliothek und ohne Server, auch auf dem iPhone.
// Dieselben Haar-Kaskaden und dasselbe Verfahren wie im Windows-Programm (datenwaechter/faces.py, dort OpenCV
// cv2.CascadeClassifier.detectMultiScale), hier Schritt für Schritt nachgebaut – bis auf die Rundung genau, damit
// beide Programme dieselben Gesichter finden (geprüft in tests/test_gesichter_js.py).
import KASKADEN from "./gesichter-daten.js";

const SCHRITT = 1.1;            // scaleFactor
const NACHBARN = 6;             // minNeighbors
const GRUPPE_EPS = 0.2;         // wie OpenCV
const f32 = Math.fround;

/** cvRound: auf die nächste ganze Zahl, genau halbe Werte zur geraden. */
function rund(v) {
  const r = Math.round(v);
  return r - v === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

// ------------------------------------------------------------------ Vorbereitung
const vorbereitet = new Map();
function kaskade(name) {
  if (!vorbereitet.has(name)) {
    const k = KASKADEN[name];
    const n = k.stuempfe.length / 4;
    const s = { breite: k.breite, hoehe: k.hoehe, anzahl: Int32Array.from(k.anzahl),
      stufen: Float32Array.from(k.stufen, (t) => f32(f32(t) - f32(1e-5))),    // OpenCV: THRESHOLD_EPS
      merkmal: new Int32Array(n), schwelle: new Float32Array(n), links: new Float32Array(n), rechts: new Float32Array(n),
      rechtecke: Int32Array.from(k.merkmale.filter((_, i) => i % 5 !== 4)),  // je Merkmal 3 × (x, y, b, h)
      gw: new Float32Array(n * 3) };                                           // Gewichte je Stumpf
    const gewichte = Float32Array.from(k.merkmale.filter((_, i) => i % 5 === 4));
    for (let i = 0; i < n; i++) {
      s.merkmal[i] = k.stuempfe[4 * i];
      s.schwelle[i] = k.stuempfe[4 * i + 1];
      s.links[i] = k.stuempfe[4 * i + 2];
      s.rechts[i] = k.stuempfe[4 * i + 3];
      s.gw.set(gewichte.subarray(s.merkmal[i] * 3, s.merkmal[i] * 3 + 3), i * 3);
    }
    vorbereitet.set(name, s);
  }
  return vorbereitet.get(name);
}

// ------------------------------------------------------------------ Bildvorbereitung
/** Graustufen wie Pillow (convert("L")). daten: RGBA-Pixel (ImageData.data). */
export function grau(daten, breite, hoehe) {
  const out = new Uint8Array(breite * hoehe);
  for (let i = 0, j = 0; i < out.length; i++, j += 4) {
    out[i] = (daten[j] * 19595 + daten[j + 1] * 38470 + daten[j + 2] * 7471 + 0x8000) >> 16;
  }
  return out;
}

/** Koeffizienten der bilinearen Verkleinerung (cv2.resize INTER_LINEAR_EXACT: Festkomma mit 8 Bit). */
function koeffizienten(quelle, ziel) {
  const skala = 1 / (ziel / quelle);
  const ofs = new Int32Array(ziel), c0 = new Int32Array(ziel), c1 = new Int32Array(ziel);
  for (let d = 0; d < ziel; d++) {
    const f = skala * (d + 0.5) - 0.5;
    const i = Math.floor(f);
    if (i >= 0 && quelle > 1 && i < quelle - 1) {
      ofs[d] = i;
      c1[d] = rund((f - i) * 256);
      c0[d] = 256 - c1[d];
    } else {                       // Rand: nur das äußerste Pixel
      ofs[d] = i < 0 ? 0 : quelle - 1;
      c0[d] = 256;
    }
  }
  return { ofs, c0, c1 };
}

function verkleinern(g, b, h, zb, zh) {
  if (zb === b && zh === h) return g;
  const kx = koeffizienten(b, zb), ky = koeffizienten(h, zh);
  const zeilen = new Int32Array(h * zb);          // waagerecht verkleinert, 8 Bit Nachkommastellen
  for (let y = 0; y < h; y++) {
    const q = y * b, z = y * zb;
    for (let x = 0; x < zb; x++) {
      const o = q + kx.ofs[x];
      zeilen[z + x] = g[o] * kx.c0[x] + (kx.c1[x] ? g[o + 1] * kx.c1[x] : 0);
    }
  }
  const out = new Uint8Array(zb * zh);
  for (let y = 0; y < zh; y++) {
    const a = ky.ofs[y] * zb, c0 = ky.c0[y], c1 = ky.c1[y];
    const n = c1 ? a + zb : a;
    for (let x = 0; x < zb; x++) {
      out[y * zb + x] = Math.min(255, (zeilen[a + x] * c0 + zeilen[n + x] * c1 + 32768) >> 16);
    }
  }
  return out;
}

function integral(g, b, h) {
  const st = b + 1;
  const sum = new Int32Array(st * (h + 1)), sq = new Float64Array(st * (h + 1));
  for (let y = 0; y < h; y++) {
    let zs = 0, zq = 0;
    for (let x = 0; x < b; x++) {
      const v = g[y * b + x];
      zs += v;
      zq += v * v;
      const p = (y + 1) * st + x + 1;
      sum[p] = sum[p - st] + zs;
      sq[p] = sq[p - st] + zq;
    }
  }
  return { sum, sq, st };
}

// ------------------------------------------------------------------ Erkennung (eine Kaskade)
/** Die Vergrößerungsstufen, in denen gesucht wird (wie detectMultiScale). */
function skalen(k, b, h, minGroesse) {
  const out = [];
  for (let faktor = 1; ; faktor *= SCHRITT) {
    const wb = rund(k.breite * faktor), wh = rund(k.hoehe * faktor);
    if (wb > b || wh > h) break;
    if (wb < minGroesse || wh < minGroesse) continue;
    out.push(f32(faktor));
  }
  return out;
}

const groesse = (k, b, h, sc) => {
  const sb = rund(f32(b / sc)), sh = rund(f32(h / sc));
  return { sb, sh, arbeitB: Math.max(sb + 1 - k.breite, 0), arbeitH: Math.max(sh + 1 - k.hoehe, 0), schritt: sc >= 2 ? 1 : 2 };
};

/** Alle Fensterpositionen einer Vergrößerungsstufe, an denen die Kaskade anschlägt (vor dem Zusammenfassen). */
function treffer(k, g, b, h, sc) {
  const kb = k.breite, kh = k.hoehe;
  const { sb, sh, arbeitB, arbeitH, schritt } = groesse(k, b, h, sc);
  const out = [];
  if (!arbeitB || !arbeitH) return out;
  const { anzahl, stufen, merkmal, schwelle, links, rechts, rechtecke, gw } = k;
  const nStufen = stufen.length, nStuempfe = merkmal.length;
  const { sum, sq, st } = integral(verkleinern(g, b, h, sb, sh), sb, sh);
  const ofs = k.ofs ||= new Int32Array(nStuempfe * 12);
  for (let j = 0; j < nStuempfe; j++) {          // Eckpunkte jedes Rechtecks als Versatz im Integralbild
    for (let r = 0; r < 3; r++) {
      const m = (merkmal[j] * 3 + r) * 4, o = (j * 3 + r) * 4;
      const x = rechtecke[m], y = rechtecke[m + 1], w = rechtecke[m + 2], hh = rechtecke[m + 3];
      ofs[o] = y * st + x;
      ofs[o + 1] = y * st + x + w;
      ofs[o + 2] = (y + hh) * st + x;
      ofs[o + 3] = (y + hh) * st + x + w;
    }
  }
  const n0 = st + 1, n1 = st + kb - 1, n2 = (kh - 1) * st + 1, n3 = (kh - 1) * st + kb - 1;   // Normierungsrechteck
  const flaeche = (kb - 2) * (kh - 2);
  const fb = rund(f32(kb * sc)), fh = rund(f32(kh * sc));
  for (let y = 0; y < arbeitH; y += schritt) {
    for (let x = 0; x < arbeitB; x += schritt) {
      const p = y * st + x;
      const s = sum[p + n0] - sum[p + n1] - sum[p + n2] + sum[p + n3];
      const q = sq[p + n0] - sq[p + n1] - sq[p + n2] + sq[p + n3];
      let nf = flaeche * q - s * s;
      if (!(nf > 0)) continue;
      nf = Math.sqrt(nf);
      const norm = f32(1 / nf);
      if (!(flaeche * norm < 0.1)) continue;      // fast einfarbig: übergehen
      let ergebnis = 1, j = 0;
      for (let stufe = 0; stufe < nStufen; stufe++) {
        let t = 0;
        for (const ende = j + anzahl[stufe]; j < ende; j++) {
          const o = j * 12, w = j * 3;
          let wert = gw[w] * (sum[p + ofs[o]] - sum[p + ofs[o + 1]] - sum[p + ofs[o + 2]] + sum[p + ofs[o + 3]])
            + gw[w + 1] * (sum[p + ofs[o + 4]] - sum[p + ofs[o + 5]] - sum[p + ofs[o + 6]] + sum[p + ofs[o + 7]]);
          const w2 = gw[w + 2];
          if (w2 !== 0) wert += w2 * (sum[p + ofs[o + 8]] - sum[p + ofs[o + 9]] - sum[p + ofs[o + 10]] + sum[p + ofs[o + 11]]);
          t += f32(wert * norm) < schwelle[j] ? links[j] : rechts[j];
        }
        if (t < stufen[stufe]) { ergebnis = -stufe; break; }
      }
      if (ergebnis > 0) out.push([rund(f32(x * sc)), rund(f32(y * sc)), fb, fh]);
      if (ergebnis === 0) x += schritt;              // gleich an der ersten Stufe gescheitert: ein Feld weiter
    }
  }
  return out;
}

/** cv2.groupRectangles: ähnliche Fenster zusammenfassen, Gruppen mit zu wenigen Treffern verwerfen. */
function gruppieren(r, schwelle, eps = GRUPPE_EPS) {
  const n = r.length, eltern = Int32Array.from({ length: n }, (_, i) => i);
  const wurzel = (i) => { while (eltern[i] !== i) i = eltern[i] = eltern[eltern[i]]; return i; };
  const aehnlich = (a, b) => {
    const d = eps * (Math.min(a[2], b[2]) + Math.min(a[3], b[3])) * 0.5;
    return Math.abs(a[0] - b[0]) <= d && Math.abs(a[1] - b[1]) <= d &&
      Math.abs(a[0] + a[2] - b[0] - b[2]) <= d && Math.abs(a[1] + a[3] - b[1] - b[3]) <= d;
  };
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) if (aehnlich(r[i], r[j])) eltern[wurzel(i)] = wurzel(j);
  const gruppen = new Map();
  for (let i = 0; i < n; i++) {
    const w = wurzel(i);
    const g = gruppen.get(w) || [0, 0, 0, 0, 0];
    for (let k = 0; k < 4; k++) g[k] += r[i][k];
    g[4]++;
    gruppen.set(w, g);
  }
  const mittel = [...gruppen.values()].map((g) => {
    const s = f32(1 / g[4]);
    return [...g.slice(0, 4).map((v) => rund(f32(v * s))), g[4]];
  });
  return mittel.filter((a, i) => a[4] > schwelle && !mittel.some((b, j) => {
    if (j === i || b[4] <= schwelle) return false;
    const dx = rund(b[2] * eps), dy = rund(b[3] * eps);
    return a[0] >= b[0] - dx && a[1] >= b[1] - dy && a[0] + a[2] <= b[0] + b[2] + dx && a[1] + a[3] <= b[1] + b[3] + dy &&
      (b[4] > Math.max(3, a[4]) || a[4] < 3);
  })).map((a) => a.slice(0, 4));
}

function spiegeln(g, b, h) {
  const out = new Uint8Array(g.length);
  for (let y = 0; y < h; y++) for (let x = 0; x < b; x++) out[y * b + x] = g[y * b + b - 1 - x];
  return out;
}

function ueberlappung(a, b) {
  const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]));
  const iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const schnitt = ix * iy;
  const vereinigt = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - schnitt;
  return vereinigt ? schnitt / vereinigt : 0;
}

const LAEUFE = [["frontal", false], ["profil", false], ["profil", true]];   // von vorn, Profil, gespiegeltes Profil

/**
 * Zerlegt die Suche in Aufgaben: je Lauf und Vergrößerungsstufe eine (mit geschätztem Aufwand).
 * Bewusst ohne Histogramm-Ausgleich – Begründung in datenwaechter/faces.py.
 */
function planen(pixel, b, h) {
  const min = Math.max(24, Math.floor(Math.min(b, h) / 25));
  const aufgaben = [];
  LAEUFE.forEach(([name, gespiegelt], lauf) => {
    const k = kaskade(name);
    for (const sc of skalen(k, b, h, min)) {
      const { sb, sh, arbeitB, arbeitH, schritt } = groesse(k, b, h, sc);
      aufgaben.push({ lauf, name, gespiegelt, sc, kosten: Math.ceil(arbeitB / schritt) * Math.ceil(arbeitH / schritt) + sb * sh / 4 });
    }
  });
  return { pixel, aufgaben };
}

/** Treffer je Lauf zusammenfassen, gespiegelte zurückrechnen, Doppelte (über 30 % Überlappung) weglassen. */
function zusammenfuehren(aufgaben, ergebnisse, b) {
  const gefunden = [];
  LAEUFE.forEach(([, gespiegelt], lauf) => {
    const kand = aufgaben.flatMap((a, i) => (a.lauf === lauf ? ergebnisse[i] : []));
    for (const [x, y, w, hh] of gruppieren(kand, NACHBARN)) {
      const x0 = gespiegelt ? b - x - w : x;
      const kasten = [x0, y, x0 + w, y + hh];
      if (!gefunden.some((a) => ueberlappung(kasten, a) > 0.3)) gefunden.push(kasten);
    }
  });
  return gefunden;
}

function rechnen(pixel, b, h, a, cache) {
  const bild = a.gespiegelt ? (cache.gespiegelt ||= spiegeln(pixel, b, h)) : pixel;
  return treffer(kaskade(a.name), bild, b, h, a.sc);
}

/**
 * Gesichter in einem Graustufenbild (Werte wie Pillow „L“). Liefert Kästen [x0, y0, x1, y1] in Pixeln –
 * genau wie datenwaechter.faces.detect: von vorn, im Profil, im gespiegelten Profil.
 */
export function finde(g, b, h) {
  const { pixel, aufgaben } = planen(g, b, h);
  const cache = {};
  return zusammenfuehren(aufgaben, aufgaben.map((a) => rechnen(pixel, b, h, a, cache)), b);
}

// ------------------------------------------------------------------ Im Hintergrund, auf mehreren Kernen
let helfer = null;          // Promise → Liste von Workern ([] = geht nicht, dann im Vordergrund)
function helferHolen() {
  helfer ||= (async () => {
    if (typeof Worker !== "function") return [];
    const n = Math.max(1, Math.min(4, (globalThis.navigator?.hardwareConcurrency || 2) - 1));
    const liste = [];
    try {
      for (let i = 0; i < n; i++) liste.push(new Worker(new URL("./gesichter-worker.js", import.meta.url), { type: "module" }));
      await Promise.all(liste.map((w) => new Promise((ok, fehler) => {
        const zeit = setTimeout(() => fehler(new Error("Hilfsprozess startet nicht")), 15000);
        w.addEventListener("message", (e) => { if (e.data?.bereit) { clearTimeout(zeit); ok(); } }, { once: true });
        w.addEventListener("error", (e) => { clearTimeout(zeit); fehler(e); }, { once: true });
      })));
      return liste;
    } catch {
      liste.forEach((w) => w.terminate());
      return [];
    }
  })();
  return helfer;
}

let auftrag = 0;
async function imHintergrund(pixel, b, h, aufgaben) {
  const liste = await helferHolen();
  if (!liste.length) return null;
  const last = liste.map(() => ({ kosten: 0, idx: [] }));           // größte Aufgaben zuerst an den freiesten
  [...aufgaben.keys()].sort((x, y) => aufgaben[y].kosten - aufgaben[x].kosten).forEach((i) => {
    const l = last.reduce((m, x) => (x.kosten < m.kosten ? x : m));
    l.kosten += aufgaben[i].kosten;
    l.idx.push(i);
  });
  const ergebnisse = new Array(aufgaben.length);
  await Promise.all(last.map((l, wi) => l.idx.length && new Promise((ok, fehler) => {
    const id = ++auftrag, w = liste[wi];
    const ende = () => { w.removeEventListener("message", antwort); w.removeEventListener("error", kaputt); };
    const antwort = (e) => {
      if (e.data?.id !== id) return;
      ende();
      if (e.data.fehler) return fehler(new Error(e.data.fehler));
      e.data.ergebnis.forEach((r, k) => { ergebnisse[l.idx[k]] = r; });
      ok();
    };
    const kaputt = (e) => { ende(); fehler(e.error || new Error(e.message || "Hilfsprozess abgestürzt")); };
    w.addEventListener("message", antwort);
    w.addEventListener("error", kaputt);
    w.postMessage({ id, pixel, b, h, aufgaben: l.idx.map((i) => aufgaben[i]) });
  })));
  return ergebnisse;
}

/** Wie finde(), aber verteilt auf Hilfsprozesse – die Oberfläche bleibt bedienbar. Ergebnis ist identisch. */
export async function findeImHintergrund(g, b, h) {
  const { pixel, aufgaben } = planen(g, b, h);
  let ergebnisse = null;
  try { ergebnisse = await imHintergrund(pixel, b, h, aufgaben); } catch {
    helfer = Promise.resolve([]);                  // Hilfsprozesse kaputt: ab jetzt im Vordergrund
  }
  if (!ergebnisse) {
    const cache = {};
    ergebnisse = [];
    for (const a of aufgaben) {
      ergebnisse.push(rechnen(pixel, b, h, a, cache));
      await new Promise((r) => setTimeout(r, 0));   // zwischendurch die Oberfläche zeichnen lassen
    }
  }
  return zusammenfuehren(aufgaben, ergebnisse, b);
}

/** Gesichter auf einer Leinwand als { x, y, w, h } (genau der Gesichtskasten, ohne Rand). */
export async function gesichterAuf(canvas) {
  const { width: b, height: h } = canvas;
  if (b < 24 || h < 24) return [];
  const daten = canvas.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, b, h).data;
  const kaesten = await findeImHintergrund(grau(daten, b, h), b, h);
  return kaesten.map(([x0, y0, x1, y1]) => ({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 }));
}

/** Nur für die Tests (Vergleich mit OpenCV Schritt für Schritt) und den Hilfsprozess. */
export const intern = {
  verkleinern, gruppieren, spiegeln, rechnen,
  kandidaten: (name, g, b, h, min) => { const k = kaskade(name); return skalen(k, b, h, min).flatMap((sc) => treffer(k, g, b, h, sc)); },
};
