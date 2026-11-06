// Datenwächter – Erkennungsregeln (JavaScript-Fassung von datenwaechter/detectors.py).
// Läuft im Browser und in Node (für Tests). Keine Netzwerkzugriffe.
(function (root) {
  "use strict";

  const HOCH = 3, MITTEL = 2, NIEDRIG = 1;
  const STUFE = { 3: "hoch", 2: "mittel", 1: "niedrig" };
  const UC = "A-ZÄÖÜ", LC = "a-zäöüß";
  const SECRET = new Set(["PRIVATER_SCHLUESSEL", "API_SCHLUESSEL", "PASSWORT", "ZUGANGSDATEN_URL", "TOKEN"]);

  const digits = (s) => s.replace(/\D/g, "");

  // Typische Verwechsler der Texterkennung in Ziffernfolgen (wie in detectors.py)
  const OCR = { O: "0", Q: "0", D: "0", I: "1", L: "1", "|": "1", S: "5", B: "8", Z: "2" };
  const ocrFix = (t) => t.replace(/[OQDIL|SBZ]/g, (c) => OCR[c]);
  function ibanValid(s) {
    const iban = s.replace(/\s/g, "").toUpperCase();
    if (ibanOk(iban)) return true;
    let fixed = iban.startsWith("DE") ? iban.slice(0, 2) + ocrFix(iban.slice(2)) : iban;
    fixed = fixed.slice(0, 2) + ocrFix(fixed.slice(2, 4)) + fixed.slice(4);
    return fixed !== iban && ibanOk(fixed);
  }
  function ibanOk(iban) {
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

  // Datum und Schlüsselwörter fürs Geburtsdatum (wie detectors.py)
  const NB = "(?<![\\p{L}\\p{N}_])";   // Wortanfang, auch vor Umlauten
  const MONAT = "(?:januar|jänner|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember|"
    + "january|february|march|may|june|july|october|december|jan|feb|mär|mrz|apr|jun|jul|aug|sept?|okt|oct|nov|dez|dec)\\.?";
  const DATUM = "(?:\\d{1,2}\\.[ ]?\\d{1,2}\\.[ ]?(?:\\d{4}|\\d{2})(?!\\d)|\\d{1,2}/\\d{1,2}/(?:\\d{4}|\\d{2})(?!\\d)"
    + `|\\d{1,2}-\\d{1,2}-\\d{4}|\\d{4}-\\d{2}-\\d{2}|\\d{1,2}\\.?[ ]?${MONAT}[ ]?\\d{4}|${MONAT}[ ]\\d{1,2},?[ ]\\d{4})`;
  const GEB = "(?:geburtsdatum(?:[ ]*(?:/|und)[ ]*-?[ ]*ort)?|geb\\.?[ ]*-?[ ]*datum|geb\\.[ ]*dat\\.?|geburtstag|geboren|geb\\.|"
    + "geb(?![\\p{L}\\p{N}_])|date of birth|birth ?date|d\\.?o\\.?b\\.?|born(?: on)?)";

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
    ["IBAN", "IBAN / Bankverbindung", /\b[A-Z]{2}[ ]?[0-9OIl]{2}(?:[ ]?[A-Z0-9Il|]{4}){2,7}(?:[ ]?[A-Z0-9Il|]{1,4})?\b/g, HOCH, { validate: ibanValid }],
    ["KREDITKARTE", "Kreditkartennummer", /(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])/g, HOCH, { validate: luhnValid }],
    ["STEUER_ID", "Steuer-ID", /(?<!\d)\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)/g, HOCH, { validate: steuerIdValid }],
    ["AUSWEIS", "Ausweis-/Passnummer",
      /\b(?:personalausweis-?nr\.?|ausweis-?nr\.?|ausweisnummer|personalausweisnummer|passnummer|pass-?nr\.?|document no\.?|führerscheinnummer)\s*:?\s*(?<v>(?=[A-Za-z]*\d)[A-Z0-9]{8,11})\b/gi, HOCH],
    ["SOZIALVERSICHERUNG", "Sozialversicherungsnummer",
      /\b\d{2}[ ]?(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}[ ]?[A-Z][ ]?\d{3}\b/g, HOCH],
    // „geb. am 03.04.1985“, „Geburtsdatum:\n12. März 1985“, „geboren am Montag, dem 3.5.90“, „* 12.03.1985“, „Jahrgang 1985“
    ["GEBURTSDATUM", "Geburtsdatum", new RegExp(`${NB}${GEB}[^\\d\\n.]{0,40}?(?:\\n[^\\d\\n.]{0,15}?)?(?<v>${DATUM})`, "giu"), MITTEL],
    ["GEBURTSDATUM", "Geburtsdatum", new RegExp(`(?:(?<![\\p{L}\\p{N}_*])\\*|(?<=\\p{L} )\\*[ ]?)(?<v>${DATUM})`, "giu"), MITTEL],
    ["GEBURTSDATUM", "Geburtsjahr",
      new RegExp(`${NB}(?:geburtsjahr(?:gang)?|jahrgang|geb\\.|geboren(?: im jahr?| in)?|born(?: in)?|year of birth)[ ]*:?[ ]*(?<v>(?:19|20)\\d{2})(?![\\d.])`, "giu"), MITTEL],
    ["EMAIL", "E-Mail-Adresse", /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, MITTEL],
    ["TELEFON", "Telefonnummer",
      /(?<![\w+/.])(?:\+\d{1,3}|00\d{1,3}|0)[ /.-]?\(?\d{2,5}\)?(?:[ /.-]?\d{2,}){1,4}(?!\w|\.\d)/g, MITTEL, { minDigits: 7, maxDigits: 15 }],
    ["ADRESSE", "Straße und Hausnummer",
      // „Hauptstraße 12“, „Karl-Marx-Straße 5“, „Bad Homburger Weg 3“ – aber nie ganze Sätze davor
      new RegExp(`(?<![\\p{L}\\d])(?:[${UC}][${LC}]+(?:-[${UC}][${LC}]+)*(?:straße|strasse|str\\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|steig)|(?:(?:[${UC}][${LC}]+-){1,3}|(?:(?:Bad|Sankt|St\\.|Alte|Neue|Große|Kleine|Obere|Untere) )?[${UC}][${LC}]+er )(?:Straße|Strasse|Str\\.|Weg|Gasse|Platz|Allee|Ring|Damm|Ufer|Chaussee|Pfad|Steig))\\s+\\d{1,4}(?:\\s?[a-zA-Z])?(?![\\p{L}\\d])`, "gu"), MITTEL],
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
    found.push(...namenFinden(text));
    const personen = aufloesen(found).filter((f) => f.kind === "PERSON");
    found.push(...weitereNennungen(text, personen));   // „Schneider“ allein, nachdem „Thomas Schneider“ erkannt ist
    const kept = aufloesen(found);
    for (const f of kept) f.display = masked(f);
    return kept;
  }

  // Überlappungen: höhere Stufe, dann längerer Treffer gewinnt
  function aufloesen(found) {
    const sorted = [...found].sort((a, b) => b.severity - a.severity || (b.end - b.start) - (a.end - a.start) || a.start - b.start);
    const kept = [];
    for (const f of sorted) if (kept.every((k) => f.end <= k.start || f.start >= k.end)) kept.push(f);
    return kept.sort((a, b) => a.start - b.start);
  }

  // ---------------------------------------------------------------- Namen ohne KI (wie datenwaechter/namen.py)
  const VN = (typeof module !== "undefined" && module.exports ? (require("./vornamen.js"), globalThis.DWVornamen) : root.DWVornamen)
    || { sicher: [], mehrdeutig: [], stopp: [], org: [] };
  const SICHER = new Set(VN.sicher), MEHRDEUTIG = new Set(VN.mehrdeutig), ALLE = new Set([...VN.sicher, ...VN.mehrdeutig]);
  const STOPP = new Set(VN.stopp), ORG = new Set(VN.org);
  const WORT = "\\p{L}+(?:-\\p{L}+)*";
  const sticky = (src, flags = "") => new RegExp(src, "uy" + flags);
  const R_WORT = sticky(WORT), R_LEER = sticky("[ \\t\\u00a0]{1,3}"), R_KOMMA = sticky(",[ \\t]*");
  const R_PARTIKEL = sticky("(?:von und zu|von der|von den|van der|van den|van de|de la|von|van|vom|zur|zu|de|da|di|del|della|du|dos|ten|ter|le|la)[ \\t]+");
  const an = (re, text, pos) => { re.lastIndex = pos; return re.exec(text); };
  const ganz = (src) => new RegExp(`^(?:${src})$`, "u");
  const R_LEER_GANZ = ganz("[ \\t\\u00a0]{1,3}"), R_KOMMA_GANZ = ganz(",[ \\t]*");
  const istGross = (c) => c !== c.toLowerCase() && c === c.toUpperCase();
  const istKlein = (c) => c !== c.toUpperCase() && c === c.toLowerCase();
  const versalWort = (w) => w === w.toUpperCase() && w !== w.toLowerCase();
  const gross = (w) => w.length > 0 && istGross(w[0]) && [...w.slice(1)].some(istKlein);

  function vorname(w, namen, versal = false) {
    let teile = w.split("-");
    if (versal) teile = teile.map((t) => t.slice(0, 1) + t.slice(1).toLowerCase());
    else if (!gross(w)) return false;
    return teile.every((t) => namen.has(t));
  }
  function nachname(w, versal = false) {
    if (versal) return versalWort(w) && w.length > 1 && !STOPP.has(w.slice(0, 1) + w.slice(1).toLowerCase());
    return gross(w) && w.length > 1 && !STOPP.has(w) && !ORG.has(w);
  }
  function nameAb(text, pos, maxTeile = 3, komma = false) {
    const m = an(R_WORT, text, pos);
    if (!m) return null;
    const versal = versalWort(m[0]) && m[0].length > 1;
    if (!nachname(m[0], versal)) return null;
    let start = m.index, ende = m.index + m[0].length, teile = 1;
    while (teile < maxTeile) {
      let p = ende;
      const sep = an(R_LEER, text, p) || (komma && an(R_KOMMA, text, p));
      if (!sep) break;
      p = sep.index + sep[0].length;
      const part = an(R_PARTIKEL, text, p);
      if (part && !versal) p = part.index + part[0].length;
      const n = an(R_WORT, text, p);
      if (!n || !nachname(n[0], versal)) {
        if (n && ORG.has(n[0])) return null;    // „Musterfirma GmbH“ ist kein Name
        break;
      }
      ende = n.index + n[0].length; teile++;
    }
    return [start, ende];
  }
  const nurLeer = (text, a, b) => R_LEER_GANZ.test(text.slice(a, b));
  const R_LISTENANFANG = /(?:^[ \t]*(?:(?:\d{1,3}[.)]|[•*\-–])[ \t]*)?|[:;][ \t]*)$/u;
  const R_DATUM_VOR = /\d{1,2}\.[ \t]*$/u, R_DATUM_NACH = sticky("\\.?[ \\t]*\\d");
  const wieDatum = (text, s, e) => R_DATUM_VOR.test(text.slice(Math.max(0, s - 6), s)) || Boolean(an(R_DATUM_NACH, text, e));
  const person = (text, s, e, label = "Name") =>
    ({ kind: "PERSON", label, text: text.slice(s, e), start: s, end: e, severity: MITTEL, severityLabel: STUFE[MITTEL] });

  function ausListe(text) {
    const toks = [...text.matchAll(new RegExp(WORT, "gu"))].map((m) => ({ w: m[0], s: m.index, e: m.index + m[0].length }));
    const out = [];
    let i = 0;
    while (i < toks.length) {
      const { w, s, e } = toks[i];
      const versal = versalWort(w) && w.length > 1;
      if (vorname(w, ALLE, versal)) {
        let j = i + 1;   // weitere Vornamen: „Anna Lena“
        while (j < toks.length && j - i < 3 && nurLeer(text, toks[j - 1].e, toks[j].s) && vorname(toks[j].w, ALLE, versal)) j++;
        const ende = toks[j - 1].e;
        const sep = an(R_LEER, text, ende);
        if (sep) {
          let p = sep.index + sep[0].length;
          const part = an(R_PARTIKEL, text, p);
          if (part && !versal) p = part.index + part[0].length;
          const n = an(R_WORT, text, p);
          if (n && nachname(n[0], versal)) {
            const nEnde = n.index + n[0].length;
            out.push(person(text, s, nEnde));
            i = j;
            while (i < toks.length && toks[i].s < nEnde) i++;
            continue;
          }
        }
        if (j > i + 1) out.push(person(text, s, ende));            // „Thomas Peter“
        else if (!versal && vorname(w, SICHER) && !wieDatum(text, s, e)) out.push(person(text, s, e, "Vorname"));
        i = j;
        continue;
      }
      // „Schneider, Thomas“ (Listen, Formulare) – nur am Zeilenanfang oder nach Doppelpunkt/Aufzählung
      if (i + 1 < toks.length && nachname(w) && !vorname(w, ALLE) && R_KOMMA_GANZ.test(text.slice(e, toks[i + 1].s))
          && vorname(toks[i + 1].w, ALLE) && !wieDatum(text, toks[i + 1].s, toks[i + 1].e)
          && R_LISTENANFANG.test(text.slice(text.lastIndexOf("\n", s - 1) + 1, s))) {
        const nach = toks[i + 2];
        if (!(nach && nurLeer(text, toks[i + 1].e, nach.s) && nachname(nach.w))) {
          out.push(person(text, s, toks[i + 1].e));
          i += 2;
          continue;
        }
      }
      // Genitiv: „Mias Kita“, „Pauls Zeugnis“
      if (!versal && w.endsWith("s") && w.length > 3 && vorname(w.slice(0, -1), SICHER) && !SICHER.has(w)) out.push(person(text, s, e - 1, "Vorname"));
      i++;
    }
    return out;
  }

  const R = (src, flags) => new RegExp(src, "gu" + flags);
  const R_TITEL = R("(?<![\\p{L}\\p{N}_])(?:Hr\\.|Fr\\.|Dr\\.|Prof\\.|Herrn?|Frau|Mr\\.?|Mrs\\.?|Ms\\.?|Miss)[ \\t]+"
    + "(?:(?:Dr|Prof|med|dent|jur|phil|rer\\.[ ]?nat|Dipl\\.-Ing|Ing|h\\.[ ]?c)\\.?[ \\t]+)*", "");
  const R_ANREDE = R("(?:^|(?<=[\\s>„\"(]))(?:liebe[rs]?|hallo|hi|hey|moin|servus|dear|hello|ciao|salut|guten (?:tag|morgen|abend))[ \\t]+", "i");
  const R_GRUSS = R("^[ \\t]*(?:mit (?:freundlichen|besten|herzlichen|lieben) grüßen|freundliche grüße|viele grüße|liebe grüße|"
    + "beste grüße|herzliche grüße|schöne grüße|sonnige grüße|grüße|gruß|lg|vg|mfg|hochachtungsvoll|best regards|kind regards|"
    + "best wishes|warm regards|regards|cheers|bis bald|bis dann|dein|deine|euer|eure|ihr|ihre)[ \\t]*[,.!]?[ \\t]*(?:\\n[ \\t]*){1,2}", "im");
  const R_GRUSS_ZEILE = R("^[ \\t]*(?:dein|deine|euer|eure|lg|vg|gruß|grüße|cheers)[ \\t,]+", "im");
  const R_FELD = R("(?<![\\p{L}\\p{N}_])(?:vor-? und (?:nach|zu)name|(?:nach)?name,[ ]?vorname|vorname,[ ]?(?:nach)?name|vollständiger name|"
    + "vorname[n]?|nachname|familienname|zuname|geburtsname|rufname|name (?:des kindes|der mutter|des vaters|der patientin|des patienten)|"
    + "patient(?:in)?|mieter(?:in)?|vermieter(?:in)?|kunde|kundin|kontoinhaber(?:in)?|inhaber(?:in)?|antragsteller(?:in)?|"
    + "arbeitnehmer(?:in)?|mitarbeiter(?:in)?|ehemann|ehefrau|ehepartner(?:in)?|kind|sohn|tochter|vater|mutter|schüler(?:in)?|"
    + "empfänger(?:in)?|absender(?:in)?|versicherte[r]?|versicherungsnehmer(?:in)?|bewerber(?:in)?|ansprechpartner(?:in)?|"
    + "verfasser(?:in)?|erziehungsberechtigte[r]?|unterzeichner(?:in)?|teilnehmer(?:in)?|mandant(?:in)?|klient(?:in)?|"
    + "beschuldigte[r]?|kläger(?:in)?|beklagte[r]?|zeug(?:e|in)|betreuer(?:in)?|vormund|full name|first name|last name|surname|"
    + "given name|name)[ \\t]*:[ \\t]*", "i");
  const R_FAMILIE = R("(?<![\\p{L}\\p{N}_])(?:Familie|Fam\\.|Eheleute|Ehepaar|Geschwister)[ \\t]+", "");
  const R_VERWANDT = R("(?<![\\p{L}\\p{N}_])(?:Sohn|Tochter|Kind|Enkel(?:in|kind)?|Bruder|Schwester|Ehemann|Ehefrau|Mann|Partner(?:in)?|"
    + "Freund(?:in)?|Lebensgefährt(?:e|in)|Verlobte[r]?|Vater|Mutter|Papa|Mama|Oma|Opa|Onkel|Tante|Cousine?|Neffe|Nichte|Schwager|"
    + "Schwägerin|Kollege|Kollegin|Chef(?:in)?|Nachbar(?:in)?|Patient(?:in)?|Klient(?:in)?|Mandant(?:in)?|Schüler(?:in)?|Azubi|Ex-Mann|"
    + "Ex-Frau|Exmann|Exfrau|Stief(?:sohn|tochter|vater|mutter)|Pflegekind|Baby)[ \\t]+", "");
  const R_ALTER = sticky("[ \\t]*\\([ \\t]*\\d{1,2}(?![\\p{L}\\p{N}_])");
  const R_ZEILENENDE = sticky("[ \\t]*(?:\\n|$|,)");
  const R_NACH_ANREDE = sticky("[ \\t]*(?:[,!:;]|\\n|$)");
  const R_NACH_GRUSSZEILE = sticky("[ \\t]*(?:\\n|$|[.!])");

  function anStellen(text) {
    const out = [];
    const nimm = (re, teile, { komma = false, danach = null, bedingung = null } = {}) => {
      for (const m of text.matchAll(re)) {
        const span = nameAb(text, m.index + m[0].length, teile, komma);
        if (!span) continue;
        if (danach && !an(danach, text, span[1])) continue;
        if (bedingung && !bedingung(span)) continue;
        out.push(person(text, span[0], span[1]));
      }
    };
    nimm(R_TITEL, 3);
    nimm(R_ANREDE, 2, { danach: R_NACH_ANREDE });
    nimm(R_GRUSS, 3, { danach: R_ZEILENENDE });
    nimm(R_GRUSS_ZEILE, 3, { danach: R_NACH_GRUSSZEILE });
    nimm(R_FELD, 4, { komma: true });
    nimm(R_FAMILIE, 2);
    nimm(R_VERWANDT, 2, { bedingung: (sp) => vorname(an(R_WORT, text, sp[0])[0], ALLE) || Boolean(an(R_ALTER, text, sp[1])) });
    return out;
  }

  const namenFinden = (text) => [...ausListe(text), ...anStellen(text)];

  function weitereNennungen(text, personen) {
    const teile = new Set();
    for (const f of personen) {
      for (const t of f.text.match(new RegExp(WORT, "gu")) || []) {
        if (t.length >= 3 && (gross(t) || versalWort(t)) && !STOPP.has(t) && !ORG.has(t) && !MEHRDEUTIG.has(t)) teile.add(t);
      }
    }
    const out = [];
    for (const t of [...teile].sort()) {
      const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      for (const m of text.matchAll(new RegExp(`(?<!\\p{L})${esc}(?=s?(?!\\p{L}))`, "gu"))) out.push(person(text, m.index, m.index + t.length));
    }
    return out;
  }

  class Anonymizer {
    constructor() { this.byValue = new Map(); this.byPlaceholder = new Map(); this.counter = {}; }
    placeholder(f) {
      const key = f.kind + "\u0000" + f.text.trim();
      if (!this.byValue.has(key) && f.kind === "PERSON") {
        const same = this.samePerson(f.text.trim());
        if (same) {   // „Herr Schneider“ nach „Herrn Thomas Schneider“ = dieselbe Person
          this.byValue.set(key, same);
          if (f.text.length > this.byPlaceholder.get(same).length) this.byPlaceholder.set(same, f.text);
        }
      }
      if (!this.byValue.has(key)) {
        const n = (this.counter[f.kind] = (this.counter[f.kind] || 0) + 1);
        const ph = `[${f.kind}_${n}]`;
        this.byValue.set(key, ph);
        this.byPlaceholder.set(ph, f.text);
      }
      return this.byValue.get(key);
    }
    samePerson(value) {
      // Teil eines Namens ↔ voller Name: „Schneider“ oder „Mia“ ↔ „Mia Schneider“; bei mehreren Kandidaten nichts zusammenlegen
      const worte = (t) => t.match(new RegExp(WORT, "gu")) || [];
      const parts = worte(value).map((p) => p.toLowerCase());
      if (!parts.length) return null;
      const matches = new Set();
      for (const [k, ph] of this.byValue) {
        const [kind, v] = k.split("\u0000");
        if (kind !== "PERSON") continue;
        const vparts = worte(v).map((p) => p.toLowerCase()), known = worte(this.byPlaceholder.get(ph)).map((p) => p.toLowerCase());
        if (!vparts.length || !known.length) continue;
        if (parts.length === 1) {
          if (vparts.length > 1 && (parts[0] === vparts.at(-1) || parts[0] === vparts[0])) matches.add(ph);
          else if (vparts.length === 1 && parts[0] === vparts[0]) matches.add(ph);
        } else if (known.length === 1 && (known[0] === parts[0] || known[0] === parts.at(-1))) matches.add(ph);
      }
      return matches.size === 1 ? [...matches][0] : null;
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
