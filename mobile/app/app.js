// Datenwächter als Handy-App: prüfen, schwärzen, geschützt weitergeben, KI-Antworten zurückübersetzen.
import * as ki from "./js/ki.js";
import * as dok from "./js/dokumente.js";

const D = globalThis.DWDetect;
const $ = (id) => document.getElementById(id);
const ZUORDNUNG = "dw-zuordnung", STATISTIK = "dw-statistik";
const PLATZHALTER = /\[[A-Z_]+_\d+\]/g;

const S = {
  einst: ki.laden(),
  anon: new D.Anonymizer(),
  dateien: [],              // geladene Dokumente
  docs: [],                 // aktuell geprüft: Text aus dem Eingabefeld + Dateien
  aus: new Set(),           // Funde, die nicht geschwärzt werden sollen (Typ + Wert)
  kiFunde: new Map(),       // Dokument → zusätzliche Funde der KI
  kiThema: null,
  ansicht: "datei",
  zeichnen: false,
  lauf: 0,
  installieren: null,
};

// ================================================================== Hilfen
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const schluessel = (f) => f.kind + "\u0000" + f.text.trim();
const anzahl = (n, eins, mehr) => `${n} ${n === 1 ? eins : mehr}`;
const lesen = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const schreiben = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privater Modus */ } };

let toastTimer;
function toast(text, ms = 2600) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

function fortschritt(text, anteil) {
  $("fortschritt").hidden = !text;
  if (!text) return;
  $("fortschritt-text").textContent = text;
  $("fortschritt-balken").style.width = anteil == null ? "100%" : `${Math.round(anteil * 100)}%`;
  $("fortschritt-balken").style.opacity = anteil == null ? ".35" : "1";
}

function zaehle(feld, n = 1) {
  const s = lesen(STATISTIK, { geprueft: 0, funde: 0, anonym: 0 });
  s[feld] = (s[feld] || 0) + n;
  schreiben(STATISTIK, s);
  statistikZeigen();
}
function statistikZeigen() {
  const s = lesen(STATISTIK, { geprueft: 0, funde: 0, anonym: 0 });
  $("stat-geprueft").textContent = s.geprueft || 0;
  $("stat-funde").textContent = s.funde || 0;
  $("stat-anonym").textContent = s.anonym || 0;
}

function zuordnungSpeichern() { schreiben(ZUORDNUNG, S.anon.exportMapping()); zuordnungZeigen(); }

async function inZwischenablage(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    const t = document.createElement("textarea");
    t.value = text; document.body.append(t); t.select();
    const ok = document.execCommand("copy"); t.remove(); return ok;
  }
}

async function ausZwischenablage() {
  try {
    if (navigator.clipboard.read) {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const bild = item.types.find((t) => t.startsWith("image/"));
        if (bild) return { datei: new File([await item.getType(bild)], "Bild aus der Zwischenablage.png", { type: bild }) };
        if (item.types.includes("text/plain")) return { text: await (await item.getType("text/plain")).text() };
      }
    }
    return { text: await navigator.clipboard.readText() };
  } catch {
    toast("Kein Zugriff auf die Zwischenablage – lange ins Feld tippen und „Einfügen“ wählen.");
    return {};
  }
}

async function teilen(daten) {
  if (navigator.canShare && navigator.canShare(daten)) {
    try { await navigator.share(daten); return true; } catch (e) { return e.name === "AbortError" ? false : speichernFallback(daten); }
  }
  return speichernFallback(daten);
}
async function speichernFallback(daten) {
  if (daten.files?.length) {
    for (const f of daten.files) {
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(f), download: f.name });
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    }
    toast(daten.files.length === 1 ? "Datei gespeichert" : "Dateien gespeichert");
    return true;
  }
  if (daten.text) { await inZwischenablage(daten.text); toast("Kopiert – jetzt in der KI-App einfügen"); return true; }
  return false;
}

// ================================================================== Navigation
function gehe(tab) {
  for (const s of document.querySelectorAll(".tab")) s.hidden = s.dataset.tab !== tab;
  for (const b of document.querySelectorAll(".tabs button")) b.classList.toggle("on", b.dataset.gehe === tab);
  S.tab = tab;
  if (tab === "ki" && !$("ki-eingabe").value.trim() && $("eingabe").value.trim()) $("ki-eingabe").value = $("eingabe").value;
  if (tab === "zurueck") zuordnungZeigen();
  if (tab === "einstellungen") { einstellungenZeigen(); ocrStatus(); }
  if (tab === "ki") aktionenZeigen();
  leisteZeigen();
  window.scrollTo({ top: 0 });
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-gehe]");
  if (b) gehe(b.dataset.gehe);
});

function kopfStatus(text, art) {
  const s = S.einst;
  if (!text) {
    if (ki.bereit(s)) { text = `KI-Server: ${ki.host(s.url)}${ki.anonymZuerst(s) ? " · anonymisiert" : ""}`; art = "ki"; }
    else { text = "Alles bleibt auf deinem Handy"; art = "ok"; }
  }
  $("status-text").textContent = text;
  $("status").querySelector(".dot").className = `dot ${art}`;
}

// ================================================================== Prüfen
let tippTimer;
$("eingabe").addEventListener("input", () => { clearTimeout(tippTimer); tippTimer = setTimeout(pruefen, 450); });
$("eingabe").addEventListener("paste", (e) => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.length) { e.preventDefault(); dateienLaden(files); }
});
$("btn-einfuegen").addEventListener("click", async () => {
  const r = await ausZwischenablage();
  if (r.datei) return dateienLaden([r.datei]);
  if (r.text) { $("eingabe").value = r.text; pruefen(); }
  else if (r.text === "") toast("Die Zwischenablage ist leer.");
});
$("datei").addEventListener("change", (e) => { dateienLaden([...e.target.files]); e.target.value = ""; });
$("foto").addEventListener("change", (e) => { dateienLaden([...e.target.files]); e.target.value = ""; });
$("btn-leeren").addEventListener("click", neuAnfangen);
$("neue-sitzung").addEventListener("click", neuAnfangen);
const karte = $("eingabe-karte");
karte.addEventListener("dragover", (e) => { e.preventDefault(); karte.classList.add("ueber"); });
karte.addEventListener("dragleave", () => karte.classList.remove("ueber"));
karte.addEventListener("drop", (e) => { e.preventDefault(); karte.classList.remove("ueber"); if (e.dataTransfer.files.length) dateienLaden([...e.dataTransfer.files]); });

function neuAnfangen() {
  S.lauf++;
  $("eingabe").value = "";
  S.dateien = []; S.docs = []; S.aus.clear(); S.kiFunde.clear(); S.kiThema = null; S.zeichnen = false;
  fortschritt(null);
  dateilisteZeigen();
  ergebnisZeigen();
  kopfStatus();
}

async function dateienLaden(files) {
  if (!files.length) return;
  const lauf = ++S.lauf;
  for (const [i, f] of files.entries()) {
    try {
      const vor = files.length > 1 ? `${f.name} (${i + 1}/${files.length}): ` : "";
      const doc = await dok.laden(f, (t, p) => lauf === S.lauf && fortschritt(vor + t, p));
      if (lauf !== S.lauf) return;
      S.dateien.push(doc);
      if (doc.hinweis) toast(doc.hinweis, 5000);
      if (!doc.text.trim() && doc.typ !== "bild") toast(`In „${f.name}“ wurde kein Text gefunden.`);
    } catch (e) {
      console.error(e);
      toast(`„${f.name}“ konnte nicht gelesen werden: ${e.message || e}`, 6000);
    }
  }
  fortschritt(null);
  dateilisteZeigen();
  pruefen();
}

function dateilisteZeigen() {
  const box = $("dateiliste");
  box.hidden = !S.dateien.length;
  box.innerHTML = S.dateien.map((d, i) => `<span class="chip"><svg><use href="#${d.typ === "bild" ? "i-kamera" : "i-datei"}"/></svg><span>${esc(d.name)}</span>`
    + `<button class="link" data-weg="${i}" aria-label="Entfernen" style="padding:0 0 0 2px"><svg style="width:15px;height:15px"><use href="#i-x"/></svg></button></span>`).join("");
}
$("dateiliste").addEventListener("click", (e) => {
  const b = e.target.closest("[data-weg]");
  if (!b) return;
  S.dateien.splice(Number(b.dataset.weg), 1);
  dateilisteZeigen();
  pruefen();
});

const kennung = (d) => d.name + "\u0000" + d.text;

/** Funde zusammenführen: Regeln zuerst, KI-Funde nur, wo noch nichts markiert ist. */
function vereinen(basis, extra) {
  const alle = [...basis];
  for (const f of extra) if (alle.every((k) => f.end <= k.start || f.start >= k.end)) alle.push(f);
  return alle.sort((a, b) => a.start - b.start);
}

function pruefen() {
  const text = $("eingabe").value;
  const docs = [];
  if (text.trim()) docs.push({ name: "Eingefügter Text", typ: "eingabe", text, seiten: [] });
  docs.push(...S.dateien);
  const neu = docs.map(kennung).join("\u0001") !== S.docs.map(kennung).join("\u0001");
  S.docs = docs;
  if (neu) {
    S.kiFunde.clear(); S.kiThema = null; S.zeichnen = false;
    S.ansicht = docs.some((d) => d.seiten.length) ? "datei" : "text";
  }
  for (const d of docs) d.funde = vereinen(D.scan(d.text), S.kiFunde.get(kennung(d)) || []);
  if (neu && docs.length) {
    zaehle("geprueft");
    const n = docs.reduce((s, d) => s + d.funde.length, 0);
    if (n) zaehle("funde", n);
  }
  ergebnisZeigen();
  if (neu && docs.length) kiPruefen(++S.lauf);
}

async function kiPruefen(lauf) {
  const s = S.einst;
  if (!ki.bereit(s) || (!s.thema && !s.namen)) return;
  const docs = S.docs;
  const gesamt = docs.map((d) => d.text).join("\n\n").trim();
  const bildDoc = docs.find((d) => d.typ === "bild");
  if (!gesamt && !bildDoc) return;
  kopfStatus(`KI prüft … (${ki.host(s.url)})`, "warn");
  const fehler = [];
  const aufgaben = [];
  if (s.thema) {
    aufgaben.push((async () => {
      const bild = bildDoc && ki.bilderSenden(s) ? await kleinesBild(bildDoc.seiten[0]) : null;
      S.kiThema = await ki.thema(s, gesamt, bild, docs.length === 1 ? docs[0].name : "");
    })().catch((e) => fehler.push(e.message)));
  }
  if (s.namen && gesamt) {
    aufgaben.push((async () => {
      const werte = await ki.personenDaten(s, gesamt);
      for (const d of docs) S.kiFunde.set(kennung(d), ki.alsFunde(werte, d.text));
    })().catch((e) => fehler.push(e.message)));
  }
  await Promise.all(aufgaben);
  if (lauf !== S.lauf) return;
  kopfStatus();
  if (fehler.length) toast(`KI-Prüfung nicht möglich: ${fehler[0]}`, 5000);
  const vorher = docs.reduce((n, d) => n + d.funde.length, 0);
  for (const d of docs) d.funde = vereinen(D.scan(d.text), S.kiFunde.get(kennung(d)) || []);
  const mehr = docs.reduce((n, d) => n + d.funde.length, 0) - vorher;
  if (mehr > 0) zaehle("funde", mehr);
  ergebnisZeigen();
}

async function kleinesBild(seite) {
  const bmp = await createImageBitmap(seite.original);
  const f = Math.min(1, 1024 / Math.max(bmp.width, bmp.height));
  const c = Object.assign(document.createElement("canvas"), { width: Math.round(bmp.width * f), height: Math.round(bmp.height * f) });
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return c.toDataURL("image/jpeg", 0.85);
}

function aktiveFunde(d) { return d.funde.filter((f) => !S.aus.has(schluessel(f))); }

function anonymText(d) { return S.anon.anonymize(d.text, aktiveFunde(d)); }

function gesamtText() {
  const teile = S.docs.filter((d) => d.text.trim()).map((d) => ({ d, t: anonymText(d).trim() }));
  zuordnungSpeichern();
  if (teile.length === 1) return teile[0].t;
  return teile.map(({ d, t }) => `— ${d.name} —\n${t}`).join("\n\n");
}

function ergebnisZeigen() {
  const docs = S.docs;
  const hat = docs.length > 0;
  $("ergebnis").hidden = !hat;
  $("willkommen").hidden = hat;
  $("neue-sitzung").hidden = !hat;
  document.body.classList.toggle("mit-leiste", hat);
  leisteZeigen();
  if (!hat) { $("seiten").innerHTML = ""; return; }

  const alle = docs.flatMap((d) => d.funde);
  const text = gesamtText();          // vergibt die Platzhalter in Lesereihenfolge
  // ---- Urteil
  const kw = D.contentCheck(docs.map((d) => d.text).join("\n"));
  const thema = mischeThema(kw, S.kiThema);
  const stufe = Math.max(0, ...alle.map((f) => f.severity), thema.severity >= 3 ? 3 : thema.severity ? 2 : 0);
  const typen = [...new Set(alle.filter((f) => f.severity >= 3).map((f) => f.label))];
  const urteil = $("urteil");
  urteil.className = `card urteil ${stufe >= 3 ? "hoch" : stufe >= 2 ? "mittel" : "ok"}`;
  const quelle = docs.map((d) => d.typ === "eingabe" ? "Text" : `${d.name}${d.quelle ? ` · ${d.quelle}` : ""}`).join(" · ");
  if (alle.length) {
    const unter = typen.length ? `Darunter ${typen.slice(0, 3).join(", ")}. ` : "";
    urteil.innerHTML = `<svg><use href="#i-warn"/></svg><div><b>${anzahl(alle.length, "sensible Angabe", "sensible Angaben")} gefunden</b>`
      + `<span class="small">${esc(unter)}Geschützt teilen ersetzt sie durch Platzhalter.</span></div>`;
  } else {
    urteil.innerHTML = `<svg><use href="#i-${thema.categories.length ? "warn" : "ok"}"/></svg><div><b>Keine persönlichen Daten gefunden</b>`
      + `<span class="small muted">Geprüft: ${esc(quelle)}</span></div>`;
  }
  // ---- Thema
  const tb = $("thema");
  tb.hidden = !thema.categories.length;
  if (thema.categories.length) {
    const hinweise = kw.hints.length ? `Hinweise: ${kw.hints.slice(0, 5).map((h) => `„${esc(h)}“`).join(", ")}` : "";
    tb.innerHTML = `<svg><use href="#i-ordner"/></svg><div><b>${esc(thema.warning)}</b>`
      + (thema.description ? `<div class="small">${esc(thema.description)}</div>` : "")
      + (hinweise ? `<div class="small muted">${hinweise}</div>` : "")
      + `<div class="quelle">${esc(thema.quelle)}</div></div>`;
  }
  // ---- Funde
  const gruppen = new Map();
  for (const f of alle) {
    const k = schluessel(f);
    const g = gruppen.get(k) || { f, n: 0 };
    g.n++;
    gruppen.set(k, g);
  }
  $("funde-karte").hidden = !gruppen.size;
  const sortiert = [...gruppen.entries()].sort((a, b) => b[1].f.severity - a[1].f.severity);
  S.fundSchluessel = sortiert.map(([k]) => k);
  $("funde").innerHTML = sortiert.map(([k, { f, n }], i) => {
    const aus = S.aus.has(k);
    const ph = aus ? "bleibt" : S.anon.placeholder(f);
    return `<li class="fund${aus ? " aus" : ""}" data-i="${i}" role="switch" aria-checked="${!aus}">`
      + `<span class="stufe ${f.severityLabel || ""}"></span><span class="was"><b>${esc(f.label)}${f.quelle === "ki" ? '<span class="ki">KI</span>' : ""}${n > 1 ? ` <span class="muted">×${n}</span>` : ""}</b>`
      + `<span>${esc(f.display || f.text)}</span></span><span class="ph">${esc(ph)}</span></li>`;
  }).join("");
  // ---- Vorschau
  const mitSeiten = docs.some((d) => d.seiten.length);
  $("ansicht").hidden = !mitSeiten;
  if (!mitSeiten) S.ansicht = "text";
  else if (S.ansicht === "text" && !docs.some((d) => d.text.trim())) S.ansicht = "datei";
  for (const b of $("ansicht").children) b.classList.toggle("on", b.dataset.ansicht === S.ansicht);
  $("vorschau-titel").textContent = S.ansicht === "datei" ? "Vorschau" : "Das bekommt die KI";
  $("anon-text").hidden = S.ansicht !== "text";
  $("anon-text").innerHTML = esc(text).replace(PLATZHALTER, (m) => `<mark>${m}</mark>`);
  $("seiten").hidden = S.ansicht !== "datei";
  $("schwaerz-hinweis").hidden = S.ansicht !== "datei";
  if (S.ansicht === "datei") seitenZeigen();
  $("teilen-text").textContent = alle.length || docs.some((d) => d.seiten.some((s) => s.manuell.length)) ? "Geschützt teilen" : "Teilen";
}

const verb = (a) => (a.length === 1 ? a[0] : a.slice(0, -1).join(", ") + " und " + a.at(-1));
function mischeThema(kw, kiThema) {
  if (!kiThema) {
    return { ...kw, warning: kw.categories.length ? `Du lädst gerade ${verb(kw.categories)} hoch.` : null,
             quelle: "Erkannt an Stichwörtern – nur auf dem Handy" };
  }
  const categories = [...kiThema.categories];
  for (const c of kw.categories) if (!categories.includes(c)) categories.push(c);
  const wo = kiThema.extern ? `KI-Server ${kiThema.host}${kiThema.anonym ? " (anonymisiert gesendet)" : ""}` : `KI im eigenen Netz (${kiThema.host})`;
  return { categories, severity: Math.max(kw.severity, kiThema.severity), description: kiThema.description,
           warning: categories.length ? `Du lädst gerade ${verb(categories)} hoch.` : null, quelle: `Geprüft von: ${wo}` };
}

$("funde").addEventListener("click", (e) => {
  const li = e.target.closest(".fund");
  if (!li) return;
  const k = S.fundSchluessel[Number(li.dataset.i)];
  S.aus.has(k) ? S.aus.delete(k) : S.aus.add(k);
  ergebnisZeigen();
});
$("ansicht").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  S.ansicht = b.dataset.ansicht;
  ergebnisZeigen();
});

// ---- Seiten mit Balken
function kaesten(d, seite) {
  const out = [];
  for (const f of aktiveFunde(d)) for (const r of dok.balken(seite, f)) out.push({ ...r, label: S.anon.placeholder(f), art: "balken", k: schluessel(f) });
  for (const g of seite.gesichter || []) out.push({ ...g, art: "gesicht" });
  for (const [i, m] of seite.manuell.entries()) out.push({ ...m, art: "manuell", i });
  return out;
}

let zeichenLauf = 0;
async function seitenZeigen() {
  const lauf = ++zeichenLauf;
  const box = $("seiten");
  const docs = S.docs.filter((d) => d.seiten.length);
  const soll = docs.flatMap((d) => d.seiten.map((s, i) => ({ d, s, i })));
  if (box.children.length !== soll.length || [...box.children].some((el, i) => el._seite !== soll[i].s)) {
    box.innerHTML = "";
    for (const { d, s, i } of soll) {
      const el = document.createElement("div");
      el.className = "seite";
      el._seite = s; el._doc = d;
      el.innerHTML = `<canvas></canvas><span class="nr">${esc(d.typ === "bild" ? d.name : `${d.name} · S. ${i + 1}`)}</span>`;
      zeichenflaeche(el);
      box.append(el);
    }
  }
  for (const el of box.children) {
    if (lauf !== zeichenLauf) return;
    el.classList.toggle("zeichnen", S.zeichnen);
    await dok.zeichne(el._seite, el.querySelector("canvas"), kaesten(el._doc, el._seite));
  }
}

/** Finger ziehen = Bereich schwärzen, Balken antippen = entfernen. */
function zeichenflaeche(el) {
  let start = null, zug = null, bild = null;
  const punkt = (e) => {
    const c = el.querySelector("canvas"), r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) };
  };
  el.addEventListener("pointerdown", (e) => {
    start = punkt(e); zug = null; bild = null;
    if (S.zeichnen) {
      el.setPointerCapture(e.pointerId);
      const c = el.querySelector("canvas");
      bild = c.getContext("2d").getImageData(0, 0, c.width, c.height);
    }
  });
  el.addEventListener("pointercancel", () => { start = null; zug = null; bild = null; });
  el.addEventListener("pointermove", (e) => {
    if (!start || !S.zeichnen) return;
    const p = punkt(e);
    zug = { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) };
    const ctx = el.querySelector("canvas").getContext("2d");
    if (bild) ctx.putImageData(bild, 0, 0);
    ctx.fillStyle = "rgb(0 0 0 / .6)";
    ctx.fillRect(zug.x, zug.y, zug.w, zug.h);
  });
  el.addEventListener("pointerup", (e) => {
    const p = punkt(e);
    if (zug && zug.w > 12 && zug.h > 8) {
      el._seite.manuell.push(zug);
    } else if (start && Math.hypot(p.x - start.x, p.y - start.y) < 12) {
      const treffer = kaesten(el._doc, el._seite).reverse().find((k) => p.x >= k.x && p.x <= k.x + k.w && p.y >= k.y && p.y <= k.y + k.h);
      if (treffer?.art === "manuell") el._seite.manuell.splice(treffer.i, 1);
      else if (treffer?.art === "balken") S.aus.add(treffer.k);
      else if (treffer?.art === "gesicht") el._seite.gesichter = el._seite.gesichter.filter((g) => !(g.x === treffer.x && g.y === treffer.y));
      else if (!S.zeichnen) { start = null; return; }
    }
    start = null; zug = null; bild = null;
    ergebnisZeigen();
  });
}

$("schwaerz-hinweis").addEventListener("click", () => {
  S.zeichnen = !S.zeichnen;
  hinweisText();
  seitenZeigen();
});
function hinweisText() {
  $("schwaerz-hinweis").innerHTML = S.zeichnen
    ? `<b class="gruen">✎ Schwärzen aktiv:</b> mit dem Finger über eine Stelle ziehen. Balken antippen = entfernen. <u>Fertig</u>`
    : `Balken antippen = nicht schwärzen · <u>✎ Selbst schwärzen</u> (z. B. Gesichter, Unterschrift)`;
}
hinweisText();

// ---- Weitergeben
function leisteZeigen() {
  $("aktionsleiste").hidden = !(S.tab === "pruefen" && S.docs.length);
  const nurText = !S.docs.some((d) => d.seiten.length) || S.ansicht === "text";
  $("oeffnen-chatgpt").hidden = !nurText;
  $("oeffnen-claude").hidden = !nurText;
}

async function geschuetzteDateien() {
  const out = [];
  const canvases = new Map([...$("seiten").children].map((el) => [el._seite, el.querySelector("canvas")]));
  for (const d of S.docs) {
    if (d.typ === "eingabe") continue;
    const ohneAenderung = !aktiveFunde(d).length && d.seiten.every((s) => !s.manuell.length && !(s.gesichter || []).length);
    if (ohneAenderung && d.datei) { out.push(d.datei); continue; }
    const cs = [];
    for (const s of d.seiten) {
      let c = canvases.get(s);
      if (!c) { c = document.createElement("canvas"); await dok.zeichne(s, c, kaesten(d, s)); }
      cs.push(c);
    }
    out.push(await dok.exportieren(d, cs, anonymText(d)));
  }
  return out;
}

$("teilen").addEventListener("click", async () => {
  const text = gesamtText();
  const geschuetzt = S.docs.some((d) => aktiveFunde(d).length);
  try {
    let ok;
    if (S.ansicht === "text" || !S.docs.some((d) => d.typ !== "eingabe")) ok = await teilen({ text });
    else {
      fortschritt("Datei wird vorbereitet …", null);
      const files = await geschuetzteDateien();
      fortschritt(null);
      ok = await teilen($("eingabe").value.trim() ? { files, text } : { files });
    }
    if (ok && geschuetzt) zaehle("anonym");
  } catch (e) {
    fortschritt(null);
    toast(`Teilen nicht möglich: ${e.message || e}`, 5000);
  }
});
$("kopieren").addEventListener("click", async () => {
  if (await inZwischenablage(gesamtText())) {
    toast("Geschützter Text kopiert");
    if (S.docs.some((d) => aktiveFunde(d).length)) zaehle("anonym");
  }
});
for (const [id, url, name] of [["oeffnen-chatgpt", "https://chatgpt.com/", "ChatGPT"], ["oeffnen-claude", "https://claude.ai/new", "Claude"]]) {
  $(id).addEventListener("click", async () => {
    await inZwischenablage(gesamtText());
    if (S.docs.some((d) => aktiveFunde(d).length)) zaehle("anonym");
    toast(`Kopiert – in ${name} einfügen`);
    setTimeout(() => window.open(url, "_blank", "noopener"), 350);
  });
}

// ================================================================== KI-Aktionen
let bearbeiten = false;
function aktionenZeigen() {
  const bereit = ki.bereit(S.einst);
  $("ki-ohne-server").hidden = bereit;
  const liste = ki.aktionenLaden();
  $("aktionen").innerHTML = liste.map((a, i) => `<button class="aktion" data-aktion="${i}"><svg><use href="#${bearbeiten ? "i-stift" : "i-ki"}"/></svg>${esc(a.name)}</button>`).join("")
    + (bearbeiten ? `<button class="aktion bearbeiten" data-aktion="neu"><svg><use href="#i-plus"/></svg>Neue Aktion</button>` : "");
  $("aktionen-bearbeiten").textContent = bearbeiten ? "Fertig" : "Bearbeiten";
}
$("aktionen-bearbeiten").addEventListener("click", () => { bearbeiten = !bearbeiten; aktionenZeigen(); });
$("aktionen").addEventListener("click", (e) => {
  const b = e.target.closest("[data-aktion]");
  if (!b) return;
  const liste = ki.aktionenLaden();
  if (bearbeiten) return aktionBearbeiten(b.dataset.aktion === "neu" ? null : Number(b.dataset.aktion));
  const a = liste[Number(b.dataset.aktion)];
  kiAusfuehren(a.name, a.anweisung);
});
$("ki-los").addEventListener("click", () => { const t = $("ki-anweisung").value.trim(); if (t) kiAusfuehren("Eigene Anweisung", t); });
$("ki-anweisung").addEventListener("keydown", (e) => { if (e.key === "Enter") $("ki-los").click(); });
$("ki-einfuegen").addEventListener("click", async () => { const r = await ausZwischenablage(); if (r.text) $("ki-eingabe").value = r.text; });
$("ki-leeren").addEventListener("click", () => { $("ki-eingabe").value = ""; $("ki-ergebnis").hidden = true; });

async function kiAusfuehren(name, anweisung) {
  if (!ki.bereit(S.einst)) { toast("Erst unter Einstellungen einen KI-Server eintragen."); return gehe("einstellungen"); }
  const text = $("ki-eingabe").value;
  if (!text.trim()) { toast("Erst einen Text eingeben oder einfügen."); return $("ki-eingabe").focus(); }
  $("ki-ergebnis").hidden = false;
  $("ki-ergebnis-titel").textContent = name;
  $("ki-info").textContent = "";
  $("ki-text").innerHTML = `<span class="muted">KI arbeitet …</span>`;
  for (const b of document.querySelectorAll(".aktion, #ki-los")) b.disabled = true;
  try {
    const r = await ki.aktion(S.einst, anweisung, text);
    $("ki-text").textContent = r.text;
    $("ki-info").textContent = r.extern ? `über ${r.host}${r.anonym ? " · anonymisiert gesendet" : ""}` : `eigener Server ${r.host}`;
  } catch (e) {
    $("ki-text").innerHTML = `<span class="rot">${esc(e.message || e)}</span>`;
  } finally {
    for (const b of document.querySelectorAll(".aktion, #ki-los")) b.disabled = false;
  }
  $("ki-ergebnis").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
$("ki-kopieren").addEventListener("click", async () => { if (await inZwischenablage($("ki-text").textContent)) toast("Kopiert"); });
$("ki-teilen").addEventListener("click", () => teilen({ text: $("ki-text").textContent }));
$("ki-uebernehmen").addEventListener("click", () => { $("ki-eingabe").value = $("ki-text").textContent; $("ki-ergebnis").hidden = true; window.scrollTo({ top: 0, behavior: "smooth" }); });

function aktionBearbeiten(index) {
  const liste = ki.aktionenLaden();
  const a = index == null ? { name: "", anweisung: "" } : liste[index];
  const dlg = $("aktion-dialog");
  $("aktion-dialog-titel").textContent = index == null ? "Neue Aktion" : "Aktion bearbeiten";
  $("aktion-name").value = a.name;
  $("aktion-anweisung").value = a.anweisung;
  $("aktion-loeschen").hidden = index == null;
  dlg.onclose = () => {
    if (dlg.returnValue === "ok") {
      const neu = { ...a, name: $("aktion-name").value.trim(), anweisung: $("aktion-anweisung").value.trim() };
      if (!neu.name || !neu.anweisung) return;
      if (index == null) liste.push(neu); else liste[index] = neu;
    } else if (dlg.returnValue === "loeschen") liste.splice(index, 1);
    else return;
    ki.aktionenSpeichern(liste);
    aktionenZeigen();
  };
  dlg.showModal();
}

// ================================================================== Zurückübersetzen
function zurueck() {
  const text = $("zurueck-eingabe").value;
  const karte = $("zurueck-ergebnis");
  karte.hidden = !text.trim();
  if (!text.trim()) return;
  const map = S.anon.exportMapping();
  let n = 0;
  const html = esc(text).replace(PLATZHALTER, (m) => {
    if (!(m in map)) return m;
    n++;
    return `<mark class="echt">${esc(map[m])}</mark>`;
  });
  $("zurueck-text").innerHTML = html;
  $("zurueck-info").textContent = n ? `${anzahl(n, "Platzhalter", "Platzhalter")} ersetzt` : "keine bekannten Platzhalter";
}
const zurueckText = () => S.anon.restore($("zurueck-eingabe").value);
$("zurueck-eingabe").addEventListener("input", zurueck);
$("zurueck-einfuegen").addEventListener("click", async () => { const r = await ausZwischenablage(); if (r.text) { $("zurueck-eingabe").value = r.text; zurueck(); } });
$("zurueck-leeren").addEventListener("click", () => { $("zurueck-eingabe").value = ""; zurueck(); });
$("zurueck-kopieren").addEventListener("click", async () => { if (await inZwischenablage(zurueckText())) toast("Kopiert – mit echten Angaben"); });
$("zurueck-teilen").addEventListener("click", () => teilen({ text: zurueckText() }));

function zuordnungZeigen() {
  const map = S.anon.exportMapping();
  const eintraege = Object.entries(map);
  $("zuordnung-anzahl").textContent = eintraege.length;
  $("zuordnung").innerHTML = eintraege.length
    ? eintraege.map(([ph, orig]) => `<tr><td>${esc(ph)}</td><td>${esc(orig)}</td></tr>`).join("")
    : `<tr><td colspan="2" class="muted">Noch nichts anonymisiert.</td></tr>`;
}
$("zuordnung-loeschen").addEventListener("click", () => {
  if (!confirm("Zuordnung löschen? Ältere KI-Antworten lassen sich danach nicht mehr zurückübersetzen.")) return;
  S.anon = new D.Anonymizer();
  zuordnungSpeichern();
  zurueck();
  if (S.docs.length) ergebnisZeigen();
  toast("Zuordnung gelöscht");
});

// ================================================================== Einstellungen
const felder = { url: "ki-url", token: "ki-token", modell: "ki-modell" };
function formular() {
  const s = { ...S.einst };
  for (const [k, id] of Object.entries(felder)) s[k] = $(id).value.trim();
  s.aktiv = $("ki-aktiv").classList.contains("on");
  for (const [k, id] of [["thema", "opt-thema"], ["namen", "opt-namen"]]) s[k] = $(id).checked;
  // anonymisieren/bilder: nur speichern, wenn vom automatischen Wert abweichend gewählt
  const autoAnon = ki.extern(s.url), autoBild = !ki.extern(s.url);
  s.anonymisieren = $("opt-anonym").checked === autoAnon && S.einst.anonymisieren == null ? null : $("opt-anonym").checked;
  s.bilder = $("opt-bilder").checked === autoBild && S.einst.bilder == null ? null : $("opt-bilder").checked;
  return s;
}
function einstellungenZeigen() {
  const s = S.einst;
  for (const [k, id] of Object.entries(felder)) $(id).value = s[k] || "";
  aktivZeigen(s.aktiv);
  $("opt-thema").checked = s.thema;
  $("opt-namen").checked = s.namen;
  $("opt-anonym").checked = ki.anonymZuerst(s);
  $("opt-bilder").checked = ki.bilderSenden(s);
  warnungZeigen();
}
function aktivZeigen(an) {
  $("ki-aktiv").classList.toggle("on", an);
  $("ki-aktiv").setAttribute("aria-checked", String(an));
  $("ki-felder").classList.toggle("aus", !an);
}
function warnungZeigen() {
  const s = formular();
  const w = $("ki-warnung");
  w.hidden = !(s.aktiv && ki.baseUrl(s.url));
  if (w.hidden) return;
  const h = ki.host(s.url) || "?";
  const mixed = location.protocol === "https:" && /^http:\/\//.test(ki.baseUrl(s.url)) && !/^http:\/\/(localhost|127\.)/.test(ki.baseUrl(s.url));
  if (mixed) {
    w.innerHTML = `<b>http:// funktioniert hier nicht</b>Die App läuft über https – der Browser blockiert unverschlüsselte Server. Bitte eine https-Adresse nutzen.`;
  } else if (ki.extern(s.url)) {
    const was = [ki.anonymZuerst(s) ? "Text (vorher anonymisiert)" : "Text <b>nicht anonymisiert</b>"];
    if (ki.bilderSenden(s)) was.push("Fotos");
    w.innerHTML = `<b>${esc(h)} liegt im Internet.</b>Gesendet werden: ${was.join(", ")} – nur für die Funktionen, die du oben einschaltest.`;
  } else {
    w.innerHTML = `<b>Server im eigenen Netz (${esc(h)})</b>Die Daten bleiben bei dir. Der Server muss Browser-Zugriffe erlauben (CORS).`;
  }
}
function einstellungenSpeichern(meldung) {
  S.einst = formular();
  ki.speichern(S.einst);
  kopfStatus();
  warnungZeigen();
  if (meldung) toast(meldung);
}
$("vorlagen").innerHTML = ki.VORLAGEN.map(([n, u]) => `<button data-url="${esc(u)}">${esc(n)}</button>`).join("");
$("vorlagen").addEventListener("click", (e) => {
  const b = e.target.closest("[data-url]");
  if (!b) return;
  $("ki-url").value = b.dataset.url;
  einstellungenSpeichern();
  $("ki-token").focus();
});
$("ki-aktiv").addEventListener("click", () => {
  aktivZeigen(!$("ki-aktiv").classList.contains("on"));
  einstellungenSpeichern();
  if (S.einst.aktiv && !ki.baseUrl(S.einst.url)) $("ki-url").focus();
});
for (const id of ["ki-url", "ki-token", "ki-modell", "opt-thema", "opt-namen", "opt-anonym", "opt-bilder"]) {
  $(id).addEventListener("change", () => einstellungenSpeichern());
}
$("ki-url").addEventListener("input", () => {
  if (S.einst.anonymisieren == null) $("opt-anonym").checked = ki.extern($("ki-url").value);
  if (S.einst.bilder == null) $("opt-bilder").checked = !ki.extern($("ki-url").value);
  warnungZeigen();
});
$("ki-speichern").addEventListener("click", () => einstellungenSpeichern("Gespeichert"));
$("modelle-laden").addEventListener("click", async () => {
  const s = formular();
  $("ki-status").className = "muted small";
  $("ki-status").textContent = "Lade Modelle …";
  try {
    const liste = await ki.modelle(s);
    $("modelle").innerHTML = liste.map((m) => `<option value="${esc(m)}">`).join("");
    if (!$("ki-modell").value && liste.length) $("ki-modell").value = liste[0];
    $("ki-status").textContent = liste.length ? `${anzahl(liste.length, "Modell", "Modelle")} gefunden – tippe ins Feld „Modell“ für die Liste.` : "Der Server nennt keine Modelle – bitte von Hand eintragen.";
    einstellungenSpeichern();
  } catch (e) {
    $("ki-status").className = "small fehler";
    $("ki-status").textContent = e.message;
  }
});
$("ki-testen").addEventListener("click", async () => {
  const s = formular();
  $("ki-status").className = "muted small";
  $("ki-status").textContent = "Teste Verbindung …";
  $("ki-testen").disabled = true;
  const r = await ki.testen({ ...s, aktiv: true });
  $("ki-testen").disabled = false;
  $("ki-status").className = `small ${r.ok ? "ok" : "fehler"}`;
  $("ki-status").textContent = r.meldung;
  if (r.ok) {
    if (!$("ki-modell").value && r.modell) $("ki-modell").value = r.modell;
    if (r.modelle?.length) $("modelle").innerHTML = r.modelle.map((m) => `<option value="${esc(m)}">`).join("");
    if (!$("ki-aktiv").classList.contains("on")) aktivZeigen(true);
    einstellungenSpeichern();
  }
});

async function ocrStatus() {
  const ok = await dok.ocrOffline().catch(() => false);
  $("ocr-status").textContent = ok ? "✔ Offline bereit" : "Noch nicht geladen – passiert sonst beim ersten Foto";
  $("ocr-laden").hidden = ok;
}
$("ocr-laden").addEventListener("click", async () => {
  $("ocr-laden").disabled = true;
  $("ocr-status").textContent = "Lade Texterkennung …";
  try { await dok.ocrBereitmachen(); toast("Texterkennung ist jetzt offline verfügbar"); } catch (e) { toast(`Laden fehlgeschlagen: ${e.message || e}`); }
  $("ocr-laden").disabled = false;
  ocrStatus();
});

$("alles-loeschen").addEventListener("click", () => {
  if (!confirm("Zuordnung, Statistik und aktuelle Ergebnisse löschen? (Einstellungen und Aktionen bleiben.)")) return;
  S.anon = new D.Anonymizer();
  zuordnungSpeichern();
  schreiben(STATISTIK, { geprueft: 0, funde: 0, anonym: 0 });
  statistikZeigen();
  neuAnfangen();
  $("zurueck-eingabe").value = ""; zurueck();
  toast("Gelöscht");
});

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  S.installieren = e;
  $("installieren-zeile").hidden = false;
});
$("installieren").addEventListener("click", async () => {
  if (!S.installieren) return;
  S.installieren.prompt();
  await S.installieren.userChoice;
  S.installieren = null;
  $("installieren-zeile").hidden = true;
});
const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
$("ios-hinweis").hidden = standalone || !/iPhone|iPad|iPod/.test(navigator.userAgent);

// ================================================================== Geteilte Inhalte (Android: Teilen → Datenwächter)
async function geteiltAbholen() {
  const cache = await caches.open("dw-geteilt");
  const info = await cache.match(new URL("geteilt/info", location.href).href);
  if (!info) return;
  const meta = await info.json();
  const files = [];
  for (const d of meta.dateien) {
    const r = await cache.match(new URL(`geteilt/${d.id}`, location.href).href);
    if (r) files.push(new File([await r.blob()], d.name, { type: d.typ || r.headers.get("Content-Type") || "" }));
  }
  for (const k of await cache.keys()) await cache.delete(k);
  const text = [meta.text || meta.titel, meta.link].filter(Boolean).join("\n").trim();
  const bekannt = Object.keys(S.anon.exportMapping());
  if (!files.length && text && (text.match(PLATZHALTER) || []).some((p) => bekannt.includes(p))) {
    gehe("zurueck");                // KI-Antwort mit unseren Platzhaltern → gleich zurückübersetzen
    $("zurueck-eingabe").value = text;
    zurueck();
    return;
  }
  gehe("pruefen");
  if (text) $("eingabe").value = text;
  if (files.length) await dateienLaden(files); else pruefen();
}

// ================================================================== Start
async function start() {
  S.anon.importMapping(lesen(ZUORDNUNG, {}));
  statistikZeigen();
  kopfStatus();
  const q = new URLSearchParams(location.search);
  gehe(["pruefen", "ki", "zurueck", "einstellungen"].includes(q.get("tab")) ? q.get("tab") : "pruefen");
  if ("serviceWorker" in navigator) {
    try { await navigator.serviceWorker.register("sw.js"); } catch (e) { console.warn("Service-Worker:", e); }
  }
  if (q.get("fehler")) toast(`Teilen hat nicht geklappt: ${q.get("fehler")}`, 5000);
  if (q.has("geteilt")) await geteiltAbholen().catch((e) => toast(`Geteilter Inhalt nicht lesbar: ${e.message || e}`));
  if (q.size) history.replaceState(null, "", location.pathname);
  document.documentElement.dataset.bereit = "1";
}
start();
