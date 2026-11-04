// Datenwächter – fängt Einfügen (Strg+V), Drag & Drop und Datei-Auswahl auf KI-Chat-Seiten ab,
// prüft den Inhalt lokal und fragt bei Funden nach, BEVOR die Seite die Daten bekommt.
(() => {
  "use strict";
  const DW = globalThis.DWDetect;
  const anon = new DW.Anonymizer();          // gleiche Werte -> gleiche Platzhalter, solange der Tab offen ist
  const own = new WeakSet();                  // von uns erneut ausgelöste Ereignisse nicht nochmal prüfen
  const TEXT_EXT = /\.(txt|md|csv|tsv|json|xml|ya?ml|ini|cfg|conf|env|log|html?|py|js|ts|java|cs|go|rb|php|sql|sh|ps1|bat|toml|properties|eml)$/i;
  const HOST_EXT = /\.(pdf|docx)$/i;
  const MAX_TEXT = 5 * 1024 * 1024;
  const MAX_HOST = 25 * 1024 * 1024;
  const COLORS = { 3: "#c62828", 2: "#ef6c00", 1: "#757575" };

  window.addEventListener("paste", onPaste, true);
  window.addEventListener("drop", onDrop, true);
  window.addEventListener("change", onFileInput, true);
  window.addEventListener("copy", onCopy, true);

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
    const findings = DW.scan(text);
    if (!findings.length) return;
    block(e);
    const html = dt.getData("text/html"); // nur während des Ereignisses lesbar
    const restoreCaret = saveCaret();
    showDialog({
      title: `Du fügst ${findings.length} sensible Angabe(n) ein`,
      rows: findings.map((f) => ({ ...f, where: "Text" })),
      actions: [
        ["anon", "✔ Anonymisiert einfügen", true],
        ["orig", "Original einfügen"],
        ["cancel", "Abbrechen"],
      ],
    }).then((choice) => {
      restoreCaret();
      if (choice === "anon") firePaste(target, { text: anon.anonymize(text, findings) });
      else if (choice === "orig") firePaste(target, { text, html });
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
      const findings = text ? DW.scan(text) : [];
      if (!findings.length) return;
      block(e);
      showDialog({
        title: `Der gezogene Text enthält ${findings.length} sensible Angabe(n)`,
        rows: findings.map((f) => ({ ...f, where: "Text" })),
        actions: [["anon", "✔ Anonymisiert ablegen", true], ["orig", "Original ablegen"], ["cancel", "Abbrechen"]],
      }).then((choice) => {
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

  // ------------------------------------------------------------------ Büroklammer / Datei-Auswahl
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
    const reports = await Promise.all(files.map(scanFile));
    const rows = [];
    for (const r of reports) {
      for (const f of r.findings) rows.push({ ...f, where: r.file.name });
      if (r.note) rows.push({ severity: 2, severityLabel: "?", label: r.note, display: "nicht geprüft", where: r.file.name });
    }
    if (!rows.length) {
      toast("✔ Keine sensiblen Daten gefunden");
      return files;
    }
    const withFindings = reports.filter((r) => r.findings.length);
    const actions = [];
    if (withFindings.length) actions.push(["anon", "✔ Anonymisierte Fassung hochladen", true]);
    actions.push(["orig", "Original hochladen"], ["cancel", "Abbrechen"]);
    const choice = await showDialog({
      title: withFindings.length
        ? `${rows.filter((r) => r.kind).length} sensible Angabe(n) in ${withFindings.length} Datei(en)`
        : "Datei(en) konnten nicht geprüft werden",
      rows,
      actions,
      hint: withFindings.some((r) => r.newName?.endsWith(".txt") && !r.file.name.endsWith(".txt"))
        ? "Bei PDF/Word wird der anonymisierte Text als .txt hochgeladen (Layout geht verloren)." : "",
    });
    if (choice === "cancel") return null;
    if (choice === "orig") return files;
    const out = [];
    for (const r of reports) {
      if (!r.findings.length) out.push(r.file);
      else if (r.anonymized != null) out.push(new File([r.anonymized], r.newName, { type: "text/plain" }));
      // Funde, aber keine anonymisierte Fassung möglich -> Datei weglassen
    }
    return out;
  }

  async function scanFile(file) {
    const base = { file, findings: [] };
    if (TEXT_EXT.test(file.name) || file.type.startsWith("text/") || file.type === "application/json") {
      if (file.size > MAX_TEXT) return { ...base, note: "Zu groß für die Prüfung im Browser" };
      const text = await file.text();
      const findings = DW.scan(text);
      const dot = file.name.lastIndexOf(".");
      const newName = dot > 0 ? `${file.name.slice(0, dot)}_anonymisiert${file.name.slice(dot)}` : `${file.name}_anonymisiert.txt`;
      return { ...base, findings, anonymized: findings.length ? anon.anonymize(text, findings) : null, newName };
    }
    if (HOST_EXT.test(file.name)) {
      if (file.size > MAX_HOST) return { ...base, note: "Zu groß für die Prüfung" };
      let reply;
      try {
        reply = await chrome.runtime.sendMessage({ type: "scanFile", name: file.name, b64: await toBase64(file) });
      } catch (err) {
        reply = { ok: false, error: String(err) };
      }
      if (!reply?.ok) {
        return { ...base, note: reply?.noHost ? "Lokaler Scanner (Python) nicht installiert – PDF/Word nicht prüfbar" : `Prüfung fehlgeschlagen: ${reply?.error}` };
      }
      const findings = reply.findings.map((f) => ({ ...f, severityLabel: { 3: "hoch", 2: "mittel", 1: "niedrig" }[f.severity] }));
      return { ...base, findings, anonymized: reply.anonymized, newName: reply.name, note: reply.error };
    }
    return base; // Bilder usw. werden (noch) nicht geprüft
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
    .card { background: #fff; color: #222; width: min(680px, 94vw); max-height: 86vh; border-radius: 12px;
            overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,.35); }
    .head { color: #fff; padding: 14px 18px; font-weight: 600; font-size: 16px; }
    .sub { padding: 10px 18px 0; color: #555; }
    .list { overflow: auto; padding: 8px 18px; }
    table { width: 100%; border-collapse: collapse; }
    td { padding: 6px 4px; border-bottom: 1px solid #eee; vertical-align: top; word-break: break-all; }
    td.sev { font-weight: 600; white-space: nowrap; word-break: normal; }
    td.where { color: #777; font-size: 12px; }
    .btns { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 18px 16px; }
    button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid #ccc; background: #f5f5f5; cursor: pointer; }
    button.main { background: #2e7d32; border-color: #2e7d32; color: #fff; }
    .toast { position: fixed; right: 18px; bottom: 18px; z-index: 2147483647; background: #263238; color: #fff;
             padding: 10px 14px; border-radius: 8px; font: 13px system-ui, "Segoe UI", sans-serif; }
    @media (prefers-color-scheme: dark) {
      .card { background: #1e1e1e; color: #eee; } td { border-color: #333; } .sub { color: #aaa; }
      button { background: #2a2a2a; color: #eee; border-color: #444; }
    }`;

  function mount() {
    const host = document.createElement("datenwaechter-ui");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    root.append(style);
    document.documentElement.append(host);
    return { host, root };
  }

  function el(tag, props = {}, ...children) {
    const n = document.createElement(tag);
    Object.assign(n, props);
    n.append(...children);
    return n;
  }

  function showDialog({ title, rows, actions, hint }) {
    return new Promise((resolve) => {
      document.querySelectorAll("datenwaechter-toast").forEach((n) => n.remove());
      const { host, root } = mount();
      const worst = Math.max(...rows.map((r) => r.severity || 1));
      const done = (choice) => { host.remove(); document.removeEventListener("keydown", onKey, true); resolve(choice); };
      const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done("cancel"); } };
      document.addEventListener("keydown", onKey, true);

      const table = el("table");
      for (const r of rows) {
        table.append(el("tr", {},
          el("td", { className: "sev", textContent: r.severityLabel, style: `color:${COLORS[r.severity] || "#777"}` }),
          el("td", { textContent: r.label + (r.source === "ki" ? " (KI)" : "") }),
          el("td", { textContent: r.display }),
          el("td", { className: "where", textContent: r.where || "" })));
      }
      const btns = el("div", { className: "btns" });
      for (const [id, label, main] of actions) {
        const b = el("button", { textContent: label, className: main ? "main" : "" });
        b.addEventListener("click", () => done(id));
        btns.append(b);
      }
      const card = el("div", { className: "card" },
        el("div", { className: "head", textContent: `⚠ Achtung: ${title}`, style: `background:${COLORS[worst]}` }),
        el("div", { className: "sub", textContent: "Diese Daten würden an den KI-Anbieter übertragen. " + (hint || "") }),
        el("div", { className: "list" }, table),
        btns);
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
    const host = document.createElement("datenwaechter-toast");
    const root = host.attachShadow({ mode: "closed" });
    root.append(el("style", { textContent: CSS }), el("div", { className: "toast", textContent: text }));
    document.documentElement.append(host);
    toastTimer = setTimeout(() => host.remove(), 2500);
  }
})();
