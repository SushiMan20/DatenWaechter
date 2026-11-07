// KI-Aktionsleiste im Browser (wird bei Bedarf in die Seite eingeschleust – nur nach Rechtsklick, nur in diesem Tab).
// Gleiches Aussehen wie im Windows-Fenster: Kopfzeile, Vorschau, Suchfeld, Aktionen mit Symbol, Tastatur-Bedienung.
// Tippen filtert – oder wird als eigene Anweisung ausgeführt. Nach der Wahl bleibt die Leiste stehen und zeigt einen
// drehenden Kreis, bis die KI fertig ist (Abbrechen jederzeit); Ergebnis, Häkchen oder Fehler erscheinen an derselben Stelle.
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
    .busy { display: flex; align-items: flex-start; gap: 10px; padding: 4px 14px 14px; }
    .spin { width: 22px; height: 22px; border-radius: 50%; border: 3px solid var(--border); border-top-color: var(--accent);
            animation: spin .8s linear infinite; flex: none; margin-top: 2px; display: grid; place-items: center;
            font-size: 12px; font-weight: 700; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .spin { animation-duration: 2.5s; } }
    .spin.ok { animation: none; border-color: var(--accent); color: var(--accent); }
    .spin.err { animation: none; border-color: #c62828; color: #c62828; }
    .busy .t { flex: 1; min-width: 0; }
    .busy .t b { display: block; font-size: 14px; }
    .busy .t b.err { color: #c62828; }
    .busy .t small { display: block; color: var(--muted); font-size: 11.5px; overflow-wrap: anywhere; }
    .link { background: none; border: 0; padding: 0; color: var(--accent); text-decoration: underline; cursor: pointer;
            font: inherit; font-size: 12.5px; flex: none; }
    .toast { position: fixed; z-index: 2147483647; right: 18px; bottom: 18px; background: #18181b; color: #fff;
             padding: 10px 14px; border-radius: 10px; font: 13px "Segoe UI", system-ui, sans-serif; max-width: 420px;
             box-shadow: 0 8px 30px rgba(0,0,0,.25); animation: pop .12s ease-out; }`;

  let gezeigt = null;   // zuletzt gezeigtes Fenster (für zustand())

  function mount() {
    document.querySelectorAll("datenwaechter-ki").forEach((n) => n.remove());
    const host = document.createElement("datenwaechter-ki");
    const root = host.attachShadow({ mode: "closed" });
    gezeigt = { host, root };
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

  // Wo steht die Maus? Den Rechtsklick merkt sich content.js auf KI-Seiten; sonst: Ende der Markierung
  function anker() {
    const z = globalThis.__dwZeiger;
    if (z && Date.now() - z.t < 120000 && z.x >= 0 && z.y >= 0 && z.x <= innerWidth && z.y <= innerHeight) {
      return { left: z.x + 12, right: z.x - 12, top: z.y - 12, bottom: z.y + 12, zeiger: true };
    }
    const st = globalThis.__datenwaechterSel || {};
    try {
      const rects = st.range ? [...st.range.getClientRects()].filter((q) => q.width || q.height) : [];
      const r = rects.at(-1);
      if (r) return { left: r.right + 4, right: r.right, top: r.top, bottom: r.bottom + 4 };
    } catch { /* egal */ }
    const r = anchorRect();
    return { left: r.left, right: r.left, top: r.top, bottom: r.bottom + 4 };
  }

  // Neben Maus bzw. Markierung: rechts unten, falls Platz – sonst links bzw. oben; reicht beides nicht, wird die Liste
  // gekürzt. fest = {left, top}: an derselben Stelle bleiben (Arbeits-, Ergebnis- und Fehleranzeige).
  function place(card, fest) {
    const w = 360;
    if (fest) {
      const h = card.offsetHeight;
      card.style.left = `${Math.min(Math.max(8, fest.left), innerWidth - w - 8)}px`;
      card.style.top = `${Math.max(8, Math.min(fest.oben ? fest.bottom - h : fest.top, innerHeight - h - 8))}px`;
      return;
    }
    const a = anker();
    const list = card.querySelector(".list, .text");
    const below = innerHeight - a.bottom - 8, above = a.top - 8;
    const space = Math.max(below, above);
    if (list && card.offsetHeight > space) {
      const rest = card.offsetHeight - list.offsetHeight;
      list.style.maxHeight = `${Math.max(110, space - rest)}px`;
    }
    const h = card.offsetHeight;
    const x = a.left + w <= innerWidth - 8 ? a.left : a.right - w;
    const oben = !(below >= h || below >= above);
    const y = oben ? a.top - h : a.bottom;
    card.style.left = `${Math.min(Math.max(8, x), innerWidth - w - 8)}px`;
    card.style.top = `${Math.max(8, Math.min(y, innerHeight - h - 8))}px`;
    card.dataset.oben = oben ? "1" : "";
  }

  // Wo die Karte gerade steht (damit Ergebnis/Fehler genau dort erscheinen)
  function stelle(card) {
    const r = card.getBoundingClientRect();
    return { left: r.left, top: r.top, bottom: r.bottom, oben: card.dataset.oben === "1" };
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

  // ------------------------------------------------------------------ Während die KI arbeitet
  let aktuell = null;   // { host, card, abgebrochen, fest }

  function arbeiten(host, card, name) {
    const fest = stelle(card);
    card.querySelectorAll(".search, .list, .foot, .busy").forEach((n) => n.remove());
    const busy = el("div", "busy");
    const spin = el("div", "spin");
    const t = el("div", "t");
    const titel = el("b", "", `${name} …`);
    const info = el("small", "", "KI arbeitet");
    t.append(titel, info);
    const knopf = el("button", "link", "Abbrechen");
    busy.append(spin, t, knopf);
    card.append(busy);
    place(card, fest);
    const lauf = { host, card, spin, titel, info, knopf, abgebrochen: false, fest: stelle(card) };
    const start = Date.now();
    const uhr = setInterval(() => {
      const s = Math.round((Date.now() - start) / 1000);
      if (!host.isConnected || lauf.ende) return clearInterval(uhr);
      info.textContent = `KI arbeitet${s ? ` · ${s} s` : ""}`;
    }, 1000);
    const abbrechen = () => { lauf.abgebrochen = true; lauf.ende = true; host.remove(); globalThis.__datenwaechterSel?.el?.focus?.(); };
    knopf.addEventListener("click", abbrechen);
    knopf.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Escape") { e.preventDefault(); abbrechen(); } });
    knopf.focus();
    aktuell = lauf;
    return lauf;
  }

  function fertig(lauf, text, ms = 2200) {
    lauf.ende = true;
    lauf.spin.className = "spin ok";
    lauf.spin.textContent = "✓";
    lauf.titel.textContent = text;
    lauf.info.textContent = "";
    lauf.knopf.remove();
    place(lauf.card, lauf.fest);
    setTimeout(() => lauf.host.remove(), ms);
  }

  function fehler(lauf, text) {
    lauf.ende = true;
    lauf.spin.className = "spin err";
    lauf.spin.textContent = "!";
    lauf.titel.textContent = "Hat nicht geklappt";
    lauf.titel.className = "err";
    lauf.info.textContent = text;
    lauf.knopf.textContent = "Schließen";
    lauf.knopf.replaceWith(lauf.knopf.cloneNode(true));
    lauf.card.querySelector(".busy .link").addEventListener("click", () => lauf.host.remove());
    place(lauf.card, lauf.fest);
    setTimeout(() => lauf.host.remove(), 12000);
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
      if (!info.server) { close(); toast("Kein KI-Server eingerichtet – im Datenwächter unter Einstellungen → KI-Server."); return; }
      document.removeEventListener("mousedown", outside, true);   // ab jetzt bleibt die Leiste stehen
      const lauf = arbeiten(host, card, a.custom ? "Eigene Anweisung" : a.name);
      const request = a.custom ? { custom: a.custom, mode: "ersetzen" } : { id: a.id };
      chrome.runtime.sendMessage({ type: "kiRun", request: { ...request, text: st.text } }).then((r) => apply(r, lauf))
        .catch((e) => apply({ ok: false, error: String(e) }, lauf));
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

  // Aktion ohne Leiste (direkt aus dem Menü): kleine Karte an der Maus mit drehendem Kreis
  function busy(name) {
    const st = globalThis.__datenwaechterSel || {};
    const { host, root } = mount();
    const card = el("div", "card");
    const head = el("div", "head");
    head.append(el("span", "spark", "✦"), el("b", "", "Mit KI bearbeiten"));
    card.append(head, el("div", "preview", `„${(st.text || "").replace(/\s+/g, " ").trim()}“`));
    root.append(card);
    place(card);
    arbeiten(host, card, name);
  }

  function resultCard(r, note, fest) {
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
    place(card, fest);
    btns.querySelector("button").focus();
  }

  function apply(r, lauf = aktuell) {
    if (lauf?.abgebrochen) {   // Abbrechen gedrückt: spätes Ergebnis verwerfen
      if (lauf === aktuell) aktuell = null;
      return;
    }
    if (lauf) aktuell = null;
    const sichtbar = lauf && lauf.host.isConnected;
    const st = globalThis.__datenwaechterSel || {};
    const note = r?.sent_to ? `An ${r.sent_to} gesendet${r.anonymized ? " – persönliche Daten vorher anonymisiert" : ""}` : "";
    if (!r?.ok) {
      if (sichtbar) return fehler(lauf, r?.error || "Unbekannter Fehler");
      return resultCard(r || {}, "");
    }
    const editable = st.kind === "input" || st.kind === "editable";
    if (r.mode === "anzeigen" || !editable || !st.el?.isConnected) return resultCard(r, note, sichtbar ? lauf.fest : undefined);

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
    const was = r.mode === "einfuegen" ? "Eingefügt" : "Ersetzt";
    if (sichtbar) {
      fertig(lauf, `${was} – Rückgängig: Strg+Z`);
      if (note) lauf.info.textContent = note;
    } else {
      toast(`✔ ${r.name} – ${was.toLowerCase()} (Rückgängig: Strg+Z)${note ? ". " + note : ""}`, 4000);
    }
  }

  // Zustand für Tests und Fehlersuche: offen?, arbeitet?, fertig?, Position – ohne Inhalte
  function zustand() {
    const card = gezeigt?.host?.isConnected && gezeigt.root.querySelector(".card");
    if (!card) return { offen: false };
    const r = card.getBoundingClientRect();
    return { offen: true, left: Math.round(r.left), top: Math.round(r.top), arbeitet: !!card.querySelector(".spin:not(.ok):not(.err)"),
      fertig: !!card.querySelector(".spin.ok"), fehler: !!card.querySelector(".spin.err"),
      titel: card.querySelector(".busy b")?.textContent || "" };
  }

  globalThis.__dwKI = { capture, open, busy, apply, toast, zustand };
})();
