// KI-Aktionsleiste im Browser (wird bei Bedarf in die Seite eingeschleust – nur nach Rechtsklick, nur in diesem Tab).
// Gleiches Aussehen wie im Windows-Fenster: Kopfzeile, Vorschau, Suchfeld, Aktionen mit Symbol, Tastatur-Bedienung.
// Tippen filtert – oder wird als eigene Anweisung ausgeführt.
(() => {
  if (globalThis.__dwKI) return;

  const SYMBOLE = [["umformulier", "✎"], ["kürz", "✂"], ["kuerz", "✂"], ["freundlich", "☺"], ["professionell", "◆"],
    ["rechtschreib", "✓"], ["korrigier", "✓"], ["übersetz", "⇄"], ["englisch", "⇄"], ["zusammenfass", "≡"],
    ["antwort", "↩"], ["tweet", "#"], ["mail", "✉"]];
  const symbol = (name) => (SYMBOLE.find(([k]) => name.toLowerCase().includes(k)) || [0, "✦"])[1];
  const MODUS = { einfuegen: ["fügt ein", "blue"], anzeigen: ["zeigt an", "gray"] };

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .card { position: fixed; z-index: 2147483647; width: 360px; background: var(--bg); color: var(--text);
            border: 1px solid var(--border); border-radius: 14px; overflow: hidden;
            box-shadow: 0 18px 50px rgba(0,0,0,.22), 0 2px 8px rgba(0,0,0,.08);
            font: 14px/1.4 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
            animation: pop .12s ease-out; }
    @keyframes pop { from { opacity: 0; transform: translateY(-4px) scale(.98); } }
    .card { --bg: #fff; --text: #18181b; --muted: #71717a; --border: #e4e4e7; --hover: #f4f4f5; --active: #ecfdf3;
            --accent: #2e7d32; --field: #f4f4f5; --icon: #f4f4f5; --blue-bg: #e3f2fd; --blue: #0d47a1;
            --gray-bg: #f3f4f6; --gray: #4b5563; }
    @media (prefers-color-scheme: dark) {
      .card { --bg: #232326; --text: #f4f4f5; --muted: #a1a1aa; --border: #3f3f46; --hover: #2e2e33; --active: #1f3322;
              --accent: #66bb6a; --field: #2e2e33; --icon: #2e2e33; --blue-bg: #172a3a; --blue: #90caf9;
              --gray-bg: #303036; --gray: #c4c4cc; }
    }
    .head { display: flex; align-items: center; gap: 8px; padding: 12px 14px 4px; }
    .head b { font-size: 14.5px; }
    .spark { color: var(--accent); font-size: 15px; }
    .server { margin-left: auto; color: var(--muted); font-size: 11.5px; }
    .server.off { color: #c62828; }
    .preview { padding: 0 14px 8px; color: var(--muted); font-style: italic; font-size: 12.5px;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .search { display: flex; align-items: center; gap: 6px; margin: 0 12px; padding: 0 10px; background: var(--field);
              border-radius: 9px; border: 1px solid transparent; }
    .search:focus-within { border-color: var(--accent); }
    .search span { color: var(--muted); }
    input { flex: 1; border: 0; outline: 0; background: transparent; color: var(--text); font: inherit; padding: 8px 0; }
    input::placeholder { color: var(--muted); }
    .list { padding: 6px; max-height: 330px; overflow: auto; }
    .row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 9px; cursor: pointer; }
    .row.on { background: var(--active); }
    .icon { width: 26px; height: 26px; border-radius: 7px; background: var(--icon); color: var(--accent);
            display: grid; place-items: center; font-size: 13px; flex: none; }
    .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pill { font-size: 11px; padding: 1px 8px; border-radius: 999px; flex: none; }
    .pill.blue { background: var(--blue-bg); color: var(--blue); }
    .pill.gray { background: var(--gray-bg); color: var(--gray); }
    .pill.green { background: var(--active); color: var(--accent); }
    .foot { display: flex; gap: 12px; padding: 8px 14px; border-top: 1px solid var(--border); color: var(--muted); font-size: 11.5px; }
    .text { padding: 4px 14px 0; white-space: pre-wrap; max-height: 45vh; overflow: auto; }
    .note { padding: 6px 14px 0; color: var(--muted); font-size: 11.5px; }
    .btns { display: flex; gap: 8px; padding: 12px 14px 14px; }
    button { font: inherit; font-size: 13px; padding: 6px 13px; border-radius: 8px; border: 0; background: var(--hover);
             color: var(--text); cursor: pointer; }
    button.main { background: var(--accent); color: #fff; font-weight: 600; }
    .close { margin-left: auto; color: var(--muted); cursor: pointer; padding: 0 2px; }
    .toast { position: fixed; z-index: 2147483647; right: 18px; bottom: 18px; background: #18181b; color: #fff;
             padding: 10px 14px; border-radius: 10px; font: 13px "Segoe UI", system-ui, sans-serif; max-width: 420px;
             box-shadow: 0 8px 30px rgba(0,0,0,.25); animation: pop .12s ease-out; }`;

  function mount() {
    document.querySelectorAll("datenwaechter-ki").forEach((n) => n.remove());
    const host = document.createElement("datenwaechter-ki");
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    root.append(style);
    document.documentElement.append(host);
    return { host, root };
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function anchorRect() {
    const st = globalThis.__datenwaechterSel || {};
    let r = null;
    try {
      if (st.range) r = st.range.getBoundingClientRect();
      if ((!r || (!r.width && !r.height)) && st.el?.getBoundingClientRect) r = st.el.getBoundingClientRect();
    } catch { /* egal */ }
    return r || { left: innerWidth / 2 - 180, bottom: 80, top: 60 };
  }

  // Neben die Markierung setzen: unten, falls Platz – sonst oben; reicht beides nicht, wird die Liste gekürzt
  function place(card) {
    const r = anchorRect();
    const list = card.querySelector(".list, .text");
    const w = 360;
    const below = innerHeight - r.bottom - 16, above = r.top - 16;
    const space = Math.max(below, above);
    if (list && card.offsetHeight > space) {
      const rest = card.offsetHeight - list.offsetHeight;
      list.style.maxHeight = `${Math.max(110, space - rest)}px`;
    }
    const h = card.offsetHeight;
    const x = Math.min(Math.max(8, r.left), innerWidth - w - 8);
    const y = below >= h || below >= above ? r.bottom + 8 : r.top - h - 8;
    card.style.left = `${x}px`;
    card.style.top = `${Math.max(8, Math.min(y, innerHeight - h - 8))}px`;
  }

  function capture() {
    const el = document.activeElement;
    const st = { kind: "page", el, text: "" };
    const isField = el && (el.tagName === "TEXTAREA" ||
      (el.tagName === "INPUT" && /^(text|search|email|url|tel|)$/i.test(el.type || "")));
    if (isField) {
      let a = el.selectionStart, b = el.selectionEnd;
      if (a === b) { a = 0; b = el.value.length; }
      Object.assign(st, { kind: "input", start: a, end: b, text: el.value.slice(a, b) });
    } else {
      const sel = getSelection();
      const editable = el && el.isContentEditable;
      if (sel.rangeCount && !sel.isCollapsed) {
        st.range = sel.getRangeAt(0).cloneRange();
        st.text = sel.toString();
        st.kind = editable && el.contains(st.range.commonAncestorContainer) ? "editable" : "page";
      } else if (editable) {
        st.range = document.createRange();
        st.range.selectNodeContents(el);
        st.text = el.innerText;
        st.kind = "editable";
      }
    }
    globalThis.__datenwaechterSel = st;
    return { text: st.text, kind: st.kind };
  }

  function toast(text, ms = 3500) {
    const { host, root } = mount();
    root.append(el("div", "toast", text));
    if (ms) setTimeout(() => host.remove(), ms);
  }

  // Aktionsleiste öffnen; actions = [{id, name, mode}], info = {server, extern}
  function open(actions, info) {
    const st = globalThis.__datenwaechterSel || {};
    const { host, root } = mount();
    const card = el("div", "card");
    const head = el("div", "head");
    head.append(el("span", "spark", "✦"), el("b", "", "Mit KI bearbeiten"),
      el("span", info.server ? "server" : "server off", info.server || "kein KI-Server"));
    const preview = el("div", "preview", `„${(st.text || "").replace(/\s+/g, " ").trim()}“`);
    const search = el("div", "search");
    const input = el("input");
    input.placeholder = "Suchen oder eigene Anweisung …";
    search.append(el("span", "", "⌕"), input);
    const list = el("div", "list");
    const foot = el("div", "foot");
    foot.append(el("span", "", "↑↓ wählen"), el("span", "", "↵ ausführen"), el("span", "", "Esc schließen"));
    card.append(head, preview, search, list, foot);
    root.append(card);

    let rows = [], index = 0, lastQ = null;
    const close = () => { host.remove(); document.removeEventListener("mousedown", outside, true); };
    const outside = (e) => { if (!e.composedPath().includes(host)) close(); };
    document.addEventListener("mousedown", outside, true);

    function render() {
      const q = input.value.trim();
      if (q !== lastQ) { lastQ = q; index = 0; }
      const items = actions.filter((a) => !q || a.name.toLowerCase().includes(q.toLowerCase()));
      if (q && !items.some((a) => a.name.toLowerCase() === q.toLowerCase())) {
        items.push({ custom: q, name: `„${q}“ als Anweisung`, mode: "ersetzen" });
      }
      list.replaceChildren();
      rows = items.map((a, i) => {
        const row = el("div", "row");
        row.append(el("span", "icon", a.custom ? "✦" : symbol(a.name)), el("span", "name", a.name));
        if (a.custom) row.append(el("span", "pill green", "eigene Anweisung"));
        else if (MODUS[a.mode]) row.append(el("span", `pill ${MODUS[a.mode][1]}`, MODUS[a.mode][0]));
        row.addEventListener("mouseenter", () => { index = i; mark(); });
        row.addEventListener("mousedown", (e) => { e.preventDefault(); index = i; choose(); });
        list.append(row);
        return { row, a };
      });
      index = Math.min(index, Math.max(0, rows.length - 1));
      mark();
    }
    function mark() {
      rows.forEach((r, i) => r.row.classList.toggle("on", i === index));
      rows[index]?.row.scrollIntoView({ block: "nearest" });
    }
    function choose() {
      const a = rows[index]?.a;
      if (!a) return;
      close();
      if (!info.server) { toast("Kein KI-Server eingerichtet – im Datenwächter unter Einstellungen → KI-Server."); return; }
      busy(a.custom ? "Eigene Anweisung" : a.name);
      const request = a.custom ? { custom: a.custom, mode: "ersetzen" } : { id: a.id };
      chrome.runtime.sendMessage({ type: "kiRun", request: { ...request, text: st.text } }).then(apply)
        .catch((e) => apply({ ok: false, error: String(e) }));
    }
    input.addEventListener("input", render);
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();   // Tastenkürzel der Webseite nicht auslösen
      if (e.key === "ArrowDown" || e.key === "Tab") { e.preventDefault(); index = (index + 1) % rows.length; mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); index = (index - 1 + rows.length) % rows.length; mark(); }
      else if (e.key === "Enter") { e.preventDefault(); choose(); }
      else if (e.key === "Escape") { e.preventDefault(); close(); st.el?.focus?.(); }
    });
    render();
    place(card);
    input.focus();
    return true;
  }

  function busy(name) {
    toast(`✦ ${name} … KI arbeitet`, 0);
  }

  function resultCard(r, note) {
    const { host, root } = mount();
    const card = el("div", "card");
    const head = el("div", "head");
    const x = el("span", "close", "✕");
    head.append(el("span", "spark", "✦"), el("b", "", r.ok ? r.name : "KI-Aktion fehlgeschlagen"), x);
    card.append(head, el("div", "text", r.ok ? r.result : r.error || "Unbekannter Fehler"));
    if (note) card.append(el("div", "note", note));
    const btns = el("div", "btns");
    if (r.ok) {
      const copy = el("button", "main", "Kopieren");
      copy.addEventListener("click", () => navigator.clipboard.writeText(r.result).then(() => host.remove()));
      btns.append(copy);
    }
    const close = el("button", "", "Schließen");
    close.addEventListener("click", () => host.remove());
    x.addEventListener("click", () => host.remove());
    btns.append(close);
    card.append(btns);
    root.append(card);
    place(card);
    btns.querySelector("button").focus();
  }

  function apply(r) {
    document.querySelectorAll("datenwaechter-ki").forEach((n) => n.remove());
    const st = globalThis.__datenwaechterSel || {};
    const note = r?.sent_to ? `An ${r.sent_to} gesendet${r.anonymized ? " – persönliche Daten vorher anonymisiert" : ""}` : "";
    if (!r?.ok) return resultCard(r || {}, "");
    const editable = st.kind === "input" || st.kind === "editable";
    if (r.mode === "anzeigen" || !editable || !st.el?.isConnected) return resultCard(r, note);

    const insert = r.mode === "einfuegen" ? `\n\n${r.result}` : r.result;
    st.el.focus();
    if (st.kind === "input") {
      const s = r.mode === "einfuegen" ? st.end : st.start;
      st.el.setSelectionRange(s, st.end);
      if (!document.execCommand("insertText", false, insert)) {   // hält Strg+Z und React & Co. synchron
        st.el.setRangeText(insert, s, st.end, "end");
        st.el.dispatchEvent(new Event("input", { bubbles: true }));
      }
    } else {
      const range = st.range;
      if (r.mode === "einfuegen") range.collapse(false);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      if (!document.execCommand("insertText", false, insert)) {
        range.deleteContents();
        range.insertNode(document.createTextNode(insert));
      }
    }
    toast(`✔ ${r.name} – ${r.mode === "einfuegen" ? "eingefügt" : "ersetzt"} (Rückgängig: Strg+Z)${note ? ". " + note : ""}`, 4000);
  }

  globalThis.__dwKI = { capture, open, busy, apply, toast };
})();
