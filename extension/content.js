// Datenwächter – fängt in KI-Chats alle Upload-Wege ab: Einfügen (Strg+V), Drag & Drop, „Datei hinzufügen“
// (Büroklammer, auch versteckte Eingabefelder und showOpenFilePicker). Der Inhalt wird lokal geprüft,
// BEVOR die Seite ihn bekommt. Bei Funden: Warnung mit Liste + Inhalts-Check („Du lädst gerade … hoch“).
(() => {
  "use strict";
  const DW = globalThis.DWDetect;
  const anon = new DW.Anonymizer();          // gleiche Werte -> gleiche Platzhalter, solange der Tab offen ist
  const own = new WeakSet();                  // von uns erneut ausgelöste Ereignisse nicht nochmal prüfen
  const TEXT_EXT = /\.(txt|md|csv|tsv|json|xml|ya?ml|ini|cfg|conf|env|log|html?|py|js|ts|java|cs|go|rb|php|sql|sh|ps1|bat|toml|properties|eml)$/i;
  const HOST_ONLY = /\.(pdf|docx|png|jpe?g|webp|bmp|gif|tiff?)$/i;
  const MAX_TEXT = 5 * 1024 * 1024;
  const MAX_HOST = 25 * 1024 * 1024;
  const MIN_CONTENT_CHECK = 80;              // kürzere Texte nicht auf Themen prüfen (zu viele Fehlalarme)
  const MIN_LLM_CHECK = 300;                 // ab dieser Länge fragt die Erweiterung zusätzlich das Sprachmodell
  const COLORS = { 3: "#c62828", 2: "#ef6c00", 1: "#757575", 0: "#1565c0" };
  const STUFE = { 3: "hoch", 2: "mittel", 1: "niedrig" };

  window.addEventListener("paste", onPaste, true);
  window.addEventListener("drop", onDrop, true);
  window.addEventListener("change", onFileInput, true);
  window.addEventListener("copy", onCopy, true);
  window.addEventListener("message", onPageMessage);

  const host = (request) => chrome.runtime.sendMessage({ type: "host", request }).catch((e) => ({ ok: false, error: String(e) }));
  const hostStatus = () => chrome.runtime.sendMessage({ type: "ping" }).catch(() => ({ ok: false }));

  function block(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }

  function saveCaret() {
    const el = document.activeElement;
    const sel = window.getSelection();
    const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    return () => {
      el?.focus?.();
      if (range) { sel.removeAllRanges(); sel.addRange(range); }
    };
  }

  // ------------------------------------------------------------------ Text prüfen (Einfügen / Ziehen)
  async function checkText(text) {
    const findings = DW.scan(text);
    let content = text.length >= MIN_CONTENT_CHECK ? DW.contentCheck(text) : null;
    if (text.length >= MIN_LLM_CHECK) {
      const status = await hostStatus();
      if (status?.ok && status.llm) {
        toast("Lokale KI prüft den Inhalt …");
        const reply = await host({ action: "check_text", text });
        if (reply?.ok) content = reply.content;
      }
    }
    return { findings, content: content?.warning ? content : null };
  }

  async function askAboutText(text, verb) {
    const { findings, content } = await checkText(text);
    if (!findings.length && !content) return { choice: "pass" };
    const choice = await showDialog({
      title: findings.length ? `Du ${verb} ${findings.length} sensible Angabe(n) ein` : "Bitte kurz prüfen, was du einfügst",
      content: content ? [content] : [],
      rows: findings.map((f) => ({ ...f, where: "Text" })),
      actions: findings.length
        ? [["anon", "✔ Anonymisiert einfügen", true], ["orig", "Original einfügen"], ["cancel", "Abbrechen"]]
        : [["cancel", "Abbrechen", true], ["orig", "Trotzdem einfügen"]],
    });
    return { choice, findings };
  }

  // ------------------------------------------------------------------ Einfügen
  function onPaste(e) {
    if (own.has(e) || !e.clipboardData) return;
    const dt = e.clipboardData;
    const target = e.target;
    const files = [...dt.files];
    if (files.length) {
      block(e);
      const restoreCaret = saveCaret();
      checkFiles(files).then((result) => {
        restoreCaret();
        if (result) firePaste(target, { files: result });
      });
      return;
    }
    const text = dt.getData("text/plain");
    if (!text) return;
    // Regeln + Stichwörter sind synchron: nur blockieren, wenn es etwas zu fragen gibt (oder die KI gefragt wird)
    const quick = DW.scan(text).length || (text.length >= MIN_CONTENT_CHECK && DW.contentCheck(text).warning);
    if (!quick && text.length < MIN_LLM_CHECK) return;
    block(e);
    const html = dt.getData("text/html"); // nur während des Ereignisses lesbar
    const restoreCaret = saveCaret();
    askAboutText(text, "fügst").then(({ choice, findings }) => {
      restoreCaret();
      if (choice === "anon") firePaste(target, { text: anon.anonymize(text, findings) });
      else if (choice === "orig" || choice === "pass") firePaste(target, { text, html });
    });
  }

  function firePaste(target, { text, html, files = [] }) {
    const d = new DataTransfer();
    if (text) d.setData("text/plain", text);
    if (html) d.setData("text/html", html);
    for (const f of files) d.items.add(f);
    const ev = new ClipboardEvent("paste", { clipboardData: d, bubbles: true, cancelable: true, composed: true });
    own.add(ev);
    target.dispatchEvent(ev);
    // Kein Editor hat das Ereignis verarbeitet (z. B. einfaches Textfeld) -> selbst einfügen
    if (!ev.defaultPrevented && text) document.execCommand("insertText", false, text);
  }

  // ------------------------------------------------------------------ Drag & Drop
  function onDrop(e) {
    if (own.has(e) || !e.dataTransfer) return;
    const dt = e.dataTransfer;
    const files = [...dt.files];
    const { target, clientX, clientY } = e;
    const fire = (d) => {
      const ev = new DragEvent("drop", { dataTransfer: d, bubbles: true, cancelable: true, composed: true, clientX, clientY });
      own.add(ev);
      target.dispatchEvent(ev);
    };
    const leave = () => target.dispatchEvent(new DragEvent("dragleave", { bubbles: true, clientX, clientY }));

    if (!files.length) {
      const text = dt.getData("text/plain");
      if (!text) return;
      const quick = DW.scan(text).length || (text.length >= MIN_CONTENT_CHECK && DW.contentCheck(text).warning);
      if (!quick && text.length < MIN_LLM_CHECK) return;
      block(e);
      askAboutText(text, "ziehst").then(({ choice, findings }) => {
        if (choice === "cancel") return leave();
        const d = new DataTransfer();
        d.setData("text/plain", choice === "anon" ? anon.anonymize(text, findings) : text);
        fire(d);
      });
      return;
    }
    block(e);
    checkFiles(files).then((result) => {
      if (!result) return leave();
      const d = new DataTransfer();
      for (const f of result) d.items.add(f);
      fire(d);
    });
  }

  // ------------------------------------------------------------------ „Datei hinzufügen“ / Büroklammer
  function onFileInput(e) {
    const input = e.target;
    if (own.has(e) || !(input instanceof HTMLInputElement) || input.type !== "file" || !input.files?.length) return;
    e.stopImmediatePropagation();
    checkFiles([...input.files]).then((result) => {
      if (!result) { input.value = ""; return; }
      const d = new DataTransfer();
      for (const f of result) d.items.add(f);
      input.files = d.files;
      const ev = new Event("change", { bubbles: true });
      own.add(ev);
      input.dispatchEvent(ev);
    });
  }

  // showOpenFilePicker-Weg (page_hook.js schickt die Dateien hierher)
  function onPageMessage(e) {
    if (e.source !== window || e.data?.__datenwaechter !== "check") return;
    const { id, files } = e.data;
    checkFiles(files).then((result) => window.postMessage({ __datenwaechter: "result", id, files: result }, "*"));
  }

  // ------------------------------------------------------------------ KI-Antwort kopieren -> Platzhalter zurück
  function onCopy(e) {
    const text = String(window.getSelection() || "");
    if (!/\[[A-Z_]+_\d+\]/.test(text)) return;
    const restored = anon.restore(text);
    if (restored === text) return;
    e.clipboardData.setData("text/plain", restored);
    e.preventDefault();
    toast("Platzhalter beim Kopieren durch die Originalwerte ersetzt");
  }

  // ------------------------------------------------------------------ Dateien prüfen
  async function checkFiles(files) {
    toast(`Datenwächter prüft ${files.length} Datei(en) …`);
    const status = await hostStatus();
    const reports = [];
    for (const f of files) reports.push(await scanFile(f, !!status?.ok)); // nacheinander: Platzhalter bleiben eindeutig
    const rows = reports.flatMap((r) => r.rows.map((row) => ({ ...row, where: r.file.name })));
    const content = reports.map((r) => r.content).filter((c) => c?.warning);
    const notes = reports.flatMap((r) => r.notes.map((n) => `${r.file.name}: ${n}`));
    const info = reports.flatMap((r) => r.info);

    if (!rows.length && !content.length && !notes.length) {
      toast("✔ Keine sensiblen Daten gefunden" + (info.length ? " (Bildmotiv nicht bewertet)" : ""));
      return files;
    }
    const canAnon = reports.some((r) => r.output);
    const actions = canAnon
      ? [["anon", "✔ Anonymisierte Fassung hochladen", true], ["orig", "Original hochladen"], ["cancel", "Abbrechen"]]
      : [["cancel", "Abbrechen", true], ["orig", "Trotzdem hochladen"]];
    const choice = await showDialog({
      title: rows.length ? `${rows.length} sensible Angabe(n) in ${reports.filter((r) => r.rows.length).length} Datei(en)`
        : content.length ? "Bitte kurz prüfen, was du hochlädst" : "Datei(en) konnten nicht vollständig geprüft werden",
      content, rows, notes: [...notes, ...info],
      actions,
      hint: canAnon ? "Bilder und PDFs werden geschwärzt (Kasten mit Platzhalter), Gesichter verpixelt." : "",
    });
    if (choice === "cancel") return null;
    if (choice === "orig") return files;
    const out = [];
    for (const r of reports) {
      if (r.output) out.push(r.output);
      else if (!r.rows.length) out.push(r.file);
      // Funde, aber keine anonymisierte Fassung möglich -> Datei weglassen
    }
    return out;
  }

  async function scanFile(file, hostOk) {
    const base = { file, rows: [], notes: [], info: [], content: null, output: null };
    const isText = TEXT_EXT.test(file.name) || file.type.startsWith("text/") || file.type === "application/json";
    const viaHost = hostOk && file.size <= MAX_HOST && (isText || HOST_ONLY.test(file.name) || file.type.startsWith("image/"));

    if (viaHost) {
      const reply = await host({ action: "scan_file", name: file.name, data_b64: await toBase64(file), mapping: anon.exportMapping() });
      if (reply?.ok) {
        if (reply.mapping) anon.importMapping(reply.mapping);
        const output = reply.output
          ? new File([Uint8Array.from(atob(reply.output.b64), (c) => c.charCodeAt(0))], reply.output.name, { type: reply.output.mime })
          : null;
        return {
          ...base, output, notes: reply.notes || [], info: reply.info || [],
          rows: reply.rows.map((r) => ({ ...r, severityLabel: STUFE[r.severity] })),
          content: reply.content?.warning ? reply.content : null,
        };
      }
      if (!isText) return { ...base, notes: [`Prüfung fehlgeschlagen: ${reply?.error || "unbekannter Fehler"}`] };
    }
    if (isText) {
      if (file.size > MAX_TEXT) return { ...base, notes: ["Zu groß für die Prüfung im Browser"] };
      const text = await file.text();
      const findings = DW.scan(text);
      const content = DW.contentCheck(text);
      const dot = file.name.lastIndexOf(".");
      const name = dot > 0 ? `${file.name.slice(0, dot)}_anonymisiert${file.name.slice(dot)}` : `${file.name}_anonymisiert.txt`;
      return {
        ...base, rows: findings, content: content.warning ? content : null,
        output: findings.length ? new File([anon.anonymize(text, findings)], name, { type: "text/plain" }) : null,
      };
    }
    if (HOST_ONLY.test(file.name) || file.type.startsWith("image/")) {
      return { ...base, notes: ["Lokaler Scanner nicht installiert – Bilder, PDF und Word können nicht geprüft werden"] };
    }
    return base; // z. B. Audio, Video, ZIP: (noch) nicht prüfbar
  }

  function toBase64(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(",")[1] || "");
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    });
  }

  // ------------------------------------------------------------------ Oberfläche (Shadow DOM, kein innerHTML mit Daten)
  const CSS = `
    :host { all: initial; }
    .bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 2147483647; display: flex;
          align-items: center; justify-content: center; font: 14px/1.4 system-ui, "Segoe UI", sans-serif; }
    .card { background: #fff; color: #222; width: min(700px, 94vw); max-height: 88vh; border-radius: 12px;
            overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,.35); }
    .head { color: #fff; padding: 14px 18px; font-weight: 600; font-size: 16px; }
    .content { margin: 12px 18px 0; padding: 10px 12px; border-radius: 8px; background: #fff3e0; color: #5d4037; }
    .content b { display: block; margin-bottom: 2px; }
    .content small { color: #8d6e63; }
    .sub { padding: 10px 18px 0; color: #555; }
    .list { overflow: auto; padding: 8px 18px; }
    table { width: 100%; border-collapse: collapse; }
    td { padding: 6px 4px; border-bottom: 1px solid #eee; vertical-align: top; word-break: break-all; }
    td.sev { font-weight: 600; white-space: nowrap; word-break: normal; }
    td.where { color: #777; font-size: 12px; }
    .notes { padding: 0 18px; color: #777; font-size: 12px; }
    .btns { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 18px 16px; }
    button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid #ccc; background: #f5f5f5; cursor: pointer; }
    button.main { background: #2e7d32; border-color: #2e7d32; color: #fff; }
    .toast { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; background: #263238; color: #fff;
             padding: 10px 14px; border-radius: 8px; font: 13px system-ui, "Segoe UI", sans-serif; }
    @media (prefers-color-scheme: dark) {
      .card { background: #1e1e1e; color: #eee; } td { border-color: #333; } .sub, .notes { color: #aaa; }
      .content { background: #3e2723; color: #ffe0b2; } .content small { color: #bcaaa4; }
      button { background: #2a2a2a; color: #eee; border-color: #444; }
    }`;

  function mount() {
    const h = document.createElement("datenwaechter-ui");
    const root = h.attachShadow({ mode: "closed" });
    root.append(el("style", { textContent: CSS }));
    document.documentElement.append(h);
    return { host: h, root };
  }

  function el(tag, props = {}, ...children) {
    const n = document.createElement(tag);
    Object.assign(n, props);
    n.append(...children);
    return n;
  }

  function showDialog({ title, rows = [], content = [], notes = [], actions, hint }) {
    return new Promise((resolve) => {
      document.querySelectorAll("datenwaechter-toast").forEach((n) => n.remove());
      const { host: h, root } = mount();
      const worst = Math.max(0, ...rows.map((r) => r.severity || 1), ...content.map((c) => c.severity || 0));
      const done = (choice) => { h.remove(); document.removeEventListener("keydown", onKey, true); resolve(choice); };
      const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done("cancel"); } };
      document.addEventListener("keydown", onKey, true);

      const card = el("div", { className: "card" },
        el("div", { className: "head", textContent: `⚠ Achtung: ${title}`, style: `background:${COLORS[worst] || COLORS[2]}` }));
      for (const c of content) {
        const box = el("div", { className: "content" }, el("b", { textContent: "🧠 " + c.warning + " Willst du das wirklich?" }));
        if (c.description) box.append(el("div", { textContent: c.description }));
        box.append(el("small", { textContent: c.source || "Erkannt an Stichwörtern" }));
        card.append(box);
      }
      if (rows.length) {
        card.append(el("div", { className: "sub", textContent: "Diese Daten würden an den KI-Anbieter übertragen. " + (hint || "") }));
        const table = el("table");
        for (const r of rows) {
          table.append(el("tr", {},
            el("td", { className: "sev", textContent: r.severityLabel || STUFE[r.severity] || "", style: `color:${COLORS[r.severity] || "#777"}` }),
            el("td", { textContent: r.label }),
            el("td", { textContent: r.display }),
            el("td", { className: "where", textContent: r.where || "" })));
        }
        card.append(el("div", { className: "list" }, table));
      }
      if (notes.length) card.append(el("div", { className: "notes" }, ...notes.map((n) => el("div", { textContent: "ℹ " + n }))));
      const btns = el("div", { className: "btns" });
      for (const [id, label, main] of actions) {
        const b = el("button", { textContent: label, className: main ? "main" : "" });
        b.addEventListener("click", () => done(id));
        btns.append(b);
      }
      card.append(btns);
      const bg = el("div", { className: "bg" }, card);
      bg.addEventListener("click", (e) => { if (e.target === bg) done("cancel"); });
      root.append(bg);
      btns.querySelector("button")?.focus();
    });
  }

  let toastTimer;
  function toast(text) {
    document.querySelectorAll("datenwaechter-toast").forEach((n) => n.remove());
    clearTimeout(toastTimer);
    const h = document.createElement("datenwaechter-toast");
    const root = h.attachShadow({ mode: "closed" });
    root.append(el("style", { textContent: CSS }), el("div", { className: "toast", textContent: text }));
    document.documentElement.append(h);
    toastTimer = setTimeout(() => h.remove(), 2500);
  }
})();
