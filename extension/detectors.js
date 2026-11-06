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
  const NB = "(?<![\\p{L}\\p{N}_])";   // Wortanfang, auch vor Umlauten (wie \\b in Python)
  const NA = "(?![\\p{L}\\p{N}_])";      // Wortende
  // Groß/klein egal nur für dieses Wort (wie (?i:…) in Python)
  const ci = (w) => [...w].map((c) => (c.toLowerCase() !== c.toUpperCase() ? `[${c.toLowerCase()}${c.toUpperCase()}]`
    : c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))).join("");
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
    ["GERAETE_ID", "IMEI (Handy)", /(?<![\p{L}\p{N}_])IMEI\s*[:.]?\s*(?<v>\d{15})(?![\p{L}\p{N}_])/giu, HOCH, { validate: luhnValid }],
    ["IBAN", "IBAN / Bankverbindung", /\b[A-Z]{2}[ ]?[0-9OIl]{2}(?:[ ]?[A-Z0-9Il|]{4}){2,7}(?:[ ]?[A-Z0-9Il|]{1,4})?\b/g, HOCH, { validate: ibanValid }],
    ["KREDITKARTE", "Kreditkartennummer", /(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])/g, HOCH, { validate: luhnValid }],
    ["STEUER_ID", "Steuer-ID", /(?<!\d)\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)/g, HOCH, { validate: steuerIdValid }],
    ["AUSWEIS", "Ausweis-/Passnummer",
      /\b(?:personalausweis-?nr\.?|ausweis-?nr\.?|ausweisnummer|personalausweisnummer|reisepassnummer|reisepass-?nr\.?|passnummer|pass-?nr\.?|document no\.?|führerscheinnummer)\s*:?\s*(?<v>(?=[A-Za-z]*\d)[A-Z0-9]{8,11})\b/gi, HOCH],
    ["SOZIALVERSICHERUNG", "Sozialversicherungsnummer",
      /\b\d{2}[ ]?(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}[ ]?[A-Z][ ]?\d{3}\b/g, HOCH],
    // „geb. am 03.04.1985“, „Geburtsdatum:\n12. März 1985“, „geboren am Montag, dem 3.5.90“, „* 12.03.1985“, „Jahrgang 1985“
    ["GEBURTSDATUM", "Geburtsdatum", new RegExp(`${NB}${GEB}[^\\d\\n.]{0,40}?(?:\\n[^\\d\\n.]{0,15}?)?(?<v>${DATUM})`, "giu"), MITTEL],
    // „*12.03.1985“, „Becker * 12.03.1985“, „(* 4.4.1997)“, „, * 21.3.1979“
    ["GEBURTSDATUM", "Geburtsdatum",
      new RegExp(`(?:(?<![\\p{L}\\p{N}_*])\\*|(?<=[^\\s*] )\\*[ ]?|(?<=\\()\\*[ ]?)(?<v>${DATUM})`, "giu"), MITTEL],
    ["GEBURTSDATUM", "Geburtsjahr",
      new RegExp(`${NB}(?:geburtsjahr(?:gang)?|jahrgang|geb\\.|geboren(?: im jahr?| in)?|born(?: in)?|year of birth)[ ]*:?[ ]*(?<v>(?:19|20)\\d{2})(?![\\d.])`, "giu"), MITTEL],
    ["EMAIL", "E-Mail-Adresse", /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, MITTEL],
    ["TELEFON", "Telefonnummer",   // auch „+43(0)333 775-8447“, „(0461) 708 - 223“
      /(?<![\p{L}\p{N}_+/.(])(?:\(?(?:\+\d{1,3}|00\d{1,3})\)?(?:[ ]?\(0\))?|\(?0)[ /.-]?\(?\d{2,5}\)?(?:(?:[ ]?[/.-][ ]?|[ ])?\d{2,}){1,4}(?![\p{L}\p{N}_]|\.\d)/gu,
      MITTEL, { minDigits: 7, maxDigits: 16 }],
    ["ADRESSE", "Straße und Hausnummer",
      // „Hauptstraße 12“, „Karl-Marx-Straße 5“, „Bad Homburger Weg 3“ – aber nie ganze Sätze davor
      // auch „Innsbrucker Landstraße 22a“, „Rote Str. 3“, „Friesische Str. 21 a“, „Kantstraße. 21“
      new RegExp(`${NB}(?!(?:Die|Eine|Seine|Meine|Ihre|Deine|Unsere|Keine|Diese|Jede|Alle|Andere)${NA})`
        + `(?:(?:[${UC}][${LC}]+(?:er|e|es|en) )?[${UC}][${LC}]+(?:-[${UC}][${LC}]+)*`
        + "(?:straße|strasse|str\\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|steig|landstraße)"
        + `|(?:(?:[${UC}][${LC}]+-){1,3}|(?:(?:Bad|Sankt|St\\.|Alte|Neue|Große|Kleine|Obere|Untere) )?[${UC}][${LC}]+(?:er|e|es|en) )`
        + "(?:Straße|Strasse|Str\\.|Weg|Gasse|Platz|Allee|Ring|Damm|Ufer|Chaussee|Pfad|Steig))"
        + `\\.?\\s+\\d{1,4}(?:\\s?[a-zA-Z])?${NA}`, "gu"), MITTEL],
    ["ADRESSE", "PLZ und Ort",
      new RegExp(`(?<![\\p{L}\\p{N}_-])(?:A|CH|D|AT|DE|FL)-\\d{4,5}[ \\t]+[${UC}][${LC}]+(?:[ -][${UC}][${LC}]+)?${NA}`, "gu"), MITTEL],
    ["ADRESSE", "Straße und Hausnummer",   // „Am Waldsaum 21“, „An der Mühle 3“, „Im Winkel 7“
      new RegExp(`${NB}(?:Am|An der|An den|Im|In der|Auf der|Auf dem|Zum|Zur|Hinter der|Unter den|Vor dem)[ \\t]+`
        + `(?![\\p{L}\\p{N}_-]*(?:ung|ion|heit|keit|schaft|tät)${NA})`
        + "(?!(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Wochenende|Ende|Anfang|Abend|"
        + `Morgen|Tag|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)${NA})`
        + `[${UC}][${LC}]+(?:-[${UC}][${LC}]+)*[ \\t]+\\d{1,4}(?:\\s?[a-zA-Z])?${NA}`, "gu"), MITTEL],
    ["ADRESSE", "Straße und Hausnummer",   // Adressblock: „Korekamp 15“ in der Zeile über „47809 Krefeld“
      new RegExp(`^[ \\t]*(?<v>[${UC}][${LC}-]+(?:[ \\t][${UC}][${LC}-]+)?[ \\t]\\d{1,4}[ \\t]?[a-zA-Z]?)`
        + `(?:[ \\t]*\\n[ \\t]*|,[ \\t]*|[ \\t]{2,})(?:[A-Z]{1,2}-)?\\d{4,5}[ \\t]+[${UC}]`, "gmu"), MITTEL],
    ["ADRESSE", "PLZ und Ort",   // vierstellig (Österreich/Schweiz) nach Straße oder „wohnhaft“
      new RegExp(`(?:(?<=\\d, )|(?<=\\d[a-z], )|(?<=${ci("wohnhaft")} )|(?<=${ci("wohnhaft in")} )|(?<=${ci("wh.:")} )|(?<=${ci("wh.")} ))`
        + `\\d{4}[ \\t]+[${UC}][${LC}]+(?:[ -][${UC}][${LC}]+)?${NA}`, "gu"), MITTEL],
    ["ADRESSE", "Wohnort",
      new RegExp(`${NB}(?:${["wohnhaft", "wohnt", "lebt", "geboren", "aufgewachsen"].map(ci).join("|")})[ \\t]+(?:in[ \\t]+)?`
        + `(?<v>[${UC}][${LC}]+(?:[ -](?:am|an der|im|bei)?[ ]?[${UC}][${LC}]+)?)${NA}`, "gu"), MITTEL],
    ["ADRESSE", "PLZ und Ort",
      new RegExp(`(?<![\\p{L}\\p{N}_.,])\\d{5}[ \\t]+(?!(?:Euro|EUR|Stück|Mal|Jahre|Tage|Mitarbeiter|Kunden|Nutzer)${NA})`
        + `[${UC}][${LC}]+(?:[ -](?:am|an der|im|ob der)?\\s?[${UC}][${LC}]+)?${NA}`, "gu"), MITTEL],
    ["PERSON", "Name (Anrede)",
      new RegExp(`${NB}(?:Herr|Herrn|Frau|Mr\\.?|Mrs\\.?|Ms\\.?)\\s+(?:(?:Dr|Prof)\\.\\s+)*(?<v>[${UC}][${LC}]+(?:[- ][${UC}][${LC}]+)?)`, "gu"),
      MITTEL, { validate: (v) => !STOPP.has(v.split(/\s+/)[0]) }],
    // ---- weitere Kennungen einer Person (immer)
    ["STEUERNUMMER", "Steuernummer",
      /(?<![\p{L}\p{N}_])(?:steuernummer|steuer-?nr\.?|st\.?-?nr\.?)\s*[:.]?\s*(?<v>\d{2,3}\/\d{3,4}\/\d{4,5}|\d{10,13})(?!\d)/giu, HOCH],
    ["KRANKENVERSICHERUNG", "Krankenversichertennummer",
      /(?<![\p{L}\p{N}_])(?:krankenversichertennummer|versichertennummer|versicherten-?nr\.?|kv-?nr\.?|kvnr|versicherten-?id)\s*[:.]?\s*(?<v>[A-Z]\d{9}|\d{9,12})(?![\p{L}\p{N}_])/giu, HOCH],
    ["KENNNUMMER", "Fall-/Patientenkennung",   // Arztbriefe: „PIZ: 1822544“, „Fallzahl: 103354008“, „E-Nr.: 172…“
      /(?<![\p{L}\p{N}_])(?:piz|pid|fn|fallzahl|fall|e-?nr\.?|h-?nr\.?|einsende-?(?:nummer|nr\.?)|histo(?:logie)?-?nr\.?|befund-?nr\.?|labor-?nr\.?|pat\.?-?(?:nr\.?|id)|kis-?nr\.?|sv[- ]?nr\.?|sv|histologie\s*\()\s*[:.#]?\s*(?<v>(?=[\p{L}\p{N}_.\/-]{4,})(?=[\p{L}\p{N}_.\/-]*\d)[A-Za-z0-9](?:[\p{L}\p{N}_.\/-]*[\p{L}\p{N}_])?)/giu, MITTEL],
    ["KENNNUMMER", "Personen-/Patientennummer",
      /(?<![\p{L}\p{N}_])(?:patienten|personal|mitglieds|versicherungsschein|policen|police|versicherungs|mandanten|schüler|matrikel|klienten|fall|aufnahme)[-\s]?(?:nr\.?|nummer|n°|no\.?|id)\s*[:.#]?\s*(?<v>(?=[\p{L}\p{N}_.\/-]*\d)[A-Za-z0-9](?:[\p{L}\p{N}_.\/-]*[\p{L}\p{N}_])?)/giu, MITTEL],
    ["KFZ", "Kfz-Kennzeichen",
      /(?<![\p{L}\p{N}_])(?:kfz-?kennzeichen|amtl\.?\s*kennzeichen|kennzeichen|nummernschild)\s*[:.]?\s*(?<v>[A-ZÄÖÜ]{1,3}[- ][A-Z]{1,2}[- ]?\d{1,4}[EH]?)(?![\p{L}\p{N}_])/giu, MITTEL],
    ["STANDORT", "GPS-Koordinaten", /(?<![\d.])-?\d{1,2}\.\d{4,7},\s?-?\d{1,3}\.\d{4,7}(?![\d.])/g, MITTEL],

    // ---- Firmen & Kunden (einstellbar, Standard an)
    ["NUMMER", "Kunden-/Vertragsnummer",
      /(?<![\p{L}\p{N}_])(?:kunden|kd|vertrags?|angebots?|auftrags?|rechnungs?|bestell(?:ungs?)?|lieferscheins?|projekts?|vorgangs?|referenz|bearbeitungs)[-\s]?(?:nr\.?|nummer|n°|no\.?|id)\s*[:.#]?\s*(?<v>(?=[\p{L}\p{N}_.\/-]*\d)[A-Za-z0-9](?:[\p{L}\p{N}_.\/-]*[\p{L}\p{N}_])?)/giu, MITTEL, { gruppe: "firmen" }],
    ["NUMMER", "USt-IdNr.",
      /(?<![\p{L}\p{N}_])(?:ust-?id(?:-?nr)?\.?|ust\.?-?idnr\.?|umsatzsteuer-?id(?:entifikationsnummer)?)\s*[:.]?\s*(?<v>[A-Z]{2}\s?\d{8,12})(?![\p{L}\p{N}_])/giu, MITTEL, { gruppe: "firmen" }],
    ["NUMMER", "Aktenzeichen",
      /(?<![\p{L}\p{N}_])(?:az\.|aktenzeichen|geschäftszeichen|kassenzeichen|ihr zeichen|unser zeichen)\s*[:.]?\s*(?<v>\d{1,4}\s?[A-Za-z]{1,4}\s?\d{1,6}\/\d{2,4}|(?=[\p{L}\p{N}_.\/-]*\d)[A-Za-z0-9](?:[\p{L}\p{N}_.\/-]*[\p{L}\p{N}_])?)/giu, MITTEL, { gruppe: "firmen" }],

    // ---- Preise & Beträge (einstellbar, Standard aus)
    ["BETRAG", "Betrag / Preis",
      /(?<![\p{L}\p{N}_.,])(?:(?:€|EUR)\s?(?:\d{1,3}(?:[.' ]\d{3})+|\d+)(?:,\d{1,2})?|(?:\d{1,3}(?:[.' ]\d{3})+|\d+)(?:,\d{1,2})?\s?(?:€|EUR|Euro)(?![\p{L}\p{N}_]))/gu, MITTEL, { gruppe: "betraege" }],

    // ---- Medizinische Inhalte (einstellbar, Standard aus)
    ["DIAGNOSE", "Diagnose (ICD-Code)",
      /(?<![\p{L}\p{N}_])[A-TV-Z]\d{2}\.\d{1,2}(?:[ ]?[GVZA](?![\p{L}\p{N}_]))?|(?<![\p{L}\p{N}_])[A-TV-Z]\d{2}[ ]?[GVZ](?![\p{L}\p{N}_])/gu, MITTEL, { gruppe: "medizin" }],
    ["DIAGNOSE", "Medizinische Angabe",
      /^[ \t]*(?:diagnosen?|dx|befund|beurteilung|anamnese|epikrise|vorerkrankungen|medikation)[ \t]*:[ \t]*(?<v>[^\n]{3,200})/gimu, MITTEL, { gruppe: "medizin" }],
    ["LABORWERT", "Laborwert",
      /(?<![\p{L}\p{N}_-])(?:CRP|PCT|Procalcitonin|Leukozyten|Leukos?|Erythrozyten|Erys?|Thrombozyten|Thrombos?|Hb|Hämoglobin|HbA1c|Hkt?|Hämatokrit|MCV|MCH|MCHC|TSH|fT3|fT4|Kreatinin|Krea|e?GFR|Harnstoff|Harnsäure|GOT|GPT|AST|ALT|GGT|γ-GT|LDH|CK(?:-MB)?|Troponin(?:\s?[IT])?|hsTnT|D-Dimere|INR|Quick|a?PTT|Ferritin|Transferrin|Vitamin\s?D3?|Vitamin\s?B12|Folsäure|Cholesterin|LDL|HDL|Triglyz?c?eride|Natrium|Kalium|Calcium|Magnesium|Phosphat|Glukose|Glucose|Blutzucker|BZ|Bilirubin|Albumin|Lipase|Amylase|PSA|NT-proBNP|BNP|IgE|IgG|IgM|BSG|Laktat|IL-6|CEA|AFP|HCG|Testosteron|Östradiol|Cortisol|Prolaktin|AMH)\s*[:=]?\s*(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?(?:\s?(?:k|tsd\.?|tausend))?(?:\s?(?:mg\/dl|mg\/l|g\/dl|g\/l|mmol\/l|µmol\/l|umol\/l|µg\/l|ng\/ml|ng\/l|pg\/ml|mU\/l|µU\/ml|U\/l|IU\/ml|\/µl|\/nl|G\/l|T\/l|%|fl|pg))?(?![\p{L}\p{N}_])/giu, MITTEL, { gruppe: "medizin" }],
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

  function scan(text, optionen = OPTIONEN) {
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
        found.push({ kind, label, text: value, start, end: start + value.length, severity, severityLabel: STUFE[severity],
          gruppe: opt.gruppe || "" });
      }
    }
    found.push(...namenFinden(text), ...firmen(text), ...kliniken(text), ...medikamente(text));
    for (let i = found.length - 1; i >= 0; i--) if (found[i].gruppe && !optionen[found[i].gruppe]) found.splice(i, 1);
    const personen = aufloesen(found).filter((f) => f.kind === "PERSON");
    found.push(...weitereNennungen(text, personen));   // „Schneider“ allein, nachdem „Thomas Schneider“ erkannt ist
    found.push(...geburtsdatenNachNamen(text, personen));   // „Albers (* 4.4.1997)“
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
  const ABKUERZUNGEN = new Set(VN.abkuerzungen || []), ABK_GROSS = new Set([...ABKUERZUNGEN].map((a) => a.toUpperCase()));
  const KOERPER = new Set(VN.koerper || []);
  const PARTIKEL = ["von und zu", "von der", "von den", "van der", "van den", "van de", "de la", "von", "van", "vom", "zur", "zu", "de", "da", "di", "del", "della", "du", "dos", "ten", "ter", "le", "la"];
  const R_PARTIKEL = sticky(`(?:${PARTIKEL.map(ci).join("|")})(?=[ \\t]+[A-ZÄÖÜ])[ \\t]+`);
  const KLEIN_PARTIKEL = `(?:${["von", "van", "de", "zu"].map(ci).join("|")})`;
  const R_INITIALEN = sticky(`(?:[A-ZÄÖÜ][a-zäöü]?\\.[ \\t]*){1,3}(?=[A-ZÄÖÜ]|${KLEIN_PARTIKEL}[ \\t])`);
  const R_MITTEL_INITIAL = sticky(`[ \\t]+[A-ZÄÖÜ]\\.(?=[ \\t]+(?:[A-ZÄÖÜ]|(?:${["von", "van", "de", "zu", "dos"].map(ci).join("|")})[ \\t]))`);
  const R_END_INITIAL = sticky("[ \\t]+[A-ZÄÖÜ]\\.(?![\\p{L}\\p{N}_])");
  const R_NOMEN_ENDUNG = /(?:ung|tion|ation|heit|keit|schaft|tät|amt|itis|ektomie|tomie|plastik|skopie|graphie|therapie|logie|ismus|ierung)$/iu;
  const R_STRASSE_DANACH = sticky("[ \\t]+[\\p{L}\\p{N}_.-]*(?:straße|strasse|str\\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|steig)(?![\\p{L}\\p{N}_])", "i");
  const R_STRASSE_WORT = /[\p{L}\p{N}_-]*(?:straße|strasse|gasse|allee|chaussee)$/iu;
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
    if (w.length > 6 && R_NOMEN_ENDUNG.test(w)) return false;   // „Rektumamputation“, „Kreisjugendamt“
    if (/^[IVXLCDM]+$/.test(w) || (versalWort(w) && w.length === 2)) return false;   // „II“, „OT“
    if (versal || (versalWort(w) && w.length >= 3)) {   // „Beatrice DE BEAUHARNAIS“, „Pierre JOUBERT“
      return versalWort(w) && w.length > 1 && !STOPP.has(w.slice(0, 1) + w.slice(1).toLowerCase())
        && !ABKUERZUNGEN.has(w) && !ABK_GROSS.has(w.toUpperCase());
    }
    return gross(w) && w.length > 1 && !STOPP.has(w) && !ORG.has(w);
  }
  function nameAb(text, pos, maxTeile = 3, komma = false) {
    const vorn = pos;
    const part = an(R_PARTIKEL, text, pos);
    if (part && !["zu", "zur", "zum", "vom", "la", "le", "da"].includes(part[0].trim().split(/\s+/)[0].toLowerCase())) pos = part.index + part[0].length;
    const m = an(R_WORT, text, pos);
    if (!m) return null;
    const versal = versalWort(m[0]) && m[0].length > 1;
    if (!nachname(m[0], versal)) return null;
    let ende = m.index + m[0].length, teile = 1;
    while (teile < maxTeile) {
      let p = ende;
      const mi = an(R_MITTEL_INITIAL, text, p);   // „Holger M. Recklinghausen“
      if (mi) p = mi.index + mi[0].length;
      const sep = an(R_LEER, text, p) || (komma && an(R_KOMMA, text, p));
      if (!sep) break;
      const nachKomma = sep[0].includes(",");
      p = sep.index + sep[0].length;
      const pt = an(R_PARTIKEL, text, p);
      if (pt && !versal) p = pt.index + pt[0].length;
      const n = an(R_WORT, text, p);
      if (n && (an(R_STRASSE_DANACH, text, n.index + n[0].length) || R_STRASSE_WORT.test(n[0]))) break;   // dort beginnt die Adresse
      if (!n || !(nachname(n[0], versal) || (nachKomma && nachname(n[0])))) {
        if (n && ORG.has(n[0])) return null;    // „Musterfirma GmbH“ ist kein Name
        break;
      }
      ende = n.index + n[0].length; teile++;
    }
    const ei = an(R_END_INITIAL, text, ende);   // „Hendlbein H.“
    if (ei) ende = ei.index + ei[0].length;
    return [vorn, ende];
  }
  const nurLeer = (text, a, b) => R_LEER_GANZ.test(text.slice(a, b));
  const R_LISTENANFANG = /(?:^[ \t]*(?:(?:\d{1,3}[.)]|[•*\-–])[ \t]*)?|[:;][ \t]*)$/u;
  const R_DATUM_VOR = /\d[.]?[ \t]*\n?$/u, R_DATUM_NACH = sticky("\\.?[ \\t]*\\d");
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
  const TITELWORT = "(?:(?:(?:Univ|UNIV|univ|Priv|PRIV|Ao)\\.?[ \\t-]?)?(?:Prof|PROF|Doz|DOZ|DDr|DDR|Drs|Dr|DR|PD|Prim|PRIM|Mag|"
    + "Dipl\\.-[A-Za-zäöü]+|Dipl|med|MED|dent|vet|univers|univer|univ|UNIV|jur|phil|rer\\.?[ \\t]?nat|mult|habil|"
    + `h\\.[ \\t]?c|OA|OÄ|Ass|MSc|MBA|PhD|MD)(?:\\.(?:in|a)?|ª|in\\.?${NA}|a\\.?${NA})?|Kollegin|Kollege)`;
  const R_TITEL = R(`${NB}(?:(?:Hr\\.|Fr\\.|Herrn?|HERRN?|Frau|FRAU|Mr\\.?|Mrs\\.?|Ms\\.?|Miss)[ \\t]+(?:${TITELWORT}[ \\t]*)*`
    + "|(?:(?:Univ|UNIV|Priv|PRIV)\\.?[ \\t-]?(?:Prof|PROF|Doz|DOZ)|Prof|PROF|Doz|DOZ|DDr|DDR|Drs|Dr|DR|Prim|PRIM)"
    + `(?:\\.(?:in|a)?|ª|in\\.?${NA}|a\\.?${NA})?(?:[ \\t]+|(?=med|MED|univ|UNIV|rer|phil|jur|dent|vet))(?:${TITELWORT}[ \\t]*)*`
    + "|(?:PD|OA|OÄ|Ass\\.?)[ \\t]+(?=(?:Dr|Prof|Doz)))", "");
  const R_TITEL_KETTE = sticky(`(?:${TITELWORT}[ \\t]*)*`);
  const R_ANREDE = R("(?:^|(?<=[\\s>„\"(]))(?:liebe[rs]?|hallo|hi|hey|moin|servus|dear|hello|ciao|salut|guten (?:tag|morgen|abend))[ \\t]+", "i");
  const R_GRUSS = R("^[ \\t]*(?:(?:mit[ \\t]+)?(?:[a-zäöüß.]+[ \\t]+){0,3}(?:grüßen|grüssen|grüße|grüsse|gruß|gruss)|lg|vg|mfg|"
    + "hochachtungsvoll|best regards|kind regards|best wishes|warm regards|regards|cheers|bis bald|bis dann|dein|deine|euer|eure|ihr|ihre)"
    + "[ \\t]*[,.!]?[ \\t]*(?:\\n[ \\t]*){1,2}", "im");
  const R_GRUSS_ZEILE = R("^[ \\t]*(?:dein|deine|euer|eure|lg|vg|gruß|grüße|cheers)[ \\t,]+", "im");
  const R_FELD = R(`${NB}(?:vor-? und (?:nach|zu)name|(?:nach)?name,[ ]?vorname|vorname,[ ]?(?:nach)?name|vollständiger name|`
    + "vorname[n]?|nachname|familienname|zuname|geburtsname|rufname|name (?:des kindes|der mutter|des vaters|der patientin|des patienten)|"
    + "patient(?:in)?|mieter(?:in)?|vermieter(?:in)?|kunde|kundin|kontoinhaber(?:in)?|inhaber(?:in)?|antragsteller(?:in)?|"
    + "arbeitnehmer(?:in)?|mitarbeiter(?:in)?|ehemann|ehefrau|ehepartner(?:in)?|kind|sohn|tochter|vater|mutter|schüler(?:in)?|"
    + "empfänger(?:in)?|absender(?:in)?|versicherte[r]?|versicherungsnehmer(?:in)?|bewerber(?:in)?|ansprechpartner(?:in)?|"
    + "verfasser(?:in)?|erziehungsberechtigte[r]?|unterzeichner(?:in)?|teilnehmer(?:in)?|mandant(?:in)?|klient(?:in)?|"
    + "beschuldigte[r]?|kläger(?:in)?|beklagte[r]?|zeug(?:e|in)|betreuer(?:in)?|vormund|full name|first name|last name|surname|"
    + "given name|name)[ \\t]*:[ \\t]*", "i");
  const R_BERUF = R(`${NB}(?:[a-zäöü-]*(?:arzt|ärztin|direktor|direktorin|leiter|leiterin|psychologe|psychologin|therapeut|therapeutin|`
    + "orthoptist|orthoptistin|pfleger|pflegerin|hebamme|primar|primaria|primarius|sachbearbeiter|sachbearbeiterin))[ \\t]*:[ \\t]*", "i");
  const R_VERFASST = R(`${NB}(?:(?:geschrieben|erstellt|diktiert|vidiert|untersucht|befundet|unterschrieben|freigegeben|behandelt|`
    + "überwiesen)[ \\t]+(?:von|durch)|untersuchung durch|gez\\.)[: \\t]+", "i");
  const R_FAMILIE = R(`${NB}(?:Familie|Fam\\.|Eheleute|Ehepaar|Geschwister)[ \\t]+`, "");
  const R_VERWANDT = R(`${NB}(?:Sohn|Tochter|Kind|Enkel(?:in|kind)?|Bruder|Schwester|Ehemann|Ehefrau|Mann|Partner(?:in)?|`
    + "Freund(?:in)?|Lebensgefährt(?:e|in)|Verlobte[r]?|Vater|Mutter|Papa|Mama|Oma|Opa|Onkel|Tante|Cousine?|Neffe|Nichte|Schwager|"
    + "Schwägerin|Kollege|Kollegin|Chef(?:in)?|Nachbar(?:in)?|Patient(?:in|en)?|Pat\\.|Klient(?:in)?|Mandant(?:in)?|Schüler(?:in)?|"
    + "Azubi|Ex-Mann|Ex-Frau|Exmann|Exfrau|Stief(?:sohn|tochter|vater|mutter)|Pflegekind|Baby)[ \\t]+", "");
  const R_PATIENT = R(`${NB}(?:Patient(?:in|en)?|Pat\\.)\\s+`, "");   // nach „Patientin“ steht fast immer ein Name
  const R_NUR_INITIAL = sticky("([A-ZÄÖÜ]\\.)(?=[ \\t]*(?:[,;:)]|\\s+[a-zäöüß]|\\n?$))");
  const R_UND = sticky("[ \\t]+und[ \\t]+");
  const R_ALTER = sticky(`[ \\t]*\\([ \\t]*\\d{1,2}${NA}`);
  const R_ZEILENENDE = sticky("[ \\t]*(?:\\n|$|,)");
  const R_NACH_ANREDE = sticky("[ \\t]*(?:[,!:;]|\\n|$)");
  const R_NACH_GRUSSZEILE = sticky("[ \\t]*(?:\\n|$|[.!])");

  function anStellen(text) {
    const out = [];
    const nimm = (m, teile, { komma = false, danach = null, bedingung = null, titel = true, und = false, initialAllein = false } = {}) => {
      let pos = m.index + m[0].length;
      if (titel) { const k = an(R_TITEL_KETTE, text, pos); pos = k.index + k[0].length; }
      const ini = an(R_INITIALEN, text, pos);
      let span = nameAb(text, ini ? ini.index + ini[0].length : pos, teile, komma);
      if (span === null && initialAllein) {   // „Herr K.“, „Frau I.“ – abgekürzter Name
        const nur = an(R_NUR_INITIAL, text, pos);
        if (nur) { out.push(person(text, nur.index, nur.index + nur[1].length)); return; }
      }
      if (span && ini) span = [ini.index, span[1]];
      if (span && und) {   // „Drs. Seiler und Wantzer“
        const u = an(R_UND, text, span[1]);
        const zweiter = u ? nameAb(text, u.index + u[0].length, 2) : null;
        if (zweiter) out.push(person(text, zweiter[0], zweiter[1]));
      }
      if (!span) return;
      if (danach && !an(danach, text, span[1])) return;
      if (bedingung && !bedingung(span)) return;
      out.push(person(text, span[0], span[1]));
    };
    const alle = (re, fn) => { for (const m of text.matchAll(re)) fn(m); };
    alle(R_TITEL, (m) => nimm(m, 3, { komma: true, und: true, initialAllein: true }));
    alle(R_PATIENT, (m) => nimm(m, 3, { komma: true, initialAllein: true }));
    alle(R_BERUF, (m) => nimm(m, 3));
    alle(R_VERFASST, (m) => nimm(m, 3));
    alle(R_ANREDE, (m) => nimm(m, 2, { danach: R_NACH_ANREDE }));
    alle(R_GRUSS, (m) => nimm(m, 3, { danach: R_ZEILENENDE }));
    alle(R_GRUSS_ZEILE, (m) => nimm(m, 3, { danach: R_NACH_GRUSSZEILE }));
    alle(R_FELD, (m) => nimm(m, 4, { komma: true }));
    alle(R_FAMILIE, (m) => nimm(m, 2));
    const wortAb = (p) => { const re = new RegExp(WORT, "gu"); re.lastIndex = p; return re.exec(text); };
    alle(R_VERWANDT, (m) => {
      if (m[0].startsWith("Patient") || m[0].startsWith("Pat.")) return;   // eigene Regel R_PATIENT
      nimm(m, 2, { bedingung: (sp) => { const w = wortAb(sp[0]); return (w && vorname(w[0], ALLE)) || Boolean(an(R_ALTER, text, sp[1])); } });
    });
    return out;
  }

  const namenFinden = (text) => [...ausListe(text), ...anStellen(text)];

  const R_ARTIKEL_DAVOR = new RegExp(`${NB}(?:der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines|kein|keine|sein|seine|seinen|`
    + "seinem|seiner|ihr|ihre|ihren|ihrem|ihrer|mein|meine|unser|unsere|zur|zum|im|am|vom|beim|ins|ans|beide|beiden)[ \\t]+$", "iu");
  const R_SATZANFANG = /(?:^|[.!?\n])[ \t\u00a0]*$/u;

  function weitereNennungen(text, personen) {
    const teile = new Set();
    for (const f of personen) {
      for (const t of f.text.match(new RegExp(WORT, "gu")) || []) {
        if (t.length >= 3 && (gross(t) || versalWort(t)) && !STOPP.has(t) && !ORG.has(t) && !ABKUERZUNGEN.has(t)) teile.add(t);
      }
    }
    const out = [];
    for (const t of [...teile].sort()) {
      if (KOERPER.has(t)) continue;   // Dr. Leber ja – aber nicht jede „Leber“ im Befund
      const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      for (const m of text.matchAll(new RegExp(`(?<!\\p{L})(?<!-)${esc}(?=s?(?!-|\\p{L}))`, "gu"))) {
        if (R_ARTIKEL_DAVOR.test(text.slice(Math.max(0, m.index - 12), m.index))) continue;   // „die Leber“, „im Schädel“
        if (MEHRDEUTIG.has(t) && R_SATZANFANG.test(text.slice(0, m.index))) continue;       // „Ernst der Lage“
        out.push(person(text, m.index, m.index + t.length));
      }
    }
    return out;
  }

  let R_NACH_NAME = null;
  function geburtsdatenNachNamen(text, personen) {
    // „Albers (* 4.4.1997)“, „Haefner, Heinz, * 21.3.1979“, „Andrea Ilgner, 21.10.1982, wohnhaft …“
    R_NACH_NAME ||= new RegExp(`[ \\t]*[,(]?[ \\t]*(?:(?<m>\\*|geb\\.?(?:[ \\t]*am)?[ \\t]*:?)[ \\t]*)?(?<d>${DATUM})(?<n>[ \\t]*[,)]|[ \\t]+wohnhaft)?`, "iuy");
    const out = [];
    for (const f of personen) {
      const m = an(R_NACH_NAME, text, f.end);
      if (m && (m.groups.m || m.groups.n)) {
        const s = m.index + m[0].indexOf(m.groups.d, m[0].length - m.groups.d.length - (m.groups.n || "").length);
        out.push({ kind: "GEBURTSDATUM", label: "Geburtsdatum", text: m.groups.d, start: s, end: s + m.groups.d.length,
          severity: MITTEL, severityLabel: STUFE[MITTEL], gruppe: "" });
      }
    }
    return out;
  }
  // ---------------------------------------------------------------- Firmen & Medikamente (wie datenwaechter/inhalte.py)
  const OPTIONEN = { firmen: true, betraege: false, medizin: false, themen_nur_mit_person: true };
  function setOptions(o) { for (const k of Object.keys(OPTIONEN)) if (o && typeof o[k] === "boolean") OPTIONEN[k] = o[k]; }
  const IDENTITAET = new Set(["PERSON", "ADRESSE", "GEBURTSDATUM", "EMAIL", "TELEFON", "IBAN", "KREDITKARTE", "STEUER_ID",
    "STEUERNUMMER", "SOZIALVERSICHERUNG", "KRANKENVERSICHERUNG", "AUSWEIS", "KFZ", "STANDORT", "KENNNUMMER", "GERAETE_ID"]);
  const R_RECHTSFORM = /(?<![\p{L}\p{N}_&])(?:GmbH\s*&\s*Co\.\s*KG(?:aA)?|AG\s*&\s*Co\.\s*KG|gGmbH|GmbH|mbH|UG\s*\(haftungsbeschränkt\)|UG|KGaA|AG|KG|OHG|GbR|PartG(?:\s*mbB)?|e\.\s?K\.|e\.\s?Kfm\.|e\.\s?V\.|eG|SE|Ltd\.?|Limited|Inc\.?|LLC|Corp\.?|S\.A\.|B\.V\.|N\.V\.|Sp\.\s?z\s?o\.\s?o\.|s\.r\.o\.)(?![\p{L}\p{N}_])/gu;
  const FWORT = "[\\p{L}\\p{N}_][\\p{L}\\p{N}_.&'+-]*";
  const VERBINDER = new Set(["&", "und", "für", "+"]);
  const KEINE_FIRMA_DAVOR = new Set(["Der", "Die", "Das", "Den", "Dem", "Des", "Firma", "Fa.", "Unternehmen", "Kunde", "Kundin",
    "Auftraggeber", "Auftragnehmer", "An", "Von", "Bei", "Mit", "Für", "Und", "Ihre", "Ihr", "Unsere", "Unser", "Eine", "Ein",
    "Sitz", "Gesellschaft:", "Registergericht", "Amtsgericht", "Wir", "Sie"]);
  const istZiffer = (c) => c >= "0" && c <= "9";
  function firmenwort(w) {
    if ([...w].filter(istZiffer).length >= 2 || (w.endsWith(".") && w !== "Dr." && w !== "St.")) return false;
    return istGross(w[0]) || (istZiffer(w[0]) && [...w].some((c) => c.toLowerCase() !== c.toUpperCase()));
  }
  function firmen(text) {
    const out = [];
    for (const m of text.matchAll(R_RECHTSFORM)) {
      const ende = m.index + m[0].length;
      if (m[0].startsWith("AG") && /^[ \t]+[A-ZÄÖÜ][a-zäöüß]/.test(text.slice(ende, ende + 3))) continue;   // „AG München“
      const zeile = text.lastIndexOf("\n", m.index - 1) + 1;
      const davor = text.slice(zeile, m.index);
      const toks = [...davor.matchAll(new RegExp(FWORT, "gu"))];
      let start = null, anzahl = 0;
      for (let i = toks.length - 1; i >= 0; i--) {
        const t = toks[i], tEnde = t.index + t[0].length;
        if (!/^[ \t]*(?:[&+][ \t]*)?$/.test(davor.slice(tEnde, start !== null ? start : davor.length))) break;
        const w = t[0];
        if (firmenwort(w)) { start = t.index; anzahl++; }
        else if (VERBINDER.has(w) && anzahl) start = t.index;
        else break;
        if (anzahl >= 5) break;
      }
      if (start === null) continue;
      if (["KG", "AG", "SE", "eG"].includes(m[0]) && /(?:ung|ion|tät|heit|keit|schaft|therapie|gymnastik)$/u.test(davor.slice(start).trim())) {
        continue;   // „Krankengymnastik KG“, „Bewegungsverschlechterung KG“: medizinische Abkürzungen
      }
      let teil = davor.slice(start);
      for (;;) {
        const erster = new RegExp(FWORT, "uy").exec(teil);
        if (erster && (KEINE_FIRMA_DAVOR.has(erster[0]) || VERBINDER.has(erster[0]))) {
          teil = teil.slice(erster[0].length).replace(/^[ \t&+]+/, "");
          continue;
        }
        break;
      }
      if (!teil.trim() || !firmenwort(teil.trim())) continue;
      const s = m.index - teil.length;
      out.push({ kind: "FIRMA", label: "Firma / Organisation", text: text.slice(s, ende), start: s, end: ende,
        severity: MITTEL, severityLabel: STUFE[MITTEL], gruppe: "firmen" });
    }
    return out;
  }
  const R_KLINIK = new RegExp("(?<![\\p{L}\\p{N}_-])(?:(?:Städt\\.|Städtisches|Ev\\.|Evangelisches|Kath\\.|Katholisches|Kreis|St\\.|Sankt)[ \\t]+)?"
    + "(?:[A-ZÄÖÜ][\\p{L}\\p{N}_-]*?(?:[Kk]rankenhaus(?:es)?|[Kk]linikum|[Kk]liniken|[Kk]linik|[Ss]pital|[Ss]anatorium|"
    + "KRANKENHAUS|KLINIKUM|KLINIK|SPITAL)|Klinikum|Krankenhaus|Spital|Uniklinik(?:um)?|Universitätsklinikum|"
    + "UNIKLINIK(?:UM)?|UNIVERSITÄTSKLINIKUM|MVZ|Praxis(?:gemeinschaft)?(?=[ \\t]+(?:Dr|Prof|[A-ZÄÖÜ][a-zäöü]+[ \\t]+[A-ZÄÖÜ])))"
    + `${NA}((?:[ \\t]+(?:(?:der|des|für|am|an der|im|St\\.|Sankt|Bad|Dr\\.|Prof\\.)[ \\t]+)?[A-ZÄÖÜ][\\p{L}\\p{N}_.-]*${NA}){0,4})`, "gu");
  // „Diakonissenkrankenhaus Berlin“, „Klinikum DD“, „Sankt-Klara-Spital Klagenfurt“ – nicht „das Krankenhaus“
  function kliniken(text) {
    const out = [];
    for (const m of text.matchAll(R_KLINIK)) {
      const name = m[1] || "";
      const kern = m[0].slice(0, m[0].length - name.length).trim().split(/\s+/).at(-1);
      if (["Klinikum", "Krankenhaus", "Spital", "Klinik", "MVZ", "Praxis"].includes(kern) && !name.trim()) continue;
      if (["klinik", "kliniken", "uniklinik", "uniklinikum", "universitätsklinikum", "poliklinik"].includes(kern.toLowerCase())
          && !name.trim()) continue;   // „in der Uniklinik“ ist kein Name
      out.push({ kind: "FIRMA", label: "Klinik / Einrichtung", text: m[0], start: m.index, end: m.index + m[0].length,
        severity: MITTEL, severityLabel: STUFE[MITTEL], gruppe: "firmen" });
    }
    return out;
  }
  const MEDIKAMENTE = VN.medikamente || [];
  const R_MEDIKAMENT = MEDIKAMENTE.length ? new RegExp(`(?<![\\p{L}\\p{N}_-])(${[...MEDIKAMENTE].sort((a, b) => b.length - a.length)
    .map((m) => m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?:[ \\t]+\\d+(?:[.,]\\d+)?[ \\t]?(?:mg|µg|mcg|g|ml|IE|I\\.E\\.|%))?(?![\\p{L}\\p{N}_-])`, "giu") : null;
  const medikamente = (text) => (R_MEDIKAMENT ? [...text.matchAll(R_MEDIKAMENT)] : []).map((m) => ({ kind: "MEDIKAMENT",
    label: "Medikament", text: m[0], start: m.index, end: m.index + m[0].length, severity: MITTEL, severityLabel: STUFE[MITTEL], gruppe: "medizin" }));


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
  const CATS = Object.entries(CAT_DATA).filter(([k]) => !k.startsWith("_")).map(([key, c]) => ({
    key, name: c.name, stufe: c.stufe,
    terms: c.begriffe.map((raw) => {
      const strong = raw.startsWith("!");
      let word = raw.replace(/^!/, "");
      const prefix = word.endsWith("*");
      word = word.replace(/\*$/, "");
      const esc = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+");
      return { strong, re: new RegExp(`(?<!${W})${esc}${prefix ? W + "*" : `(?!${W})`}`, "iu") };
    }),
  }));

  // Diese Themen sind nur heikel, wenn eine Person erkennbar ist (wie content_check.nur_mit_personenbezug)
  const PERSONENBEZOGEN = new Set(["familie", "gesundheit", "finanzen", "recht", "arbeit", "besonders", "kinder"]);

  function contentCheck(text, findings = null) {
    const categories = [], hints = [];
    let severity = 0;
    const personFrei = findings && OPTIONEN.themen_nur_mit_person && !findings.some((f) => IDENTITAET.has(f.kind));
    for (const cat of CATS) {
      if (personFrei && PERSONENBEZOGEN.has(cat.key)) continue;
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

  const api = { scan, contentCheck, Anonymizer, ibanValid, luhnValid, steuerIdValid, setOptions, optionen: OPTIONEN,
    IDENTITAET, PERSONENBEZOGEN,
    HOCH, MITTEL, NIEDRIG };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DWDetect = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
