// Datenwächter – Erkennungsregeln (JavaScript-Fassung von datenwaechter/detectors.py).
// Läuft im Browser und in Node (für Tests). Keine Netzwerkzugriffe.
(function (root) {
  "use strict";

  const HOCH = 3, MITTEL = 2, NIEDRIG = 1;
  const STUFE = { 3: "hoch", 2: "mittel", 1: "niedrig" };
  const UC = "A-ZÄÖÜ", LC = "a-zäöüß";
  const SECRET = new Set(["PRIVATER_SCHLUESSEL", "API_SCHLUESSEL", "PASSWORT", "ZUGANGSDATEN_URL", "TOKEN"]);

  const digits = (s) => s.replace(/\D/g, "");

  function ibanValid(s) {
    const iban = s.replace(/\s/g, "").toUpperCase();
    if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(iban)) return false;
    if (iban.startsWith("DE") && iban.length !== 22) return false;
    const r = iban.slice(4) + iban.slice(0, 4);
    let rem = 0;
    for (const ch of r) {
      const v = parseInt(ch, 36).toString();
      for (const d of v) rem = (rem * 10 + Number(d)) % 97;
    }
    return rem === 1;
  }

  function luhnValid(s) {
    const d = digits(s);
    if (d.length < 13 || d.length > 19 || new Set(d).size === 1) return false;
    let sum = 0;
    for (let i = 0; i < d.length; i++) {
      let n = Number(d[d.length - 1 - i]);
      if (i % 2 === 1) { n *= 2; if (n > 9) n -= 9; }
      sum += n;
    }
    return sum % 10 === 0;
  }

  function steuerIdValid(s) {
    const d = digits(s);
    if (d.length !== 11 || d[0] === "0") return false;
    let product = 10;
    for (let i = 0; i < 10; i++) {
      const total = (Number(d[i]) + product) % 10 || 10;
      product = (total * 2) % 11;
    }
    return (11 - product) % 10 === Number(d[10]);
  }

  // [Typ, Anzeige, RegExp, Stufe, Optionen]  – Gruppe "v" markiert den eigentlichen Wert
  const RULES = [
    ["PRIVATER_SCHLUESSEL", "Privater Schlüssel", /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----/g, HOCH],
    ["API_SCHLUESSEL", "API-Schlüssel (Anthropic)", /\bsk-ant-[A-Za-z0-9_\-]{20,}/g, HOCH],
    ["API_SCHLUESSEL", "API-Schlüssel (OpenAI)", /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}/g, HOCH],
    ["API_SCHLUESSEL", "AWS-Zugangsschlüssel", /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, HOCH],
    ["API_SCHLUESSEL", "GitHub-Token", /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b/g, HOCH],
    ["API_SCHLUESSEL", "Slack-Token", /\bxox[abprs]-[A-Za-z0-9-]{10,}/g, HOCH],
    ["API_SCHLUESSEL", "Google-API-Schlüssel", /\bAIza[0-9A-Za-z_\-]{35}\b/g, HOCH],
    ["API_SCHLUESSEL", "Stripe-Schlüssel", /\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b/g, HOCH],
    ["TOKEN", "JWT / Sitzungs-Token", /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, HOCH],
    ["ZUGANGSDATEN_URL", "Datenbank-Zugang mit Passwort",
      /\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|mssql|ftp|sftp):\/\/[^\s:@/]+:[^\s@/]+@[^\s"'<>]+/g, HOCH],
    ["PASSWORT", "Passwort / Geheimnis",
      /\b(?:passwor[dt]|kennwort|passwd|pwd|secret|client[_-]?secret|api[_-]?key|access[_-]?token)\b["']?\s*[:=]\s*["']?(?<v>[^\s"',;]{4,})/gi, HOCH],
    ["IBAN", "IBAN / Bankverbindung", /\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b/g, HOCH, { validate: ibanValid }],
    ["KREDITKARTE", "Kreditkartennummer", /(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])/g, HOCH, { validate: luhnValid }],
    ["STEUER_ID", "Steuer-ID", /(?<!\d)\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)/g, HOCH, { validate: steuerIdValid }],
    ["AUSWEIS", "Ausweis-/Passnummer",
      /\b(?:personalausweis-?nr\.?|ausweis-?nr\.?|ausweisnummer|personalausweisnummer|passnummer|pass-?nr\.?|document no\.?|führerscheinnummer)\s*:?\s*(?<v>(?=[A-Za-z]*\d)[A-Z0-9]{8,11})\b/gi, HOCH],
    ["SOZIALVERSICHERUNG", "Sozialversicherungsnummer",
      /\b\d{2}[ ]?(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}[ ]?[A-Z][ ]?\d{3}\b/g, HOCH],
    ["GEBURTSDATUM", "Geburtsdatum",
      /\b(?:geb(?:oren|\.)?(?:\s+am)?|geburtsdatum|geburtstag|date of birth|dob)\s*:?\s*(?<v>\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}|\d{4}-\d{2}-\d{2})/gi, MITTEL],
    ["EMAIL", "E-Mail-Adresse", /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, MITTEL],
    ["TELEFON", "Telefonnummer",
      /(?<![\w+/.])(?:\+\d{1,3}|00\d{1,3}|0)[ /.-]?\(?\d{2,5}\)?(?:[ /.-]?\d{2,}){1,4}(?!\w|\.\d)/g, MITTEL, { minDigits: 7, maxDigits: 15 }],
    ["ADRESSE", "Straße und Hausnummer",
      new RegExp(`(?<![\\p{L}\\d])[${UC}][${LC}]+(?:[- ][${UC}]?[${LC}]+)*(?:straße|strasse|str\\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|steig)\\s+\\d{1,4}(?:\\s?[a-zA-Z])?(?![\\p{L}\\d])`, "gu"), MITTEL],
    ["ADRESSE", "PLZ und Ort",
      new RegExp(`(?<![\\d.,\\p{L}])\\d{5}\\s+(?!(?:Euro|EUR|Stück|Mal|Jahre|Tage|Mitarbeiter|Kunden|Nutzer)(?![\\p{L}]))[${UC}][${LC}]+(?:[ -](?:am|an der|im|ob der)?\\s?[${UC}][${LC}]+)?(?![\\p{L}])`, "gu"), MITTEL],
    ["PERSON", "Name (Anrede)",
      new RegExp(`(?<![\\p{L}])(?:Herr|Herrn|Frau|Mr\\.?|Mrs\\.?|Ms\\.?)\\s+(?:(?:Dr|Prof)\\.\\s+)*(?<v>[${UC}][${LC}]+(?:[- ][${UC}][${LC}]+)?)`, "gu"), MITTEL],
    ["IP_ADRESSE", "IP-Adresse",
      /(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])/g, NIEDRIG],
  ];

  function masked(f) {
    if (SECRET.has(f.kind)) {
      const t = f.text.replace(/\n/g, " ");
      return t.length <= 8 ? "****" : `${t.slice(0, 4)}…${t.slice(-3)} (${f.text.length} Zeichen)`;
    }
    return f.text.length <= 80 ? f.text : f.text.slice(0, 77) + "…";
  }

  function scan(text) {
    const found = [];
    for (const [kind, label, re, severity, opt = {}] of RULES) {
      re.lastIndex = 0;
      for (const m of text.matchAll(re)) {
        let value = m[0], start = m.index;
        if (m.groups && m.groups.v !== undefined) {
          value = m.groups.v;
          start = m.index + m[0].lastIndexOf(value);
        }
        if (opt.validate && !opt.validate(value)) continue;
        if (opt.minDigits) {
          const n = digits(value).length;
          if (n < opt.minDigits || n > opt.maxDigits) continue;
        }
        found.push({ kind, label, text: value, start, end: start + value.length, severity, severityLabel: STUFE[severity] });
      }
    }
    // Überlappungen: höhere Stufe, dann längerer Treffer gewinnt
    found.sort((a, b) => b.severity - a.severity || (b.end - b.start) - (a.end - a.start) || a.start - b.start);
    const kept = [];
    for (const f of found) if (kept.every((k) => f.end <= k.start || f.start >= k.end)) kept.push(f);
    kept.sort((a, b) => a.start - b.start);
    for (const f of kept) f.display = masked(f);
    return kept;
  }

  class Anonymizer {
    constructor() { this.byValue = new Map(); this.byPlaceholder = new Map(); this.counter = {}; }
    placeholder(f) {
      const key = f.kind + "\u0000" + f.text.trim();
      if (!this.byValue.has(key)) {
        const n = (this.counter[f.kind] = (this.counter[f.kind] || 0) + 1);
        const ph = `[${f.kind}_${n}]`;
        this.byValue.set(key, ph);
        this.byPlaceholder.set(ph, f.text);
      }
      return this.byValue.get(key);
    }
    anonymize(text, findings = scan(text)) {
      let out = "", last = 0;
      for (const f of findings) {
        if (f.start < last) continue;
        out += text.slice(last, f.start) + this.placeholder(f);
        last = f.end;
      }
      return out + text.slice(last);
    }
    restore(text) {
      let out = text;
      for (const [ph, orig] of this.byPlaceholder) out = out.split(ph).join(orig);
      return out;
    }
    exportMapping() { return Object.fromEntries(this.byPlaceholder); }
    importMapping(mapping) {
      for (const [ph, orig] of Object.entries(mapping || {})) {
        const m = /^\[([A-Z_]+)_(\d+)\]$/.exec(ph);
        if (!m) continue;
        this.byValue.set(m[1] + "\u0000" + orig.trim(), ph);
        this.byPlaceholder.set(ph, orig);
        this.counter[m[1]] = Math.max(this.counter[m[1]] || 0, Number(m[2]));
      }
    }
  }

  // ---------------------------------------------------------------- Inhalts-Check per Stichwort (wie content_check.py)
  const CAT_DATA = typeof module !== "undefined" && module.exports
    ? require("../datenwaechter/kategorien.json") : root.DWKategorien || {};
  const W = "[\\p{L}\\p{N}_]";
  const CATS = Object.entries(CAT_DATA).filter(([k]) => !k.startsWith("_")).map(([, c]) => ({
    name: c.name, stufe: c.stufe,
    terms: c.begriffe.map((raw) => {
      const strong = raw.startsWith("!");
      let word = raw.replace(/^!/, "");
      const prefix = word.endsWith("*");
      word = word.replace(/\*$/, "");
      const esc = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+");
      return { strong, re: new RegExp(`(?<!${W})${esc}${prefix ? W + "*" : `(?!${W})`}`, "iu") };
    }),
  }));

  function contentCheck(text) {
    const categories = [], hints = [];
    let severity = 0;
    for (const cat of CATS) {
      const hits = [];
      let strongHit = false;
      for (const t of cat.terms) {
        const m = t.re.exec(text);
        if (m) { hits.push(m[0]); strongHit = strongHit || t.strong; }
      }
      const unique = [...new Set(hits)];   // gleiches Wort nur einmal (z. B. „Familie*“ und „Familiengericht*“)
      if (strongHit || new Set(unique.map((h) => h.toLowerCase())).size >= 2) {
        categories.push(cat.name);
        hints.push(...unique.slice(0, 3).filter((h) => !hints.includes(h)));
        severity = Math.max(severity, cat.stufe);
      }
    }
    const join = (a) => (a.length === 1 ? a[0] : a.slice(0, -1).join(", ") + " und " + a[a.length - 1]);
    const warning = categories.length
      ? `Du lädst gerade ${join(categories)} hoch (Hinweise: ${hints.slice(0, 5).map((h) => `„${h}“`).join(", ")}).`
      : null;
    return { categories, hints, severity, warning, description: null, backend: "stichworte", source: "Erkannt an Stichwörtern" };
  }

  const api = { scan, contentCheck, Anonymizer, ibanValid, luhnValid, steuerIdValid, HOCH, MITTEL, NIEDRIG };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DWDetect = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
