// Eigener KI-Server (OpenAI-kompatibel: Adresse + Token) – gleiche Fragen und Regeln wie im Windows-Programm
// (datenwaechter/llm.py, actions.py). Ohne eingerichteten Server verlässt nichts das Handy.

const SPEICHER = "dw-einstellungen";
const AKTIONEN = "dw-aktionen";
const MAX_CHARS = 6000;
const MAX_AKTION = 12000;
const TIMEOUT = 120000;

export const VORLAGEN = [
  ["Datenwächter KI", "https://ki.firma.example/v1"],
  ["OpenAI", "https://api.openai.com/v1"],
  ["OpenRouter", "https://openrouter.ai/api/v1"],
  ["Mistral", "https://api.mistral.ai/v1"],
  ["Groq", "https://api.groq.com/openai/v1"],
];

const STANDARD = { aktiv: false, url: "", token: "", modell: "", anonymisieren: null, bilder: null, thema: true, namen: false };

export function laden() {
  try { return { ...STANDARD, ...JSON.parse(localStorage.getItem(SPEICHER) || "{}") }; } catch { return { ...STANDARD }; }
}
export function speichern(s) {
  try { localStorage.setItem(SPEICHER, JSON.stringify(s)); } catch { /* privater Modus */ }
}

export function baseUrl(url) {
  let u = String(url || "").trim().replace(/\/+$/, "");
  for (const suffix of ["/chat/completions", "/completions", "/models"]) if (u.endsWith(suffix)) u = u.slice(0, -suffix.length);
  return u;
}
export function host(url) {
  try { return new URL(baseUrl(url)).hostname; } catch { return ""; }
}
/** true, wenn der Server (vermutlich) im Internet liegt – wie settings.is_external */
export function extern(url) {
  const h = host(url).toLowerCase().replace(/^\[|\]$/g, "");
  if (!h) return false;
  if (h === "localhost" || /\.(local|lan|internal|intranet|home\.arpa|localhost)$/.test(h)) return false;
  const v4 = h.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    return !(a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254));
  }
  if (h.includes(":")) return !(h === "::1" || h.startsWith("fc") || h.startsWith("fd") || h.startsWith("fe80"));
  return h.includes(".");
}
export const anonymZuerst = (s) => s.anonymisieren ?? extern(s.url);
export const bilderSenden = (s) => s.bilder ?? !extern(s.url);
export const bereit = (s) => Boolean(s.aktiv && baseUrl(s.url));

export class KiFehler extends Error {}

function freundlich(err, s) {
  if (err instanceof KiFehler) return err;
  if (err && err.name === "AbortError") return new KiFehler("Der KI-Server antwortet nicht (Zeitüberschreitung).");
  const u = baseUrl(s.url);
  if (location.protocol === "https:" && u.startsWith("http://") && !/^http:\/\/(localhost|127\.)/.test(u)) {
    return new KiFehler("Die App läuft über https – ein Server mit http:// wird vom Browser blockiert. Bitte eine https-Adresse nutzen.");
  }
  return new KiFehler("Server nicht erreichbar. Adresse prüfen – und ob der Server Zugriffe aus dem Browser erlaubt (CORS).");
}

async function anfrage(s, pfad, body, timeout = TIMEOUT) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (s.token) headers.Authorization = `Bearer ${s.token.trim()}`;
  let res;
  try {
    res = await fetch(baseUrl(s.url) + pfad, {
      method: body ? "POST" : "GET", headers, body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal, referrerPolicy: "no-referrer", credentials: "omit", cache: "no-store",
    });
  } catch (err) {
    throw freundlich(err, s);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const detail = (await res.text().catch(() => "")).slice(0, 300);
    const e = new KiFehler(res.status === 401 || res.status === 403 ? "Zugriff verweigert – Token prüfen."
      : res.status === 404 ? "Adresse nicht gefunden (404) – endet sie auf /v1?"
      : res.status === 429 ? "Zu viele Anfragen oder Guthaben aufgebraucht (429)."
      : `Der Server meldet Fehler ${res.status}${detail ? ": " + detail : ""}`);
    e.status = res.status;
    throw e;
  }
  try { return await res.json(); } catch { throw new KiFehler("Der Server hat kein gültiges JSON geschickt."); }
}

// Gateways wie LiteLLM listen auch Sprach-, Vorlese-, Embedding- und OCR-Modelle – die können keinen Chat (wie llm.py)
const KEIN_CHAT = /(?:^|[/_.:-])(?:stt|tts|whisper|embed\w*|embedding\w*|ocr|rerank\w*|moderation|dall-e|image|transcri\w*|speech|audio)(?:$|[/_.:-])|\*/i;
export const chatZuerst = (liste) => [...liste.filter((m) => !KEIN_CHAT.test(m)), ...liste.filter((m) => KEIN_CHAT.test(m))];

export async function modelle(s) {
  const data = await anfrage(s, "/models", null, 8000);
  return chatZuerst((data.data || data.models || []).map((m) => m.id || m.name).filter(Boolean));
}

async function modellFuer(s) {
  if (s.modell) return s.modell;
  const liste = await modelle(s).catch(() => []);
  if (!liste.length) throw new KiFehler("Bitte in den Einstellungen ein Modell angeben.");
  return liste[0];
}

export async function complete(s, messages, temperature = 0.3, extra = {}) {
  const body = { model: await modellFuer(s), temperature, messages, ...extra };
  let data;
  try {
    data = await anfrage(s, "/chat/completions", body);
  } catch (e) {
    if (e.status !== 400 || !extra.response_format) throw e;
    delete body.response_format;                // nicht jeder Server kennt den JSON-Modus
    data = await anfrage(s, "/chat/completions", body);
  }
  const text = data?.choices?.[0]?.message?.content;
  if (typeof text !== "string") throw new KiFehler("Unerwartetes Antwortformat vom Server.");
  return text;
}

export function parseJson(text) {
  const m = /\{[\s\S]*\}/.exec(text || "");
  if (!m) throw new KiFehler("Die Antwort enthält kein JSON.");
  try { return JSON.parse(m[0]); } catch { throw new KiFehler("Die Antwort ist kein gültiges JSON."); }
}

const anonymisierer = () => new globalThis.DWDetect.Anonymizer();

// ------------------------------------------------------------------ Inhalts-Check (Thema)
export const KATEGORIEN = {
  familie: "Familienunterlagen", kinder: "Daten über Kinder", gesundheit: "Gesundheitsdaten",
  finanzen: "Finanzunterlagen", recht: "rechtliche Unterlagen", arbeit: "Personal- und Arbeitsunterlagen",
  ausweis: "Ausweisdokumente", vertraulich: "vertrauliche Firmeninterna", zugangsdaten: "Zugangsdaten",
  intim: "intime oder private Inhalte", besonders: "besonders geschützte Daten (Religion, Politik, Sexualität)",
  personenfoto: "Fotos von Personen", personen: "Fotos von Personen",
};
export const STUFE = { kinder: 3, ausweis: 3, gesundheit: 3, intim: 3, zugangsdaten: 3, besonders: 3 };
export const FRAGEN = {
  personen: "Sind auf einem Bild Menschen zu sehen (Foto, Selfie, Gruppenbild)?",
  kinder: "Sind Kinder zu sehen oder geht es um ein bestimmtes Kind?",
  ausweis: "Ist es ein Ausweis, Pass, Führerschein, eine Bank-, Kredit- oder Versichertenkarte?",
  gesundheit: "Geht es um Krankheit, Diagnose, Therapie, Medikamente, Arztbrief oder ein medizinisches Bild?",
  finanzen: "Geht es um Kontoauszug, Gehalt, Steuer, Rechnung mit Bankdaten oder Schulden?",
  familie: "Geht es um Familienangelegenheiten wie Scheidung, Sorgerecht, Unterhalt oder Erbschaft?",
  recht: "Geht es um Gericht, Anwalt, Polizei, Strafsache oder einen Rechtsstreit?",
  arbeit: "Geht es um Personalakte, Kündigung, Abmahnung, Arbeitszeugnis oder Bewerbung?",
  vertraulich: "Ist es als vertraulich/intern markiert oder enthält es Firmengeheimnisse?",
  intim: "Enthält es Nacktheit, Sexualität oder sehr intime private Momente?",
  zugangsdaten: "Enthält es Passwörter, PINs, API-Schlüssel oder andere Zugangsdaten?",
  besonders: "Geht es um Religion, politische Meinung, Gewerkschaft oder sexuelle Orientierung einer Person?",
};
const PROMPT = (text, name) => `Du bist ein Datenschutz-Assistent. Ein Nutzer will den folgenden Inhalt gleich in einen Cloud-KI-Chat
hochladen. Platzhalter wie [PERSON_1] oder [IBAN_1] stehen für bereits entfernte echte Daten.

Beschreibe zuerst in einem kurzen deutschen Satz, was zu sehen bzw. zu lesen ist. Beantworte dann jede Frage
nur mit true oder false. Antworte im Zweifel mit false.
${Object.entries(FRAGEN).map(([k, q]) => `- ${k}: ${q}`).join("\n")}

Antworte NUR mit JSON in genau diesem Format:
{"beschreibung": "…", ${Object.keys(FRAGEN).map((k) => `"${k}": false`).join(", ")}}

Dateiname: ${name || "(eingefügter Text)"}
Inhalt:
<<<
${(text || "(kein Text – siehe Bild)").slice(0, MAX_CHARS)}
>>>`;

const wahr = (v) => v === true || (typeof v === "string" && ["true", "ja", "yes", "1"].includes(v.trim().toLowerCase()));
const verbinde = (a) => (a.length === 1 ? a[0] : a.slice(0, -1).join(", ") + " und " + a[a.length - 1]);

/** Fragt den Server, worum es geht. bild: data:-URL (JPEG) oder null. */
export async function thema(s, text, bild, name) {
  let gesendet = text || "";
  const anonym = anonymZuerst(s) && Boolean(gesendet);
  if (anonym) gesendet = anonymisierer().anonymize(gesendet);
  const prompt = PROMPT(gesendet, name);
  const mitBild = bild && bilderSenden(s);
  const content = mitBild ? [{ type: "text", text: prompt }, { type: "image_url", image_url: { url: bild } }] : prompt;
  const messages = [{ role: "system", content: "Du antwortest ausschließlich mit gültigem JSON." }, { role: "user", content }];
  let antwort;
  try {
    antwort = await complete(s, messages, 0, { response_format: { type: "json_object" } });
  } catch (e) {
    if (e.status !== 400 || !mitBild) throw e;
    messages[1].content = prompt;               // Modell kann keine Bilder – dann nur Text
    antwort = await complete(s, messages, 0);
  }
  const data = parseJson(antwort);
  let keys = Object.keys(FRAGEN).filter((k) => wahr(data[k]));
  for (const raw of data.kategorien || []) {
    const k = Object.keys(KATEGORIEN).find((key) => String(raw).trim().toLowerCase().startsWith(key.slice(0, 5)));
    if (k && !keys.includes(k)) keys.push(k);
  }
  if (!mitBild) keys = keys.filter((k) => k !== "personen" && k !== "personenfoto");
  const namen = [...new Set(keys.map((k) => KATEGORIEN[k]))];
  let beschreibung = typeof data.beschreibung === "string" ? data.beschreibung.trim().replace(/\.+$/, "") : "";
  beschreibung = beschreibung ? beschreibung + "." : null;
  return {
    categories: namen, keys, severity: Math.max(0, ...keys.map((k) => STUFE[k] || 2)), description: beschreibung,
    warning: namen.length ? `Du lädst gerade ${verbinde(namen)} hoch.` : null,
    host: host(s.url), extern: extern(s.url), anonym, mitBild: Boolean(mitBild),
  };
}

// ------------------------------------------------------------------ Namen ohne „Herr/Frau“
const NAMEN_PROMPT = (text) => `Finde in dem Text alle personenbezogenen Angaben, die eine bestimmte Person identifizieren:
Namen von Personen (auch ohne „Herr“/„Frau“, auch Kindernamen), Wohnadressen und Geburtsdaten.
Firmen, Behörden, Städte allein und Funktionen („Rechtsanwalt“, „Jugendamt“) gehören NICHT dazu.
Gib jede Angabe genau so zurück, wie sie im Text steht.

Antworte NUR mit JSON: {"namen": ["…"], "adressen": ["…"], "geburtsdaten": ["…"]}

Text:
<<<
${text.slice(0, MAX_CHARS)}
>>>`;
const ARTEN = { namen: ["PERSON", "Name einer Person", 2], adressen: ["ADRESSE", "Adresse", 2], geburtsdaten: ["GEBURTSDATUM", "Geburtsdatum", 2] };

/** Liefert Werte, die die KI als persönliche Angaben erkannt hat: [{kind, label, severity, value}] */
export async function personenDaten(s, text) {
  const gesendet = anonymZuerst(s) ? anonymisierer().anonymize(text) : text;
  const data = parseJson(await complete(s, [
    { role: "system", content: "Du antwortest ausschließlich mit gültigem JSON." },
    { role: "user", content: NAMEN_PROMPT(gesendet) }], 0));
  const out = [];
  for (const [key, [kind, label, severity]] of Object.entries(ARTEN)) {
    for (const raw of data[key] || []) {
      const value = String(raw).trim();
      if (value.length < 3 || value.length > 120 || /^\[[A-Z_]+_\d+\]$/.test(value)) continue;   // Platzhalter = schon gefunden
      out.push({ kind, label, severity, value });
    }
  }
  return out;
}

/** Sucht die KI-Werte im Text (die KI liefert keine Positionen) und macht daraus Funde wie DWDetect.scan. */
export function alsFunde(werte, text) {
  const out = [];
  for (const w of werte) {
    let i = text.indexOf(w.value);
    while (i !== -1) {
      out.push({ kind: w.kind, label: w.label, text: w.value, start: i, end: i + w.value.length, severity: w.severity,
                 severityLabel: "mittel", display: w.value, quelle: "ki" });
      i = text.indexOf(w.value, i + w.value.length);
    }
  }
  return out;
}

// ------------------------------------------------------------------ KI-Aktionen
export const STANDARD_AKTIONEN = [
  { name: "Umformulieren", anweisung: "Formuliere den Text um: gleiche Aussage, flüssiger und klarer." },
  { name: "Kürzen", anweisung: "Kürze den Text auf etwa die Hälfte, ohne wichtige Informationen zu verlieren." },
  { name: "Freundlicher formulieren", anweisung: "Formuliere den Text freundlicher und höflicher, aber nicht unterwürfig." },
  { name: "Professioneller formulieren", anweisung: "Formuliere den Text sachlich und professionell für eine geschäftliche E-Mail." },
  { name: "Rechtschreibung korrigieren", anweisung: "Korrigiere nur Rechtschreibung, Grammatik und Zeichensetzung. Ändere sonst nichts." },
  { name: "Ins Englische übersetzen", anweisung: "Übersetze den Text ins Englische." },
  { name: "Zusammenfassen", anweisung: "Fasse den Text in 3 bis 5 Stichpunkten zusammen.", modus: "anzeigen" },
  { name: "Antwort entwerfen", anweisung: "Schreibe eine kurze, freundliche Antwort auf diese Nachricht.", modus: "einfuegen" },
];
const SYSTEM = "Du bist ein Schreibassistent. Wende die Anweisung auf den Text an und gib NUR das Ergebnis zurück – "
  + "ohne Einleitung, ohne Erklärung, ohne Anführungszeichen drumherum. Behalte die Sprache des Textes bei, "
  + "außer die Anweisung verlangt etwas anderes. Platzhalter in eckigen Klammern wie [PERSON_1] oder [IBAN_1] "
  + "sind ersetzte echte Daten: übernimm sie unverändert.";

export function aktionenLaden() {
  try {
    const a = JSON.parse(localStorage.getItem(AKTIONEN) || "null");
    if (Array.isArray(a)) return a.filter((x) => x && x.name && x.anweisung);
  } catch { /* Standard */ }
  return STANDARD_AKTIONEN.map((a) => ({ ...a }));
}
export function aktionenSpeichern(liste) {
  try { localStorage.setItem(AKTIONEN, JSON.stringify(liste)); } catch { /* privater Modus */ }
}

function aufraeumen(text) {
  let t = (text || "").trim();
  const m = /^```[a-zA-Z]*\n([\s\S]*)\n```$/.exec(t);
  if (m) t = m[1].trim();
  if (t.length >= 2 && t[0] === t[t.length - 1] && "\"'„“".includes(t[0])) t = t.slice(1, -1).trim();
  if (t.startsWith("„") && t.endsWith("“")) t = t.slice(1, -1).trim();
  return t;
}

/** Anonymisieren → Server → echte Angaben wieder einsetzen. */
export async function aktion(s, anweisung, text) {
  if (!text.trim()) throw new KiFehler("Erst einen Text eingeben oder einfügen.");
  if (text.length > MAX_AKTION) throw new KiFehler(`Text zu lang (${text.length} Zeichen, höchstens ${MAX_AKTION}).`);
  const anon = anonymisierer();
  const gesendet = anonymZuerst(s) ? anon.anonymize(text) : text;
  const antwort = await complete(s, [{ role: "system", content: SYSTEM },
    { role: "user", content: `Anweisung: ${anweisung}\n\nText:\n<<<\n${gesendet}\n>>>` }]);
  return { text: anon.restore(aufraeumen(antwort)), anonym: gesendet !== text, host: host(s.url), extern: extern(s.url) };
}

/** Für „Verbindung testen“: echte Mini-Anfrage, verständliche Meldung. */
export async function testen(s) {
  if (!baseUrl(s.url)) return { ok: false, meldung: "Bitte die Adresse des Servers eintragen." };
  try {
    let liste = [];
    try { liste = await modelle(s); } catch (e) {
      if (e.status === 401 || e.status === 403) return { ok: false, meldung: "Zugriff verweigert – Token prüfen." };
      if (!(e.status === 404 || e.status === 405)) return { ok: false, meldung: e.message };
    }
    if (s.modell && liste.length && !liste.includes(s.modell)) {
      return { ok: false, meldung: `Modell „${s.modell}“ nicht gefunden. Verfügbar: ${liste.slice(0, 8).join(", ")}` };
    }
    const probe = { ...s, modell: s.modell || liste[0] || "" };
    if (!probe.modell) return { ok: false, meldung: "Bitte ein Modell angeben." };
    const t = await thema(probe, "Einkaufsliste: Milch, Brot, Äpfel.", null, "test.txt");
    const ziel = t.extern ? ` · Daten gehen an ${t.host}${anonymZuerst(s) ? ", vorher anonymisiert" : ""}` : " · Server im eigenen Netz";
    return { ok: true, meldung: `✔ Verbindung klappt (${probe.modell})${ziel}. Testantwort: ${t.description || "ok"}`, modell: probe.modell, modelle: liste };
  } catch (e) {
    return { ok: false, meldung: e.message || String(e) };
  }
}
